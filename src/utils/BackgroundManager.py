import time
import ctypes
from ok import og
from src.utils.PseudoMinimizeHelper import pseudo_minimize_helper


class BackgroundManager:
    
    def __init__(self):
        self._is_background_mode = True
        self._is_muted = False
        self._last_foreground_check = 0
        self._check_interval = 1.0
        self._hwnd = None
        self._auto_pseudo_minimize = True
        self._last_minimize_state = False
    
    def update_config(self):
        config = self._get_basic_config()
        if config:
            self._is_background_mode = config.get('后台模式', True)
            self._auto_pseudo_minimize = config.get('最小化时伪最小化', True)
        return self._is_background_mode
    
    def _get_basic_config(self):
        try:
            if og and og.config:
                # 先尝试获取中文配置名
                config = og.config.get('基本设置')
                if config:
                    return config
                # 回退到其他可能的配置名
                config = og.config.get('基础选项')
                if config:
                    return config
                config = og.config.get('Basic Options')
                if config:
                    return config
        except Exception:
            pass
        return {}
    
    def is_background_mode(self):
        return self._is_background_mode
    
    def is_game_in_background(self):
        if not self._is_background_mode:
            return False
        
        try:
            if time.time() - self._last_foreground_check < self._check_interval:
                return getattr(self, '_cached_is_background', False)
            
            self._last_foreground_check = time.time()
            
            user32 = ctypes.windll.user32
            foreground_hwnd = user32.GetForegroundWindow()
            
            if self._hwnd is None:
                try:
                    if og and og.device_manager and og.device_manager.hwnd_window:
                        self._hwnd = og.device_manager.hwnd_window.hwnd
                        pseudo_minimize_helper.set_hwnd(self._hwnd)
                except Exception:
                    pass
            
            if self._hwnd:
                is_background = foreground_hwnd != self._hwnd
                self._cached_is_background = is_background
                return is_background
                
        except Exception:
            pass
        
        return False
    
    def should_mute_game(self):
        config = self._get_basic_config()
        mute_when_background = config.get('后台时静音游戏', False)
        return mute_when_background and self.is_game_in_background()
    
    def get_background_status(self):
        self.update_config()
        
        return {
            'background_mode_enabled': self._is_background_mode,
            'is_in_background': self.is_game_in_background(),
            'should_mute': self.should_mute_game(),
            'is_muted': self._is_muted,
            'is_pseudo_minimized': pseudo_minimize_helper.is_pseudo_minimized(),
            'auto_pseudo_minimize': self._auto_pseudo_minimize,
        }
    
    def set_muted(self, muted):
        self._is_muted = muted
    
    def on_game_window_change(self, hwnd):
        self._hwnd = hwnd
        pseudo_minimize_helper.set_hwnd(hwnd)
    
    def check_and_auto_pseudo_minimize(self):
        if not self._is_background_mode or not self._auto_pseudo_minimize:
            return False
        
        if self._hwnd is None:
            return False
        
        pseudo_minimize_helper.set_hwnd(self._hwnd)
        
        is_minimized = pseudo_minimize_helper.is_window_minimized()
        
        if is_minimized and not self._last_minimize_state:
            pseudo_minimize_helper.save_original_position()
            success = pseudo_minimize_helper.pseudo_minimize()
            if success:
                print("BackgroundManager: Window pseudo-minimized for background capture")
                self._last_minimize_state = True
                return True
        
        self._last_minimize_state = is_minimized or pseudo_minimize_helper.is_pseudo_minimized()
        return False
    
    def ensure_visible_for_capture(self):
        if self._hwnd is None:
            return False
        
        pseudo_minimize_helper.set_hwnd(self._hwnd)
        return pseudo_minimize_helper.ensure_visible_for_capture()
    
    def pseudo_minimize(self):
        if self._hwnd is None:
            return False
        pseudo_minimize_helper.set_hwnd(self._hwnd)
        pseudo_minimize_helper.save_original_position()
        return pseudo_minimize_helper.pseudo_minimize()
    
    def pseudo_restore(self):
        return pseudo_minimize_helper.pseudo_restore()
    
    def toggle_pseudo_minimize(self):
        return pseudo_minimize_helper.toggle_pseudo_minimize()
    
    def is_pseudo_minimized(self):
        return pseudo_minimize_helper.is_pseudo_minimized()
    
    def reset(self):
        self._hwnd = None
        self._cached_is_background = False
        self._last_foreground_check = 0
        self._last_minimize_state = False
        pseudo_minimize_helper.reset()


background_manager = BackgroundManager()
