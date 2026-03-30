"""
CI部署管理模块

整合包下载、模拟器管理、游戏启动的完整部署流程
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from src.ci.package_manager import PackageManager, PackageInfo
from src.ci.emulator_manager import EmulatorManager, EmulatorStatus
from src.ci.exceptions import (
    PackageDownloadException,
    EmulatorStartException,
    GameStartTimeoutException,
    TaskTriggerTimeoutException,
    GameProcessExitedException
)


logger = logging.getLogger(__name__)


@dataclass
class DeploymentResult:
    """部署结果"""
    success: bool                    # 是否成功
    package_info: Optional[PackageInfo] = None  # 包信息
    local_apk_path: Optional[Path] = None       # 本地APK路径
    error_message: str = ""         # 错误信息
    duration: float = 0.0           # 部署耗时(秒)


class DeployManager:
    """
    CI部署管理器

    功能：
    - 从Jenkins下载最新APK
    - 启动雷电模拟器
    - 安装APK到模拟器
    - 启动游戏并等待进程
    - 触发自动化测试任务

    使用示例：
        manager = DeployManager(config)
        result = manager.deploy()

        if result.success:
            manager.wait_and_trigger_task(callback)
    """

    def __init__(
        self,
        jenkins_url: str,
        jenkins_job: str,
        emulator_path: str,
        package_name: str = "com.lmd.xproject.dev",
        adb_port: int = 5555,
        instance_index: int = 0,
        download_dir: str = "packages",
        emulator_timeout: int = 60,
        game_start_timeout: int = 60,
        task_trigger_timeout: int = 120,
        task_trigger_delay: int = 60,
        max_builds_to_search: int = 20,
        download_timeout: int = 300,
        keep_old_packages: int = 3
    ):
        """
        初始化部署管理器

        Args:
            jenkins_url: Jenkins服务器地址
            jenkins_job: Job名称
            emulator_path: 模拟器可执行文件路径
            package_name: 游戏包名
            adb_port: ADB端口
            instance_index: 模拟器实例索引
            download_dir: APK下载目录
            emulator_timeout: 模拟器启动超时(秒)
            game_start_timeout: 游戏启动超时(秒)
            task_trigger_timeout: 任务触发超时(秒)
            task_trigger_delay: 任务触发延迟(秒)，游戏进程启动后等待多久触发任务
            max_builds_to_search: 从Jenkins查找APK时最多遍历多少个构建
            download_timeout: APK下载超时(秒)
            keep_old_packages: 本地最多保留多少个旧版本APK
        """
        self.jenkins_url = jenkins_url
        self.jenkins_job = jenkins_job
        self.package_name = package_name
        self.game_start_timeout = game_start_timeout
        self.task_trigger_timeout = task_trigger_timeout
        self.task_trigger_delay = task_trigger_delay
        self.keep_old_packages = keep_old_packages

        # 初始化子管理器
        self.package_manager = PackageManager(
            jenkins_url=jenkins_url,
            job_name=jenkins_job,
            download_dir=download_dir,
            max_builds_to_search=max_builds_to_search,
            download_timeout=download_timeout
        )

        self.emulator_manager = EmulatorManager(
            emulator_path=emulator_path,
            package_name=package_name,
            adb_port=adb_port,
            instance_index=instance_index,
            start_timeout=emulator_timeout
        )

        # 状态追踪
        self._current_package: Optional[PackageInfo] = None
        self._local_apk_path: Optional[Path] = None
        self._game_process_started = False

    def deploy(self, skip_download: bool = False) -> DeploymentResult:
        """
        执行完整部署流程

        流程:
        1. 从Jenkins下载最新APK (可选)
        2. 启动模拟器
        3. 安装APK
        4. 启动游戏

        Args:
            skip_download: 是否跳过下载步骤（使用本地已有APK）

        Returns:
            DeploymentResult: 部署结果
        """
        start_time = time.time()
        logger.info("=" * 50)
        logger.info("开始CI部署流程")
        logger.info("=" * 50)

        try:
            # 步骤1: 下载APK
            if not skip_download:
                logger.info("[步骤1] 从Jenkins下载最新APK...")
                try:
                    package_info = self.package_manager.find_latest_apk_build()

                    # 检查是否需要下载
                    if self.package_manager.should_download(package_info.build_number):
                        self._local_apk_path = self.package_manager.download_package(package_info.url)
                    else:
                        # 使用本地已有的APK
                        local_build = self.package_manager.get_local_build_number()
                        apk_files = list(Path("packages").glob("*.apk"))
                        for apk in apk_files:
                            info = self.package_manager._parse_apk_filename(apk.name)
                            if info['build_number'] == local_build:
                                self._local_apk_path = apk
                                break

                    self._current_package = package_info
                    logger.info(f"APK准备完成: {package_info.filename}")

                except PackageDownloadException as e:
                    logger.error(f"APK下载失败: {e}")
                    return DeploymentResult(
                        success=False,
                        error_message=str(e),
                        duration=time.time() - start_time
                    )
            else:
                logger.info("[步骤1] 跳过下载，使用本地APK")

            # 步骤2: 启动模拟器
            logger.info("[步骤2] 启动雷电模拟器...")
            try:
                self.emulator_manager.start_emulator()
            except EmulatorStartException as e:
                logger.error(f"模拟器启动失败: {e}")
                return DeploymentResult(
                    success=False,
                    error_message=str(e),
                    duration=time.time() - start_time
                )

            # 步骤3: 安装APK
            logger.info("[步骤3] 安装APK到模拟器...")
            if self._local_apk_path and self._local_apk_path.exists():
                install_success = self.emulator_manager.install_package(self._local_apk_path)
                if not install_success:
                    return DeploymentResult(
                        success=False,
                        error_message="APK安装失败",
                        duration=time.time() - start_time
                    )
            else:
                return DeploymentResult(
                    success=False,
                    error_message="未找到APK文件",
                    duration=time.time() - start_time
                )

            # 步骤4: 启动游戏
            logger.info("[步骤4] 启动游戏...")
            game_started = self.emulator_manager.start_game()
            if not game_started:
                return DeploymentResult(
                    success=False,
                    error_message="游戏启动命令发送失败",
                    duration=time.time() - start_time
                )

            # 等待游戏进程启动
            logger.info(f"等待游戏进程启动 (超时: {self.game_start_timeout}秒)...")
            if not self._wait_for_game_process(self.game_start_timeout):
                return DeploymentResult(
                    success=False,
                    error_message="游戏进程启动超时",
                    duration=time.time() - start_time
                )

            self._game_process_started = True

            duration = time.time() - start_time
            logger.info("=" * 50)
            logger.info(f"CI部署流程完成，耗时: {duration:.1f}秒")
            logger.info("=" * 50)

            return DeploymentResult(
                success=True,
                package_info=self._current_package,
                local_apk_path=self._local_apk_path,
                duration=duration
            )

        except Exception as e:
            logger.error(f"部署过程发生异常: {e}", exc_info=True)
            return DeploymentResult(
                success=False,
                error_message=str(e),
                duration=time.time() - start_time
            )

    def wait_and_trigger_task(
        self,
        task_callback: Callable[[], bool],
        timeout: Optional[int] = None
    ) -> bool:
        """
        等待指定时间后触发任务

        游戏进程启动后，等待task_trigger_delay秒，然后触发测试任务。
        如果超时则抛出TaskTriggerTimeoutException。

        Args:
            task_callback: 任务回调函数，返回True表示任务成功
            timeout: 超时时间(秒)，默认使用初始化时的值

        Returns:
            bool: 任务执行成功返回True

        Raises:
            TaskTriggerTimeoutException: 触发任务超时
            GameProcessExitedException: 游戏进程意外退出
        """
        if timeout is None:
            timeout = self.task_trigger_timeout

        if not self._game_process_started:
            logger.warning("游戏进程尚未启动，无法触发任务")
            return False

        logger.info(f"等待{self.task_trigger_delay}秒后触发测试任务...")

        # 等待延迟时间
        wait_start = time.time()
        while time.time() - wait_start < self.task_trigger_delay:
            # 检查游戏进程是否仍在运行
            if not self._is_game_process_running():
                logger.error("游戏进程意外退出")
                raise GameProcessExitedException("游戏进程在等待期间意外退出")
            time.sleep(1)

        logger.info("开始触发测试任务...")

        # 检查进程状态并执行任务
        task_start = time.time()
        
        # 再次检查游戏进程
        if not self._is_game_process_running():
            raise GameProcessExitedException("游戏进程在任务执行期间意外退出")

        try:
            result = task_callback()
            if result:
                logger.info("测试任务执行成功")
                return True
            else:
                logger.error("测试任务执行失败")
                return False
        except Exception as e:
            logger.error(f"任务执行异常: {e}")
            raise

    def _wait_for_game_process(self, timeout: int) -> bool:
        """
        等待游戏进程启动

        Args:
            timeout: 超时时间(秒)

        Returns:
            bool: 进程启动成功返回True
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self._is_game_process_running():
                logger.info("检测到游戏进程已启动")
                return True
            time.sleep(1)

        return False

    def _is_game_process_running(self) -> bool:
        """
        检测游戏进程是否正在运行

        通过ADB检测游戏包名对应的进程是否存在。

        Returns:
            bool: 进程存在返回True
        """
        try:
            from adbutils import adb

            # 获取设备 - 使用 device_list() 获取 AdbDevice 对象
            devices = adb.device_list()

            if not devices:
                return False

            device = devices[0]

            # 使用pidof命令检测进程
            result = device.shell(f"pidof {self.package_name}")
            pid = result.strip()

            if pid and pid.isdigit():
                return True

            # 备用方法: 使用ps命令
            result = device.shell(f"ps | grep {self.package_name}")
            return self.package_name in result

        except Exception as e:
            logger.debug(f"检测游戏进程失败: {e}")
            return False

    def cleanup(self):
        """
        清理部署环境

        - 关闭模拟器
        - 清理临时文件
        """
        logger.info("开始清理部署环境...")

        # 关闭模拟器
        try:
            if self.emulator_manager.is_emulator_running():
                self.emulator_manager.stop_emulator()
        except Exception as e:
            logger.warning(f"关闭模拟器失败: {e}")

        # 清理旧APK
        try:
            self.package_manager.cleanup_old_packages(keep=self.keep_old_packages)
        except Exception as e:
            logger.warning(f"清理旧APK失败: {e}")

        logger.info("部署环境清理完成")

    def get_current_package(self) -> Optional[PackageInfo]:
        """
        获取当前部署的包信息

        Returns:
            PackageInfo: 包信息，未部署则返回None
        """
        return self._current_package

    def get_emulator_status(self) -> EmulatorStatus:
        """
        获取模拟器状态

        Returns:
            EmulatorStatus: 模拟器状态
        """
        return self.emulator_manager.get_emulator_status()

    def is_game_running(self) -> bool:
        """
        检测游戏是否正在运行

        Returns:
            bool: 游戏运行中返回True
        """
        return self._is_game_process_running()
