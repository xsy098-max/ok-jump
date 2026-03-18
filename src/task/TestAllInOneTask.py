from src.task.BaseJumpTask import BaseJumpTask
from src.task.AutoLoginTask import AutoLoginTask
from src.task.AutoTutorialTask import AutoTutorialTask


class TestAllInOneTask(BaseJumpTask):
    """测试一条龙任务 - 依次执行所有主要任务"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "TestAllInOneTask"
        self.description = "测试一条龙 - 依次执行自动登录和自动新手教程"
        
    def run(self):
        self.logger.info("=" * 60)
        self.logger.info("开始执行测试一条龙任务")
        self.logger.info("=" * 60)
        
        # 任务执行顺序 (任务类, 任务名称)
        tasks_sequence = [
            (AutoLoginTask, '自动登录'),
            (AutoTutorialTask, '自动新手教程'),
        ]
        
        success_count = 0
        
        for task_class, task_name in tasks_sequence:
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
        self.logger.info(f"测试一条龙任务完成: {success_count}/{len(tasks_sequence)} 个任务成功")
        self.logger.info("=" * 60)
        
        return success_count == len(tasks_sequence)
