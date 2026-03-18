from src.task.BaseJumpTask import BaseJumpTask
from src.task.AutoLoginTask import AutoLoginTask
from src.task.AutoTutorialTask import AutoTutorialTask
from src.task.AutoMatchTask import AutoMatchTask
from src.task.AutoCombatTask import AutoCombatTask
from src.task.DailyTask import DailyTask


class TestAllInOneTask(BaseJumpTask):
    """测试一条龙任务 - 可选择执行多个任务"""
    
    default_config = {
        '启用': True,
        '执行自动登录': True,
        '执行自动新手教程': True,
        '执行自动匹配': False,
        '执行自动战斗': False,
        '执行日常任务': False,
    }
    
    config_description = {
        '执行自动登录': '开启后将执行自动登录任务',
        '执行自动新手教程': '开启后将执行自动新手教程任务',
        '执行自动匹配': '开启后将执行自动匹配任务',
        '执行自动战斗': '开启后将执行自动战斗任务',
        '执行日常任务': '开启后将执行日常任务',
    }
    
    config_type = {
        '执行自动登录': {'type': 'switch_button'},
        '执行自动新手教程': {'type': 'switch_button'},
        '执行自动匹配': {'type': 'switch_button'},
        '执行自动战斗': {'type': 'switch_button'},
        '执行日常任务': {'type': 'switch_button'},
    }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "TestAllInOneTask"
        self.description = "测试一条龙 - 可选择执行多个任务"
        
    def run(self):
        self.logger.info("=" * 60)
        self.logger.info("开始执行测试一条龙任务")
        self.logger.info("=" * 60)
        
        # 读取开关配置
        run_login = self.config.get('执行自动登录', True)
        run_tutorial = self.config.get('执行自动新手教程', True)
        run_match = self.config.get('执行自动匹配', False)
        run_combat = self.config.get('执行自动战斗', False)
        run_daily = self.config.get('执行日常任务', False)
        
        # 构建任务执行顺序 (任务类, 任务名称, 是否执行)
        tasks_sequence = [
            (AutoLoginTask, '自动登录', run_login),
            (AutoTutorialTask, '自动新手教程', run_tutorial),
            (AutoMatchTask, '自动匹配', run_match),
            (AutoCombatTask, '自动战斗', run_combat),
            (DailyTask, '日常任务', run_daily),
        ]
        
        # 统计实际要执行的任务数
        enabled_tasks = [(cls, name) for cls, name, enabled in tasks_sequence if enabled]
        
        if not enabled_tasks:
            self.logger.warning("没有启用任何子任务，测试一条龙任务结束")
            return True
        
        self.logger.info(f"计划执行的任务: {', '.join(name for _, name in enabled_tasks)}")
        
        success_count = 0
        
        for task_class, task_name, enabled in tasks_sequence:
            if not enabled:
                self.logger.info(f"\n⏭ 跳过: {task_name} (未启用)")
                continue
                
            try:
                self.logger.info(f"\n▶ 开始执行: {task_name}")
                
                # 使用框架提供的 run_task_by_class 方法运行子任务
                result = self.run_task_by_class(task_class)
                
                if result:
                    self.logger.info(f"✅ {task_name} 执行成功")
                    success_count += 1
                else:
                    self.logger.error(f"❌ {task_name} 执行失败")
                    break  # 如果某个任务失败，则停止后续任务
            except Exception as e:
                self.logger.error(f"❌ {task_name} 执行异常: {e}")
                break
                
        # 总结
        self.logger.info("\n" + "=" * 60)
        self.logger.info(f"测试一条龙任务完成: {success_count}/{len(enabled_tasks)} 个任务成功")
        self.logger.info("=" * 60)
        
        return success_count == len(enabled_tasks)
