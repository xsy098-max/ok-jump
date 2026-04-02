---
name: 记忆和 Skills 存储位置
description: 所有 .claude 记忆文件和 skills 必须存储在项目目录中，而非用户目录
type: feedback
---

## 规则

所有 `.claude` 相关文件（记忆 memory、skills 等）必须创建在项目目录 `d:/Python-wuwa/ok-jump/.claude/` 下，不要存到用户目录 `C:/Users/Xu/.claude/`。

**Why:** 用户希望 .claude 文件随项目一起管理，方便版本控制和迁移。

**How to apply:** 写入记忆时路径使用 `d:/Python-wuwa/ok-jump/.claude/memory/`，创建 skills 时使用 `d:/Python-wuwa/ok-jump/.claude/skills/`。
