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
                    return True
                time.sleep(2)

            raise EmulatorStartException(f"模拟器启动超时 ({timeout}秒)")

        except subprocess.TimeoutExpired:
            raise EmulatorStartException("启动命令执行超时")
        except Exception as e:
            raise EmulatorStartException(f"启动模拟器失败: {e}")

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

        # 方法2: 使用ADB检测设备连接
        try:
            from adbutils import adb
            devices = adb.list()
            for device in devices:
                if self.device_serial in str(device):
                    return True
        except Exception:
            pass

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
            # 使用ADB安装
            from adbutils import adb

            # 连接到模拟器
            try:
                adb.connect(f"127.0.0.1:{self.adb_port}", timeout=10)
            except Exception as e:
                logger.warning(f"ADB连接警告: {e}")

            # 获取设备
            devices = adb.list()
            if not devices:
                raise Exception("未找到连接的设备")

            device = devices[0]

            # 安装APK
            logger.info("正在安装APK...")
            result = device.install_apk(str(apk_path), nms=True, flags=["-r"])
            logger.info(f"安装结果: {result}")

            logger.info("APK安装成功")
            return True

        except Exception as e:
            logger.error(f"APK安装失败: {e}")
            return False

    def uninstall_package(self) -> bool:
        """
        卸载游戏包

        Returns:
            bool: 卸载成功返回True
        """
        logger.info(f"开始卸载包: {self.package_name}")

        try:
            from adbutils import adb

            # 连接到模拟器
            adb.connect(f"127.0.0.1:{self.adb_port}", timeout=10)
            devices = adb.list()
            if not devices:
                raise Exception("未找到连接的设备")

            device = devices[0]
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
            from adbutils import adb

            # 连接到模拟器
            adb.connect(f"127.0.0.1:{self.adb_port}", timeout=10)
            devices = adb.list()
            if not devices:
                raise Exception("未找到连接的设备")

            device = devices[0]

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
            from adbutils import adb

            adb.connect(f"127.0.0.1:{self.adb_port}", timeout=10)
            devices = adb.list()
            if not devices:
                raise Exception("未找到连接的设备")

            device = devices[0]
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
