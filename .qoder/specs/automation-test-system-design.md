# ok-jump 自动化测试系统实施计划

## 一、背景与目标

### 问题描述
作为游戏测试工程师，需要一个完整的CI/CD自动化测试系统，用于：
- 自动从Jenkins下载最新Android安装包
- 自动启动模拟器并部署测试环境
- 执行自动化测试流程并捕获异常
- 生成测试报告并发送企业微信通知

### 预期成果
实现一个端到端的自动化测试流水线，支持每日定时执行，自动生成测试报告，显著提升回归测试效率。

---

## 二、系统架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ok-jump 自动化测试系统                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐ │
│  │  包管理模块   │ → │ 环境部署模块  │ → │ 测试执行模块  │ → │ 通知报告模块  │ │
│  │ PackageManager│   │ DeployManager │   │ TestExecutor │   │ Notifier     │ │
│  └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘ │
│          ↓                  ↓                  ↓                  ↓         │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      配置管理层 (configs/ci_config.json)             │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│          ↓                  ↓                  ↓                  ↓         │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      数据存储层 (test_results/ + reports/)           │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、新增文件结构

```
src/
├── ci/                                    # CI/CD 自动化测试模块
│   ├── __init__.py
│   ├── package_manager.py                 # Jenkins包下载管理
│   ├── emulator_manager.py                # 雷电模拟器管理
│   ├── deploy_manager.py                  # 环境部署管理
│   ├── test_executor.py                   # 测试执行器
│   ├── test_result_manager.py             # 测试结果管理
│   ├── exception_handler.py               # 异常捕获处理器
│   └── notifier/                          # 通知模块
│       ├── __init__.py
│       ├── base_notifier.py               # 通知基类
│       ├── wecom_notifier.py              # 企业微信通知
│       └── report_generator.py            # 测试报告生成
│
├── task/
│   └── CITestTask.py                      # CI测试一条龙任务
│
├── gui/
│   └── ci_tab.py                          # CI配置面板
│
configs/
├── ci_config.json                         # CI配置
└── test_report.json                       # 测试报告配置
```

---

## 四、模块详细设计

### 4.1 包管理模块 (PackageManager)

**文件**: `src/ci/package_manager.py`

**核心功能**:
- 从Jenkins REST API获取构建列表
- **从最新构建开始向下遍历，找到Build文件夹下有APK的构建**
- 支持版本对比，避免重复下载
- 断点续传下载支持
- 自动清理旧版本APK

**Jenkins URL结构分析**:
```
http://192.168.9.154:8080/job/P9_XProject_Android_BrawlStars_Release/99/artifact/Build/P9_XProject_Android_20260327_99_SVN173687_dev_0.31.0_3100_SDK_NONE.apk
│                      │                                      │  │        │      │
│                      │                                      │  │        │      └── APK文件名
│                      │                                      │  │        └── Build文件夹
│                      │                                      │  └── artifact路径
│                      │                                      └── 构建号(99)
│                      └── Job名称
└── Jenkins地址
```

**APK文件名解析**:
```
P9_XProject_Android_20260327_99_SVN173687_dev_0.31.0_3100_SDK_NONE.apk
│                  │         │  │        │    │       │
│                  │         │  │        │    │       └── 版本码(3100)
│                  │         │  │        │    └── 版本号(0.31.0)
│                  │         │  │        └── 分支/类型(dev)
│                  │         │  └── SVN版本号
│                  │         └── 构建号
│                  └── 日期(20260327)
└── 项目名
```

**关键接口**:
```python
class PackageManager:
    def find_latest_apk_build() -> PackageInfo
        # 从最新构建开始向下遍历，找到Build文件夹下有APK的构建

    def download_package(url: str) -> Path
    def compare_versions(local: int, remote: int) -> bool
    def get_installed_version() -> int
    def cleanup_old_packages(keep: int = 3)
```

**数据结构**:
```python
@dataclass
class PackageInfo:
    url: str           # 下载链接
    filename: str      # 文件名
    version: str       # 版本号 (如 0.31.0)
    build_number: int  # 构建号 (如 99)
    size: int          # 文件大小
    timestamp: str     # 构建时间
    svn_revision: int  # SVN版本号 (如 173687)
    version_code: int  # 版本码 (如 3100)
```

**核心实现逻辑**:
```python
class PackageManager:
    """Jenkins包管理器"""

    def __init__(self, jenkins_url: str, job_name: str):
        self.jenkins_url = jenkins_url.rstrip('/')
        self.job_name = job_name

    def find_latest_apk_build(self, max_search: int = 20) -> PackageInfo:
        """
        查找最新的有APK的构建

        Args:
            max_search: 最多向下查找多少个构建

        Returns:
            PackageInfo: 最新可用构建的信息

        Raises:
            PackageDownloadException: 在max_search范围内未找到APK
        """
        # 1. 获取所有构建列表
        builds = self._get_all_builds()

        # 2. 按构建号降序排列（最新的在前）
        builds.sort(key=lambda x: x['number'], reverse=True)

        # 3. 从最新构建开始查找
        for build in builds[:max_search]:
            build_number = build['number']

            # 4. 获取该构建的产物列表
            artifacts = self._get_build_artifacts(build_number)

            # 5. 检查Build文件夹下是否有APK
            apk_artifact = self._find_apk_in_build_folder(artifacts)

            if apk_artifact:
                self.log_info(f"找到APK: 构建#{build_number}, 文件: {apk_artifact['fileName']}")

                # 6. 构建下载URL
                download_url = (
                    f"{self.jenkins_url}/job/{self.job_name}/"
                    f"{build_number}/artifact/{apk_artifact['relativePath']}"
                )

                # 7. 解析版本信息
                version_info = self._parse_apk_filename(apk_artifact['fileName'])

                return PackageInfo(
                    url=download_url,
                    filename=apk_artifact['fileName'],
                    version=version_info['version'],
                    build_number=build_number,
                    size=apk_artifact.get('size', 0),
                    timestamp=build['timestamp'],
                    svn_revision=version_info['svn_revision'],
                    version_code=version_info['version_code']
                )

        raise PackageDownloadException(f"在最近{max_search}个构建中未找到APK文件")

    def _get_all_builds(self) -> list:
        """获取所有构建列表"""
        url = f"{self.jenkins_url}/job/{self.job_name}/api/json?tree=builds[number,timestamp,result]"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json().get('builds', [])

    def _get_build_artifacts(self, build_number: int) -> list:
        """获取指定构建的产物列表"""
        url = f"{self.jenkins_url}/job/{self.job_name}/{build_number}/api/json?tree=artifacts[*]"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json().get('artifacts', [])

    def _find_apk_in_build_folder(self, artifacts: list) -> dict | None:
        """
        在Build文件夹下查找APK文件

        Args:
            artifacts: 产物列表

        Returns:
            APK产物信息，未找到返回None
        """
        for artifact in artifacts:
            relative_path = artifact.get('relativePath', '')
            filename = artifact.get('fileName', '')

            # 必须在Build文件夹下且是APK文件
            if relative_path.startswith('Build/') and filename.endswith('.apk'):
                return artifact

        return None

    def _parse_apk_filename(self, filename: str) -> dict:
        """
        解析APK文件名

        示例: P9_XProject_Android_20260327_99_SVN173687_dev_0.31.0_3100_SDK_NONE.apk

        Returns:
            {
                'version': '0.31.0',
                'build_number': 99,
                'svn_revision': 173687,
                'version_code': 3100,
                'date': '20260327'
            }
        """
        import re

        # 移除.apk后缀
        name = filename.replace('.apk', '')

        # 分割各部分
        parts = name.split('_')

        result = {
            'version': 'unknown',
            'build_number': 0,
            'svn_revision': 0,
            'version_code': 0,
            'date': ''
        }

        # 解析各字段
        for i, part in enumerate(parts):
            # 日期 (8位数字)
            if re.match(r'^\d{8}$', part):
                result['date'] = part
            # 构建号 (纯数字，较小)
            elif part.isdigit() and int(part) < 10000 and i > 2:
                if result['build_number'] == 0:
                    result['build_number'] = int(part)
            # SVN版本号 (以SVN开头)
            elif part.startswith('SVN'):
                result['svn_revision'] = int(part.replace('SVN', ''))
            # 版本号 (x.x.x格式)
            elif re.match(r'^\d+\.\d+\.\d+$', part):
                result['version'] = part
            # 版本码 (纯数字，较大)
            elif part.isdigit() and int(part) >= 1000:
                result['version_code'] = int(part)

        return result
```

**配置项**:
```python
jenkins_config = {
    'base_url': 'http://192.168.9.154:8080',
    'job_name': 'P9_XProject_Android_BrawlStars_Release',
    'max_builds_to_search': 20,    # 最多向下查找多少个构建
    'download_timeout': 300,        # 下载超时(秒)
    'retry_count': 3,               # 重试次数
}
```

### 4.2 模拟器管理模块 (EmulatorManager)

**文件**: `src/ci/emulator_manager.py`

**核心功能**:
- 雷电模拟器启动/关闭控制
- ADB连接状态检测
- APK安装和卸载
- 游戏启动控制

**关键接口**:
```python
class EmulatorManager:
    def start_emulator(timeout: int = 60) -> bool
    def stop_emulator() -> bool
    def is_emulator_running() -> bool
    def install_package(apk_path: Path) -> bool
    def start_game() -> bool
    def get_emulator_status() -> EmulatorStatus
```

**雷电模拟器特定实现**:
- 使用 `dnplayer.exe` 命令行参数控制实例
- 通过ADB端口5555连接
- 支持 `ldconsole.exe` 命令行工具

### 4.3 部署管理模块 (DeployManager)

**文件**: `src/ci/deploy_manager.py`

**核心功能**:
- 编排完整的部署流程
- 版本检查 → 下载 → 启动模拟器 → 安装 → 启动游戏

**关键接口**:
```python
class DeployManager:
    def deploy_latest_package() -> DeployResult
    def prepare_environment() -> bool
    def cleanup_environment() -> bool
```

### 4.4 异常捕获模块 (ExceptionHandler)

**文件**: `src/ci/exception_handler.py`

**核心功能**:
- 任务执行装饰器，自动捕获异常
- 失败时自动保存截图
- 记录完整堆栈信息
- 导出任务执行日志

**关键接口**:
```python
class ExceptionHandler:
    @staticmethod
    def wrap_task(task_func)  # 装饰器
    def capture_failure(exception: Exception, task: BaseJumpTask) -> FailureInfo
    def save_screenshot(frame, name: str) -> Path
    def save_log_dump(task: BaseJumpTask) -> Path
```

**数据结构**:
```python
@dataclass
class FailureInfo:
    task_name: str
    timestamp: str
    error_type: str
    error_message: str
    stack_trace: str
    screenshot_path: str | None
    log_path: str
    context: dict
```

### 4.5 测试结果管理模块 (TestResultManager)

**文件**: `src/ci/test_result_manager.py`

**核心功能**:
- 保存每次测试的完整结果
- 生成每日汇总报告
- 历史记录查询
- 数据清理

**关键接口**:
```python
class TestResultManager:
    def save_task_result(result: TaskResult) -> Path
    def generate_daily_report(date: date) -> DailyReport
    def get_test_history(days: int = 7) -> list[TestSummary]
    def export_report(format: str) -> Path
```

### 4.6 企业微信通知模块 (WeComNotifier)

**文件**: `src/ci/notifier/wecom_notifier.py`

**核心功能**:
- 发送Markdown格式消息
- 支持发送图片（失败截图）
- 每日报告推送

**企业微信机器人配置指南**:
1. 在企业微信群中添加机器人
2. 获取Webhook URL (格式: `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx`)
3. 在GUI配置中填入Webhook URL

**消息模板**:
```
📊 CI测试报告
────────────────────────────────
版本: v1.2.3 (#123)
状态: ✅ 通过 / ❌ 失败
耗时: 5分32秒
────────────────────────────────
任务统计:
• 自动登录: ✅ 成功
• 新手教程: ✅ 成功
────────────────────────────────
失败详情: [查看报告链接]
```

---

## 五、配置设计

### 5.1 CI配置文件 (`configs/ci_config.json`)

```json
{
    "jenkins": {
        "base_url": "http://jenkins.example.com:8080",
        "job_name": "game-build",
        "artifact_pattern": "*.apk",
        "timeout_seconds": 300,
        "retry_count": 3
    },
    "emulator": {
        "type": "ldplayer",
        "path": "C:\\LDPlayer\\LDPlayer9\\dnplayer.exe",
        "adb_port": 5555,
        "start_timeout": 60,
        "auto_close": true
    },
    "game": {
        "package_name": "com.lmd.xproject.dev",
        "startup_timeout": 120
    },
    "test_schedule": {
        "enabled": false,
        "cron": "0 9 * * *",
        "timezone": "Asia/Shanghai"
    },
    "notification": {
        "wecom_webhook": "",
        "notify_on_success": true,
        "notify_on_failure": true,
        "mentioned_on_failure": ["@all"]
    },
    "storage": {
        "keep_results_days": 30,
        "keep_packages_count": 5
    }
}
```

### 5.2 config.py 新增配置选项

```python
ci_config_option = ConfigOption(
    'CI测试配置',
    {
        '启用CI测试': False,
        'Jenkins地址': '',
        '模拟器路径': '',
        '企业微信Webhook': '',
        '定时测试': '禁用',
        '每日报告': True,
    },
    config_type={
        '定时测试': {'type': 'drop_down', 'options': ['禁用', '每日一次', '每日两次']},
    },
    icon=FluentIcon.CLOUD_SYNC
)
```

---

## 六、数据存储方案

```
test_results/
├── {YYYY-MM-DD}/
│   ├── {HH-MM-SS}/
│   │   ├── report.json          # 测试报告JSON
│   │   ├── report.html          # HTML报告
│   │   ├── screenshots/         # 截图目录
│   │   │   ├── login_success.png
│   │   │   └── failure_*.png    # 失败截图
│   │   └── logs/
│   │       ├── task.log
│   │       └── stack_trace.txt
│
├── daily_reports/
│   └── {YYYY-MM-DD}_report.html
│
├── history.json                 # 历史记录索引
└── stats.json                   # 统计数据

packages/
├── game_v1.2.3_123.apk
└── game_v1.2.2_122.apk
```

---

## 七、关键流程

### 7.1 CI测试主流程

```
CITestTask.run():
│
├── 1. 准备阶段
│   ├── 初始化异常处理器
│   ├── 记录开始时间
│   └── 创建测试目录
│
├── 2. 包管理与部署
│   ├── 获取Jenkins最新包信息
│   ├── 版本对比
│   ├── 下载APK(如需更新)
│   ├── 启动雷电模拟器
│   ├── 安装APK
│   └── 启动游戏
│
├── 3. 测试执行
│   ├── 执行 AutoLoginTask (带异常捕获)
│   ├── 执行 AutoTutorialTask (带异常捕获)
│   └── 其他配置的任务
│
├── 4. 结果处理
│   ├── 生成测试报告
│   └── 更新历史记录
│
├── 5. 通知发送
│   └── 发送企业微信通知
│
└── 6. 清理
    └── 清理旧数据
```

### 7.2 任务失败捕获流程

```
ExceptionHandler.wrap_task():
│
├── try: 执行任务
│
├── except TaskTimeoutError:
│   ├── 保存当前帧截图
│   └── 记录超时上下文
│
├── except Exception:
│   ├── 保存异常截图
│   ├── 记录完整堆栈
│   └── 导出任务日志
│
└── finally: 清理临时状态
```

---

## 八、新增依赖

```txt
# requirements.txt 新增
requests>=2.31.0           # HTTP请求(Jenkins API)
schedule>=1.2.0            # 定时任务调度
jinja2>=3.1.0              # HTML报告模板
pillow>=10.0.0             # 图片处理
```

---

## 九、关键文件修改清单

| 文件路径 | 修改类型 | 说明 |
|---------|---------|------|
| `config.py` | 修改 | 添加CI配置选项 |
| `src/globals.py` | 修改 | 添加CI测试状态 |
| `src/task/AutoLoginTask.py` | 修改 | 增强异常捕获 |
| `src/task/AutoTutorialTask.py` | 修改 | 增强异常捕获 |

---

## 十、实施步骤

### 第一阶段: 包管理与部署
1. 创建 `src/ci/` 目录结构
2. 实现 `PackageManager` - Jenkins包下载
3. 实现 `EmulatorManager` - 雷电模拟器控制
4. 实现 `DeployManager` - 部署流程编排
5. 创建 `ci_config.json` 配置文件

### 第二阶段: 异常捕获增强
1. 实现 `ExceptionHandler` 基础框架
2. 增强 `AutoLoginTask` 异常捕获
3. 增强 `AutoTutorialTask` 异常捕获
4. 实现失败截图和日志保存

### 第三阶段: 结果管理与通知
1. 实现 `TestResultManager` - 结果存储
2. 实现 `ReportGenerator` - HTML报告
3. 实现 `WeComNotifier` - 企业微信通知
4. 实现每日报告汇总

### 第四阶段: 集成与GUI
1. 实现 `CITestTask` - 完整流程编排
2. 实现 `ci_tab.py` - GUI配置面板
3. 实现定时调度
4. 端到端测试验证

---

## 十一、验证方案

### 单元测试
- PackageManager: 模拟Jenkins API测试
- EmulatorManager: 模拟ADB命令测试
- WeComNotifier: 模拟HTTP请求测试

### 集成测试
- 完整CI流程测试: 下载 → 部署 → 测试 → 通知
- 异常场景测试: 模拟任务失败，验证截图保存和通知

### 端到端测试
1. 配置Jenkins地址和企业微信Webhook
2. 手动触发CI测试
3. 验证:
   - APK正确下载和安装
   - 测试流程正常执行
   - 失败时截图和日志正确保存
   - 企业微信通知正常发送
   - 报告正确生成

---

## 十二、游戏启动后自动触发测试一条龙任务

### 需求说明
- **触发时机**: 游戏进程启动后开始计时
- **等待时间**: 等待指定时间（默认60秒）后触发
- **任务范围**: 执行完整的 `TestAllInOneTask`（包含登录流程）
- **超时报错**: 游戏启动后指定时间内（默认60秒）没有成功触发任务则报错

### 流程图
```
游戏进程启动
    │
    ▼
开始计时（记录启动时间）
    │
    ▼
等待游戏稳定（配置的等待时间，默认60秒）
    │
    ├── 等待期间检测游戏窗口是否就绪
    │
    ▼
触发 TestAllInOneTask（完整流程）
    │
    ├── 成功触发 → 执行测试
    │
    └── 超时未触发（超过配置时间）
        │
        ▼
    保存截图 + 报错 + 发送通知
```

### 现有架构分析
- `AutoLoginTask` 完成后没有自动触发 `TestAllInOneTask` 的机制
- `TestAllInOneTask` 已支持调用其他任务，但反向触发不存在
- 需要新增：游戏进程监控 + 自动触发机制

### 实现方案

#### 新增 CITestTask 类
**文件**: `src/task/CITestTask.py`

```python
class CITestTask(BaseJumpTask):
    """CI测试任务 - 游戏启动后自动触发测试一条龙"""

    default_config = {
        '游戏启动后等待时间(秒)': 60,    # 游戏启动后等待时间
        '等待超时时间(秒)': 120,         # 等待游戏就绪的超时阈值
        '超时是否报错': True,            # 超时是否报错
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._game_start_time = None      # 游戏启动时间
        self._test_triggered = False      # 测试是否已触发

    def run(self):
        """主执行流程"""
        # 1. 记录游戏启动时间
        self._game_start_time = time.time()
        self.log_info(f"游戏进程已启动，开始计时...")

        # 2. 等待游戏稳定
        wait_time = self.config.get('游戏启动后等待时间(秒)', 60)
        timeout = self.config.get('等待超时时间(秒)', 120)

        if not self._wait_for_game_ready(wait_time, timeout):
            # 等待超时
            if self.config.get('超时是否报错', True):
                self._save_error_screenshot("game_not_ready")
                self._send_timeout_notification()
                raise Exception(f"游戏启动后 {timeout} 秒内未就绪")
            return False

        # 3. 检查是否在超时时间内触发
        elapsed = time.time() - self._game_start_time
        if elapsed > timeout:
            self.log_error(f"触发超时: 已等待 {elapsed:.1f} 秒")
            self._save_error_screenshot("trigger_timeout")
            self._send_timeout_notification()
            raise Exception(f"触发任务超时（{elapsed:.1f}秒 > {timeout}秒）")

        # 4. 触发完整的 TestAllInOneTask
        self.log_info(f"游戏已就绪，触发测试一条龙任务（耗时 {elapsed:.1f} 秒）")
        self._test_triggered = True

        test_task = self.get_task_by_class(TestAllInOneTask)
        test_task.set_caller(self)
        result = test_task.run()

        return result

    def _wait_for_game_ready(self, wait_time: float, timeout: float) -> bool:
        """等待游戏就绪"""
        start_time = time.time()

        # 先等待配置的时间
        self.log_info(f"等待游戏稳定 {wait_time} 秒...")
        time.sleep(wait_time)

        # 检查游戏窗口是否就绪
        while time.time() - start_time < timeout:
            self.next_frame()

            # 检测游戏是否就绪
            if self._is_game_window_ready():
                self.log_info("游戏窗口已就绪")
                return True

            time.sleep(1)

        return False

    def _is_game_window_ready(self) -> bool:
        """检测游戏窗口是否就绪"""
        # 检查是否能正常截图
        if self.frame is not None:
            return True
        return False

    def _send_timeout_notification(self):
        """发送超时通知"""
        # 调用通知模块发送企业微信通知
        pass
```

#### 扩展 globals.py
**文件**: `src/globals.py`

```python
class Globals(QObject):
    # ... 现有属性 ...

    # CI测试相关
    _ci_test_running = False
    _game_start_time = None
    _auto_trigger_enabled = False

    def set_ci_test_running(self, running: bool):
        self._ci_test_running = running

    def is_ci_test_running(self) -> bool:
        return self._ci_test_running

    def mark_game_start_time(self):
        """记录游戏启动时间"""
        self._game_start_time = time.time()

    def get_game_elapsed_time(self) -> float:
        """获取游戏启动后经过的时间"""
        if self._game_start_time is None:
            return 0
        return time.time() - self._game_start_time

    def set_auto_trigger_enabled(self, enabled: bool):
        """设置是否启用自动触发"""
        self._auto_trigger_enabled = enabled

    def is_auto_trigger_enabled(self) -> bool:
        return self._auto_trigger_enabled
```

### 新增配置项
在 `config.py` 或 `ci_config.json` 中添加：

```python
ci_test_config = ConfigOption(
    'CI自动测试',
    {
        '游戏启动后等待时间(秒)': 60,
        '等待超时时间(秒)': 120,
        '超时是否报错': True,
    },
    config_description={
        '游戏启动后等待时间(秒)': '游戏进程启动后等待多少秒再触发测试',
        '等待超时时间(秒)': '游戏启动后多长时间内必须触发测试，超时则报错',
        '超时是否报错': '超时时是否抛出异常并记录失败',
    },
    icon=FluentIcon.STOP_WATCH
)
```

### GUI配置面板
在 CI 配置面板中添加：
- **游戏启动后等待时间(秒)**: 数字输入框，默认60
- **等待超时时间(秒)**: 数字输入框，默认120
- **超时是否报错**: 开关按钮

### 异常处理
- 超时时保存当前游戏截图到 `test_results/failures/`
- 记录详细的等待日志和耗时信息
- 发送企业微信通知，包含：超时原因、实际等待时间、失败截图

---

## 十五、智能异常处理策略（非致命错误继续执行）

### 15.1 核心思想

**关键原则**：只有确认游戏无法继续时才中断任务，否则记录错误后继续尝试。

```
错误发生
    │
    ▼
判断错误类型
    │
    ├── 非致命错误（如：单次检测失败、OCR识别失败等）
    │   │
    │   ├── 记录错误日志
    │   ├── 保存截图（可选）
    │   ├── 尝试恢复/重试
    │   └── 继续执行任务 ✅
    │
    └── 致命错误（游戏实际停止/卡住）
        │
        ├── 检测画面是否变化
        │   ├── 有变化 → 游戏还在运行 → 尝试恢复 → 继续执行 ✅
        │   └── 无变化 → 确认卡死 → 报错中断 ❌
```

### 15.2 错误分类

#### 非致命错误（记录后继续）
| 错误类型 | 说明 | 处理方式 |
|---------|------|---------|
| OCR识别失败 | 单次OCR未识别到目标 | 记录日志，继续尝试 |
| 模板匹配失败 | 单次find_one未匹配 | 记录日志，继续尝试 |
| YOLO检测失败 | 单次检测未找到目标 | 记录日志，继续尝试 |
| 单次点击失败 | 点击操作未响应 | 重试点击，继续执行 |
| 加载短暂停滞 | 加载进度短暂停滞 | 等待恢复，继续执行 |
| 界面检测超时(短) | 短时间内未检测到界面 | 延长等待，继续尝试 |

#### 致命错误（确认后中断）
| 错误类型 | 说明 | 判断条件 |
|---------|------|---------|
| 游戏进程退出 | 游戏窗口不存在 | 窗口句柄无效 |
| 画面长时间无变化 | 游戏卡死 | 连续N帧相同(如30秒) |
| 关键界面无法到达 | 无法进入下一步 | 多次重试后仍失败 |
| 加载长时间停滞 | 加载卡死 | 同一进度超过配置时间(如120秒) |
| 连续检测失败 | 持续无法获取有效信息 | 连续失败超过阈值(如50次) |

### 15.3 画面变化检测机制

**目的**：判断游戏是否还在正常运行

```python
class GameActivityDetector:
    """游戏活动状态检测器"""

    def __init__(self, threshold=0.95, history_size=10):
        self._frame_history = []  # 最近N帧
        self._hash_history = []   # 帧哈希历史
        self._threshold = threshold
        self._history_size = history_size
        self._last_change_time = time.time()

    def is_game_active(self, current_frame) -> bool:
        """
        检测游戏是否活跃

        Returns:
            bool: True 表示游戏画面有变化，还在运行
        """
        # 计算当前帧哈希
        current_hash = self._compute_frame_hash(current_frame)

        if self._hash_history:
            # 与历史帧对比
            similarity = self._compute_similarity(current_hash, self._hash_history[-1])

            if similarity < self._threshold:
                # 画面有变化
                self._last_change_time = time.time()
                self._hash_history.append(current_hash)
                if len(self._hash_history) > self._history_size:
                    self._hash_history.pop(0)
                return True

        self._hash_history.append(current_hash)
        return False

    def get_stagnant_duration(self) -> float:
        """获取画面停滞时长（秒）"""
        return time.time() - self._last_change_time

    def is_stagnant(self, timeout: float = 30.0) -> bool:
        """判断画面是否停滞超时"""
        return self.get_stagnant_duration() > timeout

    def _compute_frame_hash(self, frame):
        """计算帧哈希（简化版）"""
        # 缩小图像后计算均值哈希
        import cv2
        small = cv2.resize(frame, (16, 16))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        avg = gray.mean()
        return (gray > avg).flatten().tobytes()

    def _compute_similarity(self, hash1, hash2) -> float:
        """计算哈希相似度"""
        if len(hash1) != len(hash2):
            return 0.0
        same = sum(a == b for a, b in zip(hash1, hash2))
        return same / len(hash1)
```

### 15.4 智能任务执行器

**核心逻辑**：遇到错误时先判断游戏状态，再决定是否中断

```python
class SmartTaskExecutor:
    """智能任务执行器 - 非致命错误继续执行"""

    def __init__(self, task):
        self.task = task
        self.activity_detector = GameActivityDetector()
        self.error_history = []  # 错误历史记录
        self.continuous_fail_count = 0
        self.max_continuous_fails = 10  # 连续失败阈值（10次）

    def execute_with_recovery(self, action, action_name="操作"):
        """
        带恢复机制的执行

        Args:
            action: 要执行的操作函数
            action_name: 操作名称（用于日志）

        Returns:
            操作结果，如果无法恢复则返回 None
        """
        try:
            result = action()
            self.continuous_fail_count = 0  # 成功则重置失败计数
            return result

        except Exception as e:
            # 过滤 negative box 错误（OCR无害错误，不计入失败次数）
            if self._is_negative_box_error(e):
                self.task.log_debug(f"过滤OCR negative box错误: {e}")
                return None  # 直接返回，不计入失败

            self.continuous_fail_count += 1
            self._record_error(e, action_name)

            # 检查连续失败次数（阈值=10）
            if self.continuous_fail_count >= 10:
                self.task.log_error(f"连续失败 {self.continuous_fail_count} 次，终止任务")
                raise ContinuousFailureException("连续失败次数过多")

            # 检查是否为致命错误
            if self._is_fatal_error(e):
                self.task.log_error(f"致命错误: {e}")
                raise  # 抛出致命错误

            # 非致命错误：尝试恢复
            self.task.log_warning(f"非致命错误({action_name}): {e}，尝试恢复...")

            # 检查游戏状态
            if self._check_game_stagnant():
                self.task.log_error("游戏画面长时间无变化，确认卡死")
                raise GameStagnantException("游戏卡死")

            # 游戏还在运行，返回None表示此次失败但可继续
            return None

    def _is_negative_box_error(self, error: Exception) -> bool:
        """
        判断是否为 negative box 错误

        negative box 是OCR识别时产生的无效框，属于无害错误，不应计入失败次数
        """
        error_msg = str(error).lower()
        negative_keywords = ['negative', 'negative box', '负坐标', 'invalid box']
        return any(kw in error_msg for kw in negative_keywords)

    def _is_fatal_error(self, error: Exception) -> bool:
        """判断是否为致命错误"""
        fatal_exceptions = (
            GameProcessExitedException,  # 游戏进程退出
            GameStagnantException,        # 游戏卡死
            KeyboardInterrupt,            # 用户中断
        )
        return isinstance(error, fatal_exceptions)

    def _check_game_stagnant(self, timeout: float = 30.0) -> bool:
        """检查游戏是否停滞"""
        self.task.next_frame()
        if self.task.frame is not None:
            self.activity_detector.is_game_active(self.task.frame)
            return self.activity_detector.is_stagnant(timeout)
        return False

    def _record_error(self, error: Exception, action_name: str):
        """记录错误（不中断任务）"""
        self.error_history.append({
            'timestamp': time.time(),
            'action': action_name,
            'error': str(error),
            'type': type(error).__name__
        })
```

### 15.5 增强现有任务类

#### 修改 AutoLoginTask

```python
class AutoLoginTask(BaseJumpTask):

    def _execute_login_flow(self):
        """执行登录流程 - 非致命错误继续"""
        executor = SmartTaskExecutor(self)

        while True:
            # ... 现有逻辑 ...

            # 使用智能执行器执行操作
            result = executor.execute_with_recovery(
                lambda: self._handle_login_action(current_screen),
                f"处理{current_screen}界面"
            )

            # 检查结果
            if result is None:
                # 非致命错误，继续尝试
                self.log_info("操作失败但游戏正常，继续尝试...")
                continue

            # 正常结果处理
            # ...

        # 最终检查：如果到达这里，说明流程完成或确认无法继续
```

#### 修改 AutoTutorialTask / Phase1Handler

```python
class Phase1Handler:

    def _handle_combat_trigger(self):
        """处理战斗触发 - 非致命错误继续"""
        executor = SmartTaskExecutor(self.task)

        while not phase1_end_detected:
            try:
                # 战斗循环
                # ...

            except Exception as e:
                # 使用智能执行器判断
                result = executor.execute_with_recovery(
                    lambda: self._combat_step(),
                    "战斗步骤"
                )

                if result is None:
                    # 非致命错误，游戏还在运行，继续
                    continue

            # 检查游戏是否停滞
            if executor._check_game_stagnant(timeout=60.0):
                self._log_error("游戏画面60秒无变化，确认卡死")
                self.state_machine.fail("游戏卡死")
                break
```

### 15.6 配置项设计

**原则**：参考现有任务已配置的超时时间，不修改已有配置。

```python
smart_error_config = {
    '非致命错误继续执行': True,           # 启用智能错误处理
    '连续失败阈值': 10,                   # 连续失败10次后中断
    '错误截图保存': True,                # 是否保存错误截图
    '错误日志详细记录': True,            # 是否记录详细错误日志
}
```

**场景超时时间参考**（保持现有配置不变）：

| 场景 | 现有超时配置 | 配置位置 |
|------|-------------|---------|
| 登录等待 | 60秒 | AutoLoginTask.'登录等待超时(秒)' |
| 加载停滞 | 60秒 | AutoLoginTask.'加载停滞超时(秒)' |
| 选角界面检测 | 10秒 | AutoTutorialTask.'选角界面检测超时(秒)' |
| 自身检测 | 30秒 | AutoTutorialTask.'自身检测超时(秒)' |
| 目标检测 | 10秒 | AutoTutorialTask.'目标检测超时(秒)' |
| 普攻检测 | 10秒 | AutoTutorialTask.'普攻检测超时(秒)' |
| 第一阶段结束检测 | 120秒 | AutoTutorialTask.'第一阶段结束检测超时(秒)' |
| 画面停滞检测 | 根据场景动态调整 | 使用上述配置值 |

### 15.7 任务完成判断逻辑

**最终目的**：确认任务是否真正完成

```python
def is_task_really_completed(self) -> bool:
    """
    判断任务是否真正完成

    检查条件：
    1. 到达预期的最终界面
    2. 游戏画面在变化（表示还在运行）
    3. 没有致命错误

    Returns:
        bool: True 表示任务确实完成
    """
    # 检查是否到达目标界面
    if self._check_final_screen():
        return True

    # 检查游戏是否还在运行
    if self._check_game_stagnant():
        return False

    # 检查是否有未恢复的错误
    if self.continuous_fail_count > self.max_continuous_fails:
        return False

    return False  # 还未完成，继续执行
```

### 15.8 总结：错误处理流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                      错误发生                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  过滤无害错误                                                    │
│  ├── negative box 错误 → 不计入失败 → 【继续执行】               │
│  └── 其他错误 → 继续检测                                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  判断错误类型                                                    │
│  ├── 游戏进程退出 → 【致命】直接中断                             │
│  └── 其他错误 → 继续检测                                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  检查连续失败次数                                                │
│  ├── < 10次 → 继续检测游戏状态                                   │
│  └── >= 10次 → 【致命中断】                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  检测画面变化（使用场景对应超时时间）                            │
│  ├── 有变化 → 游戏正常 → 记录错误 → 【继续执行】                 │
│  └── 无变化超过超时 → 游戏卡死 → 【致命中断】                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  任务结束判断                                                    │
│  ├── 到达目标界面 → 【任务成功】                                 │
│  ├── 确认无法继续 → 【任务失败，保存报告】                       │
│  └── 还在执行中 → 【继续执行】                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 15.9 关键点总结

1. **非致命错误继续执行** - 只有确认游戏无法继续时才中断
2. **过滤negative box错误** - OCR无害错误不计入失败次数
3. **连续失败阈值=10次** - 超过10次连续失败才中断
4. **场景动态超时** - 使用现有配置的超时时间，不修改已有设置
5. **画面变化检测** - 通过帧哈希对比判断游戏是否还在运行

### 14.1 AutoLoginTask 现有异常捕获

| 异常类型 | 场景 | 当前处理 | 文件位置 |
|---------|------|---------|---------|
| `AutoLoginInputException` | 账号输入错误（输入框识别超时、激活失败、校验失败） | 记录错误、返回False | 第16行定义，第657-661行捕获 |
| `ValueError` | 模板匹配失败（find_one） | 跳过检测，继续执行 | 第862-865行等多处 |
| **加载停滞超时** | 加载百分比停滞超过60秒 | 保存截图、抛出异常 | 第575-580行 |
| **登录超时** | 超过配置的登录等待时间 | 记录失败、中断流程 | 第533-537行 |
| **最大尝试次数** | 达到最大登录尝试次数(默认5次) | 记录失败、中断流程 | 第539-543行 |

### 14.2 AutoTutorialTask 现有异常捕获

| 异常类型 | 场景 | 当前处理 | 文件位置 |
|---------|------|---------|---------|
| `Exception` (phase1_handler) | 自动战斗过程中任何异常 | 记录堆栈、状态机标记失败 | phase1_handler.py 第971-976行 |
| `ValueError` | 模板匹配/YOLO检测失败 | 跳过检测，继续执行 | 多处 |
| `Exception` (phase2_handler) | 第二阶段处理异常 | 记录堆栈、清理资源 | phase2_handler.py 第143行 |
| **状态机超时** | 各阶段检测超时 | 状态机标记失败、保存截图 | 各_handle方法 |

### 14.3 现有异常处理的不足

1. **没有统一的异常装饰器** - 每个方法单独处理，不一致
2. **异常上下文信息不足** - 缺少当前帧号、配置快照、执行路径等
3. **日志导出功能缺失** - 失败时没有导出完整日志文件
4. **没有结构化的失败报告** - 无法生成标准化的失败记录供后续分析
5. **TestAllInOneTask异常处理简单** - 第122-124行仅简单try-except break

### 14.4 异常捕获增强方案

#### 新增异常处理器 `ExceptionHandler`

**文件**: `src/ci/exception_handler.py`

```python
@dataclass
class FailureInfo:
    """失败信息结构"""
    task_name: str
    timestamp: str
    error_type: str           # 异常类型
    error_message: str
    stack_trace: str
    screenshot_path: str | None
    log_path: str
    context: dict = field(default_factory=dict)  # 执行上下文
    # context 包含:
    # - frame_number: 当前帧号
    # - last_action: 最后执行的操作
    # - config_snapshot: 配置快照
    # - resolution: 当前分辨率
    # - background_mode: 后台模式状态

class ExceptionHandler:
    """统一异常处理器"""

    @staticmethod
    def capture_failure(exception: Exception, task: BaseJumpTask) -> FailureInfo:
        """捕获失败信息"""
        return FailureInfo(
            task_name=task.name,
            timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
            error_type=type(exception).__name__,
            error_message=str(exception),
            stack_trace=traceback.format_exc(),
            screenshot_path=ExceptionHandler._save_screenshot(task),
            log_path=ExceptionHandler._export_log(task),
            context=ExceptionHandler._collect_context(task)
        )

    @staticmethod
    def wrap_task(task_func):
        """任务装饰器：自动捕获异常并记录"""
        @functools.wraps(task_func)
        def wrapper(self, *args, **kwargs):
            try:
                return task_func(self, *args, **kwargs)
            except Exception as e:
                failure = ExceptionHandler.capture_failure(e, self)
                self._last_failure = failure
                # 调用失败回调（如果存在）
                if hasattr(self, '_on_task_failure'):
                    self._on_task_failure(failure)
                raise
        return wrapper
```

#### 增强 AutoLoginTask

```python
# 在 AutoLoginTask 中添加

def _on_task_failure(self, failure: FailureInfo):
    """任务失败回调"""
    self._last_failure = failure
    self.log_error(f"任务失败: {failure.error_message}")
    self.log_error(f"截图已保存: {failure.screenshot_path}")

    # 更新全局状态
    from src import jump_globals
    if jump_globals:
        jump_globals.set_last_failure(failure)
```

#### 增强 AutoTutorialTask

```python
# 在 AutoTutorialTask 中添加

def _on_task_failure(self, failure: FailureInfo):
    """任务失败回调"""
    # 清理资源
    if self._phase1_handler:
        self._phase1_handler.cleanup()
    if self._phase2_handler:
        self._phase2_handler.cleanup()

    # 记录失败信息
    self.log_error(f"新手教程失败: {failure.error_message}")
```

#### 增强 TestAllInOneTask

```python
# 修改 TestAllInOneTask.run() 的异常处理

for task_class, task_name, enabled in tasks_sequence:
    if not enabled:
        continue

    try:
        task_instance = self.get_task_by_class(task_class)
        task_instance.set_caller(self)
        result = task_instance.run()

        if not result:
            # 获取子任务的失败信息
            if hasattr(task_instance, '_last_failure'):
                self._last_failure = task_instance._last_failure
            break
    except Exception as e:
        # 使用异常处理器捕获
        failure = ExceptionHandler.capture_failure(e, self)
        self._last_failure = failure
        break
```

### 14.5 异常类型扩展

新增自定义异常类，便于精确识别失败原因：

```python
# src/ci/exceptions.py

class CITestException(Exception):
    """CI测试基础异常"""
    pass

class PackageDownloadException(CITestException):
    """包下载异常"""
    pass

class EmulatorStartException(CITestException):
    """模拟器启动异常"""
    pass

class GameStartTimeoutException(CITestException):
    """游戏启动超时异常"""
    pass

class TaskTriggerTimeoutException(CITestException):
    """任务触发超时异常"""
    pass

class ScreenshotException(CITestException):
    """截图异常"""
    pass
```

### 14.6 失败信息存储

所有失败信息保存到 `test_results/failures/` 目录：

```
test_results/failures/
├── 2024-03-15_09-30-15_AutoLoginTask/
│   ├── screenshot.png         # 失败截图
│   ├── stack_trace.txt        # 堆栈信息
│   ├── context.json           # 执行上下文
│   └── task.log              # 任务日志导出
```

---

## 十三、企业微信机器人配置指南

### 步骤1: 在企业微信群中添加机器人
1. 打开目标企业微信群
2. 点击群设置 → 群机器人 → 添加机器人
3. 输入机器人名称（如"测试报告机器人"）

### 步骤2: 获取Webhook URL
添加完成后，会显示Webhook地址，格式如:
```
https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

### 步骤3: 在GUI中配置
在ok-jump的CI配置面板中，将Webhook URL粘贴到"企业微信Webhook"配置项。
