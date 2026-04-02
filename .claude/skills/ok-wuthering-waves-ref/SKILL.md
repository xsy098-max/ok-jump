---
name: ok-wuthering-waves-ref
description: 鸣潮自动化工具ok-wuthering-waves参考项目。当用户提到"鸣潮"、"wuthering waves"、"ok-ww"、"战斗自动化"、"角色技能"、"自动战斗"时自动调用。提供战斗检测、角色控制、任务流程等实现参考。
---

# ok-wuthering-waves 鸣潮自动化工具

基于 ok-script 框架开发的鸣潮自动化工具，支持后台运行。

**本地路径**: `E:\python wuwa\ok-wuthering-waves`
**GitHub**: https://github.com/ok-oldking/ok-wuthering-waves
**Python版本**: 3.12

## 项目结构

```
E:\python wuwa\ok-wuthering-waves\
├── src/
│   ├── char/              # 角色技能实现
│   │   ├── BaseChar.py    # 角色基类
│   │   ├── CharFactory.py # 角色工厂
│   │   └── *.py           # 各角色实现
│   ├── combat/
│   │   └── CombatCheck.py # 战斗状态检测
│   ├── scene/
│   │   └── WWScene.py     # 场景管理
│   ├── task/              # 任务系统
│   │   ├── BaseWWTask.py  # 任务基类
│   │   ├── BaseCombatTask.py # 战斗任务基类
│   │   ├── AutoCombatTask.py # 自动战斗
│   │   └── *.py           # 各任务实现
│   ├── Labels.py          # UI标签定义
│   ├── OnnxYolo8Detect.py # YOLO检测
│   └── globals.py         # 全局配置
├── assets/                # 图片资源
├── configs/               # 配置文件
└── config.py              # 配置管理
```

## 核心模块

### CombatCheck - 战斗检测

```python
class CombatCheck(BaseWWTask):
    def __init__(self):
        self._in_combat = False
        self._in_liberation = False  # 声骸解放状态
        self.boss_health = None
        self.cds = {}  # 技能冷却

    def on_combat_check(self):
        return True

    def reset_to_false(self, reason=""):
        # 重置战斗状态
        self._in_combat = False
        self.cds = {}
```

### BaseWWTask - 任务基类

```python
class BaseWWTask(BaseTask):
    def __init__(self):
        self.scene: WWScene = None
        self.key_config = self.get_global_config('Game Hotkey Config')

    def is_open_world_auto_combat(self):
        # 判断是否为大世界自动战斗

    def absorb_echo_text(self):
        # 吸收声骸文本识别
        return re.compile(r'(吸收|Absorb)')
```

### 角色系统 (char/)

```python
# BaseChar.py - 角色基类
class BaseChar:
    def do_perform(self):
        # 执行角色技能循环

    def click_resonance(self):
        # 点击共鸣技能

    def click_liberation(self):
        # 点击声骸解放

# CharFactory.py - 角色工厂
class CharFactory:
    @staticmethod
    def create_char(name, task):
        # 根据角色名创建对应角色实例
```

### 已实现角色

| 角色 | 文件 |
|------|------|
| 卡卡罗 | Calcharo.py |
| 暗主 | HavocRover.py |
| 忌炎 | Jiyan.py |
| 今汐 | Jinhsi.py |
| 长离 | Changli.py |
| 相里要 | Xiangliyao.py |
| 椿 | Camellya.py |
| 柯莱塔 | Carlotta.py |
| 菲比 | Phoebe.py |
| 赞妮 | Zani.py |
| ... | 更多角色 |

## 关键文件

| 文件 | 用途 |
|------|------|
| `src/combat/CombatCheck.py` | 战斗状态检测 |
| `src/task/BaseWWTask.py` | 任务基类 |
| `src/task/BaseCombatTask.py` | 战斗任务基类 |
| `src/char/BaseChar.py` | 角色基类 |
| `src/char/CharFactory.py` | 角色工厂 |
| `src/Labels.py` | UI标签/模板定义 |

## 运行方式

```bash
# 安装依赖
pip install -r requirements.txt

# 运行Release版
python main.py

# 运行Debug版
python main_debug.py
```

## 命令行参数

```bash
ok-ww.exe -t 1 -e
# -t: 启动后执行第N个任务
# -e: 任务完成后退出
```

## 开发参考

开发ok-jump时可参考:
1. **战斗检测**: `src/combat/CombatCheck.py`
2. **角色技能**: `src/char/` 目录下各角色实现
3. **任务流程**: `src/task/` 目录下各任务实现
4. **UI标签**: `src/Labels.py` 模板匹配定义
