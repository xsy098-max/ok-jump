---
name: 推送打包工作流
description: 用户说"推送打包"时的完整操作流程：提交代码、打标签、推送触发 GitHub Actions 自动打包发布
type: feedback
---

## 规则

当用户说"推送打包"或类似指令时，执行以下流程：

1. 递增 `config.py` 中的 `version`
2. `git add` 相关文件
3. `git commit` 提交
4. `git tag vx.x.x`（与 config.py 中版本号一致）
5. **确认后** `git push origin main --tags`
6. GitHub Actions 自动打包并创建 Release（无需手动干预）

**Why:** CI/CD 已配置（`.github/workflows/release.yml`），推送 `v*` 标签即触发 `ok-oldking/pyappify-action@v1.0.19` 自动打包 China + Debug 两个 profile，产物上传到 GitHub Release。

**How to apply:** git push 和 git tag 影响远程仓库，执行前需要用户确认。确认后直接执行完整流程，不再重复解释步骤。
