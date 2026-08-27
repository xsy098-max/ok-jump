# -*- coding: utf-8 -*-
"""
src/compat 兼容层测试:验证每个框架补丁在 ok-script 2.x 上的应用与行为。

覆盖:
- check_device_error 三种跳过路径(自管理任务 / Unity / skip_pos_check)
- adb_connect 超时降级(不抛异常)
- Unity 虚拟设备注入与移除
- Unity 任务线程绕行启动
- Unity 触发循环的异常告警与熔断
- 日志导出重定向
- 日志噪音过滤器
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from src.compat import patches, startup


# ---------------------------------------------------------------------------
# check_device_error 跳过逻辑
# ---------------------------------------------------------------------------

class _FakeController:
    """最小 StartController 替身,仅携带补丁访问的属性"""

    def __init__(self, current_task=None):
        self.current_task = current_task
        self.original_called = False

    def original_check_device_error(self):
        self.original_called = True
        return 'Device not connected'


class TestCheckDeviceErrorSkip:
    """StartController.check_device_error 补丁的三种跳过路径"""

    @pytest.fixture(autouse=True)
    def _apply_patches(self):
        # 测试进程未走 main.py,需先应用补丁
        patches.patch_start_controller()

    def _get_patched(self):
        from ok.core.start_controller import StartController
        return StartController.check_device_error

    def test_skips_self_managed_task(self):
        patched = self._get_patched()
        task = MagicMock()
        task.__class__.__name__ = 'CITestTask'
        ctrl = _FakeController(current_task=task)

        with patch.object(patches, '_is_unity_active', return_value=False), \
                patch.object(og_config := patches, 'og', _og_with_config({'skip_pos_check': False})):
            result = patched(ctrl, )

        assert result is None
        assert ctrl.original_called is False

    def test_skips_when_unity_active(self):
        patched = self._get_patched()
        ctrl = _FakeController()

        with patch.object(patches, '_is_unity_active', return_value=True):
            result = patched(ctrl)

        assert result is None
        assert ctrl.original_called is False

    def test_skip_pos_check_allows_minimized_window(self):
        patched = self._get_patched()
        message = "Window is minimized or out of screen, and don't use full-screen exclusive mode!"
        patched.__ok_jump_orig__ = lambda self: message

        with patch.object(patches, '_is_unity_active', return_value=False), \
                patch.object(patches, 'og', _og_with_config({'skip_pos_check': True})):
            result = patched(_FakeController())

        assert result is None

    def test_other_errors_pass_through(self):
        patched = self._get_patched()
        ctrl = _FakeController()
        patched.__ok_jump_orig__ = lambda self: ctrl.original_check_device_error()

        with patch.object(patches, '_is_unity_active', return_value=False), \
                patch.object(patches, 'og', _og_with_config({'skip_pos_check': True})):
            result = patched(ctrl)

        assert result == 'Device not connected'
        assert ctrl.original_called is True

    def test_minimized_error_returned_when_skip_disabled(self):
        patched = self._get_patched()
        message = "Window is minimized or out of screen!"
        patched.__ok_jump_orig__ = lambda self: message

        with patch.object(patches, '_is_unity_active', return_value=False), \
                patch.object(patches, 'og', _og_with_config({'skip_pos_check': False})):
            result = patched(_FakeController())

        assert result == message


class _FakeOg:
    """带 windows 配置的 og 替身"""

    def __init__(self, windows_config):
        self.config = {'windows': windows_config}


def _og_with_config(windows_config):
    return _FakeOg(windows_config)


# ---------------------------------------------------------------------------
# adb_connect 日志降级
# ---------------------------------------------------------------------------

class TestAdbConnectLogging:

    def test_timeout_does_not_raise(self):
        from adbutils import AdbTimeout
        from ok.device.DeviceManager import DeviceManager

        dm = MagicMock(spec=DeviceManager)
        dm.adb.list.side_effect = AdbTimeout('adb connect timeout')

        # 2.0.5 的 patched 函数签名 (self, addr, try_connect=True)
        DeviceManager.adb_connect(dm, '127.0.0.1:5555')
        # 无异常即通过:超时被降级为 DEBUG 而非向上抛出

    def test_unexpected_error_does_not_raise(self):
        from ok.device.DeviceManager import DeviceManager

        dm = MagicMock(spec=DeviceManager)
        dm.adb.list.side_effect = RuntimeError('boom')

        DeviceManager.adb_connect(dm, '127.0.0.1:5555')


# ---------------------------------------------------------------------------
# Unity 虚拟设备注入
# ---------------------------------------------------------------------------

class TestUnityDeviceInjection:

    @pytest.fixture(autouse=True)
    def _apply_patches(self):
        patches.patch_device_manager_for_unity()

    def _fake_dm(self):
        dm = MagicMock()
        dm.device_dict = {}
        dm.exit_event = MagicMock()
        dm.exit_event.is_set.return_value = False
        return dm

    def test_port_closed_removes_unity_device(self):
        from ok.device.DeviceManager import DeviceManager

        dm = self._fake_dm()
        dm.device_dict['unity'] = {'nick': 'stale'}

        with patch('socket.socket') as mock_socket_cls,                 patch.object(patches, '_auto_enable_correct_combat_task'):
            sock = mock_socket_cls.return_value
            sock.connect_ex.return_value = 1  # 端口不可达
            DeviceManager.do_refresh(dm)

        assert 'unity' not in dm.device_dict

    def test_port_open_injects_unity_device(self):
        from ok.device.DeviceManager import DeviceManager

        dm = self._fake_dm()

        with patch('socket.socket') as mock_socket_cls, \
                patch.object(patches, '_auto_enable_correct_combat_task'):
            sock = mock_socket_cls.return_value
            sock.connect_ex.return_value = 0  # 端口可达
            DeviceManager.do_refresh(dm)

        entry = dm.device_dict.get('unity')
        assert entry is not None
        # device 字段必须用框架已知的 "windows":StartTab 按它选类型标签,
        # 自定义值会落入 Android 兜底分支,把 Unity Editor 显示成"安卓版"
        assert entry['device'] == 'windows'
        assert entry['connected'] is True
        assert entry['capture'] == 'windows'
        assert entry['imei'] == 'unity'
        assert entry['nick'] == 'Unity Editor'


# ---------------------------------------------------------------------------
# Unity 任务线程绕行
# ---------------------------------------------------------------------------

class TestUnityBypass:

    def _fake_controller(self):
        ctrl = MagicMock()
        ctrl.start_timeout = 5
        ctrl.tr = str
        ctrl.start_device = MagicMock(return_value=True)
        return ctrl

    def _fake_og(self, task_list=None):
        og = MagicMock()
        og.device_manager.do_refresh = MagicMock()
        og.executor.trigger_tasks = task_list or []
        og.executor.onetime_tasks = []
        og.executor.exit_event = threading.Event()
        return og

    def test_unity_do_start_runs_task_in_thread(self):
        task = MagicMock()
        task.name = 'FakeUnityTask'
        task.run = MagicMock(return_value=True)
        og = self._fake_og()

        with patch.object(patches, 'og', og), \
                patch.object(patches, '_is_unity_active', return_value=True), \
                patch.object(patches, '_auto_enable_correct_combat_task'):
            result = patches._unity_do_start(self._fake_controller(), task)

        assert result is True
        # 独立线程异步执行,短暂等待 run 被调用
        for _ in range(50):
            if task.run.called:
                break
            time.sleep(0.02)
        task.run.assert_called_once()
        task.enable.assert_called_once()

    def test_unity_do_start_starts_enabled_triggers_when_no_task(self):
        t1 = MagicMock()
        t1.name = 'AutoCombatTaskUnity'
        t1._enabled = True
        t2 = MagicMock()
        t2.name = 'Other'
        t2._enabled = False
        og = self._fake_og(task_list=[t1, t2])
        og.executor.exit_event.set()  # 立即退出循环,只验证线程已派发

        with patch.object(patches, 'og', og), \
                patch.object(patches, '_is_unity_active', return_value=True), \
                patch.object(patches, '_auto_enable_correct_combat_task'), \
                patch.object(patches, '_unity_trigger_loop') as mock_loop:
            result = patches._unity_do_start(self._fake_controller(), None)

        assert result is True
        assert mock_loop.call_count == 1
        assert mock_loop.call_args[0][0] is t1

    def test_trigger_loop_calls_run_when_should_trigger(self):
        task = MagicMock()
        task.name = 'AutoCombatTaskUnity'
        task.should_trigger.side_effect = [True, False]
        task.run = MagicMock(return_value=True)

        og = self._fake_og()
        # 第一次 run 后立即要求退出
        def _set_exit(*a, **k):
            og.executor.exit_event.set()
        task.run.side_effect = _set_exit

        with patch.object(patches, 'og', og), \
                patch.object(patches.time, 'sleep'):
            patches._unity_trigger_loop(task)

        task.run.assert_called_once()

    def test_trigger_loop_alerts_and_stops_after_repeated_errors(self):
        task = MagicMock()
        task.name = 'AutoCombatTaskUnity'
        task.should_trigger.side_effect = ConnectionError('unity gone')

        og = self._fake_og()

        with patch.object(patches, 'og', og), \
                patch.object(patches.time, 'sleep'), \
                patch.object(patches, '_alert_unity_unhealthy') as mock_unhealthy, \
                patch.object(patches, '_alert_unity_disconnected') as mock_disconnected:
            patches._unity_trigger_loop(task)

        # 连续 5 次异常触发健康告警,20 次触发断连告警并退出
        assert mock_unhealthy.call_count == 1
        assert mock_disconnected.call_count == 1


# ---------------------------------------------------------------------------
# 日志导出重定向与过滤器
# ---------------------------------------------------------------------------

class TestExportLogsPatch:

    def test_start_tab_export_logs_redirected(self, tmp_path, monkeypatch):
        from ok.ui.qt.start import StartTab

        monkeypatch.setattr(startup.og, 'config', {'gui_title': '测试应用'})
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'logs').mkdir()
        (tmp_path / 'logs' / 'ok-jump.log').write_text('hello', encoding='utf-8')

        with patch('subprocess.Popen') as mock_popen:
            patches.patch_export_logs(startup.export_logs)
            # 调用补丁后的静态方法
            StartTab.export_logs()

        mock_popen.assert_called_once()
        zip_arg = mock_popen.call_args[0][0]
        assert '测试应用-log.zip' in zip_arg


class TestLogFilters:

    def test_negative_box_filtered(self):
        f = patches._MessageFilter(['negative box'])
        record = MagicMock()
        record.getMessage.return_value = 'ocr result negative box found'
        assert f.filter(record) is False

    def test_normal_message_passes(self):
        f = patches._MessageFilter(['negative box'])
        record = MagicMock()
        record.getMessage.return_value = 'normal message'
        assert f.filter(record) is True

    def test_bad_record_does_not_crash(self):
        f = patches._MessageFilter(['x'])
        record = MagicMock()
        record.getMessage.side_effect = Exception('boom')
        assert f.filter(record) is True


# ---------------------------------------------------------------------------
# 启动编排:定时调度器
# ---------------------------------------------------------------------------

class TestScheduledTaskExecutor:

    def test_skips_when_config_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert startup.init_scheduled_task_executor() is None

    def test_skips_when_disabled(self, tmp_path, monkeypatch):
        import json
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'configs').mkdir()
        (tmp_path / 'configs' / 'CITestTask.json').write_text(
            json.dumps({'启用定时执行': False}), encoding='utf-8')
        assert startup.init_scheduled_task_executor() is None
