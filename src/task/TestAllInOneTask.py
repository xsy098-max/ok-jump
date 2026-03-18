import time

from src.task.BaseJumpTask import BaseJumpTask
from src.task.AutoLoginTask import AutoLoginTask
from src.task.AutoTutorialTask import AutoTutorialTask
from src.task.AutoMatchTask import AutoMatchTask
from src.task.AutoCombatTask import AutoCombatTask
from src.task.DailyTask import DailyTask


class TestAllInOneTask(BaseJumpTask):
    """测试一条龙任务 - 可选择执行多个任务"""
    
    # 任务过渡配置：定义哪些任务之间需要特殊过渡处理
    TRANSITION_CONFIG = {
        # AutoLoginTask → AutoTutorialTask: 需要验证角色选择界面
        (AutoLoginTask, AutoTutorialTask): {
            'wait_time': 2.0,  # 过渡等待时间
            'verify_screen': 'character_select',  # 需要验证的界面
            'verify_timeout': 10.0,  # 验证超时时间
        },
        # 可以继续添加其他任务过渡配置
    }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "TestAllInOneTask"
        self.description = "测试一条龙 - 可选择执行多个任务"
        
        # 默认配置 - 必须在 __init__ 中定义为实例属性
        self.default_config = {
            '启用': True,
            '执行自动登录': True,
            '执行自动新手教程': True,
            '执行自动匹配': False,
            '执行自动战斗': False,
            '执行日常任务': False,
            '任务间等待时间(秒)': 2.0,
        }
        
        # 配置描述
        self.config_description = {
            '执行自动登录': '开启后将执行自动登录任务',
            '执行自动新手教程': '开启后将执行自动新手教程任务',
            '执行自动匹配': '开启后将执行自动匹配任务',
            '执行自动战斗': '开启后将执行自动战斗任务',
            '执行日常任务': '开启后将执行日常任务',
            '任务间等待时间(秒)': '任务之间等待界面稳定的时间',
        }
        
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
        default_wait = self.config.get('任务间等待时间(秒)', 2.0)
        
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
        prev_task_class = None
        
        for task_class, task_name, enabled in tasks_sequence:
            if not enabled:
                self.logger.info(f"\n⏭ 跳过: {task_name} (未启用)")
                continue
            
            # 任务间过渡处理
            if prev_task_class is not None:
                transition_key = (prev_task_class, task_class)
                if transition_key in self.TRANSITION_CONFIG:
                    transition = self.TRANSITION_CONFIG[transition_key]
                    self._handle_transition(prev_task_class, task_class, transition)
                else:
                    # 默认过渡等待
                    self.logger.info(f"\n⏳ 等待 {default_wait} 秒后继续下一个任务...")
                    time.sleep(default_wait)
            
            try:
                self.logger.info(f"\n▶ 开始执行: {task_name}")
                
                # 使用框架提供的 run_task_by_class 方法运行子任务
                result = self.run_task_by_class(task_class)
                
                if result:
                    self.logger.info(f"✅ {task_name} 执行成功")
                    success_count += 1
                    prev_task_class = task_class
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
    
    def _handle_transition(self, from_task, to_task, transition_config):
        """
        处理任务间的过渡
        
        Args:
            from_task: 上一个任务类
            to_task: 下一个任务类
            transition_config: 过渡配置
        """
        wait_time = transition_config.get('wait_time', 2.0)
        verify_screen = transition_config.get('verify_screen', None)
        verify_timeout = transition_config.get('verify_timeout', 10.0)
        
        self.logger.info(f"\n{'='*40}")
        self.logger.info(f"任务过渡: {from_task.__name__} → {to_task.__name__}")
        self.logger.info(f"{'='*40}")
        
        # 等待界面稳定
        self.logger.info(f"⏳ 等待 {wait_time} 秒让界面稳定...")
        time.sleep(wait_time)
        
        # 验证界面状态
        if verify_screen:
            self.logger.info(f"🔍 验证界面状态: {verify_screen}")
            if not self._verify_screen(verify_screen, verify_timeout):
                self.logger.warning(f"⚠️ 界面验证失败，但继续执行下一个任务")
            else:
                self.logger.info(f"✅ 界面验证通过")
    
    def _verify_screen(self, screen_type, timeout):
        """
        验证当前界面状态
        
        Args:
            screen_type: 界面类型
            timeout: 超时时间
            
        Returns:
            bool: 是否验证通过
        """
        import re
        from src.constants.features import Features
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            self.next_frame()
            
            if screen_type == 'character_select':
                # 验证角色选择界面
                # 方法1: 模板匹配
                try:
                    xuanren = self.find_one(Features.XUANREN, threshold=0.6)
                    if xuanren:
                        self.logger.info("模板匹配确认角色选择界面")
                        return True
                except ValueError:
                    pass
                except Exception as e:
                    self.logger.debug(f"模板匹配异常: {e}")
                
                # 方法2: OCR 检测
                try:
                    texts = self.ocr()
                    patterns = [
                        re.compile(r"请选择一位你心仪的角色"),
                        re.compile(r"请选择.*心仪的角色"),
                        re.compile(r"心仪的角色"),
                    ]
                    for pattern in patterns:
                        if self.find_boxes(texts, match=pattern):
                            self.logger.info("OCR确认角色选择界面")
                            return True
                except Exception as e:
                    self.logger.debug(f"OCR检测异常: {e}")
            
            time.sleep(0.5)
        
        return False
