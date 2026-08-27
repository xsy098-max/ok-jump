# -*- coding: utf-8 -*-
"""
GUI 与 i18n 测试:守护 ok-script 2.x 的界面层契约。

- 中文翻译目录:所有英文名任务必须登记 msgid,框架路径可加载
- LogTab 符合 2.x 自定义页签接口(executor 注入 + 导航属性)
"""

import ast
import gettext
from pathlib import Path

import pytest


I18N_DIR = Path('i18n')
CATALOG = I18N_DIR / 'zh_CN' / 'LC_MESSAGES' / 'ok.po'


def _load_catalog():
    return gettext.translation('ok', str(I18N_DIR), languages=['zh_CN'])


class TestChineseCatalog:
    """2.x gettext 翻译目录契约(JSON 机制已在 2.x 移除)"""

    def test_mo_compiled_and_fresh(self):
        po = CATALOG
        mo = po.with_suffix('.mo')
        assert mo.is_file(), 'ok.mo 未编译,运行 python scripts/gen_i18n_mo.py'
        assert mo.stat().st_mtime >= po.stat().st_mtime, \
            'ok.po 比 ok.mo 新,请重新编译: python scripts/gen_i18n_mo.py'

    def test_registered_ascii_task_names_are_translated(self):
        """config.py 注册的任务中,英文名必须有中文映射(否则侧栏显示类名)"""
        import sys
        sys.path.insert(0, '.')
        from config import config

        cat = _load_catalog()
        for module_path, _cls in config['onetime_tasks'] + config['trigger_tasks']:
            name = ast.literal_eval(_extract_assignment(module_path.replace('.', '/') + '.py',
                                                        'self.name'))
            if not name.isascii():
                continue
            translated = cat.gettext(name)
            assert translated != name, \
                f'任务 {name} 缺少中文翻译,请在 {CATALOG} 登记后重新编译'
            assert not translated.isascii() or translated.startswith(('CI', 'Unity')), \
                f'任务 {name} 的译文应为主流中文描述: {translated}'

    def test_framework_loads_catalog_via_its_own_path(self):
        from ok.util.file import get_path_relative_to_exe
        t = gettext.translation('ok', get_path_relative_to_exe('i18n'), languages=['zh_CN'])
        assert t.gettext('DailyTask') == '日常任务'


def _extract_assignment(file_path, target_src):
    """从模块源码提取 `target_src = "字符串"` 的字面量源码"""
    src = Path(file_path).read_text(encoding='utf-8')
    for line in src.splitlines():
        if line.strip().startswith(target_src):
            return line.split('=', 1)[1].strip()
    raise AssertionError(f'{file_path} 中未找到 {target_src}')


class TestLogTabInterface:
    """LogTab 必须符合 2.x 主窗口自定义页签接口

    (ok/ui/qt/MainWindow.py: init_class_by_name 后设置 .executor,
     读取 .add_after_default_tabs/.icon/.name/.position)
    """

    def test_interface_attributes(self):
        from src.gui.log_tab import LogTab
        assert isinstance(getattr(LogTab, 'name'), str) and LogTab.name
        assert LogTab.icon is not None
        assert LogTab.position is not None
        assert isinstance(LogTab.add_after_default_tabs, bool)

    def test_log_panel_handler_interface(self):
        from src.gui.log_panel import GUILogHandler, LogPanel

        # GUILogHandler 是标准 logging.Handler(LogTab 将其挂到 root logger)
        import logging
        assert issubclass(GUILogHandler, logging.Handler)

        # 避免重复添加的判重逻辑依赖精确的类名匹配
        tree = ast.parse(Path('src/gui/log_tab.py').read_text(encoding='utf-8'))
        assert any(isinstance(n, ast.Name) and n.id == 'GUILogHandler'
                   for n in ast.walk(tree))


class TestWebEntry:
    """Web UI 入口(ok-script 2.x 特性,远程监控用)"""

    def test_main_web_exists_and_switches_gui_backend(self):
        src = Path('main_web.py').read_text(encoding='utf-8')
        assert '"type": "web"' in src
        assert 'apply_pre_init_patches' in src, 'Web 入口也必须应用框架补丁'

    def test_web_requirements_message_paths_exist(self):
        """check_web_requirements 校验 fastapi/uvicorn — 文档必须给出安装指引"""
        src = Path('main_web.py').read_text(encoding='utf-8')
        assert 'fastapi uvicorn' in src or 'fastapi uvicorn' in src.lower()
