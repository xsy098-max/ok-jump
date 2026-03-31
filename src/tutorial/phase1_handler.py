"""
第一阶段处理器

处理新手教程第一阶段的完整流程：
选角界面检测 → 第一次点击 → 确认对话框 → 第二次点击 → 加载 → 自身检测 → 目标检测 → 移动 → 普攻检测 → 向下移动 → 自动战斗触发 → 第一阶段结束检测
"""

import time
from typing import Optional

from ok import og

from src.tutorial.state_machine import TutorialState, TutorialStateMachine
from src.tutorial.character_selector import CharacterSelector, CharacterConfig
from src.tutorial.tutorial_detector import TutorialDetector
from src.combat.movement_controller import MovementController
from src.combat.distance_calculator import DistanceCalculator
from src.utils import background_manager


class Phase1Handler:
    """
    第一阶段处理器
    
    处理新手教程第一阶段的完整流程
    """
    
    def __init__(self, task):
        """
        初始化处理器
        
        Args:
            task: 关联的任务对象
        """
        self.task = task
        self.state_machine = TutorialStateMachine()
        self.detector = TutorialDetector(task)
        self.character_selector: Optional[CharacterSelector] = None
        self.movement_ctrl: Optional[MovementController] = None
        self.distance_calc: Optional[DistanceCalculator] = None
        self._verbose = False
        self._last_enemy_pos = None  # 敌人最后位置 (x, y, timestamp)
        
        # 【抖动检测】坐标历史记录，用于检测 A→B→A→B 模式
        self._position_history = []  # 存储最近的位置 (x, y)
        self._position_history_max = 4  # 最多记录4个位置（与卡住检测次数一致）
        
        # 抖动检测调试统计
        self._jitter_check_count = 0  # 抖动检测次数统计
        self._last_recorded_pos = None  # 上次记录的位置（用于调试）
        self._skipped_record_count = 0  # 因阈值跳过记录的次数
        
        # 【新增】移动方向历史记录（用于检测方向抖动）
        self._move_direction_history = []  # 存储最近的移动方向 (dx, dy)
        self._move_direction_max = 6  # 最多记录6个方向
        
        # 【新增】敌人位置平滑机制 - 用于解决 YOLO 检测抖动问题
        self._enemy_position_history = []  # 存储最近的敌人位置 (x, y)
        self._enemy_position_history_max = 5  # 最多记录5个位置
        self._enemy_position_jump_threshold = 150  # 位置跳动阈值（像素），超过此值认为是检测异常
    
    def set_verbose(self, verbose: bool):
        """设置详细日志"""
        self._verbose = verbose
        self.detector.set_verbose(verbose)
    
    def _log(self, message: str):
        """输出日志"""
        if hasattr(self.task, 'logger'):
            self.task.logger.info(f"[第一阶段] {message}")
    
    def _log_error(self, message: str):
        """输出错误日志"""
        if hasattr(self.task, 'logger'):
            self.task.logger.error(f"[第一阶段] {message}")
    
    def _cfg(self, key: str, default=None):
        """获取配置值"""
        if self.task.config is not None:
            return self.task.config.get(key, default)
        return self.task.default_config.get(key, default)
    
    def initialize(self, character: str) -> bool:
        """
        初始化处理器
        
        Args:
            character: 角色名称
            
        Returns:
            bool: 是否初始化成功
        """
        self.character_selector = CharacterSelector(character)
        self.movement_ctrl = MovementController(
            self.task,
            move_duration=self._cfg('移动持续时间(秒)', 0.5)
        )
        self.distance_calc = DistanceCalculator()
        
        self.detector.set_verbose(self._cfg('详细日志', False))
        
        # 初始化后台模式
        background_manager.update_config()
        
        self._log(f"初始化完成，角色: {character}")
        return True
    
    def run(self) -> bool:
        """
        运行第一阶段
        
        Returns:
            bool: 是否成功完成
        """
        self._log("=" * 50)
        self._log("开始执行第一阶段")
        self._log("=" * 50)
        
        try:
            # 状态机主循环
            while not self.state_machine.is_terminal():
                current_state = self.state_machine.current_state
                self._log(f"当前状态: {self.state_machine.get_state_name()}")
                
                # 更新帧
                self.task.next_frame()
                
                # 根据当前状态执行对应处理
                if current_state == TutorialState.IDLE:
                    self._handle_idle()
                
                elif current_state == TutorialState.CHECK_CHARACTER_SELECT:
                    self._handle_check_character_select()
                
                elif current_state == TutorialState.FIRST_CLICK:
                    self._handle_first_click()
                
                elif current_state == TutorialState.CONFIRM_DIALOG:
                    self._handle_confirm_dialog()
                
                elif current_state == TutorialState.SECOND_CLICK:
                    self._handle_second_click()
                
                elif current_state == TutorialState.LOADING:
                    self._handle_loading()
                
                elif current_state == TutorialState.SELF_DETECTION:
                    self._handle_self_detection()
                
                elif current_state == TutorialState.TARGET_DETECTION:
                    self._handle_target_detection()
                
                elif current_state == TutorialState.MOVE_TO_TARGET:
                    self._handle_move_to_target()
                
                elif current_state == TutorialState.NORMAL_ATTACK_DETECTION:
                    self._handle_normal_attack_detection()
                
                elif current_state == TutorialState.MOVE_DOWN:
                    self._handle_move_down()
                
                elif current_state == TutorialState.COMBAT_TRIGGER:
                    self._handle_combat_trigger()
                
                elif current_state == TutorialState.PHASE1_END_DETECTION:
                    self._handle_phase1_end_detection()
                
                elif current_state == TutorialState.PHASE1_END:
                    self._log("第一阶段已完成，退出第一阶段处理器")
                    return True
                
                else:
                    # 未知状态，跳过
                    time.sleep(0.1)
            
            # 检查最终状态
            if self.state_machine.is_completed():
                self._log("第一阶段完成")
                return True
            else:
                self._log_error(f"第一阶段失败: {self.state_machine.failure_reason}")
                return False
                
        except Exception as e:
            self._log_error(f"第一阶段异常: {e}")
            self.state_machine.fail(str(e))
            self._save_error_screenshot(f"phase1_error_{time.strftime('%H-%M-%S')}")
            return False
    
    # ==================== 状态处理方法 ====================
    
    def _handle_idle(self):
        """处理空闲状态"""
        # 直接转换到下一个状态
        self.state_machine.transition_to(TutorialState.CHECK_CHARACTER_SELECT)
    
    def _handle_check_character_select(self):
        """处理选角界面检测"""
        timeout = self._cfg('选角界面检测超时(秒)', 10.0)
        
        if self.detector.detect_character_select_screen(timeout):
            self._log("检测到选角界面")
            self.state_machine.transition_to(TutorialState.FIRST_CLICK)
        else:
            self._log_error("未检测到选角界面")
            self._save_error_screenshot("character_select_not_found")
            self.state_machine.fail("未检测到选角界面")
    
    def _handle_first_click(self):
        """处理第一次点击角色"""
        config = self.character_selector.get_current_config()
        if not config:
            self.state_machine.fail("无法获取角色配置")
            return
        
        # 计算点击位置
        click_x, click_y = config.get_click_position(self.task.width, self.task.height)
        self._log(f"第一次点击角色 '{config.name}' 位置: ({click_x}, {click_y})")
        
        # 执行点击
        self.task.click(click_x, click_y, after_sleep=self._cfg('点击后等待时间(秒)', 1.0))
        
        self.state_machine.transition_to(TutorialState.CONFIRM_DIALOG)
    
    def _handle_confirm_dialog(self):
        """处理确认对话框（第一次点击后）"""
        # 等待画面稳定
        time.sleep(0.5)
        
        # 第一次点击后，应该点击返回按钮返回选角界面（带容错重试）
        max_retry = 3  # 最大重试次数
        for retry in range(max_retry):
            back_pos = self.detector.detect_back_button(timeout=5.0)
            
            if back_pos:
                self._log(f"检测到返回按钮，点击返回: {back_pos} (尝试 {retry + 1}/{max_retry})")
                self.task.click(back_pos[0], back_pos[1], after_sleep=1.5)
                
                # 验证是否成功返回选角界面
                self.task.next_frame()
                if self.detector.detect_character_select_screen(timeout=2.0):
                    self._log("成功返回选角界面")
                    self.state_machine.transition_to(TutorialState.SECOND_CLICK)
                    return
                else:
                    self._log("点击后未返回选角界面，可能点击未生效")
            else:
                self._log(f"未检测到返回按钮 (尝试 {retry + 1}/{max_retry})")
                
                # 检查是否已经在选角界面（可能已经返回）
                self.task.next_frame()
                if self.detector.detect_character_select_screen(timeout=1.0):
                    self._log("已在选角界面，跳过返回按钮点击")
                    self.state_machine.transition_to(TutorialState.SECOND_CLICK)
                    return
        
        # 所有重试都失败
        self._log_error("多次尝试点击返回按钮后仍未返回选角界面")
        self._save_error_screenshot("back_button_click_failed")
        self.state_machine.fail("返回按钮点击失败")
    
    def _handle_second_click(self):
        """处理第二次点击角色"""
        # 等待画面稳定
        time.sleep(0.5)
        
        # 确认是否在选角界面
        self._log("确认选角界面...")
        if not self.detector.detect_character_select_screen(timeout=5.0):
            self._log("未检测到选角界面，继续尝试...")
        
        config = self.character_selector.get_current_config()
        if not config:
            self.state_machine.fail("无法获取角色配置")
            return
        
        # 计算点击位置
        click_x, click_y = config.get_click_position(self.task.width, self.task.height)
        self._log(f"第二次点击角色 '{config.name}' 位置: ({click_x}, {click_y})")
        
        # 执行点击
        self.task.click(click_x, click_y, after_sleep=1.0)
        
        # 第二次点击后，点击确定按钮（带容错重试）
        max_retry = 3  # 最大重试次数
        for retry in range(max_retry):
            confirm_pos = self.detector.detect_confirm_button(timeout=5.0)
            
            if confirm_pos:
                self._log(f"检测到确定按钮，点击确定: {confirm_pos} (尝试 {retry + 1}/{max_retry})")
                self.task.click(confirm_pos[0], confirm_pos[1], after_sleep=1.5)
                
                # 验证是否成功进入加载界面
                self.task.next_frame()
                if self.detector.detect_loading_start(timeout=3.0):
                    self._log("成功进入加载界面")
                    self.state_machine.transition_to(TutorialState.LOADING)
                    return
                else:
                    self._log(f"点击后未检测到加载界面，可能点击未生效")
                    # 继续下一次重试
            else:
                self._log(f"未检测到确定按钮 (尝试 {retry + 1}/{max_retry})")
                
                # 检查是否已经在加载界面
                self.task.next_frame()
                if self.detector.detect_loading_start(timeout=1.0):
                    self._log("已在加载界面，跳过确定按钮点击")
                    self.state_machine.transition_to(TutorialState.LOADING)
                    return
        
        # 所有重试都失败
        self._log_error("多次尝试点击确定按钮后仍未进入加载界面")
        self._save_error_screenshot("confirm_button_click_failed")
        self.state_machine.fail("确定按钮点击失败")
    
    def _handle_loading(self):
        """处理加载界面"""
        # 等待加载开始
        self.detector.detect_loading_start(timeout=10.0)
        
        # 等待加载结束
        if self.detector.detect_loading_end(timeout=60.0):
            # 加载后等待缓冲
            buffer_time = self._cfg('加载后等待时间(秒)', 30.0)
            self._log(f"加载完成，等待 {buffer_time} 秒缓冲...")
            time.sleep(buffer_time)
            self.state_machine.transition_to(TutorialState.SELF_DETECTION)
        else:
            self._log_error("加载超时")
            self.state_machine.fail("加载超时")
    
    def _handle_self_detection(self):
        """处理自身检测"""
        timeout = self._cfg('自身检测超时(秒)', 30.0)
        
        self_pos = self.detector.detect_self(timeout)
        
        if self_pos:
            self._log(f"检测到自身位置: ({self_pos.center_x}, {self_pos.center_y})")
            
            # 获取角色配置，判断角色类型
            config = self.character_selector.get_current_config()
            if config and config.target_type == 'monkey':
                # 悟空角色：检测到自身后等待10秒，然后向左上移动3秒
                self._log("悟空角色：等待10秒后向左上移动...")
                time.sleep(10.0)
                self._log("悟空角色：开始向左上移动3秒...")
                # 使用MovementController确保后台模式兼容
                # 使用KEY_UP和KEY_LEFT常量确保键名正确
                self.movement_ctrl._press_movement_keys_for_duration(
                    [self.movement_ctrl.KEY_UP, self.movement_ctrl.KEY_LEFT], 3.0
                )
                self._log("悟空角色：左上移动3秒完成，进入普攻按钮检测")
                self.state_machine.transition_to(TutorialState.NORMAL_ATTACK_DETECTION)
            else:
                # 路飞/小鸣人：保持原有流程，进入目标检测
                self.state_machine.transition_to(TutorialState.TARGET_DETECTION)
        else:
            self._log_error("自身检测超时")
            self._save_error_screenshot("self_detection_failed")
            self.state_machine.fail("自身检测超时")
    
    def _handle_target_detection(self):
        """处理目标检测"""
        timeout = self._cfg('目标检测超时(秒)', 10.0)
        config = self.character_selector.get_current_config()
        
        if not config:
            self.state_machine.fail("无法获取角色配置")
            return
        
        target = None
        
        if config.target_type == 'monkey':
            # 悟空：检测猴子
            self._log("检测猴子...")
            target = self.detector.detect_monkey(timeout)
        else:
            # 路飞/小鸣人：检测目标圈
            self._log("检测目标圈...")
            target = self.detector.detect_target_circle(timeout)
        
        if target:
            self._log(f"检测到目标: ({target.center_x}, {target.center_y})")
            self._target = target  # 保存目标位置
            self.state_machine.transition_to(TutorialState.MOVE_TO_TARGET)
        else:
            self._log_error("目标检测超时")
            self._save_error_screenshot("target_detection_failed")
            self.state_machine.fail("目标检测超时")
    
    def _handle_move_to_target(self):
        """处理移动靠近目标"""
        if not hasattr(self, '_target') or self._target is None:
            self.state_machine.fail("目标位置丢失")
            return
        
        # 移动总体超时机制（50秒）
        MOVE_TOTAL_TIMEOUT = 50.0
        if not hasattr(self, '_move_start_time'):
            self._move_start_time = time.time()
        
        elapsed_time = time.time() - self._move_start_time
        if elapsed_time > MOVE_TOTAL_TIMEOUT:
            self._log_error(f"移动超时 ({elapsed_time:.1f}秒)，转向普攻按钮检测")
            self.movement_ctrl.stop()
            self.state_machine.transition_to(TutorialState.NORMAL_ATTACK_DETECTION)
            return
        
        # 更新帧数据，确保使用最新截图
        self.task.next_frame()
        
        # 重新检测目标
        config = self.character_selector.get_current_config()
        target_type = config.target_type if config else 'target_circle'
        
        if target_type == 'monkey':
            # 【悟空专用】猴子会移动，可能走出屏幕
            # 使用更短超时(0.5秒)快速检测，检测不到时使用最后位置继续移动
            new_target = self.detector.detect_monkey(timeout=0.5)
            
            if new_target:
                # 检测到猴子，更新位置并保存最后位置
                self._target = new_target
                self._last_monkey_pos = (new_target.center_x, new_target.center_y)
                # 减少日志输出频率，每3次更新输出一次
                if not hasattr(self, '_monkey_update_count'):
                    self._monkey_update_count = 0
                self._monkey_update_count += 1
                if self._monkey_update_count % 3 == 1:
                    self._log(f"猴子位置更新: ({new_target.center_x}, {new_target.center_y})")
            elif hasattr(self, '_last_monkey_pos') and self._last_monkey_pos:
                # 未检测到猴子，使用最后位置继续移动（不输出日志以减少噪音）
                pass
            else:
                # 没有最后位置，跳过本次循环继续尝试
                self._log("猴子未检测到且无最后位置，继续尝试...")
                time.sleep(0.05)
                return
            
            # 【悟空专用】在移动期间检测普攻按钮（每3次循环检测一次，减少开销）
            if not hasattr(self, '_combat_check_count'):
                self._combat_check_count = 0
            self._combat_check_count += 1
            
            if self._combat_check_count % 3 == 1 and self.detector.quick_detect_normal_attack_button():
                self._log("移动期间检测到普攻按钮，进入普攻按钮检测阶段")
                self.movement_ctrl.stop()
                self._move_start_time = None
                self.state_machine.transition_to(TutorialState.NORMAL_ATTACK_DETECTION)
                return
        else:
            # 路飞/小鸣人：目标圈检测（快速检测，目标消失则进入下一阶段）
            new_target = self.detector.detect_target_circle(timeout=1.0)
            
            if new_target:
                self._target = new_target
                self._log(f"目标位置更新: ({new_target.center_x}, {new_target.center_y})")
            else:
                # 目标圈消失，角色已进入目标区域
                self._log("目标圈已消失，角色已进入目标区域，转向普攻按钮检测")
                self.movement_ctrl.stop()
                self._move_start_time = None
                self.state_machine.transition_to(TutorialState.NORMAL_ATTACK_DETECTION)
                return
        
        # 检测自身位置（使用更短超时，快速检测）
        self_pos = self.detector.detect_self(timeout=0.5)
        if not self_pos:
            # 无法检测自身，使用最后已知位置或屏幕中心
            if hasattr(self, '_last_self_pos') and self._last_self_pos:
                self_pos_x, self_pos_y = self._last_self_pos
            else:
                frame = self.task.frame
                self_pos_x = frame.shape[1] // 2
                self_pos_y = frame.shape[0] // 2
        else:
            self_pos_x = self_pos.center_x
            self_pos_y = self_pos.center_y
            self._last_self_pos = (self_pos_x, self_pos_y)
        
        # 计算距离
        distance = self.distance_calc.calculate_from_coords(
            self_pos_x, self_pos_y,
            self._target.center_x, self._target.center_y
        )
        
        # 减少距离日志输出频率（每2秒输出一次）
        if not hasattr(self, '_last_distance_log_time'):
            self._last_distance_log_time = 0
        if time.time() - self._last_distance_log_time > 2.0:
            self._log(f"距离目标: {distance:.0f}px, 已移动: {elapsed_time:.1f}秒")
            self._last_distance_log_time = time.time()
        
        # 移动靠近目标
        self.movement_ctrl.move_towards(
            self._target.center_x, self._target.center_y,
            self_pos_x, self_pos_y
        )
        
        # 短暂等待后继续循环（减少等待时间以加快响应）
        time.sleep(0.05)
    
    def _handle_normal_attack_detection(self):
        """处理普攻按钮检测"""
        # 获取角色配置，悟空使用更长的超时时间
        config = self.character_selector.get_current_config()
        if config and config.target_type == 'monkey':
            timeout = self._cfg('悟空普攻检测超时(秒)', 40.0)
        else:
            timeout = self._cfg('普攻检测超时(秒)', 10.0)
        
        if self.detector.detect_normal_attack_button(timeout):
            self._log("检测到普攻按钮")
            self.state_machine.transition_to(TutorialState.MOVE_DOWN)
        else:
            self._log_error("普攻按钮检测超时")
            self.state_machine.fail("普攻按钮检测超时")
    
    def _handle_move_down(self):
        """处理向下移动"""
        move_time = self._cfg('向下移动时间(秒)', 1.0)  # 默认1秒
        
        self._log(f"向下移动 {move_time} 秒...")
        
        # 使用MovementController确保后台模式兼容
        # 使用KEY_DOWN常量确保键名正确
        self.movement_ctrl._press_movement_keys_for_duration(
            [self.movement_ctrl.KEY_DOWN], move_time
        )
        
        self._log("向下移动完成")
        self.state_machine.transition_to(TutorialState.COMBAT_TRIGGER)
    
    def _get_combat_config(self, key: str, default=None):
        """
        从 AutoCombatTask 配置中读取战斗参数
        
        确保新手教程中的自动战斗使用用户在GUI中配置的参数
        
        Args:
            key: 配置键名
            default: 默认值
            
        Returns:
            配置值
        """
        # 优先从全局配置中获取 AutoCombatTask 的配置
        try:
            if og and og.config:
                combat_config = og.config.get('AutoCombatTask', {})
                if combat_config and key in combat_config:
                    return combat_config[key]
        except Exception:
            pass
        
        # 回退：从配置文件直接读取
        try:
            import json
            import os
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'configs', 'AutoCombatTask.json'
            )
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    combat_config = json.load(f)
                    if key in combat_config:
                        return combat_config[key]
        except Exception:
            pass
        
        return default
    
    def _create_combat_config_adapter(self):
        """
        创建配置适配器，使 SkillController 能读取 AutoCombatTask 的配置
        
        SkillController 期望 task 对象具有 config 属性，
        此适配器将 config.get() 调用重定向到 _get_combat_config
        
        Returns:
            配置适配器对象
        """
        handler = self
        
        class CombatConfigAdapter:
            """战斗配置适配器"""
            
            def __init__(self, handler):
                self._handler = handler
                # 复制必要的属性给 SkillController 使用
                self.logger = handler.task.logger
                self.frame = None  # 将在运行时更新
                self.executor = handler.task.executor if hasattr(handler.task, 'executor') else None
            
            @property
            def config(self):
                """返回配置字典，支持 .get() 方法"""
                return self
            
            def get(self, key, default=None):
                """从 AutoCombatTask 配置读取"""
                return handler._get_combat_config(key, default)
            
            def send_key(self, key):
                """转发按键操作"""
                return handler.task.send_key(key)
            
            def click(self, x, y, after_sleep=None):
                """转发点击操作（ADB 模式需要）"""
                return handler.task.click(x, y, after_sleep=after_sleep)
            
            def is_adb(self):
                """检查是否为 ADB 模式（动态检测）"""
                try:
                    # 检查 task 是否有 is_adb 方法
                    if not hasattr(handler.task, 'is_adb'):
                        return False
                    
                    # 检查 executor 是否存在且有效
                    if not hasattr(handler.task, 'executor') or handler.task.executor is None:
                        return False
                    
                    # 检查 interaction 是否存在
                    if not hasattr(handler.task.executor, 'interaction') or handler.task.executor.interaction is None:
                        return False
                    
                    # 调用原始 is_adb 方法
                    result = handler.task.is_adb()
                    return result
                except Exception as e:
                    return False
            
            def update_frame(self):
                """更新帧引用"""
                self.frame = handler.task.frame
        
        return CombatConfigAdapter(self)
    
    def _handle_combat_trigger(self):
        """处理自动战斗触发
        
        同时运行自动战斗和第一阶段结束检测，
        检测到 end01.png 和 end02.png 后直接进入 PHASE1_END。
        
        注意：第一阶段使用独立的战斗逻辑，不使用 GUI 自动战斗触发器。
        """
        self._log("新手教程第一阶段完成，启动自动战斗...")
        
        # 获取第一阶段结束检测超时配置
        phase1_end_timeout = self._cfg('第一阶段结束检测超时(秒)', 120.0)
        
        # 直接在新手教程任务中运行自动战斗逻辑
        try:
            from src.combat.state_detector import StateDetector
            from src.combat.skill_controller import SkillController
            from src.combat import BattlefieldState
            from src.task.AutoCombatTask import AutoCombatTask
            import random
            
            # 初始化战斗控制器（与AutoCombatTask保持一致）
            state_detector = StateDetector(self.task)
            state_detector.set_verbose(self._verbose)
            
            # 创建配置适配器，使 SkillController 能读取 AutoCombatTask 的配置
            combat_config_adapter = self._create_combat_config_adapter()
            skill_ctrl = SkillController(combat_config_adapter)
            
            # 【关键】复用AutoCombatTask的战场处理方法
            # 创建临时AutoCombatTask实例，注入当前控制器
            auto_combat = AutoCombatTask(self.task.executor, self.task)
            auto_combat.state_detector = state_detector
            auto_combat.movement_ctrl = self.movement_ctrl
            auto_combat.skill_ctrl = skill_ctrl
            auto_combat.distance_calc = self.distance_calc
            auto_combat.logger = self.task.logger
            
            # 输出当前战斗配置（详细日志模式）
            if self._verbose:
                self._log("自动战斗配置（从AutoCombatTask继承）:")
                self._log(f"  自动普攻: {self._get_combat_config('自动普攻', True)}")
                self._log(f"  自动技能1: {self._get_combat_config('自动技能1', True)}")
                self._log(f"  自动技能2: {self._get_combat_config('自动技能2', True)}")
                self._log(f"  自动大招: {self._get_combat_config('自动大招', True)}")
                self._log(f"  普攻间隔: {self._get_combat_config('普攻间隔(秒)', 0.5)}秒")
                self._log(f"  技能1间隔: {self._get_combat_config('技能1间隔(秒)', 2.0)}秒")
                self._log(f"  技能2间隔: {self._get_combat_config('技能2间隔(秒)', 3.0)}秒")
                self._log(f"  大招间隔: {self._get_combat_config('大招间隔(秒)', 5.0)}秒")
            
            # 启动死亡状态并行监控
            state_detector.start_death_monitor()
            self._log("死亡状态监控线程已启动")
            
            # 【关键修复】启动第一阶段结束检测线程（并行运行）
            self.detector.start_phase1_end_detection(phase1_end_timeout)
            self._log(f"第一阶段结束检测线程已启动（超时: {phase1_end_timeout}秒）")
            
            # 自动战斗主循环
            loop_count = 0
            last_state = None
            verbose = self._verbose
            phase1_end_detected = False
            
            while True:
                loop_count += 1
                
                # 【关键修复】检查是否检测到第一阶段结束
                if self.detector.is_phase1_end_detected():
                    self._log("检测到第一阶段结束标志，停止自动战斗")
                    phase1_end_detected = True
                    break
                
                # 检测退出信号
                if hasattr(self.task, 'exit_is_set') and self.task.exit_is_set():
                    self._log("检测到退出信号，停止自动战斗")
                    break
                
                # 后台模式：检查并自动伪最小化
                background_manager.check_and_auto_pseudo_minimize()
                
                # 更新帧
                self.task.next_frame()
                combat_config_adapter.update_frame()  # 同步帧到适配器
                
                # 死亡状态检测
                if state_detector.is_death_detected():
                    self._log("检测到死亡状态，等待复活...")
                    skill_ctrl.stop_auto_skills()
                    self.movement_ctrl.stop()
                    time.sleep(1)
                    continue
                
                # 自身位置检测（带容错重试）
                self_pos = state_detector.detect_self(timeout=15)
                if self_pos is None:
                    self._log("【容错】15秒未检测到自身位置，尝试随机移动1秒后再次检测...")
                    
                    # 随机移动1秒
                    import random
                    random.seed()  # 重置随机种子确保每次都是真正随机
                    directions = [
                        (['W'], 3), (['S'], 2), (['A'], 2), (['D'], 2),
                        (['W', 'A'], 2), (['W', 'D'], 2), (['S', 'A'], 1), (['S', 'D'], 1),
                    ]
                    weights = [w for _, w in directions]
                    keys = random.choices([d[0] for d in directions], weights=weights, k=1)[0]
                    self._log(f"【容错】随机移动方向: {'+'.join(keys)}, 持续1秒 (权重随机)")
                    self.movement_ctrl._press_movement_keys_for_duration(keys, 1.0)
                    
                    # 再次检测自身位置（10秒超时）
                    self._log("【容错】随机移动后再次检测自身位置（10秒超时）...")
                    self_pos = state_detector.detect_self(timeout=10)
                    
                    if self_pos is None:
                        self._log_error("【容错】随机移动后仍10秒未检测到自身位置，停止自动战斗")
                        self._save_error_screenshot("self_detection_failed_after_retry")
                        break
                    else:
                        self._log(f"【容错】随机移动后成功检测到自身位置: ({self_pos.center_x}, {self_pos.center_y})")
                
                # 【抖动检测】记录当前位置
                self._record_position(self_pos.center_x, self_pos.center_y)
                
                # 【优先级修复】先进行战场状态检测，判断是否有敌人在技能范围内
                # 如果有敌人在范围内，跳过卡住/抖动检测，直接进入战斗逻辑
                state, allies, enemies = state_detector.get_battlefield_state_detailed()
                last_state = state.value
                
                # 【快速检测】如果有敌人在技能范围内，立即进入战斗逻辑
                has_enemy_in_range = False
                if enemies:
                    skill_distance, any_in_range = self._get_skill_distance_all_enemies(self_pos, enemies)
                    if any_in_range:
                        has_enemy_in_range = True
                
                # 【卡住检测】只有在没有敌人在技能范围内时才执行
                if not has_enemy_in_range:
                    is_stuck = self._detect_stuck()
                    if is_stuck:
                        self._log("【卡住检测】连续4次检测到相同坐标，角色可能被卡住，向下移动1秒")
                        self.movement_ctrl._press_movement_keys_for_duration(['S'], 1.0)
                        # 清空位置历史，重新检测
                        self._position_history.clear()
                        time.sleep(0.1)
                        continue
                    
                    # 【抖动检测】检测是否存在 A-B-A-B 抖动模式
                    is_jitter = self._detect_jitter()
                    
                    # 简化日志输出：只在抖动检测失败且历史记录不足时输出
                    if not is_jitter and len(self._position_history) < 4:
                        self._log(f"【抖动检测】历史记录不足: {len(self._position_history)}/4, 继续收集数据...")
                    
                    # 如果检测到抖动，执行随机移动并清空历史记录
                    if is_jitter:
                        self._perform_random_move()
                        # 清空位置历史，确保下次抖动检测能重新积累数据
                        self._position_history.clear()
                        self._log("【抖动检测】已清空位置历史，准备重新检测")
                        # 随机移动后继续正常循环
                        time.sleep(0.1)
                        continue
                
                # 每次循环都输出详细的战场状态（便于调试随机移动问题）
                self._log(f"战场状态: {last_state}, 友方: {len(allies) if allies else 0}, 敌方: {len(enemies) if enemies else 0}, 自身: ({self_pos.center_x},{self_pos.center_y})")
                
                # 根据战场状态处理
                if state == BattlefieldState.NO_UNITS:
                    # 无单位：检查技能监控线程是否最近检测到敌人
                    if skill_ctrl.is_in_skill_range() and skill_ctrl.auto_skill_enabled:
                        # 技能正在进行中，不随机移动，继续攻击
                        self._log("战场无单位但技能仍在范围内，继续攻击")
                        self.movement_ctrl.stop()
                        skill_ctrl.start_auto_skills()
                    elif hasattr(self, '_last_enemy_pos') and self._last_enemy_pos:
                        # 有敌人最后位置，向该位置移动
                        last_x, last_y, last_time = self._last_enemy_pos
                        # 如果最后位置信息不超过5秒，向该位置移动
                        if time.time() - last_time < 5.0:
                            self._log(f"战场无单位，向敌人最后位置移动: ({last_x}, {last_y})")
                            skill_ctrl.stop_auto_skills()
                            self.movement_ctrl.move_towards(last_x, last_y,
                                                           self_pos.center_x, self_pos.center_y)
                        else:
                            # 最后位置信息过期，随机移动
                            self._last_enemy_pos = None
                            skill_ctrl.stop_auto_skills()
                            skill_ctrl.update_distance(9999)
                            self.movement_ctrl.stop()
                            directions = [
                                (['W'], 3), (['S'], 2), (['A'], 2), (['D'], 2),
                                (['W', 'A'], 2), (['W', 'D'], 2), (['S', 'A'], 1), (['S', 'D'], 1),
                            ]
                            weights = [w for _, w in directions]
                            # 【修复】重置随机种子确保每次都是真正随机
                            random.seed()
                            keys = random.choices([d[0] for d in directions], weights=weights, k=1)[0]
                            self._log(f"随机移动: {'+'.join(keys)} 方向 (权重随机)")
                            self.movement_ctrl._press_movement_keys_for_duration(keys, 3.0)
                    else:
                        # 确实没有敌人信息，随机移动搜索
                        skill_ctrl.stop_auto_skills()
                        skill_ctrl.update_distance(9999)
                        self.movement_ctrl.stop()
                        directions = [
                            (['W'], 3), (['S'], 2), (['A'], 2), (['D'], 2),
                            (['W', 'A'], 2), (['W', 'D'], 2), (['S', 'A'], 1), (['S', 'D'], 1),
                        ]
                        weights = [w for _, w in directions]
                        # 【修复】使用 random.randint 确保每次都是真正随机
                        import random
                        random.seed()  # 重置随机种子
                        keys = random.choices([d[0] for d in directions], weights=weights, k=1)[0]
                        self._log(f"随机移动: {'+'.join(keys)} 方向 (权重随机)")
                        self.movement_ctrl._press_movement_keys_for_duration(keys, 3.0)
                
                elif state == BattlefieldState.ALLIES_ONLY:
                    # 仅有友方：跟随友方
                    skill_ctrl.stop_auto_skills()
                    if allies:
                        target = allies[0]
                        distance = self.distance_calc.calculate(self_pos, target)
                        if distance > 200:
                            self.movement_ctrl.move_towards(target.center_x, target.center_y,
                                                           self_pos.center_x, self_pos.center_y)
                        elif distance < 100:
                            self.movement_ctrl.move_away(target.center_x, target.center_y,
                                                        self_pos.center_x, self_pos.center_y)
                        else:
                            self.movement_ctrl.stop()
                
                elif state == BattlefieldState.ENEMIES_ONLY or state == BattlefieldState.MIXED:
                    # 有敌人：向最近的敌人移动并攻击
                    targets = enemies if state == BattlefieldState.ENEMIES_ONLY else enemies
                    if targets:
                        # 【目标锁定】优先使用已锁定的目标，避免频繁切换
                        if not hasattr(self, '_locked_enemy'):
                            self._locked_enemy = None
                            self._locked_enemy_time = 0
                        
                        # 【位置平滑】对检测到的敌人位置进行平滑处理
                        raw_enemy = min(targets, key=lambda e: self.distance_calc.calculate(self_pos, e))
                        smoothed_x, smoothed_y = self._smooth_enemy_position(raw_enemy)
                                                
                        # 尝试找到与锁定目标最接近的敌人
                        if self._locked_enemy is not None:
                            locked_x, locked_y = self._locked_enemy
                            # 寻找距离锁定位置最近的敌人（使用平滑后的位置）
                            best_match = None
                            min_offset = float('inf')
                            for enemy in targets:
                                offset = abs(enemy.center_x - locked_x) + abs(enemy.center_y - locked_y)
                                if offset < min_offset:
                                    min_offset = offset
                                    best_match = enemy
                                                    
                            # 【关键修复】放宽匹配范围到 300px，适应 YOLO 检测抖动
                            if best_match and min_offset < 300:
                                # 使用平滑后的位置更新锁定
                                nearest = best_match
                                # 更新锁定位置（使用平滑后的位置）
                                self._locked_enemy = (smoothed_x, smoothed_y)
                                self._locked_enemy_time = time.time()
                                # 每5秒输出一次锁定信息
                                if loop_count % 100 == 0:
                                    self._log(f"【目标锁定】保持锁定: ({smoothed_x},{smoothed_y}), 偏移:{min_offset:.0f}px")
                            else:
                                # 锁定目标丢失，使用平滑后的位置
                                nearest = raw_enemy
                                self._locked_enemy = (smoothed_x, smoothed_y)
                                self._locked_enemy_time = time.time()
                                self._log(f"【目标锁定】重新锁定目标: ({smoothed_x},{smoothed_y})")
                        else:
                            # 没有锁定目标，使用平滑后的位置锁定
                            nearest = raw_enemy
                            self._locked_enemy = (smoothed_x, smoothed_y)
                            self._locked_enemy_time = time.time()
                                                
                        # 【关键修复】检测所有敌人的距离
                        # 如果有一个敌人在范围内，就启动技能
                        skill_distance, any_in_range = self._get_skill_distance_all_enemies(self_pos, targets)
                        
                        # 【调试】输出自身、敌人坐标和距离（包含敌人数量信息）
                        self._log(f"【战斗】敌人数量:{len(targets)}, 自身:({self_pos.center_x},{self_pos.center_y}), 最近敌人距离:{skill_distance:.0f}px, 有敌人在范围内:{any_in_range}")
                                                
                        # 【关键】保存敌人最后位置（用于 NO_UNITS 时的追踪）
                        self._last_enemy_pos = (smoothed_x, smoothed_y, time.time())
                                                
                        # 【关键修复】更新技能控制器的距离信息
                        skill_ctrl.update_distance(skill_distance)
                                                
                        if any_in_range:
                            # 有敌人在技能范围内，启动自动技能
                            self._log(f"【战斗】检测到敌人在范围内({skill_distance:.0f}px <= 225px)，停止移动，开始攻击")
                            skill_ctrl.start_auto_skills()
                            skill_ctrl.update()
                            self.movement_ctrl.stop()
                        else:
                            # 所有敌人都超出技能范围，靠近最近的目标
                            self._log(f"【战斗】所有敌人超出范围，最近距离{skill_distance:.0f}px > 225px，靠近敌人")
                            skill_ctrl.stop_auto_skills()
                            # 【调试】输出移动方向（使用平滑后的位置）
                            dx = smoothed_x - self_pos.center_x
                            dy = smoothed_y - self_pos.center_y
                            self._log(f"【移动方向】dx:{dx:+.0f}, dy:{dy:+.0f}, 目标:({smoothed_x},{smoothed_y}), 自身:({self_pos.center_x},{self_pos.center_y})")
                                                    
                            # 【方向抖动检测】记录移动方向
                            self._record_move_direction(dx, dy)
                                                    
                            # 【方向抖动检测】检测是否方向抖动
                            is_direction_jitter = self._detect_direction_jitter()
                            if is_direction_jitter:
                                self._log("【方向抖动检测】检测到方向反复变化，执行随机移动")
                                self._perform_random_move()
                                self._move_direction_history.clear()  # 清空方向历史
                                time.sleep(0.1)
                                continue
                                                    
                            # 【关键修复】使用平滑后的位置进行移动
                            self.movement_ctrl.move_towards(smoothed_x, smoothed_y,
                                                           self_pos.center_x, self_pos.center_y)
                
                time.sleep(0.05)  # 主循环间隔
            
            # 清理资源
            self.detector.stop_phase1_end_detection()
            state_detector.stop_death_monitor()
            skill_ctrl.stop_auto_skills()
            self.movement_ctrl.stop()
            self._log("自动战斗已停止")
            
            # 根据检测结果转换状态
            if phase1_end_detected:
                self._log("第一阶段结束检测成功，进入下一阶段")
                self.state_machine.transition_to(TutorialState.PHASE1_END)
            else:
                self._log_error("第一阶段结束检测超时，停止自动战斗")
                self.state_machine.fail("第一阶段结束检测超时")
        
        except Exception as e:
            self._log_error(f"自动战斗异常: {e}")
            import traceback
            self._log_error(traceback.format_exc())
            self.detector.stop_phase1_end_detection()
            self.state_machine.fail(f"自动战斗异常: {e}")
    
    def _handle_phase1_end_detection(self):
        """处理第一阶段结束检测"""
        timeout = self._cfg('第一阶段结束检测超时(秒)', 120.0)
        
        self._log("开始第一阶段结束检测...")
        
        # 启动结束检测
        self.detector.start_phase1_end_detection(timeout)
        
        # 等待检测完成
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.detector.is_phase1_end_detected():
                self._log("第一阶段结束检测成功")
                self.detector.stop_phase1_end_detection()
                self.state_machine.transition_to(TutorialState.PHASE1_END)
                return
            
            if hasattr(self.task, '_should_exit') and self.task._should_exit():
                self.detector.stop_phase1_end_detection()
                self.state_machine.fail("用户取消")
                return
            
            time.sleep(0.5)
        
        self._log_error("第一阶段结束检测超时")
        self.detector.stop_phase1_end_detection()
        self.state_machine.fail("第一阶段结束检测超时")
    
    # ==================== 辅助方法 ====================
    
    def _save_error_screenshot(self, error_name: str):
        """保存错误截图"""
        import re
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', error_name)
        filename = f"{safe_name}_{time.strftime('%H-%M-%S')}.png"
        self.detector.save_screenshot(filename)
    
    def _record_position(self, x: int, y: int):
        """
        记录位置历史，用于检测抖动和卡住
        
        检测逻辑：
        - 无论位置是否变化，都记录到历史中（用于检测卡住）
        - 抖动检测会区分位置是否真正变化

        Args:
            x, y: 当前坐标
        """
        # 直接记录当前位置（不再跳过相近的位置，以便卡住检测能正常工作）
        self._position_history.append((x, y))
        self._last_recorded_pos = (x, y)
        
        # 保持历史记录在限制范围内
        if len(self._position_history) > self._position_history_max:
            self._position_history.pop(0)
        
        # 输出记录信息（包含与上一个位置的距离）
        if len(self._position_history) >= 2:
            prev_x, prev_y = self._position_history[-2]
            dist = ((x - prev_x) ** 2 + (y - prev_y) ** 2) ** 0.5
            self._log(f"【位置记录】新位置: ({x},{y}) <- 距离上个位置{dist:.0f}px, 历史: {len(self._position_history)}个")
        else:
            self._log(f"【位置记录】首个位置: ({x},{y}), 历史: {len(self._position_history)}个")
    
    def _detect_jitter(self) -> bool:
        """
        检测是否存在抖动的模式
        
        检测逻辑：
        1. 检查最近4个位置是否在两组区域之间来回移动 (A-B-A-B模式)
        2. 使用聚类思想，将位置分为两组（A区和B区）
        3. 如果模式是 A-B-A-B 或类似来回模式，则判定为抖动
        
        Returns:
            bool: 如果检测到抖动返回 True
        """
        self._jitter_check_count += 1
        
        # 需要4个位置才能检测 A-B-A-B 模式
        if len(self._position_history) < 4:
            return False
        
        # 获取最近4个位置
        pos = self._position_history[-4:]
        
        # 使用阈值来判断位置是否在同一区域
        AREA_THRESHOLD = 100  # 100像素内视为同一区域
        
        # 检查是否在两组位置之间来回移动
        # 简化检测：检查奇数位和偶数位是否分别聚类
        even_positions = [pos[0], pos[2]]  # 第1,3个位置（偶数索引）- A区域
        odd_positions = [pos[1], pos[3]]   # 第2,4个位置（奇数索引）- B区域
        
        # 计算偶数位置的平均中心点（A区域中心）
        even_center_x = sum(p[0] for p in even_positions) / 2
        even_center_y = sum(p[1] for p in even_positions) / 2
        
        # 计算奇数位置的平均中心点（B区域中心）
        odd_center_x = sum(p[0] for p in odd_positions) / 2
        odd_center_y = sum(p[1] for p in odd_positions) / 2
        
        # 检查偶数位置是否都靠近偶数中心点（A区域）
        even_clustered = all(
            ((p[0] - even_center_x) ** 2 + (p[1] - even_center_y) ** 2) ** 0.5 < AREA_THRESHOLD
            for p in even_positions
        )
        
        # 检查奇数位置是否都靠近奇数中心点（B区域）
        odd_clustered = all(
            ((p[0] - odd_center_x) ** 2 + (p[1] - odd_center_y) ** 2) ** 0.5 < AREA_THRESHOLD
            for p in odd_positions
        )
        
        # 检查A区域和B区域是否不同（有足够的距离）
        distance_between_areas = ((even_center_x - odd_center_x) ** 2 + (even_center_y - odd_center_y) ** 2) ** 0.5
        areas_are_different = distance_between_areas > AREA_THRESHOLD
        
        # 每10次检测或检测到抖动时输出详细调试信息
        if self._jitter_check_count % 10 == 1 or (even_clustered and odd_clustered and areas_are_different):
            history_str = " -> ".join([f"({x},{y})" for x, y in pos])
            self._log(f"【抖动检测详情】位置历史: {history_str}")
            self._log(f"【抖动检测详情】A区域中心: ({even_center_x:.0f},{even_center_y:.0f}), "
                     f"B区域中心: ({odd_center_x:.0f},{odd_center_y:.0f}), "
                     f"区域间距离: {distance_between_areas:.0f}px, "
                     f"A区域聚类: {even_clustered}, B区域聚类: {odd_clustered}, 区域不同: {areas_are_different}")
        
        # 只有当偶数位置聚类、奇数位置聚类，且两个区域不同时，才判定为抖动
        is_jitter = even_clustered and odd_clustered and areas_are_different
        if is_jitter:
            self._log(f"【抖动检测】✓ 检测到抖动! A-B-A-B模式确认")
        return is_jitter
    
    def _detect_stuck(self) -> bool:
        """
        检测角色是否被卡住（连续4次检测到相同坐标）
        
        检测逻辑：
        - 如果最近4个位置都在10像素范围内，认为角色被卡住
        - 每次触发后清空历史，允许再次检测
        
        Returns:
            bool: 如果检测到卡住返回 True
        """
        STUCK_THRESHOLD = 10  # 10像素内视为同一位置
        STUCK_COUNT = 4  # 连续4次
        
        if len(self._position_history) < STUCK_COUNT:
            return False
        
        # 获取最近6个位置
        recent_positions = self._position_history[-STUCK_COUNT:]
        
        # 计算这6个位置的平均中心点
        avg_x = sum(p[0] for p in recent_positions) / STUCK_COUNT
        avg_y = sum(p[1] for p in recent_positions) / STUCK_COUNT
        
        # 检查所有位置是否都在阈值范围内
        all_same = all(
            ((p[0] - avg_x) ** 2 + (p[1] - avg_y) ** 2) ** 0.5 < STUCK_THRESHOLD
            for p in recent_positions
        )
        
        if all_same:
            positions_str = " -> ".join([f"({x},{y})" for x, y in recent_positions])
            self._log(f"【卡住检测】连续{STUCK_COUNT}次相同坐标: {positions_str}")
        
        return all_same
    
    def _record_move_direction(self, dx: float, dy: float):
        """
        记录移动方向历史，用于检测方向抖动
        
        Args:
            dx, dy: 移动方向向量
        """
        # 只记录水平方向（dx）的符号，因为左右抖动是最常见的
        direction_sign = 1 if dx > 0 else -1
        
        self._move_direction_history.append(direction_sign)
        
        # 保持历史记录在限制范围内
        if len(self._move_direction_history) > self._move_direction_max:
            self._move_direction_history.pop(0)
    
    def _detect_direction_jitter(self) -> bool:
        """
        检测是否存在方向抖动（左右反复变化）
        
        检测逻辑：
        - 如果最近6次移动方向是 +1, -1, +1, -1, +1, -1（左右左右左右）或 -1, +1, -1, +1, -1, +1（右左右左右左）
        - 则认为存在方向抖动
        
        Returns:
            bool: 如果检测到方向抖动返回 True
        """
        if len(self._move_direction_history) < 6:
            return False
        
        # 获取最近6个方向
        dirs = self._move_direction_history[-6:]
        
        # 检测左右左右左右或右左右左右左模式
        # 模式1: [+1, -1, +1, -1, +1, -1] (左右左右左右)
        # 模式2: [-1, +1, -1, +1, -1, +1] (右左右左右左)
        pattern1 = dirs == [1, -1, 1, -1, 1, -1]
        pattern2 = dirs == [-1, 1, -1, 1, -1, 1]
        
        is_jitter = pattern1 or pattern2
        
        if is_jitter:
            self._log(f"【方向抖动检测】方向历史: {dirs}, 模式1:{pattern1}, 模式2:{pattern2}")
        
        return is_jitter
    
    def _smooth_enemy_position(self, enemy):
        """
        敌人位置平滑处理 - 解决 YOLO 检测抖动问题
        
        策略：
        1. 记录最近 N 次检测到的敌人位置
        2. 如果新位置与历史平均值相差太大（超过阈值），认为是检测异常
        3. 异常情况下，使用历史位置的加权平均
        4. 即使检测到跳动，也以低权重将新位置加入历史（适应真实移动）
        
        Args:
            enemy: 检测到的敌人对象（DetectionResult）
            
        Returns:
            平滑后的敌人位置对象
        """
        current_x = enemy.center_x
        current_y = enemy.center_y
        
        # 如果没有历史记录，直接记录并返回
        if not self._enemy_position_history:
            self._enemy_position_history.append((current_x, current_y))
            return (current_x, current_y)
        
        # 计算历史位置的中位数（对异常值更鲁棒）
        x_coords = sorted([pos[0] for pos in self._enemy_position_history])
        y_coords = sorted([pos[1] for pos in self._enemy_position_history])
        n = len(self._enemy_position_history)
        
        if n % 2 == 1:
            median_x = x_coords[n // 2]
            median_y = y_coords[n // 2]
        else:
            median_x = (x_coords[n // 2 - 1] + x_coords[n // 2]) // 2
            median_y = (y_coords[n // 2 - 1] + y_coords[n // 2]) // 2
        
        # 计算当前位置与历史中位数的距离
        distance_from_median = ((current_x - median_x) ** 2 + (current_y - median_y) ** 2) ** 0.5
        
        # 判断是否为位置跳动（异常检测）
        if distance_from_median > self._enemy_position_jump_threshold:
            # 检测到位置跳动，输出日志
            self._log(f"【位置平滑】检测到跳动 {distance_from_median:.0f}px > {self._enemy_position_jump_threshold}px, 中位数: ({median_x},{median_y}) 原位置: ({current_x},{current_y})")
                    
            # 【关键修复】仍然将原位置加入历史，让历史记录能够跟踪真实移动
            # 但返回加权平均位置作为平滑结果
            self._enemy_position_history.append((current_x, current_y))
            if len(self._enemy_position_history) > self._enemy_position_history_max:
                self._enemy_position_history.pop(0)
                    
            # 计算加权平均（越近的权重越高）
            total_weight = 0
            weighted_x = 0
            weighted_y = 0
            for i, (hx, hy) in enumerate(self._enemy_position_history):
                weight = i + 1  # 越近的权重越高
                weighted_x += hx * weight
                weighted_y += hy * weight
                total_weight += weight
                    
            return (int(weighted_x / total_weight), int(weighted_y / total_weight))
        else:
            # 位置正常，记录到历史
            self._enemy_position_history.append((current_x, current_y))
                    
            # 保持历史记录在限制范围内
            if len(self._enemy_position_history) > self._enemy_position_history_max:
                self._enemy_position_history.pop(0)
                    
            return (current_x, current_y)
    
    def _perform_random_move(self):
        """执行随机移动，用于摆脱抖动"""
        import random
        random.seed()  # 重置随机种子确保每次都是真正随机
        
        self._log("【抖动检测】检测到坐标抖动(A→B→A→B→A→B)，执行随机移动")
        
        # 随机选择一个方向移动2秒
        directions = [
            (['W'], 3), (['S'], 2), (['A'], 2), (['D'], 2),
            (['W', 'A'], 2), (['W', 'D'], 2), (['S', 'A'], 1), (['S', 'D'], 1),
        ]
        weights = [w for _, w in directions]
        keys = random.choices([d[0] for d in directions], weights=weights, k=1)[0]
        
        self._log(f"【抖动检测】随机移动方向: {'+'.join(keys)}, 持续2秒 (权重随机)")
        self.movement_ctrl._press_movement_keys_for_duration(keys, 2.0)
    
    def _get_skill_distance_all_enemies(self, self_pos, enemies):
        """
        获取技能释放距离（检测所有敌人）
        
        逻辑：
        1. 如果有任何一个敌人在技能范围内(0-225px)，返回该距离（优先）
        2. 否则返回最近敌人的距离
        
        Args:
            self_pos: 自身位置
            enemies: 敌人列表
            
        Returns:
            tuple: (distance, in_range) 距离和是否在范围内
        """
        if not enemies or self_pos is None:
            return (float('inf'), False)
        
        # 技能范围
        SKILL_RANGE_MIN = 0
        SKILL_RANGE_MAX = 225
        
        nearest_distance = float('inf')
        in_range_distance = None
        
        for enemy in enemies:
            distance = self.distance_calc.calculate(self_pos, enemy)
            
            # 更新最近距离
            if distance < nearest_distance:
                nearest_distance = distance
            
            # 检查是否在技能范围内
            if SKILL_RANGE_MIN <= distance <= SKILL_RANGE_MAX:
                if in_range_distance is None or distance < in_range_distance:
                    in_range_distance = distance
        
        
        # 优先返回范围内的距离，否则返回最近距离
        if in_range_distance is not None:
            return (in_range_distance, True)
        return (nearest_distance, False)
    
    def cleanup(self):
        """清理资源"""
        self.detector.stop_phase1_end_detection()
        
        if self.movement_ctrl:
            self.movement_ctrl.stop()
        
        # 清空位置历史
        self._position_history.clear()
        
        # 清空敌人位置历史
        self._enemy_position_history.clear()
        
        # 清空锁定目标
        if hasattr(self, '_locked_enemy'):
            self._locked_enemy = None
        
        self._log("第一阶段资源清理完成")
