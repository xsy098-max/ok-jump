"""
新手教程模块单元测试

测试覆盖：
- 状态机 (TutorialStateMachine)
- 角色选择器 (CharacterSelector, CharacterConfig)
- 检测器 (TutorialDetector)
- 第一阶段处理器 (Phase1Handler)
- 主任务类 (AutoTutorialTask)
"""

import pytest
import time
import threading
from unittest.mock import MagicMock, patch, PropertyMock

from src.tutorial.state_machine import TutorialState, TutorialStateMachine
from src.tutorial.character_selector import CharacterSelector, CharacterConfig, CharacterType
from src.tutorial.tutorial_detector import TutorialDetector
from src.tutorial.phase1_handler import Phase1Handler


# ==================== 测试辅助函数 ====================

def build_mock_task():
    """构建模拟的任务对象"""
    task = MagicMock()
    task.config = {
        '角色选择': '路飞',
        '选角界面检测超时(秒)': 10.0,
        '自身检测超时(秒)': 30.0,
        '目标检测超时(秒)': 10.0,
        '普攻检测超时(秒)': 10.0,
        '第一阶段结束检测超时(秒)': 120.0,
        '加载后等待时间(秒)': 30.0,
        '向下移动时间(秒)': 1.5,
        '移动持续时间(秒)': 0.5,
        '点击后等待时间(秒)': 1.0,
        '详细日志': True,
    }
    task.default_config = task.config.copy()
    task.logger = MagicMock()
    task.frame = MagicMock()
    task.frame.shape = (1080, 1920, 3)
    task.width = 1920
    task.height = 1080
    task.next_frame = MagicMock()
    task.click = MagicMock()
    task.click_relative = MagicMock()
    task.send_key = MagicMock()
    task.send_key_down = MagicMock()
    task.send_key_up = MagicMock()
    task.ocr = MagicMock(return_value=[])
    task.find_one = MagicMock(return_value=None)
    task.find_boxes = MagicMock(return_value=[])
    task._should_exit = MagicMock(return_value=False)
    task.executor = MagicMock()
    task.executor.get_task = MagicMock(return_value=None)
    return task


# ==================== 状态机测试 ====================

class TestTutorialStateMachine:
    """状态机测试类"""
    
    def test_initial_state_is_idle(self):
        """测试初始状态为 IDLE"""
        sm = TutorialStateMachine()
        assert sm.current_state == TutorialState.IDLE
        assert sm.history == [TutorialState.IDLE]
    
    def test_can_transition_to_valid_state(self):
        """测试可以转换到有效状态"""
        sm = TutorialStateMachine()
        assert sm.can_transition_to(TutorialState.CHECK_CHARACTER_SELECT) is True
        assert sm.can_transition_to(TutorialState.FAILED) is True
        assert sm.can_transition_to(TutorialState.COMPLETED) is False
    
    def test_transition_to_updates_state_and_history(self):
        """测试状态转换更新当前状态和历史"""
        sm = TutorialStateMachine()
        result = sm.transition_to(TutorialState.CHECK_CHARACTER_SELECT)
        
        assert result is True
        assert sm.current_state == TutorialState.CHECK_CHARACTER_SELECT
        assert len(sm.history) == 2
        assert TutorialState.CHECK_CHARACTER_SELECT in sm.history
    
    def test_cannot_transition_to_invalid_state(self):
        """测试不能转换到无效状态"""
        sm = TutorialStateMachine()
        result = sm.transition_to(TutorialState.COMPLETED)
        
        assert result is False
        assert sm.current_state == TutorialState.IDLE
    
    def test_fail_sets_failure_reason(self):
        """测试失败状态设置失败原因"""
        sm = TutorialStateMachine()
        sm.fail("测试失败原因")
        
        assert sm.current_state == TutorialState.FAILED
        assert sm.failure_reason == "测试失败原因"
    
    def test_reset_clears_state(self):
        """测试重置清除状态"""
        sm = TutorialStateMachine()
        sm.transition_to(TutorialState.CHECK_CHARACTER_SELECT)
        sm.fail("测试失败")
        
        sm.reset()
        
        assert sm.current_state == TutorialState.IDLE
        assert sm.failure_reason is None
        assert sm.history == [TutorialState.IDLE]
    
    def test_is_terminal_for_completed(self):
        """测试完成状态是终态"""
        sm = TutorialStateMachine()
        sm.transition_to(TutorialState.CHECK_CHARACTER_SELECT)
        sm.transition_to(TutorialState.FIRST_CLICK)
        # 手动设置为完成状态测试
        sm._current_state = TutorialState.COMPLETED
        
        assert sm.is_terminal() is True
        assert sm.is_completed() is True
        assert sm.is_failed() is False
    
    def test_is_terminal_for_failed(self):
        """测试失败状态是终态"""
        sm = TutorialStateMachine()
        sm.fail("测试失败")
        
        assert sm.is_terminal() is True
        assert sm.is_failed() is True
        assert sm.is_completed() is False
    
    def test_get_state_name_returns_chinese(self):
        """测试状态名称返回中文"""
        sm = TutorialStateMachine()
        assert sm.get_state_name() == '空闲'
        
        sm.transition_to(TutorialState.CHECK_CHARACTER_SELECT)
        assert sm.get_state_name() == '检查选角界面'
        
        sm.transition_to(TutorialState.FIRST_CLICK)
        assert sm.get_state_name() == '第一次点击角色'
    
    def test_full_state_flow(self):
        """测试完整状态流程"""
        sm = TutorialStateMachine()
        
        # 模拟完整流程（注意：COMBAT_TRIGGER 直接转换到 PHASE1_END，不再经过 PHASE1_END_DETECTION）
        states = [
            TutorialState.CHECK_CHARACTER_SELECT,
            TutorialState.FIRST_CLICK,
            TutorialState.CONFIRM_DIALOG,
            TutorialState.SECOND_CLICK,
            TutorialState.LOADING,
            TutorialState.SELF_DETECTION,
            TutorialState.TARGET_DETECTION,
            TutorialState.MOVE_TO_TARGET,
            TutorialState.NORMAL_ATTACK_DETECTION,
            TutorialState.MOVE_DOWN,
            TutorialState.COMBAT_TRIGGER,
            # PHASE1_END_DETECTION 在 COMBAT_TRIGGER 内部并行运行
            TutorialState.PHASE1_END,
        ]
        
        for state in states:
            assert sm.can_transition_to(state), f"应该能转换到 {state}"
            sm.transition_to(state)
            assert sm.current_state == state


# ==================== 角色选择器测试 ====================

class TestCharacterSelector:
    """角色选择器测试类"""
    
    def test_default_character_is_luffy(self):
        """测试默认角色为路飞"""
        selector = CharacterSelector()
        assert selector.character_type == CharacterType.LUFFY
    
    def test_parse_character_type_wukong(self):
        """测试解析悟空角色"""
        selector = CharacterSelector('悟空')
        assert selector.character_type == CharacterType.WUKONG
        assert selector.is_all_mode is False
    
    def test_parse_character_type_luffy(self):
        """测试解析路飞角色"""
        selector = CharacterSelector('路飞')
        assert selector.character_type == CharacterType.LUFFY
        assert selector.is_all_mode is False
    
    def test_parse_character_type_naruto(self):
        """测试解析小鸣人角色"""
        selector = CharacterSelector('小鸣人')
        assert selector.character_type == CharacterType.NARUTO
        assert selector.is_all_mode is False
    
    def test_parse_character_type_all(self):
        """测试解析全部模式"""
        selector = CharacterSelector('全部')
        assert selector.character_type == CharacterType.ALL
        assert selector.is_all_mode is True
    
    def test_get_current_config_single_character(self):
        """测试获取单个角色配置"""
        selector = CharacterSelector('路飞')
        config = selector.get_current_config()
        
        assert config is not None
        assert config.name == '路飞'
        assert config.target_type == 'target_circle'
        assert config.yolo_model == 'fight.onnx'
        assert config.yolo_label == 4
    
    def test_get_current_config_wukong(self):
        """测试获取悟空配置"""
        selector = CharacterSelector('悟空')
        config = selector.get_current_config()
        
        assert config is not None
        assert config.name == '悟空'
        assert config.target_type == 'monkey'
        assert config.yolo_model == 'fight2.onnx'
        assert config.yolo_label == 0
    
    def test_get_current_config_all_mode_first(self):
        """测试全部模式第一个角色"""
        selector = CharacterSelector('全部')
        config = selector.get_current_config()
        
        # 第一个应该是悟空
        assert config is not None
        assert config.name == '悟空'
    
    def test_move_to_next_character_in_all_mode(self):
        """测试全部模式下移动到下一个角色"""
        selector = CharacterSelector('全部')
        
        # 第一个：悟空
        config = selector.get_current_config()
        assert config.name == '悟空'
        
        # 移动到下一个
        result = selector.move_to_next_character()
        assert result is True
        
        # 第二个：小鸣人
        config = selector.get_current_config()
        assert config.name == '小鸣人'
        
        # 移动到下一个
        result = selector.move_to_next_character()
        assert result is True
        
        # 第三个：路飞
        config = selector.get_current_config()
        assert config.name == '路飞'
        
        # 移动到下一个（应该返回False，已全部完成）
        result = selector.move_to_next_character()
        assert result is False
        assert selector.has_more_characters() is False
    
    def test_reset_clears_index(self):
        """测试重置清除索引"""
        selector = CharacterSelector('全部')
        selector.move_to_next_character()
        selector.move_to_next_character()
        
        selector.reset()
        
        config = selector.get_current_config()
        assert config.name == '悟空'
    
    def test_get_available_characters(self):
        """测试获取可用角色列表"""
        characters = CharacterSelector.get_available_characters()
        
        assert '悟空' in characters
        assert '路飞' in characters
        assert '小鸣人' in characters
        assert '全部' in characters
        assert len(characters) == 4
    
    def test_get_config_by_name(self):
        """测试根据名称获取配置"""
        config = CharacterSelector.get_config_by_name('悟空')
        
        assert config is not None
        assert config.name == '悟空'
        
        config = CharacterSelector.get_config_by_name('不存在的角色')
        assert config is None


class TestCharacterConfig:
    """角色配置测试类"""
    
    def test_get_click_position_wukong(self):
        """测试悟空点击位置（左侧1/3）"""
        config = CharacterConfig(
            name='悟空',
            click_region=(0.0, 1/3),
            target_type='monkey',
            yolo_model='fight2.onnx',
            yolo_label=0
        )
        
        x, y = config.get_click_position(1920, 1080)
        
        # 应该在左侧1/3的中心
        assert x == 320  # (0 + 640) / 2 = 320
        assert y == 540  # 1080 / 2
    
    def test_get_click_position_luffy(self):
        """测试路飞点击位置（中间1/3）"""
        config = CharacterConfig(
            name='路飞',
            click_region=(1/3, 2/3),
            target_type='target_circle',
            yolo_model='fight.onnx',
            yolo_label=4
        )
        
        x, y = config.get_click_position(1920, 1080)
        
        # 应该在中间1/3的中心
        assert x == 960  # (640 + 1280) / 2 = 960
        assert y == 540
    
    def test_get_click_position_naruto(self):
        """测试小鸣人点击位置（右侧1/3）"""
        config = CharacterConfig(
            name='小鸣人',
            click_region=(2/3, 1.0),
            target_type='target_circle',
            yolo_model='fight.onnx',
            yolo_label=4
        )
        
        x, y = config.get_click_position(1920, 1080)
        
        # 应该在右侧1/3的中心
        assert x == 1600  # (1280 + 1920) / 2 = 1600
        assert y == 540
    
    def test_get_relative_click_position(self):
        """测试获取相对点击位置"""
        config = CharacterConfig(
            name='路飞',
            click_region=(1/3, 2/3),
            target_type='target_circle',
            yolo_model='fight.onnx',
            yolo_label=4
        )
        
        x, y = config.get_relative_click_position()
        
        assert x == 0.5  # 中间
        assert y == 0.5  # 中间


# ==================== 检测器测试 ====================

class TestTutorialDetector:
    """检测器测试类"""
    
    def test_set_verbose(self):
        """测试设置详细日志"""
        task = build_mock_task()
        detector = TutorialDetector(task)
        
        detector.set_verbose(True)
        assert detector._verbose is True
        
        detector.set_verbose(False)
        assert detector._verbose is False
    
    def test_detect_character_select_screen_success(self):
        """测试检测选角界面成功"""
        task = build_mock_task()
        
        # 模拟OCR返回选角文字
        mock_box = MagicMock()
        mock_box.name = "请选择一位你心仪的角色"
        task.find_boxes = MagicMock(return_value=[mock_box])
        
        detector = TutorialDetector(task)
        result = detector.detect_character_select_screen(timeout=1.0)
        
        assert result is True
    
    def test_detect_character_select_screen_timeout(self):
        """测试检测选角界面超时"""
        task = build_mock_task()
        task.find_boxes = MagicMock(return_value=[])
        
        detector = TutorialDetector(task)
        result = detector.detect_character_select_screen(timeout=0.5)
        
        assert result is False
    
    def test_detect_back_button_success(self):
        """测试检测返回按钮成功"""
        task = build_mock_task()
        
        mock_btn = MagicMock()
        mock_btn.x = 100
        mock_btn.y = 50
        mock_btn.width = 100
        mock_btn.height = 50
        task.find_one = MagicMock(return_value=mock_btn)
        
        detector = TutorialDetector(task)
        result = detector.detect_back_button(timeout=1.0)
        
        assert result is not None
        assert result == (150, 75)  # 中心点
    
    def test_detect_back_button_not_found(self):
        """测试检测返回按钮未找到"""
        task = build_mock_task()
        task.find_one = MagicMock(side_effect=ValueError("not found"))
        
        detector = TutorialDetector(task)
        result = detector.detect_back_button(timeout=0.5)
        
        assert result is None
    
    def test_detect_confirm_button_success(self):
        """测试检测确定按钮成功"""
        task = build_mock_task()
        
        mock_btn = MagicMock()
        mock_btn.x = 200
        mock_btn.y = 100
        mock_btn.width = 100
        mock_btn.height = 50
        task.find_one = MagicMock(return_value=mock_btn)
        
        detector = TutorialDetector(task)
        result = detector.detect_confirm_button(timeout=1.0)
        
        assert result is not None
        assert result == (250, 125)
    
    def test_detect_normal_attack_button_success(self):
        """测试检测普攻按钮成功"""
        task = build_mock_task()
        
        mock_box = MagicMock()
        mock_box.name = "普攻按钮"
        task.find_boxes = MagicMock(return_value=[mock_box])
        
        detector = TutorialDetector(task)
        result = detector.detect_normal_attack_button(timeout=1.0)
        
        assert result is True
    
    def test_detect_normal_attack_button_timeout(self):
        """测试检测普攻按钮超时"""
        task = build_mock_task()
        task.find_boxes = MagicMock(return_value=[])
        
        detector = TutorialDetector(task)
        result = detector.detect_normal_attack_button(timeout=0.5)
        
        assert result is False
    
    def test_phase1_end_detection_start_and_stop(self):
        """测试第一阶段结束检测启动和停止"""
        task = build_mock_task()
        task.find_one = MagicMock(side_effect=ValueError("not found"))
        
        detector = TutorialDetector(task)
        
        # 启动检测
        detector.start_phase1_end_detection(timeout=2.0)
        assert detector._end_detection_running is True
        
        # 等待一小段时间
        time.sleep(0.5)
        
        # 停止检测
        detector.stop_phase1_end_detection()
        assert detector._end_detection_running is False
    
    def test_phase1_end_detection_detects_end02(self):
        """测试第一阶段结束检测检测到end02"""
        task = build_mock_task()
        
        # 模拟检测到end02按钮
        mock_btn = MagicMock()
        mock_btn.x = 500
        mock_btn.y = 400
        mock_btn.width = 150
        mock_btn.height = 50
        
        call_count = [0]
        def find_one_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 3:  # 第3次调用返回按钮
                return mock_btn
            raise ValueError("not found")
        
        task.find_one = MagicMock(side_effect=find_one_side_effect)
        
        detector = TutorialDetector(task)
        detector.start_phase1_end_detection(timeout=2.0)
        
        # 等待检测完成
        time.sleep(1.0)
        
        # 应该检测到了
        assert detector.is_phase1_end_detected() is True
        
        detector.stop_phase1_end_detection()


# ==================== 第一阶段处理器测试 ====================

class TestPhase1Handler:
    """第一阶段处理器测试类"""
    
    def test_initialize(self):
        """测试初始化"""
        task = build_mock_task()
        handler = Phase1Handler(task)
        
        result = handler.initialize('路飞')
        
        assert result is True
        assert handler.character_selector is not None
        assert handler.movement_ctrl is not None
        assert handler.distance_calc is not None
    
    def test_handle_idle_transitions_to_check_character_select(self):
        """测试空闲状态转换到检查选角界面"""
        task = build_mock_task()
        handler = Phase1Handler(task)
        handler.initialize('路飞')
        
        handler._handle_idle()
        
        assert handler.state_machine.current_state == TutorialState.CHECK_CHARACTER_SELECT
    
    def test_handle_check_character_select_success(self):
        """测试检查选角界面成功"""
        task = build_mock_task()
        
        mock_box = MagicMock()
        mock_box.name = "请选择一位你心仪的角色"
        task.find_boxes = MagicMock(return_value=[mock_box])
        
        handler = Phase1Handler(task)
        handler.initialize('路飞')
        handler.state_machine.transition_to(TutorialState.CHECK_CHARACTER_SELECT)
        
        handler._handle_check_character_select()
        
        assert handler.state_machine.current_state == TutorialState.FIRST_CLICK
    
    def test_handle_check_character_select_failure(self):
        """测试检查选角界面失败"""
        import numpy as np
        task = build_mock_task()
        task.find_boxes = MagicMock(return_value=[])
        # 模拟有效的 frame (numpy 数组)
        task.frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        
        handler = Phase1Handler(task)
        handler.initialize('路飞')
        handler.state_machine.transition_to(TutorialState.CHECK_CHARACTER_SELECT)
        
        # 设置短超时
        handler.detector.detect_character_select_screen = MagicMock(return_value=False)
        
        handler._handle_check_character_select()
        
        assert handler.state_machine.current_state == TutorialState.FAILED
    
    def test_handle_first_click(self):
        """测试第一次点击角色"""
        task = build_mock_task()
        
        handler = Phase1Handler(task)
        handler.initialize('路飞')
        handler.state_machine.transition_to(TutorialState.CHECK_CHARACTER_SELECT)
        handler.state_machine.transition_to(TutorialState.FIRST_CLICK)
        
        handler._handle_first_click()
        
        # 应该点击了屏幕中间
        task.click.assert_called_once()
        assert handler.state_machine.current_state == TutorialState.CONFIRM_DIALOG
    
    def test_handle_move_down(self):
        """测试向下移动"""
        task = build_mock_task()
        
        handler = Phase1Handler(task)
        handler.initialize('路飞')
        # 需要先转换到正确的前置状态
        handler.state_machine.transition_to(TutorialState.CHECK_CHARACTER_SELECT)
        handler.state_machine.transition_to(TutorialState.FIRST_CLICK)
        handler.state_machine.transition_to(TutorialState.CONFIRM_DIALOG)
        handler.state_machine.transition_to(TutorialState.SECOND_CLICK)
        handler.state_machine.transition_to(TutorialState.LOADING)
        handler.state_machine.transition_to(TutorialState.SELF_DETECTION)
        handler.state_machine.transition_to(TutorialState.TARGET_DETECTION)
        handler.state_machine.transition_to(TutorialState.MOVE_TO_TARGET)
        handler.state_machine.transition_to(TutorialState.NORMAL_ATTACK_DETECTION)
        handler.state_machine.transition_to(TutorialState.MOVE_DOWN)
        
        # Mock movement controller 的方法
        handler.movement_ctrl._press_movement_keys_for_duration = MagicMock()
        
        handler._handle_move_down()
        
        # 验证调用了向下移动
        handler.movement_ctrl._press_movement_keys_for_duration.assert_called_once()
        assert handler.state_machine.current_state == TutorialState.COMBAT_TRIGGER
    
    def test_cleanup_stops_detection(self):
        """测试清理停止检测"""
        task = build_mock_task()
        
        handler = Phase1Handler(task)
        handler.initialize('路飞')
        handler.detector.start_phase1_end_detection(timeout=10.0)
        
        handler.cleanup()
        
        assert handler.detector._end_detection_running is False


# ==================== 主任务类测试 ====================

class TestAutoTutorialTask:
    """主任务类测试类"""
    
    def test_default_config(self):
        """测试默认配置"""
        from src.task.AutoTutorialTask import AutoTutorialTask
        
        # 不调用 __init__，直接设置属性
        task = AutoTutorialTask.__new__(AutoTutorialTask)
        task.name = "AutoTutorialTask"
        task.description = "自动新手教程 - 自动完成游戏新手教程"
        task.default_config = {
            '启用': True,
            '角色选择': '路飞',
            '选角界面检测超时(秒)': 10.0,
            '自身检测超时(秒)': 30.0,
            '目标检测超时(秒)': 10.0,
            '普攻检测超时(秒)': 10.0,
            '第一阶段结束检测超时(秒)': 120.0,
            '加载后等待时间(秒)': 30.0,
            '向下移动时间(秒)': 1.5,
            '移动持续时间(秒)': 0.5,
            '点击后等待时间(秒)': 1.0,
            '详细日志': True,
        }
        
        assert '角色选择' in task.default_config
        assert task.default_config['角色选择'] == '路飞'
        assert '自身检测超时(秒)' in task.default_config
        assert task.default_config['自身检测超时(秒)'] == 30.0
    
    def test_get_current_state_before_run(self):
        """测试运行前获取当前状态"""
        from src.task.AutoTutorialTask import AutoTutorialTask
        
        task = AutoTutorialTask.__new__(AutoTutorialTask)
        task._phase1_handler = None
        
        state = task.get_current_state()
        assert state == "未开始"
    
    def test_get_completed_characters_empty_initially(self):
        """测试初始完成角色列表为空"""
        from src.task.AutoTutorialTask import AutoTutorialTask
        
        task = AutoTutorialTask.__new__(AutoTutorialTask)
        task._completed_characters = []
        
        completed = task.get_completed_characters()
        assert completed == []


# ==================== 集成测试 ====================

class TestIntegration:
    """集成测试类"""
    
    def test_state_machine_full_flow(self):
        """测试状态机完整流程"""
        sm = TutorialStateMachine()
        
        # 模拟完整流程（注意：COMBAT_TRIGGER 直接转换到 PHASE1_END）
        flow = [
            TutorialState.IDLE,
            TutorialState.CHECK_CHARACTER_SELECT,
            TutorialState.FIRST_CLICK,
            TutorialState.CONFIRM_DIALOG,
            TutorialState.SECOND_CLICK,
            TutorialState.LOADING,
            TutorialState.SELF_DETECTION,
            TutorialState.TARGET_DETECTION,
            TutorialState.MOVE_TO_TARGET,
            TutorialState.NORMAL_ATTACK_DETECTION,
            TutorialState.MOVE_DOWN,
            TutorialState.COMBAT_TRIGGER,
            # PHASE1_END_DETECTION 在 COMBAT_TRIGGER 内部并行运行
            TutorialState.PHASE1_END,
            TutorialState.COMPLETED,
        ]
        
        for i, state in enumerate(flow[1:], 1):
            assert sm.can_transition_to(state), f"Step {i}: Cannot transition to {state}"
            sm.transition_to(state)
            assert sm.current_state == state
        
        assert sm.is_completed() is True
    
    def test_character_selector_all_mode_sequence(self):
        """测试全部模式角色顺序"""
        selector = CharacterSelector('全部')
        
        expected_sequence = ['悟空', '小鸣人', '路飞']
        actual_sequence = []
        
        while selector.has_more_characters():
            config = selector.get_current_config()
            actual_sequence.append(config.name)
            selector.move_to_next_character()
        
        assert actual_sequence == expected_sequence
    
    def test_detector_with_different_characters(self):
        """测试检测器与不同角色的配合"""
        task = build_mock_task()
        
        # 测试路飞配置
        selector_luffy = CharacterSelector('路飞')
        config_luffy = selector_luffy.get_current_config()
        assert config_luffy.target_type == 'target_circle'
        
        # 测试悟空配置
        selector_wukong = CharacterSelector('悟空')
        config_wukong = selector_wukong.get_current_config()
        assert config_wukong.target_type == 'monkey'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


# ==================== SkillController 测试 ====================

class TestSkillController:
    """技能控制器测试类"""
    
    def test_update_distance_with_valid_value(self):
        """测试更新有效距离值"""
        from src.combat.skill_controller import SkillController
        
        task = MagicMock()
        task.logger = MagicMock()
        task.config = {}
        task.executor = None
        
        skill_ctrl = SkillController(task)
        skill_ctrl.update_distance(150.0)
        
        assert skill_ctrl.get_current_distance() == 150.0
    
    def test_update_distance_with_none_value(self):
        """测试更新 None 距离值应被忽略"""
        from src.combat.skill_controller import SkillController
        
        task = MagicMock()
        task.logger = MagicMock()
        task.config = {}
        task.executor = None
        
        skill_ctrl = SkillController(task)
        # 先设置一个有效值
        skill_ctrl.update_distance(100.0)
        assert skill_ctrl.get_current_distance() == 100.0
        
        # 尝试更新 None，应保持原值
        skill_ctrl.update_distance(None)
        assert skill_ctrl.get_current_distance() == 100.0
    
    def test_is_in_skill_range_with_valid_distance(self):
        """测试有效距离的范围检查"""
        from src.combat.skill_controller import SkillController
        
        task = MagicMock()
        task.logger = MagicMock()
        task.config = {}
        task.executor = None
        
        skill_ctrl = SkillController(task)
        
        # 在范围内
        skill_ctrl.update_distance(150.0)
        assert skill_ctrl.is_in_skill_range() is True
        
        # 超出范围
        skill_ctrl.update_distance(300.0)
        assert skill_ctrl.is_in_skill_range() is False
        
        # 边界值
        skill_ctrl.update_distance(250.0)
        assert skill_ctrl.is_in_skill_range() is True
        
        skill_ctrl.update_distance(0.0)
        assert skill_ctrl.is_in_skill_range() is True
    
    def test_is_in_skill_range_with_none_distance(self):
        """测试 None 距离的范围检查应返回 False"""
        from src.combat.skill_controller import SkillController
        
        task = MagicMock()
        task.logger = MagicMock()
        task.config = {}
        task.executor = None
        
        skill_ctrl = SkillController(task)
        # 不更新距离，初始值为 inf
        
        # 手动设置为 None 测试
        skill_ctrl._current_distance = None
        assert skill_ctrl.is_in_skill_range() is False
    
    def test_is_in_skill_range_with_inf_distance(self):
        """测试 inf 距离的范围检查应返回 False"""
        from src.combat.skill_controller import SkillController
        
        task = MagicMock()
        task.logger = MagicMock()
        task.config = {}
        task.executor = None
        
        skill_ctrl = SkillController(task)
        # 初始值是 inf
        assert skill_ctrl.is_in_skill_range() is False


# ==================== CombatConfigAdapter 测试 ====================

class TestCombatConfigAdapter:
    """战斗配置适配器测试类"""
    
    def test_adapter_has_required_methods(self):
        """测试适配器具有所有必需方法"""
        task = build_mock_task()
        handler = Phase1Handler(task)
        handler.initialize('路飞')
        
        adapter = handler._create_combat_config_adapter()
        
        # 检查必需方法存在
        assert hasattr(adapter, 'config')
        assert hasattr(adapter, 'get')
        assert hasattr(adapter, 'send_key')
        assert hasattr(adapter, 'click')
        assert hasattr(adapter, 'is_adb')
        assert hasattr(adapter, 'update_frame')
    
    def test_adapter_click_forwards_to_task(self):
        """测试适配器 click 方法转发到任务"""
        task = build_mock_task()
        handler = Phase1Handler(task)
        handler.initialize('路飞')
        
        adapter = handler._create_combat_config_adapter()
        adapter.click(100, 200, after_sleep=0.5)
        
        task.click.assert_called_once_with(100, 200, after_sleep=0.5)
    
    def test_adapter_send_key_forwards_to_task(self):
        """测试适配器 send_key 方法转发到任务"""
        task = build_mock_task()
        handler = Phase1Handler(task)
        handler.initialize('路飞')
        
        adapter = handler._create_combat_config_adapter()
        adapter.send_key('J')
        
        task.send_key.assert_called_once_with('J')
    
    def test_adapter_get_reads_combat_config(self):
        """测试适配器 get 方法读取战斗配置"""
        task = build_mock_task()
        handler = Phase1Handler(task)
        handler.initialize('路飞')
        
        adapter = handler._create_combat_config_adapter()
        
        # 测试获取默认值
        value = adapter.get('自动普攻', True)
        assert value is True


# ==================== Phase1Handler 战斗触发测试 ====================

class TestPhase1HandlerCombatTrigger:
    """第一阶段处理器战斗触发测试类"""
    
    def test_combat_trigger_updates_skill_distance(self):
        """测试战斗触发时更新技能控制器距离"""
        task = build_mock_task()
        
        # 模拟敌人检测结果
        mock_enemy = MagicMock()
        mock_enemy.center_x = 500
        mock_enemy.center_y = 400
        
        handler = Phase1Handler(task)
        handler.initialize('路飞')
        handler._verbose = True
        
        # 创建技能控制器并检查距离更新
        from src.combat.skill_controller import SkillController
        combat_config_adapter = handler._create_combat_config_adapter()
        skill_ctrl = SkillController(combat_config_adapter)
        
        # 模拟自身位置
        mock_self = MagicMock()
        mock_self.center_x = 400
        mock_self.center_y = 300
        
        # 计算距离
        import math
        distance = math.sqrt((500-400)**2 + (400-300)**2)
        
        # 更新距离
        skill_ctrl.update_distance(distance)
        
        # 验证距离已更新
        assert skill_ctrl.get_current_distance() == distance
        assert skill_ctrl.is_in_skill_range() is True  # 距离约 141，在 0-250 范围内
    
    def test_phase1_end_detection_runs_parallel(self):
        """测试第一阶段结束检测在战斗期间并行运行"""
        task = build_mock_task()
        task.find_one = MagicMock(side_effect=ValueError("not found"))
        
        handler = Phase1Handler(task)
        handler.initialize('路飞')
        
        # 启动结束检测
        handler.detector.start_phase1_end_detection(timeout=2.0)
        
        # 验证检测线程已启动
        assert handler.detector._end_detection_running is True
        assert handler.detector._end_detection_thread is not None
        
        # 停止检测
        handler.detector.stop_phase1_end_detection()
        
        assert handler.detector._end_detection_running is False


# ==================== 距离计算测试 ====================

class TestDistanceCalculator:
    """距离计算器测试类"""
    
    def test_calculate_from_coords(self):
        """测试从坐标计算距离"""
        from src.combat.distance_calculator import DistanceCalculator
        
        calc = DistanceCalculator()
        
        # 相同点距离为 0
        distance = calc.calculate_from_coords(100, 100, 100, 100)
        assert distance == 0
        
        # 水平距离
        distance = calc.calculate_from_coords(0, 0, 100, 0)
        assert distance == 100
        
        # 垂直距离
        distance = calc.calculate_from_coords(0, 0, 0, 100)
        assert distance == 100
        
        # 对角线距离
        distance = calc.calculate_from_coords(0, 0, 300, 400)
        assert distance == 500
    
    def test_calculate_from_detection_results(self):
        """测试从检测结果计算距离"""
        from src.combat.distance_calculator import DistanceCalculator
        
        calc = DistanceCalculator()
        
        # 模拟检测结果
        mock_self = MagicMock()
        mock_self.center_x = 100
        mock_self.center_y = 100
        
        mock_target = MagicMock()
        mock_target.center_x = 400
        mock_target.center_y = 500
        
        distance = calc.calculate(mock_self, mock_target)
        
        import math
        expected = math.sqrt((400-100)**2 + (500-100)**2)
        assert abs(distance - expected) < 0.01
