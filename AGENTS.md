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
- **三处必须同步**:`config.py` 的 `version`、`pyproject.toml` 的 `version`
  (`tests/test_repo_hygiene.py` 有校验)、`i18n/zh_CN/LC_MESSAGES/ok.po` 头部
  Project-Id-Version(改完跑 `scripts/gen_i18n_mo.py`)

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
- 任务显示名翻译加入 `i18n/zh_CN/LC_MESSAGES/ok.po`(gettext;ok-script 2.x 已不支持
  translations.json),编辑后运行 `python scripts/gen_i18n_mo.py` 编译 ok.mo

### Unity 模式注意
- Unity 触发任务由 `src/compat/patches.py` 的线程绕行驱动(无截图设备,
  executor 会跳过触发任务),不要假设 `TaskExecutor.execute()` 在跑
- Unity 连接对象在 `og.my_app._unity_connection`(`src/utils/UnityConnection.py`)
- 判断 Unity 模式请用 `isinstance` 严格校验(见 `state_detector._get_unity_connection`),
  纯 hasattr 判断在 mock 测试下会误报

## 游戏工程与插件对接(E:\Program\Client-Jump)

Unity 工程侧通过 Editor 包 `Packages/com.unity-ai-custom` 提供 TCP 服务
(127.0.0.1:9876,NDJSON,菜单 LogicTools/AI/AICustom 开关)。改其代码的规则:

- **改 C# 后必须让用户退出播放模式触发编译**。播放模式下请求编译只会被挂起
  (`editor_request_script_compile` 返回 `deferred`);domain reload 时 TCP 服务
  随之重启,Python 端需容忍短暂拒连后重试
- 插件命令集中在 `Editor/Commands/Automation/AutomationCommandHandler.cs`,
  switch 分发+Handler 方法;已确认的关键机制(勿破坏):
  - `ClickUiGameObject`:项目自定义 `WButton : Button` 把回调绑定在**私有
    `_onClickAction`,只在重写的 OnPointerClick 里触发**,直接 `onClick.Invoke()`
    是空操作。对 WButton 必须走 `SimulatePointerPress`(ExecuteEvents 完整指针链:
    Enter→Down→Up→Click→Exit)。新增按钮自动化优先复用它
  - `automation_go_back`:反射调用热更层 `FrameManager.Instance.CloseUIByBackBtn()`
    (返回栈),用于关闭没有关闭按钮的全屏窗口(如战备窗)。原则:**编辑器程序集不直连
    热更程序集(Game.Hotfix),一律 FindLoadedType 反射**
  - `automation_get_ui_info`:在 find_ui 基础上附加 text/color(RGBA 0~255 数组,
    Color 是 0~1 浮点需×255、Color32 原样)/toggle.isOn。文本类断言都走它
- ok-jump 侧新命令封装加在 `src/utils/UnityConnection.py`(错误永不抛出,
  以 `status=='ok'` 判定)

## UI 自动化规则(BattleRoomTestTask 体系)

以战备房间测试为范本:`src/task/BattleRoomTestTask.py` 装配 →
`battle_room_cases.py`(用例数据)→ `battle_room_ui.py`(UI 解析/导航/GM)→
`battle_room_checks.py`(用例执行器)→ `battle_room_report.py`(双格式报告)。

- **UI 名称三来源,禁止猜测**(由 `TestNoGuessedNames` 守卫强制):
  1. 绑定清单 `configs/battle_room_ui_bindings.json`(改游戏工程后跑
     `scripts/extract_sdc_ui.py` 重生成,来自 Generated/MBBehaviours)
  2. 真机枚举 `logs/ui_inventory/*.json`(工具 `scripts/explore_ui.py`,
     支持 --click/--wait 链式探查子界面)
  3. 白名单常量(仅限真机验证过的动态节点)
- 插件 `find_ui/get_ui_info` **不支持无选择器全量扫描**(nameContains 为空直接
  返回空);快照/盘点必须用宽泛关键字分批扫再合并去重
- `UiContext.find` 候选支持 `"@path:<完整路径>"` 前缀精确查找,回退
  nameContains;同名校验时内层真按钮与外层容器重名——按 hasButton/激活态打分取优
- 导航判定:打开界面=点击前后 `active_view_roots()` 差集,详情如实记录真实视图根名;
  关闭界面统一走返回栈 `close_top_window()`
- GM 发道具链路全自动:常驻视图 `GMOutBattleView`,玩家本需按 F9 置
  IsDisplayGM 显示开关——工具用 `automation_set_ui_active` 直接激活
  `GMSwitch` 替代按键,再 `BtnBG/InputField` 写入 `AddItem={ID}={数量}` →
  `Send`。封装在 `UiContext.gm_add_item`;
  由任务配置"允许GM自动发道具"(默认关)+"GM道具ID映射"门控;ID **自动读取**:
  `src/task/battle_room_items.py` 解析游戏工程 Item/SDCItem/MultiLanguage 三张
  Json 表(Type==16 为搜打撤道具,SubType 即装备分类),每类取最小ID并缓存
  configs/battle_room_item_ids.json;手动JSON仅作个别修正(优先级更高)
- 拨系统时间类用例(TC-4.1-002):必须默认关闭+finally 恢复+失败日志里显著告警
  提醒手动核对时钟,仅管理员权限下生效(`battle_room_checks._os_set_localtime`)
- 缺测试素材的处理模式:先扫描仓库格子(TIPS 标题匹配),缺失时 BLOCKED 并提示
  备料途径,而非假绿或中断整轮

### 改动生效规则(是否需要重启 GUI)

- Python 任务/工具层代码改动 → **必须重启 GUI**:任务对象在 GUI 启动时已实例化,
  Python 无热重载。向用户交付时要显式标注"需重启 GUI"或"免重启"
- Unity 插件 C# 改动 → GUI 不用动:用户退出播放模式触发编译,domain reload 会
  重启 TCP 服务,Python 端 `send_command` 失败后自动重连恢复
- 数据文件(cases/item_ids 等缓存 json) → 免重启:`run()` 内实时读取;
  GUI 界面里改配置即时生效,但手改 configs/ 下 json 建议重启(框架启动时加载)
- 同时涉及 C#+Python 时推荐顺序:退播放模式编译 → 进播放模式 → 重启 GUI → 启动任务

### 测试用例自动化通用判定(四层失败体系)

每条用例的判定依次经过四层,失败即判 FAIL 并把证据写进报告详情:
1. **命令层**:TCP 应答 status!=ok / 断连 / 超时(UnityConnection 默认 5s)
2. **断言层**:锚点存在性、文本数值、颜色分类等预期比对——点击成功≠用例通过
3. **前置传播层**:入口/登录失败使下游用例记 Blocked(而非 FAIL),区分自身缺陷
   与被上游拖累
4. **运行时错误清扫**:PASS 后读 Unity 错误环形缓冲
   (`automation_get_battle_state.includeErrors`,基于 logMessageReceived),
   用例期间出现 Error/Exception 即改判 FAIL;命令不可用时自动禁用
单条用例异常兜底转 FAIL 不中断整轮;耗时逐条记录。

### 报告与产物纪律

- 测试执行报告双格式落盘 `logs/battle_room/report_*.json|*.xlsx`
  (xlsx 列结构对齐 QA《搜打撤测试用例整合.xlsx》,含汇总/用例结果/待Unity支持
  三表 + environment 元数据记录目标环境来源:公共服/私服)
- 私服目录 `E:\CN-CBT-Server`(全局设置"测试环境"可配):actionLog/ 下有
  `ch_player_sdc_item_flow_log|drop_log|battle_report_log`,是货币/掉落类用例的
  服务端核对数据源;赛季切换目前只能服务器侧触发(用户确认暂跳过相关用例)
- **单元测试严禁写真实 logs/ 输出目录**:所有产出文件的方法必须支持 `out_dir`
  注入参数,测试传临时目录并断言路径隔离(曾有 pytest 污染真实报告目录的事故)

### 测试
- 测试不依赖真实游戏/模拟器,全部 MagicMock
- 用 `AutoLoginTask.__new__` 构造任务时,记得手动初始化被测方法访问的全部属性
- 新增功能必须带测试;改框架补丁必须同步更新 `tests/test_compat_patches.py`

## 目录速查

| 路径 | 内容 |
|------|------|
| `config.py` | 装配清单:版本、任务注册、窗口/ADB/Unity/全局设置(含"测试环境") |
| `src/compat/` | 框架补丁 + 启动编排 |
| `src/task/` | 任务类;战备房间自动化四件套:`BattleRoomTestTask.py`+`battle_room_cases/ui/checks/report.py` |
| `src/combat/` | 战斗系统(状态检测/技能/移动/AI大脑) |
| `src/tutorial/` | 新手教程状态机 |
| `src/utils/` | 后台输入/伪最小化/截图/分辨率/繁简转换/Unity连接(TCP客户端) |
| `src/ci/` | Jenkins CI 流水线模块 |
| `assets/` | YOLO 模型与模板图 + coco_detection.json |
| `scripts/explore_ui.py` | 真机 UI 枚举工具(--click/--wait 链式探查,产物 logs/ui_inventory/) |
| `scripts/extract_sdc_ui.py` | 从游戏工程生成绑定清单 configs/battle_room_ui_bindings.json |
| `scripts/gen_battle_room_cases.py` | xlsx 用例表 → configs/battle_room_cases.json(181条) |
| `logs/battle_room/` | 测试执行报告(json+xlsx);只允许真实运行写入 |
| `.qoder/repowiki/zh/` | 详细架构文档(按需查阅) |
