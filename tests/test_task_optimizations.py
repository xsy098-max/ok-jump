# -*- coding: utf-8 -*-
"""
任务层优化测试:验证对照 ok-wuthering-waves 用法落地的优化点。

- 触发任务节奏(trigger_interval > 0,AST 结构校验)
- 后台模式守卫(伪最小化窗口不被框架自动回正)
- wait_until 委托框架实现(settle_time=0 保持立即返回语义)
- config 契约(start_timeout、死配置移除)
- 任务代码不再使用不响应暂停的裸 time.sleep
"""

import ast
from unittest.mock import MagicMock, patch

import pytest

from src.compat import patches


def _find_init_assignment(file_path, class_name, attr):
    """在指定类的 __init__ 中查找 self.<attr> = <数值> 赋值,返回值"""
    tree = ast.parse(open(file_path, encoding='utf-8').read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in ast.walk(node):
                if (isinstance(item, ast.Assign)
                        and isinstance(item.targets[0], ast.Attribute)
                        and item.targets[0].attr == attr
                        and isinstance(item.value, ast.Constant)):
                    return item.value.value
    return None


class TestTriggerIntervals:
    """触发任务必须有触发间隔(对齐 ok-ww,防止 interval=0 全速轮询)"""

    def test_auto_combat_task_interval(self):
        v = _find_init_assignment('src/task/AutoCombatTask.py', 'AutoCombatTask', 'trigger_interval')
        assert v is not None and 0 < v <= 1, \
            f'AutoCombatTask.trigger_interval 应在 (0,1] 秒,当前: {v}'

    def test_auto_combat_unity_interval(self):
        v = _find_init_assignment(
            'src/task/AutoCombatTaskUnity.py', 'AutoCombatTaskUnity', 'trigger_interval')
        assert v is not None and 0 < v <= 2, \
            f'AutoCombatTaskUnity.trigger_interval 应在 (0,2] 秒,当前: {v}'


class TestBackgroundModeGuard:
    """后台模式守卫:伪最小化(屏幕外)窗口不被 2.0.5 的自动回正破坏"""

    @pytest.fixture(autouse=True)
    def _apply_patches(self):
        patches.patch_start_controller()

    def _og_with_window(self, pos_valid):
        og = MagicMock()
        og.config = {'windows': {'skip_pos_check': True}}
        og.device_manager.capture_method.hwnd_window.pos_valid = pos_valid
        return og

    def _get_patched(self):
        from ok.core.start_controller import StartController
        return StartController.check_device_error

    def test_offscreen_window_skips_original_check(self):
        patched = self._get_patched()
        original = MagicMock(return_value='should not be called')

        with patch.object(patches, '_is_unity_active', return_value=False), \
                patch.object(patches, 'og', self._og_with_window(pos_valid=False)), \
                patch.object(patched, '__ok_jump_orig__', original):
            result = patched(MagicMock())

        assert result is None
        original.assert_not_called()

    def test_onscreen_window_runs_original_check(self):
        patched = self._get_patched()
        original = MagicMock(return_value='device ok')

        with patch.object(patches, '_is_unity_active', return_value=False), \
                patch.object(patches, 'og', self._og_with_window(pos_valid=True)), \
                patch.object(patched, '__ok_jump_orig__', original):
            result = patched(MagicMock())

        assert result == 'device ok'
        original.assert_called_once()

    def test_guard_inactive_without_skip_pos_check(self):
        patched = self._get_patched()
        original = MagicMock(return_value='some error')
        og = self._og_with_window(pos_valid=False)
        og.config = {'windows': {'skip_pos_check': False}}

        with patch.object(patches, '_is_unity_active', return_value=False), \
                patch.object(patches, 'og', og), \
                patch.object(patched, '__ok_jump_orig__', original):
            result = patched(MagicMock())

        assert result == 'some error'
        original.assert_called_once()


class TestWaitUntilDelegation:
    """BaseJumpTask.wait_until 委托框架 wait_condition"""

    def _make_task(self):
        from src.task.BaseJumpTask import BaseJumpTask
        task = BaseJumpTask.__new__(BaseJumpTask)
        # executor 是只读 property,底层是 _executor
        task._executor = MagicMock()
        return task

    def test_delegates_with_immediate_return_semantics(self):
        task = self._make_task()
        sentinel = object()
        task._executor.wait_condition.return_value = sentinel

        result = task.wait_until(lambda: True, time_out=5)

        assert result is sentinel
        # settle_time=0:保持 ok-jump 立即返回语义(框架默认需稳定 1s)
        _, kwargs = task._executor.wait_condition.call_args
        assert kwargs.get('settle_time') == 0

    def test_timeout_returns_none_without_raise(self):
        task = self._make_task()
        task._executor.wait_condition.side_effect = TimeoutError('timeout')

        assert task.wait_until(lambda: None, time_out=0.1) is None

    def test_timeout_raises_when_requested(self):
        task = self._make_task()
        task._executor.wait_condition.side_effect = TimeoutError('timeout')

        with pytest.raises(TimeoutError):
            task.wait_until(lambda: None, time_out=0.1, raise_if_not_found=True)


class TestConfigContract:

    def test_start_timeout_extended(self):
        import sys
        sys.path.insert(0, '.')
        from config import config
        assert config.get('start_timeout') == 120, \
            '游戏冷启动慢,启动超时应为 120 秒(对齐 ok-ww)'

    def test_dead_trigger_interval_option_removed(self):
        import sys
        sys.path.insert(0, '.')
        from config import basic_config_option
        assert '触发间隔' not in basic_config_option.default_config, \
            '死配置「触发间隔」应移除(生效的是框架 Basic Options 的 Trigger Interval)'


class TestNoRawSleepInSimpleTasks:
    """简单任务的 sleep 必须经由 self.sleep(响应暂停/停止)"""

    FILES = [
        'src/task/DailyTask.py',
        'src/task/AutoMatchTask.py',
        'src/task/TestAllInOneTask.py',
    ]

    @pytest.mark.parametrize('path', FILES)
    def test_no_raw_time_sleep(self, path):
        src = open(path, encoding='utf-8').read()
        assert 'time.sleep(' not in src, \
            f'{path} 存在不响应暂停的裸 time.sleep,应使用 self.sleep'


class TestFrameworkGuard:
    """运行时版本守卫:用错解释器时给出可操作的指引而非堆栈"""

    def test_passes_on_healthy_env(self):
        from src.compat.patches import enforce_ok_script_compat
        enforce_ok_script_compat()  # 当前 venv 为 2.0.5,不应抛异常

    def test_fails_with_actionable_message(self, monkeypatch):
        import sys
        from src.compat import patches

        fake_md = MagicMock()
        fake_md.version.return_value = '1.0.68'
        monkeypatch.setattr('importlib.metadata.version', fake_md.version)

        with pytest.raises(RuntimeError) as exc_info:
            patches.enforce_ok_script_compat()

        msg = str(exc_info.value)
        assert '1.0.68' in msg                       # 暴露实际检测到的版本
        assert '.venv' in msg                        # 给出正确启动方式
        assert 'ok-script[ocr,qt]==2.0.5' in msg     # 给出安装命令
        assert sys.executable in msg                 # 指明当前用错了哪个解释器

    def test_fails_when_core_module_missing(self, monkeypatch):
        from src.compat import patches

        fake_md = MagicMock()
        fake_md.version.return_value = '2.0.5'
        monkeypatch.setattr('importlib.metadata.version', fake_md.version)
        monkeypatch.setitem(__import__('sys').modules,
                            'ok.core.start_controller', None)  # 强制导入失败

        with pytest.raises(RuntimeError) as exc_info:
            patches.enforce_ok_script_compat()

        assert '关键模块缺失' in str(exc_info.value)


class TestUpdateCardSourceMode:
    """源码模式下应用内更新检查应静默降级而非刷 ERROR"""

    def _make_card(self):
        card = MagicMock()
        card._busy = False
        return card

    def test_skips_check_when_not_packaged(self, monkeypatch):
        import pyappify
        from ok.ui.qt.about.UpdateCard import UpdateCard
        from src.compat.patches import patch_update_card_source_mode

        monkeypatch.setattr(pyappify, 'app_version', None)
        monkeypatch.setattr(pyappify, 'pyappify_version', None)
        patch_update_card_source_mode()

        original = MagicMock()
        UpdateCard.check_for_updates.__ok_jump_orig__ = original
        card = self._make_card()

        UpdateCard.check_for_updates(card)

        original.assert_not_called()          # 不发后台检查线程
        card._set_status.assert_called_once() # 卡片给出静态说明

    def test_delegates_when_packaged(self, monkeypatch):
        import pyappify
        from ok.ui.qt.about.UpdateCard import UpdateCard
        from src.compat.patches import patch_update_card_source_mode

        monkeypatch.setattr(pyappify, 'app_version', '1.8.0')
        monkeypatch.setattr(pyappify, 'pyappify_version', '1.0.13')
        patch_update_card_source_mode()

        calls = []

        def fake_original(self):
            calls.append(1)
            return 'delegated'

        UpdateCard.check_for_updates.__ok_jump_orig__ = fake_original

        result = UpdateCard.check_for_updates(self._make_card())

        assert result == 'delegated' and len(calls) == 1
