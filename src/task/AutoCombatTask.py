"""
自动战斗任务

根据流程图实现完整的自动战斗逻辑：
1. 死亡状态检测（并行后台线程）
2. 自身检测（15秒超时）
3. 战场状态判断（4种情况）
4. 自动技能释放（距离达标时）

特性：
- 并行死亡检测：独立线程持续监控，响应迅速
- GUI配置驱动：技能开关和按键严格遵循用户设置
- 伪后台支持：游戏窗口可最小化时继续运行
"""

import time
import random

from ok import og

from src.task.BaseJumpTriggerTask import BaseJumpTriggerTask
from src.combat import (
    StateDetector,
    BattlefieldState,
    MovementController,
    SkillController,
    DistanceCalculator,
)
from src.utils import background_manager


class AutoCombatTask(BaseJumpTriggerTask):
    """
    自动战斗任务
    
    作为触发任务（TriggerTask）运行，在其他任务中调用
    实现完整的自动战斗逻辑
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "AutoCombatTask"
        self.description = "自动战斗 - 智能战斗辅助"
        
        # 配置选项（技能开关和间隔）
        self.default_config = {
            '测试模式': False,  # 测试模式：跳过场景检测，直接启动战斗
            '详细日志': True,   # 输出详细的调试日志
            '自动普攻': True,
            '自动技能1': True,
            '自动技能2': True,
            '自动大招': True,
            '普攻间隔(秒)': 0.5,
            '技能1间隔(秒)': 2.0,
            '技能2间隔(秒)': 3.0,
            '大招间隔(秒)': 5.0,
            '移动持续时间(秒)': 0.5,  # 每次移动按键持续的时间
        }
        
        self.config_description = {
            '测试模式': '启用后跳过场景检测，直接启动战斗逻辑（用于调试）',
            '详细日志': '启用后输出YOLO检测结果、位置、距离等详细信息',
            '自动普攻': '启用后自动释放普通攻击',
            '自动技能1': '启用后自动释放技能1',
            '自动技能2': '启用后自动释放技能2',
            '自动大招': '启用后自动释放大招',
            '移动持续时间(秒)': '每次移动按键的持续时间，值越大移动距离越长',
        }
        
        # 日志计数器（用于定期输出状态摘要）
        self._loop_count = 0
        self._last_state = None
        
        # 控制器（延迟初始化）
        self.state_detector = None
        self.movement_ctrl = None
        self.skill_ctrl = None
        self.distance_calc = None
        
        # 内部状态
        self._resolution_logged = False
        self._exit_requested = False
    
    def run(self):
        """
        运行自动战斗任务
        
        作为触发任务，会被其他任务调用
        """
        self.logger.info("=" * 50)
        self.logger.info("自动战斗任务启动")
        self.logger.info("=" * 50)
        
        # 初始化后台管理器
        background_manager.update_config()
        self.logger.info(f"后台模式: {'启用' if background_manager.is_background_mode() else '禁用'}")
        
        # 检查是否为测试模式（使用 self.config 获取用户实际设置的值）
        test_mode = self.config.get('测试模式', False)
        if test_mode:
            self.logger.warning("测试模式已启用 - 跳过场景检测")
        
        # 更新分辨率
        self.update_resolution()
        
        if not self._resolution_logged:
            res_info = self.get_resolution_info()
            self.logger.info(f"当前分辨率: {res_info['current'][0]}x{res_info['current'][1]}, "
                            f"缩放比例: {res_info['scale_x']:.2f}x{res_info['scale_y']:.2f}")
            self._resolution_logged = True
        
        self.check_and_warn_resolution()
        
        # 等待进入游戏（测试模式下跳过）
        if not test_mode:
            self.logger.info("等待进入游戏...")
            if not self._wait_for_game():
                self.logger.error("未能进入游戏场景")
                return False
        else:
            self.logger.info("测试模式：跳过等待游戏场景")
        
        # 初始化控制器
        self._init_controllers()
        
        # 启动死亡状态并行监控
        self.state_detector.start_death_monitor()
        self.logger.info("死亡状态监控线程已启动")
        
        # 开始主循环
        self.logger.info("开始自动战斗主循环")
        self._main_loop()
        
        return True
    
    def _init_controllers(self):
        """初始化所有控制器"""
        self.state_detector = StateDetector(self)
        
        # 从配置中读取移动时间
        move_duration = self.config.get('移动持续时间(秒)', 0.5)
        self.movement_ctrl = MovementController(self, move_duration=move_duration)
        
        self.skill_ctrl = SkillController(self)  # 不再传递 default_config
        self.distance_calc = DistanceCalculator()
        
        # 传递详细日志开关给检测器
        verbose = self.config.get('详细日志', False)
        self.state_detector.set_verbose(verbose)
        
        if verbose:
            self.logger.info("详细日志已启用")
            
            # 输出当前技能配置
            skill_status = self.skill_ctrl.get_skill_status()
            self.logger.info("当前技能配置:")
            for skill_name, status in skill_status.items():
                self.logger.info(f"  {skill_name}: 启用={status['启用']}, "
                               f"按键={status['按键']}, 间隔={status['间隔']}秒")
    
    def _verbose_log(self, message):
        """输出详细日志（仅在详细日志开启时）"""
        if self.config.get('详细日志', False):
            self.logger.info(f"[详细] {message}")
    
    def _wait_for_game(self, timeout=30):
        """等待进入游戏"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._should_exit():
                return False
            if self.in_game():
                return True
            time.sleep(0.5)
        return False
    
    def _should_exit(self):
        """检测是否应该退出自动战斗"""
        # 检测退出请求
        if self._exit_requested:
            return True
        
        # 测试模式下不检测场景（只响应退出请求）
        if self.config.get('测试模式', False):
            return False
        
        # 检测是否还在游戏中
        if not self.in_game():
            return True
        
        return False
    
    def request_exit(self):
        """请求退出自动战斗"""
        self._exit_requested = True
    
    def _main_loop(self):
        """
        主循环 - 按照流程图执行
        
        流程：
        1. 死亡状态检测（并行线程持续监控）
        2. 自身检测（15秒超时）
        3. 战场状态判断（4种情况）
        4. 持续更新距离给技能控制器
        """
        verbose = self.config.get('详细日志', False)
        
        while True:
            self._loop_count += 1
            
            # 检测退出信号
            if self._should_exit():
                self.logger.info("检测到退出自动战斗信号，正常终止")
                self._cleanup()
                return
            
            # 后台模式：检查并自动伪最小化
            background_manager.check_and_auto_pseudo_minimize()
            
            try:
                # 每10次循环输出一次状态摘要
                if verbose and self._loop_count % 10 == 0:
                    self.logger.info(f"循环计数: {self._loop_count}, 当前状态: {self._last_state}")
                
                # ======== 第一步：死亡状态检测（并行线程，快速查询）========
                if self.state_detector.is_death_detected():
                    self.logger.warning("检测到死亡状态，等待复活...")
                    # 死亡状态下停止技能，继续循环检测
                    self.skill_ctrl.stop_auto_skills()
                    self.movement_ctrl.stop()
                    time.sleep(1)
                    continue
                
                # ======== 第二步：自身检测（15秒超时）========
                if verbose:
                    self.logger.info(f"步骤2: 自身位置检测开始...")
                    
                self_pos = self.state_detector.detect_self(timeout=15)
                
                if self_pos is None:
                    self.logger.error("15秒未检测到自身位置，终止脚本")
                    self._log_frame_info("自身检测失败")
                    raise Exception("自身检测超时 - 15秒内未找到自己")
                
                if verbose:
                    self.logger.info(f"步骤2完成: 自身位置=({self_pos.center_x}, {self_pos.center_y}), "
                                    f"置信度={self_pos.confidence:.2f}, "
                                    f"框=({self_pos.x}, {self_pos.y}, {self_pos.width}x{self_pos.height})")
                
                # ======== 第三步：战场状态判断 ========
                if verbose:
                    self.logger.info(f"步骤3: 战场状态检测...")
                
                state, allies, enemies = self.state_detector.get_battlefield_state_detailed()
                self._last_state = state.value
                
                if verbose:
                    self._log_battlefield_details(state, self_pos, allies, enemies)
                
                # ======== 第四步：更新距离给技能控制器 ========
                if enemies:
                    nearest_enemy = self._get_nearest_target(self_pos, enemies)
                    if nearest_enemy:
                        distance = self.distance_calc.calculate(self_pos, nearest_enemy)
                        self.skill_ctrl.update_distance(distance)
                
                # 根据战场状态处理（传递已检测的单位信息）
                self._handle_battlefield_state(state, self_pos, allies, enemies)
                
                # 不需要额外休息，让移动更平滑
                # time.sleep(0.02)
                
            except Exception as e:
                self.logger.error(f"自动战斗异常: {e}")
                self._log_frame_info("异常发生时")
                self._cleanup()
                raise
    
    def _log_frame_info(self, context=""):
        """记录当前帧信息"""
        frame = self.frame
        if frame is not None:
            h, w = frame.shape[:2]
            self.logger.info(f"📷 帧信息[{context}]: 尺寸={w}x{h}")
        else:
            self.logger.warning(f"📷 帧信息[{context}]: 无法获取帧（frame=None）")
    
    def _log_battlefield_details(self, state, self_pos, allies, enemies):
        """记录战场详细信息"""
        self.logger.info(f"战场状态: {state.value}")
        self.logger.info(f"   自己: ({self_pos.center_x}, {self_pos.center_y})")
        
        if allies:
            for i, ally in enumerate(allies):
                dist = self.distance_calc.calculate(self_pos, ally)
                self.logger.info(f"   友方{i+1}: ({ally.center_x}, {ally.center_y}), "
                               f"置信度={ally.confidence:.2f}, 距离={dist:.0f}px")
        else:
            self.logger.info(f"   友方: 无")
        
        if enemies:
            for i, enemy in enumerate(enemies):
                dist = self.distance_calc.calculate(self_pos, enemy)
                self.logger.info(f"   敌军{i+1}: ({enemy.center_x}, {enemy.center_y}), "
                               f"置信度={enemy.confidence:.2f}, 距离={dist:.0f}px")
        else:
            self.logger.info(f"   敌军: 无")
    
    def _handle_battlefield_state(self, state, self_pos, allies, enemies):
        """
        处理战场状态 - 4种情况
        
        Args:
            state: 战场状态
            self_pos: 自身位置
            allies: 已检测的友方列表
            enemies: 已检测的敌方列表
        """
        # 关键：有敌人时启动技能，无敌人时停止技能
        if enemies:
            self.skill_ctrl.start_auto_skills()
        else:
            self.skill_ctrl.stop_auto_skills()
        
        if state == BattlefieldState.NO_UNITS:
            self._handle_no_units()
        elif state == BattlefieldState.ALLIES_ONLY:
            self._handle_allies_only(self_pos, allies)
        elif state == BattlefieldState.ENEMIES_ONLY:
            self._handle_enemies_only(self_pos, enemies)
        else:  # MIXED
            self._handle_mixed(self_pos, allies, enemies)
    
    def _get_nearest_target(self, self_pos, targets):
        """
        从目标列表中获取最近的目标
        
        Args:
            self_pos: 自身位置
            targets: 目标列表
            
        Returns:
            最近的目标，无则返回 None
        """
        if not targets or self_pos is None:
            return None
        
        nearest = None
        min_distance = float('inf')
        
        for target in targets:
            distance = self.distance_calc.calculate(self_pos, target)
            if distance < min_distance:
                min_distance = distance
                nearest = target
        
        return nearest
    
    def _handle_no_units(self):
        """
        情况1：无友方、无敌军
        
        执行8方向随机移动，向上权重略高
        每次随机移动持续3秒后重新检测
        """
        self.logger.info("场上无单位，开始随机移动搜索...")
        
        # 强制关闭自动技能
        self.skill_ctrl.stop_auto_skills()
        
        # 8个方向：上、下、左、右、左上、右上、左下、右下
        # 权重：向上方向权重更高
        directions = [
            ('W', 3),      # 上 - 权重3
            ('S', 2),      # 下 - 权重2
            ('A', 2),      # 左 - 权重2
            ('D', 2),      # 右 - 权重2
            ('W+A', 2),    # 左上 - 权重2
            ('W+D', 2),    # 右上 - 权重2
            ('S+A', 1),    # 左下 - 权重1
            ('S+D', 1),    # 右下 - 权重1
        ]
        
        # 持续随机移动，直到检测到单位
        max_search_time = 30  # 最长搜索30秒
        start_time = time.time()
        move_duration = 3.0   # 每次移动持续3秒
        
        while time.time() - start_time < max_search_time:
            if self._should_exit():
                return
            
            # 更新帧
            self.next_frame()
            
            # 检测是否出现单位
            state = self.state_detector.get_battlefield_state()
            if state != BattlefieldState.NO_UNITS:
                self.logger.info("检测到单位，返回主循环")
                return
            
            # 检测死亡状态
            if self.state_detector.is_death_detected():
                self.logger.warning("检测到死亡状态")
                return
            
            # 加权随机选择方向
            weights = [w for _, w in directions]
            direction_keys = random.choices(
                [d[0] for d in directions],
                weights=weights,
                k=1
            )[0]
            
            # 解析按键组合
            keys = direction_keys.split('+')
            key_str = '+'.join(keys)
            
            self.logger.info(f"随机移动: {key_str} 方向，持续 {move_duration}秒")
            
            # 执行移动
            self.movement_ctrl._press_movement_keys_for_duration(keys, move_duration)
        
        # 超时后仍未找到单位
        self.logger.error(f"随机移动搜索{max_search_time}秒后仍无单位，终止脚本")
        raise Exception("无单位搜索超时 - 30秒内未找到任何单位")
    
    def _handle_allies_only(self, self_pos, allies):
        """
        情况2：仅有友方、无敌军
        
        向友方移动，保持距离0~250像素
        强制关闭自动技能
        
        Args:
            self_pos: 自身位置（初始检测）
            allies: 已检测的友方列表（初始检测）
        """
        self.logger.debug("场上仅有友方，跟随友方移动...")
        
        # 强制关闭自动技能（无敌人时不放技能）
        self.skill_ctrl.stop_auto_skills()
        
        # 获取最近的友方（使用初始检测的数据）
        target = self._get_nearest_target(self_pos, allies)
        if not target:
            return
        
        # 持续跟随友方，直到发现敌人或超时（最多3秒）
        max_follow_time = 3.0
        start_time = time.time()
        
        while time.time() - start_time < max_follow_time:
            # 检查退出信号
            if self._should_exit():
                return
            
            # 更新帧（获取最新画面）
            self.next_frame()
            
            # 检查死亡状态
            if self.state_detector.is_death_detected():
                self.movement_ctrl.stop()
                return
            
            # 检查是否出现敌人
            enemies = self.state_detector.detect_enemies()
            if enemies:
                self.logger.info("发现敌人，退出友方跟随模式")
                return
            
            # 重新检测自身位置
            current_self = self.state_detector.detect_self_once()
            if current_self is None:
                current_self = self_pos
            
            # 重新检测友方位置
            current_allies = self.state_detector.detect_allies()
            if current_allies:
                target = self._get_nearest_target(current_self, current_allies)
            
            if not target:
                return
            
            # 计算当前距离并调整
            distance = self.distance_calc.calculate(current_self, target)
            self.logger.info(f"最近友方距离: {distance:.0f}px，调整位置")
            
            direction = self.distance_calc.get_movement_direction(current_self, target, distance)
            
            if direction == "towards":
                self.movement_ctrl.move_towards(
                    target.center_x, target.center_y,
                    current_self.center_x, current_self.center_y
                )
            elif direction == "away":
                self.movement_ctrl.move_away(
                    target.center_x, target.center_y,
                    current_self.center_x, current_self.center_y
                )
            else:
                self.movement_ctrl.stop()
                return  # 距离达标，退出
    
    def _handle_enemies_only(self, self_pos, enemies):
        """
        情况3：仅有敌军、无友方
            
        向敌军移动，保持距离0~250像素
        技能释放由独立线程根据距离自动处理
        
        优化：
        - 移动过程中实时检测距离
        - 一旦距离进入0-250px范围，立即中断移动
        - 移动过程中持续更新帧和距离给技能控制器
            
        目标锁定机制：
        - 选择最近的敌人作为目标后锁定
        - 只跟踪锁定目标的位置更新
        - 只有目标丢失时才重新选择
            
        Args:
            self_pos: 自身位置（初始检测）
            enemies: 已检测的敌方列表（初始检测）
        """
        self.logger.debug("场上仅有敌军，向敌军移动...")
            
        # 获取最近的敌人并锁定目标
        target = self._get_nearest_target(self_pos, enemies)
        if not target:
            self.logger.warning("敌军列表为空，无法获取目标")
            return
        
        # 注意：技能已在 _handle_battlefield_state 中启动
            
        # 锁定目标：记录目标的大致位置区域，用于后续识别同一目标
        locked_target_center = (target.center_x, target.center_y)
        self.logger.info(f"锁定目标: 位置({target.center_x:.0f}, {target.center_y:.0f})")
            
        # 重置距离计算器的滞后状态（新目标）
        self.distance_calc.reset_state()
        
        # 目标丢失计数器（连续多次丢失才重新锁定）
        target_lost_count = 0
        max_lost_count = 3  # 连续3次丢失才重新锁定
            
        # 持续调整距离，直到达标或超时（最多5秒）
        max_adjust_time = 5.0
        start_time = time.time()
            
        while time.time() - start_time < max_adjust_time:
            # 检查退出信号
            if self._should_exit():
                return
                
            # 更新帧（获取最新画面）
            self.next_frame()
                
            # 检查死亡状态
            if self.state_detector.is_death_detected():
                self.logger.warning("检测到死亡状态，停止移动")
                self.movement_ctrl.stop()
                return
                
            # 重新检测自身位置
            current_self = self.state_detector.detect_self_once()
            if current_self is None:
                self.logger.warning("无法检测到自身位置，使用上一次位置")
                current_self = self_pos
                
            # 重新检测敌人位置，但只跟踪锁定目标
            current_enemies = self.state_detector.detect_enemies()
            if current_enemies:
                # 尝试找到锁定的目标（位置最接近的目标）
                best_match = None
                min_offset = float('inf')
                    
                for enemy in current_enemies:
                    offset = abs(enemy.center_x - locked_target_center[0]) + abs(enemy.center_y - locked_target_center[1])
                    if offset < min_offset:
                        min_offset = offset
                        best_match = enemy
                    
                # 如果找到匹配目标（允许一定偏移，增加到200像素）
                if best_match and min_offset < 200:
                    target = best_match
                    locked_target_center = (target.center_x, target.center_y)  # 更新锁定位置
                    target_lost_count = 0  # 重置丢失计数
                else:
                    # 目标丢失，增加计数
                    target_lost_count += 1
                    self.logger.debug(f"目标丢失计数: {target_lost_count}/{max_lost_count}")
                    
                    if target_lost_count >= max_lost_count:
                        # 连续多次丢失，重新选择最近的敌人
                        new_target = self._get_nearest_target(current_self, current_enemies)
                        if new_target:
                            self.logger.info(f"目标丢失，重新锁定: ({new_target.center_x:.0f}, {new_target.center_y:.0f})")
                            target = new_target
                            locked_target_center = (target.center_x, target.center_y)
                            target_lost_count = 0
                            # 重置距离计算器的滞后状态
                            self.distance_calc.reset_state()
                    else:
                        # 使用上一次的目标位置继续
                        pass
                
            if not target:
                self.logger.warning("无法检测到敌人，退出距离调整")
                return
                
            # 计算当前距离
            distance = self.distance_calc.calculate(current_self, target)
            
            # 更新距离给技能控制器（独立线程会根据距离判断是否释放技能）
            self.skill_ctrl.update_distance(distance)
                
            if self.distance_calc.is_in_optimal_range(distance):
                # 距离达标，停止移动，技能由独立线程处理
                self.logger.info(f"距离达标({distance:.0f}px)，保持位置，技能持续释放")
                self.movement_ctrl.stop()
                return
            else:
                # 距离不达标，执行移动
                direction = self.distance_calc.get_movement_direction(current_self, target, distance)
                keys = self._calculate_movement_keys(current_self, target, direction)
                    
                if keys:
                    # 使用可中断移动，在移动过程中实时检测距离
                    def should_stop_moving():
                        """检测是否应该停止移动（距离进入0-250px范围）"""
                        # 更新帧
                        self.next_frame()
                        
                        # 重新检测自身和敌人
                        new_self = self.state_detector.detect_self_once()
                        new_enemies = self.state_detector.detect_enemies()
                        
                        if new_self and new_enemies:
                            new_target = self._get_nearest_target(new_self, new_enemies)
                            if new_target:
                                new_distance = self.distance_calc.calculate(new_self, new_target)
                                # 更新距离给技能控制器
                                self.skill_ctrl.update_distance(new_distance)
                                
                                # 如果距离进入0-250px范围，停止移动
                                if self.distance_calc.is_in_optimal_range(new_distance):
                                    self.logger.info(f"[移动中断] 距离达标({new_distance:.0f}px)")
                                    return True
                        return False
                    
                    # 执行可中断移动
                    interrupted = self.movement_ctrl.move_with_interrupt_check(keys, should_stop_moving)
                    
                    if interrupted:
                        # 移动被中断，说明距离已达标
                        self.movement_ctrl.stop()
                        return
                    
        # 超时后仍未达标，记录警告
        self.logger.warning(f"距离调整超时({max_adjust_time}秒)，当前距离: {distance:.0f}px")
    
    def _calculate_movement_keys(self, self_pos, target, direction):
        """
        计算移动按键
        
        Args:
            self_pos: 自身位置
            target: 目标位置
            direction: 移动方向 ("towards" 或 "away")
            
        Returns:
            list: 需要按下的键列表
        """
        import math
        
        if direction == "towards":
            dx = target.center_x - self_pos.center_x
            dy = target.center_y - self_pos.center_y
            self.logger.debug(f"距离{self.distance_calc.calculate(self_pos, target):.0f}px > 250px，靠近目标")
        elif direction == "away":
            dx = self_pos.center_x - target.center_x
            dy = self_pos.center_y - target.center_y
            self.logger.debug(f"距离{self.distance_calc.calculate(self_pos, target):.0f}px < 0px，远离目标")
        else:
            return []
        
        keys = []
        THRESHOLD = 30
        
        if abs(dx) >= THRESHOLD:
            keys.append('D' if dx > 0 else 'A')
        if abs(dy) >= THRESHOLD:
            keys.append('S' if dy > 0 else 'W')
        
        return keys
    
    def _handle_mixed(self, self_pos, allies, enemies):
        """
        情况4：友方+敌军都存在
        
        优先向敌军移动，保持距离0~250像素
        距离达标后 → 自动技能持续释放
        
        Args:
            self_pos: 自身位置
            allies: 已检测的友方列表
            enemies: 已检测的敌方列表
        """
        self.logger.debug("场上有友方和敌军，优先攻击敌军...")
        
        # 与 _handle_enemies_only 逻辑相同
        self._handle_enemies_only(self_pos, enemies)
    
    def _maintain_distance(self, self_pos, target):
        """
        统一距离逻辑：保持0~250像素距离
        
        1. 距离在0~250像素之间 → 停止移动，保持位置
        2. 距离 < 0像素 → 反向移动，远离目标（理论上不会发生）
        3. 距离 > 250像素 → 正向移动，靠近目标
        
        Args:
            self_pos: 自身位置
            target: 目标位置
        """
        distance = self.distance_calc.calculate(self_pos, target)
        direction = self.distance_calc.get_movement_direction(self_pos, target, distance)
        
        if direction == "towards":
            self.logger.info(f"➡️ 距离{distance:.0f}px > 250px，靠近目标")
            self.movement_ctrl.move_towards(
                target.center_x, target.center_y,
                self_pos.center_x, self_pos.center_y
            )
        elif direction == "away":
            self.logger.info(f"⬅️ 距离{distance:.0f}px < 0px，远离目标")
            self.movement_ctrl.move_away(
                target.center_x, target.center_y,
                self_pos.center_x, self_pos.center_y
            )
        else:
            self.logger.info(f"⏹️ 距离{distance:.0f}px 在最佳范围内，停止移动")
            self.movement_ctrl.stop()
    
    def _cleanup(self):
        """清理资源"""
        # 停止死亡监控线程
        if self.state_detector:
            self.state_detector.stop_death_monitor()
        
        # 停止移动
        if self.movement_ctrl:
            self.movement_ctrl.stop()
        
        # 关闭技能控制器（停止独立线程）
        if self.skill_ctrl:
            self.skill_ctrl.shutdown()
        
        self.logger.info("自动战斗任务清理完成")

