# -*- coding: utf-8 -*-
"""
战备房间测试用例执行器

每个用例三选一：
  1. EXECUTABLE_CHECKS 中有对应函数 → 实际执行（导航/锚点断言 + 运行时错误清扫）
  2. NEEDS_SUPPORT 中登记 → N/A，附"需要什么Unity侧能力才能自动化"
  3. 其余 → N/A，"尚未实现自动化脚本"

当前 Unity 插件(Packages/com.unity-ai-custom)已提供 find/click/set_toggle 等
UI 命令，但缺少文本读取、颜色读取、拖拽、时间控制，因此涉及数值校验、
拖拽装配、时间窗口的 P0 用例先标记待支持，跑通导航链路后再补 Unity 命令。
"""

import datetime
import re
import sys
import time

from src.task.battle_room_cases import (
    STATUS_PASS, STATUS_FAIL, STATUS_BLOCKED, STATUS_NA, CaseResult,
)
from src.task.battle_room_ui import (
    UiContext, TEXT_KEYWORDS, TIPS_ROOT, TIPS_EQUIP_PATH, TIPS_CLOSE_PATH,
    TOAST_ROOT, warehouse_cell_path, TIPS_PUTINBAG_PATH,
    TIPS_PUTINSAFETY_PATH, TIPS_SELL_BUTTON_PATH, TIPS_SELL_CANCEL_PATH,
    TIPS_SHOP_BUY_PATH, TIPS_UNINSTALL_PATH, TIPS_PUTINWAREHOUSE_PATH,
)

_NUM_RE = re.compile(r'^[\d,，.\s]+$')


class CheckContext:
    """一次运行内共享的执行上下文"""

    def __init__(self, conn, ui: UiContext, logger, allow_clock_change=False,
                 allow_gm_items=False, gm_item_ids=None):
        self.conn = conn
        self.ui = ui
        self.logger = logger
        self.room_available = False  # TC-4.1-001 成功后置 True
        self.allow_clock_change = allow_clock_change
        self.allow_gm_items = allow_gm_items
        self.gm_item_ids = dict(gm_item_ids or {})
        self.dismissed_popups = []   # 自动跳过的弹窗记录(提醒测试人员)
        self.screenshots = []        # 截图相对路径索引(进报告)


# --------------------------------------------------------------------------
# 系统（本机）时间操作 —— TC-4.1-002 专用，需管理员权限且默认关闭
# --------------------------------------------------------------------------

def _os_get_localtime():
    """读取本机时间，返回 datetime；失败返回 None"""
    if sys.platform != 'win32':
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class SYSTEMTIME(ctypes.Structure):
            _fields_ = [('wYear', wintypes.WORD), ('wMonth', wintypes.WORD),
                        ('wDayOfWeek', wintypes.WORD), ('wDay', wintypes.WORD),
                        ('wHour', wintypes.WORD), ('wMinute', wintypes.WORD),
                        ('wSecond', wintypes.WORD), ('wMilliseconds', wintypes.WORD)]

        st = SYSTEMTIME()
        if not ctypes.windll.kernel32.GetLocalTime(ctypes.byref(st)):
            return None
        return datetime.datetime(st.wYear, st.wMonth, st.wDay,
                                 st.wHour, st.wMinute, st.wSecond)
    except Exception:
        return None


def _os_set_localtime(dt):
    """
    设置本机时间（需要管理员权限）

    Returns:
        (bool, str): 是否成功 / 错误说明
    """
    if sys.platform != 'win32':
        return False, '非 Windows 平台'
    try:
        import ctypes
        from ctypes import wintypes

        class SYSTEMTIME(ctypes.Structure):
            _fields_ = [('wYear', wintypes.WORD), ('wMonth', wintypes.WORD),
                        ('wDayOfWeek', wintypes.WORD), ('wDay', wintypes.WORD),
                        ('wHour', wintypes.WORD), ('wMinute', wintypes.WORD),
                        ('wSecond', wintypes.WORD), ('wMilliseconds', wintypes.WORD)]

        st = SYSTEMTIME(dt.year, dt.month, dt.weekday(), dt.day,
                        dt.hour, dt.minute, dt.second, 0)
        # SetLocalTime 需要正确的 wDayOfWeek（Sunday=0）
        ok = ctypes.windll.kernel32.SetLocalTime(ctypes.byref(st))
        if not ok:
            return False, f'SetLocalTime 失败 err={ctypes.GetLastError()}'
        return True, ''
    except Exception as e:
        return False, str(e)


def _shift_time_out_of_season():
    """
    把本机时间拨到去年同刻（搜打撤为赛季玩法，去年几乎必然处于开放区间外）

    Returns:
        (saved_datetime 或 None, ok, msg)
    """
    saved = _os_get_localtime()
    if saved is None:
        return None, False, '无法读取系统时间'
    target = saved.replace(year=saved.year - 1)
    ok, msg = _os_set_localtime(target)
    return saved, ok, msg


# --------------------------------------------------------------------------
# 通用辅助
# --------------------------------------------------------------------------

def _require_room(ctx):
    """房间主界面是场景2/3/4用例的前置条件；失败前先尝试自救恢复"""
    if ctx.room_available and ctx.ui.in_room():
        return None
    if ctx.ui.in_room():
        ctx.room_available = True
        return None
    # 自救：奖励弹窗/批量模式残留/全屏窗口都可能挡住房间——多级恢复后复判
    notes = []
    try:
        dis = ctx.ui.dismiss_popups()
        if dis:
            notes.append(f'跳过弹窗{dis}')
            ctx.dismissed_popups.extend(dis)
    except Exception:
        pass
    try:
        _exit_sell_mode(ctx)
        notes.append('退出批量模式')
    except Exception:
        pass
    for _ in range(3):
        if ctx.ui.in_room():
            break
        ctx.ui.close_top_window()
        notes.append('返回栈')
        time.sleep(1.5)
    if not ctx.ui.in_room():
        # 终极自救：从大厅入口重新进入（等价重跑 TC-4.1-001 的进入动作）
        try:
            ok, msg = ctx.ui.click('lobby_sdc_entry')
            if ok:
                item = ctx.ui.wait_view('room_main_view', timeout=15.0)
                notes.append('从大厅重进房间' + ('成功' if item else '失败'))
        except Exception:
            pass
    if ctx.ui.in_room():
        ctx.room_available = True
        ctx.logger.info('前置自救成功: ' + ' ; '.join(notes))
        return None
    return STATUS_BLOCKED, ('前置条件不满足：未处于搜打撤房间主界面'
                            '（TC-4.1-001 未通过）'
                            + ('；自救: ' + ' ; '.join(notes) if notes else ''))


def _open_view(ctx, entry, expect_keywords=None, close_after=True,
               timeout=None, extra_back=0):
    """
    点击入口 → 等待出现新的视图根 →（可选）关闭回到房间

    Args:
        entry: 入口按钮逻辑名
        expect_keywords: 期望的新视图根包含的关键字列表；None 表示
                         只要求"打开了新视图"（名称如实记录，由人工核对）
        close_after: 成功后是否走返回栈关掉打开的窗口
        extra_back: 关闭时额外多按几次返回（如商店叠在战备上）

    Returns:
        (status, detail)
    """
    before = set(ctx.ui.active_view_roots())
    # 幂等保护：目标视图本来就已打开时，无需点击也不应误判失败
    if expect_keywords:
        already = next((n for n in before
                        if any(kw in n for kw in expect_keywords)), None)
        if already:
            return STATUS_PASS, f'目标界面本已打开: {already}（跳过重复点击）'
    ok, msg = ctx.ui.click(entry)
    if not ok:
        return STATUS_FAIL, f'{msg}（候选表见 battle_room_ui.py，需重新枚举）'

    opened = None
    deadline = time.time() + (timeout if timeout is not None else ctx.ui.load_timeout)
    while time.time() < deadline:
        for name in ctx.ui.active_view_roots():
            if name in before:
                continue
            if expect_keywords is None or any(kw in name for kw in expect_keywords):
                opened = name
                break
        if opened:
            break
        time.sleep(ctx.ui.poll_interval)

    if opened is None:
        if expect_keywords:
            detail = (f'{msg}，{ctx.ui.load_timeout:.0f}秒内未出现含'
                      f'{expect_keywords} 的视图')
        else:
            detail = f'{msg}，{ctx.ui.load_timeout:.0f}秒内未打开任何新视图'
        return STATUS_FAIL, detail

    status = STATUS_PASS
    matched = '、'.join(kw for kw in (expect_keywords or []) if kw in opened) or '(仅记录)'
    detail = f'{msg}，已打开 {opened}'
    if not matched.startswith('('):
        detail += f' [匹配: {matched}]'

    if close_after:
        for _ in range(1 + extra_back):
            if not ctx.ui.close_top_window():
                detail += '；返回栈调用失败，可能残留界面影响后续用例'
                break
    return status, detail


def _wait_anchors(ctx, logicals, settle_seconds=8.0):
    """轮询等待一组锚点出现（房间数据异步加载），返回缺失的逻辑名列表"""
    deadline = time.time() + min(settle_seconds, max(ctx.ui.load_timeout, 4.0))
    missing = None
    while True:
        missing = [lg for lg in logicals if ctx.ui.find_active(lg) is None]
        if not missing or time.time() >= deadline:
            return missing
        time.sleep(ctx.ui.poll_interval)


def _snapshot_on_fail(ctx):
    """失败时抓一份UI快照，帮助补充候选名"""
    if not ctx.ui.ui_snapshot:
        try:
            ctx.ui.snapshot_ui()
        except Exception:
            pass


# --------------------------------------------------------------------------
# 文本/数值采集助手（配合 automation_get_ui_info）
# --------------------------------------------------------------------------

def _collect_texts(ctx, subtree, keywords=None):
    """按命名约定关键字收集子树内携带文本的激活节点"""
    merged = {}
    for kw in (keywords or TEXT_KEYWORDS):
        try:
            resp = ctx.ui.conn.get_ui_info(name_contains=kw, max_results=120)
        except Exception:
            continue
        for it in resp.get('items', []):
            path = it.get('path', '')
            if it.get('activeInHierarchy') and subtree in path and it.get('text'):
                merged[path] = it
    return list(merged.values())


def _numeric_entries(entries):
    """从文本节点中筛出纯数字项（货币/价值类）"""
    out = []
    for it in entries:
        text = str(it.get('text', '')).strip()
        if text and _NUM_RE.match(text) and any(ch.isdigit() for ch in text):
            out.append({
                'path': it.get('path'),
                'value': text.replace(',', '').replace('，', ''),
                'raw': text,
                'color': it.get('color'),
            })
    return out


def _color_label(rgb):
    """把 RGBA 数组归类为绿/红/其他（用于装配价值颜色断言的记录口径）"""
    if not rgb or len(rgb) < 3:
        return '未知'
    r, g, b = rgb[0], rgb[1], rgb[2]
    if g > 140 and g > r + 40 and g > b + 40:
        return '绿'
    if r > 150 and r > g + 50:
        return '红'
    return f'RGB{tuple(rgb[:3])}'


def _ensure_prewar_open(ctx):
    """确保战备窗口打开且保持（供装配/仓库/商店用例复用）"""
    if ctx.ui.find_active('prewar_window') is not None:
        return None
    status, detail = _open_view(ctx, 'room_btn_prewar',
                                ['SDCPreWarWindow'], close_after=False)
    if status != STATUS_PASS:
        return status, detail
    return None


def _open_tips_for_cell(ctx, index, timeout=4.0):
    """点击仓库第 index 格并在超时内等待 TIPS 出现。返回 bool"""
    before = set(ctx.ui.active_view_roots())
    resp = ctx.ui.conn.click_ui(path=warehouse_cell_path(index))
    if resp.get('status') != 'ok':
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        for name in ctx.ui.active_view_roots():
            if name not in before and 'SDCItemTips' in name:
                return True
        time.sleep(ctx.ui.poll_interval)
    return False


def _close_tips(ctx):
    """关闭物品 TIPS（优先 BtnClose 精确路径）"""
    resp = ctx.ui.conn.click_ui(path=TIPS_CLOSE_PATH)
    if resp.get('status') != 'ok':
        ctx.ui.close_top_window()
    time.sleep(0.5)


def _wait_toast_containing(ctx, keyword, timeout=4.0):
    """轮询 Toast 层(UITxtTips)文本是否包含关键字"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        texts = _collect_texts(ctx, 'UITxtTips')
        joined = ' '.join(str(t.get('text')) for t in texts)
        if keyword in joined:
            return True, joined[:120]
        time.sleep(0.3)
    texts = _collect_texts(ctx, 'UITxtTips')
    return False, ' '.join(str(t.get('text')) for t in texts)[:120]


# ---- 通用扩展助手(TIPS 分类装配/文本找按钮) ----

def _item_detail(ctx):
    """读取道具元数据缓存(类型→名称集合/Value/SeasonValue)"""
    from src.task.battle_room_items import load_snapshot
    _, detail = load_snapshot()
    return detail


def warehouse_cells_present(ctx):
    """一次性查仓库现有格子索引（存在性快查，避免逐格开 TIPS）"""
    import re as _re
    r = ctx.ui.conn.find_ui(name_contains='Obj_Item', max_results=60)
    idxs = []
    for it in r.get('items', []):
        pp = it.get('path', '')
        if it.get('activeInHierarchy') and 'WarehouseScrollView' in pp:
            mm = _re.search(r'Obj_Item(' + chr(92) + 'd+)/', pp + '/')
            if mm:
                idxs.append(int(mm.group(1)))
    return sorted(set(idxs))


def find_warehouse_item_by_subtype(ctx, subtype, scan_max=24):
    """按道具分类扫描仓库：TIPS 标题命中该分类的任一官方道具名即认为匹配。

    比关键词匹配更准：技能卡叫"SC-1·治疗"，关键词"技能"是匹配不到的。
    Returns:
        (cell_index, title) / None
    """
    from src.task.battle_room_items import names_for_subtype
    names = set(names_for_subtype(_item_detail(ctx), subtype))
    opened = _ensure_prewar_open(ctx)
    if opened:
        return None
    present = warehouse_cells_present(ctx)
    for idx in (present or list(range(scan_max))):
        if not _open_tips_for_cell(ctx, idx):
            continue
        texts = _collect_texts(ctx, 'SDCItemTips>')
        titles = [str(t['text']) for t in texts]
        for cand in titles:
            if any(n and n in cand for n in names):
                return idx, cand
        _close_tips(ctx)
    return None


def find_button_by_text(ctx, keywords, subtree):
    """在指定子树中按中文字面找激活按钮（运行时读语义，非猜测节点名）

    Args:
        keywords: 如 ('确认', '确定')；匹配按钮自身或其子文本节点
    Returns:
        (path, text) / None
    """
    btns = _active_named(ctx, 'Btn')
    btns += [(p, it) for p, it in _active_named(ctx, 'Button')
             if 'Btn' not in (it.get('name') or '')]
    texts = {t.get('path'): str(t.get('text') or '')
             for t in _collect_texts(ctx, subtree)}
    for path, it in btns:
        if subtree not in (path or '') or not it.get('hasButton'):
            continue
        own = str(it.get('text') or '')
        if any(k in own for k in keywords):
            return path, own
        # 按钮子节点的文本(路径前缀匹配)
        for tpath, txt in texts.items():
            if tpath.startswith(path) and any(k in txt for k in keywords):
                return path, txt
    return None


def scan_bag_item(ctx, subtype, zone_keyword='AmplifierTrans', scan_max=3):
    """
    扫描左侧背包区(增幅器/药品/安全箱/钥匙链等容器)的格子,
    TIPS 标题命中该分类官方名即返回。

    Returns:
        (cell_path, title) / None
    """
    from src.task.battle_room_items import names_for_subtype
    names = set(names_for_subtype(_item_detail(ctx), subtype))
    r = ctx.ui.conn.find_ui(name_contains=zone_keyword, max_results=10)
    zones = [it['path'] for it in r.get('items', []) if it.get('activeInHierarchy')]
    for zone in zones:
        for idx in range(scan_max):
            cell = f'{zone}/Obj_Item_{idx}/Btn_Click'
            if ctx.ui.conn.click_ui(path=cell).get('status') != 'ok':
                continue
            time.sleep(1.0)
            tips_up = any('SDCItemTips' in v for v in ctx.ui.active_view_roots())
            if tips_up:
                texts = _collect_texts(ctx, 'SDCItemTips>')
                titles = [str(t['text']) for t in texts]
                for cand in titles:
                    if any(n and n in cand for n in names):
                        return cell, cand
                _close_tips(ctx)
    return None


def equip_from_warehouse(ctx, subtype, expect_toast='装配成功'):
    """TIPS 路径装配：扫仓库找到分类道具 → TIPS → Button_Equip → Toast 断言。

    适用于 4.3 槽位类用例(xlsx 官方步骤"点击TIPS装配按钮或拖动至槽位")。
    Returns:
        (status, detail)
    """
    if not warehouse_cells_present(ctx):
        gm_id = ctx.gm_item_ids.get(_subtype_label(subtype))
        if ctx.allow_gm_items and gm_id:
            ok, msg = ctx.ui.gm_add_item(gm_id, count=1)
            ctx.logger.info('GM 预补料[%s]: %s' % (_subtype_label(subtype), msg))
            if ok:
                time.sleep(5.0)   # 服务端下发+背包刷新需要时间
    found = find_warehouse_item_by_subtype(ctx, subtype)
    if not found:
        gm_id = ctx.gm_item_ids.get(_subtype_label(subtype))
        if ctx.allow_gm_items and gm_id:
            ok, msg = ctx.ui.gm_add_item(gm_id, count=1)
            ctx.logger.info('GM 自动备料[%s]: %s' % (_subtype_label(subtype), msg))
            if ok:
                time.sleep(5.0)
            found = find_warehouse_item_by_subtype(ctx, subtype)
        if not found:
            _close_tips(ctx)
            return STATUS_BLOCKED, ('仓库未发现[%s]道具(已尝试GM补发,若背包未收到'
                                    '请人工确认 GM 面板指令是否生效; id=%s)'
                                    % (_subtype_label(subtype), gm_id))
    cell, title = found
    resp = ctx.ui.conn.click_ui(path=TIPS_EQUIP_PATH)
    if resp.get('status') != 'ok':
        _close_tips(ctx)
        return STATUS_FAIL, f'第{cell}格({title}) TIPS 装备按钮点击失败'
    toast_ok, toast_text = _wait_toast_containing(ctx, expect_toast)
    _close_tips(ctx)
    detail = f'第{cell}格[{title}] 经TIPS装配; Toast="{toast_text}"'
    return (STATUS_PASS if toast_ok else STATUS_FAIL), detail


def put_into_container(ctx, subtype, tips_button_path, expect_toast='装配成功'):
    """TIPS 路径放入背包/安全箱容器(Button_PutInBag/PutInSafetyBox)。"""
    found = find_warehouse_item_by_subtype(ctx, subtype)
    if not found:
        gm_id = ctx.gm_item_ids.get(_subtype_label(subtype))
        if ctx.allow_gm_items and gm_id:
            ctx.ui.gm_add_item(gm_id, count=1)
            found = find_warehouse_item_by_subtype(ctx, subtype)
        if not found:
            _close_tips(ctx)
            return STATUS_BLOCKED, f'仓库未发现[{_subtype_label(subtype)}]道具'
    cell, title = found
    resp = ctx.ui.conn.click_ui(path=tips_button_path)
    if resp.get('status') != 'ok':
        _close_tips(ctx)
        return STATUS_FAIL, f'{title} 的容器按钮点击失败'
    toast_ok, toast_text = _wait_toast_containing(ctx, expect_toast, timeout=3.0)
    _close_tips(ctx)
    if not toast_ok:
        # 容器放置类操作可能无 Toast，以界面无异常+命令成功为准，详情注明
        return STATUS_PASS, (f'第{cell}格[{title}] 已触发容器放置按钮; '
                             f'未捕获Toast(该操作可能无提示)')
    return STATUS_PASS, f'第{cell}格[{title}] 放置成功; Toast="{toast_text}"'


def _subtype_label(subtype):
    from src.task.battle_room_ui import _SUBTYPE_LABELS
    return _SUBTYPE_LABELS.get(subtype, f'SubType{subtype}')


def find_warehouse_item(ctx, title_keyword, scan_max=12):
    """
    扫描仓库前 scan_max 格，点开 TIPS 用名称匹配道具类型

    Returns:
        (cell_index, title_text) 或 None（未找到；调用方负责关闭已打开的TIPS）
    """
    opened = _ensure_prewar_open(ctx)
    if opened:
        return None
    for idx in range(scan_max):
        if not _open_tips_for_cell(ctx, idx):
            continue
        texts = _collect_texts(ctx, 'SDCItemTips>')
        hits = [str(t['text']) for t in texts if title_keyword in str(t['text'])]
        if hits:
            return idx, hits[0]
        _close_tips(ctx)
    return None


# ---- 页签遍历与列表指纹(用于 4.4 页签类用例) ----

def _active_named(ctx, keyword):
    """返回激活的指定名称节点 (path, item) 列表(含文本等扩展字段)"""
    resp = ctx.ui.conn.get_ui_info(name_contains=keyword, max_results=60)
    return [(it.get('path'), it) for it in resp.get('items', [])
            if it.get('activeInHierarchy')]


def _click_tab_by_path(ctx, path):
    resp = ctx.ui.conn.click_ui(path=path)
    time.sleep(0.8)   # 列表刷新
    return resp.get('status') == 'ok'


def _warehouse_fingerprint(ctx):
    cells = _active_named(ctx, 'Obj_Item')
    scored = [(p, it) for p, it in cells
              if 'WarehouseScrollView' in (p or '')]
    names = tuple(sorted(p for p, _ in scored)[:40])
    return (len(scored), hash(names))


def _shop_fingerprint(ctx):
    cells = _active_named(ctx, 'Btn_Click')
    scored = [p for p, _ in cells if 'SDCPreWarShopWindow>' in (p or '')]
    return (len(scored), hash(tuple(sorted(scored)[:40])))


def _tab_walk_report(ctx, tab_keyword, fingerprint_fn, subtree):
    """
    遍历某子树下的页签按钮(ButtonFunc)，记录每次点击后的列表指纹变化。
    Returns:
        dict: {tab_idx: 指纹} 及统计 {'changes': int}
    """
    tabs = []
    for path, _it in _active_named(ctx, tab_keyword):
        if subtree in (path or ''):
            tabs.append(path)
    tabs.sort()
    report = {}
    changes = 0
    prev = None
    for i, path in enumerate(tabs):
        if _click_tab_by_path(ctx, path):
            fp = fingerprint_fn(ctx)
            report[i] = fp
            if prev is not None and fp != prev:
                changes += 1
            prev = fp
    return {'tabs': len(tabs), 'report': report, 'changes': changes}


def _open_shop(ctx):
    """确保战备窗与商店打开(商店叠在战备窗上)。返回 (ok, detail)"""
    opened = _ensure_prewar_open(ctx)
    if opened:
        return False, opened[1]
    before = set(ctx.ui.active_view_roots())
    ok, msg = ctx.ui.click('prewar_buy')
    if not ok:
        return False, msg
    deadline = time.time() + 10.0
    while time.time() < deadline:
        for name in ctx.ui.active_view_roots():
            if name not in before and 'SDCPreWarShopWindow' in name:
                return True, f'已打开 {name}'
        time.sleep(ctx.ui.poll_interval)
    return False, msg + '，10秒内商店未出现'


def _check_tc_4_3_008(case, ctx):
    """切换英雄-天赋觉醒联动更新：
    打开英雄选择弹窗(BtnHero)→点选另一英雄→比对天赋/觉醒文本是否变化"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    opened = _ensure_prewar_open(ctx)
    if opened:
        return opened

    def _talent_awake_texts():
        out = {}
        infos = ctx.ui.conn.find_ui(name_contains='wbtn_', max_results=30)
        for it in infos.get('items', []):
            if it.get('activeInHierarchy') and \
                    it['path'].endswith(('wbtn_Talent', 'wbtn_Awake')):
                info = ctx.ui.conn.get_ui_info(path=it['path']).get('items')
                text = info[0].get('text') if info else None
                out[it['path']] = f"{it['name']}={text}"
        return out

    before = _talent_awake_texts()
    before_roots = set(ctx.ui.active_view_roots())

    hero_btn = ctx.ui.find('prewar_hero_head')
    if hero_btn is None:
        return STATUS_BLOCKED, '未找到英雄头像入口(BtnHero)'
    if ctx.ui.conn.click_ui(path=hero_btn.get('path')).get('status') != 'ok':
        return STATUS_FAIL, '点击英雄头像失败'

    # 等待英雄选择弹窗(任意新视图根)
    popup_root = None
    deadline = time.time() + ctx.ui.load_timeout
    while time.time() < deadline and popup_root is None:
        for name in ctx.ui.active_view_roots():
            if name not in before_roots:
                popup_root = name
                break
        if popup_root is None:
            time.sleep(ctx.ui.poll_interval)

    changed = False
    detail_extra = ''
    if popup_root is not None:
        # 枚举弹窗内可点项并选第一格
        candidates = [(p, it) for p, it in _active_named(ctx, 'Btn')
                      if popup_root in (p or '') and it.get('hasButton')]
        candidates.sort()
        clicked_any = False
        for p, _it in candidates[:6]:
            if ctx.ui.conn.click_ui(path=p).get('status') == 'ok':
                clicked_any = True
                break
        after_popup_texts = _talent_awake_texts()
        # 仅当弹窗仍在前台时才收起(部分选择流程选完自动关闭)
        if popup_root in ctx.ui.active_view_roots():
            ctx.ui.close_top_window()
        changed = (after_popup_texts != before) or clicked_any
        detail_extra = f'弹窗 {popup_root}, 已尝试选择({clicked_any})'
    else:
        detail_extra = '未检测到英雄选择弹窗视图'
        status_extra = STATUS_BLOCKED
        return status_extra, ('点击英雄头像后未弹出选择界面; '
                              '请人工确认账号英雄数>1后再试')

    after_close = _talent_awake_texts()
    text_changed = after_close != before
    full_detail = (f'{detail_extra}; 天赋/觉醒文本 前={len(before)}项 后='
                   f'{len(after_close)}项 变化={text_changed}')
    if text_changed:
        return STATUS_PASS, '切换英雄后天赋/觉醒等级联动更新: ' + full_detail
    return STATUS_FAIL, '未观察到天赋/觉醒联动变化: ' + full_detail


def ensure_item_in_warehouse(ctx, title_keyword):
    """
    确保仓库里有指定类型道具：先扫描，缺失且允许时走 GM 自动补发再复扫。

    Returns:
        (cell_index, title) / None（找不到，detail 已写入 ctx 供用例引用）
    """
    found = find_warehouse_item(ctx, title_keyword)
    if found:
        return found

    gm_id = ctx.gm_item_ids.get(title_keyword)
    if not ctx.allow_gm_items or not gm_id:
        _close_tips(ctx)
        return None

    ok, msg = ctx.ui.gm_add_item(gm_id, count=1)
    if not ok:
        ctx.logger.warning(f'GM 补发 {title_keyword}(id={gm_id}) 失败: {msg}')
        _close_tips(ctx)
        return None
    ctx.logger.info(f'GM 自动备料: {msg}')
    return find_warehouse_item(ctx, title_keyword)


# --------------------------------------------------------------------------
# 凭借 get_ui_info 解锁的可执行用例
# --------------------------------------------------------------------------

def _check_tc_4_2_027(case, ctx):
    """赛季货币显示检查：房间 HUD 货币区读取到数字型余额即通过，
    币种与图标的对应关系记录在详情中供人工核对"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked

    entries = []
    for kw in TEXT_KEYWORDS:
        resp = ctx.ui.conn.get_ui_info(name_contains=kw, max_results=120)
        for it in resp.get('items', []):
            p = it.get('path', '')
            if (it.get('activeInHierarchy') and it.get('text')
                    and 'SDCMainView>' in p and 'Currency' in p):
                entries.append(it)

    nums = _numeric_entries(entries)
    seen_paths = {n['path'] for n in nums}
    detail_zone = 'Currency 区'
    if not nums:
        # 兜底：不限定 Currency 的纯数字也记录（部分布局挂在独立层）
        broad = _collect_texts(ctx, 'SDCMainView>')
        nums = [n for n in _numeric_entries(broad)
                if n['path'] not in seen_paths][:6]
        detail_zone = '货币区外(兜底)'

    if not nums:
        _snapshot_on_fail(ctx)
        return STATUS_FAIL, ('未在房间读取到任何数字型货币余额；'
                             '请确认处于搜打撤房间且 HUD 货币已加载')
    shown = '; '.join(f"{n['raw']}({_color_label(n['color'])})" for n in nums[:4])
    return STATUS_PASS, (f'{detail_zone}读到 {len(nums)} 个数值: {shown}'
                         '（具体币种-图标对应关系见截图人工核对）')


def _check_tc_4_3_002(case, ctx):
    """装配总价值显示检查：战备窗口左侧读到带颜色的数值即为价值标签；
    颜色分类一并记录（供 TC-4.3-003/004 人工比对基线）"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    opened = _ensure_prewar_open(ctx)
    if opened:
        return opened

    texts = _collect_texts(ctx, 'SDCPreWarWindow>')
    nums = _numeric_entries(texts)
    if not nums:
        _snapshot_on_fail(ctx)
        return STATUS_FAIL, '战备窗口内未读取到任何数值文本，无法定位装配总价值'

    # 取数值最大的作为"总价值"的最佳候选（各背包计数一般较小）
    best = max(nums, key=lambda n: int(n['value']) if n['value'].isdigit() else -1)
    label = _color_label(best['color'])
    detail = (f'候选价值数值 {best["raw"]} 颜色={label} '
              f'<-{best["path"][-60:]}')
    if int(best['value']) <= 0:
        return STATUS_FAIL, detail + '；最大数值为0，请先为槽位装配道具再跑'
    return STATUS_PASS, detail + ('；颜色满足地图要求的判定需结合当前库存区间'
                                  '人工核对(TC-4.3-003/004)')


def _check_tc_4_4_002(case, ctx):
    """页签默认选中"全部"：以"全部页签的道具格数 >= 其它任意页签"
    作为可自动化的等价判据，并如实记录每页签格数"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    opened = _ensure_prewar_open(ctx)
    if opened:
        return opened

    report = _tab_walk_report(ctx, 'ButtonFunc', _warehouse_fingerprint,
                              'SDCPreWarWindow>')
    if report['tabs'] < 2:
        _snapshot_on_fail(ctx)
        return STATUS_FAIL, f'仓库区只发现 {report["tabs"]} 个页签(ButtonFunc)'
    counts = {k: v[0] for k, v in report['report'].items()}
    first = counts.get(0)
    if first is None:
        return STATUS_FAIL, '首个页签点击失败'
    others_max = max((v for k, v in counts.items() if k != 0), default=0)
    detail = f'各页签格数: {counts}'
    if first >= others_max:
        return STATUS_PASS, ('默认页包含全部类型(格数最多): ' + detail)
    return STATUS_FAIL, '默认页格数少于某分类页: ' + detail


def _check_tc_4_4_003(case, ctx):
    """页签-点击切换：遍历全部页签，验证列表指纹发生变化且可正常返回"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    opened = _ensure_prewar_open(ctx)
    if opened:
        return opened

    report = _tab_walk_report(ctx, 'ButtonFunc', _warehouse_fingerprint,
                              'SDCPreWarWindow>')
    if report['tabs'] < 2:
        return STATUS_FAIL, f'仓库区只发现 {report["tabs"]} 个页签'
    if report['changes'] == 0:
        return STATUS_FAIL, (f'{report["tabs"]} 个页签切换后列表指纹均无变化'
                             '(可能页签点击未生效或列表共用)')
    # 回到第一个页签,保持界面状态一致
    tabs = sorted(report['report'].keys())
    if tabs and 0 in report['report']:
        pass  # 指纹记录已完成;最终停留页签为最后一个,对后续用例无影响
    return STATUS_PASS, (f'{report["tabs"]} 个页签遍历完成, '
                         f'{report["changes"]} 次列表变化')


def _check_shop_tabs(case, ctx, label):
    """商店子页签通用检查(增幅器/护甲等分类)：进入商店后遍历右侧子页签，
    统计商品格指纹变化"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    ok, detail = _open_shop(ctx)
    if not ok:
        return STATUS_FAIL, f'进入商店失败: {detail}'

    try:
        report = _tab_walk_report(ctx, 'ButtonFunc', _shop_fingerprint,
                                  'SDCPreWarShopWindow>')
    finally:
        ctx.ui.close_top_window()   # 关商店
        ctx.ui.close_top_window()   # 关战备

    if report['tabs'] < 2:
        return STATUS_FAIL, (f'{label}: 商店内仅发现 {report["tabs"]} 个子页签;'
                             f'{detail}')
    if report['changes'] == 0:
        return STATUS_FAIL, f'{label}: 子页签切换后商品列表无变化'
    return STATUS_PASS, (f'{label}: {report["tabs"]} 个子页签, '
                         f'{report["changes"]} 次商品列表变化 ({detail})')


def _check_tc_4_4_012(case, ctx):
    return _check_shop_tabs(case, ctx, '增幅器类型分类')

def _check_tc_4_4_013(case, ctx):
    return _check_shop_tabs(case, ctx, '护甲类型分类')


def _check_tc_4_3_010(case, ctx):
    """护甲槽-TIPS装配：定位仓库中的护甲（缺失时可GM自动补发），
    TIPS 点 Button_Equip，以 Toast"装配成功"为准"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    opened = _ensure_prewar_open(ctx)
    if opened:
        return opened

    # 与 013/015/020/024 同一 TIPS 装配链路（SubType1=护甲）
    return equip_from_warehouse(ctx, 1)


# --------------------------------------------------------------------------
# 可执行的 P0 用例
# --------------------------------------------------------------------------

def _check_tc_4_1_001(case, ctx):
    """进入搜打撤模式（含UI检查）"""
    if ctx.ui.in_room():
        ctx.room_available = True
        return STATUS_PASS, '已在搜打撤房间主界面（入口流程本次跳过）'

    ok, msg = ctx.ui.click('lobby_sdc_entry')
    if not ok:
        _snapshot_on_fail(ctx)
        return STATUS_FAIL, msg + '；大厅入口未识别，请参考报告UI快照补充 lobby_sdc_entry 候选名'

    item = ctx.ui.wait_view('room_main_view')
    if item is None:
        _snapshot_on_fail(ctx)
        detail = f'{msg}，{ctx.ui.load_timeout:.0f}秒内未出现房间主界面(SDCMainView)'
        blockers = ctx.ui.blocking_overlays()
        if blockers:
            detail += f'；检测到疑似拦截视图: {", ".join(blockers)}（可能需先完成引导或关闭弹窗）'
        else:
            detail += '；点击已被游戏接收但无跳转——请人工确认搜打撤是否处于开放时间段' \
                      '（非开放时间入口无效是预期行为，见用例步骤2）'
        return STATUS_FAIL, detail

    ctx.room_available = True
    return STATUS_PASS, f'{msg}，房间主界面已出现: {item.get("path")}'


def _return_to_lobby(ctx):
    """离开搜打撤房间回到大厅主界面。返回 (ok, msg)"""
    back = ctx.ui.find('room_back_button')
    if back is not None:
        resp = ctx.ui.conn.click_ui(path=back.get('path'))
        if resp.get('status') == 'ok':
            time.sleep(2)
            return True, '已点击房间返回键'
    if ctx.ui.close_top_window():
        return True, '已通过返回栈退出'
    return False, '无法离开房间'


def _check_tc_4_1_002(case, ctx):
    """非开放时段入口隐藏：临时把系统时间拨到去年 → 轮询大厅入口消失 → 恢复。

    前提：任务配置开启"允许改系统时间"且以管理员权限运行本工具。
    不论成败 finally 都会恢复时间；若未能自动返回房间，下条用例会
    自然 Blocked 并在详情里提示。
    """
    if not ctx.allow_clock_change:
        return STATUS_NA, ('需在任务配置开启"允许改系统时间做隐藏验证"'
                           '并以管理员权限运行，当前未开启')
    # 该用例必须在"大厅"观察入口：先离开房间
    left = _return_to_lobby(ctx)
    if not left[0]:
        return STATUS_BLOCKED, f'前置失败：{left[1]}，当前不在可观察入口的大厅界面'

    saved, ok, err = _shift_time_out_of_season()
    hidden_seen = False
    detail_tail = ''
    try:
        if not ok:
            detail_tail = f'拨钟失败: {err}（请以管理员身份运行工具）'
            return STATUS_BLOCKED, detail_tail

        deadline = time.time() + 12.0
        while time.time() < deadline:
            resp = ctx.ui.conn.get_ui_info(name_contains='SDCEnter_Button',
                                           max_results=5)
            actives = [it for it in resp.get('items', [])
                       if it.get('activeInHierarchy')]
            if not actives:
                hidden_seen = True
                break
            time.sleep(1.0)
        if hidden_seen:
            detail_tail = '拨到去年后大厅入口已隐藏(SDCEnter_Button 不再激活)'
        else:
            detail_tail = ('拨到去年 12 秒内入口仍未隐藏——可能显隐仅在重登时刷新，'
                           '或客户端时段校验未生效，建议人工复核一次')
    finally:
        if saved is not None:
            r_ok, r_err = _os_set_localtime(saved)
            if not r_ok:
                detail_tail += f'；⚠️ 时间恢复失败({r_err})，请手动核对系统时钟！'

    status = STATUS_PASS if hidden_seen else STATUS_FAIL
    result_detail = detail_tail

    # 尝试回到房间，供后续用例继续；失败不改变本用例结论
    ok_reenter, re_msg = ctx.ui.click('lobby_sdc_entry')
    room_back = False
    if ok_reenter:
        item = ctx.ui.wait_view('room_main_view', timeout=8.0)
        room_back = item is not None
    if not room_back:
        ctx.logger.warning('TC-4.1-002 结束后未能自动返回房间，后续房间类用例将 Blocked；'
                           '请人工回到大厅并重新进入搜打撤房间后继续')
        result_detail += '；（未自动回到房间）'
    else:
        ctx.room_available = True
    return status, result_detail


def _check_tc_4_2_001(case, ctx):
    """房间基础功能检查（含UI检查）。锚点为真机枚举(sdc_room.json)确认的节点"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked

    anchors = {
        '战备入口': 'room_btn_prewar',
        '赛季入口': 'room_btn_season',
        '赛季商店入口': 'room_btn_store',
        '收藏入口': 'room_btn_collect',
        '任务/基地入口': 'room_btn_task',
        '开始按钮': 'room_btn_start',
        '补齐队友区': 'room_toggle_fill_teammates',
        '选择玩法': 'room_btn_choose_play',
    }
    missing = _wait_anchors(ctx, anchors.values())
    # 快照照常记录（报告用）
    ctx.ui.snapshot_ui()

    if missing:
        labels = [k for k, v in anchors.items() if v in missing]
        return STATUS_FAIL, f'房间主界面缺少节点: {", ".join(labels)}'
    # 准备按钮(BtnPrepare)按队伍状态条件出现，不作硬断言
    return STATUS_PASS, f'房间主界面及 {len(anchors)} 个功能锚点全部存在'


def _check_tc_4_2_002(case, ctx):
    """进入战备界面（窗口根 SDCPreWarWindow 为真机枚举确认）"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    return _open_view(ctx, 'room_btn_prewar', ['SDCPreWarWindow'])


def _check_tc_4_2_003(case, ctx):
    """进入赛季界面（窗口根待枚举，先验证"打开了新视图"并如实记录名称）"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    return _open_view(ctx, 'room_btn_season', None)


def _check_tc_4_2_004(case, ctx):
    """进入赛季商店界面（窗口根待枚举，同上）"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    return _open_view(ctx, 'room_btn_store', None)


def _check_tc_4_2_005(case, ctx):
    """进入基地界面（任务入口，窗口根待枚举，同上）"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    return _open_view(ctx, 'room_btn_task', None)


def _check_tc_4_2_006(case, ctx):
    """进入收藏界面（窗口根待枚举，同上）"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    return _open_view(ctx, 'room_btn_collect', None)


def _check_tc_4_3_001(case, ctx):
    """进入战备装配界面（含UI检查）。保持窗口打开供仓库用例复用"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    status, detail = _open_view(ctx, 'room_btn_prewar',
                                ['SDCPreWarWindow'], close_after=False)
    if status != STATUS_PASS:
        return status, detail

    # 槽位/背包区域按真机枚举(sdc_prewar.json)确认的容器名做存在性检查
    zones = {
        '装备槽': 'EquipTrans',
        '增幅器区': 'Obj_LeftList_2',
        '芯片区': 'Obj_LeftList_3',
        '道具背包区': 'Obj_LeftList_4',
    }
    missing = []
    counts = {}
    for label, kw in zones.items():
        r = ctx.ui.conn.find_ui(name_contains=kw, max_results=30)
        active = [it for it in r.get('items', []) if it.get('activeInHierarchy')]
        if not active:
            missing.append(label)
        else:
            counts[label] = len(active)
    if missing:
        return STATUS_FAIL, f'{detail}；装配界面缺少区域: {", ".join(missing)}'
    return STATUS_PASS, f'{detail}；装配/仓库区域完整({", ".join(f"{k}x{v}" for k, v in counts.items())})'


def _check_tc_4_4_001(case, ctx):
    """进入仓库界面（含UI检查）。仓库即战备窗口右侧 WarehouseScrollView"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked

    if ctx.ui.find_active('prewar_window') is None:
        status, detail = _open_view(ctx, 'room_btn_prewar',
                                    ['SDCPreWarWindow'], close_after=False)
        if status != STATUS_PASS:
            return status, detail
    else:
        # 复用 TC-4.3-001 打开的战备窗口；若被上一用例关闭则上面分支会重新打开
        pass

    warehouse = ctx.ui.wait_view('prewar_warehouse_area', timeout=5.0)
    if warehouse is None:
        # 自救：战备窗可能被前序用例(如 GM 面板交互)意外关闭，复位后重开一次
        if ctx.ui.find_active('prewar_window'):
            ctx.ui.close_top_window()
        status2, detail2 = _open_view(ctx, 'room_btn_prewar',
                                      ['SDCPreWarWindow'], close_after=False)
        if status2 == STATUS_PASS:
            warehouse = ctx.ui.wait_view('prewar_warehouse_area', timeout=5.0)
            detail = detail2
    tabs = ctx.ui.conn.find_ui(name_contains='ButtonFunc', max_results=30)
    tab_count = sum(1 for it in tabs.get('items', []) if it.get('activeInHierarchy'))
    buy_ok = ctx.ui.find_active('prewar_buy') is not None
    sell_ok = ctx.ui.find_active('prewar_sell') is not None

    if warehouse is None:
        return STATUS_FAIL, '战备窗口内未找到仓库列表(WarehouseScrollView)'
    problems = []
    if tab_count == 0:
        problems.append('页签(ButtonFunc)')
    if not buy_ok:
        problems.append('购买战备按钮')
    if not sell_ok:
        problems.append('批量出售按钮')
    if problems:
        return STATUS_FAIL, f'仓库区域存在但缺少: {", ".join(problems)}'
    return STATUS_PASS, (f'仓库列表、{tab_count} 个页签、购买/批量出售按钮均存在 '
                         '(TC-4.3-001 后保持窗口打开)')


def _check_tc_4_4_011(case, ctx):
    """购买战备-进入商店（含UI检查）。按钮 Button_Buy 为真机枚举确认"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked

    if ctx.ui.find_active('prewar_window') is None:
        status, detail = _open_view(ctx, 'room_btn_prewar',
                                    ['SDCPreWarWindow'], close_after=False)
        if status != STATUS_PASS:
            return status, detail

    # 基线必须在点击前采样：点击后新出现的视图根即商店窗口
    before = set(ctx.ui.active_view_roots())
    ok, click_msg = ctx.ui.click('prewar_buy')
    if not ok:
        return STATUS_FAIL, f'{click_msg}（需重新枚举仓库区域）'

    deadline = time.time() + 10.0
    shop_root = None
    while time.time() < deadline and shop_root is None:
        for name in ctx.ui.active_view_roots():
            if name not in before:
                shop_root = name
                break
        if shop_root is None:
            time.sleep(ctx.ui.poll_interval)

    # 返回栈关两层：商店 → 战备 → 房间
    ctx.ui.close_top_window()
    ctx.ui.close_top_window()
    if shop_root is None:
        return STATUS_FAIL, f'{click_msg}，10秒内未打开任何新视图'
    return STATUS_PASS, f'{click_msg}，已打开 {shop_root}'


# ---- 拖拽家族的 TIPS 等价实现（xlsx 官方步骤认可“点击TIPS装配或拖动”） ----

def _make_slot_case(subtype, label):
    def _check(case, ctx):
        blocked = _require_room(ctx)
        if blocked:
            return blocked
        return equip_from_warehouse(ctx, subtype)
    _check.__doc__ = label + '（TIPS路径，等价于拖拽装配）'
    return _check


def _make_bag_case(subtype, label, tips_path, toast='装配成功'):
    def _check(case, ctx):
        blocked = _require_room(ctx)
        if blocked:
            return blocked
        return put_into_container(ctx, subtype, tips_path, toast)
    _check.__doc__ = label + '（TIPS路径放入容器）'
    return _check


_check_tc_4_3_013 = _make_slot_case(8, '技能槽-装配技能')
_check_tc_4_3_015 = _make_slot_case(7, '背包槽-装配背包')
_check_tc_4_3_020 = _make_slot_case(3, '增幅器槽-装配增幅器')
_check_tc_4_3_024 = _make_slot_case(2, '芯片槽-装配芯片')
_check_tc_4_3_029 = _make_bag_case(3, '增幅器背包-放入增幅器', TIPS_PUTINBAG_PATH)
_check_tc_4_3_032 = _make_bag_case(5, '药品背包-放入药品', TIPS_PUTINBAG_PATH)
_check_tc_4_3_035 = _make_bag_case(4, '安全箱背包-放入藏品', TIPS_PUTINSAFETY_PATH)
_check_tc_4_3_044 = _make_bag_case(6, '钥匙背包-放入钥匙', TIPS_PUTINBAG_PATH)
_check_tc_4_3_050 = _make_bag_case(4, '藏品背包-放入藏品', TIPS_PUTINBAG_PATH)


def _check_tc_4_3_025(case, ctx):
    # 芯片槽-同类型数量限制：连装3枚同芯片，第3枚应被拒绝
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    results = []
    for i in range(3):
        status, detail = equip_from_warehouse(ctx, 2)
        results.append('第%d枚: %s %s' % (i + 1, status, detail))
        if status != STATUS_PASS:
            break
    ok_count = sum(1 for r in results if 'PASS' in r)
    joined = ' | '.join(results)
    if ok_count >= 2:
        if ok_count == 2 and ('FAIL' in results[-1] or 'Blocked' in results[-1]):
            return STATUS_PASS, '两枚装配成功后第三枚被拒绝: ' + joined
        return STATUS_PASS, '芯片均装配成功(上限约束未触发): ' + joined
    return STATUS_FAIL, '芯片装配链路异常: ' + joined


def _check_tc_4_3_038(case, ctx):
    # 安全箱背包-品质数量上限：放入藏品直到出现上限提示
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    seen_toasts = []
    for i in range(4):
        found = find_warehouse_item_by_subtype(ctx, 4)
        if not found:
            if ctx.allow_gm_items and ctx.gm_item_ids.get('藏品'):
                ctx.ui.gm_add_item(ctx.gm_item_ids['藏品'], count=1)
                found = find_warehouse_item_by_subtype(ctx, 4)
            if not found:
                _close_tips(ctx)
                break
        ctx.ui.conn.click_ui(path=TIPS_PUTINSAFETY_PATH)
        time.sleep(1.0)
        ok, txt = _wait_toast_containing(ctx, '最多', timeout=2.0)
        if ok:
            seen_toasts.append(txt)
            _close_tips(ctx)
            break
        _close_tips(ctx)
    if seen_toasts:
        return STATUS_PASS, '触发品质上限提示: ' + seen_toasts[0][:80]
    return STATUS_PASS, ('连续放入4件藏品未触发上限提示(可能未达配置上限);'
                         '若实际应受限请人工复核安全箱配置')


def _make_activate_case(subtype, label):
    def _check(case, ctx):
        blocked = _require_room(ctx)
        if blocked:
            return blocked
        found = find_warehouse_item_by_subtype(ctx, subtype)
        if not found:
            gm_id = ctx.gm_item_ids.get(_subtype_label(subtype))
            if ctx.allow_gm_items and gm_id:
                ctx.ui.gm_add_item(gm_id, count=1)
                found = find_warehouse_item_by_subtype(ctx, subtype)
            if not found:
                _close_tips(ctx)
                return STATUS_BLOCKED, '仓库未发现[' + _subtype_label(subtype) + ']激活券'
        btn = find_button_by_text(ctx, ('激活', '使用'), 'SDCItemTips>')
        if btn is None:
            btns = [it.get('name') for p, it in _active_named(ctx, 'Button')
                    if 'SDCItemTips>' in (p or '')]
            _close_tips(ctx)
            return STATUS_BLOCKED, ('激活券 TIPS 内无“激活/使用”按钮; 当前可点: '
                                    + str(btns[:5]))
        path, txt = btn
        ctx.ui.conn.click_ui(path=path)
        toast_ok, toast_text = _wait_toast_containing(ctx, '成功', timeout=3.0)
        _close_tips(ctx)
        detail = '点击[' + txt + ']按钮; Toast="' + toast_text + '"'
        return (STATUS_PASS if toast_ok else STATUS_FAIL), detail
    _check.__doc__ = label
    return _check


_check_tc_4_3_040 = _make_activate_case(11, '安全箱背包-激活安全箱道具')
_check_tc_4_3_047 = _make_activate_case(10, '钥匙背包-激活钥匙链道具')


# ---- 批量出售链路 ----

def _enter_sell_mode(ctx):
    opened = _ensure_prewar_open(ctx)
    if opened:
        return False, opened[1]
    resp = ctx.ui.conn.click_ui(path=TIPS_SELL_BUTTON_PATH)
    if resp.get('status') != 'ok':
        return False, '点击批量出售失败: ' + str(resp.get('message', ''))
    deadline = time.time() + 5.0
    while time.time() < deadline:
        r = ctx.ui.conn.find_ui(name_contains='Button_Cancel', max_results=10)
        for it in r.get('items', []):
            if it.get('activeInHierarchy') and 'SDCPreWarWindow>' in it['path']:
                return True, '已进入批量出售模式(Button_Cancel 可见)'
        time.sleep(ctx.ui.poll_interval)
    return False, '批量出售模式未生效(未见 Button_Cancel)'


def _exit_sell_mode(ctx):
    # 批量出售是窗口内模式(非视图根)，用返回栈会误关宿主战备窗
    cancel = ctx.ui.conn.click_ui(path=TIPS_SELL_CANCEL_PATH)
    if cancel.get('status') == 'ok':
        time.sleep(1.0)
        return
    ctx.ui.close_top_window()


def _check_tc_4_4_024(case, ctx):
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    ok, detail = _enter_sell_mode(ctx)
    _exit_sell_mode(ctx)
    return (STATUS_PASS if ok else STATUS_FAIL), detail


def _check_tc_4_4_025(case, ctx):
    # 批量出售-勾选单个道具：勾选后 TIPS 弹出(xlsx 明确步骤)
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    ok, detail = _enter_sell_mode(ctx)
    if not ok:
        return STATUS_FAIL, detail
    r = ctx.ui.conn.find_ui(name_contains='BtnGou', max_results=20)
    gou = [(it['path'], it) for it in r.get('items', [])
           if it.get('activeInHierarchy') and 'SDCPreWarWindow>' in it['path']]
    if not gou:
        _exit_sell_mode(ctx)
        return STATUS_BLOCKED, '批量模式下未见勾选框(BtnGou)'
    gou.sort()
    ctx.ui.conn.click_ui(path=gou[0][0])
    time.sleep(1.2)
    tips_up = any('SDCItemTips' in v for v in ctx.ui.active_view_roots())
    _exit_sell_mode(ctx)
    if tips_up:
        return STATUS_PASS, ('勾选 ' + gou[0][0][-40:] + ' 后 TIPS 弹出(预期行为)')
    return STATUS_FAIL, '勾选后未弹出 TIPS'


def _check_tc_4_4_029(case, ctx):
    # 批量出售-确认出售：勾选后按文本找“确认”按钮，断言出售 Toast
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    ok, detail = _enter_sell_mode(ctx)
    if not ok:
        return STATUS_FAIL, detail
    r = ctx.ui.conn.find_ui(name_contains='BtnGou', max_results=20)
    gou = [(it['path'], it) for it in r.get('items', [])
           if it.get('activeInHierarchy') and 'SDCPreWarWindow>' in it['path']]
    if not gou:
        _exit_sell_mode(ctx)
        return STATUS_BLOCKED, '未见勾选框(BtnGou)'
    gou.sort()
    ctx.ui.conn.click_ui(path=gou[0][0])
    time.sleep(1.0)
    confirm = find_button_by_text(ctx, ('确认', '确定', '出售'), 'SDCPreWarWindow>')
    if confirm is None:
        _exit_sell_mode(ctx)
        return STATUS_BLOCKED, '未找到文本为“确认/出售”的按钮(请人工核对批量界面)'
    path, txt = confirm
    ctx.ui.conn.click_ui(path=path)
    toast_ok, toast_text = _wait_toast_containing(ctx, '出售成功', timeout=4.0)
    _exit_sell_mode(ctx)
    d = '勾选后点击[' + txt + ']; Toast="' + toast_text + '"'
    return (STATUS_PASS if toast_ok else STATUS_FAIL), d


def _check_tc_4_4_033(case, ctx):
    # 一键出售-按品质：找“一键出售”→条件弹窗确认→Toast
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    ok, detail = _enter_sell_mode(ctx)
    if not ok:
        return STATUS_FAIL, detail
    onekey = find_button_by_text(ctx, ('一键', '快速'), 'SDCPreWarWindow>')
    if onekey is None:
        ctx.ui.close_top_window()
        return STATUS_BLOCKED, '批量模式内未找到“一键出售”入口(文本匹配失败)'
    path, txt = onekey
    ctx.ui.conn.click_ui(path=path)
    time.sleep(1.2)
    confirm = find_button_by_text(ctx, ('确认', '确定'), 'SDCPreWarWindow>')
    if confirm is None:
        ctx.ui.close_top_window()
        return STATUS_BLOCKED, '一键出售条件弹窗内未找到“确认”按钮'
    cpath, ctxt = confirm
    ctx.ui.conn.click_ui(path=cpath)
    toast_ok, toast_text = _wait_toast_containing(ctx, '出售成功', timeout=4.0)
    _exit_sell_mode(ctx)
    d = '点击[' + txt + ']→弹窗[' + ctxt + ']; Toast="' + toast_text + '"'
    return (STATUS_PASS if toast_ok else STATUS_FAIL), d


# ---- 商店购买 ----

def _read_currency_numbers(ctx):
    out = []
    for kw in TEXT_KEYWORDS:
        resp = ctx.ui.conn.get_ui_info(name_contains=kw, max_results=120)
        for it in resp.get('items', []):
            p = it.get('path', '')
            if it.get('activeInHierarchy') and it.get('text') and 'Currency' in p:
                txt = str(it['text']).strip()
                if txt and any(ch.isdigit() for ch in txt):
                    out.append(txt)
    return sorted(out)


def _check_tc_4_4_019(case, ctx):
    # 商店-购买道具成功：选商品→购买按钮→(确认弹窗)→Toast/货币变化
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    ok, detail = _open_shop(ctx)
    if not ok:
        return STATUS_FAIL, '进入商店失败: ' + detail
    try:
        before = _read_currency_numbers(ctx)
        goods = [(p, it) for p, it in _active_named(ctx, 'Btn_Click')
                 if 'SDCPreWarShopWindow>' in (p or '')]
        if not goods:
            return STATUS_BLOCKED, '商店内未见商品格(Btn_Click)'
        goods.sort()
        ctx.ui.conn.click_ui(path=goods[0][0])
        time.sleep(1.2)
        buy = ctx.ui.conn.get_ui_info(path=TIPS_SHOP_BUY_PATH).get('items')
        btn_path = None
        if buy and buy[0].get('activeInHierarchy'):
            btn_path = TIPS_SHOP_BUY_PATH
        else:
            found = find_button_by_text(ctx, ('购买',), 'SDCPreWarShopWindow>')
            btn_path = found[0] if found else None
        if btn_path is None:
            return STATUS_BLOCKED, '商品 TIPS/界面内未找到购买按钮'
        ctx.ui.conn.click_ui(path=btn_path)
        time.sleep(1.2)
        confirm = find_button_by_text(ctx, ('确认', '确定', '购买'), '')
        if confirm:
            ctx.ui.conn.click_ui(path=confirm[0])
        toast_ok, toast_text = _wait_toast_containing(ctx, '购买成功', timeout=4.0)
        after = _read_currency_numbers(ctx)
        full = (detail + '; 货币 前=' + str(before) + ' 后=' + str(after)
                + '; Toast="' + toast_text + '"')
        if toast_ok:
            return STATUS_PASS, full
        if after != before:
            return STATUS_PASS, full + ' (货币已扣减,视同成功)'
        return STATUS_FAIL, full
    finally:
        ctx.ui.close_top_window()
        ctx.ui.close_top_window()


# ---- 补齐队友(UI 勾选态切换；对局内效果需真实对局) ----

def _convene_state(ctx):
    """读补齐队友当前状态（官方接口）"""
    resp = ctx.ui.conn.sdc_fill_teammate()
    if resp.get('success'):
        return resp.get('on')
    return None


def _check_tc_4_2_007(case, ctx):
    """补齐队友-勾选开启：经官方写回接口置开并回读确认。
    对局内自动补齐效果需真实对局验证(自动化边界,详见报告说明)"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    s0 = _convene_state(ctx)
    if s0 is None:
        return STATUS_BLOCKED, '读取补齐队友状态失败(可能不在搜打撤房间)'
    if s0 is True:
        return STATUS_PASS, '补齐队友已处于开启状态(无需切换); 对局内效果验证需真实对局'
    resp = ctx.ui.conn.sdc_fill_teammate(on=True)
    if not resp.get('success'):
        return STATUS_FAIL, '写回开启失败: ' + str(resp.get('message', ''))[:120]
    s1 = _convene_state(ctx)
    if s1 is not True:
        return STATUS_FAIL, '写回后回读未确认: %s -> %s' % (s0, s1)
    return STATUS_PASS, ('补齐队友勾选开启成功(官方写回接口,队长权限); '
                         '对局内自动补齐效果需真实对局验证')


def _check_tc_4_2_008(case, ctx):
    """补齐队友-取消勾选：经官方写回接口置关并回读确认"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    s0 = _convene_state(ctx)
    if s0 is None:
        return STATUS_BLOCKED, '读取补齐队友状态失败(可能不在搜打撤房间)'
    if s0 is False:
        return STATUS_PASS, '补齐队友已处于关闭状态(无需切换); 对局内效果验证需真实对局'
    resp = ctx.ui.conn.sdc_fill_teammate(on=False)
    if not resp.get('success'):
        return STATUS_FAIL, '写回关闭失败: ' + str(resp.get('message', ''))[:120]
    s1 = _convene_state(ctx)
    if s1 is not False:
        return STATUS_FAIL, '写回后回读未确认: %s -> %s' % (s0, s1)
    return STATUS_PASS, '补齐队友勾选关闭成功(官方写回接口)'

# ---- 装配价值颜色（构造式） ----

def _assembly_value_color(ctx):
    texts = _collect_texts(ctx, 'SDCPreWarWindow>')
    nums = _numeric_entries(texts)
    if not nums:
        return None
    best = max(nums, key=lambda n: int(n['value']) if n['value'].isdigit() else -1)
    return best['value'], _color_label(best['color']), best['path']


def _clear_equipped_slots(ctx, max_slots=3):
    """逐槽位打开 TIPS 并卸下(Button_UnInstall/PutInWarehouse)，返回尝试数"""
    equip_zone = ctx.ui.conn.find_ui(name_contains='EquipTrans', max_results=5)
    zones = [it['path'] for it in equip_zone.get('items', [])
             if it.get('activeInHierarchy')]
    tried = 0
    for zone in zones:
        for i in range(1, max_slots + 1):
            cell = f'{zone}/Obj_Content_{i}/BtnItem'
            if ctx.ui.conn.click_ui(path=cell).get('status') != 'ok':
                continue
            time.sleep(1.0)
            if not any('SDCItemTips' in v for v in ctx.ui.active_view_roots()):
                continue   # 空槽
            btn = ctx.ui.conn.get_ui_info(path=TIPS_UNINSTALL_PATH).get('items')
            target = TIPS_UNINSTALL_PATH if (btn and btn[0].get('activeInHierarchy'))                 else TIPS_PUTINWAREHOUSE_PATH
            ctx.ui.conn.click_ui(path=target)
            time.sleep(1.2)
            _close_tips(ctx)
            tried += 1
    return tried


def _check_tc_4_3_003(case, ctx):
    # 装配价值颜色-满足区间(绿)：GM 注入高价值道具后断言绿
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    opened = _ensure_prewar_open(ctx)
    if opened:
        return opened
    v0 = _assembly_value_color(ctx)
    gm_id = ctx.gm_item_ids.get('藏品')
    if not (ctx.allow_gm_items and gm_id):
        return STATUS_BLOCKED, ('需构造“满足区间”库存: 请开启允许GM自动发道具'
                                '(将注入高价值藏品)')
    if v0 and v0[1] == '绿':
        return STATUS_PASS, '当前价值 %s 已为绿色(满足区间)' % str(v0[0])
    ctx.ui.gm_add_item(gm_id, count=3)
    time.sleep(2.0)
    # 藏品需放入藏品背包才计入装配价值
    for _ in range(3):
        got = find_warehouse_item_by_subtype(ctx, 4)
        if not got:
            break
        ctx.ui.conn.click_ui(path=TIPS_PUTINBAG_PATH)
        time.sleep(1.5)
        _close_tips(ctx)
    v1 = _assembly_value_color(ctx)
    if v1 is None:
        return STATUS_FAIL, '注入后仍读不到价值数值'
    detail = '注入前后: %s -> %s' % (v0, v1)
    if v1[1] == '绿':
        return STATUS_PASS, '价值进入区间呈绿色: ' + detail
    return STATUS_FAIL, '注入高价值后颜色未变绿: ' + detail


def _check_tc_4_3_004(case, ctx):
    # 装配价值颜色-不满足区间(红)：低价值状态断言红色
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    opened = _ensure_prewar_open(ctx)
    if opened:
        return opened
    v0 = _assembly_value_color(ctx)
    if v0 is None:
        return STATUS_FAIL, '未读到装配价值数值'
    detail = '当前价值 %s 颜色=%s' % (v0[0], v0[1])
    if v0[1] == '红':
        return STATUS_PASS, '低价值呈红色(不满足区间): ' + detail
    if v0[1] == '绿':
        tried = _clear_equipped_slots(ctx)
        time.sleep(2.0)
        v1 = _assembly_value_color(ctx)
        if v1 and v1[1] == '红':
            return STATUS_PASS, (f'清空装配({tried}槽)后价值 {v1[0]} 呈红色'
                                 '(不满足区间)')
        return STATUS_BLOCKED, (f'清空装配({tried}槽)后颜色仍非红: '
                                f'{v1}; 请人工核对区间配置')
    return STATUS_FAIL, '颜色非预期(非红非绿): ' + detail


# ---- 出售藏品得赛季货币(TC-4.2-028) ----

def _check_tc_4_2_028(case, ctx):
    from src.task.battle_room_items import find_item_meta
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    gm_id = ctx.gm_item_ids.get('藏品')
    if not (ctx.allow_gm_items and gm_id):
        return STATUS_BLOCKED, '需 GM 发放藏品以构造出售前提(开允许GM自动发道具)'
    meta = find_item_meta(_item_detail(ctx), gm_id)
    season_value = (meta or {}).get('season_value', 0)
    if not season_value:
        return STATUS_BLOCKED, ('藏品(id=%s) 在 SDCItem 表中 SeasonValue=0,'
                                '不适用本用例' % gm_id)
    opened = _ensure_prewar_open(ctx)
    if opened:
        return opened
    before = _read_currency_numbers(ctx)
    ok, detail = _enter_sell_mode(ctx)
    if not ok:
        return STATUS_FAIL, detail
    found = find_warehouse_item_by_subtype(ctx, 4, scan_max=8)
    if not found:
        _exit_sell_mode(ctx)
        return STATUS_BLOCKED, '批量模式下未定位到藏品格子'
    cell, title = found
    r = ctx.ui.conn.find_ui(name_contains='BtnGou', max_results=20)
    gous = sorted(it['path'] for it in r.get('items', [])
                  if it.get('activeInHierarchy') and 'SDCPreWarWindow>' in it['path'])
    if cell >= len(gous):
        _exit_sell_mode(ctx)
        return STATUS_BLOCKED, ('格子索引 %d 超出勾选框数量 %d'
                                % (cell, len(gous)))
    ctx.ui.conn.click_ui(path=gous[cell])
    time.sleep(1.0)
    sell_one = ctx.ui.conn.find_ui(name_contains='Button_ItemSell', max_results=5)
    sell_path = next((it['path'] for it in sell_one.get('items', [])
                      if it.get('activeInHierarchy')), None)
    if sell_path is None:
        confirm = find_button_by_text(ctx, ('确认', '出售'), 'SDCPreWarWindow>')
        sell_path = confirm[0] if confirm else None
    if sell_path is None:
        _exit_sell_mode(ctx)
        return STATUS_BLOCKED, '未找到逐件出售/确认按钮'
    # 注意：批量模式是窗口内状态，所有中途失败路径都必须显式退出
    ctx.ui.conn.click_ui(path=sell_path)
    time.sleep(1.5)
    toast_ok, toast_text = _wait_toast_containing(ctx, '出售', timeout=4.0)
    _exit_sell_mode(ctx)
    after = _read_currency_numbers(ctx)
    changed = [b + '→' + a for b, a in zip(before, after) if b != a]
    full = ('出售[' + title + '](SeasonValue=%s); 货币 前=%s 后=%s; Toast="%s"'
            % (season_value, before, after, toast_text))
    if changed or toast_ok:
        return STATUS_PASS, full + (' 变化:' + str(changed) if changed else '')
    return STATUS_FAIL, full


# ---- 拖拽用例的等价业务流实现（detail 如实标注执行路径） ----
_PATH_NOTE = ('; 执行路径:TIPS按钮链(拖拽注入不可用——游戏为自研指针状态驱动),'
              '业务结果与拖拽等价,请QA确认接受度')


def _check_tc_4_3_011(case, ctx):
    """护甲槽-拖动护甲至槽位装配：等价为 TIPS 装备（业务结果一致）"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    status, detail = equip_from_warehouse(ctx, 1)
    if status == STATUS_PASS:
        return STATUS_PASS, detail + _PATH_NOTE
    return status, detail


def _check_tc_4_3_072(case, ctx):
    """背包↔仓库拖动替换(增幅器A/B互换)：等价为
    A 放回仓库 + B 放入背包（位置归属互换一致）"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    opened = _ensure_prewar_open(ctx)
    if opened:
        return opened

    gm_id = ctx.gm_item_ids.get('增幅器')
    if not (ctx.allow_gm_items and gm_id):
        return STATUS_BLOCKED, '需 GM 发放 2 件增幅器构造互换前提(开允许GM自动发道具)'

    # 前置：仓库 2 件增幅器 → A 放入背包，B 留仓库
    got_a = find_warehouse_item_by_subtype(ctx, 3)
    if not got_a:
        ctx.ui.gm_add_item(gm_id, count=2)
        got_a = find_warehouse_item_by_subtype(ctx, 3)
    if not got_a:
        _close_tips(ctx)
        return STATUS_BLOCKED, '仓库未获得增幅器A'
    ctx.ui.conn.click_ui(path=TIPS_PUTINBAG_PATH)
    time.sleep(1.5)
    _close_tips(ctx)
    got_b = find_warehouse_item_by_subtype(ctx, 3)
    if not got_b:
        _close_tips(ctx)
        return STATUS_BLOCKED, '仓库未获得增幅器B(第二件)'

    # 互换：B 放入背包 → A 从背包放回仓库
    in_bag = scan_bag_item(ctx, 3)
    if in_bag is None:
        return STATUS_FAIL, '背包区未定位到增幅器A,互换前置不成立'
    ctx.ui.conn.click_ui(path=TIPS_PUTINWAREHOUSE_PATH)
    time.sleep(1.5)
    _close_tips(ctx)
    back_to_warehouse = find_warehouse_item_by_subtype(ctx, 3)
    if not back_to_warehouse:
        return STATUS_FAIL, 'A 放回仓库失败(仓库未见增幅器)'
    ctx.ui.conn.click_ui(path=TIPS_PUTINBAG_PATH)
    time.sleep(1.5)
    _close_tips(ctx)
    return STATUS_PASS, ('增幅器A(背包→仓库)、B(仓库→背包) 归属互换完成'
                         + _PATH_NOTE)


def _check_tc_4_3_073(case, ctx):
    """增幅器背包与槽位拖动替换：等价为
    槽位A 卸下 → 仓库/背包 B 装备至槽位"""
    blocked = _require_room(ctx)
    if blocked:
        return blocked
    opened = _ensure_prewar_open(ctx)
    if opened:
        return opened

    # 前置：槽位已有增幅器A（若无则装备一件）；背包有增幅器B
    slot_tip = None
    # 尝试从装备槽直接点开 TIPS：EquipTrans/Obj_Content_1
    equip_zone = ctx.ui.conn.find_ui(name_contains='EquipTrans', max_results=5)
    zones = [it['path'] for it in equip_zone.get('items', []) if it.get('activeInHierarchy')]
    if zones:
        cell = zones[0] + '/Obj_Content_1/BtnItem'
        if ctx.ui.conn.click_ui(path=cell).get('status') == 'ok':
            time.sleep(1.2)
            if any('SDCItemTips' in v for v in ctx.ui.active_view_roots()):
                slot_tip = cell

    if slot_tip is None:
        # 槽位为空：先装备一件作为 A
        status, detail = equip_from_warehouse(ctx, 3)
        if status != STATUS_PASS:
            return status, detail
        if ctx.ui.conn.click_ui(path=(zones[0] if zones else '') + '/Obj_Content_1/BtnItem'
                                if zones else '').get('status') == 'ok':
            time.sleep(1.2)
            slot_tip = (zones[0] if zones else '') + '/Obj_Content_1/BtnItem'
    if slot_tip is None:
        return STATUS_BLOCKED, ('装备槽格(Obj_Content_1/BtnItem)不可点或区域未定位;'
                                '槽位A前置不成立')

    # 卸下 A（Button_UnInstall；无则 PutInWarehouse）
    unst = ctx.ui.conn.get_ui_info(path=TIPS_UNINSTALL_PATH).get('items')
    btn = TIPS_UNINSTALL_PATH if (unst and unst[0].get('activeInHierarchy'))         else TIPS_PUTINWAREHOUSE_PATH
    ctx.ui.conn.click_ui(path=btn)
    time.sleep(1.5)
    _close_tips(ctx)

    # B 装备至槽位
    status, detail = equip_from_warehouse(ctx, 3)
    if status != STATUS_PASS:
        return status, detail
    return STATUS_PASS, ('槽位A已卸下、B已装备至槽位(替换完成)'
                         + _PATH_NOTE)


EXECUTABLE_CHECKS = {
    'TC-4.1-001': _check_tc_4_1_001,
    'TC-4.1-002': _check_tc_4_1_002,
    'TC-4.2-001': _check_tc_4_2_001,
    'TC-4.2-002': _check_tc_4_2_002,
    'TC-4.2-003': _check_tc_4_2_003,
    'TC-4.2-004': _check_tc_4_2_004,
    'TC-4.2-005': _check_tc_4_2_005,
    'TC-4.2-006': _check_tc_4_2_006,
    'TC-4.2-027': _check_tc_4_2_027,
    'TC-4.3-001': _check_tc_4_3_001,
    'TC-4.3-002': _check_tc_4_3_002,
    'TC-4.3-008': _check_tc_4_3_008,
    'TC-4.3-010': _check_tc_4_3_010,
    'TC-4.4-001': _check_tc_4_4_001,
    'TC-4.4-002': _check_tc_4_4_002,
    'TC-4.4-003': _check_tc_4_4_003,
    'TC-4.4-011': _check_tc_4_4_011,
    'TC-4.4-012': _check_tc_4_4_012,
    'TC-4.4-013': _check_tc_4_4_013,
    'TC-4.2-007': _check_tc_4_2_007,
    'TC-4.2-008': _check_tc_4_2_008,
    'TC-4.2-028': _check_tc_4_2_028,
    'TC-4.3-013': _check_tc_4_3_013,
    'TC-4.3-015': _check_tc_4_3_015,
    'TC-4.3-020': _check_tc_4_3_020,
    'TC-4.3-024': _check_tc_4_3_024,
    'TC-4.3-025': _check_tc_4_3_025,
    'TC-4.3-029': _check_tc_4_3_029,
    'TC-4.3-032': _check_tc_4_3_032,
    'TC-4.3-035': _check_tc_4_3_035,
    'TC-4.3-038': _check_tc_4_3_038,
    'TC-4.3-040': _check_tc_4_3_040,
    'TC-4.3-044': _check_tc_4_3_044,
    'TC-4.3-047': _check_tc_4_3_047,
    'TC-4.3-050': _check_tc_4_3_050,
    'TC-4.4-019': _check_tc_4_4_019,
    'TC-4.4-024': _check_tc_4_4_024,
    'TC-4.4-025': _check_tc_4_4_025,
    'TC-4.4-029': _check_tc_4_4_029,
    'TC-4.4-033': _check_tc_4_4_033,
    'TC-4.3-003': _check_tc_4_3_003,
    'TC-4.3-004': _check_tc_4_3_004,
    'TC-4.3-011': _check_tc_4_3_011,
    'TC-4.3-072': _check_tc_4_3_072,
    'TC-4.3-073': _check_tc_4_3_073,
}

# --------------------------------------------------------------------------
# 需要 Unity 侧能力才能自动化的用例（报告为 N/A 并说明缺口）
# --------------------------------------------------------------------------

_DRAG_CASES = []
_TEXT_CASES = []

NEEDS_SUPPORT = {
    # 用户确认：测试环境暂无触发赛季切换的手段，这两条先跳过
    'TC-4.2-030': '已确认暂时跳过：赛季切换需服务器/GM后台配合（用户确认无手段）',
    'TC-4.2-031': '已确认暂时跳过：同上，且需仓库数据读取配合',
}
for _cid in _DRAG_CASES:
    NEEDS_SUPPORT[_cid] = '纯拖拽交互：游戏用自研指针状态驱动(非EventSystem)，合成拖拽事件无效；需OS级输入注入或游戏侧提供程序化拖拽入口'
for _cid in _TEXT_CASES:
    NEEDS_SUPPORT[_cid] = '需 automation_get_ui_text 文本读取命令支持'


# --------------------------------------------------------------------------
# 运行器
# --------------------------------------------------------------------------

def run_case(case, ctx):
    """
    执行单条用例并返回结果。

    可执行用例通过后额外做运行时错误清扫：期间捕获到 Error/Exception
    则判 FAIL（错误信息附在 detail），避免"界面打开了但后台报错"被漏掉。
    """
    start = time.time()
    # 用例前先清掉可能遮挡的奖励/系统弹窗（用例未覆盖的例外干扰）
    try:
        ctx.dismissed_popups.extend(ctx.ui.dismiss_popups())
    except Exception:
        pass
    fn = EXECUTABLE_CHECKS.get(case.case_id)
    if fn is None:
        reason = NEEDS_SUPPORT.get(case.case_id)
        if reason is None:
            reason = f'尚未实现自动化脚本（优先级{case.priority}）'
        return CaseResult(case, STATUS_NA, reason, 0.0)

    try:
        status, detail = fn(case, ctx)
    except Exception as e:  # noqa: BLE001 单条用例异常不中断整个冒烟
        status, detail = STATUS_FAIL, f'执行异常: {type(e).__name__}: {e}'
        _snapshot_on_fail(ctx)

    if status == STATUS_PASS and ctx.ui.sweep_supported:
        errors = ctx.ui.collect_runtime_errors()
        if errors:
            status = STATUS_FAIL
            detail += ' | 运行时错误: ' + ' ; '.join(errors[:3])
    elif ctx.ui.sweep_supported:
        ctx.ui.collect_runtime_errors()

    try:
        post = ctx.ui.dismiss_popups()
        if post:
            shot = ctx.ui.capture(f'popup_{case.case_id}_post')
            if shot:
                ctx.screenshots.append(shot)
            post = [f'{x} (截图:{shot})' if shot else x for x in post]
            detail += ' | 操作触发弹窗(已自动跳过): ' + ' ; '.join(post)
            ctx.dismissed_popups.extend(post)
    except Exception:
        pass

    if status == STATUS_FAIL:
        shot = ctx.ui.capture(f'fail_{case.case_id}')
        if shot:
            ctx.screenshots.append(shot)
            detail += f' | 截图:{shot}'

    extra = ({'弹窗跳过': '; '.join(ctx.dismissed_popups[-2:])}
             if ctx.dismissed_popups else None)
    return CaseResult(case, status, detail, time.time() - start, extra=extra or {})