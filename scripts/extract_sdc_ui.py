# -*- coding: utf-8 -*-
"""
从 Unity 工程 Game.Hotfix 提取搜打撤(SDC)相关的 UI 组件绑定清单

数据源(真实绑定，非猜测)：
  1. Generate/MBBehaviours/MBBehaviour_*.cs —— 视图绑定的控件字段
     (public readonly WButton BtnXxx; ...) 及类型
  2. Game/GUI/SDCSystem/**/*.cs —— 窗口类、prefab 名称、入口按钮绑定

输出: configs/battle_room_ui_bindings.json
      {behaviour_class: [{name, type}, ...]}, views: {...}
供 BattleRoomTestTask 候选表/锚点与用例映射引用。
"""

import json
import os
import re
import sys
from pathlib import Path

GAME_ROOT = Path(r'E:\Program\Client-Jump')
GEN_DIR = GAME_ROOT / 'Assets' / 'Game.Hotfix' / 'Generate' / 'MBBehaviours'
GUI_DIR = GAME_ROOT / 'Assets' / 'Game.Hotfix' / 'Game' / 'GUI'
OUT = Path(__file__).resolve().parent.parent / 'configs' / 'battle_room_ui_bindings.json'

FIELD_RE = re.compile(
    r'public readonly\s+(?P<decl>[\w.]+)\s+(?P<name>\w+)\s*;')
ASSIGN_RE = re.compile(r'this\.(?P<name>\w+)\s*=\s*this\.Get<')

# 只收 UI 控件类型的字段
WIDGET_TYPES = {'WButton', 'Button', 'WToggle', 'Toggle', 'WImage', 'WText',
                'InputField', 'WInputField', 'LoopScrollRect', 'Slider',
                'RectTransform'}


def parse_behaviour(path):
    text = path.read_text(encoding='utf-8', errors='ignore')
    declared = {}
    for m in FIELD_RE.finditer(text):
        short_type = m.group('decl').split('.')[-1]
        if short_type in WIDGET_TYPES:
            declared[m.group('name')] = short_type
    assigned = {mm.group('name') for mm in ASSIGN_RE.finditer(text)}
    return [{'name': n, 'type': t} for n, t in sorted(declared.items())
            if n in assigned]


def walk_cs(root):
    for p in root.rglob('*.cs'):
        yield p


def main():
    if not GEN_DIR.exists():
        print(f'未找到生成目录: {GEN_DIR}')
        return 1

    # 关键字过滤：搜打撤体系 + 大厅主城入口 + 相关公共窗口
    interest = re.compile(
        r'SDC|TeamRoom|Convene|Season|Store|Collect|Task|PreWar|Shop'
        r'|MainCity|Lobby|PlayerInfo|TipsNew', re.I)

    behaviours = {}
    for p in GEN_DIR.glob('MBBehaviour_*.cs'):
        if not interest.search(p.stem):
            continue
        items = parse_behaviour(p)
        if items:
            behaviours[p.stem.replace('MBBehaviour_', '')] = items

    # SDCSystem 下所有窗口/视图类清单（含所在子目录）
    views = []
    sdc_dir = GUI_DIR / 'SDCSystem'
    for p in walk_cs(sdc_dir):
        rel = p.relative_to(sdc_dir).as_posix()
        cls = re.search(r'class\s+(\w+)', p.read_text(encoding='utf-8',
                                                        errors='ignore'))
        if cls:
            views.append({'class': cls.group(1), 'file': rel})

    out = {
        '_source': str(GAME_ROOT),
        '_note': ('scripts/extract_sdc_ui.py 从游戏工程生成的绑定清单；'
                  '候选表/锚点只允许引用这里的名称或真机枚举结果'),
        'behaviours': behaviours,
        'views': views,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding='utf-8')

    total_controls = sum(len(v) for v in behaviours.values())
    buttons = sum(1 for v in behaviours.values() for c in v
                  if c['type'] in ('WButton', 'Button'))
    print(f'已提取 {len(behaviours)} 个 Behaviour / '
          f'{total_controls} 个控件(其中按钮 {buttons}) -> {OUT}')
    print(f'SDCSystem 窗口类 {len(views)} 个')
    for b in sorted(behaviours):
        cnt = len(behaviours[b])
        btns = [c['name'] for c in behaviours[b]
                if c['type'] in ('WButton', 'Button')]
        head = ', '.join(btns[:12])
        more = f' ...共{len(btns)}个按钮' if len(btns) > 12 else ''
        print(f'  {b:44s} 控件{cnt:3d}: {head}{more}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
