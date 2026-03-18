from src.task.BaseJumpTask import BaseJumpTask


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
        
        # 任务执行顺序
        tasks_sequence = [
            ('自动登录', self._run_auto_login),
            ('自动新手教程', self._run_auto_tutorial),
        ]
        
        success_count = 0
        
        for task_name, task_func in tasks_sequence:
            try:
                self.logger.info(f"\n▶ 开始执行: {task_name}")
                if task_func():
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
    
    def _run_auto_login(self):
        """执行自动登录任务"""
        try:
            from src.task.AutoLoginTask import AutoLoginTask
            
            # 创建并执行自动登录任务实例，传递相同的上下文
            login_task = AutoLoginTask(self.context)
            login_task.logger = self.logger  # 共享日志器
            login_task.set_caller(self)  # 标记调用关系
            
            return login_task.run()
        except Exception as e:
            self.logger.error(f"自动登录任务执行失败: {e}")
            return False
    
    def _run_auto_tutorial(self):
        """执行自动新手教程任务"""
        try:
            from src.task.AutoTutorialTask import AutoTutorialTask
            
            # 创建并执行自动新手教程任务实例，传递相同的上下文
            tutorial_task = AutoTutorialTask(self.context)
            tutorial_task.logger = self.logger  # 共享日志器
            tutorial_task.set_caller(self)  # 标记调用关系
            
            return tutorial_task.run()
        except Exception as e:
            self.logger.error(f"自动新手教程任务执行失败: {e}")
            return False