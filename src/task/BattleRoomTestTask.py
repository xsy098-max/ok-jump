# -*- coding: utf-8 -*-
"""
战备房间测试用例自动化任务（Unity 直连）

基于《搜打撤测试用例整合.xlsx》"战备房间"工作表（由
scripts/gen_battle_room_cases.py 同步到 configs/battle_room_cases.json），
按优先级执行用例：
  - "仅运行P0冒烟用例" 开启时只执行 P0（冒烟测试）
  - 可自动化的用例通过 Unity TCP UI 命令实际执行
  - 暂不可自动化的用例报告为 N/A 并说明所需的 Unity 侧能力

结果写入 logs/battle_room/report_<时间戳>.json，并在日志中输出汇总。
"""

import os
import time

from ok import og
from ok import BaseTask

import config as app_config
from src.task.mixins import JumpTaskMixin
from src.task.battle_room_cases import (
    load_cases, filter_cases, summarize, sort_by_priority,
    STATUS_FAIL, STATUS_SKIPPED, STATUS_BLOCKED, CaseResult,
)
from src.task.battle_room_checks import EXECUTABLE_CHECKS, CheckContext, run_case
from src.task.battle_room_ui import UiContext
from src.utils.UnityConnection import UnityConnection

_MAX_TCP_FAILURES = 3


class BattleRoomTestTask(BaseTask, JumpTaskMixin):
    """
    战备房间测试用例自动化（Unity 直连）

    通过 Unity TCP 的 UI 查找/点击命令驱动界面导航，
    不依赖截图/OCR。用例清单与优先级来自 QA 维护的 xlsx。
    """

    def __init__(self, *args, **kwargs):
        BaseTask.__init__(self, *args, **kwargs)
        JumpTaskMixin._init_mixin_vars(self)
        self.name = "BattleRoomTestTask"
        self.description = "战备房间测试用例自动化（搜打撤）"

        self.default_config = {
            '仅运行P0冒烟用例': True,
            '自动登录到大厅': True,
            '失败后停止': False,
            '界面加载超时(秒)': 20,
            '用例编号过滤': '',
            '允许改系统时间做隐藏验证': False,
            '允许GM自动发道具': False,
            'GM道具ID映射': '',
        }

        self.config_description = {
            '仅运行P0冒烟用例': '冒烟测试开关：开启后仅执行P0用例，关闭则按编号过滤或全量执行',
            '自动登录到大厅': '执行前若不在主城，自动调用Unity登录流程（复用AutoLoginTaskUnity配置）',
            '失败后停止': '任一用例FAIL后停止后续用例',
            '界面加载超时(秒)': '点击入口后等待界面出现的超时时间（进入房间含加载建议≥20秒）',
            '用例编号过滤': '仅执行指定用例，逗号分隔，如 TC-4.2-001,TC-4.2-002（留空不限制）',
            '允许改系统时间做隐藏验证':
                'TC-4.1-002 需临时把Windows时间拨到去年再恢复（管理员权限运行才生效，'
                '期间Unity在线连接可能短暂异常），默认关闭',
            '允许GM自动发道具':
                '装配类用例缺料时自动经 GM 面板(激活GMSwitch→AddItem→发送)补发，'
                '全程无需人工按键',
            'GM道具ID映射':
                '可选覆盖项(JSON)。默认自动读取游戏工程 Item/SDCItem/MultiLanguage '
                '三表按分类取最小ID;此JSON可修正个别类型，如 {"护甲":1600056}',
        }

    # ------------------------------------------------------------------

    def run(self):
        conn = self._get_unity_connection()
        if conn is None:
            self.logger.error("Unity 连接不可用，无法执行战备房间测试")
            return False

        smoke = bool(self.config.get('仅运行P0冒烟用例', True))
        id_filter = str(self.config.get('用例编号过滤', '') or '')
        load_timeout = float(self.config.get('界面加载超时(秒)', 10) or 10)

        cases = load_cases()
        selected, skipped = filter_cases(cases, smoke_only=smoke, case_id_filter=id_filter)
        selected = sort_by_priority(selected)
        case_map = {c.case_id: c for c in cases}

        self.logger.info("=" * 60)
        self.logger.info(f"战备房间测试启动：共 {len(cases)} 条用例，本次执行 {len(selected)} 条"
                         f"（冒烟={smoke}，编号过滤={idf_repr(id_filter)}）")
        self.logger.info("=" * 60)

        if not selected:
            self.logger.warning("没有符合条件的用例，任务结束")
            return True

        login_ok = True
        if bool(self.config.get('自动登录到大厅', True)):
            login_ok = self._ensure_main_city(conn)

        ui = UiContext(conn, self.logger, load_timeout=load_timeout)

        # GM 备料映射: 自动读取游戏工程 Item/SDCItem/MultiLanguage 三表为底,
        # 用户"GM道具ID映射"JSON 仅做覆盖/修正
        from src.task.battle_room_items import load_snapshot, merge_item_ids
        auto_mapping, auto_detail = load_snapshot()
        gm_ids, gm_err = merge_item_ids(auto_mapping,
                                        str(self.config.get('GM道具ID映射', '') or ''))
        if gm_err:
            self.logger.warning(gm_err)
        if auto_detail:
            self.logger.info(f"GM备料映射已自动加载 {len(auto_detail)} 个搜打撤道具"
                             f"(覆盖项以手动JSON为准)")
        elif not gm_ids:
            self.logger.warning('未能从游戏工程解析道具表且无手动映射,'
                                '缺料用例将 Blocked 提示备料')

        ctx = CheckContext(
            conn, ui, self.logger,
            allow_clock_change=bool(self.config.get('允许改系统时间做隐藏验证', False)),
            allow_gm_items=bool(self.config.get('允许GM自动发道具', False)),
            gm_item_ids=gm_ids)
        ui.clear_runtime_errors()  # 建立错误基线（命令不可用时自动禁用清扫）

        stop_on_fail = bool(self.config.get('失败后停止', False))
        results = []
        aborted = False
        for case in selected:
            if self._should_exit():
                results.append(CaseResult(case, STATUS_SKIPPED, '任务被停止'))
                aborted = True
                continue
            if EXECUTABLE_CHECKS.get(case.case_id) is not None and not login_ok:
                results.append(CaseResult(case, STATUS_BLOCKED, '未能进入主城（登录失败），用例被阻塞'))
                continue

            result = run_case(case, ctx)
            results.append(result)
            marker = '✔' if result.status == 'PASS' else ('✘' if result.status == STATUS_FAIL else '-')
            self.logger.info(f"[{result.status:>7}] {marker} {case.case_id}({case.priority}) "
                             f"{case.feature} | {result.detail}")
            if stop_on_fail and result.status == STATUS_FAIL:
                self.logger.warning("失败后停止已开启，跳过剩余用例")
                aborted = True

            if aborted and stop_on_fail:
                for rest in selected[selected.index(case) + 1:]:
                    results.append(CaseResult(rest, STATUS_SKIPPED, '失败后停止'))
                break

        for cid, reason in skipped.items():
            if cid in case_map:
                results.append(CaseResult(case_map[cid], STATUS_SKIPPED, reason))

        summary = summarize(results)
        dismissed = sorted({d for r in results for d in
                            (r.extra.get('弹窗跳过').split('; ')
                             if r.extra and r.extra.get('弹窗跳过') else [])})
        report_json, report_xlsx = self._write_report(
            smoke, results, summary, ui.ui_snapshot, aborted,
            dismissed_popups=dismissed)

        executed = summary['PASS'] + summary['FAIL'] + summary['Blocked']
        rate = (summary['PASS'] / executed * 100) if executed else 0.0
        self.logger.info("=" * 60)
        self.logger.info(f"战备房间测试完成：PASS={summary['PASS']} FAIL={summary['FAIL']} "
                         f"Blocked={summary['Blocked']} N/A={summary['N/A']} "
                         f"Skipped={summary['Skipped']}，通过率 {rate:.0f}%")
        self.logger.info(f"执行报告(JSON): {report_json}")
        self.logger.info(f"执行报告(XLSX): {report_xlsx}")
        self.logger.info("=" * 60)

        if summary['N/A']:
            self.logger.info(f"提示：{summary['N/A']} 条用例暂不可自动化（详见报告 needs_unity_support 字段），"
                             "补齐 Unity 侧命令后可逐步纳入")
        return summary['FAIL'] == 0 and not aborted

    # ------------------------------------------------------------------

    def _get_unity_connection(self):
        """获取 Unity 连接（isinstance 严格校验，mock 测试下不误报）"""
        try:
            if og and hasattr(og, 'my_app'):
                conn = getattr(og.my_app, '_unity_connection', None)
                if isinstance(conn, UnityConnection) and conn.is_connected():
                    return conn
        except Exception:
            pass
        return None

    def _ensure_main_city(self, conn):
        """
        确保当前处于主城（用例前置条件）。

        不在主城时复用已注册的 AutoLoginTaskUnity 实例执行登录，
        避免复制登录状态机。
        """
        for _ in range(_MAX_TCP_FAILURES):
            state = conn.get_login_state()
            if state == 'MainCity':
                return True
            if not conn.is_connected():
                self.logger.warning("TCP 连接中断，稍后重试")
                time.sleep(2)
                continue

            login_task = self._find_login_task()
            if login_task is None:
                self.logger.error(f"当前不在主城(状态:{state})，且 AutoLoginTaskUnity 未注册，无法自动登录")
                return False
            self.logger.info(f"当前不在主城(状态:{state})，调用 Unity 自动登录...")
            try:
                if login_task.run():
                    return conn.get_login_state() == 'MainCity'
            except Exception as e:  # noqa: BLE001
                self.logger.error(f"自动登录异常: {e}")
            return False
        self.logger.error("Unity 连接持续中断，放弃登录前置")
        return False

    def _find_login_task(self):
        try:
            from src.task.AutoLoginTaskUnity import AutoLoginTaskUnity
            for task in (og.executor.onetime_tasks or []):
                if isinstance(task, AutoLoginTaskUnity):
                    return task
        except Exception:
            pass
        return None

    def _should_exit(self):
        try:
            return og.executor.exit_event.is_set()
        except Exception:
            return False

    def _write_report(self, smoke, results, summary, ui_snapshot, aborted,
                      out_dir=None, dismissed_popups=None):
        """写入 JSON + XLSX 双报告，返回 (json路径, xlsx路径)"""
        from src.task.battle_room_report import load_env_info, write_reports
        if out_dir is None:
            out_dir = os.path.join(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))), 'logs', 'battle_room')
        return write_reports(out_dir, app_config.config.get('version'),
                             smoke, aborted, results, summary, ui_snapshot,
                             environment=load_env_info(),
                             dismissed_popups=dismissed_popups)


def idf_repr(id_filter):
    return id_filter if id_filter else '无'
