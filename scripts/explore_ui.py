# -*- coding: utf-8 -*-
"""
UI 探查工具：直连 Unity 枚举当前画面所有激活的可交互节点

用法：
    # 探查当前界面
    python scripts/explore_ui.py

    # 点击某按钮后等待再探查（可重复出现）
    python scripts/explore_ui.py --click BtnPreBattle --wait 4

    # 指定输出文件名（默认按时间戳）
    python scripts/explore_ui.py --name sdc_room

说明：插件 automation_find_ui 不支持无选择器全量扫描，
这里用多个宽泛关键字分批查询后合并去重；候选表/锚点一律
以本脚本枚举到的真实名称为准，禁止凭源码猜测。
"""

import argparse
import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.UnityConnection import UnityConnection  # noqa: E402

SWEEP_KEYWORDS = ['Btn', 'Button', 'Toggle', 'wbtn', 'Window', 'Popup', 'Tab']


def inventory(conn):
    """枚举当前激活的所有节点，返回 {path: item}"""
    collected = {}
    for kw in SWEEP_KEYWORDS:
        resp = conn.find_ui(name_contains=kw, max_results=400)
        for it in resp.get('items', []):
            path = it.get('path')
            if path and it.get('activeInHierarchy'):
                collected[path] = it
    return collected


def summarize(items):
    """按视图根分组输出可交互节点的简要信息"""
    groups = {}
    for path, it in items.items():
        seg = path.split('/')
        root = next((x for x in seg if x.startswith('ViewRoot')), None)
        rel = '/'.join(seg[seg.index(root):]) if root else path
        groups.setdefault(root or '(other)', []).append((it, rel))
    lines = []
    for root, entries in sorted(groups.items()):
        interactive = [e for e in entries if e[0].get('hasButton') or e[0].get('hasToggle')]
        lines.append(f"\n== {root} ({len(entries)} 节点, 其中可交互 {len(interactive)}) ==")
        for it, rel in sorted(interactive, key=lambda x: x[1]):
            kind = 'T' if it.get('hasToggle') else 'B'
            mark = '' if it.get('interactable', True) else ' [禁用]'
            lines.append(f"  [{kind}]{mark} {it['name']:32s} <- {rel}")
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='枚举 Unity 当前界面的可交互节点')
    parser.add_argument('--click', action='append', default=[],
                        help='探查前依次点击的按钮名(nameContains)，可多次出现')
    parser.add_argument('--wait', type=float, default=3.0,
                        help='每次点击后的等待秒数(默认3)')
    parser.add_argument('--name', default=None, help='输出文件名前缀')
    args = parser.parse_args()

    conn = UnityConnection(timeout=5)
    if not conn.connect():
        print('无法连接 Unity TCP(9876)')
        return 1

    log_state = conn.get_login_state()
    print(f'登录状态: {log_state}')

    for target in args.click:
        resp = conn.click_ui(name_contains=target)
        ok = resp.get('status') == 'ok'
        print(f"点击 [{target}]: {'ok' if ok else 'FAIL ' + str(resp.get('message', ''))[:80]}")
        time.sleep(args.wait)

    items = inventory(conn)
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'logs', 'ui_inventory')
    os.makedirs(out_dir, exist_ok=True)
    prefix = args.name or f'{datetime.datetime.now():%Y%m%d_%H%M%S}'
    out_path = os.path.join(out_dir, f'{prefix}.json')

    payload = {
        'captured_at': datetime.datetime.now().isoformat(),
        'login_state': log_state,
        'clicked': args.click,
        'node_count': len(items),
        'items': [{'path': p, **{k: it.get(k) for k in
                                 ('name', 'hasButton', 'hasToggle', 'interactable')}}
                  for p, it in sorted(items.items())],
    }
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f'\n共 {len(items)} 个激活节点 -> {out_path}')
    print(summarize(items))
    return 0


if __name__ == '__main__':
    sys.exit(main())
