from ok import og
from src.task.BaseJumpTask import BaseJumpTask


class AutoMatchTask(BaseJumpTask):
    
    MATCH_START_REL = (0.5, 0.85)
    MATCH_ACCEPT_REL = (0.5, 0.6)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "AutoMatchTask"
        self.description = "自动匹配 - 自动开始游戏匹配"
        self.default_config = {
            '启用': True,
            '游戏模式': '排位赛',
            '自动接受匹配': True,
            '最大等待时间(秒)': 300,
        }
    
    def run(self):
        self.logger.info("=" * 50)
        self.logger.info("自动匹配任务启动")
        self.logger.info("=" * 50)
        
        if not self.default_config.get('启用', True):
            self.logger.info("自动匹配已禁用")
            return False
        
        self.update_resolution()
        res_info = self.get_resolution_info()
        self.logger.info(f"当前分辨率: {res_info['current'][0]}x{res_info['current'][1]}, "
                        f"缩放比例: {res_info['scale_x']:.2f}x{res_info['scale_y']:.2f}")
        
        if not self.check_and_warn_resolution():
            self.logger.warning("分辨率比例不匹配，可能影响识别效果")
        
        self.logger.info(f"游戏模式: {self.default_config.get('游戏模式', '排位赛')}")
        
        if not self._navigate_to_lobby():
            self.logger.error("无法进入大厅")
            return False
        
        if not self._start_match():
            self.logger.error("开始匹配失败")
            return False
        
        if self.default_config.get('自动接受匹配', True):
            if not self._wait_and_accept_match():
                self.logger.error("匹配接受失败")
                return False
        
        self.logger.info("自动匹配完成，游戏即将开始")
        return True
    
    def _navigate_to_lobby(self):
        self.logger.info("导航至大厅...")
        
        import time
        max_attempts = 10
        for _ in range(max_attempts):
            if self.in_lobby():
                self.logger.info("已在大厅")
                return True
            time.sleep(0.5)
        
        return False
    
    def _start_match(self):
        self.logger.info("开始匹配...")
        
        start_button = self.find_feature('match_start')
        if start_button:
            self.click(start_button[0], start_button[1])
            self.logger.info("点击开始匹配按钮 (特征匹配)")
            return True
        
        self.logger.info("未找到匹配按钮，使用相对坐标点击")
        self.click_relative(self.MATCH_START_REL[0], self.MATCH_START_REL[1])
        self.logger.info(f"点击开始匹配按钮 (相对坐标: {self.MATCH_START_REL})")
        return True
    
    def _wait_and_accept_match(self, timeout=None):
        if timeout is None:
            timeout = self.default_config.get('最大等待时间(秒)', 300)
        
        import time
        start_time = time.time()
        
        self.logger.info(f"等待匹配... (最长等待 {timeout} 秒)")
        
        while time.time() - start_time < timeout:
            accept_button = self.find_feature('match_accept')
            if accept_button:
                self.logger.info("检测到匹配成功！")
                self.click(accept_button[0], accept_button[1])
                self.logger.info("已接受匹配 (特征匹配)")
                return True
            
            time.sleep(0.5)
        
        self.logger.warning("匹配超时")
        return False
