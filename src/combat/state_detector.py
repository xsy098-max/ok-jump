"""
战斗状态检测器

使用 YOLO 模型或 Unity TCP 命令检测战场单位和状态
"""

import time
import threading
from enum import Enum

from ok import og

from src.combat.labels import CombatLabel


class UnityDetectionResult:
    """
    Unity 工程连接检测结果

    镜像 YOLO DetectionResult 的接口，用于兼容现有战斗系统
    """

    def __init__(self, center_x, center_y, class_id, confidence=1.0):
        self.center_x = center_x
        self.center_y = center_y
        self.class_id = class_id
        self.confidence = confidence
        self.x = center_x
        self.y = center_y
        self.width = 0
        self.height = 0

    @property
    def center(self):
        return (self.center_x, self.center_y)

    @property
    def box(self):
        return (self.x, self.y, self.width, self.height)

    @property
    def xyxy(self):
        return (self.x, self.y, self.x + self.width, self.y + self.height)


class BattlefieldState(Enum):
    """战场状态枚举"""
    NO_UNITS = "no_units"           # 无友方、无敌军
    ALLIES_ONLY = "allies_only"     # 仅有友方
    ENEMIES_ONLY = "enemies_only"   # 仅有敌军
    MIXED = "mixed"                 # 友方+敌军均存在


class StateDetector:
    """
    战斗状态检测器
    
    使用 YOLO 模型检测：
    - 死亡状态（支持后台线程持续检测）
    - 自身位置
    - 友方单位
    - 敌方单位
    - 战斗状态（通过自身角色检测判断是否在战斗中）
    """
    
    def __init__(self, task):
        """
        初始化检测器
        
        Args:
            task: 关联的任务对象（用于获取截图帧）
        """
        self.task = task
        self._verbose = False
        self._detection_count = 0
        
        # 死亡状态并行检测相关
        self._death_detected = False
        self._death_monitor_running = False
        self._death_monitor_thread = None
        self._death_lock = threading.Lock()
        self._death_check_interval = 0.03  # 30ms检测一次，更快响应状态变化
        
        # 战斗状态检测相关（通过YOLO自身检测判断）
        self._in_combat_state = False
        self._combat_state_lock = threading.Lock()
        
        # 战斗状态切换的防抖动机制
        self._consecutive_self_found = 0  # 连续检测到自身的次数
        self._consecutive_self_not_found = 0  # 连续未检测到自身的次数
        self._self_found_threshold = 2  # 连续2次检测到自身才确认进入战斗
        self._self_not_found_threshold = 3  # 连续3次未检测到自身才确认退出战斗
    
    def set_verbose(self, verbose):
        """设置是否输出详细日志"""
        self._verbose = verbose
    
    def _log(self, message):
        """输出日志（仅在详细模式下）"""
        if self._verbose and hasattr(self.task, 'logger'):
            self.task.logger.info(f"[检测器] {message}")
    
    def _get_frame(self):
        """获取当前帧"""
        return self.task.frame
    
    def _should_exit(self):
        """检查是否应该退出"""
        return hasattr(self.task, '_should_exit') and self.task._should_exit()
    
    # ==================== 并行死亡检测 ====================
    
    def start_death_monitor(self):
        """
        启动死亡状态后台监控线程
        
        在独立线程中持续检测死亡状态，主线程可通过 is_death_detected() 快速查询
        """
        with self._death_lock:
            if self._death_monitor_running:
                self._log("死亡监控线程已在运行")
                return
        
        self._death_detected = False
        self._death_monitor_running = True
        self._death_monitor_thread = threading.Thread(
            target=self._death_monitor_loop,
            name="DeathMonitorThread",
            daemon=True
        )
        self._death_monitor_thread.start()
        self._log("死亡监控线程已启动")
    
    def stop_death_monitor(self):
        """停止死亡状态后台监控线程"""
        with self._death_lock:
            self._death_monitor_running = False
        
        if self._death_monitor_thread and self._death_monitor_thread.is_alive():
            self._death_monitor_thread.join(timeout=1.0)
            self._log("死亡监控线程已停止")
    
    def is_death_detected(self):
        """
        快速查询是否检测到死亡状态
        
        Returns:
            bool: True 如果检测到死亡状态
        """
        with self._death_lock:
            return self._death_detected
    
    def reset_death_state(self):
        """重置死亡状态（复活后调用）"""
        with self._death_lock:
            self._death_detected = False
            self._log("死亡状态已重置")
    
    def _death_monitor_loop(self):
        """
        死亡状态监控循环（在后台线程中运行）

        持续高速检测死亡状态，检测到后立即设置标志
        当死亡状态消失时（复活），自动重置标志
        """
        check_count = 0
        consecutive_death = 0  # 连续检测到死亡的次数
        consecutive_alive = 0  # 连续未检测到死亡的次数

        while True:
            with self._death_lock:
                if not self._death_monitor_running:
                    break

            # 检查退出信号
            if self._should_exit():
                self._log("死亡监控：检测到退出信号")
                break

            check_count += 1

            try:
                is_dead = False

                if self._is_unity_mode():
                    # Unity 模式：通过 TCP 命令获取死亡状态
                    info = self._detect_self_unity()
                    if info is None:
                        # 玩家不存在（不在战斗中），视为存活
                        is_dead = False
                    else:
                        conn = self._get_unity_connection()
                        if conn:
                            player_info = conn.get_player_info()
                            is_dead = player_info.get('isDead', False)
                else:
                    # YOLO 模式：更新帧并检测
                    if hasattr(self.task, 'next_frame'):
                        self.task.next_frame()

                    frame = self._get_frame()
                    if frame is None:
                        time.sleep(self._death_check_interval)
                        continue

                    results = og.my_app.yolo_detect(
                        frame,
                        threshold=0.5,
                        label=CombatLabel.DEATH
                    )
                    is_dead = len(results) > 0

                if is_dead:
                    consecutive_death += 1
                    consecutive_alive = 0

                    # 连续2次检测到死亡才确认（避免误判）
                    if consecutive_death >= 2:
                        with self._death_lock:
                            if not self._death_detected:
                                self._log("死亡监控：确认死亡状态")
                            self._death_detected = True
                else:
                    consecutive_alive += 1
                    consecutive_death = 0

                    # 连续3次未检测到死亡才确认复活（避免误判）
                    if consecutive_alive >= 3:
                        with self._death_lock:
                            if self._death_detected:
                                self._log("死亡监控：确认复活状态")
                            self._death_detected = False

            except Exception as e:
                self._log(f"死亡监控异常: {e}")

            time.sleep(self._death_check_interval)

        self._log(f"死亡监控线程结束，共执行{check_count}次检测")
    
    # ==================== 同步检测方法 ====================
    
    def detect_death_state(self, timeout=10):
        """
        10秒内持续监测死亡状态（同步方法，建议使用并行检测代替）
        
        使用 YOLO 模型检测"死亡状态"标签
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            bool: True 如果检测到死亡状态
        """
        start_time = time.time()
        check_count = 0
        
        while time.time() - start_time < timeout:
            # 检查退出信号
            if self._should_exit():
                return False
            
            frame = self._get_frame()
            if frame is None:
                self._log("⚠️ 死亡检测: 无法获取帧")
                time.sleep(0.05)  # 减少等待时间
                continue
            
            check_count += 1
            results = og.my_app.yolo_detect(
                frame,
                threshold=0.5,
                label=CombatLabel.DEATH
            )
            
            if results:
                self._log(f"💀 死亡检测: 第{check_count}次检测到死亡状态, "
                         f"置信度={results[0].confidence:.2f}")
                return True  # 检测到死亡
            
            # 仅在需要等待时才sleep，减少延迟
            time.sleep(0.05)  # 50ms，约20Hz检测频率
        
        self._log(f"死亡检测完成: {check_count}次检测, 未发现死亡状态")
        return False  # 超时未检测到死亡
    
    def detect_self(self, timeout=15):
        """
        15秒内检测自身位置
        
        使用 YOLO 模型检测"自己"标签
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            DetectionResult: 自身位置，超时返回 None
        """
        start_time = time.time()
        check_count = 0              # 总检测次数
        null_frame_count = 0         # 帧为None次数
        first_frame_logged = False   # 是否已记录首帧
        last_null_frame_log_time = 0  # 上次输出帧获取失败日志的时间
        last_no_detect_log_time = 0   # 上次输出未检测到日志的时间
        
        # 进入方法时输出日志
        if hasattr(self.task, 'logger'):
            self.task.logger.info(f"[自身检测] 开始检测, 超时={timeout}秒")
        
        while time.time() - start_time < timeout:
            # 检查退出信号
            if self._should_exit():
                return None
            
            # 更新帧（获取最新画面）
            if hasattr(self.task, 'next_frame'):
                self.task.next_frame()
            
            frame = self._get_frame()
            elapsed = time.time() - start_time
            
            if frame is None:
                null_frame_count += 1
                # 每2秒输出一次帧获取失败日志，避免刷屏
                if time.time() - last_null_frame_log_time >= 2:
                    if hasattr(self.task, 'logger'):
                        self.task.logger.warning(f"[自身检测] 帧获取失败(None), 已等待{elapsed:.1f}秒, 尝试{null_frame_count}次")
                    last_null_frame_log_time = time.time()
                time.sleep(0.05)
                continue
            
            # 首次获取到帧时输出日志
            if not first_frame_logged:
                h, w = frame.shape[:2]
                if hasattr(self.task, 'logger'):
                    self.task.logger.info(f"[自身检测] 首次获取到帧, 尺寸={w}x{h}")
                first_frame_logged = True
            
            check_count += 1
            
            results = og.my_app.yolo_detect(
                frame,
                threshold=0.5,
                label=CombatLabel.SELF
            )
            
            if results:
                # 检测成功
                if hasattr(self.task, 'logger'):
                    self.task.logger.info(
                        f"[自身检测] 成功! 位置=({results[0].center_x},{results[0].center_y}), "
                        f"置信度={results[0].confidence:.2f}, 耗时{elapsed:.1f}秒, 共检测{check_count}次"
                    )
                return results[0]  # 返回第一个检测到的自身位置
            else:
                # 每3秒输出一次未检测到日志，避免刷屏
                if time.time() - last_no_detect_log_time >= 3:
                    if hasattr(self.task, 'logger'):
                        self.task.logger.warning(f"[自身检测] 未检测到自身, 已耗时{elapsed:.1f}秒, 已检测{check_count}次")
                    last_no_detect_log_time = time.time()
            
            time.sleep(0.03)  # 30ms，更快响应
        
        # 超时时输出详细日志
        if hasattr(self.task, 'logger'):
            self.task.logger.warning(f"[自身检测] 超时! {timeout}秒内共检测{check_count}次, 帧获取失败{null_frame_count}次")
        return None  # 超时未检测到
    
    def detect_self_once(self):
        """
        单次检测自身位置（不循环）

        Returns:
            DetectionResult: 自身位置，未检测到返回 None
        """
        # Unity 工程连接模式：通过 TCP 命令获取玩家位置
        if self._is_unity_mode():
            return self._detect_self_unity()

        frame = self._get_frame()
        if frame is None:
            return None

        results = og.my_app.yolo_detect(
            frame,
            threshold=0.5,
            label=CombatLabel.SELF
        )

        return results[0] if results else None
    
    def detect_allies(self):
        """
        检测友方单位
        
        使用 YOLO 模型检测"友方"标签
        
        Returns:
            list: 友方单位列表 [DetectionResult, ...]
        """
        frame = self._get_frame()
        if frame is None:
            return []
        
        return og.my_app.yolo_detect(
            frame,
            threshold=0.5,
            label=CombatLabel.ALLY
        )
    
    def detect_enemies(self):
        """
        检测敌方单位
        
        使用 YOLO 模型检测"敌军"标签
        
        Returns:
            list: 敌方单位列表 [DetectionResult, ...]
        """
        frame = self._get_frame()
        if frame is None:
            return []
        
        return og.my_app.yolo_detect(
            frame,
            threshold=0.5,
            label=CombatLabel.ENEMY
        )
    
    def detect_all_units(self):
        """
        检测所有战场单位（3 次 YOLO 推理，已废弃，请用 detect_all_once）

        Returns:
            tuple: (self_pos, allies, enemies)
        """
        return self.detect_all_once()

    def detect_all_once(self, frame=None):
        """
        单次全量检测：1 帧 + 1 次 YOLO 推理 或 Unity TCP 命令

        Unity 模式下通过 get_all_actors 命令获取所有 Actor 数据，
        替代 YOLO 截图识别。

        Args:
            frame: BGR 图像。如果为 None，使用 self.task.frame。

        Returns:
            tuple: (self_pos, allies, enemies, has_death)
                self_pos: DetectionResult 或 None（最高置信度的 SELF）
                allies: list[DetectionResult]
                enemies: list[DetectionResult]
                has_death: bool（是否检测到 DEATH 标签）
        """
        # Unity 工程连接模式：使用 TCP 命令替代 YOLO
        if self._is_unity_mode():
            return self._detect_all_unity()

        if frame is None:
            frame = self._get_frame()
        if frame is None:
            return None, [], [], False

        all_detections = og.my_app.yolo_detect(
            frame, threshold=0.5, label=-1
        )

        self_pos = None
        allies = []
        enemies = []
        has_death = False

        for det in all_detections:
            if det.class_id == CombatLabel.SELF:
                if self_pos is None or det.confidence > self_pos.confidence:
                    self_pos = det
            elif det.class_id == CombatLabel.ALLY:
                allies.append(det)
            elif det.class_id == CombatLabel.ENEMY:
                enemies.append(det)
            elif det.class_id == CombatLabel.DEATH:
                has_death = True
            # TARGET_CIRCLE(4) 不归入任何列表

        return self_pos, allies, enemies, has_death
    
    def get_battlefield_state(self):
        """
        判断战场状态
        
        Returns:
            BattlefieldState: 战场状态枚举值
        """
        state, _, _ = self.get_battlefield_state_detailed()
        return state
    
    def get_battlefield_state_detailed(self):
        """
        判断战场状态（返回详细信息）
        
        注意：此方法会先更新帧，确保使用最新的画面进行检测
        
        Returns:
            tuple: (BattlefieldState, allies_list, enemies_list)
        """
        # 先更新帧，确保使用最新的画面
        if hasattr(self.task, 'next_frame'):
            self.task.next_frame()
        
        # 获取当前帧
        frame = self._get_frame()
        if frame is None:
            # 无法获取帧，返回无单位状态
            return BattlefieldState.NO_UNITS, [], []
        
        # 使用同一帧检测友方和敌方（确保一致性）
        allies = og.my_app.yolo_detect(
            frame,
            threshold=0.5,
            label=CombatLabel.ALLY
        )
        enemies = og.my_app.yolo_detect(
            frame,
            threshold=0.5,
            label=CombatLabel.ENEMY
        )
        
        has_allies = len(allies) > 0
        has_enemies = len(enemies) > 0
        
        if not has_allies and not has_enemies:
            state = BattlefieldState.NO_UNITS
        elif has_allies and not has_enemies:
            state = BattlefieldState.ALLIES_ONLY
        elif not has_allies and has_enemies:
            state = BattlefieldState.ENEMIES_ONLY
        else:
            state = BattlefieldState.MIXED
        
        return state, allies, enemies
    
    def get_nearest_ally(self, self_pos):
        """
        获取最近的友方单位
        
        Args:
            self_pos: 自身位置
            
        Returns:
            DetectionResult: 最近的友方单位，无则返回 None
        """
        allies = self.detect_allies()
        if not allies or self_pos is None:
            return None
        
        return self._get_nearest(self_pos, allies)
    
    def get_nearest_enemy(self, self_pos):
        """
        获取最近的敌方单位
        
        Args:
            self_pos: 自身位置
            
        Returns:
            DetectionResult: 最近的敌方单位，无则返回 None
        """
        enemies = self.detect_enemies()
        if not enemies or self_pos is None:
            return None
        
        return self._get_nearest(self_pos, enemies)
    
    def _get_nearest(self, self_pos, targets):
        """
        获取最近的目标
        
        Args:
            self_pos: 自身位置
            targets: 目标列表
            
        Returns:
            DetectionResult: 最近的目标
        """
        import math
        
        nearest = None
        min_distance = float('inf')
        
        for target in targets:
            dx = target.center_x - self_pos.center_x
            dy = target.center_y - self_pos.center_y
            distance = math.sqrt(dx * dx + dy * dy)
            
            if distance < min_distance:
                min_distance = distance
                nearest = target
        
        return nearest
    
    # ==================== 战斗状态检测（通过YOLO自身检测）====================
    
    def check_combat_state_by_self_detection(self):
        """
        通过自身检测判断战斗状态

        YOLO 模式：截图 + YOLO 检测自身
        Unity 模式：通过 get_player_info TCP 命令检测

        Returns:
            tuple: (in_combat_state, state_changed)
        """
        # Unity 模式：跳过 next_frame（没有窗口捕获）
        if not self._is_unity_mode():
            if hasattr(self.task, 'next_frame'):
                self.task.next_frame()
        
        # 执行单次自身检测
        self_pos = self.detect_self_once()
        
        state_changed = False
        
        with self._combat_state_lock:
            if self_pos is not None:
                # 检测到自身
                self._consecutive_self_found += 1
                self._consecutive_self_not_found = 0
                
                # 连续检测到自身达到阈值，确认进入战斗
                if not self._in_combat_state and self._consecutive_self_found >= self._self_found_threshold:
                    self._in_combat_state = True
                    state_changed = True
                    self._log(f"战斗状态检测: 进入战斗 (连续{self._consecutive_self_found}次检测到自身)")
            else:
                # 未检测到自身
                self._consecutive_self_not_found += 1
                self._consecutive_self_found = 0
                
                # 连续未检测到自身达到阈值，确认退出战斗
                if self._in_combat_state and self._consecutive_self_not_found >= self._self_not_found_threshold:
                    self._in_combat_state = False
                    state_changed = True
                    self._log(f"战斗状态检测: 退出战斗 (连续{self._consecutive_self_not_found}次未检测到自身)")
            
            return self._in_combat_state, state_changed
    
    def is_in_combat_state(self):
        """
        快速查询当前是否在战斗状态
        
        Returns:
            bool: True 如果在战斗状态中
        """
        with self._combat_state_lock:
            return self._in_combat_state
    
    def set_combat_state(self, in_combat):
        """
        手动设置战斗状态
        
        Args:
            in_combat: 是否在战斗状态
        """
        with self._combat_state_lock:
            if self._in_combat_state != in_combat:
                self._in_combat_state = in_combat
                self._log(f"战斗状态手动设置为: {'战斗中' if in_combat else '非战斗'}")
            # 重置计数器
            self._consecutive_self_found = 0
            self._consecutive_self_not_found = 0
    
    def reset_combat_state(self):
        """
        重置战斗状态（退出时调用）
        """
        with self._combat_state_lock:
            self._in_combat_state = False
            self._consecutive_self_found = 0
            self._consecutive_self_not_found = 0
            self._log("战斗状态已重置")

    # ==================== Unity 工程连接检测 ====================

    def _is_unity_mode(self):
        """检查是否使用 Unity 工程连接模式"""
        return self._get_unity_connection() is not None

    def _get_unity_connection(self):
        """获取 Unity 连接实例"""
        try:
            if og and hasattr(og, 'my_app') and hasattr(og.my_app, '_unity_connection'):
                conn = og.my_app._unity_connection
                if conn and conn.is_connected():
                    return conn
        except Exception:
            pass
        return None

    def _detect_all_unity(self):
        """
        Unity 模式：通过 get_all_actors 命令获取所有 Actor 数据

        Returns:
            tuple: (self_pos, allies, enemies, has_death)
        """
        conn = self._get_unity_connection()
        if conn is None:
            return None, [], [], False

        try:
            actors = conn.get_all_actors()
            if not actors:
                return None, [], [], False

            self_pos = None
            allies = []
            enemies = []
            has_death = False

            # 先获取玩家阵营
            player_camp = None
            for actor in actors:
                if actor.get('isPlayer', False):
                    player_camp = actor.get('campType')
                    break

            for actor in actors:
                screen_x = actor.get('screenX', 0)
                screen_y = actor.get('screenY', 0)
                is_dead = actor.get('isDead', False)
                is_player = actor.get('isPlayer', False)
                camp_type = actor.get('campType', 0)

                if is_dead:
                    if is_player:
                        has_death = True
                    continue

                # 根据阵营判断敌我
                if is_player:
                    class_id = CombatLabel.SELF
                elif player_camp is not None and camp_type == player_camp:
                    class_id = CombatLabel.ALLY
                else:
                    class_id = CombatLabel.ENEMY

                det = UnityDetectionResult(
                    center_x=screen_x,
                    center_y=screen_y,
                    class_id=class_id,
                    confidence=1.0
                )

                if class_id == CombatLabel.SELF:
                    self_pos = det
                elif class_id == CombatLabel.ALLY:
                    allies.append(det)
                elif class_id == CombatLabel.ENEMY:
                    enemies.append(det)

            return self_pos, allies, enemies, has_death

        except Exception as e:
            self._log(f"Unity 检测失败: {e}")
            return None, [], [], False

    def _detect_self_unity(self):
        """
        Unity 模式：获取玩家自身位置

        Returns:
            UnityDetectionResult: 玩家位置，未在战斗中返回 None
        """
        conn = self._get_unity_connection()
        if conn is None:
            return None

        try:
            info = conn.get_player_info()
            if not info or not info.get('found', False):
                return None

            return UnityDetectionResult(
                center_x=info.get('screenX', 0),
                center_y=info.get('screenY', 0),
                class_id=CombatLabel.SELF,
                confidence=1.0
            )
        except Exception as e:
            self._log(f"Unity 自身检测失败: {e}")
            return None
