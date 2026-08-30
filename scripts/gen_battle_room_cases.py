# -*- coding: utf-8 -*-
"""
从《搜打撤测试用例整合.xlsx》的"战备房间"工作表提取测试用例,
生成 configs/battle_room_cases.json 供 BattleRoomTestTask 使用。

xlsx 属于策划/QA 维护的源文档,不随工具打包分发;
改表后重新运行本脚本同步:
    python scripts/gen_battle_room_cases.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XLSX_CANDIDATES = ['搜打撤测试用例整合.xlsx']
SHEET_NAME = '战备房间'
OUT = ROOT / 'configs' / 'battle_room_cases.json'


def load_rows(xlsx_path):
    import openpyxl
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb[SHEET_NAME]
    rows = []
    for row in ws.iter_rows(values_only=True):
        rows.append(['' if v is None else str(v).strip() for v in row])
    return rows


def parse_cases(rows):
    cases = []
    for row in rows:
        # 表头行: 用例编号 | 用例优先级 | 模块 | 功能 | 操作步骤 | 期望结果 | 测试结果 | Bug ID | 备注
        if len(row) < 6 or not row[0].startswith('TC-'):
            continue
        case = {
            'case_id': row[0],
            'priority': row[1],
            'module': row[2],
            'feature': row[3],
            'steps': row[4],
            'expected': row[5],
            'note': row[8] if len(row) > 8 else '',
        }
        if case['priority'] not in ('P0', 'P1', 'P2'):
            continue
        cases.append(case)
    return cases


def main():
    xlsx = next((ROOT / name for name in XLSX_CANDIDATES if (ROOT / name).exists()), None)
    if xlsx is None:
        print(f'未找到用例xlsx: {XLSX_CANDIDATES}')
        return 1

    cases = parse_cases(load_rows(xlsx))
    if not cases:
        print(f'xlsx 中未解析到用例,请检查工作表 "{SHEET_NAME}" 格式')
        return 1

    OUT.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding='utf-8')
    by_priority = {}
    for c in cases:
        by_priority[c['priority']] = by_priority.get(c['priority'], 0) + 1
    print(f'已生成 {len(cases)} 条用例 -> {OUT}')
    print(f'优先级分布: {by_priority}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
