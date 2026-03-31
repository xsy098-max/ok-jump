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
        }

        # 配置类型(下拉框等)
        self.config_type = {
            '定时执行日期': {'type': "drop_down", 'options': ['每天', '工作日', '周末', '周一', '周二', '周三', '周四', '周五', '周六', '周日']},
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

    def run(self):
        """执行CI测试任务"""
        self.logger.info("=" * 60)
        self.logger.info("开始执行CI自动化测试任务")
        self.logger.info("=" * 60)

        self._start_time = time.time()

        try:
            # 1. 加载配置
            self._load_config()

            # 2. 初始化组件
            self._init_components()

            # 3. 执行部署
            deploy_result = self._execute_deployment()

            if not deploy_result.success:
                self._handle_deployment_failure(deploy_result)
                return False

            # 4. 等待并触发测试任务
            test_result = self._execute_test_task()

            # 5. 保存结果
            self._save_results(deploy_result, test_result)

            # 6. 发送通知
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
            self._handle_continuous_failure(str(e))
            return False

        except Exception as e:
            self.logger.error(f"CI测试任务异常: {e}", exc_info=True)
            self._handle_exception(e)
            return False

    def _load_config(self):
        """加载CI配置"""
        # 从任务配置获取
        self._ci_config = {
            'jenkins_url': self.config.get('Jenkins服务器地址', 'http://192.168.9.154:8080'),
            'jenkins_job': self.config.get('Jenkins Job名称', 'P9_XProject_Android_BrawlStars_Release'),
            'emulator_path': self.config.get('模拟器路径', 'C:\\LDPlayer\\LDPlayer9\\dnplayer.exe'),
            'download_dir': self.config.get('APK下载目录', 'packages'),
            'package_name': self.config.get('游戏包名', 'com.lmd.xproject.dev'),
            'adb_port': self.config.get('ADB端口', 5555),
            'instance_index': self.config.get('模拟器实例索引', 0),
            'wecom_webhook': self.config.get('企业微信Webhook', ''),
            'task_trigger_delay': self.config.get('任务触发延迟(秒)', 60),
            'continuous_failure_threshold': self.config.get('连续失败阈值', 10),
            # 定时执行配置
            'schedule_enabled': self.config.get('启用定时执行', False),
            'schedule_hour': self.config.get('定时执行时间(时)', 9),
            'schedule_minute': self.config.get('定时执行时间(分)', 0),
            'schedule_day': self.config.get('定时执行日期', '每天'),
            # 超时配置
            'emulator_timeout': self.config.get('模拟器启动超时(秒)', 60),
            'game_start_timeout': self.config.get('游戏启动超时(秒)', 60),
            'task_trigger_timeout': self.config.get('任务触发超时(秒)', 120),
            # Jenkins配置
            'max_builds_to_search': self.config.get('最大查找构建数', 20),
            'download_timeout': self.config.get('下载超时(秒)', 300),
            'keep_old_packages': self.config.get('保留旧包数量', 3),
        }

        # 尝试从配置文件加载
        config_file = Path('configs/ci_config.json')
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                self._ci_config.update(file_config)
                self.logger.info("已加载CI配置文件")
            except Exception as e:
                self.logger.warning(f"加载CI配置文件失败: {e}")

        self.logger.info(f"CI配置: {self._ci_config}")

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
            if self._test_report:
                success = self._notifier.send_test_result(self._test_report)
                if success:
                    self.logger.info("企业微信通知发送成功")
                else:
                    self.logger.warning("企业微信通知发送失败")
        except Exception as e:
            self.logger.error(f"发送通知异常: {e}")

    def _handle_deployment_failure(self, deploy_result: DeploymentResult):
        """处理部署失败"""
        self.logger.error(f"部署失败: {deploy_result.error_message}")

        # 发送告警
        if self._notifier:
            self._notifier.send_alert(
                title="部署失败",
                message=f"CI部署失败: {deploy_result.error_message}"
            )

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

    def _handle_exception(self, exception: Exception):
        """处理异常"""
        # 发送告警
        if self._notifier:
            self._notifier.send_alert(
                title="CI测试异常",
                message=f"CI测试任务发生异常: {type(exception).__name__}: {exception}"
            )

    def _cleanup(self):
        """清理环境"""
        self.logger.info("清理CI环境...")

        try:
            if self._deploy_manager:
                self._deploy_manager.cleanup()
        except Exception as e:
            self.logger.warning(f"清理环境失败: {e}")

        self.logger.info("CI环境清理完成")

    def get_task_by_class(self, task_class):
        """
        获取指定类的任务实例

        Args:
            task_class: 任务类

        Returns:
            任务实例，如果无法获取则返回None
        """
        try:
            # 尝试从ok框架获取
            if hasattr(og, 'get_task_by_class'):
                return og.get_task_by_class(task_class)

            # 尝试直接实例化
            return task_class()

        except Exception as e:
            self.logger.error(f"获取任务实例失败: {e}")
            return None
