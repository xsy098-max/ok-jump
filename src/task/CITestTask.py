"""
CI自动化测试任务

整合部署、测试、通知的完整CI流程
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from ok import BaseTask, og

from src.ci.deploy_manager import DeployManager, DeploymentResult
from src.ci.test_result_manager import TestResultManager, TestReport, TaskResult
from src.ci.notifier.wecom_notifier import WeComNotifier
from src.ci.exceptions import ContinuousFailureException


logger = logging.getLogger(__name__)


class CITestTask(BaseTask):
    """
    CI自动化测试任务

    完整流程:
    1. 从Jenkins下载最新APK
    2. 启动雷电模拟器
    3. 安装并启动游戏
    4. 等待游戏进程启动后60秒触发TestAllInOneTask
    5. 执行智能异常处理
    6. 保存测试结果
    7. 发送企业微信通知
    8. 生成每日报告

    使用示例:
        task = CITestTask()
        task.run()
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "CITestTask"
        self.description = "CI自动化测试 - 完整的部署和测试流程"

        # 默认配置
        self.default_config = {
            'Jenkins服务器地址': 'http://192.168.9.154:8080',
            'Jenkins Job名称': 'P9_XProject_Android_BrawlStars_Release',
            '模拟器路径': 'C:\\LDPlayer\\LDPlayer9\\dnplayer.exe',
            'APK下载目录': 'packages',
            '游戏包名': 'com.lmd.xproject.dev',
            'ADB端口': 5555,
            '模拟器实例索引': 0,
            '企业微信Webhook': '',
            '任务触发延迟(秒)': 60,
            '连续失败阈值': 10,
            # 定时执行配置
            '启用定时执行': False,
            '定时执行时间(时)': 9,
            '定时执行时间(分)': 0,
            '定时执行日期': '每天',
            # 超时配置
            '模拟器启动超时(秒)': 60,
            '游戏启动超时(秒)': 60,
            '任务触发超时(秒)': 120,
            # Jenkins配置
            '最大查找构建数': 20,
            '下载超时(秒)': 300,
            '保留旧包数量': 3,
            # 账号递增配置
            '账号递增启用': False,
            '账号递增模式': '从AutoLoginTask读取',  # 可选: '从AutoLoginTask读取', '使用模板'
            '账号模板': 'qwer878787{N}',
            '账号当前序号': 1,
            # 任务失败重试配置
            '失败自动重试': True,
            '重试次数': 3,
            '重试间隔(秒)': 60,
        }

        # 配置类型(下拉框等)
        self.config_type = {
            '定时执行日期': {'type': "drop_down", 'options': ['每天', '工作日', '周末', '周一', '周二', '周三', '周四', '周五', '周六', '周日']},
            '账号递增模式': {'type': "drop_down", 'options': ['从AutoLoginTask读取', '使用模板']},
        }

        # 配置描述
        self.config_description = {
            'Jenkins服务器地址': 'Jenkins服务器URL',
            'Jenkins Job名称': 'Jenkins Job名称',
            '模拟器路径': '雷电模拟器dnplayer.exe的完整路径',
            'APK下载目录': '从Jenkins下载的APK包存放目录',
            '游戏包名': '游戏APK的包名',
            'ADB端口': '模拟器ADB端口',
            '模拟器实例索引': '模拟器实例编号(从0开始)',
            '企业微信Webhook': '企业微信机器人Webhook URL',
            '任务触发延迟(秒)': '游戏进程启动后等待多久触发测试任务',
            '连续失败阈值': '连续失败多少次后中断任务',
            '启用定时执行': '是否启用定时自动执行CI测试',
            '定时执行时间(时)': '定时执行的小时(0-23)',
            '定时执行时间(分)': '定时执行的分钟(0-59)',
            '定时执行日期': '定时执行的日期周期',
            '模拟器启动超时(秒)': '模拟器启动最长等待时间',
            '游戏启动超时(秒)': '游戏启动最长等待时间',
            '任务触发超时(秒)': '任务触发最长等待时间',
            '最大查找构建数': '从Jenkins查找APK时最多遍历多少个构建',
            '下载超时(秒)': 'APK下载最长等待时间',
            '保留旧包数量': '本地最多保留多少个旧版本APK',
            # 账号递增配置
            '账号递增启用': '启用后每次测试自动使用新账号',
            '账号递增模式': '账号递增方式：从AutoLoginTask读取（推荐）或使用模板',
            '账号模板': '账号模板，{N}会被序号替换，如qwer878787{N} -> qwer87878786',
            '账号当前序号': '当前使用的账号序号，每次测试后自动+1（仅模板模式使用）',
            # 任务失败重试配置
            '失败自动重试': '启用后任务失败时自动重试',
            '重试次数': '失败后最多重试次数',
            '重试间隔(秒)': '每次重试之间的等待时间（秒）',
        }

        # 组件实例
        self._deploy_manager: Optional[DeployManager] = None
        self._result_manager: Optional[TestResultManager] = None
        self._notifier: Optional[WeComNotifier] = None

        # 测试结果
        self._test_report: Optional[TestReport] = None
        self._task_results = []

        # 状态追踪
        self._ci_config: Dict[str, Any] = {}
        self._start_time: float = 0
        
        # 重试状态追踪
        self._current_retry_count: int = 0
        self._retry_enabled: bool = False
        self._max_retries: int = 3
        
        # 最终截图路径
        self._final_screenshot_path: Optional[str] = None

    def run(self):
        """执行CI测试任务（支持失败自动重试）"""
        # CI任务特殊性：需要先启动模拟器才能截图
        # 在部署阶段，我们绕过 ok 框架的截图机制
        self.logger.info("=" * 60)
        self.logger.info("开始执行 CI 自动化测试任务")
        self.logger.info("注意: 将先启动模拟器，这可能需要一些时间...")
        self.logger.info("=" * 60)
        
        # 读取重试配置
        self._retry_enabled = self.config.get('失败自动重试', True)
        self._max_retries = self.config.get('重试次数', 3)
        retry_interval = self.config.get('重试间隔(秒)', 60)
        
        # 【重要】先加载配置，确保 _ci_config 有值
        self._load_config()
        
        # 【账号递增】任务开始前递增账号
        self._increment_account_before_test()
        
        try:
            # 执行任务（支持重试）
            for attempt in range(self._max_retries + 1):  # +1 是因为首次执行不算重试
                self._current_retry_count = attempt
                
                if attempt > 0:
                    self.logger.info("=" * 60)
                    self.logger.info(f"第 {attempt}/{self._max_retries} 次重试...")
                    self.logger.info("=" * 60)
                    
                    # 【关键修复】重试前递增账号
                    self._increment_account_for_retry()
                    
                    # 重试前等待
                    self.logger.info(f"等待 {retry_interval} 秒后重试...")                
                    # 重试前恢复截图循环
                    try:
                        if hasattr(og, 'executor') and og.executor:
                            og.executor.paused = False
                            self.logger.info("已恢复 TaskExecutor 截图循环")
                    except Exception as e:
                        self.logger.warning(f"恢复 TaskExecutor 失败: {e}")
                    time.sleep(retry_interval)
                
                result = self._run_once()
                
                if result:
                    # 成功，直接返回
                    return True
                
                # 失败，检查是否需要重试
                if not self._retry_enabled:
                    self.logger.info("失败自动重试未启用，不进行重试")
                    return False
                
                if attempt >= self._max_retries:
                    self.logger.info(f"已达到最大重试次数 {self._max_retries}，不再重试")
                    return False
                
                self.logger.info(f"任务失败，准备进行第 {attempt + 1} 次重试...")
            
            
            return False
        finally:
            # 【账号递增】无论任务成功还是失败，都保存递增后的账号
            self._increment_account_after_test()
    
    def _run_once(self):
        """执行一次CI测试任务（内部方法）"""
        self.logger.info("=" * 60)
        if self._current_retry_count > 0:
            self.logger.info(f"开始执行CI自动化测试任务（重试 {self._current_retry_count}/{self._max_retries}）")
        else:
            self.logger.info("开始执行CI自动化测试任务")
        self.logger.info("=" * 60)

        # 【关键】任务开始前重置环境，确保多次执行时环境隔离
        self._reset_task_environment()

        self._start_time = time.time()

        try:
            # 1. 初始化组件（配置已在 run() 开头加载）
            self._init_components()

            # 2. 执行部署
            deploy_result = self._execute_deployment()

            if not deploy_result.success:
                self._handle_deployment_failure(deploy_result)
                return False

            # 3. 等待并触发测试任务
            test_result = self._execute_test_task()

            # 4. 保存结果
            self._save_results(deploy_result, test_result)

            # 5. 保存最终截图（在清理环境前）
            self._save_final_screenshot()

            # 6. 发送通知（附带截图）
            self._send_notification()

            # 7. 清理环境
            self._cleanup()

            success = test_result
            self.logger.info("=" * 60)
            self.logger.info(f"CI自动化测试任务完成: {'成功' if success else '失败'}")
            self.logger.info("=" * 60)

            return success

        except ContinuousFailureException as e:
            self.logger.error(f"连续失败中断: {e}")
            # 保存截图
            self._save_final_screenshot()
            self._handle_continuous_failure(str(e))
            return False

        except Exception as e:
            self.logger.error(f"CI测试任务异常: {e}", exc_info=True)
            # 保存截图
            self._save_final_screenshot()
            self._handle_exception(e)
            return False

    def _load_config(self):
        """加载CI配置"""
        # 直接从配置文件读取，避免 ok 框架缓存问题
        config_file_path = Path('configs/CITestTask.json')
        file_config = {}
        if config_file_path.exists():
            try:
                with open(config_file_path, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                self.logger.info(f"从配置文件加载: {config_file_path}")
            except Exception as e:
                self.logger.warning(f"读取配置文件失败: {e}")
        
        # 优先级: 配置文件 > self.config (框架缓存) > 默认值
        def get_config(key, default):
            if key in file_config:
                return file_config[key]
            return self.config.get(key, default)
        
        self._ci_config = {
            'jenkins_url': get_config('Jenkins服务器地址', 'http://192.168.9.154:8080'),
            'jenkins_job': get_config('Jenkins Job名称', 'P9_XProject_Android_BrawlStars_Release'),
            'emulator_path': get_config('模拟器路径', 'C:\\LDPlayer\\LDPlayer9\\dnplayer.exe'),
            'download_dir': get_config('APK下载目录', 'packages'),
            'package_name': get_config('游戏包名', 'com.lmd.xproject.dev'),
            'adb_port': get_config('ADB端口', 5555),
            'instance_index': get_config('模拟器实例索引', 0),
            'wecom_webhook': get_config('企业微信Webhook', ''),
            'task_trigger_delay': get_config('任务触发延迟(秒)', 60),
            'continuous_failure_threshold': get_config('连续失败阈值', 10),
            # 定时执行配置
            'schedule_enabled': get_config('启用定时执行', False),
            'schedule_hour': get_config('定时执行时间(时)', 9),
            'schedule_minute': get_config('定时执行时间(分)', 0),
            'schedule_day': get_config('定时执行日期', '每天'),
            # 超时配置
            'emulator_timeout': get_config('模拟器启动超时(秒)', 60),
            'game_start_timeout': get_config('游戏启动超时(秒)', 60),
            'task_trigger_timeout': get_config('任务触发超时(秒)', 120),
            # Jenkins配置
            'max_builds_to_search': get_config('最大查找构建数', 20),
            'download_timeout': get_config('下载超时(秒)', 300),
            'keep_old_packages': get_config('保留旧包数量', 3),
            # 账号递增配置
            'account_increment_enabled': get_config('账号递增启用', False),
            'account_increment_mode': get_config('账号递增模式', '从AutoLoginTask读取'),
            'account_template': get_config('账号模板', 'qwer878787{N}'),
            'account_current_index': get_config('账号当前序号', 1),
            # 任务失败重试配置
            'retry_enabled': get_config('失败自动重试', True),
            'max_retries': get_config('重试次数', 3),
            'retry_interval': get_config('重试间隔(秒)', 60),
        }

        # 尝试从 ci_config.json 加载补充配置（仅填充缺失项，不覆盖 GUI 配置）
        ci_config_file = Path('configs/ci_config.json')
        if ci_config_file.exists():
            try:
                with open(ci_config_file, 'r', encoding='utf-8') as f:
                    extra_config = json.load(f)
                # 只添加缺失的配置项，不覆盖已有配置
                for key, value in extra_config.items():
                    if key not in self._ci_config:
                        self._ci_config[key] = value
                self.logger.info("已加载CI配置文件（仅补充缺失项）")
            except Exception as e:
                self.logger.warning(f"加载CI配置文件失败: {e}")

        self.logger.info(f"CI配置: emulator_path={self._ci_config['emulator_path']}, adb_port={self._ci_config['adb_port']}")

    def _init_components(self):
        """初始化各组件"""
        self.logger.info("初始化CI组件...")

        # 部署管理器
        self._deploy_manager = DeployManager(
            jenkins_url=self._ci_config['jenkins_url'],
            jenkins_job=self._ci_config['jenkins_job'],
            emulator_path=self._ci_config['emulator_path'],
            package_name=self._ci_config['package_name'],
            adb_port=self._ci_config['adb_port'],
            instance_index=self._ci_config['instance_index'],
            download_dir=self._ci_config.get('download_dir', 'packages'),
            task_trigger_delay=self._ci_config['task_trigger_delay'],
            emulator_timeout=self._ci_config.get('emulator_timeout', 60),
            game_start_timeout=self._ci_config.get('game_start_timeout', 60),
            task_trigger_timeout=self._ci_config.get('task_trigger_timeout', 120),
            max_builds_to_search=self._ci_config.get('max_builds_to_search', 20),
            download_timeout=self._ci_config.get('download_timeout', 300),
            keep_old_packages=self._ci_config.get('keep_old_packages', 3)
        )

        # 结果管理器
        self._result_manager = TestResultManager(
            results_dir="test_results",
            history_file="test_results/history.json"
        )

        # 企业微信通知器
        webhook = self._ci_config.get('wecom_webhook', '')
        if webhook:
            self._notifier = WeComNotifier(webhook_url=webhook)
        else:
            self.logger.warning("未配置企业微信Webhook，将跳过通知发送")

        self.logger.info("CI组件初始化完成")

    def _execute_deployment(self) -> DeploymentResult:
        """执行部署流程"""
        self.logger.info("-" * 40)
        self.logger.info("执行部署流程")
        self.logger.info("-" * 40)

        return self._deploy_manager.deploy(skip_download=False)

    def _execute_test_task(self) -> bool:
        """
        执行测试任务

        等待游戏进程启动后，延迟指定时间后触发TestAllInOneTask

        Returns:
            bool: 测试成功返回True
        """
        self.logger.info("-" * 40)
        self.logger.info("执行测试任务")
        self.logger.info("-" * 40)

        # 定义任务回调
        def run_test_all_in_one() -> bool:
            """执行TestAllInOneTask"""
            try:
                from src.task.TestAllInOneTask import TestAllInOneTask

                # 获取任务实例
                task = self.get_task_by_class(TestAllInOneTask)
                if task is None:
                    self.logger.error("无法获取TestAllInOneTask实例")
                    return False

                # 设置调用者
                task.set_caller(self)

                # 执行任务
                self.logger.info("开始执行TestAllInOneTask...")
                result = task.run()

                # 记录结果
                task_result = TaskResult(
                    task_name="TestAllInOneTask",
                    status="success" if result else "failed",
                    start_time=datetime.now().isoformat(),
                    end_time=datetime.now().isoformat(),
                    duration=0.0,
                    error_info=None if result else {"error_message": "任务执行失败"}
                )
                self._task_results.append(task_result)

                return result

            except Exception as e:
                self.logger.error(f"TestAllInOneTask执行异常: {e}", exc_info=True)

                # 记录失败结果
                task_result = TaskResult(
                    task_name="TestAllInOneTask",
                    status="failed",
                    start_time=datetime.now().isoformat(),
                    end_time=datetime.now().isoformat(),
                    duration=0.0,
                    error_info={"error_type": type(e).__name__, "error_message": str(e)}
                )
                self._task_results.append(task_result)

                return False

        # 等待并触发任务
        try:
            result = self._deploy_manager.wait_and_trigger_task(
                task_callback=run_test_all_in_one,
                timeout=120
            )
            return result

        except Exception as e:
            self.logger.error(f"触发测试任务失败: {e}")

            # 记录失败结果
            task_result = TaskResult(
                task_name="TaskTrigger",
                status="failed",
                start_time=datetime.now().isoformat(),
                end_time=datetime.now().isoformat(),
                duration=0.0,
                error_info={"error_type": type(e).__name__, "error_message": str(e)}
            )
            self._task_results.append(task_result)

            return False

    def _save_results(self, deploy_result: DeploymentResult, test_success: bool):
        """保存测试结果"""
        self.logger.info("保存测试结果...")

        # 计算统计信息
        total_tasks = len(self._task_results)
        passed = sum(1 for r in self._task_results if r.status == "success")
        failed = sum(1 for r in self._task_results if r.status == "failed")

        # 创建测试报告
        self._test_report = TestReport(
            report_id=f"ci_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.now().isoformat(),
            version=deploy_result.package_info.version if deploy_result.package_info else "unknown",
            build_number=deploy_result.package_info.build_number if deploy_result.package_info else 0,
            total_tasks=total_tasks,
            passed=passed,
            failed=failed,
            skipped=0,
            duration=time.time() - self._start_time,
            task_results=self._task_results,
            summary=f"部署{'成功' if deploy_result.success else '失败'}, 测试{'通过' if test_success else '失败'}"
        )

        # 保存报告
        try:
            report_path = self._result_manager.save_test_report(self._test_report)
            self.logger.info(f"测试报告已保存: {report_path}")
        except Exception as e:
            self.logger.error(f"保存测试报告失败: {e}")

    def _send_notification(self):
        """发送企业微信通知"""
        if self._notifier is None:
            self.logger.info("跳过通知发送(未配置Webhook)")
            return

        self.logger.info("发送企业微信通知...")

        try:
            # 发送测试报告
            if self._test_report:
                success = self._notifier.send_test_result(self._test_report)
                if success:
                    self.logger.info("企业微信测试报告发送成功")
                else:
                    self.logger.warning("企业微信测试报告发送失败")
            
            # 发送最终截图
            if self._final_screenshot_path:
                import os
                if os.path.exists(self._final_screenshot_path):
                    self.logger.info(f"发送最终截图: {self._final_screenshot_path}")
                    image_success = self._notifier.send_image(self._final_screenshot_path)
                    if image_success:
                        self.logger.info("最终截图发送成功")
                    else:
                        self.logger.warning("最终截图发送失败")
                else:
                    self.logger.warning(f"截图文件不存在: {self._final_screenshot_path}")
                    
        except Exception as e:
            self.logger.error(f"发送通知异常: {e}")

    def _handle_deployment_failure(self, deploy_result: DeploymentResult):
        """处理部署失败"""
        self.logger.error(f"部署失败: {deploy_result.error_message}")
        
        # 保存截图
        self._save_final_screenshot()

        # 发送告警
        if self._notifier:
            self._notifier.send_alert(
                title="部署失败",
                message=f"CI部署失败: {deploy_result.error_message}"
            )
            # 发送截图
            if self._final_screenshot_path:
                import os
                if os.path.exists(self._final_screenshot_path):
                    self._notifier.send_image(self._final_screenshot_path)

    def _handle_continuous_failure(self, message: str):
        """处理连续失败"""
        self.logger.error(f"连续失败中断: {message}")

        # 发送告警
        if self._notifier:
            self._notifier.send_alert(
                title="连续失败告警",
                message=f"CI测试连续失败达到阈值: {message}",
                mentioned_list=["@all"]
            )
            # 发送截图
            if self._final_screenshot_path:
                import os
                if os.path.exists(self._final_screenshot_path):
                    self._notifier.send_image(self._final_screenshot_path)

    def _handle_exception(self, exception: Exception):
        """处理异常"""
        # 发送告警
        if self._notifier:
            self._notifier.send_alert(
                title="CI测试异常",
                message=f"CI测试任务发生异常: {type(exception).__name__}: {exception}"
            )
            # 发送截图
            if self._final_screenshot_path:
                import os
                if os.path.exists(self._final_screenshot_path):
                    self._notifier.send_image(self._final_screenshot_path)

    def _save_final_screenshot(self):
        """
        保存最终截图
        
        在任务结束前保存当前画面，作为测试结果的可视化证据
        """
        try:
            # 获取当前帧
            frame = None
            if hasattr(self, 'frame') and self.frame is not None:
                frame = self.frame
            elif hasattr(og, 'device') and og.device:
                # 尝试从设备获取截图
                try:
                    frame = og.device.get_frame()
                except Exception:
                    pass
            
            if frame is not None:
                import cv2
                import os
                
                # 确保目录存在
                os.makedirs('test_results/screenshots', exist_ok=True)
                
                # 生成文件名
                timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
                filename = f"final_screenshot_{timestamp}.png"
                filepath = os.path.join('test_results/screenshots', filename)
                
                # 保存截图
                cv2.imwrite(filepath, frame)
                self._final_screenshot_path = filepath
                self.logger.info(f"最终截图已保存: {filepath}")
            else:
                self.logger.warning("无法获取当前帧，跳过截图保存")
                
        except Exception as e:
            self.logger.warning(f"保存最终截图失败: {e}")

    def _cleanup(self):
        """清理环境"""
        self.logger.info("清理CI环境...")

        # 先暂停 TaskExecutor 的截图循环，避免在模拟器关闭后尝试截图
        try:
            if hasattr(og, 'executor') and og.executor:
                og.executor.paused = True
                self.logger.info("已暂停 TaskExecutor 截图循环")
        except Exception as e:
            self.logger.warning(f"暂停 TaskExecutor 失败: {e}")

        try:
            if self._deploy_manager:
                self._deploy_manager.cleanup()
        except Exception as e:
            self.logger.warning(f"清理环境失败: {e}")

        self.logger.info("CI环境清理完成")

    # ==================== 环境隔离与状态重置 ====================

    def _reset_task_environment(self):
        """
        重置任务环境，确保多次执行时的环境隔离

        此方法在任务开始时调用，负责：
        1. 重置设备连接状态（清除缓存的离线设备）
        2. 重置 AutoCombatTask 的类变量状态
        3. 重置本任务实例的内部状态
        """
        self.logger.info("[环境重置] 开始重置任务环境...")

        # 1. 重置设备连接状态（关键：清除缓存的离线设备）
        self._reset_device_connection()

        # 2. 重置 AutoCombatTask 的类变量状态
        self._reset_autocombattask_state()

        # 3. 重置本任务实例的内部状态
        self._reset_internal_state()

        self.logger.info("[环境重置] 任务环境重置完成")

    def _reset_device_connection(self):
        """
        重置设备连接状态

        当模拟器被关闭后重新启动，ok框架的DeviceManager可能仍缓存着旧的设备引用。
        这会导致"device offline"错误。此方法清除缓存的设备引用，强制重新连接。
        """
        try:
            from ok import og

            if not hasattr(og, 'device_manager') or og.device_manager is None:
                self.logger.info("[环境重置] device_manager 不存在，跳过设备重置")
                return

            dm = og.device_manager

            # 清除缓存的设备引用
            if hasattr(dm, 'adb_device') and dm.adb_device is not None:
                self.logger.info("[环境重置] 清除缓存的 adb_device 引用")
                dm.adb_device = None

            # 重置设备管理器的内部状态
            if hasattr(dm, '_device'):
                dm._device = None

            # 断开现有 ADB 连接（如果有）
            try:
                from adbutils import adb
                # 断开所有连接
                for device_info in adb.list():
                    try:
                        addr = device_info.serial
                        if addr and ('127.0.0.1' in addr or 'emulator' in addr):
                            self.logger.info(f"[环境重置] 断开 ADB 连接: {addr}")
                            adb.disconnect(addr)
                    except Exception:
                        pass
            except Exception as e:
                self.logger.debug(f"[环境重置] 断开 ADB 连接时出错: {e}")

            self.logger.info("[环境重置] 设备连接状态已重置")

        except Exception as e:
            self.logger.warning(f"[环境重置] 重置设备连接失败: {e}")

    def _reset_autocombattask_state(self):
        """
        重置 AutoCombatTask 的类变量状态

        清除上次任务可能残留的状态，确保本次任务从头开始
        """
        try:
            from src.task.AutoCombatTask import AutoCombatTask

            # 调用类方法重置所有状态
            AutoCombatTask.reset_class_state()
            self.logger.info("[环境重置] AutoCombatTask 类状态已重置")

        except Exception as e:
            self.logger.warning(f"[环境重置] 重置 AutoCombatTask 状态失败: {e}")

    def _reset_internal_state(self):
        """
        重置本任务实例的内部状态
        """
        # 清空测试结果
        if hasattr(self, '_task_results'):
            self._task_results = []

        # 重置部署相关状态
        self._deploy_manager = None
        self._result_manager = None
        self._notifier = None

        self.logger.info("[环境重置] 内部状态已重置")

    def get_task_by_class(self, task_class):
        """
        获取指定类的任务实例

        从 og.executor.onetime_tasks 中查找已注册的任务实例。
        注意：不能直接实例化任务类，因为 BaseTask 需要参数初始化。

        Args:
            task_class: 任务类

        Returns:
            任务实例，如果无法获取则返回None
        """
        try:
            # 从 og.executor.onetime_tasks 中查找已注册的任务实例
            if hasattr(og, 'executor') and og.executor:
                for task in og.executor.onetime_tasks:
                    if isinstance(task, task_class):
                        return task

            self.logger.warning(f"未在 executor 中找到 {task_class.__name__} 实例")
            return None

        except Exception as e:
            self.logger.error(f"获取任务实例失败: {e}")
            return None

    # ==================== 账号递增功能 ====================

    def _increment_account_before_test(self):
        """
        在测试开始前递增账号

        从AutoLoginTask配置中读取当前账号，递增后设置到运行时配置。
        注意：实际保存到文件在 _increment_account_after_test 中进行。
        """
        if not self._ci_config.get('account_increment_enabled', False):
            self.logger.info("[账号递增] 未启用，跳过")
            return

        mode = self._ci_config.get('account_increment_mode', '从AutoLoginTask读取')

        if mode == '从AutoLoginTask读取':
            # 读取当前账号
            current_account = self._read_account_from_autologin()
            if current_account:
                self.logger.info(f"[账号递增] 当前账号: {current_account}")
                # 递增账号
                new_account = self._increment_account_string(current_account)
                self.logger.info(f"[账号递增] 递增后账号: {new_account}")
                # 设置到运行时配置（供本次测试使用）
                self._set_runtime_account(new_account)
                # 记录待保存的账号（任务结束时保存）
                self._pending_account = new_account
        else:
            # 使用模板模式
            template = self._ci_config.get('account_template', 'qwer878787{N}')
            current_index = self._ci_config.get('account_current_index', 1)
            new_account = template.replace('{N}', str(current_index))
            self.logger.info(f"[账号递增] 模板模式: 使用账号 {new_account}")
            self._set_runtime_account(new_account)
            self._pending_account = new_account
            self._pending_index = current_index + 1

    def _increment_account_after_test(self):
        """
        在测试结束后递增账号并保存

        无论任务成功还是失败，都应该递增账号序号供下次使用。
        """
        if not self._ci_config.get('account_increment_enabled', False):
            return

        mode = self._ci_config.get('account_increment_mode', '从AutoLoginTask读取')

        if mode == '从AutoLoginTask读取':
            # 保存递增后的账号到AutoLoginTask配置
            if hasattr(self, '_pending_account') and self._pending_account:
                self._save_account_to_autologin(self._pending_account)
                self.logger.info(f"[账号递增] 已保存新账号到配置: {self._pending_account}")
                self._pending_account = None
        else:
            # 模板模式：更新序号
            if hasattr(self, '_pending_index'):
                self._save_account_index(self._pending_index)
                self.logger.info(f"[账号递增] 已更新账号序号: {self._pending_index}")
                self._pending_index = None

    def _increment_account_for_retry(self):
        """
        重试前递增账号

        每次重试都应该使用新的账号，确保不会因为同一个账号失败而无限重试。
        例如：第一次 qwer984 失败，重试使用 qwer985，再重试使用 qwer986...
        """
        if not self._ci_config.get('account_increment_enabled', False):
            self.logger.info("[账号递增-重试] 未启用，跳过")
            return

        mode = self._ci_config.get('account_increment_mode', '从AutoLoginTask读取')

        if mode == '从AutoLoginTask读取':
            # 从上次保存的待定账号开始递增
            if hasattr(self, '_pending_account') and self._pending_account:
                current = self._pending_account
            else:
                # 如果没有待定账号，从配置重新读取
                current = self._read_account_from_autologin()

            if current:
                new_account = self._increment_account_string(current)
                self.logger.info(f"[账号递增-重试] 账号递增: {current} -> {new_account}")
                self._set_runtime_account(new_account)
                self._pending_account = new_account
        else:
            # 模板模式：继续递增序号
            if hasattr(self, '_pending_index'):
                current_index = self._pending_index
            else:
                current_index = self._ci_config.get('账号当前序号', 1) + 1

            template = self._ci_config.get('account_template', 'qwer878787{N}')
            new_account = template.replace('{N}', str(current_index))
            self.logger.info(f"[账号递增-重试] 模板模式: 使用账号 {new_account}")
            self._set_runtime_account(new_account)
            self._pending_account = new_account
            self._pending_index = current_index + 1

    def _read_account_from_autologin(self) -> Optional[str]:
        """
        从AutoLoginTask.json读取当前账号

        Returns:
            str: 当前账号，读取失败返回None
        """
        try:
            config_path = Path('configs/AutoLoginTask.json')
            if not config_path.exists():
                self.logger.warning("[账号递增] AutoLoginTask.json 不存在")
                return None

            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            account = config.get('账号', '')
            if not account:
                self.logger.warning("[账号递增] 账号配置为空")
                return None

            return account

        except Exception as e:
            self.logger.error(f"[账号递增] 读取账号失败: {e}")
            return None

    def _increment_account_string(self, account: str) -> str:
        """
        智能递增账号字符串

        支持多种格式:
        - qwer123 -> qwer124 (末尾数字递增)
        - abc001 -> abc002 (保留前导零)
        - xyz -> xyz1 (无数字后缀则添加)
        - 12345 -> 12346 (纯数字)

        Args:
            account: 原账号字符串

        Returns:
            str: 递增后的账号
        """
        import re

        if not account:
            return '1'

        # 查找末尾的数字部分
        match = re.search(r'(\d+)$', account)

        if match:
            # 找到末尾数字
            number_str = match.group(1)
            prefix = account[:match.start()]
            
            # 保留前导零的格式
            width = len(number_str)
            number = int(number_str) + 1
            new_number_str = str(number).zfill(width)
            
            return prefix + new_number_str
        else:
            # 没有数字后缀，添加1
            return account + '1'

    def _save_account_to_autologin(self, new_account: str) -> bool:
        """
        保存新账号到AutoLoginTask.json

        Args:
            new_account: 新账号

        Returns:
            bool: 保存成功返回True
        """
        try:
            config_path = Path('configs/AutoLoginTask.json')

            # 读取现有配置
            config = {}
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)

            # 更新账号
            config['账号'] = new_account

            # 保存
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            self.logger.info(f"[账号递增] 已保存账号到配置文件: {new_account}")
            return True

        except Exception as e:
            self.logger.error(f"[账号递增] 保存账号失败: {e}")
            return False

    def _set_runtime_account(self, account: str):
        """
        设置运行时账号配置

        更新AutoLoginTask的运行时配置，使其在本次测试中使用新账号。
        需要同时设置 og.config['ci_account'] 和 autologin_task.config['账号']，
        因为 AutoLoginTask._cfg() 优先从 og.config 获取账号。

        Args:
            account: 新账号
        """
        try:
            # 【关键】设置 og.config['ci_account']，这是 AutoLoginTask._cfg() 优先读取的
            if hasattr(og, 'config') and og.config is not None:
                og.config['ci_account'] = account
                og.config['ci_input_account'] = True
                self.logger.info(f"[账号递增] 已设置 og.config['ci_account']: {account}")
            else:
                self.logger.warning("[账号递增] og.config 不可用，尝试设置 AutoLoginTask.config")

            # 同时更新AutoLoginTask的运行时配置（作为备用）
            from src.task.AutoLoginTask import AutoLoginTask
            autologin_task = self.get_task_by_class(AutoLoginTask)

            if autologin_task:
                autologin_task.config['账号'] = account
                autologin_task.config['输入账号'] = True
                self.logger.info(f"[账号递增] 已设置 AutoLoginTask.config['账号']: {account}")
            else:
                self.logger.warning("[账号递增] 未找到AutoLoginTask实例")

        except Exception as e:
            self.logger.error(f"[账号递增] 设置运行时账号失败: {e}")

    def _save_account_index(self, index: int):
        """
        保存账号序号（模板模式）

        Args:
            index: 新的序号
        """
        try:
            config_path = Path('configs/CITestTask.json')

            # 读取现有配置
            config = {}
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)

            # 更新序号
            config['账号当前序号'] = index

            # 保存
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            self.logger.info(f"[账号递增] 已更新账号序号: {index}")

        except Exception as e:
            self.logger.error(f"[账号递增] 保存序号失败: {e}")
