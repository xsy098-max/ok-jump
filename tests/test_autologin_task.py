from unittest.mock import MagicMock, call, patch, PropertyMock

import pytest
import time

from src.task.AutoLoginTask import AutoLoginInputException, AutoLoginTask


def build_task():
    task = AutoLoginTask.__new__(AutoLoginTask)
    task.config = None
    task.default_config = {
        '输入账号': True,
        '账号': 'demo_user_01',
        '输入后缓冲时间(秒)': 0.8,
        '账号输入重试次数': 2,
        '输入校验超时(秒)': 0.2,
        '登录等待超时(秒)': 60,
        '点击后等待时间(秒)': 3,
    }
    task._account_input_done = False
    task._account_input_finish_time = 0
    task._screenshots_dir = "screenshots"
    task._cached_ocr = None
    task._last_error = None
    task.logger = MagicMock()
    task.log_info = MagicMock()
    task.log_error = MagicMock()
    task.log_warning = MagicMock()
    task.click_relative = MagicMock(return_value=True)
    task.send_key = MagicMock()
    task.sleep = MagicMock()
    task.next_frame = MagicMock()
    task._save_error_screenshot = MagicMock()
    task.find_one = MagicMock(return_value=None)
    task._click_button_by_ocr = MagicMock(return_value=True)
    task.click = MagicMock()
    task._get_screen_size = MagicMock(return_value=(1920, 1080))
    task.input_text = MagicMock()
    task.clipboard = MagicMock(return_value='demo_user_01')
    task.ocr = MagicMock(return_value=[])
    task._set_clipboard = MagicMock(return_value=True)
    task._clear_ocr_cache = MagicMock()
    task.find_boxes = MagicMock(return_value=[])
    task._get_ocr_texts = MagicMock(return_value=[])
    type(task).width = PropertyMock(return_value=1920)
    type(task).height = PropertyMock(return_value=1080)
    return task


def build_wenjuan_task():
    task = build_task()
    return task


class TestWenjuanScreen:
    
    def test_check_wenjuan_screen_template_match_success(self):
        task = build_wenjuan_task()
        task.find_one = MagicMock(return_value=(100, 50))
        
        result = task._check_wenjuan_screen()
        
        assert result is True
        task.find_one.assert_called_once_with('wenjuan_enter', threshold=0.7)
    
    def test_check_wenjuan_screen_template_match_failed_ocr_success(self):
        task = build_wenjuan_task()
        task.find_one = MagicMock(side_effect=ValueError("not found"))
        
        mock_box = MagicMock()
        mock_box.name = "问卷调查"
        task.find_boxes = MagicMock(return_value=[mock_box])
        
        result = task._check_wenjuan_screen()
        
        assert result is True
    
    def test_check_wenjuan_screen_not_found(self):
        task = build_wenjuan_task()
        task.find_one = MagicMock(side_effect=ValueError("not found"))
        task.find_boxes = MagicMock(return_value=[])
        
        result = task._check_wenjuan_screen()
        
        assert result is False
    
    def test_handle_wenjuan_full_flow_success(self):
        task = build_wenjuan_task()
        
        mock_box1 = MagicMock()
        mock_box1.name = "至少有一部动画/漫画作品追到最新剧情"
        mock_box1.x = 490
        mock_box1.y = 353
        mock_box1.width = 500
        mock_box1.height = 30
        
        mock_box2 = MagicMock()
        mock_box2.name = "王者10星及以上"
        mock_box2.x = 492
        mock_box2.y = 389
        mock_box2.width = 500
        mock_box2.height = 30
        
        mock_box3 = MagicMock()
        mock_box3.name = "追求团队胜利、更高的段位和排名"
        mock_box3.x = 492
        mock_box3.y = 417
        mock_box3.width = 500
        mock_box3.height = 30
        
        mock_return = MagicMock()
        mock_return.name = "返回游戏"
        mock_return.x = 100
        mock_return.y = 50
        mock_return.width = 200
        mock_return.height = 40
        
        mock_thanks = MagicMock()
        mock_thanks.name = "感谢您的耐心回答"
        mock_thanks.x = 500
        mock_thanks.y = 600
        mock_thanks.width = 400
        mock_thanks.height = 30
        
        mock_xuanren = MagicMock()
        mock_xuanren.name = "请选择一位你心仪的角色"
        mock_xuanren.x = 500
        mock_xuanren.y = 400
        mock_xuanren.width = 400
        mock_xuanren.height = 30
        
        mock_submit = MagicMock()
        mock_submit.name = "提交"
        mock_submit.x = 900
        mock_submit.y = 800
        mock_submit.width = 100
        mock_submit.height = 40
        
        call_count = [0]
        def find_boxes_side_effect(texts, match=None):
            call_count[0] += 1
            pattern_str = str(match.pattern) if match else ""
            if "返回游戏" in pattern_str:
                return [mock_return]
            elif "至少有一部" in pattern_str:
                return [mock_box1]
            elif "王者10星" in pattern_str:
                return [mock_box2]
            elif "追求团队胜利" in pattern_str:
                return [mock_box3]
            elif "提交" in pattern_str:
                return [mock_submit]
            elif "感谢" in pattern_str:
                return [mock_thanks]
            elif "请选择" in pattern_str:
                return [mock_xuanren]
            return []
        
        task.find_boxes = MagicMock(side_effect=find_boxes_side_effect)
        task.click_relative = MagicMock(return_value=True)
        
        result = task._handle_wenjuan()
        
        assert result is True
        assert task.click_relative.call_count >= 4
    
    def test_handle_wenjuan_wait_return_game_timeout(self):
        task = build_wenjuan_task()
        
        task.find_one = MagicMock(side_effect=ValueError("not found"))
        task.find_boxes = MagicMock(return_value=[])
        
        result = task._handle_wenjuan()
        
        assert result is False
    
    def test_click_wenjuan_option_success(self):
        task = build_wenjuan_task()
        
        mock_box = MagicMock()
        mock_box.name = "至少有一部动画/漫画作品追到最新剧情"
        mock_box.x = 490
        mock_box.y = 353
        mock_box.width = 500
        mock_box.height = 30
        
        task.find_boxes = MagicMock(return_value=[mock_box])
        task.click_relative = MagicMock(return_value=True)
        
        result = task._click_wenjuan_option('wenjuan1', '问卷选项1')
        
        assert result is True
        task.click_relative.assert_called_once()
    
    def test_click_wenjuan_option_timeout(self):
        task = build_wenjuan_task()
        task.find_boxes = MagicMock(return_value=[])
        
        result = task._click_wenjuan_option('wenjuan1', '问卷选项1')
        
        assert result is False


class TestLoginScreen0:
    
    def test_handle_login_screen_0_checkbox_already_checked(self):
        task = build_task()
        task.find_one = MagicMock(side_effect=[
            (100, 50),
            (500, 300),
        ])
        task.click = MagicMock(return_value=True)
        
        result = task._handle_login_screen_0()
        
        assert result is True
        task.click.assert_called_once()
    
    def test_handle_login_screen_0_checkbox_not_checked_click_success(self):
        task = build_task()
        task.find_one = MagicMock(side_effect=[
            None,
            (150, 75),
            (500, 300),
        ])
        task.click = MagicMock(return_value=True)
        
        result = task._handle_login_screen_0()
        
        assert result is True
        assert task.click.call_count == 2


class TestLoginScreen2:
    
    def test_handle_login_screen_2_checkbox_already_checked(self):
        task = build_task()
        task.find_one = MagicMock(side_effect=[
            (100, 50),
            (600, 400),
            ValueError("not found"),
        ])
        task.click = MagicMock(return_value=True)
        task._check_character_selection = MagicMock(return_value=False)
        
        result = task._handle_login_screen_2()
        
        assert result is True
        task.click.assert_called_once()
    
    def test_handle_login_screen_2_detects_character_selection(self):
        task = build_task()
        task.find_one = MagicMock(side_effect=[
            (100, 50),
            (600, 400),
        ])
        task.click = MagicMock(return_value=True)
        task._check_character_selection = MagicMock(return_value=True)
        task.info_set = MagicMock()
        
        result = task._handle_login_screen_2()
        
        assert result is True
        assert task._logged_in is True


class TestCheckLoginSuccess:
    
    def test_check_login_success_with_ocr(self):
        task = build_task()
        task.in_lobby = MagicMock(return_value=False)
        task.in_game = MagicMock(return_value=False)
        task.find_one = MagicMock(side_effect=ValueError("not found"))
        
        mock_role = MagicMock()
        mock_role.name = "角色"
        mock_rank = MagicMock()
        mock_rank.name = "排位赛"
        
        task.find_boxes = MagicMock(side_effect=[
            [mock_role],
            [mock_rank],
        ])
        
        result = task._check_login_success()
        
        assert result is True
    
    def test_check_login_success_empty_list(self):
        task = build_task()
        task.in_lobby = MagicMock(return_value=False)
        task.in_game = MagicMock(return_value=False)
        task.find_one = MagicMock(side_effect=ValueError("not found"))
        task.find_boxes = MagicMock(return_value=[])
        
        result = task._check_login_success()
        
        assert result is False


def test_input_account_visible_and_enabled_success():
    task = build_task()
    account = "demo_user_01"
    task._locate_account_input_box = MagicMock(
        return_value={'x': 600, 'y': 320, 'width': 300, 'height': 50, 'confidence': 0.91}
    )
    task._verify_account_input = MagicMock(return_value=True)

    result = task._input_account(account)

    assert result is True
    task.click_relative.assert_called_once()
    task.send_key.assert_any_call('ctrl', 'a')
    task.send_key.assert_any_call('backspace')
    task.send_key.assert_any_call('tab')

    task._verify_account_input.assert_called_once()


def test_input_account_keyboard_input_every_attempt():
    task = build_task()
    account = "demo_user_01"
    task._locate_account_input_box = MagicMock(
        return_value={'x': 600, 'y': 320, 'width': 300, 'height': 50, 'confidence': 0.91}
    )
    task.default_config['账号输入重试次数'] = 2
    task._verify_account_input = MagicMock(side_effect=[False, True])

    result = task._input_account(account)

    assert result is True
    task.send_key.assert_any_call('ctrl', 'a')
    task.send_key.assert_any_call('backspace')
    task.send_key.assert_any_call('tab')
    
    assert task._verify_account_input.call_count == 2


def test_input_account_not_visible_no_input_sent():
    task = build_task()
    task._locate_account_input_box = MagicMock(return_value=None)

    with pytest.raises(AutoLoginInputException):
        task._input_account("demo_user_01")
    task.click_relative.assert_not_called()
    task.send_key.assert_not_called()
    task._save_error_screenshot.assert_called_once()


def test_login_screen_1_not_checked_skip_input():
    task = build_task()
    task.default_config['输入账号'] = False
    task._input_account = MagicMock()
    task.find_one = MagicMock(return_value=(500, 300))
    result = task._handle_login_screen_1()
    assert result is True
    task._input_account.assert_not_called()
    task.click.assert_called_once()


def test_login_screen_1_respects_gui_config_for_input():
    task = build_task()
    task.default_config['输入账号'] = False
    task.config = MagicMock()
    task.config.get.side_effect = lambda key, default=None: {
        '输入账号': True,
        '账号': 'gui_account_88'
    }.get(key, default)
    task._input_account = MagicMock(return_value=True)
    result = task._handle_login_screen_1()
    assert result is True
    task._input_account.assert_called_once_with('gui_account_88')
    task.click.assert_not_called()
    task._click_button_by_ocr.assert_not_called()


def test_input_account_mismatch_retries_and_raises_exception():
    task = build_task()
    task.default_config['账号输入重试次数'] = 2
    task._locate_account_input_box = MagicMock(
        return_value={'x': 600, 'y': 320, 'width': 300, 'height': 50, 'confidence': 0.91}
    )
    task._verify_account_input = MagicMock(return_value=False)
    with pytest.raises(AutoLoginInputException):
        task._input_account("qwer280")
    task.input_text.assert_not_called()
    assert task.logger.warning.call_count >= 1
    task._save_error_screenshot.assert_called_once()


def test_verify_account_input_success_requires_exact_match():
    task = build_task()
    task.clipboard = MagicMock(return_value="qwer280")
    task.default_config['输入校验超时(秒)'] = 0.2
    result = task._verify_account_input("qwer280")
    assert result is True


def test_verify_account_input_clipboard_mismatch():
    task = build_task()
    task.clipboard = MagicMock(return_value="qwer2981111")
    task.default_config['输入校验超时(秒)'] = 0.2
    task.ocr = MagicMock(return_value=[MagicMock(name="qwer280")])
    result = task._verify_account_input("qwer280")
    assert result is True
