"""
后台输入助手

为 Unity 游戏提供可靠的后台输入支持

实现原理：
1. 伪最小化模式：窗口移到屏幕外但仍保持为"活动窗口"，可以使用 SendInput 发送按键
2. 窗口激活模式：短暂激活游戏窗口，发送 SendInput，然后恢复原窗口焦点

Unity 游戏通常使用 DirectInput 或 Raw Input 来获取输入，
PostMessage 发送的按键不会被检测到，必须使用 SendInput。

参考：MaaEnd 项目对 Unity 游戏的后台支持方案
"""

import time
import ctypes
from ctypes import wintypes

import win32gui
import win32con
import win32api

from src.utils.PseudoMinimizeHelper import pseudo_minimize_helper

# Windows API 常量
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

# 鼠标输入常量
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

# 虚拟键码映射
VK_CODE = {
    'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45, 'f': 0x46,
    'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A, 'k': 0x4B, 'l': 0x4C,
    'm': 0x4D, 'n': 0x4E, 'o': 0x4F, 'p': 0x50, 'q': 0x51, 'r': 0x52,
    's': 0x53, 't': 0x54, 'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58,
    'y': 0x59, 'z': 0x5A,
    '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
    '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
    'space': 0x20, 'enter': 0x0D, 'tab': 0x09, 'escape': 0x1B,
    'backspace': 0x08, 'shift': 0x10, 'ctrl': 0x11, 'alt': 0x12,
    'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73, 'f5': 0x74,
    'f6': 0x75, 'f7': 0x76, 'f8': 0x77, 'f9': 0x78, 'f10': 0x79,
    'f11': 0x7A, 'f12': 0x7B,
    'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
}


# SendInput 结构体定义
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [
            ("ki", KEYBDINPUT),
            ("mi", MOUSEINPUT),
        ]
    _anonymous_ = ("_input",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_input", _INPUT),
    ]


user32 = ctypes.windll.user32


class BackgroundInputHelper:
    """
    后台输入助手
    
    为 Unity 游戏提供可靠的后台输入支持
    """
    
    # 输入模式
    MODE_FOREGROUND = 'foreground'  # 前台模式（需要窗口激活）
    MODE_PSEUDO = 'pseudo'          # 伪最小化模式（窗口移到屏幕外）
    MODE_AUTO = 'auto'              # 自动选择
    
    def __init__(self):
        self._hwnd = None
        self._mode = self.MODE_AUTO
        self._activation_delay = 0.05  # 窗口激活后的等待时间
        self._restore_focus = True     # 是否恢复原窗口焦点
        self._logger = None
    
    def set_hwnd(self, hwnd):
        """设置游戏窗口句柄"""
        self._hwnd = hwnd
    
    def set_logger(self, logger):
        """设置日志器"""
        self._logger = logger
    
    def set_mode(self, mode):
        """设置输入模式"""
        if mode in [self.MODE_FOREGROUND, self.MODE_PSEUDO, self.MODE_AUTO]:
            self._mode = mode
    
    def _log(self, level, msg):
        """记录日志"""
        if self._logger:
            getattr(self._logger, level)(msg)
        else:
            print(f"[BackgroundInput] {msg}")
    
    def _get_vk_code(self, key):
        """获取虚拟键码"""
        key_lower = key.lower()
        return VK_CODE.get(key_lower)
    
    def _send_input(self, inputs):
        """发送输入事件"""
        n_inputs = len(inputs)
        input_array = (INPUT * n_inputs)(*inputs)
        return user32.SendInput(n_inputs, input_array, ctypes.sizeof(INPUT))
    
    def _create_key_down_input(self, vk_code):
        """创建按键按下输入"""
        scan_code = user32.MapVirtualKeyW(vk_code, 0)
        ki = KEYBDINPUT(
            wVk=vk_code,
            wScan=scan_code,
            dwFlags=0,  # 不使用 KEYEVENTF_SCANCODE，同时发送 vk 和 scan
            time=0,
            dwExtraInfo=ctypes.pointer(ctypes.c_ulong(0))
        )
        return INPUT(type=INPUT_KEYBOARD, ki=ki)
    
    def _create_key_up_input(self, vk_code):
        """创建按键释放输入"""
        scan_code = user32.MapVirtualKeyW(vk_code, 0)
        ki = KEYBDINPUT(
            wVk=vk_code,
            wScan=scan_code,
            dwFlags=KEYEVENTF_KEYUP,  # 只使用 KEYUP 标志
            time=0,
            dwExtraInfo=ctypes.pointer(ctypes.c_ulong(0))
        )
        return INPUT(type=INPUT_KEYBOARD, ki=ki)
    
    def _is_pseudo_minimized(self):
        """检查是否处于伪最小化状态"""
        return pseudo_minimize_helper.is_pseudo_minimized()
    
    def _is_background_mode(self):
        """
        检查是否处于后台模式
        
        后台模式包括：
        - 伪最小化状态
        - 游戏窗口在后台（被遮挡）且后台模式已启用
        """
        # 伪最小化状态
        if self._is_pseudo_minimized():
            return True
        
        # 检查后台管理器：后台模式启用且窗口在后台
        try:
            from src.utils.BackgroundManager import background_manager
            if background_manager.is_game_in_background():
                return True
        except Exception:
            pass
        
        return False
    
    def _should_use_sendinput(self):
        """
        判断是否应该使用 SendInput
        
        在后台模式下，使用 SendInput 而不是激活窗口
        这样可以避免窗口被切到前台
        """
        return self._is_background_mode()
    
    def _activate_window_briefly(self):
        """
        短暂激活游戏窗口
        
        使用 AttachThreadInput 技巧来激活窗口
        """
        if self._hwnd is None:
            return False
        
        try:
            current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            target_thread = user32.GetWindowThreadProcessId(self._hwnd, None)
            
            if current_thread != target_thread:
                user32.AttachThreadInput(current_thread, target_thread, True)
            
            # 激活窗口
            user32.SetForegroundWindow(self._hwnd)
            user32.SetFocus(self._hwnd)
            
            if current_thread != target_thread:
                user32.AttachThreadInput(current_thread, target_thread, False)
            
            # 短暂等待确保窗口激活
            time.sleep(0.02)
            return True
            
        except Exception as e:
            self._log('error', f"激活窗口失败: {e}")
            return False
    
    def _restore_focus(self, previous_hwnd):
        """恢复之前的窗口焦点"""
        if previous_hwnd is None:
            return
        
        try:
            current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            target_thread = user32.GetWindowThreadProcessId(previous_hwnd, None)
            
            if current_thread != target_thread:
                user32.AttachThreadInput(current_thread, target_thread, True)
            
            user32.SetForegroundWindow(previous_hwnd)
            
            if current_thread != target_thread:
                user32.AttachThreadInput(current_thread, target_thread, False)
        except Exception:
            pass
    
    def _activate_window(self):
        """
        激活游戏窗口
        
        Returns:
            tuple: (成功标志, 之前的前台窗口句柄)
        """
        if self._hwnd is None:
            return False, None
        
        try:
            # 保存当前前台窗口
            previous_hwnd = user32.GetForegroundWindow()
            
            # 如果游戏已经是前台窗口，无需操作
            if previous_hwnd == self._hwnd:
                return True, None
            
            # 尝试激活窗口
            # 使用 AttachThreadInput 技巧来绕过限制
            current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            target_thread = user32.GetWindowThreadProcessId(self._hwnd, None)
            
            if current_thread != target_thread:
                user32.AttachThreadInput(current_thread, target_thread, True)
            
            # 激活窗口
            user32.SetForegroundWindow(self._hwnd)
            user32.SetFocus(self._hwnd)
            
            if current_thread != target_thread:
                user32.AttachThreadInput(current_thread, target_thread, False)
            
            # 等待窗口激活
            time.sleep(self._activation_delay)
            
            return True, previous_hwnd
            
        except Exception as e:
            self._log('error', f"激活窗口失败: {e}")
            return False, None
    
    def _restore_window_focus(self, previous_hwnd):
        """恢复之前的窗口焦点"""
        if previous_hwnd is None or not self._restore_focus:
            return
        
        try:
            user32.SetForegroundWindow(previous_hwnd)
        except Exception:
            pass
    
    def send_key(self, key, duration=0.02):
        """
        发送按键（按下并释放）
        
        Args:
            key: 按键名称（如 'J', 'K', 'space'）
            duration: 按键持续时间（秒）
            
        Returns:
            bool: 发送成功返回 True
        """
        import pydirectinput
        
        vk_code = self._get_vk_code(key)
        if vk_code is None:
            self._log('warning', f"未知按键: {key}")
            return False
        
        # 判断是否应该使用 SendInput（后台模式或伪最小化）
        use_sendinput = self._should_use_sendinput()
        
        try:
            if use_sendinput:
                # 后台模式：使用 SendInput，不激活窗口
                key_down = self._create_key_down_input(vk_code)
                key_up = self._create_key_up_input(vk_code)
                
                self._send_input([key_down])
                if duration > 0:
                    time.sleep(duration)
                self._send_input([key_up])
                
                self._log('debug', f"SendInput 发送按键: {key} (后台模式)")
            else:
                # 前台模式：直接使用 pydirectinput
                pydirectinput.keyDown(key.lower())
                if duration > 0:
                    time.sleep(duration)
                pydirectinput.keyUp(key.lower())
                
                self._log('debug', f"pydirectinput 发送按键: {key} (前台模式)")
            
            return True
            
        except Exception as e:
            self._log('error', f"发送按键失败: {e}")
            return False
    
    def send_key_down(self, key):
        """
        发送按键按下（不释放）
        
        Args:
            key: 按键名称
            
        Returns:
            bool: 发送成功返回 True
        """
        vk_code = self._get_vk_code(key)
        if vk_code is None:
            return False
        
        try:
            key_down = self._create_key_down_input(vk_code)
            self._send_input([key_down])
            return True
        except Exception as e:
            self._log('error', f"发送按键按下失败: {e}")
            return False
    
    def send_key_up(self, key):
        """
        发送按键释放
        
        Args:
            key: 按键名称
            
        Returns:
            bool: 发送成功返回 True
        """
        vk_code = self._get_vk_code(key)
        if vk_code is None:
            return False
        
        try:
            key_up = self._create_key_up_input(vk_code)
            self._send_input([key_up])
            return True
        except Exception as e:
            self._log('error', f"发送按键释放失败: {e}")
            return False
    
    def send_keys_hold(self, keys, duration=0.3):
        """
        同时按住多个键一段时间
        
        用于移动控制（如同时按 W+D 斜向移动）
        
        Args:
            keys: 按键列表
            duration: 按住持续时间（秒）
            
        Returns:
            bool: 发送成功返回 True
        """
        import pydirectinput
        
        if not keys:
            return False
        
        # 获取所有虚拟键码
        vk_codes = []
        for key in keys:
            vk = self._get_vk_code(key)
            if vk is None:
                self._log('warning', f"未知按键: {key}")
                continue
            vk_codes.append(vk)
        
        if not vk_codes:
            return False
        
        # 判断是否应该使用 SendInput（后台模式或伪最小化）
        use_sendinput = self._should_use_sendinput()
        
        try:
            if use_sendinput:
                # 后台模式：使用 SendInput，不激活窗口
                for vk in vk_codes:
                    key_down = self._create_key_down_input(vk)
                    self._send_input([key_down])
                
                time.sleep(duration)
                
                for vk in vk_codes:
                    key_up = self._create_key_up_input(vk)
                    self._send_input([key_up])
                
                key_str = '+'.join(keys)
                self._log('debug', f"SendInput 按住按键: {key_str}, {duration}秒 (后台模式)")
            else:
                # 前台模式：直接使用 pydirectinput
                for key in keys:
                    pydirectinput.keyDown(key.lower())
                
                time.sleep(duration)
                
                for key in keys:
                    pydirectinput.keyUp(key.lower())
                
                key_str = '+'.join(keys)
                self._log('debug', f"pydirectinput 按住按键: {key_str}, {duration}秒 (前台模式)")
            
            return True
            
        except Exception as e:
            self._log('error', f"按住按键失败: {e}")
            # 尝试释放所有可能按下的键
            try:
                for key in keys:
                    pydirectinput.keyUp(key.lower())
            except Exception:
                pass
            return False


    # ==================== 鼠标操作方法 ====================
    
    def _window_to_screen(self, x, y):
        """
        将窗口相对坐标转换为屏幕绝对坐标
        
        Args:
            x, y: 窗口内的相对坐标
            
        Returns:
            tuple: (屏幕x, 屏幕y)
        """
        if self._hwnd is None:
            return x, y
        try:
            rect = win32gui.GetWindowRect(self._hwnd)
            return rect[0] + x, rect[1] + y
        except Exception:
            return x, y
    
    def _to_normalized_coords(self, screen_x, screen_y):
        """
        转换为 SendInput 需要的归一化坐标 (0-65535)
        
        Args:
            screen_x, screen_y: 屏幕绝对坐标
            
        Returns:
            tuple: (归一化x, 归一化y)
        """
        screen_width = user32.GetSystemMetrics(0)  # SM_CXSCREEN
        screen_height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
        norm_x = int(screen_x * 65536 / screen_width)
        norm_y = int(screen_y * 65536 / screen_height)
        return norm_x, norm_y
    
    def _create_mouse_input(self, dx, dy, flags, mouse_data=0):
        """
        创建鼠标输入结构
        
        Args:
            dx, dy: 归一化坐标或相对移动量
            flags: 鼠标事件标志
            mouse_data: 鼠标数据（滚轮等）
            
        Returns:
            INPUT: 鼠标输入结构
        """
        mi = MOUSEINPUT(
            dx=dx,
            dy=dy,
            mouseData=mouse_data,
            dwFlags=flags,
            time=0,
            dwExtraInfo=ctypes.pointer(ctypes.c_ulong(0))
        )
        return INPUT(type=INPUT_MOUSE, mi=mi)
    
    def move_to(self, x, y):
        """
        移动鼠标到指定位置（窗口内坐标）
        
        Args:
            x, y: 窗口内的坐标
            
        Returns:
            bool: 成功返回 True
        """
        try:
            # 转换为屏幕坐标
            screen_x, screen_y = self._window_to_screen(x, y)
            # 转换为归一化坐标
            norm_x, norm_y = self._to_normalized_coords(screen_x, screen_y)
            
            # 创建鼠标移动输入
            flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
            mouse_input = self._create_mouse_input(norm_x, norm_y, flags)
            self._send_input([mouse_input])
            
            return True
        except Exception as e:
            self._log('error', f"移动鼠标失败: {e}")
            return False
    
    def mouse_down(self, x, y, button='left'):
        """
        在指定位置按下鼠标按钮
        
        Args:
            x, y: 窗口内的坐标
            button: 鼠标按钮 ('left', 'right', 'middle')
            
        Returns:
            bool: 成功返回 True
        """
        try:
            # 先移动到目标位置
            self.move_to(x, y)
            time.sleep(0.01)
            
            # 确定按钮标志
            if button == 'left':
                flags = MOUSEEVENTF_LEFTDOWN
            elif button == 'right':
                flags = MOUSEEVENTF_RIGHTDOWN
            elif button == 'middle':
                flags = MOUSEEVENTF_MIDDLEDOWN
            else:
                flags = MOUSEEVENTF_LEFTDOWN
            
            # 发送鼠标按下
            mouse_input = self._create_mouse_input(0, 0, flags)
            self._send_input([mouse_input])
            
            return True
        except Exception as e:
            self._log('error', f"鼠标按下失败: {e}")
            return False
    
    def mouse_up(self, x, y, button='left'):
        """
        在指定位置释放鼠标按钮
        
        Args:
            x, y: 窗口内的坐标
            button: 鼠标按钮 ('left', 'right', 'middle')
            
        Returns:
            bool: 成功返回 True
        """
        try:
            # 先移动到目标位置
            self.move_to(x, y)
            time.sleep(0.01)
            
            # 确定按钮标志
            if button == 'left':
                flags = MOUSEEVENTF_LEFTUP
            elif button == 'right':
                flags = MOUSEEVENTF_RIGHTUP
            elif button == 'middle':
                flags = MOUSEEVENTF_MIDDLEUP
            else:
                flags = MOUSEEVENTF_LEFTUP
            
            # 发送鼠标释放
            mouse_input = self._create_mouse_input(0, 0, flags)
            self._send_input([mouse_input])
            
            return True
        except Exception as e:
            self._log('error', f"鼠标释放失败: {e}")
            return False
    
    def click(self, x, y, button='left', duration=0.02):
        """
        在指定位置点击鼠标（支持后台操作）
        
        Args:
            x, y: 窗口内的坐标
            button: 鼠标按钮 ('left', 'right', 'middle')
            duration: 按下持续时间（秒）
            
        Returns:
            bool: 成功返回 True
        """
        import pydirectinput
        
        # 判断是否应该使用 SendInput（后台模式或伪最小化）
        use_sendinput = self._should_use_sendinput()
        
        try:
            if use_sendinput:
                # 后台模式：使用 SendInput，不激活窗口
                # 转换为屏幕坐标
                screen_x, screen_y = self._window_to_screen(x, y)
                # 转换为归一化坐标
                norm_x, norm_y = self._to_normalized_coords(screen_x, screen_y)
                
                # 确定按钮标志
                if button == 'left':
                    down_flags = MOUSEEVENTF_LEFTDOWN
                    up_flags = MOUSEEVENTF_LEFTUP
                elif button == 'right':
                    down_flags = MOUSEEVENTF_RIGHTDOWN
                    up_flags = MOUSEEVENTF_RIGHTUP
                elif button == 'middle':
                    down_flags = MOUSEEVENTF_MIDDLEDOWN
                    up_flags = MOUSEEVENTF_MIDDLEUP
                else:
                    down_flags = MOUSEEVENTF_LEFTDOWN
                    up_flags = MOUSEEVENTF_LEFTUP
                
                # 移动 + 按下
                move_flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
                move_input = self._create_mouse_input(norm_x, norm_y, move_flags)
                down_input = self._create_mouse_input(0, 0, down_flags)
                up_input = self._create_mouse_input(0, 0, up_flags)
                
                # 发送：移动 -> 按下 -> 等待 -> 释放
                self._send_input([move_input])
                time.sleep(0.01)
                self._send_input([down_input])
                if duration > 0:
                    time.sleep(duration)
                self._send_input([up_input])
                
                self._log('debug', f"SendInput 点击: ({x}, {y}) {button} (后台模式)")
            else:
                # 前台模式：直接使用 pydirectinput
                # 转换为屏幕坐标
                screen_x, screen_y = self._window_to_screen(x, y)
                
                # 使用 pydirectinput 点击
                pydirectinput.moveTo(int(screen_x), int(screen_y))
                time.sleep(0.01)
                
                if button == 'left':
                    pydirectinput.click()
                elif button == 'right':
                    pydirectinput.rightClick()
                elif button == 'middle':
                    pydirectinput.middleClick()
                else:
                    pydirectinput.click()
                
                self._log('debug', f"pydirectinput 点击: ({x}, {y}) {button} (前台模式)")
            
            return True
            
        except Exception as e:
            self._log('error', f"鼠标点击失败: {e}")
            return False
    
    def drag(self, start_x, start_y, end_x, end_y, duration=0.3, steps=10, button='left'):
        """
        拖拽操作（支持后台操作）
        
        用于滑动验证、拖动物品等场景
        
        Args:
            start_x, start_y: 起始位置（窗口内坐标）
            end_x, end_y: 结束位置（窗口内坐标）
            duration: 拖拽持续时间（秒）
            steps: 移动步数
            button: 鼠标按钮 ('left', 'right', 'middle')
            
        Returns:
            bool: 成功返回 True
        """
        import pydirectinput
        
        # 判断是否应该使用 SendInput（后台模式或伪最小化）
        use_sendinput = self._should_use_sendinput()
        
        try:
            if use_sendinput:
                # 后台模式：使用 SendInput，不激活窗口
                # 确定按钮标志
                if button == 'left':
                    down_flags = MOUSEEVENTF_LEFTDOWN
                    up_flags = MOUSEEVENTF_LEFTUP
                elif button == 'right':
                    down_flags = MOUSEEVENTF_RIGHTDOWN
                    up_flags = MOUSEEVENTF_RIGHTUP
                else:
                    down_flags = MOUSEEVENTF_LEFTDOWN
                    up_flags = MOUSEEVENTF_LEFTUP
                
                # 移动到起始位置
                self.move_to(start_x, start_y)
                time.sleep(0.05)
                
                # 按下鼠标
                down_input = self._create_mouse_input(0, 0, down_flags)
                self._send_input([down_input])
                time.sleep(0.02)
                
                # 分步移动
                step_delay = duration / steps
                for i in range(1, steps + 1):
                    ratio = i / steps
                    curr_x = int(start_x + (end_x - start_x) * ratio)
                    curr_y = int(start_y + (end_y - start_y) * ratio)
                    self.move_to(curr_x, curr_y)
                    time.sleep(step_delay)
                
                # 释放鼠标
                up_input = self._create_mouse_input(0, 0, up_flags)
                self._send_input([up_input])
                
                self._log('debug', f"SendInput 拖拽: ({start_x},{start_y}) -> ({end_x},{end_y}) (后台模式)")
            else:
                # 前台模式：直接使用 pydirectinput
                # 转换为屏幕坐标
                start_screen_x, start_screen_y = self._window_to_screen(start_x, start_y)
                end_screen_x, end_screen_y = self._window_to_screen(end_x, end_y)
                
                # 移动到起始位置
                pydirectinput.moveTo(int(start_screen_x), int(start_screen_y))
                time.sleep(0.05)
                
                # 按下鼠标
                if button == 'left':
                    pydirectinput.mouseDown()
                elif button == 'right':
                    pydirectinput.mouseDown(button='right')
                time.sleep(0.02)
                
                # 分步移动
                step_delay = duration / steps
                for i in range(1, steps + 1):
                    ratio = i / steps
                    curr_x = int(start_screen_x + (end_screen_x - start_screen_x) * ratio)
                    curr_y = int(start_screen_y + (end_screen_y - start_screen_y) * ratio)
                    pydirectinput.moveTo(curr_x, curr_y)
                    time.sleep(step_delay)
                
                # 释放鼠标
                if button == 'left':
                    pydirectinput.mouseUp()
                elif button == 'right':
                    pydirectinput.mouseUp(button='right')
                
                self._log('debug', f"pydirectinput 拖拽: ({start_x},{start_y}) -> ({end_x},{end_y}) (前台模式)")
            
            return True
            
        except Exception as e:
            self._log('error', f"拖拽操作失败: {e}")
            # 尝试释放鼠标
            try:
                if use_sendinput:
                    up_input = self._create_mouse_input(0, 0, MOUSEEVENTF_LEFTUP)
                    self._send_input([up_input])
                else:
                    pydirectinput.mouseUp()
            except Exception:
                pass
            return False
    
    def double_click(self, x, y, button='left', interval=0.1):
        """
        双击操作
        
        Args:
            x, y: 窗口内的坐标
            button: 鼠标按钮
            interval: 两次点击之间的间隔（秒）
            
        Returns:
            bool: 成功返回 True
        """
        try:
            self.click(x, y, button, duration=0.02)
            time.sleep(interval)
            self.click(x, y, button, duration=0.02)
            return True
        except Exception as e:
            self._log('error', f"双击操作失败: {e}")
            return False


# 全局实例
background_input = BackgroundInputHelper()
