from ok import og
from src.task.BaseJumpTask import BaseJumpTask


class AutoTutorialTask(BaseJumpTask):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "AutoTutorialTask"
        self.description = "自动新手引导 - 自动完成游戏新手教程"
        self.default_config = {
            '启用': True,
            '自动跳过对话': True,
            '自动点击引导': True,
            '自动完成教学战斗': True,
            '对话等待时间(秒)': 1.0,
            '点击间隔(秒)': 0.5,
        }
    
    def run(self):
        self.logger.info("=" * 50)
        self.logger.info("自动新手引导任务启动")
        self.logger.info("=" * 50)
        
        if not self.default_config.get('启用', True):
            self.logger.info("自动新手引导已禁用")
            return False
        
        self.logger.info("开始检测新手引导...")
        
        steps_completed = 0
        max_steps = 100
        
        for step in range(max_steps):
            if self._is_tutorial_complete():
                self.logger.info("新手引导已完成！")
                break
            
            if self.default_config.get('自动跳过对话', True):
                if self._skip_dialog():
                    steps_completed += 1
                    continue
            
            if self.default_config.get('自动点击引导', True):
                if self._click_tutorial_guide():
                    steps_completed += 1
                    continue
            
            if self.default_config.get('自动完成教学战斗', True):
                if self._handle_tutorial_combat():
                    steps_completed += 1
                    continue
            
            import time
            time.sleep(0.5)
        
        self.logger.info(f"新手引导完成，共完成 {steps_completed} 个步骤")
        return True
    
    def _is_tutorial_complete(self):
        complete_indicator = self.find_feature('tutorial_complete')
        if complete_indicator:
            self.logger.info("检测到新手引导完成标志")
            return True
        
        if self.in_lobby():
            no_tutorial = self.find_feature('no_tutorial_indicator')
            if no_tutorial:
                return True
        
        return False
    
    def _skip_dialog(self):
        dialog_skip = self.find_feature('dialog_skip')
        if dialog_skip:
            self.click(dialog_skip[0], dialog_skip[1])
            self.logger.info("跳过对话")
            
            import time
            wait_time = self.default_config.get('对话等待时间(秒)', 1.0)
            time.sleep(wait_time)
            return True
        
        dialog_next = self.find_feature('dialog_next')
        if dialog_next:
            self.click(dialog_next[0], dialog_next[1])
            self.logger.info("点击下一步对话")
            
            import time
            wait_time = self.default_config.get('对话等待时间(秒)', 1.0)
            time.sleep(wait_time)
            return True
        
        return False
    
    def _click_tutorial_guide(self):
        guide_arrow = self.find_feature('tutorial_arrow')
        if guide_arrow:
            self.click(guide_arrow[0], guide_arrow[1])
            self.logger.info("点击引导箭头")
            
            import time
            interval = self.default_config.get('点击间隔(秒)', 0.5)
            time.sleep(interval)
            return True
        
        guide_highlight = self.find_feature('tutorial_highlight')
        if guide_highlight:
            self.click(guide_highlight[0], guide_highlight[1])
            self.logger.info("点击高亮引导区域")
            
            import time
            interval = self.default_config.get('点击间隔(秒)', 0.5)
            time.sleep(interval)
            return True
        
        guide_button = self.find_feature('tutorial_button')
        if guide_button:
            self.click(guide_button[0], guide_button[1])
            self.logger.info("点击引导按钮")
            
            import time
            interval = self.default_config.get('点击间隔(秒)', 0.5)
            time.sleep(interval)
            return True
        
        return False
    
    def _handle_tutorial_combat(self):
        tutorial_combat = self.find_feature('tutorial_combat_indicator')
        if tutorial_combat:
            self.logger.info("检测到教学战斗")
            
            attack_key = og.config.get('游戏热键配置', {}).get('普通攻击', 'J')
            skill1_key = og.config.get('游戏热键配置', {}).get('技能1', 'U')
            skill2_key = og.config.get('游戏热键配置', {}).get('技能2', 'I')
            ultimate_key = og.config.get('游戏热键配置', {}).get('大招', 'O')
            
            import time
            for _ in range(5):
                self.send_key(attack_key)
                time.sleep(0.3)
                self.send_key(skill1_key)
                time.sleep(0.3)
                self.send_key(skill2_key)
                time.sleep(0.3)
                self.send_key(ultimate_key)
                time.sleep(0.5)
            
            self.logger.info("教学战斗攻击完成")
            return True
        
        return False
