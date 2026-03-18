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
        
        # 移动总体超时机制（30秒）
        MOVE_TOTAL_TIMEOUT = 30.0
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
        
        # 重新检测目标（快速检测，如果目标消失则立即进入下一阶段）
        config = self.character_selector.get_current_config()
        target_type = config.target_type if config else 'target_circle'
        
        if target_type == 'monkey':
            new_target = self.detector.detect_monkey(timeout=1.0)
        else:
            new_target = self.detector.detect_target_circle(timeout=1.0)
        
        if new_target:
            # 目标仍存在，更新位置
            self._target = new_target
            self._log(f"目标位置更新: ({new_target.center_x}, {new_target.center_y})")
            
            # 检测自身位置
            self_pos = self.detector.detect_self(timeout=5.0)
            if not self_pos:
                self._log("无法检测自身位置，使用屏幕中心")
                frame = self.task.frame
                self_pos_x = frame.shape[1] // 2
                self_pos_y = frame.shape[0] // 2
            else:
                self_pos_x = self_pos.center_x
                self_pos_y = self_pos.center_y
            
            # 计算距离
            distance = self.distance_calc.calculate_from_coords(
                self_pos_x, self_pos_y,
                self._target.center_x, self._target.center_y
            )
            
            self._log(f"距离目标: {distance:.0f}px, 已移动: {elapsed_time:.1f}秒")
            
            # 移动靠近目标
            self.movement_ctrl.move_towards(
                self._target.center_x, self._target.center_y,
                self_pos_x, self_pos_y
            )
        else:
            # 目标消失（角色已进入目标区域），立即转向普攻按钮检测
            target_name = '猴子' if target_type == 'monkey' else '目标圈'
            self._log(f"{target_name}已消失，角色已进入目标区域，转向普攻按钮检测")
            self.movement_ctrl.stop()
            # 重置移动计时
            self._move_start_time = None
            self.state_machine.transition_to(TutorialState.NORMAL_ATTACK_DETECTION)
            return
        
        # 短暂等待后继续循环
        time.sleep(0.1)
    
    def _handle_normal_attack_detection(self):
        """处理普攻按钮检测"""
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
    
    def _handle_combat_trigger(self):
        """处理自动战斗触发"""
        self._log("新手教程第一阶段完成，启动自动战斗...")
        
        # 直接在新手教程任务中运行自动战斗逻辑
        try:
            from src.combat.state_detector import StateDetector
            from src.combat.skill_controller import SkillController
            from src.combat import BattlefieldState
            import random
            
            # 初始化战斗控制器
            state_detector = StateDetector(self.task)
            state_detector.set_verbose(self._verbose)
            skill_ctrl = SkillController(self.task)
            
            # 启动死亡状态并行监控
            state_detector.start_death_monitor()
            self._log("死亡状态监控线程已启动")
            
            # 自动战斗主循环
            loop_count = 0
            last_state = None
            verbose = self._verbose
            
            while True:
                loop_count += 1
                
                # 检测退出信号
                if hasattr(self.task, 'exit_is_set') and self.task.exit_is_set():
                    self._log("检测到退出信号，停止自动战斗")
                    break
                
                # 后台模式：检查并自动伪最小化
                background_manager.check_and_auto_pseudo_minimize()
                
                # 更新帧
                self.task.next_frame()
                
                # 死亡状态检测
                if state_detector.is_death_detected():
                    self._log("检测到死亡状态，等待复活...")
                    skill_ctrl.stop_auto_skills()
                    self.movement_ctrl.stop()
                    time.sleep(1)
                    continue
                
                # 自身位置检测
                self_pos = state_detector.detect_self(timeout=15)
                if self_pos is None:
                    self._log_error("15秒未检测到自身位置，停止自动战斗")
                    break
                
                # 战场状态判断
                state, allies, enemies = state_detector.get_battlefield_state_detailed()
                last_state = state.value
                
                if verbose and loop_count % 10 == 0:
                    self._log(f"循环: {loop_count}, 状态: {last_state}")
                
                # 根据战场状态处理
                if state == BattlefieldState.NO_UNITS:
                    # 无单位：随机移动搜索
                    skill_ctrl.stop_auto_skills()
                    directions = [
                        (['W'], 3), (['S'], 2), (['A'], 2), (['D'], 2),
                        (['W', 'A'], 2), (['W', 'D'], 2), (['S', 'A'], 1), (['S', 'D'], 1),
                    ]
                    weights = [w for _, w in directions]
                    keys = random.choices([d[0] for d in directions], weights=weights, k=1)[0]
                    self._log(f"随机移动: {'+'.join(keys)} 方向")
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
                        # 获取最近的敌人
                        nearest = min(targets, key=lambda e: self.distance_calc.calculate(self_pos, e))
                        distance = self.distance_calc.calculate(self_pos, nearest)
                        
                        if 100 <= distance <= 200:
                            # 距离达标，启动自动技能
                            skill_ctrl.start_auto_skills()
                            skill_ctrl.update()
                            self.movement_ctrl.stop()
                        elif distance > 200:
                            # 靠近目标
                            skill_ctrl.stop_auto_skills()
                            self.movement_ctrl.move_towards(nearest.center_x, nearest.center_y,
                                                           self_pos.center_x, self_pos.center_y)
                        else:
                            # 远离目标
                            skill_ctrl.stop_auto_skills()
                            self.movement_ctrl.move_away(nearest.center_x, nearest.center_y,
                                                        self_pos.center_x, self_pos.center_y)
                
                time.sleep(0.05)  # 主循环间隔
            
            # 清理资源
            state_detector.stop_death_monitor()
            skill_ctrl.stop_auto_skills()
            self.movement_ctrl.stop()
            self._log("自动战斗已停止")
        
        except Exception as e:
            self._log_error(f"自动战斗异常: {e}")
            import traceback
            self._log_error(traceback.format_exc())
        
        self.state_machine.transition_to(TutorialState.PHASE1_END_DETECTION)
    
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
    
    def cleanup(self):
        """清理资源"""
        self.detector.stop_phase1_end_detection()
        
        if self.movement_ctrl:
            self.movement_ctrl.stop()
        
        self._log("第一阶段资源清理完成")
