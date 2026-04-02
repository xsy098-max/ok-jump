"""
自动战斗模块单元测试

测试覆盖：
- StateDetector.detect_all_once() 全量检测
- AutoCombatTask._get_skill_distance() 距离计算
- AutoCombatTask._get_nearest_target() 最近目标
- AutoCombatTask._calculate_movement_keys() 方向按键
- AutoCombatTask 卡住/抖动检测
- AutoCombatTask._combat_loop 扁平循环行为
- AutoCombatTask._find_locked_target() 目标锁定
- 死亡检测合并 + 防抖
- 敌人丢失记忆防抖
- 技能生命周期管理
"""

import pytest
import math
import time
import threading
from unittest.mock import MagicMock, patch, call

from src.combat.state_detector import StateDetector, BattlefieldState
from src.combat.labels import CombatLabel
from src.combat.distance_calculator import DistanceCalculator
from src.combat.skill_controller import SkillController
from src.task.AutoCombatTask import AutoCombatTask


# ==================== 测试辅助函数 ====================

def build_mock_task():
    """构建模拟的任务对象"""
    task = MagicMock()
    task.config = {
        '测试模式': False,
        '详细日志': False,
        '自动普攻': True,
        '自动技能1': True,
        '自动技能2': True,
        '自动大招': True,
        '普攻间隔(秒)': 0.5,
        '技能1间隔(秒)': 2.0,
        '技能2间隔(秒)': 3.0,
        '大招间隔(秒)': 5.0,
        '移动持续时间(秒)': 0.5,
    }
    task.default_config = task.config.copy()
    task.logger = MagicMock()
    task.frame = MagicMock()
    task.frame.shape = (1080, 1920, 3)
    task.width = 1920
    task.height = 1080
    task.next_frame = MagicMock()
    task.click = MagicMock()
    task.send_key = MagicMock()
    task.send_key_down = MagicMock()
    task.send_key_up = MagicMock()
    task.ocr = MagicMock(return_value=[])
    task.find_one = MagicMock(return_value=None)
    task.find_boxes = MagicMock(return_value=[])
    task._should_exit = MagicMock(return_value=False)
    task._exit_requested = False
    task.executor = MagicMock()
    task.executor.get_task = MagicMock(return_value=None)
    return task


def build_mock_combat_task():
    """构建模拟的 AutoCombatTask 对象（使用 MagicMock 避免 Cython 属性限制）"""
    task = MagicMock(spec=AutoCombatTask)
    # config 必须是真正的 dict 才能用 .get()
    _config = {
        '测试模式': False,
        '详细日志': False,
        '自动普攻': True,
        '自动技能1': True,
        '自动技能2': True,
        '自动大招': True,
        '普攻间隔(秒)': 0.5,
        '技能1间隔(秒)': 2.0,
        '技能2间隔(秒)': 3.0,
        '大招间隔(秒)': 5.0,
        '移动持续时间(秒)': 0.5,
    }
    task.config = _config
    task.logger = MagicMock()
    task.next_frame = MagicMock()
    task._should_exit = MagicMock(return_value=False)
    task._exit_requested = False

    # 控制器
    task.state_detector = MagicMock(spec=StateDetector)
    task.movement_ctrl = MagicMock()
    task.movement_ctrl.move_duration = 0.5
    task.skill_ctrl = MagicMock()
    task.distance_calc = DistanceCalculator()

    # 绑定真实方法（覆盖 MagicMock 的自动 mock）
    task._get_skill_distance = AutoCombatTask._get_skill_distance.__get__(task)
    task._get_nearest_target = AutoCombatTask._get_nearest_target.__get__(task)
    task._calculate_movement_keys = AutoCombatTask._calculate_movement_keys.__get__(task)
    task._handle_stuck_or_jitter = AutoCombatTask._handle_stuck_or_jitter.__get__(task)
    task._record_position = AutoCombatTask._record_position.__get__(task)
    task._detect_stuck = AutoCombatTask._detect_stuck.__get__(task)
    task._detect_jitter = AutoCombatTask._detect_jitter.__get__(task)
    task._find_locked_target = AutoCombatTask._find_locked_target.__get__(task)
    task._is_combat_active = AutoCombatTask._is_combat_active.__get__(task)
    task._combat_loop = AutoCombatTask._combat_loop.__get__(task)
    task._verbose_log = MagicMock()

    # 战斗状态（需要真实的锁和标志，用于 _is_combat_active / _combat_loop）
    task._combat_active = True
    task._combat_lock = threading.Lock()

    # 内部状态
    task._loop_count = 0
    task._last_state = None
    task._position_history = []
    task._position_history_max = 8
    task._last_enemy_pos = None

    return task


def make_detection(x, y, w, h, class_id, confidence=0.9):
    """构建模拟的 DetectionResult"""
    det = MagicMock()
    det.x = x
    det.y = y
    det.width = w
    det.height = h
    det.class_id = class_id
    det.confidence = confidence
    det.center_x = x + w // 2
    det.center_y = y + h // 2
    return det


# ==================== TestDetectAllOnce ====================

class TestDetectAllOnce:
    """detect_all_once() 全量检测测试"""

    def test_returns_self_allies_enemies_no_death(self):
        """单次 YOLO 返回混合标签，正确分类"""
        task = build_mock_task()
        detector = StateDetector(task)

        mock_self = make_detection(900, 500, 80, 120, CombatLabel.SELF)
        mock_ally = make_detection(200, 400, 60, 90, CombatLabel.ALLY)
        mock_enemy = make_detection(1400, 300, 70, 100, CombatLabel.ENEMY)

        with patch('src.combat.state_detector.og') as mock_og:
            mock_og.my_app.yolo_detect.return_value = [mock_self, mock_ally, mock_enemy]
            self_pos, allies, enemies, has_death = detector.detect_all_once()

        assert self_pos is not None
        assert len(allies) == 1
        assert len(enemies) == 1
        assert has_death is False

    def test_no_self_returns_none(self):
        """无 SELF 标签时 self_pos 为 None"""
        task = build_mock_task()
        detector = StateDetector(task)

        mock_enemy = make_detection(1400, 300, 70, 100, CombatLabel.ENEMY)

        with patch('src.combat.state_detector.og') as mock_og:
            mock_og.my_app.yolo_detect.return_value = [mock_enemy]
            self_pos, allies, enemies, has_death = detector.detect_all_once()

        assert self_pos is None
        assert len(enemies) == 1
        assert has_death is False

    def test_no_frame_returns_empty(self):
        """frame=None 时返回空结果"""
        task = build_mock_task()
        task.frame = None
        detector = StateDetector(task)

        self_pos, allies, enemies, has_death = detector.detect_all_once(frame=None)

        assert self_pos is None
        assert allies == []
        assert enemies == []
        assert has_death is False

    def test_multiple_self_keeps_highest_confidence(self):
        """多个 SELF 结果时保留最高置信度"""
        task = build_mock_task()
        detector = StateDetector(task)

        mock_self_low = make_detection(900, 500, 80, 120, CombatLabel.SELF, confidence=0.6)
        mock_self_high = make_detection(850, 480, 80, 120, CombatLabel.SELF, confidence=0.95)

        with patch('src.combat.state_detector.og') as mock_og:
            mock_og.my_app.yolo_detect.return_value = [mock_self_low, mock_self_high]
            self_pos, allies, enemies, has_death = detector.detect_all_once()

        assert self_pos.confidence == 0.95

    def test_ignores_target_circle(self):
        """TARGET_CIRCLE(4) 标签被忽略"""
        task = build_mock_task()
        detector = StateDetector(task)

        mock_tc = make_detection(100, 100, 50, 50, CombatLabel.TARGET_CIRCLE)
        mock_self = make_detection(900, 500, 80, 120, CombatLabel.SELF)

        with patch('src.combat.state_detector.og') as mock_og:
            mock_og.my_app.yolo_detect.return_value = [mock_tc, mock_self]
            self_pos, allies, enemies, has_death = detector.detect_all_once()

        assert self_pos is not None
        assert allies == []
        assert enemies == []

    def test_uses_provided_frame(self):
        """传入 frame 参数时直接使用"""
        task = build_mock_task()
        detector = StateDetector(task)
        import numpy as np
        custom_frame = np.zeros((600, 800, 3), dtype=np.uint8)

        with patch('src.combat.state_detector.og') as mock_og:
            mock_og.my_app.yolo_detect.return_value = []
            detector.detect_all_once(frame=custom_frame)

        mock_og.my_app.yolo_detect.assert_called_once_with(custom_frame, threshold=0.5, label=-1)

    def test_detects_death_in_results(self):
        """DEATH 标签被检测到时 has_death 为 True"""
        task = build_mock_task()
        detector = StateDetector(task)

        mock_self = make_detection(900, 500, 80, 120, CombatLabel.SELF)
        mock_death = make_detection(500, 400, 100, 100, CombatLabel.DEATH)

        with patch('src.combat.state_detector.og') as mock_og:
            mock_og.my_app.yolo_detect.return_value = [mock_self, mock_death]
            self_pos, allies, enemies, has_death = detector.detect_all_once()

        assert has_death is True
        assert self_pos is not None  # SELF 仍然被正确分类

    def test_death_only_frame(self):
        """仅检测到 DEATH 标签"""
        task = build_mock_task()
        detector = StateDetector(task)

        mock_death = make_detection(500, 400, 100, 100, CombatLabel.DEATH)

        with patch('src.combat.state_detector.og') as mock_og:
            mock_og.my_app.yolo_detect.return_value = [mock_death]
            self_pos, allies, enemies, has_death = detector.detect_all_once()

        assert self_pos is None
        assert allies == []
        assert enemies == []
        assert has_death is True


# ==================== TestGetSkillDistance ====================

class TestGetSkillDistance:
    """_get_skill_distance() 距离计算测试"""

    def test_no_enemies_returns_inf(self):
        """无敌人返回 inf"""
        task = build_mock_combat_task()
        self_pos = make_detection(960, 540, 80, 120, CombatLabel.SELF)
        assert task._get_skill_distance(self_pos, []) == float('inf')

    def test_self_pos_none_returns_inf(self):
        """self_pos 为 None 返回 inf"""
        task = build_mock_combat_task()
        enemy = make_detection(1400, 300, 70, 100, CombatLabel.ENEMY)
        assert task._get_skill_distance(None, [enemy]) == float('inf')

    def test_single_enemy_in_range(self):
        """单个敌人在技能范围内"""
        task = build_mock_combat_task()
        self_pos = make_detection(960, 540, 80, 120, CombatLabel.SELF)
        enemy = make_detection(1060, 540, 70, 100, CombatLabel.ENEMY)  # ~100px away

        distance = task._get_skill_distance(self_pos, [enemy])
        assert distance <= 225

    def test_single_enemy_out_range(self):
        """单个敌人超出技能范围，返回最近距离"""
        task = build_mock_combat_task()
        self_pos = make_detection(960, 540, 80, 120, CombatLabel.SELF)
        enemy = make_detection(1500, 540, 70, 100, CombatLabel.ENEMY)  # far away

        distance = task._get_skill_distance(self_pos, [enemy])
        assert distance > 225

    def test_multiple_enemies_one_in_range(self):
        """多个敌人中一个在范围内，优先返回范围内距离"""
        task = build_mock_combat_task()
        self_pos = make_detection(960, 540, 80, 120, CombatLabel.SELF)
        close_enemy = make_detection(1010, 540, 70, 100, CombatLabel.ENEMY)   # ~50px
        far_enemy = make_detection(1500, 540, 70, 100, CombatLabel.ENEMY)     # far

        distance = task._get_skill_distance(self_pos, [close_enemy, far_enemy])
        assert distance <= 225


# ==================== TestGetNearestTarget ====================

class TestGetNearestTarget:
    """_get_nearest_target() 最近目标测试"""

    def test_returns_nearest(self):
        """从多个目标中返回最近的"""
        task = build_mock_combat_task()
        self_pos = make_detection(960, 540, 80, 120, CombatLabel.SELF)
        near = make_detection(1010, 540, 70, 100, CombatLabel.ENEMY)
        far = make_detection(1500, 540, 70, 100, CombatLabel.ENEMY)

        result = task._get_nearest_target(self_pos, [far, near])
        assert result == near

    def test_empty_list_returns_none(self):
        """空列表返回 None"""
        task = build_mock_combat_task()
        self_pos = make_detection(960, 540, 80, 120, CombatLabel.SELF)
        assert task._get_nearest_target(self_pos, []) is None

    def test_single_target(self):
        """单个目标直接返回"""
        task = build_mock_combat_task()
        self_pos = make_detection(960, 540, 80, 120, CombatLabel.SELF)
        enemy = make_detection(1100, 540, 70, 100, CombatLabel.ENEMY)

        result = task._get_nearest_target(self_pos, [enemy])
        assert result == enemy


# ==================== TestCalculateMovementKeys ====================

class TestCalculateMovementKeys:
    """_calculate_movement_keys() 方向按键测试"""

    def test_target_right_press_D(self):
        """目标在右边按 D"""
        task = build_mock_combat_task()
        self_pos = make_detection(500, 500, 80, 120, CombatLabel.SELF)
        target = make_detection(800, 500, 70, 100, CombatLabel.ENEMY)
        keys = task._calculate_movement_keys(self_pos, target, "towards")
        assert 'D' in keys

    def test_target_left_press_A(self):
        """目标在左边按 A"""
        task = build_mock_combat_task()
        self_pos = make_detection(800, 500, 80, 120, CombatLabel.SELF)
        target = make_detection(500, 500, 70, 100, CombatLabel.ENEMY)
        keys = task._calculate_movement_keys(self_pos, target, "towards")
        assert 'A' in keys

    def test_target_below_press_S(self):
        """目标在下方按 S"""
        task = build_mock_combat_task()
        self_pos = make_detection(500, 300, 80, 120, CombatLabel.SELF)
        target = make_detection(500, 600, 70, 100, CombatLabel.ENEMY)
        keys = task._calculate_movement_keys(self_pos, target, "towards")
        assert 'S' in keys

    def test_target_above_press_W(self):
        """目标在上方按 W"""
        task = build_mock_combat_task()
        self_pos = make_detection(500, 600, 80, 120, CombatLabel.SELF)
        target = make_detection(500, 300, 70, 100, CombatLabel.ENEMY)
        keys = task._calculate_movement_keys(self_pos, target, "towards")
        assert 'W' in keys

    def test_diagonal_press_two_keys(self):
        """对角方向按两个键"""
        task = build_mock_combat_task()
        self_pos = make_detection(400, 400, 80, 120, CombatLabel.SELF)
        target = make_detection(800, 800, 70, 100, CombatLabel.ENEMY)
        keys = task._calculate_movement_keys(self_pos, target, "towards")
        assert len(keys) == 2
        assert 'D' in keys
        assert 'S' in keys

    def test_offset_below_threshold_no_keys(self):
        """偏移太小不按键"""
        task = build_mock_combat_task()
        self_pos = make_detection(500, 500, 80, 120, CombatLabel.SELF)
        target = make_detection(510, 505, 70, 100, CombatLabel.ENEMY)  # 仅 10px 偏移
        keys = task._calculate_movement_keys(self_pos, target, "towards")
        assert keys == []


# ==================== TestStuckAndJitterDetection ====================

class TestStuckAndJitterDetection:
    """卡住/抖动检测测试"""

    def test_stuck_detected_after_4_same_positions(self):
        """连续 4 个相同位置检测到卡住"""
        task = build_mock_combat_task()
        self_pos = make_detection(500, 500, 80, 120, CombatLabel.SELF)
        for _ in range(4):
            task._record_position(500, 500)
        assert task._detect_stuck() is True

    def test_stuck_not_detected_when_moving(self):
        """位置不同时不检测卡住"""
        task = build_mock_combat_task()
        task._record_position(100, 100)
        task._record_position(150, 120)
        task._record_position(200, 140)
        task._record_position(250, 160)
        assert task._detect_stuck() is False

    def test_stuck_clears_history_after_detection(self):
        """卡住检测后手动清空历史"""
        task = build_mock_combat_task()
        for _ in range(4):
            task._record_position(500, 500)
        assert task._detect_stuck() is True
        task._position_history.clear()
        assert len(task._position_history) == 0

    def test_jitter_detected_with_abab_pattern(self):
        """A-B-A-B 模式检测到抖动"""
        task = build_mock_combat_task()
        # A-B-A-B-A-B pattern
        positions = [(100, 100), (300, 100), (100, 100), (300, 100), (100, 100), (300, 100)]
        for x, y in positions:
            task._record_position(x, y)
        assert task._detect_jitter() is True

    def test_jitter_not_detected_with_linear_movement(self):
        """线性移动不触发抖动"""
        task = build_mock_combat_task()
        positions = [(100, 100), (150, 120), (200, 140), (250, 160), (300, 180), (350, 200)]
        for x, y in positions:
            task._record_position(x, y)
        assert task._detect_jitter() is False

    def test_handle_stuck_or_jitter_returns_true_when_stuck(self):
        """卡住时返回 True"""
        task = build_mock_combat_task()
        # _handle_stuck_or_jitter 内部调用 movement_ctrl._press_movement_keys_for_duration
        task.movement_ctrl._press_movement_keys_for_duration = MagicMock()
        # center_x = x + w//2, center_y = y + h//2
        self_pos = make_detection(500, 500, 80, 120, CombatLabel.SELF)  # center=(540, 560)
        # 记录与 self_pos 中心一致的位置
        for _ in range(3):
            task._record_position(self_pos.center_x, self_pos.center_y)
        result = task._handle_stuck_or_jitter(self_pos)
        assert result is True

    def test_handle_stuck_or_jitter_returns_false_normal(self):
        """正常移动返回 False"""
        task = build_mock_combat_task()
        self_pos = make_detection(500, 500, 80, 120, CombatLabel.SELF)
        task._position_history.clear()
        result = task._handle_stuck_or_jitter(self_pos)
        assert result is False


# ==================== TestDeathDebounce ====================

class TestDeathDebounce:
    """死亡检测防抖测试"""

    def test_single_death_frame_no_confirm(self):
        """仅 1 帧 DEATH 不确认死亡"""
        task = build_mock_combat_task()
        mock_self = make_detection(960, 540, 80, 120, CombatLabel.SELF)

        # 模拟第 1 帧：有 DEATH
        task.state_detector.detect_all_once.return_value = (mock_self, [], [], True)

        task._should_exit.return_value = False

        # 运行一次循环（通过 _should_exit 在第 2 次返回 True 来退出）
        call_count = [0]
        def should_exit():
            call_count[0] += 1
            return call_count[0] >= 2
        task._should_exit.side_effect = should_exit
        task.state_detector.detect_all_once.return_value = (mock_self, [], [], True)

        task._combat_loop()

        # 仅 1 帧 DEATH 不应触发 stop_auto_skills（需要连续 2 帧）
        # 因为循环只运行了 1 次，consecutive_death = 1 < 2
        task.skill_ctrl.stop_auto_skills.assert_not_called()

    def test_consecutive_two_death_frames_confirms(self):
        """连续 2 帧 DEATH 确认死亡"""
        task = build_mock_combat_task()
        mock_self = make_detection(960, 540, 80, 120, CombatLabel.SELF)

        call_count = [0]
        def should_exit():
            call_count[0] += 1
            return call_count[0] >= 3
        task._should_exit.side_effect = should_exit

        task.state_detector.detect_all_once.return_value = (mock_self, [], [], True)

        task._combat_loop()

        # 连续 2 帧 DEATH 后应调用 stop_auto_skills
        task.skill_ctrl.stop_auto_skills.assert_called()

    def test_revive_requires_three_alive_frames(self):
        """死亡后需连续 3 帧无 DEATH 才确认复活"""
        task = build_mock_combat_task()
        mock_self = make_detection(960, 540, 80, 120, CombatLabel.SELF)

        frame_count = [0]
        results = [
            (mock_self, [], [], True),   # 1: death
            (mock_self, [], [], True),   # 2: death -> confirmed
            (mock_self, [], [], False),  # 3: alive (1)
            (mock_self, [], [], False),  # 4: alive (2)
            (mock_self, [], [], False),  # 5: alive (3) -> revived
        ]

        def detect():
            idx = min(frame_count[0], len(results) - 1)
            frame_count[0] += 1
            return results[idx]

        call_count = [0]
        def should_exit():
            call_count[0] += 1
            return call_count[0] >= 6
        task._should_exit.side_effect = should_exit

        task.state_detector.detect_all_once.side_effect = detect

        task._combat_loop()

        # 应该先被调用（死亡确认），然后复活后不重复调用
        assert task.skill_ctrl.stop_auto_skills.call_count >= 1


# ==================== TestTargetLocking ====================

class TestTargetLocking:
    """_find_locked_target() 目标锁定测试"""

    def test_initial_lock_nearest(self):
        """首次锁定最近的敌人"""
        task = build_mock_combat_task()
        self_pos = make_detection(960, 540, 80, 120, CombatLabel.SELF)
        near = make_detection(1010, 540, 70, 100, CombatLabel.ENEMY)
        far = make_detection(1500, 540, 70, 100, CombatLabel.ENEMY)

        result = task._find_locked_target(self_pos, [far, near], None, 0, 200, 3)
        assert result == near

    def test_track_locked_target(self):
        """后续帧跟踪已锁定目标"""
        task = build_mock_combat_task()
        self_pos = make_detection(960, 540, 80, 120, CombatLabel.SELF)
        target = make_detection(1010, 540, 70, 100, CombatLabel.ENEMY)
        other = make_detection(1500, 540, 70, 100, CombatLabel.ENEMY)

        # locked_center 指向 target 附近
        result = task._find_locked_target(self_pos, [target, other], (1010, 540), 0, 200, 3)
        assert result == target

    def test_lost_count_no_match(self):
        """锁定目标丢失时返回 None"""
        task = build_mock_combat_task()
        self_pos = make_detection(960, 540, 80, 120, CombatLabel.SELF)
        # 只有一个敌人，位置远离锁定中心
        enemy = make_detection(200, 200, 70, 100, CombatLabel.ENEMY)

        result = task._find_locked_target(self_pos, [enemy], (1000, 500), 0, 200, 3)
        # 曼哈顿距离 |200-1000| + |200-500| = 1100 > 200，匹配失败
        assert result is None

    def test_no_enemies_returns_none(self):
        """无敌人返回 None"""
        task = build_mock_combat_task()
        self_pos = make_detection(960, 540, 80, 120, CombatLabel.SELF)
        result = task._find_locked_target(self_pos, [], None, 0, 200, 3)
        assert result is None


# ==================== TestSkillLifecycle ====================

class TestSkillLifecycle:
    """技能控制器生命周期测试"""

    def test_start_called_once_on_enemy_appear(self):
        """出现敌人时 start_auto_skills 只调用一次"""
        task = build_mock_combat_task()
        mock_self = make_detection(960, 540, 80, 120, CombatLabel.SELF)
        mock_enemy = make_detection(1100, 540, 70, 100, CombatLabel.ENEMY)

        call_count = [0]
        def should_exit():
            call_count[0] += 1
            return call_count[0] >= 3
        task._should_exit.side_effect = should_exit

        task.state_detector.detect_all_once.return_value = (mock_self, [], [mock_enemy], False)

        task._combat_loop()

        # 连续 3 帧有敌人，start_auto_skills 只应调用 1 次
        assert task.skill_ctrl.start_auto_skills.call_count == 1

    def test_stop_called_on_enemy_disappear(self):
        """敌人消失时 stop_auto_skills 被调用"""
        task = build_mock_combat_task()
        mock_self = make_detection(960, 540, 80, 120, CombatLabel.SELF)
        mock_enemy = make_detection(1100, 540, 70, 100, CombatLabel.ENEMY)

        frame_count = [0]
        results = [
            (mock_self, [], [mock_enemy], False),  # 1: 有敌人
            (mock_self, [], [], False),              # 2: 无敌人
        ]

        def detect():
            idx = min(frame_count[0], len(results) - 1)
            frame_count[0] += 1
            return results[idx]

        call_count = [0]
        def should_exit():
            call_count[0] += 1
            return call_count[0] >= 3
        task._should_exit.side_effect = should_exit

        task.state_detector.detect_all_once.side_effect = detect

        task._combat_loop()

        # 应调用 start（第1帧）然后 stop（第2帧）
        task.skill_ctrl.start_auto_skills.assert_called_once()
        task.skill_ctrl.stop_auto_skills.assert_called_once()


# ==================== TestThreadSafety ====================

class TestThreadSafety:
    """线程安全测试"""

    def test_update_distance_thread_safe(self):
        """多线程同时 update_distance 不报错"""
        task = build_mock_combat_task()
        errors = []

        def update_many():
            try:
                for i in range(100):
                    task.skill_ctrl.update_distance(float(i))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=update_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0

    def test_combat_active_flag_thread_safe(self):
        """_is_combat_active 多线程读取一致"""
        task = build_mock_combat_task()
        task._combat_active = True
        results = []

        def read_flag():
            for _ in range(100):
                results.append(task._is_combat_active())

        threads = [threading.Thread(target=read_flag) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # 所有读取都应为 True
        assert all(r is True for r in results)


# ==================== TestCombatLoopCalls ====================

class TestCombatLoopCalls:
    """_combat_loop 单轮调用行为验证"""

    def test_calls_detect_all_once_per_cycle(self):
        """每轮调用 detect_all_once"""
        task = build_mock_combat_task()
        mock_self = make_detection(960, 540, 80, 120, CombatLabel.SELF)

        call_count = [0]
        def should_exit():
            call_count[0] += 1
            return call_count[0] >= 2
        task._should_exit.side_effect = should_exit

        task.state_detector.detect_all_once.return_value = (mock_self, [], [], False)

        task._combat_loop()

        task.state_detector.detect_all_once.assert_called()

    def test_calls_next_frame_per_cycle(self):
        """每轮调用 next_frame"""
        task = build_mock_combat_task()
        mock_self = make_detection(960, 540, 80, 120, CombatLabel.SELF)

        call_count = [0]
        def should_exit():
            call_count[0] += 1
            return call_count[0] >= 2
        task._should_exit.side_effect = should_exit

        task.state_detector.detect_all_once.return_value = (mock_self, [], [], False)

        task._combat_loop()

        task.next_frame.assert_called()

    def test_enemies_in_range_stops_movement(self):
        """敌人在范围内时停止移动"""
        task = build_mock_combat_task()
        mock_self = make_detection(960, 540, 80, 120, CombatLabel.SELF)
        # 敌人在 ~50px 处（在 225px 范围内）
        mock_enemy = make_detection(1010, 540, 70, 100, CombatLabel.ENEMY)

        call_count = [0]
        def should_exit():
            call_count[0] += 1
            return call_count[0] >= 2
        task._should_exit.side_effect = should_exit

        task.state_detector.detect_all_once.return_value = (mock_self, [], [mock_enemy], False)

        task._combat_loop()

        task.movement_ctrl.stop.assert_called()

    def test_self_lost_increments_counter(self):
        """self_pos=None 时 sleep 后 continue"""
        task = build_mock_combat_task()

        call_count = [0]
        def should_exit():
            call_count[0] += 1
            return call_count[0] >= 2
        task._should_exit.side_effect = should_exit

        task.state_detector.detect_all_once.return_value = (None, [], [], False)

        task._combat_loop()

        # self_pos=None 时不应该调用任何移动或技能方法
        task.movement_ctrl.move_towards.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
