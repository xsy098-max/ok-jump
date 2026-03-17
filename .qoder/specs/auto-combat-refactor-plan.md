# 自动战斗模块重构实现计划

## Context（背景）

本计划针对用户提出的五个核心需求进行设计：

1. **任务模块调整**：去除一次性任务中的AutoCombatTask，保留实时触发功能
2. **GUI整合**：整合"基本设置"和"基础选项"中的重复配置项
3. **自动战斗重构**：根据流程图实现完整的自动战斗逻辑
4. **GUI选项调整**：去除"启用"选项，修正按键映射默认值
5. **手机端适配**：评估并制定手机端适配计划（后续开发）

**关键技术决策**：
- 战场单位检测使用用户提供的YOLO模型（`assets/Fight/fight.onnx`）
- PC端移动控制使用WASD键盘
- 手机端适配作为后续独立开发任务

---

## 一、文件修改清单

### 1.1 需修改的文件

| 文件路径 | 修改内容 |
|---------|---------|
| `config.py` | 移除onetime_tasks中的AutoCombatTask；修正按键映射默认值；整合全局配置 |
| `src/task/AutoCombatTask.py` | 完全重构自动战斗逻辑 |
| `src/globals.py` | 添加YOLO模型加载功能 |
| `src/constants/features.py` | 新增战斗相关特征常量 |
| `assets/coco_detection.json` | 新增战斗相关特征定义 |

### 1.2 需新增的文件

| 文件路径 | 用途 |
|---------|------|
| `src/combat/__init__.py` | 战斗模块包初始化 |
| `src/combat/labels.py` | YOLO模型标签定义 |
| `src/combat/state_detector.py` | 战斗状态检测器（YOLO检测） |
| `src/combat/movement_controller.py` | 移动控制器（WASD） |
| `src/combat/skill_controller.py` | 技能控制器 |
| `src/combat/distance_calculator.py` | 距离计算器 |
| `src/OnnxYolo8Detect.py` | ONNX YOLO检测类 |

---

## 二、YOLO模型标签定义

用户提供的YOLO模型（`assets/Fight/fight.onnx`）可识别以下类别：

| 标签名称 | 用途 | 使用场景 |
|---------|------|---------|
| **自己** | 检测自身位置 | 自身检测流程（15秒超时） |
| **友方** | 检测友方单位 | 战场状态判断、距离计算 |
| **敌军** | 检测敌方单位 | 战场状态判断、距离计算、自动技能启动 |
| **死亡状态** | 检测是否死亡 | 死亡状态监测（10秒循环） |
| **目标圈** | 检测目标选择 | （暂不用于核心战斗逻辑） |

**标签映射设计**：
```python
# src/combat/labels.py
class CombatLabel:
    SELF = 0        # 自己
    ALLY = 1        # 友方
    ENEMY = 2       # 敌军
    DEATH = 3       # 死亡状态
    TARGET_CIRCLE = 4  # 目标圈
```

---

## 三、详细实现步骤

### 步骤1：修改config.py配置

**1.1 移除一次性任务中的AutoCombatTask**
```python
# 修改前
'onetime_tasks': [
    ['src.task.MainWindowTask', 'MainWindowTask'],
    ['src.task.AutoLoginTask', 'AutoLoginTask'],
    ['src.task.AutoTutorialTask', 'AutoTutorialTask'],
    ['src.task.AutoMatchTask', 'AutoMatchTask'],
    ['src.task.AutoCombatTask', 'AutoCombatTask'],  # 移除此行
    ['src.task.DailyTask', 'DailyTask'],
],

# 修改后
'onetime_tasks': [
    ['src.task.MainWindowTask', 'MainWindowTask'],
    ['src.task.AutoLoginTask', 'AutoLoginTask'],
    ['src.task.AutoTutorialTask', 'AutoTutorialTask'],
    ['src.task.AutoMatchTask', 'AutoMatchTask'],
    ['src.task.DailyTask', 'DailyTask'],
],
```

**1.2 修正按键映射默认值**
```python
# 修改前
key_config_option = ConfigOption(
    '游戏热键配置',
    {
        '普通攻击': 'J',
        '技能1': 'U',  # 改为 'K'
        '技能2': 'I',  # 改为 'L'
        '大招': 'O',   # 改为 'U'
    }
)

# 修改后
key_config_option = ConfigOption(
    '游戏热键配置',
    {
        '普通攻击': 'J',
        '技能1': 'K',
        '技能2': 'L',
        '大招': 'U',
    }
)
```

**1.3 整合全局配置（去重）**

将 `basic_config_option` 重命名为"基本设置"，整合重复功能：
- 移除与AutoLoginTask中重复的"启动时自动开始游戏"
- 保留后台模式相关配置

```python
basic_config_option = ConfigOption(
    '基本设置',  # 从"基础选项"改为"基本设置"
    {
        '关闭时最小化到系统托盘': False,
        '后台模式': True,
        '最小化时伪最小化': True,
        '后台时静音游戏': False,
        '自动调整游戏窗口大小': False,
        '游戏退出时关闭程序': False,
        '触发间隔': 1,
        '启动/停止快捷键': 'F9',
    },
    # ...
)
```

---

### 步骤2：添加YOLO模型支持

**2.1 创建 OnnxYolo8Detect.py**

参考鸣潮项目实现，创建ONNX YOLO检测类：

```python
# src/OnnxYolo8Detect.py
import numpy as np
import onnxruntime as ort
from ok import Box

class OnnxYolo8Detect:
    def __init__(self, weights, conf_threshold=0.25, iou_threshold=0.45):
        self.session = ort.InferenceSession(weights)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold

    def detect(self, image, threshold=0.5, label=-1):
        # YOLOv8 ONNX推理
        # 返回 Box 列表
        pass
```

**2.2 修改 globals.py**

添加YOLO模型加载：

```python
# src/globals.py
class Globals(QObject):
    def __init__(self, exit_event=None):
        super().__init__()
        self._yolo_model = None
        # ... 其他初始化

    @property
    def yolo_model(self):
        if self._yolo_model is None:
            weights = os.path.join("assets", "Fight", "fight.onnx")
            from src.OnnxYolo8Detect import OnnxYolo8Detect
            self._yolo_model = OnnxYolo8Detect(weights=weights)
        return self._yolo_model

    def yolo_detect(self, image, threshold=0.5, label=-1):
        return self.yolo_model.detect(image, threshold=threshold, label=label)
```

**2.3 修改 config.py 添加自定义全局对象**

```python
config = {
    # ... 其他配置
    'my_app': ['src.globals', 'Globals'],  # 添加自定义全局对象
}
```

---

### 步骤3：创建战斗模块

**3.1 战斗状态检测器 (state_detector.py)**

```python
# src/combat/state_detector.py
from enum import Enum
from ok import og
from src.combat.labels import CombatLabel

class BattlefieldState(Enum):
    NO_UNITS = "no_units"           # 无友方、无敌军
    ALLIES_ONLY = "allies_only"     # 仅有友方
    ENEMIES_ONLY = "enemies_only"   # 仅有敌军
    MIXED = "mixed"                 # 友方+敌军均存在

class StateDetector:
    def __init__(self, task):
        self.task = task

    def detect_death_state(self, timeout=10):
        """10秒内持续监测死亡状态

        使用YOLO模型检测"死亡状态"标签
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            results = og.my_app.yolo_detect(
                self.task.frame,
                threshold=0.5,
                label=CombatLabel.DEATH  # 检测死亡状态标签
            )
            if results:
                return True  # 检测到死亡
            time.sleep(0.1)
        return False  # 10秒内未检测到死亡

    def detect_self(self, timeout=15):
        """15秒内检测自身位置

        使用YOLO模型检测"自己"标签
        返回自身位置Box，超时返回None
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            results = og.my_app.yolo_detect(
                self.task.frame,
                threshold=0.5,
                label=CombatLabel.SELF  # 检测自己标签
            )
            if results:
                return results[0]  # 返回自身位置
            time.sleep(0.1)
        return None  # 超时未检测到

    def detect_allies(self):
        """检测友方单位

        使用YOLO模型检测"友方"标签
        """
        return og.my_app.yolo_detect(
            self.task.frame,
            threshold=0.5,
            label=CombatLabel.ALLY
        )

    def detect_enemies(self):
        """检测敌方单位

        使用YOLO模型检测"敌军"标签
        """
        return og.my_app.yolo_detect(
            self.task.frame,
            threshold=0.5,
            label=CombatLabel.ENEMY
        )

    def detect_all_units(self):
        """检测所有战场单位（自己、友方、敌军）"""
        self_pos = self.detect_self()
        allies = self.detect_allies()
        enemies = self.detect_enemies()
        return self_pos, allies, enemies

    def get_battlefield_state(self):
        """判断战场状态"""
        allies = self.detect_allies()
        enemies = self.detect_enemies()

        has_allies = len(allies) > 0
        has_enemies = len(enemies) > 0

        if not has_allies and not has_enemies:
            return BattlefieldState.NO_UNITS
        elif has_allies and not has_enemies:
            return BattlefieldState.ALLIES_ONLY
        elif not has_allies and has_enemies:
            return BattlefieldState.ENEMIES_ONLY
        else:
            return BattlefieldState.MIXED
```

**3.2 移动控制器 (movement_controller.py)**

```python
# src/combat/movement_controller.py
class MovementController:
    def __init__(self, task):
        self.task = task

    def move_towards(self, target_x, target_y):
        """向目标移动（WASD控制）"""
        # 计算方向
        # 发送WASD按键
        pass

    def move_away(self, target_x, target_y):
        """远离目标"""
        pass

    def move_left_right(self, duration=15):
        """左右来回移动"""
        pass

    def move_up(self, duration=10):
        """向上移动"""
        pass

    def stop(self):
        """停止移动"""
        pass
```

**3.3 距离计算器 (distance_calculator.py)**

```python
# src/combat/distance_calculator.py
class DistanceCalculator:
    MIN_DISTANCE = 100  # 最小距离（像素）
    MAX_DISTANCE = 200  # 最大距离（像素）

    @staticmethod
    def calculate(unit1, unit2):
        """计算两单位间距离"""
        import math
        return math.sqrt((unit1.x - unit2.x)**2 + (unit1.y - unit2.y)**2)

    def is_in_optimal_range(self, distance):
        """判断是否在最佳距离范围"""
        return self.MIN_DISTANCE <= distance <= self.MAX_DISTANCE

    def get_movement_direction(self, self_pos, target_pos, distance):
        """获取移动方向建议"""
        if distance < self.MIN_DISTANCE:
            return "away"  # 需要远离
        elif distance > self.MAX_DISTANCE:
            return "towards"  # 需要靠近
        else:
            return "stop"  # 停止移动
```

**3.4 技能控制器 (skill_controller.py)**

```python
# src/combat/skill_controller.py
import time
from ok import og

class SkillController:
    def __init__(self, task, config):
        self.task = task
        self.config = config
        self.last_attack = 0
        self.last_skill1 = 0
        self.last_skill2 = 0
        self.last_ultimate = 0
        self.auto_skill_enabled = False

    def start_auto_skills(self):
        """启动自动技能"""
        self.auto_skill_enabled = True

    def stop_auto_skills(self):
        """停止自动技能"""
        self.auto_skill_enabled = False

    def update(self):
        """更新技能释放（在自动技能启用时调用）"""
        if not self.auto_skill_enabled:
            return

        current_time = time.time()

        if self.config.get('自动普攻', True):
            if current_time - self.last_attack >= self.config.get('普攻间隔(秒)', 0.5):
                self._do_attack()
                self.last_attack = current_time

        # 技能1、技能2、大招类似...

    def _do_attack(self):
        key = og.config.get('游戏热键配置', {}).get('普通攻击', 'J')
        self.task.send_key(key)
```

---

### 步骤4：重构AutoCombatTask

```python
# src/task/AutoCombatTask.py
import time
from ok import og
from src.task.BaseJumpTriggerTask import BaseJumpTriggerTask
from src.combat.state_detector import StateDetector, BattlefieldState
from src.combat.movement_controller import MovementController
from src.combat.skill_controller import SkillController
from src.combat.distance_calculator import DistanceCalculator

class AutoCombatTask(BaseJumpTriggerTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "AutoCombatTask"
        self.description = "自动战斗 - 智能战斗辅助"
        self.default_config = {
            # 移除 '启用' 选项
            '自动普攻': True,
            '自动技能1': True,
            '自动技能2': True,
            '自动大招': True,
            '普攻间隔(秒)': 0.5,
            '技能1间隔(秒)': 2.0,
            '技能2间隔(秒)': 3.0,
            '大招间隔(秒)': 5.0,
        }

        # 初始化控制器
        self.state_detector = None
        self.movement_ctrl = None
        self.skill_ctrl = None
        self.distance_calc = DistanceCalculator()

    def run(self):
        self.logger.info("自动战斗任务启动")
        self._init_controllers()
        self._main_loop()

    def _init_controllers(self):
        self.state_detector = StateDetector(self)
        self.movement_ctrl = MovementController(self)
        self.skill_ctrl = SkillController(self, self.default_config)

    def _main_loop(self):
        """主循环 - 按照流程图执行"""
        while True:
            # 检测退出信号
            if self._should_exit():
                self.logger.info("检测到退出自动战斗信号，正常终止")
                return

            # 步骤1：死亡状态检测（10秒内持续监测）
            is_dead = self.state_detector.detect_death_state(timeout=10)
            if is_dead:
                self.logger.info("检测到死亡状态，继续循环监测...")
                continue  # 死亡状态下继续循环检测

            # 步骤2：自身检测（15秒超时）
            self_pos = self.state_detector.detect_self(timeout=15)
            if self_pos is None:
                self.logger.error("15秒未检测到自身，抛出错误终止脚本")
                raise Exception("Self detection timeout - 15 seconds")

            # 步骤3：战场状态判断
            state = self.state_detector.get_battlefield_state()
            self.logger.debug(f"战场状态: {state.value}")

            # 根据战场状态处理
            self._handle_battlefield_state(state, self_pos)

    def _should_exit(self):
        """检测是否应该退出自动战斗"""
        # 检测是否还在游戏中
        return not self.in_game()

    def _handle_battlefield_state(self, state, self_pos):
        """处理战场状态 - 4种情况"""
        if state == BattlefieldState.NO_UNITS:
            self._handle_no_units()
        elif state == BattlefieldState.ALLIES_ONLY:
            self._handle_allies_only(self_pos)
        elif state == BattlefieldState.ENEMIES_ONLY:
            self._handle_enemies_only(self_pos)
        else:  # MIXED
            self._handle_mixed(self_pos)

    def _handle_no_units(self):
        """情况1：无友方、无敌军

        左右来回移动15秒，期间持续检测敌人/队友
        若15秒内检测到单位 → 立刻回到战场判断逻辑
        15秒仍无单位 → 向上移动10秒
        若10秒仍无单位 → 抛出错误，终止脚本
        """
        start_time = time.time()
        while time.time() - start_time < 15:
            if self._should_exit():
                return

            # 检测是否出现单位
            state = self.state_detector.get_battlefield_state()
            if state != BattlefieldState.NO_UNITS:
                return  # 回到主循环重新判断

            # 左右移动
            self.movement_ctrl.move_left_right(duration=1)
            time.sleep(0.1)

        # 15秒后仍无单位，向上移动10秒
        self.logger.info("15秒无单位，尝试向上移动...")
        start_time = time.time()
        while time.time() - start_time < 10:
            if self._should_exit():
                return

            state = self.state_detector.get_battlefield_state()
            if state != BattlefieldState.NO_UNITS:
                return

            self.movement_ctrl.move_up(duration=1)
            time.sleep(0.1)

        # 10秒后仍无单位，抛出错误
        raise Exception("No units found after 25 seconds of searching")

    def _handle_allies_only(self, self_pos):
        """情况2：仅有友方、无敌军

        向友方移动，保持距离100~200像素
        强制关闭自动技能
        """
        self.skill_ctrl.stop_auto_skills()

        allies = self.state_detector.detect_allies()
        if allies:
            target = allies[0]  # 选择最近的友方
            self._maintain_distance(self_pos, target)

    def _handle_enemies_only(self, self_pos):
        """情况3：仅有敌军、无友方

        向敌军移动，保持距离100~200像素
        距离达标后 → 启动自动技能
        """
        enemies = self.state_detector.detect_enemies()
        if enemies:
            target = enemies[0]  # 选择最近的敌军
            distance = self.distance_calc.calculate(self_pos, target)

            if self.distance_calc.is_in_optimal_range(distance):
                # 距离达标，启动自动技能
                self.skill_ctrl.start_auto_skills()
                self.skill_ctrl.update()
            else:
                # 距离不达标，只移动、不放技能
                self.skill_ctrl.stop_auto_skills()
                self._maintain_distance(self_pos, target)

    def _handle_mixed(self, self_pos):
        """情况4：友方+敌军都存在

        优先向敌军移动，保持距离100~200像素
        距离达标后 → 启动自动技能
        """
        # 与 _handle_enemies_only 逻辑相同
        self._handle_enemies_only(self_pos)

    def _maintain_distance(self, self_pos, target):
        """统一距离逻辑：保持100~200像素距离"""
        distance = self.distance_calc.calculate(self_pos, target)
        direction = self.distance_calc.get_movement_direction(self_pos, target, distance)

        if direction == "towards":
            self.movement_ctrl.move_towards(target.x, target.y)
        elif direction == "away":
            self.movement_ctrl.move_away(target.x, target.y)
        else:
            self.movement_ctrl.stop()
```

---

### 步骤5：更新特征定义

**5.1 更新 features.py**

```python
# src/constants/features.py
class Features:
    # ... 现有特征

    # ==================== 战斗相关 ====================
    # 死亡状态
    DEATH_INDICATOR = 'death_indicator'
    REVIVE_BUTTON = 'revive_button'

    # 自身检测
    SELF_INDICATOR = 'self_indicator'

    # 退出战斗
    EXIT_COMBAT_BUTTON = 'exit_combat_button'
    IN_GAME_INDICATOR = 'in_game_indicator'
```

---

## 三、手机端适配评估

### 3.1 当前支持情况

**框架层面支持**：
- ok-script框架原生支持ADB模式
- 配置文件中已有ADB配置：
  ```python
  'adb': {
      'enabled': True,
      'package_name': 'com.fivecross.mhqdjj',
  }
  ```

**可用方法**：
- `self.is_adb()` - 检测是否为ADB模式
- `self.swipe(x1, y1, x2, y2)` - 滑动操作
- `self.click()` - ADB模式下自动转换为触摸

### 3.2 需要适配的功能点

| 功能 | PC端实现 | 移动端实现 | 适配难度 |
|------|---------|-----------|---------|
| 移动控制 | WASD按键 | 虚拟摇杆滑动 | 中等 |
| 技能释放 | 按键 J/K/L/U | 点击技能按钮位置 | 低 |
| 普通攻击 | 按键 J | 点击攻击按钮位置 | 低 |
| 截图识别 | 相同 | 相同 | 无需适配 |

### 3.3 手机端开发计划（后续独立任务）

**第一阶段：基础适配**
- 实现移动端虚拟摇杆控制
- 定义技能按钮相对位置
- 适配点击操作

**第二阶段：UI元素识别**
- 采集移动端UI截图
- 添加移动端特征图片
- 调整识别阈值

**第三阶段：测试验证**
- 在模拟器/真机上测试
- 修复适配问题

---

## 四、验证方法

### 4.1 功能测试

1. **配置验证**
   - 运行程序，检查GUI中"基本设置"是否正常显示
   - 验证按键映射默认值是否为 J、K、L、U
   - 确认AutoCombatTask不在一次性任务列表中

2. **战斗逻辑测试**
   - 进入游戏战斗场景
   - 启动触发任务
   - 观察日志输出，验证各状态检测是否正常
   - 验证移动控制和技能释放

3. **YOLO检测测试**
   - 使用debug模式查看检测结果
   - 验证友方/敌军识别准确率

### 4.2 运行命令

```bash
# 调试模式
python main_debug.py

# 正式模式
python main.py
```

---

## 五、关键文件路径

- `d:\Python-wuwa\ok-jump\config.py` - 核心配置
- `d:\Python-wuwa\ok-jump\src\task\AutoCombatTask.py` - 自动战斗主控制器
- `d:\Python-wuwa\ok-jump\src\globals.py` - 全局资源（YOLO模型）
- `d:\Python-wuwa\ok-jump\src\constants\features.py` - 特征常量
- `d:\Python-wuwa\ok-jump\assets\Fight\fight.onnx` - YOLO模型文件
- `d:\Python-wuwa\ok-jump\终极定稿版：自动化战斗脚本 全逻辑流程图.md` - 流程图参考

---

## 六、实施顺序

1. **阶段一**：修改config.py（移除任务、修正按键、整合配置）
2. **阶段二**：添加YOLO模型支持（OnnxYolo8Detect.py、globals.py）
3. **阶段三**：创建战斗模块（combat/目录下的各控制器）
4. **阶段四**：重构AutoCombatTask.py
5. **阶段五**：测试验证
