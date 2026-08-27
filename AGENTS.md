# AGENTS.md — ok-jump AI 开发代理指南

本文件供 AI 编码代理(Claude Code / ZCode / Copilot 等)在仓库内工作时参考。
人类开发者的完整指南见 `CLAUDE.md`。

## 项目简介

《漫画群星：大集结》(Unity 引擎)自动化工具,基于 [ok-script](https://github.com/ok-oldking/ok-script) 2.x 框架。
双管线架构:
- **视觉管线**:WGC/BitBlt 截图 + 自训练 YOLO 模型 + OCR,适配 PC/模拟器
- **Unity 直连管线**:TCP (NDJSON) 直连 Unity Editor 插件,零截图零输入注入

## 环境与命令

- Python 3.12,虚拟环境在 `.venv\`
- **始终直接调用 venv 解释器,不要依赖 shell activation**:
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/ -q
  ```
- 一键测试: `.\run_tests.ps1`
- 运行 GUI(调试): `.\.venv\Scripts\python.exe main_debug.py`

## 关键约定

### 版本号
每次功能更新或 bug 修复,递增 `config.py` 中的 `version`:
- 小改动(bug 修复)→ patch +1
- 大改动(新功能/重构)→ minor +1

### 推送打包
用户说"推送打包"时:更新版本号 → `git commit` → `git tag v<版本>` → `git push`(含 tag),
GitHub Actions 自动构建发布(pyappify),CNB 中国镜像自动白名单同步。

### 框架兼容补丁
所有对 ok-script 内部的 monkey-patch 集中在 `src/compat/patches.py`,
每个补丁注明解决的问题与适用版本;**升级 ok-script 前先读该文件头部的退役清单**。
应用层启动编排(智能设备选择、定时调度器等)在 `src/compat/startup.py`,`main.py` 只做装配。

### 任务开发
- 一次性任务继承 `src/task/BaseJumpTask.py` 的 `BaseJumpTask`
- 触发任务继承 `BaseJumpTriggerTask`
- 共享逻辑在 `src/task/mixins.py` (JumpTaskMixin)
- 新任务必须在 `config.py` 的 `onetime_tasks` / `trigger_tasks` 注册
- 任务显示名翻译加入 `i18n/zh_CN/translations.json`

### Unity 模式注意
- Unity 触发任务由 `src/compat/patches.py` 的线程绕行驱动(无截图设备,
  executor 会跳过触发任务),不要假设 `TaskExecutor.execute()` 在跑
- Unity 连接对象在 `og.my_app._unity_connection`(`src/utils/UnityConnection.py`)
- 判断 Unity 模式请用 `isinstance` 严格校验(见 `state_detector._get_unity_connection`),
  纯 hasattr 判断在 mock 测试下会误报

### 测试
- 测试不依赖真实游戏/模拟器,全部 MagicMock
- 用 `AutoLoginTask.__new__` 构造任务时,记得手动初始化被测方法访问的全部属性
- 新增功能必须带测试;改框架补丁必须同步更新 `tests/test_compat_patches.py`

## 目录速查

| 路径 | 内容 |
|------|------|
| `config.py` | 装配清单:版本、任务注册、窗口/ADB/Unity 配置 |
| `src/compat/` | 框架补丁 + 启动编排 |
| `src/task/` | 任务类 |
| `src/combat/` | 战斗系统(状态检测/技能/移动/AI大脑) |
| `src/tutorial/` | 新手教程状态机 |
| `src/utils/` | 后台输入/伪最小化/截图/分辨率/繁简转换/Unity连接 |
| `src/ci/` | Jenkins CI 流水线模块 |
| `assets/` | YOLO 模型与模板图 + coco_detection.json |
| `.qoder/repowiki/zh/` | 详细架构文档(按需查阅) |
