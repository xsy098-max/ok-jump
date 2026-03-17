from ok import og
from src.task.BaseJumpTask import BaseJumpTask


class DailyTask(BaseJumpTask):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "DailyTask"
        self.description = "日常任务 - 自动完成每日任务"
        self.default_config = {
            '启用': True,
            '完成日常任务': True,
            '收集奖励': True,
            '使用体力': True,
            '体力阈值': 50,
        }
    
    def run(self):
        self.logger.info("=" * 50)
        self.logger.info("日常任务启动")
        self.logger.info("=" * 50)
        
        if not self.default_config.get('启用', True):
            self.logger.info("日常任务已禁用")
            return False
        
        results = {
            'daily_quests': False,
            'rewards': False,
            'stamina': False,
        }
        
        if self.default_config.get('完成日常任务', True):
            results['daily_quests'] = self._complete_daily_quests()
        
        if self.default_config.get('收集奖励', True):
            results['rewards'] = self._collect_rewards()
        
        if self.default_config.get('使用体力', True):
            results['stamina'] = self._use_stamina()
        
        self._print_summary(results)
        return True
    
    def _complete_daily_quests(self):
        self.logger.info("开始完成日常任务...")
        
        if not self._navigate_to_quests():
            self.logger.error("无法进入任务界面")
            return False
        
        quest_count = 0
        max_quests = 10
        
        for i in range(max_quests):
            quest_item = self.find_feature(f'daily_quest_{i}')
            if quest_item:
                self.click(quest_item[0], quest_item[1])
                self.logger.info(f"点击日常任务 {i + 1}")
                
                import time
                time.sleep(1)
                
                go_button = self.find_feature('quest_go')
                if go_button:
                    self.click(go_button[0], go_button[1])
                    self.logger.info("执行任务中...")
                    quest_count += 1
                    time.sleep(2)
        
        self.logger.info(f"完成 {quest_count} 个日常任务")
        return quest_count > 0
    
    def _navigate_to_quests(self):
        self.logger.info("导航至任务界面...")
        
        quest_tab = self.find_feature('tab_quests')
        if quest_tab:
            self.click(quest_tab[0], quest_tab[1])
            self.logger.info("点击任务标签")
            
            import time
            time.sleep(1)
            return True
        
        return False
    
    def _collect_rewards(self):
        self.logger.info("收集奖励...")
        
        rewards_collected = 0
        max_attempts = 20
        
        for _ in range(max_attempts):
            claim_button = self.find_feature('claim_reward')
            if claim_button:
                self.click(claim_button[0], claim_button[1])
                self.logger.info("领取奖励")
                rewards_collected += 1
                
                import time
                time.sleep(0.5)
            else:
                break
        
        self.logger.info(f"收集了 {rewards_collected} 个奖励")
        return rewards_collected > 0
    
    def _use_stamina(self):
        self.logger.info("使用体力...")
        
        threshold = self.default_config.get('体力阈值', 50)
        self.logger.info(f"体力阈值: {threshold}")
        
        stamina_button = self.find_feature('use_stamina')
        if stamina_button:
            self.click(stamina_button[0], stamina_button[1])
            self.logger.info("使用体力")
            return True
        
        self.logger.info("未找到体力使用入口")
        return False
    
    def _print_summary(self, results):
        self.logger.info("")
        self.logger.info("=" * 50)
        self.logger.info("日常任务完成摘要:")
        self.logger.info(f"  日常任务: {'✓' if results['daily_quests'] else '×'}")
        self.logger.info(f"  收集奖励: {'✓' if results['rewards'] else '×'}")
        self.logger.info(f"  使用体力: {'✓' if results['stamina'] else '×'}")
        self.logger.info("=" * 50)
