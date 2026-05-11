# 错误记录

命令执行失败、工具异常、集成错误

---

## [ERR-20260509-001] ensure_hwnd 位置参数错传

**时间**: 2026-05-09T15:27:39Z
**优先级**: high
**状态**: resolved
**领域**: config

### 摘要
monkey-patch 中调用 `ensure_hwnd` 时将 `hwnd_class`（string）传给了 `frame_width`（int）参数，导致 `an integer is required` 异常。

### 错误信息
```
[WARNING] Unity 模式窗口捕获初始化失败: an integer is required
```

### 上下文
- 操作：在 main.py `patch_device_manager_for_unity` 中调用 `self.ensure_hwnd(title, exe, hwnd_class)`
- 环境：ok-jump v1.6.0, Windows 10
- 复现步骤：选择 Unity 设备启动时触发

### 修复方案
使用关键字参数调用：`self.ensure_hwnd(title=..., exe=..., hwnd_class=...)`

### 解决信息
- **时间**: 2026-05-09
- **方法**: 改为关键字参数传参，避免位置参数错位

### 元数据
- 可复现: yes
- 关联文件: main.py
- 根因: Python 方法签名有默认参数间隔，位置参数传递时类型不匹配不会在调用时报错，只在内部使用时才抛异常

---

## [ERR-20260511-001] Cython trigger() 在 interaction=None 时静默失败

**时间**: 2026-05-11T06:30:00Z
**优先级**: high
**状态**: resolved
**领域**: backend

### 摘要
AutoCombatTaskUnity 触发器循环启动成功，日志显示 "Unity trigger 循环启动"，但游戏中无实际操作。`task.trigger()` 是 Cython 编译方法，在 `interaction=None` 时静默返回不执行 `run()`。

### 错误信息
```
[INFO] Unity trigger 循环启动: AutoCombatTaskUnity
（无后续操作日志，无异常抛出）
```

### 上下文
- 操作：`_unity_trigger_loop` 调用 `task.trigger()` 触发战斗任务
- 环境：ok-jump v1.7.0, Windows 10, Unity Editor TCP 连接
- 复现步骤：选择 Unity 设备 → 启用 AutoCombatTaskUnity 触发器 → 进入游戏战斗

### 修复方案
在 `_unity_trigger_loop` 中绕过 `task.trigger()`，直接调用 `task.run()`：
```python
if task.should_trigger():
    task.run()  # 而非 task.trigger()
```

### 解决信息
- **时间**: 2026-05-11
- **方法**: 直接调用 `run()` 绕过 Cython 编译的 `trigger()` 方法

### 元数据
- 可复现: yes
- 关联文件: main.py, src/task/AutoCombatTaskUnity.py
- 根因: TaskExecutor 是 Cython 编译类（.pyd），trigger() 内部依赖 self.interaction，在 Unity 模式下 interaction 为 None 但不抛异常而是静默返回

---

## [ERR-20260511-002] AI 评分系统常量名错误导致 NameError

**时间**: 2026-05-11T06:45:00Z
**优先级**: high
**状态**: resolved
**领域**: backend

### 摘要
`ai_brain.py` 中 `_execute_action` 使用了不存在的常量 `ACTION_SKILL_ULTIMATE`，实际定义名是 `ACTION_ULTIMATE`，导致运行时 NameError。

### 错误信息
```
NameError: name 'ACTION_SKILL_ULTIMATE' is not defined. Did you mean: 'ACTION_SKILL_ATTACK'?
```

### 上下文
- 操作：AIBrain.tick() → _execute_action() 执行动作时分发到对应技能
- 环境：ok-jump v1.7.0, Python 3.x
- 复现步骤：任何触发 AI 释放大招的场景

### 修复方案
将 `ACTION_SKILL_ULTIMATE` 改为 `ACTION_ULTIMATE`，与文件顶部的常量定义一致。

### 解决信息
- **时间**: 2026-05-11
- **方法**: 修正常量名引用

### 元数据
- 可复现: yes
- 关联文件: src/combat/ai_brain.py
- 根因: 常量命名风格不一致。文件中定义了 `ACTION_ULTIMATE`（无 SKILL_ 前缀），但使用处写了 `ACTION_SKILL_ULTIMATE`。其他技能常量如 `ACTION_SKILL_1`/`ACTION_SKILL_2`/`ACTION_SKILL_ATTACK` 都有 `SKILL_` 前缀，但大招的常量定义漏掉了前缀

---

## [ERR-20260511-003] AI 评分权重失衡导致技能不释放

**时间**: 2026-05-11T07:00:00Z
**优先级**: high
**状态**: resolved
**领域**: backend

### 摘要
`evaluate_attack_hero` 评分高达 90 分（base 30 + in_range 40 + skill_available 20），超过 skill1（70）甚至 skill2（80），导致 AI 始终选择"移动到敌人"而不释放技能。

### 错误信息
（无异常，表现为游戏内角色站在敌人旁边不攻击）

### 上下文
- 操作：AI 决策循环 CleanScore → Evaluate → RefreshMax → Execute
- 环境：ok-jump v1.7.0
- 复现步骤：任何战斗场景，敌人在技能范围内

### 修复方案
将 `evaluate_attack_hero` 降级为低优先级兜底（base 15，range bonus +10），确保技能评分（40-100）始终高于"移动靠近"评分（15-25）。

### 解决信息
- **时间**: 2026-05-11
- **方法**: 重新调整评分权重，ATAK_HERO 从 90 降至 15-25

### 元数据
- 可复现: yes
- 关联文件: src/combat/ai_brain.py
- 根因: AI 评分设计时未考虑相对权重。ATAK_HERO 的职责是"移动靠近敌人"，应为最低优先级兜底动作。但它获得了距离加分(40)和技能可用加分(20)，使其总分超过技能动作。评分系统必须确保：技能 > 普攻 > 移动靠近 > 防御/逃跑

---
