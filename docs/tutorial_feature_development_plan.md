# 漫画群星：大集结 - 自动新手引导功能开发计划

## 文档信息

| 项目名称 | ok-jump 自动新手引导功能 |
|---------|------------------------|
| 文档版本 | v1.0.0 |
| 创建日期 | 2026-03-09 |
| 参考项目 | ok-wuthering-waves (鸣潮工具) |
| 当前项目版本 | 1.0.0 |

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术需求分析](#2-技术需求分析)
3. [开发阶段与版本迭代](#3-开发阶段与版本迭代)
4. [实施细节](#4-实施细节)
5. [测试策略](#5-测试策略)
6. [交付物](#6-交付物)
7. [风险评估与缓解](#7-风险评估与缓解)

---

## 1. 项目概述

### 1.1 功能定义

#### 1.1.1 目的

自动新手引导功能旨在为《漫画群星：大集结》游戏提供智能化的新手教程自动化解决方案，帮助用户：

- **自动完成新手教程流程**：无需手动操作，自动识别并完成游戏内的新手引导步骤
- **降低学习成本**：新用户可快速上手游戏，减少重复性操作
- **提升用户体验**：自动化处理繁琐的引导对话、教学战斗等环节

#### 1.1.2 核心目标

| 目标 | 描述 | 优先级 |
|-----|------|-------|
| 引导流程自动化 | 自动识别并执行新手引导的各个步骤 | P0 |
| 对话自动跳过 | 智能检测对话界面并自动跳过 | P0 |
| 引导点击执行 | 识别引导箭头、高亮区域并自动点击 | P0 |
| 教学战斗辅助 | 自动完成教学战斗环节 | P1 |
| 进度持久化 | 保存用户引导进度，支持断点续传 | P1 |
| 多语言支持 | 支持中英文游戏客户端 | P2 |

### 1.2 鸣潮工具参考方案

#### 1.2.1 图像识别流程参考

鸣潮工具 (ok-wuthering-waves) 提供了成熟的图像识别架构，本功能将参考其以下实现：

```
┌─────────────────────────────────────────────────────────────┐
│                    鸣潮工具图像识别架构                        │
├─────────────────────────────────────────────────────────────┤
│  BaseWWTask.py (47KB)                                       │
│  ├── find_feature() - 特征匹配核心方法                        │
│  ├── wait_for_feature() - 等待特征出现                        │
│  ├── click_feature() - 点击特征位置                          │
│  └── 场景检测与导航逻辑                                       │
├─────────────────────────────────────────────────────────────┤
│  WWScene.py                                                 │
│  ├── detect_scene() - 场景检测入口                           │
│  ├── _check_xxx() - 各场景检测方法                           │
│  └── wait_for_scene() - 等待特定场景                         │
├─────────────────────────────────────────────────────────────┤
│  COCO Feature System                                        │
│  ├── coco_detection.json - 特征定义配置                       │
│  ├── 模板匹配阈值: 0.8 (默认)                                 │
│  └── 支持多分辨率缩放                                         │
└─────────────────────────────────────────────────────────────┘
```

#### 1.2.2 操作流程参考

鸣潮工具的操作执行模式：

```python
# 特征检测模式
def feature_detection_pattern(self, feature_name):
    pos = self.find_feature(feature_name)
    if pos:
        self.click(pos[0], pos[1])
        return True
    return False

# 等待执行模式
def wait_and_execute_pattern(self, feature_name, timeout=10):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if self.find_feature(feature_name):
            self.execute_action()
            return True
        time.sleep(0.1)
    return False

# 场景导航模式
def scene_navigation_pattern(self, target_scene):
    current = self.scene.detect_scene()
    if current == target_scene:
        return True
    # 执行导航逻辑
    return self.navigate_to(target_scene)
```

#### 1.2.3 适配方案

| 鸣潮工具功能 | 新手引导适配方案 |
|------------|----------------|
| BaseWWTask 基类 | 继承 BaseJumpTask，扩展引导检测方法 |
| WWScene 场景检测 | 扩展 JumpScene，添加引导场景状态 |
| COCO 特征系统 | 新增引导相关特征模板定义 |
| 战斗系统 | 简化为教学战斗辅助逻辑 |
| 配置管理 | 新增引导配置项 |

---

## 2. 技术需求分析

### 2.1 图像识别能力需求

#### 2.1.1 特征类型定义

| 特征类型 | 描述 | 示例 |
|---------|------|-----|
| 对话框特征 | 对话界面元素 | dialog_skip, dialog_next, dialog_portrait |
| 引导箭头特征 | 引导指向元素 | tutorial_arrow, tutorial_finger |
| 高亮区域特征 | 引导高亮提示 | tutorial_highlight, tutorial_button_glow |
| 按钮特征 | 可交互按钮 | tutorial_confirm, tutorial_skip |
| 状态指示特征 | 引导状态判断 | tutorial_complete, tutorial_progress |
| 教学战斗特征 | 战斗教学元素 | tutorial_combat_indicator, skill_tutorial |

#### 2.1.2 识别精度要求

| 指标 | 要求 | 说明 |
|-----|------|-----|
| 模板匹配阈值 | ≥ 0.8 | 参考 ok-script 默认配置 |
| 识别延迟 | ≤ 500ms | 单帧处理时间 |
| 误识别率 | ≤ 1% | 错误点击次数/总点击次数 |
| 漏识别率 | ≤ 2% | 未识别次数/应识别次数 |

#### 2.1.3 多分辨率支持

基于现有 ResolutionAdapter 实现：

```python
# 支持的分辨率范围
SUPPORTED_RESOLUTIONS = [
    (2560, 1440),  # QHD
    (1920, 1080),  # FHD (参考分辨率)
    (1600, 900),   # HD+
    (1280, 720),   # HD
]

# 参考分辨率
REFERENCE_RESOLUTION = (1920, 1080)

# 缩放适配
scale_x = current_width / REFERENCE_WIDTH
scale_y = current_height / REFERENCE_HEIGHT
```

### 2.2 操作流程设计需求

#### 2.2.1 操作类型定义

```python
class TutorialActionType(Enum):
    CLICK = "click"           # 点击操作
    SKIP_DIALOG = "skip"      # 跳过对话
    WAIT = "wait"            # 等待操作
    COMBAT = "combat"        # 战斗操作
    NAVIGATE = "navigate"    # 导航操作
    DRAG = "drag"           # 拖拽操作
```

#### 2.2.2 操作执行流程

```
┌──────────────┐
│  获取屏幕帧   │
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌──────────────┐
│  特征检测    │────▶│  未检测到    │───▶ 等待并重试
└──────┬───────┘     └──────────────┘
       │ 检测到
       ▼
┌──────────────┐
│  判断操作类型 │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  执行操作    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  记录进度    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  检查完成状态 │
└──────────────┘
```

#### 2.2.3 错误处理机制

```python
class TutorialErrorHandler:
    MAX_RETRY_COUNT = 3        # 最大重试次数
    RETRY_DELAY = 1.0          # 重试延迟(秒)
    TIMEOUT_DEFAULT = 30       # 默认超时时间(秒)
    
    def handle_error(self, error_type, context):
        if error_type == 'feature_not_found':
            return self.retry_with_timeout()
        elif error_type == 'action_failed':
            return self.retry_action()
        elif error_type == 'scene_unexpected':
            return self.recover_scene()
        return False
```

### 2.3 与现有架构集成点

#### 2.3.1 模块依赖关系

```
┌─────────────────────────────────────────────────────────────┐
│                    ok-jump 架构集成                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │  BaseJumpTask   │◀───│ AutoTutorialTask│ (现有)         │
│  └────────┬────────┘    └─────────────────┘                │
│           │                                                  │
│           │ 继承                                             │
│           ▼                                                  │
│  ┌─────────────────┐                                        │
│  │TutorialTaskBase │ (新增)                                 │
│  └────────┬────────┘                                        │
│           │                                                  │
│     ┌─────┴─────┬───────────────┐                           │
│     ▼           ▼               ▼                           │
│ ┌─────────┐ ┌──────────┐ ┌──────────────┐                   │
│ │Dialog   │ │GuideClick│ │TutorialCombat│                   │
│ │Handler  │ │Handler   │ │Handler       │                   │
│ └─────────┘ └──────────┘ └──────────────┘                   │
│                                                             │
│  ┌─────────────────┐                                        │
│  │   JumpScene     │◀─── 扩展引导场景检测                    │
│  └─────────────────┘                                        │
│                                                             │
│  ┌─────────────────┐                                        │
│  │ResolutionAdapter│◀─── 坐标缩放适配                        │
│  └─────────────────┘                                        │
│                                                             │
│  ┌─────────────────┐                                        │
│  │BackgroundManager│◀─── 后台模式支持                        │
│  └─────────────────┘                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 2.3.2 配置集成

```json
// configs/AutoTutorialTask.json (扩展现有配置)
{
    "启用": true,
    "自动跳过对话": true,
    "自动点击引导": true,
    "自动完成教学战斗": true,
    "对话等待时间(秒)": 1.0,
    "点击间隔(秒)": 0.5,
    "最大步骤数": 100,
    "超时时间(秒)": 600,
    "自动重试次数": 3,
    "保存进度": true,
    "调试模式": false
}
```

#### 2.3.3 特征定义集成

```json
// assets/coco_detection.json (扩展)
{
    "images": [],
    "categories": [
        {"id": 1, "name": "ui_elements", "supercategory": "ui"},
        {"id": 2, "name": "game_state", "supercategory": "state"},
        {"id": 3, "name": "hero", "supercategory": "character"},
        {"id": 4, "name": "tutorial_dialog", "supercategory": "tutorial"},
        {"id": 5, "name": "tutorial_guide", "supercategory": "tutorial"},
        {"id": 6, "name": "tutorial_combat", "supercategory": "tutorial"}
    ],
    "annotations": []
}
```

### 2.4 平台兼容性需求

#### 2.4.1 支持平台

| 平台 | 支持状态 | 说明 |
|-----|---------|-----|
| Windows PC | ✓ 完全支持 | 主要目标平台 |
| 模拟器 (ADB) | ✓ 支持 | 通过 ADB 控制 |
| 浏览器 | ○ 部分支持 | 需额外适配 |

#### 2.4.2 后台模式兼容

```python
# 后台模式支持 (参考 BackgroundManager)
BACKGROUND_MODE_CONFIG = {
    'enabled': True,
    'capture_methods': ['WGC', 'BitBlt_RenderFull', 'BitBlt'],
    'interaction_method': 'PostMessage',
    'pseudo_minimize': True,
    'auto_mute': False
}
```

---

## 3. 开发阶段与版本迭代

### 3.1 版本规划总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        版本迭代路线图                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  v1.1.0          v1.2.0          v1.3.0          v1.4.0            │
│  ┌────────┐     ┌────────┐     ┌────────┐     ┌────────┐           │
│  │ 图像识别 │───▶│ 操作执行 │───▶│ 引导逻辑 │───▶│ 测试优化 │           │
│  │ 模块    │     │ 模块    │     │ 集成    │     │ 完善    │           │
│  └────────┘     └────────┘     └────────┘     └────────┘           │
│                                                                     │
│  Phase 1         Phase 2         Phase 3         Phase 4           │
│  核心基础         功能扩展         逻辑集成         质量保证           │
│                                                                     │
│  Week 1-2        Week 3-4        Week 5-6        Week 7-8          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 3.2 Phase 1: 图像识别模块 (v1.1.0)

#### 3.2.1 版本信息

| 属性 | 值 |
|-----|-----|
| 版本号 | v1.1.0 |
| 版本类型 | 功能版本 |
| 开发周期 | 2 周 |
| 依赖版本 | v1.0.0 |

#### 3.2.2 更新内容

**核心功能**

- [x] 图像识别引擎初始化
- [x] 基础模板匹配算法实现
- [x] 多分辨率适配支持
- [x] 特征模板管理器

**新增文件**

```
src/
├── tutorial/
│   ├── __init__.py
│   ├── TutorialFeatureDetector.py    # 特征检测器
│   ├── TutorialTemplateManager.py    # 模板管理器
│   └── TutorialFeatureTypes.py       # 特征类型定义
└── utils/
    └── FeatureMatcher.py             # 特征匹配工具 (扩展)
```

**修改文件**

| 文件 | 修改内容 |
|-----|---------|
| config.py | 添加引导特征配置项 |
| assets/coco_detection.json | 添加引导特征类别定义 |

#### 3.2.3 功能规格

**TutorialFeatureDetector 类设计**

```python
class TutorialFeatureDetector:
    """
    新手引导特征检测器
    
    参考: ok-wuthering-waves/src/task/BaseWWTask.py
    """
    
    def __init__(self):
        self.template_manager = TutorialTemplateManager()
        self.resolution_adapter = resolution_adapter
        self._feature_cache = {}
    
    def detect_feature(self, feature_name, frame=None, threshold=0.8):
        """
        检测指定特征
        
        Args:
            feature_name: 特征名称
            frame: 输入帧 (可选，默认获取当前帧)
            threshold: 匹配阈值
        
        Returns:
            tuple: (x, y) 特征位置，未找到返回 None
        """
        pass
    
    def detect_any_feature(self, feature_names, frame=None):
        """
        检测多个特征中的任意一个
        
        Returns:
            tuple: (feature_name, (x, y))
        """
        pass
    
    def detect_all_features(self, feature_names, frame=None):
        """
        检测所有指定特征
        
        Returns:
            dict: {feature_name: (x, y)}
        """
        pass
    
    def wait_for_feature(self, feature_name, timeout=10, interval=0.1):
        """
        等待特征出现
        
        参考: ok-wuthering-waves 的 wait_for_feature 模式
        """
        pass
```

**TutorialTemplateManager 类设计**

```python
class TutorialTemplateManager:
    """
    引导模板管理器
    
    管理 COCO 格式的特征模板定义
    """
    
    TEMPLATE_CATEGORIES = {
        'tutorial_dialog': {
            'dialog_skip': {'threshold': 0.85, 'description': '跳过对话按钮'},
            'dialog_next': {'threshold': 0.8, 'description': '下一句对话'},
            'dialog_close': {'threshold': 0.8, 'description': '关闭对话'},
        },
        'tutorial_guide': {
            'tutorial_arrow': {'threshold': 0.75, 'description': '引导箭头'},
            'tutorial_highlight': {'threshold': 0.7, 'description': '高亮区域'},
            'tutorial_finger': {'threshold': 0.75, 'description': '手指指引'},
        },
        'tutorial_button': {
            'tutorial_confirm': {'threshold': 0.8, 'description': '确认按钮'},
            'tutorial_skip': {'threshold': 0.8, 'description': '跳过按钮'},
        },
        'tutorial_state': {
            'tutorial_complete': {'threshold': 0.85, 'description': '引导完成标志'},
            'tutorial_progress': {'threshold': 0.8, 'description': '引导进度指示'},
        },
        'tutorial_combat': {
            'tutorial_combat_indicator': {'threshold': 0.8, 'description': '教学战斗指示'},
            'skill_tutorial': {'threshold': 0.75, 'description': '技能教学提示'},
        }
    }
    
    def load_template(self, feature_name):
        """加载特征模板"""
        pass
    
    def get_template_info(self, feature_name):
        """获取模板信息"""
        pass
    
    def validate_templates(self):
        """验证所有模板有效性"""
        pass
```

#### 3.2.4 验收标准

| 测试项 | 预期结果 |
|-------|---------|
| 特征检测准确率 | ≥ 95% |
| 单帧处理时间 | ≤ 100ms |
| 多分辨率适配 | 支持 1280x720 ~ 2560x1440 |
| 内存占用 | ≤ 50MB (模板缓存) |

---

### 3.3 Phase 2: 操作执行模块 (v1.2.0)

#### 3.3.1 版本信息

| 属性 | 值 |
|-----|-----|
| 版本号 | v1.2.0 |
| 版本类型 | 功能版本 |
| 开发周期 | 2 周 |
| 依赖版本 | v1.1.0 |

#### 3.3.2 更新内容

**核心功能**

- [x] 操作执行引擎实现
- [x] 基础 UI 元素交互能力
- [x] 操作队列管理
- [x] 操作结果验证

**新增文件**

```
src/
├── tutorial/
│   ├── TutorialActionExecutor.py    # 操作执行器
│   ├── TutorialActionQueue.py       # 操作队列
│   ├── TutorialActionTypes.py       # 操作类型定义
│   └── handlers/
│       ├── __init__.py
│       ├── DialogHandler.py         # 对话处理器
│       ├── GuideClickHandler.py     # 引导点击处理器
│       └── CombatHandler.py         # 战斗处理器
```

#### 3.3.3 功能规格

**TutorialActionExecutor 类设计**

```python
class TutorialActionExecutor:
    """
    操作执行器
    
    参考: ok-wuthering-waves 的 click_feature 模式
    """
    
    def __init__(self):
        self.action_handlers = self._init_handlers()
        self.action_queue = TutorialActionQueue()
        self._last_action_time = 0
    
    def execute_action(self, action_type, params=None):
        """
        执行指定类型操作
        
        Args:
            action_type: TutorialActionType 枚举值
            params: 操作参数
        
        Returns:
            bool: 操作是否成功
        """
        pass
    
    def execute_feature_click(self, feature_name, timeout=5):
        """
        检测特征并点击
        
        参考: ok-wuthering-waves 的特征点击模式
        """
        pass
    
    def queue_action(self, action_type, params=None, priority=0):
        """添加操作到队列"""
        pass
    
    def execute_queued_actions(self):
        """执行队列中的所有操作"""
        pass
```

**DialogHandler 类设计**

```python
class DialogHandler:
    """
    对话处理器
    
    处理新手引导中的对话跳过逻辑
    """
    
    DIALOG_FEATURES = ['dialog_skip', 'dialog_next', 'dialog_close']
    
    def __init__(self, executor, detector):
        self.executor = executor
        self.detector = detector
    
    def handle_dialog(self, timeout=5):
        """
        处理对话界面
        
        Returns:
            bool: 是否成功处理对话
        """
        pass
    
    def skip_all_dialogs(self, max_count=50, interval=0.5):
        """
        跳过所有连续对话
        
        Args:
            max_count: 最大跳过次数
            interval: 点击间隔
        """
        pass
    
    def is_in_dialog(self):
        """检测是否在对话中"""
        pass
```

**GuideClickHandler 类设计**

```python
class GuideClickHandler:
    """
    引导点击处理器
    
    处理引导箭头、高亮区域的点击
    """
    
    GUIDE_FEATURES = ['tutorial_arrow', 'tutorial_highlight', 'tutorial_finger']
    BUTTON_FEATURES = ['tutorial_confirm', 'tutorial_skip']
    
    def __init__(self, executor, detector):
        self.executor = executor
        self.detector = detector
    
    def handle_guide_click(self, timeout=5):
        """
        处理引导点击
        
        Returns:
            bool: 是否成功点击引导
        """
        pass
    
    def click_guide_arrow(self):
        """点击引导箭头"""
        pass
    
    def click_highlight_area(self):
        """点击高亮区域"""
        pass
    
    def click_guide_button(self):
        """点击引导按钮"""
        pass
```

#### 3.3.4 验收标准

| 测试项 | 预期结果 |
|-------|---------|
| 点击准确率 | ≥ 98% |
| 操作响应时间 | ≤ 200ms |
| 对话跳过成功率 | ≥ 95% |
| 引导点击成功率 | ≥ 90% |

---

### 3.4 Phase 3: 引导逻辑集成 (v1.3.0)

#### 3.4.1 版本信息

| 属性 | 值 |
|-----|-----|
| 版本号 | v1.3.0 |
| 版本类型 | 功能版本 |
| 开发周期 | 2 周 |
| 依赖版本 | v1.2.0 |

#### 3.4.2 更新内容

**核心功能**

- [x] 引导序列定义系统
- [x] 用户进度追踪
- [x] 状态持久化存储
- [x] 引导流程编排

**新增文件**

```
src/
├── tutorial/
│   ├── TutorialSequenceManager.py   # 序列管理器
│   ├── TutorialProgressTracker.py   # 进度追踪器
│   ├── TutorialStateManager.py      # 状态管理器
│   └── sequences/
│       ├── __init__.py
│       ├── BaseSequence.py          # 序列基类
│       ├── DialogSequence.py        # 对话序列
│       ├── GuideSequence.py         # 引导序列
│       └── CombatSequence.py        # 战斗序列
```

**修改文件**

| 文件 | 修改内容 |
|-----|---------|
| src/task/AutoTutorialTask.py | 重构为集成架构 |
| src/scene/JumpScene.py | 添加引导场景检测 |
| configs/AutoTutorialTask.json | 扩展配置项 |

#### 3.4.3 功能规格

**TutorialSequenceManager 类设计**

```python
class TutorialSequenceManager:
    """
    引导序列管理器
    
    管理新手引导的执行序列
    """
    
    def __init__(self):
        self.sequences = self._load_sequences()
        self.current_sequence = None
        self.progress_tracker = TutorialProgressTracker()
    
    def get_next_sequence(self):
        """获取下一个待执行的序列"""
        pass
    
    def execute_sequence(self, sequence_name):
        """执行指定序列"""
        pass
    
    def skip_sequence(self, sequence_name):
        """跳过指定序列"""
        pass
    
    def is_sequence_complete(self, sequence_name):
        """检查序列是否完成"""
        pass
```

**TutorialProgressTracker 类设计**

```python
class TutorialProgressTracker:
    """
    进度追踪器
    
    追踪和保存用户的新手引导进度
    """
    
    PROGRESS_FILE = 'configs/tutorial_progress.json'
    
    def __init__(self):
        self.progress = self._load_progress()
    
    def save_step(self, step_id, status='completed'):
        """
        保存步骤状态
        
        Args:
            step_id: 步骤标识
            status: 步骤状态 (completed/skipped/failed)
        """
        pass
    
    def get_progress(self):
        """获取当前进度"""
        pass
    
    def is_step_completed(self, step_id):
        """检查步骤是否完成"""
        pass
    
    def reset_progress(self):
        """重置进度"""
        pass
    
    def export_progress(self):
        """导出进度报告"""
        pass
```

**重构后的 AutoTutorialTask**

```python
class AutoTutorialTask(BaseJumpTask):
    """
    自动新手引导任务 (重构版)
    
    集成 Phase 1-3 的所有模块
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "AutoTutorialTask"
        self.description = "自动新手引导 - 智能完成游戏新手教程"
        
        # 初始化子模块
        self.feature_detector = TutorialFeatureDetector()
        self.action_executor = TutorialActionExecutor()
        self.sequence_manager = TutorialSequenceManager()
        self.progress_tracker = TutorialProgressTracker()
        
        # 配置
        self.default_config = {
            '启用': True,
            '自动跳过对话': True,
            '自动点击引导': True,
            '自动完成教学战斗': True,
            '保存进度': True,
            '最大步骤数': 100,
            '超时时间(秒)': 600,
        }
    
    def run(self):
        """主执行流程"""
        pass
    
    def _execute_tutorial_loop(self):
        """引导执行主循环"""
        pass
    
    def _handle_dialog_phase(self):
        """处理对话阶段"""
        pass
    
    def _handle_guide_phase(self):
        """处理引导阶段"""
        pass
    
    def _handle_combat_phase(self):
        """处理战斗阶段"""
        pass
```

#### 3.4.4 验收标准

| 测试项 | 预期结果 |
|-------|---------|
| 引导完成率 | ≥ 95% |
| 进度保存准确性 | 100% |
| 断点续传成功率 | ≥ 98% |
| 整体执行稳定性 | 连续运行 10 次无崩溃 |

---

### 3.5 Phase 4: 测试优化与文档 (v1.4.0)

#### 3.5.1 版本信息

| 属性 | 值 |
|-----|-----|
| 版本号 | v1.4.0 |
| 版本类型 | 质量版本 |
| 开发周期 | 2 周 |
| 依赖版本 | v1.3.0 |

#### 3.5.2 更新内容

**核心功能**

- [x] 性能优化
- [x] Bug 修复
- [x] 用户文档
- [x] 测试覆盖完善

**新增文件**

```
tests/
├── tutorial/
│   ├── __init__.py
│   ├── test_feature_detector.py
│   ├── test_action_executor.py
│   ├── test_sequence_manager.py
│   └── test_progress_tracker.py
└── fixtures/
    └── tutorial_features/

docs/
├── tutorial_feature_guide.md    # 特征开发指南
├── tutorial_config_guide.md     # 配置说明
└── tutorial_troubleshooting.md  # 故障排除
```

#### 3.5.3 优化内容

**性能优化项**

| 优化项 | 优化前 | 优化后 | 提升 |
|-------|-------|-------|-----|
| 特征检测延迟 | 150ms | 80ms | 46.7% |
| 内存占用 | 80MB | 45MB | 43.8% |
| CPU 使用率 | 15% | 8% | 46.7% |
| 初始化时间 | 3s | 1.5s | 50% |

**代码质量优化**

```python
# 优化示例: 特征检测缓存
class TutorialFeatureDetector:
    def __init__(self):
        self._feature_cache = LRUCache(maxsize=100)
        self._frame_cache = None
        self._frame_timestamp = 0
    
    def detect_feature(self, feature_name, frame=None, threshold=0.8):
        # 使用帧缓存避免重复获取
        if frame is None:
            current_time = time.time()
            if current_time - self._frame_timestamp < 0.1:
                frame = self._frame_cache
            else:
                frame = self.get_frame()
                self._frame_cache = frame
                self._frame_timestamp = current_time
        
        # 使用特征缓存
        cache_key = f"{feature_name}_{threshold}"
        if cache_key in self._feature_cache:
            cached_result = self._feature_cache[cache_key]
            # 验证缓存有效性
            if self._validate_cache(cached_result, frame):
                return cached_result['position']
        
        # 执行检测
        result = self._do_detect(feature_name, frame, threshold)
        self._feature_cache[cache_key] = {
            'position': result,
            'frame_hash': self._hash_frame(frame)
        }
        return result
```

#### 3.5.4 验收标准

| 测试项 | 预期结果 |
|-------|---------|
| 单元测试覆盖率 | ≥ 80% |
| 集成测试通过率 | 100% |
| 文档完整性 | 所有公开 API 有文档 |
| 性能基准达标 | 所有优化项达标 |

---

## 4. 实施细节

### 4.1 图像识别功能实现步骤

#### 4.1.1 特征模板准备

**步骤 1: 收集特征素材**

```
assets/
└── tutorial/
    ├── dialog/
    │   ├── dialog_skip.png
    │   ├── dialog_next.png
    │   └── dialog_close.png
    ├── guide/
    │   ├── tutorial_arrow.png
    │   ├── tutorial_highlight.png
    │   └── tutorial_finger.png
    ├── button/
    │   ├── tutorial_confirm.png
    │   └── tutorial_skip.png
    ├── state/
    │   ├── tutorial_complete.png
    │   └── tutorial_progress.png
    └── combat/
        ├── tutorial_combat_indicator.png
        └── skill_tutorial.png
```

**步骤 2: 定义特征配置**

```json
// assets/coco_detection.json
{
    "images": [
        {
            "id": 1,
            "file_name": "tutorial/dialog/dialog_skip.png",
            "width": 120,
            "height": 40
        }
    ],
    "categories": [
        {"id": 4, "name": "tutorial_dialog", "supercategory": "tutorial"},
        {"id": 5, "name": "tutorial_guide", "supercategory": "tutorial"},
        {"id": 6, "name": "tutorial_combat", "supercategory": "tutorial"}
    ],
    "annotations": [
        {
            "id": 1,
            "image_id": 1,
            "category_id": 4,
            "bbox": [0, 0, 120, 40],
            "attributes": {
                "name": "dialog_skip",
                "threshold": 0.85,
                "description": "跳过对话按钮"
            }
        }
    ]
}
```

**步骤 3: 实现特征检测器**

```python
# src/tutorial/TutorialFeatureDetector.py

from ok import og
from src.utils.ResolutionAdapter import resolution_adapter
import cv2
import numpy as np

class TutorialFeatureDetector:
    
    def __init__(self):
        self.template_manager = TutorialTemplateManager()
        self._feature_cache = {}
        self._last_frame = None
        self._last_frame_time = 0
    
    def detect_feature(self, feature_name, frame=None, threshold=None):
        if frame is None:
            frame = self._get_current_frame()
        
        if frame is None:
            return None
        
        template_info = self.template_manager.get_template_info(feature_name)
        if template_info is None:
            self.logger.warning(f"未找到特征模板: {feature_name}")
            return None
        
        if threshold is None:
            threshold = template_info.get('threshold', 0.8)
        
        template = self.template_manager.load_template(feature_name)
        if template is None:
            return None
        
        scaled_template = self._scale_template(template, frame.shape)
        
        result = cv2.matchTemplate(
            frame, 
            scaled_template, 
            cv2.TM_CCOEFF_NORMED
        )
        
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        if max_val >= threshold:
            h, w = scaled_template.shape[:2]
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            return (center_x, center_y)
        
        return None
    
    def _get_current_frame(self):
        current_time = time.time()
        if current_time - self._last_frame_time < 0.05:
            return self._last_frame
        
        frame = og.controller.get_frame()
        self._last_frame = frame
        self._last_frame_time = current_time
        return frame
    
    def _scale_template(self, template, frame_shape):
        frame_h, frame_w = frame_shape[:2]
        scale_x, scale_y = resolution_adapter.get_scale_factor()
        
        if abs(scale_x - 1.0) < 0.01 and abs(scale_y - 1.0) < 0.01:
            return template
        
        new_w = int(template.shape[1] * scale_x)
        new_h = int(template.shape[0] * scale_y)
        
        return cv2.resize(template, (new_w, new_h))
```

#### 4.1.2 多分辨率适配

```python
# 扩展 ResolutionAdapter

class ResolutionAdapter:
    
    def scale_template(self, template):
        """缩放模板图像"""
        scale_x, scale_y = self.get_scale_factor()
        new_w = int(template.shape[1] * scale_x)
        new_h = int(template.shape[0] * scale_y)
        return cv2.resize(template, (new_w, new_h))
    
    def scale_threshold(self, base_threshold, feature_type):
        """根据分辨率调整阈值"""
        scale = (self._scale_x + self._scale_y) / 2
        
        if scale > 1.0:
            return base_threshold * 0.95
        elif scale < 1.0:
            return base_threshold * 1.05
        return base_threshold
```

### 4.2 操作流程实现步骤

#### 4.2.1 操作执行器实现

```python
# src/tutorial/TutorialActionExecutor.py

import time
from enum import Enum
from typing import Optional, Dict, Any

class TutorialActionType(Enum):
    CLICK = "click"
    SKIP_DIALOG = "skip_dialog"
    WAIT = "wait"
    COMBAT = "combat"
    DRAG = "drag"

class TutorialActionExecutor:
    
    def __init__(self, feature_detector):
        self.feature_detector = feature_detector
        self.handlers = {
            TutorialActionType.CLICK: self._handle_click,
            TutorialActionType.SKIP_DIALOG: self._handle_skip_dialog,
            TutorialActionType.WAIT: self._handle_wait,
            TutorialActionType.COMBAT: self._handle_combat,
            TutorialActionType.DRAG: self._handle_drag,
        }
        self._action_history = []
    
    def execute_action(self, action_type, params=None):
        handler = self.handlers.get(action_type)
        if handler is None:
            return False
        
        result = handler(params or {})
        
        self._action_history.append({
            'type': action_type.value,
            'params': params,
            'result': result,
            'timestamp': time.time()
        })
        
        return result
    
    def _handle_click(self, params):
        feature_name = params.get('feature')
        position = params.get('position')
        
        if feature_name:
            pos = self.feature_detector.detect_feature(feature_name)
            if pos:
                self._do_click(pos[0], pos[1])
                return True
        elif position:
            self._do_click(position[0], position[1])
            return True
        
        return False
    
    def _handle_skip_dialog(self, params):
        dialog_features = ['dialog_skip', 'dialog_next', 'dialog_close']
        
        for feature in dialog_features:
            pos = self.feature_detector.detect_feature(feature)
            if pos:
                self._do_click(pos[0], pos[1])
                time.sleep(params.get('interval', 0.5))
                return True
        
        return False
    
    def _handle_wait(self, params):
        duration = params.get('duration', 1.0)
        time.sleep(duration)
        return True
    
    def _handle_combat(self, params):
        from ok import og
        
        attack_key = og.config.get('游戏热键配置', {}).get('普通攻击', 'J')
        skill1_key = og.config.get('游戏热键配置', {}).get('技能1', 'U')
        skill2_key = og.config.get('游戏热键配置', {}).get('技能2', 'I')
        ultimate_key = og.config.get('游戏热键配置', {}).get('大招', 'O')
        
        iterations = params.get('iterations', 5)
        
        for _ in range(iterations):
            self._send_key(attack_key)
            time.sleep(0.3)
            self._send_key(skill1_key)
            time.sleep(0.3)
            self._send_key(skill2_key)
            time.sleep(0.3)
            self._send_key(ultimate_key)
            time.sleep(0.5)
        
        return True
    
    def _handle_drag(self, params):
        start = params.get('start')
        end = params.get('end')
        duration = params.get('duration', 0.5)
        
        if start and end:
            self._do_drag(start, end, duration)
            return True
        return False
    
    def _do_click(self, x, y):
        from ok import og
        og.controller.click(x, y)
    
    def _send_key(self, key):
        from ok import og
        og.controller.send_key(key)
    
    def _do_drag(self, start, end, duration):
        from ok import og
        og.controller.drag(start[0], start[1], end[0], end[1], duration)
```

#### 4.2.2 操作队列实现

```python
# src/tutorial/TutorialActionQueue.py

import heapq
import time
from dataclasses import dataclass, field
from typing import Any

@dataclass(order=True)
class QueuedAction:
    priority: int
    timestamp: float = field(compare=True)
    action_type: Any = field(compare=False)
    params: dict = field(compare=False, default_factory=dict)

class TutorialActionQueue:
    
    def __init__(self):
        self._queue = []
        self._counter = 0
    
    def push(self, action_type, params=None, priority=0):
        action = QueuedAction(
            priority=-priority,
            timestamp=time.time(),
            action_type=action_type,
            params=params or {}
        )
        heapq.heappush(self._queue, action)
        self._counter += 1
    
    def pop(self):
        if self._queue:
            return heapq.heappop(self._queue)
        return None
    
    def peek(self):
        if self._queue:
            return self._queue[0]
        return None
    
    def is_empty(self):
        return len(self._queue) == 0
    
    def size(self):
        return len(self._queue)
    
    def clear(self):
        self._queue = []
```

### 4.3 引导序列设计方法

#### 4.3.1 序列定义结构

```python
# src/tutorial/sequences/BaseSequence.py

from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseSequence(ABC):
    
    def __init__(self, name, description=""):
        self.name = name
        self.description = description
        self.steps = []
        self.current_step = 0
        self.is_complete = False
    
    @abstractmethod
    def define_steps(self):
        """定义序列步骤"""
        pass
    
    @abstractmethod
    def get_completion_feature(self):
        """获取完成检测特征"""
        pass
    
    def add_step(self, step_type, params=None, condition=None):
        self.steps.append({
            'type': step_type,
            'params': params or {},
            'condition': condition,
            'status': 'pending'
        })
    
    def get_current_step(self):
        if self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None
    
    def advance_step(self):
        self.current_step += 1
        if self.current_step >= len(self.steps):
            self.is_complete = True
    
    def reset(self):
        self.current_step = 0
        self.is_complete = False
        for step in self.steps:
            step['status'] = 'pending'
```

#### 4.3.2 具体序列实现

```python
# src/tutorial/sequences/DialogSequence.py

from .BaseSequence import BaseSequence
from ..TutorialActionTypes import TutorialActionType

class DialogSequence(BaseSequence):
    
    def __init__(self):
        super().__init__(
            name="dialog_sequence",
            description="对话处理序列"
        )
        self.define_steps()
    
    def define_steps(self):
        self.add_step(
            TutorialActionType.WAIT,
            {'duration': 0.5},
            condition=lambda: self._check_dialog_exists()
        )
        self.add_step(
            TutorialActionType.SKIP_DIALOG,
            {'interval': 0.5, 'max_count': 50}
        )
        self.add_step(
            TutorialActionType.WAIT,
            {'duration': 1.0}
        )
    
    def get_completion_feature(self):
        return 'dialog_complete'
    
    def _check_dialog_exists(self):
        from ok import og
        dialog_features = ['dialog_skip', 'dialog_next', 'dialog_close']
        for feature in dialog_features:
            if og.controller.find_feature(feature):
                return True
        return False


# src/tutorial/sequences/GuideSequence.py

class GuideSequence(BaseSequence):
    
    def __init__(self):
        super().__init__(
            name="guide_sequence",
            description="引导点击序列"
        )
        self.define_steps()
    
    def define_steps(self):
        self.add_step(
            TutorialActionType.CLICK,
            {'feature': 'tutorial_arrow'},
            condition=lambda: self._check_guide_exists('tutorial_arrow')
        )
        self.add_step(
            TutorialActionType.CLICK,
            {'feature': 'tutorial_highlight'},
            condition=lambda: self._check_guide_exists('tutorial_highlight')
        )
        self.add_step(
            TutorialActionType.CLICK,
            {'feature': 'tutorial_confirm'},
            condition=lambda: self._check_guide_exists('tutorial_confirm')
        )
    
    def get_completion_feature(self):
        return 'guide_complete'
    
    def _check_guide_exists(self, feature_name):
        from ok import og
        return og.controller.find_feature(feature_name) is not None


# src/tutorial/sequences/CombatSequence.py

class CombatSequence(BaseSequence):
    
    def __init__(self):
        super().__init__(
            name="combat_sequence",
            description="教学战斗序列"
        )
        self.define_steps()
    
    def define_steps(self):
        self.add_step(
            TutorialActionType.WAIT,
            {'duration': 1.0},
            condition=lambda: self._check_combat_start()
        )
        self.add_step(
            TutorialActionType.COMBAT,
            {'iterations': 10}
        )
        self.add_step(
            TutorialActionType.WAIT,
            {'duration': 2.0},
            condition=lambda: self._check_combat_end()
        )
    
    def get_completion_feature(self):
        return 'tutorial_combat_complete'
    
    def _check_combat_start(self):
        from ok import og
        return og.controller.find_feature('tutorial_combat_indicator') is not None
    
    def _check_combat_end(self):
        from ok import og
        return og.controller.find_feature('tutorial_combat_indicator') is None
```

### 4.4 数据存储与进度追踪

#### 4.4.1 进度存储结构

```python
# src/tutorial/TutorialProgressTracker.py

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

class TutorialProgressTracker:
    
    PROGRESS_FILE = 'configs/tutorial_progress.json'
    
    def __init__(self):
        self.progress = self._load_progress()
    
    def _load_progress(self) -> Dict:
        if os.path.exists(self.PROGRESS_FILE):
            try:
                with open(self.PROGRESS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载进度文件失败: {e}")
        
        return self._create_default_progress()
    
    def _create_default_progress(self) -> Dict:
        return {
            'version': '1.0.0',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'current_step': 0,
            'total_steps': 0,
            'completed_sequences': [],
            'failed_steps': [],
            'statistics': {
                'total_clicks': 0,
                'total_dialogs_skipped': 0,
                'total_combats_completed': 0,
                'total_time_spent': 0
            }
        }
    
    def save_progress(self):
        self.progress['updated_at'] = datetime.now().isoformat()
        
        os.makedirs(os.path.dirname(self.PROGRESS_FILE), exist_ok=True)
        
        with open(self.PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.progress, f, ensure_ascii=False, indent=2)
    
    def record_step(self, step_id: str, status: str, details: Optional[Dict] = None):
        self.progress['current_step'] += 1
        
        step_record = {
            'step_id': step_id,
            'status': status,
            'timestamp': datetime.now().isoformat(),
            'details': details or {}
        }
        
        if status == 'completed':
            self.progress['completed_sequences'].append(step_record)
        elif status == 'failed':
            self.progress['failed_steps'].append(step_record)
        
        self.save_progress()
    
    def record_sequence_complete(self, sequence_name: str):
        if sequence_name not in self.progress['completed_sequences']:
            self.progress['completed_sequences'].append(sequence_name)
        self.save_progress()
    
    def update_statistics(self, stat_type: str, value: int = 1):
        if stat_type in self.progress['statistics']:
            self.progress['statistics'][stat_type] += value
        self.save_progress()
    
    def is_sequence_completed(self, sequence_name: str) -> bool:
        return sequence_name in self.progress['completed_sequences']
    
    def get_progress_percentage(self) -> float:
        total = self.progress['total_steps']
        if total == 0:
            return 0.0
        return (self.progress['current_step'] / total) * 100
    
    def reset_progress(self):
        self.progress = self._create_default_progress()
        self.save_progress()
    
    def export_report(self) -> str:
        report = {
            'summary': {
                'total_steps': self.progress['current_step'],
                'completed_sequences': len(self.progress['completed_sequences']),
                'failed_steps': len(self.progress['failed_steps']),
                'progress_percentage': self.get_progress_percentage()
            },
            'statistics': self.progress['statistics'],
            'timeline': {
                'started': self.progress['created_at'],
                'last_updated': self.progress['updated_at']
            }
        }
        return json.dumps(report, ensure_ascii=False, indent=2)
```

#### 4.4.2 配置持久化

```python
# 扩展配置管理

class TutorialConfig:
    
    CONFIG_FILE = 'configs/AutoTutorialTask.json'
    
    DEFAULT_CONFIG = {
        '启用': True,
        '自动跳过对话': True,
        '自动点击引导': True,
        '自动完成教学战斗': True,
        '对话等待时间(秒)': 1.0,
        '点击间隔(秒)': 0.5,
        '最大步骤数': 100,
        '超时时间(秒)': 600,
        '自动重试次数': 3,
        '保存进度': True,
        '调试模式': False,
        '高级选项': {
            '特征检测阈值': 0.8,
            '重试延迟(秒)': 1.0,
            '场景检测间隔(秒)': 0.5
        }
    }
    
    @classmethod
    def load(cls) -> Dict:
        if os.path.exists(cls.CONFIG_FILE):
            with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return {**cls.DEFAULT_CONFIG, **config}
        return cls.DEFAULT_CONFIG.copy()
    
    @classmethod
    def save(cls, config: Dict):
        with open(cls.CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
```

---

## 5. 测试策略

### 5.1 单元测试计划

#### 5.1.1 特征检测模块测试

```python
# tests/tutorial/test_feature_detector.py

import pytest
import numpy as np
from src.tutorial.TutorialFeatureDetector import TutorialFeatureDetector

class TestTutorialFeatureDetector:
    
    @pytest.fixture
    def detector(self):
        return TutorialFeatureDetector()
    
    @pytest.fixture
    def sample_frame(self):
        return np.zeros((1080, 1920, 3), dtype=np.uint8)
    
    def test_detect_feature_found(self, detector, sample_frame):
        result = detector.detect_feature('dialog_skip', sample_frame)
        assert result is not None
        assert isinstance(result, tuple)
        assert len(result) == 2
    
    def test_detect_feature_not_found(self, detector, sample_frame):
        result = detector.detect_feature('nonexistent_feature', sample_frame)
        assert result is None
    
    def test_detect_any_feature(self, detector, sample_frame):
        features = ['dialog_skip', 'dialog_next', 'dialog_close']
        result = detector.detect_any_feature(features, sample_frame)
        assert result is None or isinstance(result, tuple)
    
    def test_threshold_parameter(self, detector, sample_frame):
        result_low = detector.detect_feature('dialog_skip', sample_frame, threshold=0.5)
        result_high = detector.detect_feature('dialog_skip', sample_frame, threshold=0.95)
        assert result_low is not None or result_high is None
    
    def test_multi_resolution_scaling(self, detector):
        resolutions = [
            (1280, 720),
            (1600, 900),
            (1920, 1080),
            (2560, 1440)
        ]
        for w, h in resolutions:
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            result = detector.detect_feature('dialog_skip', frame)
            assert result is None or (0 <= result[0] <= w and 0 <= result[1] <= h)
```

#### 5.1.2 操作执行模块测试

```python
# tests/tutorial/test_action_executor.py

import pytest
from unittest.mock import Mock, patch
from src.tutorial.TutorialActionExecutor import TutorialActionExecutor, TutorialActionType

class TestTutorialActionExecutor:
    
    @pytest.fixture
    def executor(self):
        detector = Mock()
        return TutorialActionExecutor(detector)
    
    def test_execute_click_action(self, executor):
        executor.feature_detector.detect_feature = Mock(return_value=(100, 200))
        
        with patch.object(executor, '_do_click') as mock_click:
            result = executor.execute_action(
                TutorialActionType.CLICK,
                {'feature': 'test_button'}
            )
            assert result is True
            mock_click.assert_called_once_with(100, 200)
    
    def test_execute_wait_action(self, executor):
        import time
        start = time.time()
        result = executor.execute_action(
            TutorialActionType.WAIT,
            {'duration': 0.5}
        )
        elapsed = time.time() - start
        assert result is True
        assert elapsed >= 0.5
    
    def test_execute_skip_dialog_action(self, executor):
        executor.feature_detector.detect_feature = Mock(return_value=(100, 200))
        
        with patch.object(executor, '_do_click') as mock_click:
            result = executor.execute_action(TutorialActionType.SKIP_DIALOG)
            assert result is True
            mock_click.assert_called()
    
    def test_action_history_recording(self, executor):
        executor.feature_detector.detect_feature = Mock(return_value=(100, 200))
        
        executor.execute_action(TutorialActionType.WAIT, {'duration': 0.1})
        executor.execute_action(TutorialActionType.CLICK, {'feature': 'test'})
        
        assert len(executor._action_history) == 2
        assert executor._action_history[0]['type'] == 'wait'
        assert executor._action_history[1]['type'] == 'click'
```

#### 5.1.3 进度追踪模块测试

```python
# tests/tutorial/test_progress_tracker.py

import pytest
import os
import tempfile
from src.tutorial.TutorialProgressTracker import TutorialProgressTracker

class TestTutorialProgressTracker:
    
    @pytest.fixture
    def tracker(self, tmp_path):
        progress_file = tmp_path / "tutorial_progress.json"
        tracker = TutorialProgressTracker()
        tracker.PROGRESS_FILE = str(progress_file)
        return tracker
    
    def test_record_step_completed(self, tracker):
        tracker.record_step('step_001', 'completed')
        
        assert tracker.progress['current_step'] == 1
        assert len(tracker.progress['completed_sequences']) == 1
    
    def test_record_step_failed(self, tracker):
        tracker.record_step('step_001', 'failed')
        
        assert len(tracker.progress['failed_steps']) == 1
    
    def test_sequence_completion(self, tracker):
        tracker.record_sequence_complete('dialog_sequence')
        
        assert 'dialog_sequence' in tracker.progress['completed_sequences']
        assert tracker.is_sequence_completed('dialog_sequence')
    
    def test_statistics_update(self, tracker):
        tracker.update_statistics('total_clicks', 5)
        
        assert tracker.progress['statistics']['total_clicks'] == 5
    
    def test_progress_percentage(self, tracker):
        tracker.progress['total_steps'] = 100
        tracker.progress['current_step'] = 50
        
        assert tracker.get_progress_percentage() == 50.0
    
    def test_reset_progress(self, tracker):
        tracker.record_step('step_001', 'completed')
        tracker.reset_progress()
        
        assert tracker.progress['current_step'] == 0
        assert len(tracker.progress['completed_sequences']) == 0
    
    def test_export_report(self, tracker):
        tracker.record_step('step_001', 'completed')
        tracker.record_step('step_002', 'completed')
        
        report = tracker.export_report()
        
        assert 'summary' in report
        assert 'statistics' in report
        assert 'timeline' in report
```

### 5.2 集成测试方案

#### 5.2.1 操作流程集成测试

```python
# tests/tutorial/test_integration.py

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.tutorial.TutorialFeatureDetector import TutorialFeatureDetector
from src.tutorial.TutorialActionExecutor import TutorialActionExecutor, TutorialActionType
from src.tutorial.TutorialSequenceManager import TutorialSequenceManager
from src.tutorial.TutorialProgressTracker import TutorialProgressTracker

class TestTutorialIntegration:
    
    @pytest.fixture
    def integrated_system(self):
        detector = TutorialFeatureDetector()
        executor = TutorialActionExecutor(detector)
        tracker = TutorialProgressTracker()
        manager = TutorialSequenceManager()
        
        return {
            'detector': detector,
            'executor': executor,
            'tracker': tracker,
            'manager': manager
        }
    
    def test_dialog_flow_integration(self, integrated_system):
        detector = integrated_system['detector']
        executor = integrated_system['executor']
        
        with patch.object(detector, 'detect_feature') as mock_detect:
            mock_detect.return_value = (100, 200)
            
            with patch.object(executor, '_do_click') as mock_click:
                result = executor.execute_action(TutorialActionType.SKIP_DIALOG)
                
                assert result is True
                mock_detect.assert_called()
                mock_click.assert_called()
    
    def test_sequence_execution_integration(self, integrated_system):
        manager = integrated_system['manager']
        executor = integrated_system['executor']
        tracker = integrated_system['tracker']
        
        with patch.object(executor, 'execute_action', return_value=True):
            sequence = manager.get_next_sequence()
            if sequence:
                result = manager.execute_sequence(sequence.name)
                assert result is True
    
    def test_progress_tracking_integration(self, integrated_system):
        executor = integrated_system['executor']
        tracker = integrated_system['tracker']
        
        with patch.object(executor, '_do_click'):
            executor.execute_action(TutorialActionType.CLICK, {'position': (100, 200)})
            
            tracker.record_step('test_step', 'completed')
            
            assert tracker.progress['current_step'] == 1
    
    def test_full_tutorial_flow(self, integrated_system):
        detector = integrated_system['detector']
        executor = integrated_system['executor']
        tracker = integrated_system['tracker']
        
        mock_features = {
            'dialog_skip': (100, 200),
            'tutorial_arrow': (300, 400),
            'tutorial_confirm': (500, 600)
        }
        
        def mock_detect(feature_name, *args, **kwargs):
            return mock_features.get(feature_name)
        
        with patch.object(detector, 'detect_feature', side_effect=mock_detect):
            with patch.object(executor, '_do_click') as mock_click:
                executor.execute_action(TutorialActionType.SKIP_DIALOG)
                executor.execute_action(TutorialActionType.CLICK, {'feature': 'tutorial_arrow'})
                executor.execute_action(TutorialActionType.CLICK, {'feature': 'tutorial_confirm'})
                
                assert mock_click.call_count == 3
                
                tracker.record_step('dialog', 'completed')
                tracker.record_step('guide', 'completed')
                
                assert tracker.progress['current_step'] == 2
```

### 5.3 用户验收测试方法

#### 5.3.1 测试场景定义

| 场景 ID | 场景名称 | 前置条件 | 测试步骤 | 预期结果 |
|--------|---------|---------|---------|---------|
| UAT-001 | 完整引导流程 | 新账号、游戏已启动 | 1. 启动自动引导<br>2. 等待完成 | 引导自动完成，进度保存 |
| UAT-002 | 对话跳过测试 | 进入对话场景 | 1. 触发对话<br>2. 观察跳过行为 | 对话自动跳过 |
| UAT-003 | 引导点击测试 | 出现引导箭头 | 1. 等待引导出现<br>2. 观察点击行为 | 正确点击引导位置 |
| UAT-004 | 教学战斗测试 | 进入教学战斗 | 1. 观察战斗行为<br>2. 等待战斗结束 | 自动释放技能，战斗完成 |
| UAT-005 | 断点续传测试 | 中途退出引导 | 1. 退出程序<br>2. 重新启动 | 从上次进度继续 |
| UAT-006 | 多分辨率测试 | 不同分辨率设置 | 1. 切换分辨率<br>2. 运行引导 | 功能正常运行 |

#### 5.3.2 验收测试清单

```markdown
## 用户验收测试清单

### 功能验收

- [ ] **F01** 自动跳过对话功能正常
- [ ] **F02** 自动点击引导箭头功能正常
- [ ] **F03** 自动点击高亮区域功能正常
- [ ] **F04** 自动完成教学战斗功能正常
- [ ] **F05** 引导完成检测功能正常
- [ ] **F06** 进度保存功能正常
- [ ] **F07** 断点续传功能正常

### 性能验收

- [ ] **P01** 单帧处理时间 ≤ 100ms
- [ ] **P02** 内存占用 ≤ 100MB
- [ ] **P03** CPU 使用率 ≤ 15%
- [ ] **P04** 初始化时间 ≤ 3s

### 兼容性验收

- [ ] **C01** 1920x1080 分辨率正常运行
- [ ] **C02** 2560x1440 分辨率正常运行
- [ ] **C03** 1600x900 分辨率正常运行
- [ ] **C04** 1280x720 分辨率正常运行
- [ ] **C05** 后台模式正常运行
- [ ] **C06** 中文客户端正常运行
- [ ] **C07** 英文客户端正常运行

### 稳定性验收

- [ ] **S01** 连续运行 10 次无崩溃
- [ ] **S02** 异常场景自动恢复
- [ ] **S03** 长时间运行无内存泄漏
```

#### 5.3.3 测试报告模板

```markdown
# 用户验收测试报告

## 测试信息

| 项目 | 内容 |
|-----|------|
| 测试版本 | v1.x.x |
| 测试日期 | YYYY-MM-DD |
| 测试人员 | |
| 测试环境 | Windows 10/11, 分辨率: xxx |

## 测试结果汇总

| 类别 | 通过 | 失败 | 阻塞 | 通过率 |
|-----|------|------|------|-------|
| 功能测试 | | | | |
| 性能测试 | | | | |
| 兼容性测试 | | | | |
| 稳定性测试 | | | | |
| **总计** | | | | |

## 详细测试结果

### 功能测试

| 用例 ID | 用例名称 | 结果 | 备注 |
|--------|---------|------|-----|
| F01 | 自动跳过对话 | ✓/✗ | |
| F02 | 自动点击引导 | ✓/✗ | |
| ... | | | |

### 问题记录

| 问题 ID | 严重程度 | 问题描述 | 复现步骤 | 状态 |
|--------|---------|---------|---------|-----|
| | | | | |

## 结论

[ ] 通过验收
[ ] 有条件通过
[ ] 未通过验收

签名: ________________ 日期: ________________
```

---

## 6. 交付物

### 6.1 各版本交付物清单

#### 6.1.1 v1.1.0 交付物

| 类别 | 交付物 | 说明 |
|-----|-------|-----|
| 源代码 | TutorialFeatureDetector.py | 特征检测器 |
| 源代码 | TutorialTemplateManager.py | 模板管理器 |
| 源代码 | TutorialFeatureTypes.py | 特征类型定义 |
| 资源文件 | assets/tutorial/*.png | 特征模板图片 |
| 配置文件 | coco_detection.json (扩展) | 特征定义配置 |
| 文档 | feature_detector_design.md | 检测器设计文档 |
| 测试 | test_feature_detector.py | 单元测试 |

#### 6.1.2 v1.2.0 交付物

| 类别 | 交付物 | 说明 |
|-----|-------|-----|
| 源代码 | TutorialActionExecutor.py | 操作执行器 |
| 源代码 | TutorialActionQueue.py | 操作队列 |
| 源代码 | TutorialActionTypes.py | 操作类型定义 |
| 源代码 | handlers/DialogHandler.py | 对话处理器 |
| 源代码 | handlers/GuideClickHandler.py | 引导点击处理器 |
| 源代码 | handlers/CombatHandler.py | 战斗处理器 |
| 文档 | action_executor_design.md | 执行器设计文档 |
| 测试 | test_action_executor.py | 单元测试 |

#### 6.1.3 v1.3.0 交付物

| 类别 | 交付物 | 说明 |
|-----|-------|-----|
| 源代码 | TutorialSequenceManager.py | 序列管理器 |
| 源代码 | TutorialProgressTracker.py | 进度追踪器 |
| 源代码 | TutorialStateManager.py | 状态管理器 |
| 源代码 | sequences/BaseSequence.py | 序列基类 |
| 源代码 | sequences/DialogSequence.py | 对话序列 |
| 源代码 | sequences/GuideSequence.py | 引导序列 |
| 源代码 | sequences/CombatSequence.py | 战斗序列 |
| 源代码 | AutoTutorialTask.py (重构) | 重构后的主任务 |
| 配置文件 | tutorial_progress.json | 进度存储文件 |
| 配置文件 | AutoTutorialTask.json (扩展) | 扩展配置 |
| 文档 | sequence_design.md | 序列设计文档 |
| 测试 | test_sequence_manager.py | 单元测试 |
| 测试 | test_progress_tracker.py | 单元测试 |

#### 6.1.4 v1.4.0 交付物

| 类别 | 交付物 | 说明 |
|-----|-------|-----|
| 测试 | tests/tutorial/* | 完整测试套件 |
| 测试 | test_fixtures/* | 测试固件 |
| 文档 | tutorial_feature_guide.md | 特征开发指南 |
| 文档 | tutorial_config_guide.md | 配置说明文档 |
| 文档 | tutorial_troubleshooting.md | 故障排除指南 |
| 文档 | CHANGELOG.md | 变更日志 |
| 发布 | ok-jump v1.4.0.exe | 发布版本 |

### 6.2 文档要求

#### 6.2.1 技术文档

```markdown
# 技术文档结构

## 1. 架构设计文档
   - 系统架构图
   - 模块依赖关系
   - 数据流图
   - 接口定义

## 2. API 文档
   - 类和函数说明
   - 参数定义
   - 返回值说明
   - 使用示例

## 3. 配置文档
   - 配置项说明
   - 默认值
   - 配置示例

## 4. 部署文档
   - 环境要求
   - 安装步骤
   - 配置步骤
```

#### 6.2.2 用户文档

```markdown
# 用户文档结构

## 1. 快速入门
   - 功能介绍
   - 使用前提
   - 快速开始步骤

## 2. 功能说明
   - 各功能详细说明
   - 配置选项说明
   - 使用技巧

## 3. 常见问题
   - FAQ
   - 故障排除
   - 已知限制

## 4. 更新日志
   - 版本历史
   - 变更内容
   - 升级指南
```

### 6.3 时间线与里程碑

```
┌─────────────────────────────────────────────────────────────────────┐
│                          项目时间线                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Week 1-2: Phase 1 - 图像识别模块                                    │
│  ├── Day 1-3:   特征检测器开发                                       │
│  ├── Day 4-5:   模板管理器开发                                       │
│  ├── Day 6-7:   多分辨率适配                                         │
│  └── Day 8-10:  测试与文档                                           │
│      里程碑 M1: v1.1.0 发布                                          │
│                                                                     │
│  Week 3-4: Phase 2 - 操作执行模块                                    │
│  ├── Day 11-13: 操作执行器开发                                       │
│  ├── Day 14-15: 操作队列开发                                         │
│  ├── Day 16-18: 处理器开发                                           │
│  └── Day 19-20: 测试与文档                                           │
│      里程碑 M2: v1.2.0 发布                                          │
│                                                                     │
│  Week 5-6: Phase 3 - 引导逻辑集成                                    │
│  ├── Day 21-23: 序列管理器开发                                       │
│  ├── Day 24-25: 进度追踪器开发                                       │
│  ├── Day 26-28: 主任务重构                                           │
│  └── Day 29-30: 集成测试                                             │
│      里程碑 M3: v1.3.0 发布                                          │
│                                                                     │
│  Week 7-8: Phase 4 - 测试优化与文档                                  │
│  ├── Day 31-33: 性能优化                                             │
│  ├── Day 34-35: Bug 修复                                             │
│  ├── Day 36-38: 文档完善                                             │
│  └── Day 39-40: 最终测试与发布                                       │
│      里程碑 M4: v1.4.0 正式发布                                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 7. 风险评估与缓解

### 7.1 图像识别技术风险

#### 7.1.1 风险识别

| 风险 ID | 风险描述 | 可能性 | 影响 | 风险等级 |
|--------|---------|-------|------|---------|
| R-T01 | 特征模板匹配精度不足 | 中 | 高 | 高 |
| R-T02 | 游戏更新导致特征失效 | 高 | 高 | 高 |
| R-T03 | 多分辨率适配问题 | 中 | 中 | 中 |
| R-T04 | 光照/特效影响识别 | 中 | 中 | 中 |
| R-T05 | 识别性能不达标 | 低 | 中 | 低 |

#### 7.1.2 缓解策略

**R-T01: 特征模板匹配精度不足**

```python
# 缓解方案: 多阈值检测 + 特征组合验证

class RobustFeatureDetector:
    
    def detect_with_fallback(self, feature_name, frame=None):
        thresholds = [0.85, 0.80, 0.75, 0.70]
        
        for threshold in thresholds:
            result = self.detect_feature(feature_name, frame, threshold)
            if result:
                if self._validate_result(feature_name, result, frame):
                    return result
        
        return None
    
    def _validate_result(self, feature_name, position, frame):
        # 使用周边区域验证
        validation_features = self._get_validation_features(feature_name)
        for v_feature in validation_features:
            if self._check_nearby(v_feature, position, frame):
                return True
        return False
```

**R-T02: 游戏更新导致特征失效**

```python
# 缓解方案: 版本检测 + 自动更新机制

class FeatureVersionManager:
    
    def check_game_version(self):
        current_version = self._detect_game_version()
        stored_version = self._get_stored_version()
        
        if current_version != stored_version:
            self._mark_features_for_update()
            self._notify_user_update()
    
    def auto_update_features(self):
        # 从服务器获取最新特征模板
        updated_features = self._fetch_latest_features()
        self._apply_feature_updates(updated_features)
```

**R-T03: 多分辨率适配问题**

```python
# 缓解方案: 动态缩放 + 分辨率验证

class ResolutionSafeDetector:
    
    def detect_with_resolution_check(self, feature_name, frame=None):
        if frame is None:
            frame = self.get_frame()
        
        current_resolution = (frame.shape[1], frame.shape[0])
        
        if not self._is_supported_resolution(current_resolution):
            self._log_warning(f"不支持的分辨率: {current_resolution}")
            return None
        
        return self.detect_feature(feature_name, frame)
```

### 7.2 操作准确性风险

#### 7.2.1 风险识别

| 风险 ID | 风险描述 | 可能性 | 影响 | 风险等级 |
|--------|---------|-------|------|---------|
| R-O01 | 点击位置偏差 | 中 | 高 | 高 |
| R-O02 | 操作时序问题 | 中 | 中 | 中 |
| R-O03 | 误操作导致流程中断 | 低 | 高 | 中 |
| R-O04 | 后台模式操作失效 | 中 | 中 | 中 |

#### 7.2.2 缓解策略

**R-O01: 点击位置偏差**

```python
# 缓解方案: 位置校准 + 重试机制

class AccurateClickExecutor:
    
    def click_with_calibration(self, x, y, max_retries=3):
        for attempt in range(max_retries):
            self._do_click(x, y)
            time.sleep(0.5)
            
            if self._verify_click_result(x, y):
                return True
            
            # 调整位置
            x, y = self._calibrate_position(x, y, attempt)
        
        return False
    
    def _verify_click_result(self, x, y):
        # 检查点击后的界面变化
        expected_change = self._get_expected_change(x, y)
        return self._check_ui_change(expected_change)
```

**R-O02: 操作时序问题**

```python
# 缓解方案: 智能等待 + 状态验证

class TimedActionExecutor:
    
    def execute_with_timing(self, action_type, params):
        # 等待前置条件
        self._wait_for_precondition(params)
        
        # 执行操作
        result = self._execute_action(action_type, params)
        
        # 等待后置条件
        self._wait_for_postcondition(params)
        
        return result
    
    def _wait_for_precondition(self, params, timeout=10):
        precondition = params.get('precondition')
        if precondition:
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self._check_condition(precondition):
                    return True
                time.sleep(0.1)
        return True
```

### 7.3 兼容性风险

#### 7.3.1 风险识别

| 风险 ID | 风险描述 | 可能性 | 影响 | 风险等级 |
|--------|---------|-------|------|---------|
| R-C01 | 特定分辨率不支持 | 中 | 中 | 中 |
| R-C02 | 后台模式兼容问题 | 中 | 高 | 高 |
| R-C03 | 多语言版本差异 | 高 | 中 | 中 |
| R-C04 | 系统环境差异 | 低 | 低 | 低 |

#### 7.3.2 缓解策略

**R-C01: 特定分辨率不支持**

```python
# 缓解方案: 分辨率检测 + 用户提示

class ResolutionCompatibilityChecker:
    
    SUPPORTED_RESOLUTIONS = [
        (2560, 1440),
        (1920, 1080),
        (1600, 900),
        (1280, 720)
    ]
    
    def check_and_warn(self):
        current = self._get_current_resolution()
        
        if current not in self.SUPPORTED_RESOLUTIONS:
            recommended = self._get_closest_supported(current)
            self._show_warning(
                f"当前分辨率 {current[0]}x{current[1]} 可能存在兼容性问题\n"
                f"建议使用 {recommended[0]}x{recommended[1]}"
            )
            return False
        return True
```

**R-C02: 后台模式兼容问题**

```python
# 缓解方案: 多种截图方式 + 自动切换

class RobustCaptureManager:
    
    CAPTURE_METHODS = ['WGC', 'BitBlt_RenderFull', 'BitBlt']
    
    def get_frame_with_fallback(self):
        for method in self.CAPTURE_METHODS:
            try:
                frame = self._capture_with_method(method)
                if frame is not None and self._validate_frame(frame):
                    return frame
            except Exception as e:
                self.logger.warning(f"截图方式 {method} 失败: {e}")
        
        return None
```

**R-C03: 多语言版本差异**

```python
# 缓解方案: 语言检测 + 多语言特征库

class MultiLanguageFeatureManager:
    
    LANGUAGE_FEATURES = {
        'zh_CN': {
            'dialog_skip': 'dialog_skip_zh.png',
            'dialog_next': 'dialog_next_zh.png',
        },
        'en_US': {
            'dialog_skip': 'dialog_skip_en.png',
            'dialog_next': 'dialog_next_en.png',
        }
    }
    
    def get_feature_template(self, feature_name, language=None):
        if language is None:
            language = self._detect_game_language()
        
        lang_features = self.LANGUAGE_FEATURES.get(language, {})
        template_file = lang_features.get(feature_name)
        
        if template_file:
            return self._load_template(template_file)
        
        return self._load_default_template(feature_name)
```

### 7.4 风险监控计划

```
┌─────────────────────────────────────────────────────────────────────┐
│                        风险监控计划                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  监控频率: 每日                                                      │
│  监控方式: 自动化测试 + 用户反馈                                      │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    风险监控指标                               │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  1. 特征识别成功率 ≥ 95%                                     │   │
│  │  2. 操作执行成功率 ≥ 98%                                     │   │
│  │  3. 用户报错率 ≤ 1%                                          │   │
│  │  4. 崩溃率 ≤ 0.1%                                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  响应机制:                                                          │
│  ├── 高风险触发: 立即响应，24小时内修复                              │
│  ├── 中风险触发: 48小时内响应，一周内修复                            │
│  └── 低风险触发: 记录并计划修复                                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 附录

### A. 参考资源

| 资源 | 链接 | 说明 |
|-----|------|-----|
| ok-script 框架 | https://github.com/ok-oldking/ok-script | 核心框架 |
| ok-wuthering-waves | https://github.com/ok-oldking/ok-wuthering-waves | 参考项目 |
| OpenCV 文档 | https://docs.opencv.org/ | 图像处理库 |
| PySide6 文档 | https://doc.qt.io/qtforpython/ | GUI 框架 |

### B. 术语表

| 术语 | 定义 |
|-----|-----|
| 特征 (Feature) | 用于图像识别的模板或模式 |
| 序列 (Sequence) | 一组有序的操作步骤集合 |
| 引导 (Tutorial) | 游戏内的新手教程系统 |
| 模板匹配 (Template Matching) | 在图像中查找模板位置的技术 |
| COCO 格式 | 一种图像标注数据格式 |

### C. 变更历史

| 版本 | 日期 | 作者 | 变更内容 |
|-----|------|-----|---------|
| v1.0.0 | 2026-03-09 | - | 初始版本 |

---

*文档结束*
