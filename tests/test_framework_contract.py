# -*- coding: utf-8 -*-
"""
ok-script 2.x 框架契约测试。

这些测试守护"补丁退役决策"的前提条件:一旦上游行为变化
(如 stop_clicked 不再 unpause、模块路径再次迁移、ok-script 版本回退),
对应测试立刻失败,提示需要重新评估 src/compat/patches.py。
"""

import importlib.metadata as md
import importlib.util
import inspect

import pytest


class TestFrameworkVersion:
    """框架版本契约"""

    def test_ok_script_at_least_2_0_5(self):
        version = md.version('ok-script')
        major, minor, patch_ = (int(x) for x in version.split('.')[:3])
        assert (major, minor, patch_) >= (2, 0, 5), \
            f"ok-script {version} < 2.0.5,补丁层按 2.x 设计"

    def test_requirements_pinned(self):
        line = None
        with open('requirements.txt', encoding='utf-8') as f:
            for l in f:
                if l.strip().startswith('ok-script'):
                    line = l.strip()
                    break
        assert line is not None, 'requirements.txt 缺少 ok-script 依赖'
        assert line.startswith('ok-script[ocr,qt]=='), \
            f'ok-script 必须带 [ocr,qt] extras 并精确锁版,当前: {line}'


class TestModulePaths:
    """2.x 模块路径契约(路径再迁移时第一时间暴露)"""

    def test_core_modules_importable(self):
        from ok.core.start_controller import StartController  # noqa: F401
        from ok.core.events import communicate  # noqa: F401
        from ok.core.notifications import alert_error, alert_info  # noqa: F401

    def test_ui_modules_importable(self):
        from ok.ui.qt.start import StartTab  # noqa: F401
        from ok.ui.qt.tasks.TaskCard import TaskCard as TaskCardClass  # noqa: F401

    def test_task_modules_importable(self):
        from ok.task.task import BaseTask, TriggerTask  # noqa: F401
        from ok.task.TaskExecutor import TaskExecutor  # noqa: F401

    def test_legacy_intercation_alias_still_works(self):
        # ok-jump 的 mixins.py 使用 1.x 的拼写别名 intercation
        from ok.device.intercation import ADBInteraction  # noqa: F401

    def test_task_executor_is_pure_python(self):
        """TaskExecutor 不再是 Cython 编译类(可 patch,未来可迁移回 executor)"""
        import ok.task.TaskExecutor as te_module
        assert te_module.__file__.endswith('.py'), \
            'TaskExecutor 又变回编译实现了,请重新评估 Unity 绕行方案'


class TestRetiredPatchAssumptions:
    """已退役补丁的前提条件守护"""

    def test_stop_clicked_still_disables_and_unpauses(self):
        from ok.ui.qt.tasks.TaskCard import TaskCard
        src = inspect.getsource(TaskCard.stop_clicked)
        assert 'disable' in src and 'unpause' in src, \
            'stop_clicked 不再包含 disable+unpause,需重新引入 ok-jump 的停止修复补丁'

    def test_safe_file_handler_guards_closed_stream(self):
        from ok.util.logger import SafeFileHandler
        src = inspect.getsource(SafeFileHandler.emit)
        assert 'closed' in src, \
            'SafeFileHandler.emit 不再保护关闭的流,需重新引入日志静音补丁'

    def test_do_start_queues_contended_task(self):
        from ok.core.start_controller import StartController
        src = inspect.getsource(StartController._do_start)
        assert 'queue task' in src, \
            '_do_start 不再原生排队任务,需重新引入 executor 争用绕行'

    def test_alert_helpers_available(self):
        from ok.core import notifications
        assert callable(notifications.alert_error)
        assert callable(notifications.alert_info)


class TestAppUsesCompatLayer:
    """应用装配契约:main.py 不再内联补丁"""

    def test_main_is_thin(self):
        src = open('main.py', encoding='utf-8').read()
        assert 'from src.compat import' in src
        # 补丁细节全部收敛在 compat 层
        assert 'def patch_' not in src
        assert len(src.splitlines()) < 120, \
            f'main.py 应保持精简装配,当前 {len(src.splitlines())} 行'

    def test_compat_patches_docstring_documents_retirement(self):
        doc = __import__('src.compat.patches', fromlist=['']).__doc__
        for kw in ['SafeFileHandler', 'stop_clicked', 'do_start', 'Unity']:
            assert kw in doc, f'补丁模块文档缺少 {kw} 的退役/保留说明'
