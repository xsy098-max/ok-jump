"""
CI/CD 自动化测试模块

提供完整的自动化测试流水线，包括：
- Jenkins包管理与下载
- 雷电模拟器管理
- 环境部署
- 测试执行
- 异常捕获
- 结果管理与报告
- 企业微信通知
"""

from src.ci.exceptions import (
    CITestException,
    PackageDownloadException,
    EmulatorStartException,
    GameStartTimeoutException,
    TaskTriggerTimeoutException,
    GameStagnantException,
    ContinuousFailureException,
    GameProcessExitedException,
)
from src.ci.package_manager import PackageManager, PackageInfo
from src.ci.emulator_manager import EmulatorManager, EmulatorStatus
from src.ci.exception_handler import (
    ExceptionHandler,
    FailureInfo,
    SmartTaskExecutor,
    GameActivityDetector,
)
from src.ci.test_result_manager import TestResultManager, TaskResult, TestReport
from src.ci.deploy_manager import DeployManager, DeploymentResult

__all__ = [
    # 异常类
    'CITestException',
    'PackageDownloadException',
    'EmulatorStartException',
    'GameStartTimeoutException',
    'TaskTriggerTimeoutException',
    'GameStagnantException',
    'ContinuousFailureException',
    'GameProcessExitedException',
    # 包管理
    'PackageManager',
    'PackageInfo',
    # 模拟器管理
    'EmulatorManager',
    'EmulatorStatus',
    # 异常处理
    'ExceptionHandler',
    'FailureInfo',
    'SmartTaskExecutor',
    'GameActivityDetector',
    # 测试结果管理
    'TestResultManager',
    'TaskResult',
    'TestReport',
    # 部署管理
    'DeployManager',
    'DeploymentResult',
]
