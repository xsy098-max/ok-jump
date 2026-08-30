# -*- coding: utf-8 -*-
"""
战备房间测试用例数据模型与加载/过滤

用例源数据由 scripts/gen_battle_room_cases.py 从
《搜打撤测试用例整合.xlsx》"战备房间"工作表生成到
configs/battle_room_cases.json，本模块只负责加载与筛选。
"""

import json
import os
from dataclasses import dataclass, field

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CASES_PATH = os.path.join(_PROJECT_ROOT, 'configs', 'battle_room_cases.json')

# 用例执行状态（与 xlsx 模板的统计口径一致）
STATUS_PASS = 'PASS'
STATUS_FAIL = 'FAIL'
STATUS_BLOCKED = 'Blocked'
STATUS_NA = 'N/A'
STATUS_SKIPPED = 'Skipped'

_PRIORITY_ORDER = {'P0': 0, 'P1': 1, 'P2': 2}


@dataclass
class TestCase:
    case_id: str      # TC-4.1-001
    priority: str     # P0 / P1 / P2
    module: str       # 场景1-玩法入口
    feature: str      # 功能点
    steps: str        # 操作步骤
    expected: str     # 期望结果
    note: str = ''

    def to_dict(self):
        return {
            'case_id': self.case_id,
            'priority': self.priority,
            'module': self.module,
            'feature': self.feature,
            'steps': self.steps,
            'expected': self.expected,
            'note': self.note,
        }


@dataclass
class CaseResult:
    case: TestCase
    status: str                    # STATUS_* 之一
    detail: str = ''
    duration: float = 0.0
    extra: dict = field(default_factory=dict)

    def to_dict(self):
        d = self.case.to_dict()
        d.update({
            'status': self.status,
            'detail': self.detail,
            'duration_s': round(self.duration, 2),
        })
        d.update(self.extra)
        return d


def load_cases(path=None):
    """
    加载用例列表

    Returns:
        list[TestCase]: 按 xlsx 中的原始顺序
    Raises:
        FileNotFoundError / ValueError: 用例文件缺失或格式非法时
    """
    path = path or DEFAULT_CASES_PATH
    with open(path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        raise ValueError(f'用例文件格式非法(应为列表): {path}')
    cases = []
    for item in raw:
        if not item.get('case_id', '').startswith('TC-'):
            continue
        cases.append(TestCase(
            case_id=item['case_id'],
            priority=item.get('priority', ''),
            module=item.get('module', ''),
            feature=item.get('feature', ''),
            steps=item.get('steps', ''),
            expected=item.get('expected', ''),
            note=item.get('note', ''),
        ))
    return cases


def filter_cases(cases, smoke_only=False, case_id_filter=None):
    """
    按冒烟开关/用例编号过滤用例

    Args:
        cases: load_cases() 的结果
        smoke_only: True 时仅保留 P0（冒烟测试）
        case_id_filter: 逗号分隔的用例编号白名单（优先级最高）

    Returns:
        (selected, skipped_reasons: {case_id: str})
    """
    wanted = None
    if case_id_filter:
        wanted = {s.strip().upper() for s in case_id_filter.split(',') if s.strip()}
    selected, skipped = [], {}
    for case in cases:
        if wanted is not None:
            if case.case_id.upper() in wanted:
                selected.append(case)
            else:
                skipped[case.case_id] = '不在用例编号过滤范围内'
        elif smoke_only and case.priority != 'P0':
            skipped[case.case_id] = f'冒烟模式仅执行P0(当前{case.priority})'
        else:
            selected.append(case)
    return selected, skipped


def summarize(results):
    """按状态统计结果数量"""
    summary = {STATUS_PASS: 0, STATUS_FAIL: 0, STATUS_BLOCKED: 0, STATUS_NA: 0, STATUS_SKIPPED: 0}
    for r in results:
        summary[r.status] = summary.get(r.status, 0) + 1
    return summary


def sort_by_priority(cases):
    """稳定地按优先级排序（P0 → P1 → P2），同优先级保持原始顺序"""
    return sorted(cases, key=lambda c: _PRIORITY_ORDER.get(c.priority, 99))
