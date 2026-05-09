"""
设备连接状态检测器

用于检测PC版、模拟器和Unity工程的连接状态，实现智能设备选择
"""

import socket
import subprocess
import win32gui


class DeviceDetector:
    """
    设备连接状态检测器

    用于检测PC版游戏、模拟器ADB和Unity工程的连接状态，
    实现智能默认设备选择逻辑
    """

    # PC版游戏窗口标题关键词（更精确的匹配）
    PC_WINDOW_KEYWORDS = ['漫画群星：大集结']

    # 需要排除的窗口标题关键词（避免误判）
    EXCLUDE_KEYWORDS = ['自动化工具', 'Auto', '自动化', '工具']

    # 模拟器窗口标题关键词
    EMULATOR_KEYWORDS = ['MuMu', '雷电', '夜神', 'BlueStacks', 'Nox', 'LDPlayer', '模拟器']

    # Unity 工程连接默认端口
    UNITY_DEFAULT_PORT = 9876

    @classmethod
    def detect_pc_running(cls) -> bool:
        """
        检测PC版游戏是否正在运行

        通过枚举窗口标题，查找包含游戏关键词的窗口
        排除模拟器窗口和工具自身窗口的干扰

        Returns:
            bool: True 如果PC版游戏正在运行
        """
        try:
            def enum_windows_callback(hwnd, results):
                title = win32gui.GetWindowText(hwnd)
                
                # 跳过空标题
                if not title:
                    return True
                
                # 跳过模拟器窗口
                for emulator_keyword in cls.EMULATOR_KEYWORDS:
                    if emulator_keyword in title:
                        return True
                
                # 跳过工具自身窗口
                for exclude_keyword in cls.EXCLUDE_KEYWORDS:
                    if exclude_keyword in title:
                        return True

                # 检查是否是PC游戏窗口
                for keyword in cls.PC_WINDOW_KEYWORDS:
                    if keyword in title:
                        results.append((hwnd, title))
                        break
                return True

            windows = []
            win32gui.EnumWindows(enum_windows_callback, windows)
            return len(windows) > 0
        except Exception:
            return False

    @classmethod
    def detect_adb_connected(cls) -> bool:
        """
        检测模拟器ADB连接是否可用

        使用 adbutils 包检测设备连接状态

        Returns:
            bool: True 如果有ADB设备已连接
        """
        try:
            # 使用 adbutils 包检测（与 OK 框架一致）
            from adbutils import adb

            # 获取设备列表
            devices = adb.list()
            return len(devices) > 0
        except ImportError:
            # adbutils 包未安装，尝试使用系统 adb
            try:
                result = subprocess.run(
                    ['adb', 'devices'],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                lines = result.stdout.strip().split('\n')
                device_count = 0
                for line in lines[1:]:
                    line = line.strip()
                    if line and '\t' in line:
                        parts = line.split('\t')
                        if len(parts) >= 2 and parts[1] == 'device':
                            device_count += 1
                return device_count > 0
            except Exception:
                return False
        except Exception:
            return False

    @classmethod
    def detect_unity_running(cls) -> bool:
        """
        检测 Unity Editor 的 AI Custom TCP 服务器是否可达

        Returns:
            bool: True 如果 Unity TCP 服务器在端口 9876 上可连接
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('127.0.0.1', cls.UNITY_DEFAULT_PORT))
            sock.close()
            return result == 0
        except Exception:
            return False

    @classmethod
    def get_smart_default(cls) -> str | None:
        """
        智能选择默认设备

        根据当前连接状态智能选择设备：
        - 只有Unity可达 → 返回 'unity'
        - 只有PC运行 → 返回 'pc'
        - 只有模拟器连接 → 返回 'adb'
        - 多个或没有 → 返回 None（保持用户选择）

        Returns:
            str | None: 'unity', 'pc', 'adb' 或 None
        """
        unity_running = cls.detect_unity_running()
        pc_running = cls.detect_pc_running()
        adb_connected = cls.detect_adb_connected()

        # 计算活跃设备数量
        active_count = sum([unity_running, pc_running, adb_connected])

        if active_count == 1:
            if unity_running:
                return 'unity'
            elif pc_running:
                return 'pc'
            else:
                return 'adb'
        else:
            # 多个或没有活跃设备，保持用户选择
            return None

    @classmethod
    def get_device_status(cls) -> dict:
        """
        获取设备连接状态详情

        Returns:
            dict: 包含PC、ADB和Unity连接状态的字典
        """
        return {
            'pc_running': cls.detect_pc_running(),
            'adb_connected': cls.detect_adb_connected(),
            'unity_running': cls.detect_unity_running(),
            'smart_default': cls.get_smart_default()
        }
