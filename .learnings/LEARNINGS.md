# 经验教训

分类: correction | insight | knowledge_gap | best_practice

---

## [LRN-20260511-004] knowledge_gap

**时间**: 2026-05-11T08:00:00Z
**优先级**: high
**状态**: resolved
**领域**: backend

### 摘要
游戏使用 Logic/Render 双端架构，两端的 Actor 对象是不同实例，必须用 ActorIndex 值比较而非引用比较来识别玩家。

### 详情
游戏战斗系统分为 Logic 端（逻辑计算）和 Render 端（渲染表现），通过 `BattleMemoryCopyHelper` 深拷贝同步。`GameBattle.PlayerActor` 来自 Render 端，`BattleManager.AllActors` 来自 Logic 端。两端对象引用不同，`actor == playerActor` 永远为 false。游戏自身的 `ViewBattle.IsPlayer()` 用 `ActorIndex` 值比较。

### 解决信息
- **时间**: 2026-05-11
- **方法**: AutomationCommandHandler 中用 `actor.ActorIndex == playerActor.ActorIndex` 替代 `actor == playerActor`

### 元数据
- 来源: error
- 关联文件: Client-Jump AutomationCommandHandler.cs
- 标签: unity, logic-render-split, actor-identification
- 复发次数: 1

---

## [LRN-20260511-001] insight

**时间**: 2026-05-11T07:00:00Z
**优先级**: high
**状态**: pending
**领域**: backend

### 摘要
Cython 编译类（.pyd）的方法无法被 monkey-patch，且在内部依赖为 None 时可能静默失败而非抛异常。

### 详情
TaskExecutor 是 ok-script 框架的 Cython 编译类（`Py_TPFLAGS_IMMUTABLETYPE`）。当 Unity 模式下 `interaction` 为 None 时：
- `trigger()` 不抛异常，静默返回 → 任务看似启动但无效果
- `enable()` 内部调用 `interaction.on_run()` → 抛 AttributeError

必须绕过这些编译方法，直接调用 `run()` 等 Python 层方法。

### 建议行动
在 Unity 模式下：
1. 直接调用 `task.run()` 而非 `task.trigger()`
2. `task.enable()`/`disable()` 用 try/except 包裹或重写
3. 在 `_unity_trigger_loop` 中添加日志确认 `run()` 被实际调用

### 元数据
- 来源: error
- 关联文件: main.py, src/task/AutoCombatTaskUnity.py
- 标签: cython, monkey-patch, silent-failure, unity
- 复发次数: 1

---

## [LRN-20260511-002] best_practice

**时间**: 2026-05-11T07:00:00Z
**优先级**: high
**状态**: pending
**领域**: backend

### 摘要
AI 分数效用评估系统中，各评估器的评分必须满足严格的优先级关系，否则高优先级动作会被低优先级动作压制。

### 详情
在 AIBrain 的评分系统中，`evaluate_attack_hero` 给了 90 分（base 30 + range 40 + skill 20），超过技能评分（skill1=70, skill2=80），导致 AI 只做"移动靠近"而不释放技能。

正确的优先级关系：技能释放 > 普攻 > 移动靠近 > 防御行为

关键规则：
- "移动靠近"类动作应为最低优先级兜底（15-25 分）
- 技能评分必须始终高于移动类动作
- 距离加分不应让移动类动作超过技能类动作

### 建议行动
设计评分系统时：
1. 先确定动作优先级顺序
2. 为每类动作设定不重叠的分数区间
3. 用单元测试验证各场景下优先级正确
4. 避免"条件加分"导致某类动作越级超过高优先级动作

### 元数据
- 来源: error
- 关联文件: src/combat/ai_brain.py
- 标签: ai-scoring, priority, utility-evaluation
- 复发次数: 1

---

## [LRN-20260511-003] insight

**时间**: 2026-05-11T07:00:00Z
**优先级**: medium
**状态**: pending
**领域**: backend

### 摘要
常量命名风格必须在整个文件内保持一致，混用不同前缀风格会导致运行时 NameError。

### 详情
`ai_brain.py` 中定义了 `ACTION_ULTIMATE`（无 SKILL_ 前缀），但同文件的 `ACTION_SKILL_ATTACK`/`ACTION_SKILL_1`/`ACTION_SKILL_2` 都有 SKILL_ 前缀。使用时按一致性猜测写了 `ACTION_SKILL_ULTIMATE`，导致 NameError。

### 建议行动
定义常量组时统一前缀风格。如果用 SKILL_ 前缀，则所有技能动作都应使用：`ACTION_SKILL_ATTACK`, `ACTION_SKILL_1`, `ACTION_SKILL_2`, `ACTION_SKILL_ULTIMATE`。

### 元数据
- 来源: error
- 关联文件: src/combat/ai_brain.py
- 标签: naming-convention, consistency
- 复发次数: 1

---
