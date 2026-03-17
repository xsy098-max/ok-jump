import ctypes
import time
from typing import Optional, Tuple
import win32gui
import win32con
import win32api

user32 = ctypes.windll.user32

PSEUDO_MINIMIZE_POS = (-32000, -32000)


class PseudoMinimizeHelper:
    
    def __init__(self):
        self._hwnd: Optional[int] = None
        self._original_rect: Optional[Tuple[int, int, int, int]] = None
        self._is_pseudo_minimized: bool = False
        self._last_window_state: dict = {}
    
    def set_hwnd(self, hwnd: int):
        if self._hwnd != hwnd:
            self._hwnd = hwnd
            self._original_rect = None
            self._is_pseudo_minimized = False
    
    def get_window_rect(self, hwnd: int = None) -> Optional[Tuple[int, int, int, int]]:
        if hwnd is None:
            hwnd = self._hwnd
        if hwnd is None:
            return None
        try:
            return win32gui.GetWindowRect(hwnd)
        except Exception:
            return None
    
    def is_window_minimized(self, hwnd: int = None) -> bool:
        if hwnd is None:
            hwnd = self._hwnd
        if hwnd is None:
            return False
        try:
            placement = win32gui.GetWindowPlacement(hwnd)
            return placement[1] == win32con.SW_SHOWMINIMIZED
        except Exception:
            return False
    
    def is_window_visible(self, hwnd: int = None) -> bool:
        if hwnd is None:
            hwnd = self._hwnd
        if hwnd is None:
            return False
        try:
            return win32gui.IsWindowVisible(hwnd)
        except Exception:
            return False
    
    def is_window_in_foreground(self, hwnd: int = None) -> bool:
        """
        检查窗口是否在前台
        
        Returns:
            bool: True 如果窗口是当前前台窗口
        """
        if hwnd is None:
            hwnd = self._hwnd
        if hwnd is None:
            return False
        try:
            foreground_hwnd = user32.GetForegroundWindow()
            return foreground_hwnd == hwnd
        except Exception:
            return False
    
    def needs_pseudo_minimize(self, hwnd: int = None) -> bool:
        """
        检查是否需要伪最小化
        
        当窗口被最小化或不在前台时，需要伪最小化以支持后台截图
        
        Returns:
            bool: True 如果需要伪最小化
        """
        if hwnd is None:
            hwnd = self._hwnd
        if hwnd is None:
            return False
        
        # 已经伪最小化，不需要再次操作
        if self._is_pseudo_minimized:
            return False
        
        # 检查窗口是否被最小化
        if self.is_window_minimized(hwnd):
            return True
        
        # 检查窗口是否不在前台（被其他窗口遮挡）
        if not self.is_window_in_foreground(hwnd):
            return True
        
        return False
    
    def is_pseudo_minimized(self) -> bool:
        return self._is_pseudo_minimized
    
    def is_at_pseudo_position(self, hwnd: int = None) -> bool:
        rect = self.get_window_rect(hwnd)
        if rect is None:
            return False
        x, y = rect[0], rect[1]
        return x <= -30000 and y <= -30000
    
    def save_original_position(self):
        if self._hwnd is None:
            return False
        if self._original_rect is None and not self._is_pseudo_minimized:
            rect = self.get_window_rect()
            if rect and not self.is_at_pseudo_position():
                self._original_rect = rect
                return True
        return False
    
    def pseudo_minimize(self) -> bool:
        if self._hwnd is None:
            return False
        
        if self._is_pseudo_minimized:
            return True
        
        try:
            rect = self.get_window_rect()
            if rect is None:
                return False
            
            if self.is_window_minimized():
                self._restore_from_minimized()
                time.sleep(0.1)
                rect = self.get_window_rect()
                if rect is None:
                    return False
            
            if self._original_rect is None and not self.is_at_pseudo_position():
                self._original_rect = rect
            
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            
            win32gui.SetWindowPos(
                self._hwnd,
                win32con.HWND_TOP,
                PSEUDO_MINIMIZE_POS[0],
                PSEUDO_MINIMIZE_POS[1],
                width,
                height,
                win32con.SWP_NOACTIVATE | win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED
            )
            
            self._is_pseudo_minimized = True
            return True
            
        except Exception as e:
            print(f"PseudoMinimizeHelper: pseudo_minimize failed: {e}")
            return False
    
    def pseudo_restore(self) -> bool:
        if self._hwnd is None:
            return False
        
        if not self._is_pseudo_minimized:
            return True
        
        try:
            if self._original_rect is None:
                return False
            
            x, y, right, bottom = self._original_rect
            width = right - x
            height = bottom - y
            
            win32gui.SetWindowPos(
                self._hwnd,
                win32con.HWND_TOP,
                x, y,
                width, height,
                win32con.SWP_NOACTIVATE | win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED
            )
            
            self._is_pseudo_minimized = False
            return True
            
        except Exception as e:
            print(f"PseudoMinimizeHelper: pseudo_restore failed: {e}")
            return False
    
    def _restore_from_minimized(self) -> bool:
        if self._hwnd is None:
            return False
        
        try:
            win32gui.ShowWindow(self._hwnd, win32con.SW_RESTORE)
            return True
        except Exception:
            return False
    
    def toggle_pseudo_minimize(self) -> bool:
        if self._is_pseudo_minimized:
            return self.pseudo_restore()
        else:
            return self.pseudo_minimize()
    
    def ensure_visible_for_capture(self) -> bool:
        if self._hwnd is None:
            return False
        
        if self.is_window_minimized():
            return self.pseudo_minimize()
        
        return True
    
    def get_state(self) -> dict:
        return {
            'hwnd': self._hwnd,
            'original_rect': self._original_rect,
            'is_pseudo_minimized': self._is_pseudo_minimized,
            'is_window_minimized': self.is_window_minimized() if self._hwnd else False,
            'is_window_visible': self.is_window_visible() if self._hwnd else False,
            'is_at_pseudo_position': self.is_at_pseudo_position() if self._hwnd else False,
        }
    
    def reset(self):
        self._hwnd = None
        self._original_rect = None
        self._is_pseudo_minimized = False
        self._last_window_state = {}


pseudo_minimize_helper = PseudoMinimizeHelper()
