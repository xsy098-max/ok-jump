import time

from ok import BaseScene

from src.utils.ResolutionAdapter import resolution_adapter


class JumpScene(BaseScene):
    
    SCENE_MAIN_MENU = 'main_menu'
    SCENE_LOGIN_0 = 'login_screen_0'
    SCENE_LOGIN_1 = 'login_screen_1'
    SCENE_LOGIN_3 = 'login_screen_3'
    SCENE_LOBBY = 'lobby'
    SCENE_HERO_SELECT = 'hero_select'
    SCENE_LOADING = 'loading'
    SCENE_IN_GAME = 'in_game'
    SCENE_RESULT = 'result'
    SCENE_UNKNOWN = 'unknown'
    
    def __init__(self):
        super().__init__()
        self.name = "JumpScene"
        self.current_scene = self.SCENE_UNKNOWN
        self.scene_history = []
        self._resolution_checked = False
        self._last_resolution = (0, 0)
        self._in_login = None
    
    def _update_resolution(self):
        if self.frame is not None:
            height, width = self.frame.shape[:2]
            if (width, height) != self._last_resolution:
                resolution_adapter.update_resolution(width, height)
                self._last_resolution = (width, height)
                self._resolution_checked = True
                self.logger.debug(f"场景检测器分辨率更新: {width}x{height}")
    
    def detect_scene(self):
        self._update_resolution()
        
        if self.frame is None:
            return self.SCENE_UNKNOWN
        
        if self._check_login_screen_0():
            self.current_scene = self.SCENE_LOGIN_0
        elif self._check_login_screen_1():
            self.current_scene = self.SCENE_LOGIN_1
        elif self._check_login_screen_3():
            self.current_scene = self.SCENE_LOGIN_3
        elif self._check_main_menu():
            self.current_scene = self.SCENE_MAIN_MENU
        elif self._check_lobby():
            self.current_scene = self.SCENE_LOBBY
        elif self._check_hero_select():
            self.current_scene = self.SCENE_HERO_SELECT
        elif self._check_loading():
            self.current_scene = self.SCENE_LOADING
        elif self._check_in_game():
            self.current_scene = self.SCENE_IN_GAME
        elif self._check_result():
            self.current_scene = self.SCENE_RESULT
        else:
            self.current_scene = self.SCENE_UNKNOWN
        
        if not self.scene_history or self.scene_history[-1] != self.current_scene:
            self.scene_history.append(self.current_scene)
            if len(self.scene_history) > 10:
                self.scene_history.pop(0)
        
        return self.current_scene
    
    def _check_main_menu(self):
        try:
            if self.find_feature('main_menu_start'):
                return True
            if self.find_feature('enter_game_button'):
                return True
        except ValueError:
            pass
        return False
    
    def _check_login_screen_0(self):
        try:
            if self.find_feature('login_screen_0_indicator'):
                self._in_login = True
                return True
            if self.find_feature('enter_game_button'):
                self._in_login = True
                return True
        except ValueError:
            pass
        return False
    
    def _check_login_screen_1(self):
        try:
            if self.find_feature('login_screen_1_indicator'):
                self._in_login = True
                return True
            if self.find_feature('login_button'):
                self._in_login = True
                return True
        except ValueError:
            pass
        return False
    
    def _check_login_screen_3(self):
        try:
            if self.find_feature('login_screen_3_indicator'):
                self._in_login = True
                return True
            if self.find_feature('start_game_button'):
                self._in_login = True
                return True
        except ValueError:
            pass
        return False
    
    def _check_lobby(self):
        try:
            return self.find_feature('lobby_indicator') is not None
        except ValueError:
            return False
    
    def _check_hero_select(self):
        try:
            return self.find_feature('hero_select_confirm') is not None
        except ValueError:
            return False
    
    def _check_loading(self):
        try:
            return self.find_feature('loading_indicator') is not None
        except ValueError:
            return False
    
    def _check_in_game(self):
        try:
            return self.find_feature('in_game_hud') is not None
        except ValueError:
            return False
    
    def _check_result(self):
        try:
            return self.find_feature('result_victory') is not None or \
                   self.find_feature('result_defeat') is not None
        except ValueError:
            return False
    
    def get_current_scene(self):
        return self.current_scene
    
    def get_scene_name(self, scene_key=None):
        if scene_key is None:
            scene_key = self.current_scene
        
        scene_names = {
            self.SCENE_MAIN_MENU: '主菜单',
            self.SCENE_LOGIN_0: '登录界面0(适龄提示)',
            self.SCENE_LOGIN_1: '登录界面1(账户登录)',
            self.SCENE_LOGIN_3: '登录界面3(开始游戏)',
            self.SCENE_LOBBY: '大厅',
            self.SCENE_HERO_SELECT: '英雄选择',
            self.SCENE_LOADING: '加载中',
            self.SCENE_IN_GAME: '游戏中',
            self.SCENE_RESULT: '结算画面',
            self.SCENE_UNKNOWN: '未知场景'
        }
        return scene_names.get(scene_key, '未知场景')
    
    def wait_for_scene(self, target_scene, timeout=30):
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.detect_scene() == target_scene:
                return True
            time.sleep(0.5)
        return False
    
    def is_in_game(self):
        return self.current_scene == self.SCENE_IN_GAME
    
    def is_in_menu(self):
        return self.current_scene in [self.SCENE_MAIN_MENU, self.SCENE_LOBBY]
    
    def is_in_login(self):
        return self.current_scene in [self.SCENE_LOGIN_0, self.SCENE_LOGIN_1, self.SCENE_LOGIN_3]
    
    def in_login(self, check_func):
        if self._in_login is None:
            self._in_login = check_func()
        return self._in_login
    
    def reset(self):
        self._in_login = None
        self.current_scene = self.SCENE_UNKNOWN
        self.scene_history = []
    
    def get_resolution_info(self):
        return {
            'current': resolution_adapter.get_current_resolution(),
            'reference': resolution_adapter.get_reference_resolution(),
            'scale': resolution_adapter.get_scale_factor(),
            'is_valid': resolution_adapter.is_valid_resolution()
        }
    
    def check_resolution_warning(self):
        if not resolution_adapter.is_valid_resolution():
            current = resolution_adapter.get_current_resolution()
            recommended = resolution_adapter.get_recommended_resize()
            self.logger.warning(
                f"当前分辨率 {current[0]}x{current[1]} 不是 16:9 比例，"
                f"可能导致场景识别问题。建议调整为 {recommended[0]}x{recommended[1]}"
            )
            return False
        return True
