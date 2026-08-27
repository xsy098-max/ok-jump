# -*- coding: utf-8 -*-
"""
仓库卫生测试:保证打包/镜像分发的完整性与整洁。

- 运行时必需文件齐全(任务模块、资源、依赖清单、打包配置)
- AI 工具本地数据与日志不再入库(CNB 镜像随之保持干净)
- 版本号、入口脚本与 pyappify 配置一致
"""

import json
import os
import subprocess

import pytest


def _git_files():
    out = subprocess.run(
        ['git', 'ls-files'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        check=True,
    ).stdout
    return {line.strip().strip('"') for line in out.splitlines() if line.strip()}


class TestRuntimeCompleteness:
    """config.py 注册的运行时资源必须真实存在"""

    def test_task_modules_exist(self):
        import sys
        sys.path.insert(0, os.getcwd())
        from config import config
        for module_path, class_name in config['onetime_tasks'] + config['trigger_tasks']:
            file_path = module_path.replace('.', '/') + '.py'
            assert os.path.isfile(file_path), \
                f'任务 {class_name} 的模块文件不存在: {file_path}'

    def test_scene_and_tabs_exist(self):
        import sys
        sys.path.insert(0, os.getcwd())
        from config import config
        scene = config.get('scene')
        if scene:
            assert os.path.isfile(scene[0].replace('.', '/') + '.py')
        for module_path, class_name in config.get('custom_tabs', []):
            assert os.path.isfile(module_path.replace('.', '/') + '.py'), \
                f'自定义页签 {class_name} 的模块文件不存在'

    def test_packaging_files_exist(self):
        for f in ['main.py', 'main_debug.py', 'config.py', 'requirements.txt',
                  'pyappify.yml', 'run_tests.ps1', 'AGENTS.md']:
            assert os.path.isfile(f), f'打包/开发必需文件缺失: {f}'

    def test_assets_exist(self):
        import sys
        sys.path.insert(0, os.getcwd())
        from config import config
        coco = config['template_matching']['coco_feature_json']
        assert os.path.isfile(coco), f'特征标注文件缺失: {coco}'
        assert os.path.isdir('icons'), 'icons/ 目录缺失'
        assert os.path.isfile(os.path.join('icons', 'icon.png')), 'GUI 图标缺失'

    def test_pyappify_profiles_reference_real_scripts(self):
        with open('pyappify.yml', encoding='utf-8') as f:
            content = f.read()
        assert 'main_script: "main.py"' in content
        assert 'main_script: "main_debug.py"' in content


class TestRepoHygiene:
    """本地开发数据不入库(镜像保持干净)"""

    def test_ai_tool_dirs_not_tracked(self):
        files = _git_files()
        offenders = [f for f in files
                     if f.startswith(('.qoder/', '.claude/', '.learnings/', '.zcode/'))]
        assert not offenders, f'AI 工具数据不应入库: {offenders[:5]}'

    def test_log_files_not_tracked(self):
        files = _git_files()
        offenders = [f for f in files if f.startswith('logs/') or f.endswith('.log')]
        assert not offenders, f'日志文件不应入库: {offenders[:5]}'

    def test_gitignore_covers_local_data(self):
        content = open('.gitignore', encoding='utf-8').read()
        for pattern in ['.qoder/', '.claude/', '.zcode/', 'logs/']:
            assert pattern in content, f'.gitignore 缺少 {pattern}'


class TestVersionConsistency:

    def test_config_version_is_semver(self):
        import sys
        sys.path.insert(0, os.getcwd())
        from config import config
        v = config['version']
        parts = v.split('.')
        assert len(parts) == 3 and all(p.isdigit() for p in parts), \
            f'config.py 版本号 {v} 应为 X.Y.Z'

    def test_pyproject_version_matches_config(self):
        import sys
        sys.path.insert(0, os.getcwd())
        from config import config
        content = open('pyproject.toml', encoding='utf-8').read()
        assert f'version = "{config["version"]}"' in content, \
            'pyproject.toml 与 config.py 版本号不一致'
