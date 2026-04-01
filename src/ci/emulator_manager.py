"""
雷电模拟器管理模块

提供雷电模拟器的启动、关闭、APK安装、游戏启动等功能
"""

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from src.ci.exceptions import EmulatorStartException, GameStartTimeoutException


logger = logging.getLogger(__name__)


class EmulatorStatus(Enum):
    """模拟器状态"""
    STOPPED = "stopped"        # 已停止
    STARTING = "starting"      # 启动中
    RUNNING = "running"        # 运行中
    ERROR = "error"            # 错误


@dataclass
class EmulatorInfo:
    """模拟器信息"""
    name: str                  # 模拟器名称
    index: int                 # 实例索引
    adb_port: int              # ADB端口
    status: EmulatorStatus     # 状态


class EmulatorManager:
    """
    雷电模拟器管理器

    支持的功能：
    - 启动/关闭模拟器
    - 检测模拟器运行状态
    - 安装/卸载APK
    - 启动游戏

    使用示例:
        manager = EmulatorManager(
            emulator_path="C:\\LDPlayer\\LDPlayer9\\dnplayer.exe",
            package_name="com.lmd.xproject.dev"
        )
        manager.start_emulator()
        manager.install_package(Path("game.apk"))
        manager.start_game()
    """

    def __init__(
        self,
        emulator_path: str,
        package_name: str = "com.lmd.xproject.dev",
        adb_port: int = 5555,
        instance_index: int = 0,
        start_timeout: int = 60
    ):
        """
        初始化模拟器管理器

        Args:
            emulator_path: 模拟器可执行文件路径 (dnplayer.exe)
            package_name: 游戏包名
            adb_port: ADB端口
            instance_index: 模拟器实例索引
            start_timeout: 启动超时(秒)
        """
        self.emulator_path = Path(emulator_path)
        self.package_name = package_name
        self.adb_port = adb_port
        self.instance_index = instance_index
        self.start_timeout = start_timeout

        # 获取ldconsole路径
        self.emulator_dir = self.emulator_path.parent
        self.ldconsole_path = self.emulator_dir / "ldconsole.exe"

        # 设备序列号 (用于ADB连接)
        self.device_serial = f"emulator-{self.adb_port}"

    def start_emulator(self, timeout: Optional[int] = None) -> bool:
        """
        启动雷电模拟器

        Args:
            timeout: 超时时间(秒)，默认使用初始化时的值

        Returns:
            bool: 启动成功返回True

        Raises:
            EmulatorStartException: 启动失败
        """
        if timeout is None:
            timeout = self.start_timeout

        logger.info(f"开始启动雷电模拟器: {self.emulator_path}")
        logger.info(f"实例索引: {self.instance_index}, ADB端口: {self.adb_port}")

        # 检查模拟器路径是否存在
        if not self.emulator_path.exists():
            raise EmulatorStartException(f"模拟器路径不存在: {self.emulator_path}")

        # 检查是否已经在运行
        if self.is_emulator_running():
            logger.info("模拟器已在运行中")
            return True

        try:
            # 使用ldconsole启动模拟器
            if self.ldconsole_path.exists():
                cmd = [str(self.ldconsole_path), "launch", "--index", str(self.instance_index)]
                logger.info(f"执行命令: {' '.join(cmd)}")
                subprocess.run(
                    cmd,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=30
                )
            else:
                # 直接启动dnplayer
                cmd = [str(self.emulator_path)]
                logger.info(f"执行命令: {' '.join(cmd)}")
                subprocess.Popen(
                    cmd,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    cwd=str(self.emulator_dir)
                )

            # 等待模拟器启动
            logger.info(f"等待模拟器启动 (超时: {timeout}秒)...")
            start_time = time.time()

            while time.time() - start_time < timeout:
                if self.is_emulator_running():
                    logger.info("模拟器启动成功")
                    # 额外等待系统稳定
                    time.sleep(3)
                    # 刷新 ok 框架的设备连接
                    self._refresh_ok_device_connection()
                    return True
                time.sleep(2)

            raise EmulatorStartException(f"模拟器启动超时 ({timeout}秒)")

        except subprocess.TimeoutExpired:
            raise EmulatorStartException("启动命令执行超时")
        except Exception as e:
            raise EmulatorStartException(f"启动模拟器失败: {e}")

    def _refresh_ok_device_connection(self):
        """
        刷新 ok 框架的设备连接
        
        模拟器启动后，需要通知 ok 框架重新连接 ADB 设备
        """
        try:
            from ok import og
            from adbutils import adb
            
            # 先连接正确的端口
            adb.connect(f"127.0.0.1:{self.adb_port}", timeout=10)
            
            # 检查 ok 框架的设备管理器
            if hasattr(og, 'device') and og.device:
                # 调用设备的刷新方法
                device = og.device
                if hasattr(device, 'do_refresh'):
                    logger.info("刷新 ok 框架设备连接...")
                    device.do_refresh()
                    logger.info("ok 框架设备连接已刷新")
                elif hasattr(device, 'refresh'):
                    logger.info("刷新 ok 框架设备连接...")
                    device.refresh()
                    logger.info("ok 框架设备连接已刷新")
                else:
                    logger.debug("ok 设备对象没有刷新方法")
            else:
                logger.debug("ok 框架设备管理器未初始化")
                
        except Exception as e:
            logger.warning(f"刷新 ok 框架设备连接失败: {e}")

    def stop_emulator(self) -> bool:
        """
        关闭雷电模拟器

        Returns:
            bool: 关闭成功返回True
        """
        logger.info("开始关闭雷电模拟器")

        try:
            if self.ldconsole_path.exists():
                cmd = [str(self.ldconsole_path), "quit", "--index", str(self.instance_index)]
                logger.info(f"执行命令: {' '.join(cmd)}")
                subprocess.run(
                    cmd,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=30
                )
            else:
                # 使用taskkill关闭进程
                subprocess.run(
                    ["taskkill", "/F", "/IM", "dnplayer.exe"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=30
                )

            # 等待关闭
            for _ in range(10):
                if not self.is_emulator_running():
                    logger.info("模拟器已关闭")
                    return True
                time.sleep(1)

            logger.warning("模拟器关闭超时")
            return False

        except Exception as e:
            logger.error(f"关闭模拟器失败: {e}")
            return False

    def is_emulator_running(self) -> bool:
        """
        检测模拟器是否正在运行

        Returns:
            bool: 运行中返回True
        """
        try:
            # 方法1: 使用ldconsole查询状态
            if self.ldconsole_path.exists():
                cmd = [str(self.ldconsole_path), "isrunning", "--index", str(self.instance_index)]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=10
                )
                return "running" in result.stdout.lower() or "true" in result.stdout.lower()

        except Exception as e:
            logger.debug(f"检测模拟器状态失败: {e}")

        # 方法2: 使用ADB直接连接检测（使用配置的端口）
        # 雷电模拟器使用 emulator-{port} 格式的序列号
        try:
            from adbutils import adb
            # 尝试两种连接格式：emulator-{port} 和 127.0.0.1:{port}
            serial_patterns = [
                f"emulator-{self.adb_port}",
                f"127.0.0.1:{self.adb_port}"
            ]
            adb.connect(f"127.0.0.1:{self.adb_port}", timeout=5)
            devices = adb.device_list()
            for device in devices:
                for pattern in serial_patterns:
                    if pattern in device.serial:
                        logger.info(f"检测到模拟器设备: {device.serial}")
                        return True
        except Exception as e:
            logger.debug(f"ADB检测模拟器状态失败: {e}")

        return False

    def install_package(self, apk_path: Path) -> bool:
        """
        安装APK包

        Args:
            apk_path: APK文件路径

        Returns:
            bool: 安装成功返回True
        """
        if not apk_path.exists():
            raise FileNotFoundError(f"APK文件不存在: {apk_path}")

        logger.info(f"开始安装APK: {apk_path}")

        try:
            from adbutils import adb

            # 连接到模拟器（带重试）
            device = self._wait_for_adb_device(timeout=30)
            if device is None:
                raise Exception("等待ADB设备连接超时")

            # 安装APK（使用 install 方法，而非 install_apk）
            logger.info("正在安装APK...")
            result = device.install(str(apk_path), uninstall=True, flags=["-r", "-t"])
            logger.info(f"安装结果: {result}")

            logger.info("APK安装成功")
            return True

        except Exception as e:
            logger.error(f"APK安装失败: {e}")
            return False

    def _wait_for_adb_device(self, timeout: int = 30) -> Optional[object]:
        """
        等待ADB设备连接就绪

        模拟器重启后，ADB设备可能需要一些时间才能被识别。
        此方法会重试连接直到超时。

        Args:
            timeout: 超时时间(秒)

        Returns:
            AdbDevice: 连接的设备对象，超时返回None
        """
        from adbutils import adb
        import time

        start_time = time.time()
        serial_patterns = [
            f"emulator-{self.adb_port}",
            f"127.0.0.1:{self.adb_port}"
        ]

        while time.time() - start_time < timeout:
            try:
                # 尝试连接
                adb.connect(f"127.0.0.1:{self.adb_port}", timeout=5)

                # 获取设备列表
                devices = adb.device_list()

                # 查找匹配的设备
                for dev in devices:
                    for pattern in serial_patterns:
                        if pattern in dev.serial:
                            logger.info(f"ADB设备已就绪: {dev.serial}")
                            return dev

                # 设备列表不为空但没有匹配的设备
                if devices:
                    logger.debug(f"ADB设备列表: {[d.serial for d in devices]}，等待目标设备...")

            except Exception as e:
                logger.debug(f"ADB连接尝试失败: {e}")

            time.sleep(2)

        logger.error(f"等待ADB设备超时 ({timeout}秒)")
        return None

    def uninstall_package(self) -> bool:
        """
        卸载游戏包

        Returns:
            bool: 卸载成功返回True
        """
        logger.info(f"开始卸载包: {self.package_name}")

        try:
            # 等待ADB设备就绪
            device = self._wait_for_adb_device(timeout=30)
            if device is None:
                raise Exception("等待ADB设备连接超时")

            device.uninstall(self.package_name)

            logger.info("包卸载成功")
            return True

        except Exception as e:
            logger.error(f"包卸载失败: {e}")
            return False

    def start_game(self, timeout: int = 30) -> bool:
        """
        启动游戏

        Args:
            timeout: 等待超时(秒)

        Returns:
            bool: 启动成功返回True
        """
        logger.info(f"开始启动游戏: {self.package_name}")

        try:
            # 等待ADB设备就绪
            device = self._wait_for_adb_device(timeout=30)
            if device is None:
                raise Exception("等待ADB设备连接超时")

            # 启动游戏Activity
            # 使用monkey命令启动
            cmd = f"monkey -p {self.package_name} -c android.intent.category.LAUNCHER 1"
            device.shell(cmd)

            logger.info("游戏启动命令已发送")
            return True

        except Exception as e:
            logger.error(f"启动游戏失败: {e}")
            return False

    def get_emulator_status(self) -> EmulatorStatus:
        """
        获取模拟器状态

        Returns:
            EmulatorStatus: 模拟器状态
        """
        if self.is_emulator_running():
            return EmulatorStatus.RUNNING
        return EmulatorStatus.STOPPED

    def clear_package_data(self) -> bool:
        """
        清除游戏数据

        Returns:
            bool: 清除成功返回True
        """
        logger.info(f"清除游戏数据: {self.package_name}")

        try:
            # 等待ADB设备就绪
            device = self._wait_for_adb_device(timeout=30)
            if device is None:
                raise Exception("等待ADB设备连接超时")

            device.shell(f"pm clear {self.package_name}")

            logger.info("游戏数据已清除")
            return True

        except Exception as e:
            logger.error(f"清除游戏数据失败: {e}")
            return False

    def get_device_serial(self) -> str:
        """
        获取设备序列号

        Returns:
            str: 设备序列号
        """
        return self.device_serial
