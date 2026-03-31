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
import threading
import re

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
from src.constants.features import Features


class AutoCombatTask(BaseJumpTriggerTask):
    """
    自动战斗任务
    
    作为触发任务（TriggerTask）运行，在其他任务中调用
    实现完整的自动战斗逻辑
    """
    
    # 类变量：跟踪当前是否有自动战斗正在运行
    _running_instance = None
    _running_lock = threading.Lock()
    
    # 类变量：暂停标志（用于新手教程第一阶段暂停 GUI 触发器）
    _paused_by_tutorial = False
    _paused_lock = threading.Lock()
    
    @classmethod
    def is_running(cls):
        """
        检查是否有自动战斗正在运行
        
        Returns:
            bool: True 如果有自动战斗实例正在运行
        """
        with cls._running_lock:
            return cls._running_instance is not None
    
    @classmethod
    def get_running_instance(cls):
        """
        获取当前运行的自动战斗实例
        
        Returns:
            AutoCombatTask: 当前运行的实例，无则返回 None
        """
        with cls._running_lock:
            return cls._running_instance
    
    @classmethod
    def pause_for_tutorial(cls):
        """
        暂停 GUI 自动战斗触发器（用于新手教程第一阶段）
        
        不使用 disable() 以避免触发框架异常
        """
        with cls._paused_lock:
            cls._paused_by_tutorial = True
    
    @classmethod
    def resume_from_tutorial(cls):
        """
        恢复 GUI 自动战斗触发器（新手教程第一阶段结束后）
        """
        with cls._paused_lock:
            cls._paused_by_tutorial = False
    
    @classmethod
    def is_paused_by_tutorial(cls) -> bool:
        """
        检查是否被新手教程暂停
        
        Returns:
            bool: 是否被暂停
        """
        with cls._paused_lock:
            return cls._paused_by_tutorial
    
    @classmethod
    def reset_class_state(cls):
        """
        重置所有类变量状态
        
        此方法在 CITestTask 任务开始时调用，确保多次执行时环境隔离。
        清除上次任务可能残留的状态。
        """
        # 清除运行实例
        with cls._running_lock:
            cls._running_instance = None
        
        # 清除暂停标志
        with cls._paused_lock:
            cls._paused_by_tutorial = False
        
    @classmethod
    def reset_combat_instance(cls):
        """
        重置当前运行的战斗实例
        
        如果有正在运行的自动战斗实例，强制停止并清除。
        此方法比 reset_class_state 更彻底，会停止正在进行的战斗。
        """
        with cls._running_lock:
            if cls._running_instance is not None:
                instance = cls._running_instance
                # 设置退出标志
                if hasattr(instance, '_exit_requested'):
                    instance._exit_requested = True
                # 停止战斗线程
                if hasattr(instance, '_stop_combat_thread'):
                    instance._stop_combat_thread()
                # 清除引用
                cls._running_instance = None
        
        # 清除暂停标志
        with cls._paused_lock:
            cls._paused_by_tutorial = False
    
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "AutoCombatTask"
        self.description = "自动战斗 - 智能战斗辅助"

        # 配置选项（技能开关和间隔）
        # 使用 update 方法添加配置，保留父类 TriggerTask 设置的 _enabled 键
        self.default_config.update({
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
        })
        
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
        
        # 战斗状态管理（非测试模式下使用）
        self._combat_active = False  # 当前战斗是否激活
        self._combat_thread = None  # 战斗执行线程
        self._combat_lock = threading.Lock()  # 战斗状态锁
        self._combat_check_interval = 0.5  # 战斗状态检测间隔（秒）
        
        # 卡住/抖动检测相关
        self._position_history = []  # 存储最近的位置 (x, y)
        self._position_history_max = 8  # 最多记录8个位置（抖动检测需要）
        self._last_enemy_pos = None  # 敌人最后位置 (x, y, timestamp)
    
    def run(self):
        """
        运行自动战斗任务
        
        作为触发任务，会被其他任务调用
        
        根据测试模式决定运行方式：
        - 测试模式开启：跳过场景检测，直接执行战斗循环
        - 测试模式关闭：通过YOLO自身检测动态启停战斗
        """
        # 重置退出标志（触发器实例复用时需要重置）
        self._exit_requested = False
        
        # 清空位置历史（避免残留数据影响卡住/抖动检测）
        self._position_history.clear()
        self._last_enemy_pos = None
        
        # 注册运行实例
        with self._running_lock:
            AutoCombatTask._running_instance = self
        
        self.logger.info("=" * 50)
        self.logger.info("自动战斗任务启动")
        self.logger.info("=" * 50)
        
        # 初始化后台管理器
        background_manager.update_config()
        self.logger.info(f"后台模式: {'启用' if background_manager.is_background_mode() else '禁用'}")
        
        # 检查是否为测试模式
        test_mode = self.config.get('测试模式', False)
        if test_mode:
            self.logger.warning("测试模式已启用 - 跳过场景检测，直接启动战斗")
        else:
            self.logger.info("正常模式已启用 - 通过YOLO自身检测动态启停战斗")
        
        # 更新分辨率
        self.update_resolution()
        
        if not self._resolution_logged:
            res_info = self.get_resolution_info()
            self.logger.info(f"当前分辨率: {res_info['current'][0]}x{res_info['current'][1]}, "
                            f"缩放比例: {res_info['scale_x']:.2f}x{res_info['scale_y']:.2f}")
            self._resolution_logged = True
        
        self.check_and_warn_resolution()
        
        # 初始化控制器
        self._init_controllers()
        
        # 启动死亡状态并行监控
        self.state_detector.start_death_monitor()
        self.logger.info("死亡状态监控线程已启动")
        
        if test_mode:
            # 测试模式：跳过场景检测，直接进入主循环
            self.logger.info("测试模式：跳过场景检测，直接启动战斗主循环")
            self._main_loop()
        else:
            # 正常模式：通过YOLO自身检测动态启停战斗
            self.logger.info("正常模式：启动战斗状态检测主循环")
            self._state_aware_main_loop()
        
        
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
        
        # 非测试模式：不再使用 in_game() 检测，由状态感知主循环处理
        return False
    
    def request_exit(self):
        """请求退出自动战斗"""
        self._exit_requested = True
    
    def _detect_battle_end(self):
        """
        检测战斗是否结束
        
        检测方式：
        1. 模板匹配 fight_end.png
        2. OCR 检测"对战结束"文字（简繁双语）
        
        Returns:
            bool: True 如果检测到战斗结束
        """
        # 方法1: 模板匹配
        try:
            fight_end = self.find_one(Features.TUTORIAL_FIGHT_END, threshold=0.6)
            if fight_end:
                self.logger.info(f"[战斗结束检测] 检测到战斗结束标志(模板): ({fight_end.x}, {fight_end.y})")
                return True
        except (ValueError, Exception):
            pass
        
        # 方法2: OCR检测"对战结束"（简繁双语）
        try:
            texts = self.ocr()
            if texts:
                pattern = re.compile(r"对战结束|對戰結束")
                matched = self.find_boxes(texts, match=pattern)
                if matched:
                    self.logger.info(f"[战斗结束检测] OCR匹配到结束文字: '{matched[0].name}'")
                    return True
        except Exception as e:
            self.logger.debug(f"[战斗结束检测] OCR异常: {e}")
        
        return False
    
    def _main_loop(self):
        """
        主循环 - 按照流程图执行（测试模式下使用）
        
        流程：
        1. 死亡状态检测（并行线程持续监控）
        2. 自身检测（15秒超时）
        3. 战场状态判断（4种情况）
        4. 持续更新距离给技能控制器
        """
        verbose = self.config.get('详细日志', False)
        
        # 【关键修复】测试模式下设置战斗激活状态
        # 否则 _handle_no_units() 等函数会立即退出
        with self._combat_lock:
            self._combat_active = True
        self.logger.info("测试模式：战斗激活状态已设置")
        
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
                    # 自身检测超时，可能是战斗已结束
                    self.logger.warning("15秒未检测到自身位置")
                    
                    # 检测是否战斗结束
                    if self._detect_battle_end():
                        self.logger.info("检测到战斗结束标志，正常退出自动战斗")
                        self._cleanup()
                        return
                    
                    
                    # 不是战斗结束，记录错误并退出
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
                # 检测所有敌人，只要有一个在范围内就启动技能
                if enemies:
                    distance = self._get_skill_distance(self_pos, enemies)
                    self.skill_ctrl.update_distance(distance)
                
                # 根据战场状态处理（传递已检测的单位信息）
                self._handle_battlefield_state(state, self_pos, allies, enemies)
                
            except Exception as e:
                self.logger.error(f"自动战斗异常: {e}")
                self._log_frame_info("异常发生时")
                self._cleanup()
                raise
    
    def _state_aware_main_loop(self):
        """
        状态感知主循环 - 通过YOLO自身检测动态启停战斗（非测试模式下使用）
        
        流程：
        1. 持续检测战斗状态（通过YOLO检测自身角色）
        2. 检测到自身 -> 进入战斗状态 -> 启动战斗线程
        3. 检测不到自身 -> 退出战斗状态 -> 停止战斗线程
        4. 管理状态切换时的资源清理和初始化
        """
        verbose = self.config.get('详细日志', False)
        self.logger.info("状态感知主循环已启动")
        
        while True:
            if self._should_exit():
                self.logger.info("检测到退出信号，停止状态感知主循环")
                self._stop_combat_thread()
                self._cleanup()
                return
            
            # 检查是否被新手教程暂停
            if self.is_paused_by_tutorial():
                # 被暂停时跳过战斗检测，等待恢复
                if self._combat_active:
                    self._stop_combat_thread()
                time.sleep(self._combat_check_interval)
                continue
            
            # 后台模式：检查并自动伪最小化
            background_manager.check_and_auto_pseudo_minimize()
            
            try:
                # 检测战斗状态（通过YOLO自身检测）
                in_combat, state_changed = self.state_detector.check_combat_state_by_self_detection()
                
                # 处理状态变化
                if state_changed:
                    if in_combat:
                        # 进入战斗状态
                        self.logger.info("=" * 40)
                        self.logger.info("检测到进入战斗场景，启动自动战斗...")
                        self.logger.info("=" * 40)
                        self._start_combat_thread()
                    else:
                        # 退出战斗状态
                        self.logger.info("=" * 40)
                        self.logger.info("检测到退出战斗场景，停止自动战斗...")
                        self.logger.info("=" * 40)
                        self._stop_combat_thread()
                
                # 状态日志输出
                if verbose and self._loop_count % 20 == 0:
                    self.logger.info(f"状态感知循环: 战斗状态={'战斗中' if in_combat else '非战斗'}, "
                                   f"战斗线程={'运行中' if self._combat_active else '已停止'}")
                
                self._loop_count += 1
                
                # 检测间隔
                time.sleep(self._combat_check_interval)
                
            except Exception as e:
                self.logger.error(f"状态感知主循环异常: {e}")
                self._stop_combat_thread()
                time.sleep(1)
    
    def _start_combat_thread(self):
        """
        启动战斗执行线程
        
        在独立的线程中运行战斗主循环
        """
        with self._combat_lock:
            if self._combat_active:
                self.logger.warning("战斗线程已在运行中")
                return
            
            self._combat_active = True
            self._combat_thread = threading.Thread(
                target=self._combat_loop,
                name="CombatLoopThread",
                daemon=True
            )
            self._combat_thread.start()
            self.logger.info("战斗执行线程已启动")
    
    def _stop_combat_thread(self):
        """
        停止战斗执行线程
        
        停止战斗循环并清理相关资源
        """
        # 先设置标志位（需要在锁外操作避免死锁）
        with self._combat_lock:
            if not self._combat_active:
                return
            self._combat_active = False
        
        # 停止技能和移动（在锁外操作）
        if self.skill_ctrl:
            self.skill_ctrl.stop_auto_skills()
        if self.movement_ctrl:
            self.movement_ctrl.stop()
        
        # 等待线程结束（在锁外操作，避免死锁）
        if self._combat_thread and self._combat_thread.is_alive():
            self._combat_thread.join(timeout=2.0)
        
        self.logger.info("战斗执行线程已停止")
    
    def _combat_loop(self):
        """
        战斗执行循环（在独立线程中运行）
        
        当检测到进入战斗状态时，执行此循环
        """
        verbose = self.config.get('详细日志', False)
        self.logger.info("战斗执行循环开始")
        
        # 自身位置丢失计数器（连续多次丢失才检测战斗结束）
        self_lost_count = 0
        self_lost_threshold = 10  # 连续10次检测不到自身才检测战斗结束
        
        while self._is_combat_active() and not self._should_exit():
            try:
                # 检查死亡状态
                if self.state_detector.is_death_detected():
                    self.logger.warning("战斗中检测到死亡状态，等待复活...")
                    self.skill_ctrl.stop_auto_skills()
                    self.movement_ctrl.stop()
                    time.sleep(1)
                    continue
                
                # 更新帧（确保使用最新画面）
                self.next_frame()
                
                # 检测自身位置
                self_pos = self.state_detector.detect_self_once()
                if self_pos is None:
                    self_lost_count += 1
                    
                    # 连续多次丢失，检测战斗是否结束
                    if self_lost_count >= self_lost_threshold:
                        self.logger.info(f"连续{self_lost_count}次未检测到自身位置，检测战斗是否结束...")
                        if self._detect_battle_end():
                            self.logger.info("检测到战斗结束标志，设置退出标志")
                            self._exit_requested = True
                            break
                    
                    if verbose:
                        self.logger.debug(f"战斗循环中自身位置丢失 ({self_lost_count}/{self_lost_threshold})")
                    time.sleep(0.1)
                    continue
                
                
                # 重置丢失计数器
                self_lost_count = 0
                
                # 检测战场状态
                state, allies, enemies = self.state_detector.get_battlefield_state_detailed()
                self._last_state = state.value
                
                # 更新距离（检测所有敌人）
                if enemies:
                    distance = self._get_skill_distance(self_pos, enemies)
                    self.skill_ctrl.update_distance(distance)
                    # 记录敌人最后位置
                    nearest_enemy = self._get_nearest_target(self_pos, enemies)
                    if nearest_enemy:
                        self._last_enemy_pos = (nearest_enemy.center_x, nearest_enemy.center_y, time.time())
                
                
                # 【卡住/抖动检测】只有在没有敌人在技能范围内时才执行
                has_enemy_in_range = False
                if enemies:
                    distance = self._get_skill_distance(self_pos, enemies)
                    if distance <= 225:  # 技能范围 0-225px
                        has_enemy_in_range = True
                
                if not has_enemy_in_range:
                    # 执行卡住/抖动检测
                    if self._handle_stuck_or_jitter(self_pos):
                        # 执行了摆脱操作，继续下一次循环
                        time.sleep(0.1)
                        continue
                
                
                # 处理战场状态
                self._handle_battlefield_state(state, self_pos, allies, enemies)
                
                # 短暂休眠
                time.sleep(0.05)
                
            except Exception as e:
                self.logger.error(f"战斗执行循环异常: {e}")
                time.sleep(0.1)
        
        self.logger.info("战斗执行循环结束")
    
    def _is_combat_active(self):
        """
        线程安全地检查战斗是否激活
        
        Returns:
            bool: 战斗是否激活
        """
        with self._combat_lock:
            return self._combat_active
    
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
    
    def _get_skill_distance(self, self_pos, enemies):
        """
        获取技能释放距离（检测所有敌人）
        
        逻辑：
        1. 如果有任何一个敌人在技能范围内(0-225px)，返回该距离（优先）
        2. 否则返回最近敌人的距离
        
        Args:
            self_pos: 自身位置
            enemies: 敌人列表
            
        Returns:
            float: 用于技能控制的距离
        """
        if not enemies or self_pos is None:
            return float('inf')
        
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
            return in_range_distance
        return nearest_distance
    
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
            
            # 检查战斗是否仍在激活状态
            if not self._is_combat_active():
                self.logger.info("战斗已停止，退出随机移动搜索")
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
        
        向友方移动，保持距离0~225像素
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
            
            # 检查战斗是否仍在激活状态
            if not self._is_combat_active():
                self.logger.info("战斗已停止，退出友方跟随模式")
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
            
        向敌军移动，保持距离0~225像素
        技能释放由独立线程根据距离自动处理
        
        优化：
        - 移动过程中实时检测距离
        - 一旦距离进入0-225px范围，立即中断移动
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
            
            # 检查战斗是否仍在激活状态
            if not self._is_combat_active():
                self.logger.info("战斗已停止，退出敌军追踪模式")
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
                        """检测是否应该停止移动（距离进入0-225px范围）"""
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
                                
                                # 如果距离进入0-225px范围，停止移动
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
            self.logger.debug(f"距离{self.distance_calc.calculate(self_pos, target):.0f}px > 225px，靠近目标")
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
        
        优先向敌军移动，保持距离0~225像素
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
        统一距离逻辑：保持0~225像素距离
        
        1. 距离在0~225像素之间 → 停止移动，保持位置
        2. 距离 < 0像素 → 反向移动，远离目标（理论上不会发生）
        3. 距离 > 225像素 → 正向移动，靠近目标
        
        Args:
            self_pos: 自身位置
            target: 目标位置
        """
        distance = self.distance_calc.calculate(self_pos, target)
        direction = self.distance_calc.get_movement_direction(self_pos, target, distance)
        
        if direction == "towards":
            self.logger.info(f"➡️ 距离{distance:.0f}px > 225px，靠近目标")
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
    
    def _record_position(self, x: float, y: float):
        """
        记录位置历史，用于卡住/抖动检测
        
        Args:
            x, y: 自身位置坐标
        """
        self._position_history.append((x, y))
        if len(self._position_history) > self._position_history_max:
            self._position_history.pop(0)
    
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
        
        # 获取最近4个位置
        recent_positions = self._position_history[-STUCK_COUNT:]
        
        # 计算这4个位置的平均中心点
        avg_x = sum(p[0] for p in recent_positions) / STUCK_COUNT
        avg_y = sum(p[1] for p in recent_positions) / STUCK_COUNT
        
        # 检查所有位置是否都在阈值范围内
        all_same = all(
            ((p[0] - avg_x) ** 2 + (p[1] - avg_y) ** 2) ** 0.5 < STUCK_THRESHOLD
            for p in recent_positions
        )
        
        if all_same:
            positions_str = " -> ".join([f"({x:.0f},{y:.0f})" for x, y in recent_positions])
            self.logger.info(f"【卡住检测】连续{STUCK_COUNT}次相同坐标: {positions_str}")
        
        return all_same
    
    def _detect_jitter(self) -> bool:
        """
        检测是否存在A-B-A-B抖动模式
        
        将历史位置分为偶数组和奇数组：
        - 偶数位置 (0,2,4,6) 形成A区域
        - 奇数位置 (1,3,5,7) 形成B区域
        
        如果A区域聚类、B区域聚类，且两个区域中心距离较远，判定为抖动
        
        Returns:
            bool: 如果检测到抖动返回 True
        """
        JITTER_THRESHOLD = 15  # 聚类阈值：15像素内视为聚类
        AREA_THRESHOLD = 30  # 区域阈值：两个区域中心距离超过30像素才算抖动
        MIN_HISTORY = 6  # 至少需要6个位置
        
        if len(self._position_history) < MIN_HISTORY:
            return False
        
        # 分离偶数位置和奇数位置
        even_positions = [self._position_history[i] for i in range(0, len(self._position_history), 2)]
        odd_positions = [self._position_history[i] for i in range(1, len(self._position_history), 2)]
        
        if len(even_positions) < 2 or len(odd_positions) < 2:
            return False
        
        # 计算偶数位置中心（A区域）
        even_center_x = sum(p[0] for p in even_positions) / len(even_positions)
        even_center_y = sum(p[1] for p in even_positions) / len(even_positions)
        
        # 计算奇数位置中心（B区域）
        odd_center_x = sum(p[0] for p in odd_positions) / len(odd_positions)
        odd_center_y = sum(p[1] for p in odd_positions) / len(odd_positions)
        
        # 检查偶数位置是否聚类（都在中心附近）
        even_clustered = all(
            ((p[0] - even_center_x) ** 2 + (p[1] - even_center_y) ** 2) ** 0.5 < JITTER_THRESHOLD
            for p in even_positions
        )
        
        # 检查奇数位置是否聚类（都在中心附近）
        odd_clustered = all(
            ((p[0] - odd_center_x) ** 2 + (p[1] - odd_center_y) ** 2) ** 0.5 < JITTER_THRESHOLD
            for p in odd_positions
        )
        
        # 检查A区域和B区域是否不同（有足够的距离）
        distance_between_areas = ((even_center_x - odd_center_x) ** 2 + (even_center_y - odd_center_y) ** 2) ** 0.5
        areas_are_different = distance_between_areas > AREA_THRESHOLD
        
        # 只有当偶数位置聚类、奇数位置聚类，且两个区域不同时，才判定为抖动
        is_jitter = even_clustered and odd_clustered and areas_are_different
        if is_jitter:
            self.logger.info(f"【抖动检测】✓ 检测到抖动! A区域({even_center_x:.0f},{even_center_y:.0f}), B区域({odd_center_x:.0f},{odd_center_y:.0f}), 距离{distance_between_areas:.0f}px")
        
        return is_jitter
    
    def _perform_random_move(self):
        """
        执行随机移动，用于摆脱卡住或抖动
        """
        random.seed()  # 重置随机种子确保每次都是真正随机
        
        # 随机选择一个方向移动2秒
        directions = [
            (['W'], 3), (['S'], 2), (['A'], 2), (['D'], 2),
            (['W', 'A'], 2), (['W', 'D'], 2), (['S', 'A'], 1), (['S', 'D'], 1),
        ]
        weights = [w for _, w in directions]
        keys = random.choices([d[0] for d in directions], weights=weights, k=1)[0]
        
        self.logger.info(f"【随机移动】方向: {'+'.join(keys)}, 持续2秒 (权重随机)")
        self.movement_ctrl._press_movement_keys_for_duration(keys, 2.0)
    
    def _handle_stuck_or_jitter(self, self_pos):
        """
        处理卡住或抖动情况
        
        Args:
            self_pos: 当前自身位置
            
        Returns:
            bool: 如果执行了摆脱操作返回 True
        """
        # 记录当前位置
        self._record_position(self_pos.center_x, self_pos.center_y)
        
        # 卡住检测
        is_stuck = self._detect_stuck()
        if is_stuck:
            self.logger.info("【卡住检测】角色可能被卡住，向下移动1秒")
            self.movement_ctrl._press_movement_keys_for_duration(['S'], 1.0)
            self._position_history.clear()
            return True
        
        # 抖动检测
        is_jitter = self._detect_jitter()
        if is_jitter:
            self._perform_random_move()
            self._position_history.clear()
            return True
        
        return False
    
    
    def _cleanup(self):
        """清理资源"""
        # 清除运行实例
        with self._running_lock:
            if AutoCombatTask._running_instance is self:
                AutoCombatTask._running_instance = None
        
        # 停止战斗线程（非测试模式下）
        self._stop_combat_thread()
        
        # 重置战斗状态
        if self.state_detector:
            self.state_detector.reset_combat_state()
        
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

