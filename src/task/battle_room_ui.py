# -*- coding: utf-8 -*-
"""
战备房间 UI 解析与导航辅助

Unity 插件侧 automation_find_ui / automation_click_ui 按名称查找 UI，
但游戏内大量节点名未在插件中登记。本模块用"逻辑名 → 候选名列表"的
方式在运行时解析真实路径：候选命中即缓存；全部未命中返回 None，
由用例报告"UI名待补充"。候选表是纯数据，跑完一次冒烟后按报告里
的 UI 快照补充即可，无需改逻辑代码。
"""

import datetime
import json
import os
import time

# 逻辑名 → 候选列表。候选两种形态：
#   "@path:<完整路径>"   按精确路径查找
#   "<nameContains>"     名称包含匹配
#
# 全部名称来自 scripts/explore_ui.py 对真机的实际枚举（logs/ui_inventory/），
# 禁止凭源码猜测新增；界面改版后重新枚举同步。
_ROOM = ('UIRoot/RootCanvas/__dynamicRoot/Layer_Common/'
         'ViewRoot<Game.SDCMainView>/MainView/UILobby_SDCMainView/TeamRoom/SafeArea')
UI_CANDIDATES = {
    # 大厅 → 搜打撤入口（真机确认）
    'lobby_sdc_entry': [
        '@path:UIRoot/RootCanvas/__dynamicRoot/Layer_Common/'
        'ViewRoot<Game.UIMainCity2DView>/MainView/UIMainCity2D/SafeArea/'
        'MainCityNew/ControlPanel/Content_Banner/obj_LeftList/Obj_SDC/Root/SDCEnter_Button',
        'SDCEnter_Button',
    ],
    # 房间主界面（根节点 ViewRoot<Game.SDCMainView>）
    'room_main_view': ['SDCMainView'],
    # 房间功能入口（sdc_room.json 枚举，内层才是 WButton）
    'room_btn_prewar': [f'@path:{_ROOM}/BtnPreBattle', 'BtnPreBattle'],
    'room_btn_season': [f'@path:{_ROOM}/Obj_BtnList/Btn_NodeSeason/BtnNodeSeason', 'BtnNodeSeason'],
    'room_btn_store': [f'@path:{_ROOM}/Obj_BtnList/BtnStore/BtnStore', 'BtnStore'],
    'room_btn_collect': [f'@path:{_ROOM}/Obj_BtnList/BtnCollect/BtnCollect', 'BtnCollect'],
    'room_btn_task': [f'@path:{_ROOM}/Obj_BtnList/BtnTask/BtnTask', 'BtnTask'],
    'room_btn_start': [f'@path:{_ROOM}/RightBottom/ButtonRoot/ImgStart/BtnStart', 'BtnStart'],
    'room_btn_choose_play': [f'@path:{_ROOM}/RightBottom/ModeInfo/BtnChoosePlay', 'BtnChoosePlay'],
    'room_toggle_fill_teammates': [f'@path:{_ROOM}/Obj_Convene/Button_Convene', 'Button_Convene'],
    # 战备窗口（sdc_prewar.json 枚举 + 绑定清单）
    'prewar_window': ['SDCPreWarWindow'],
    'prewar_buy': ['@path:UIRoot/RootCanvas/__dynamicRoot/Layer_Common/'
                   'ViewRoot<Game.SDCPreWarWindow>/MainView/SDCPreWarWindow/SafeArea/'
                   'Right/Button_Buy', 'Button_Buy'],
    'prewar_sell': ['Button_Sell'],
    'prewar_tabs': ['ButtonFunc'],
    'prewar_warehouse_area': ['WarehouseScrollView'],
    # 战备商店（绑定清单 SDCPreWarShopWindow，自带返回键）
    'prewar_shop_window': ['SDCPreWarShopWindow'],
    'prewar_shop_back': ['BtnBack2'],
    # 战备装配二级操作（绑定清单 SDCPreWarWindow_Left 等，供后续 P1 扩展引用）
    'prewar_one_key_put': ['BtnOneKeyPut'],
    'prewar_hero_head': ['BtnHero'],
    # 房间返回大厅按钮（sdc_room.json 枚举：HUD NodeLeft/NodeBack）
    'room_back_button': [
        f'@path:{_ROOM[:_ROOM.index("/TeamRoom")]}/HUD/UIHUD_1/SafeArea/'
        'NodeLeft/NodeBack/BG/BtnBack1',
        'BtnBack1',
    ],
}

# 季节窗/商店窗/基地/收藏窗口的实际视图根待枚举后补入：
#   先点入口再跑  python scripts/explore_ui.py --name <名字>
PENDING_ENUMERATION = ['season_window', 'store_window', 'base_window', 'collect_window']

# ---- 真机确认的关键路径常量（供检查器拼装精确路径） ----
_PREWAR_PREFIX = ('UIRoot/RootCanvas/__dynamicRoot/Layer_Common/'
                  'ViewRoot<Game.SDCPreWarWindow>/MainView/SDCPreWarWindow')
TIPS_ROOT = 'UIRoot/RootCanvas/__dynamicRoot/Layer_Common/ViewRoot<Game.SDCItemTips>'
TOAST_ROOT = 'UIRoot/RootCanvas/Layer_Top/ViewRoot<Game.UITxtTips>'

# 仓库格子按钮的精确路径模板（第 i 格，i 从 0 开始）
def warehouse_cell_path(index):
    return (f'{_PREWAR_PREFIX}/SafeArea/Right/WarehouseScrollView/'
            f'Viewport/Content/Obj_Item{index}/Btn_Click')

# TIPS 装备按钮 / 关闭按钮
TIPS_EQUIP_PATH = (f'{TIPS_ROOT}/MainView/SDCItemTips/Content/'
                   'ItemMid/GiftDescInfoContent/Button_Equip')
TIPS_CLOSE_PATH = f'{TIPS_ROOT}/MainView/SDCItemTips/BtnClose'
TIPS_SELL_BUTTON_PATH = f'{_PREWAR_PREFIX}/SafeArea/Right/Button_Sell'
TIPS_SELL_CANCEL_PATH = f'{_PREWAR_PREFIX}/SafeArea/Right/Button_Cancel'

# 文本节点命名约定（从绑定清单/真机观察归纳：Personal面板 wimg_ItemNum、
# 房间 Text_Convene、TIPS TxTips、按钮文案 ButtonText 等）
TEXT_KEYWORDS = ['Text', 'Txt', 'Num', 'Value', 'Count']

# Item.SubType → 装备分类（与 battle_room_items.SUBTYPE_LABELS 同源）
_SUBTYPE_LABELS = {1: '护甲', 2: '芯片', 3: '增幅器', 4: '藏品', 5: '药品',
                   6: '钥匙', 7: '背包', 8: '技能', 9: '套装券', 10: '钥匙链',
                   11: '安全箱'}

# TIPS 操作按钮路径（绑定清单 SDCItemTips_ItemMid 确认）
TIPS_PUTINBAG_PATH = (f'{TIPS_ROOT}/MainView/SDCItemTips/Content/'
                      'ItemMid/GiftDescInfoContent/Button_PutInBag')
TIPS_PUTINSAFETY_PATH = (f'{TIPS_ROOT}/MainView/SDCItemTips/Content/'
                         'ItemMid/GiftDescInfoContent/Button_PutInSafetyBox')
TIPS_SHOP_BUY_PATH = (f'{TIPS_ROOT}/MainView/SDCItemTips/Content/'
                      'ItemMid/GiftDescInfoContent/Button_Buy')
TIPS_UNINSTALL_PATH = (f'{TIPS_ROOT}/MainView/SDCItemTips/Content/'
                       'ItemMid/GiftDescInfoContent/Button_UnInstall')
TIPS_PUTINWAREHOUSE_PATH = (f'{TIPS_ROOT}/MainView/SDCItemTips/Content/'
                            'ItemMid/GiftDescInfoContent/Button_PutInWarehouse')

# ---- GM 发道具（真机枚举 GMOutBattleView 子树确认） ----
GM_ROOT = 'UIRoot/RootCanvas/__dynamicRoot/Layer_Top/ViewRoot<Game.GMOutBattleView>'
GM_SWITCH_PATH = f'{GM_ROOT}/MainView/UIOutBattleGM/SafeArea/GMSwitch'
GM_INPUT_PATH = f'{GM_ROOT}/MainView/UIOutBattleGM/SafeArea/BtnBG/InputField'
GM_SEND_PATH = f'{GM_ROOT}/MainView/UIOutBattleGM/SafeArea/BtnBG/Send'


class UiContext:
    """
    封装一次冒烟运行中的 UI 查找/点击/等待，缓存已解析的路径。

    只缓存解析成功的逻辑名；未命中的候选每次重查（界面可能延迟出现）。
    """

    def __init__(self, conn, logger, load_timeout=10.0, poll_interval=0.5, close_settle=1.0):
        self.conn = conn
        self.logger = logger
        self.load_timeout = load_timeout
        self.poll_interval = poll_interval
        self.close_settle = close_settle
        self._resolved = {}          # logical -> item(dict)
        self.ui_snapshot = []        # 发现模式的 UI 快照（写进报告）
        self.sweep_supported = True  # 运行时错误清扫是否可用

    # ---------- 基础查找 ----------

    @staticmethod
    def _pick(items):
        """从 find_ui 结果中挑选最可信的一个：激活 > 带按钮 > 名称含 Btn"""
        if not items:
            return None
        def score(it):
            return (
                1 if it.get('activeInHierarchy') else 0,
                1 if it.get('hasButton') else 0,
                1 if 'Btn' in str(it.get('name', '')) else 0,
            )
        return max(items, key=score)

    def _query(self, cand, max_results=10):
        # "@path:" 前缀表示按完整路径精确查找
        if cand.startswith('@path:'):
            resp = self.conn.find_ui(path=cand[len('@path:'):])
        else:
            resp = self.conn.find_ui(name_contains=cand, max_results=max_results)
        if not resp.get('success'):
            return []
        return [it for it in resp.get('items', []) if it.get('name')]

    def find(self, logical, use_cache=True):
        """
        解析逻辑名到具体 UI item

        Args:
            use_cache: True 时命中已解析项直接返回缓存快照。
                注意: 缓存是"某次查询的静态快照",激活态可能已过期。
        Returns:
            dict 或 None: {'name','path','hasButton',...}
        """
        if use_cache and logical in self._resolved:
            return self._resolved[logical]
        candidates = UI_CANDIDATES.get(logical)
        if not candidates:
            return None
        best = None
        for cand in candidates:
            items = self._query(cand)
            if items:
                picked = self._pick(items)
                if picked is not None:
                    self.logger.debug(f"[UI] {logical} -> {picked.get('path')} (候选: {cand})")
                    best = picked
                    break
        if best is not None and use_cache:
            self._resolved[logical] = best
        return best

    def find_active(self, logical):
        """
        要求节点当前处于层级激活态(用于界面是否打开的判定)。

        刻意绕过缓存实时解析——缓存的激活态只是历史快照,
        界面开/关后旧值会失真(真机事故教训)。
        """
        item = self.find(logical, use_cache=False)
        if item is None:
            return None
        return item if item.get('activeInHierarchy') else None

    # ---------- 导航 ----------

    def click(self, logical):
        """点击逻辑名对应的按钮，返回 (成功, 说明)"""
        item = self.find(logical)
        if item is None:
            cands = UI_CANDIDATES.get(logical, [])
            return False, f"未找到UI[{logical}]，已试候选: {cands}"
        resp = self.conn.click_ui(path=item.get('path'))
        if resp.get('status') != 'ok':
            return False, f"点击 {item.get('path')} 失败: {resp.get('message', '')}"
        return True, f"已点击 {item.get('path')}"

    def wait_view(self, logical, timeout=None):
        """
        等待界面出现（轮询候选名，界面打开前的节点可能不存在/未激活）

        Returns:
            dict 或 None: 出现的 item
        """
        deadline = time.time() + (timeout if timeout is not None else self.load_timeout)
        while time.time() < deadline:
            item = self.find_active(logical)
            if item is not None:
                return item
            time.sleep(self.poll_interval)
        return None

    def close_top_window(self):
        """
        关闭当前最上层界面：优先走游戏返回栈（等价系统返回），
        兼容没有关闭按钮的全屏窗口（如战备窗口）
        """
        try:
            resp = self.conn.go_back()
            ok = resp.get('status') == 'ok'
        except Exception:
            ok = False
        time.sleep(self.close_settle)
        return ok

    # ---- 通用弹窗跳过（奖励/恭喜获得类，用例外干扰） ----

    # 弹窗视图名模式与确认/关闭按钮文案（真机发现后可持续补充）
    POPUP_VIEW_KEYWORDS = ['Reward', 'Award', 'Gain', 'Receive', 'Drop']
    POPUP_CONFIRM_TEXTS = ('确定', '领取', '关闭', '继续', '知道了', '确认')
    POPUP_CLOSE_NAMES = ('BtnClose', 'BtnOk', 'wbtn_Close', 'Close')

    def dismiss_popups(self):
        """
        识别并跳过当前界面的奖励/恭喜获得类弹窗。

        Returns:
            list[str]: 本次跳过的弹窗描述（供报告记录提醒测试人员）
        """
        dismissed = []
        roots = self.active_view_roots()
        # 短路：无奖励类根视图时跳过昂贵的全量关键字扫描
        if not any(any(kw in n for kw in self.POPUP_VIEW_KEYWORDS)
                   for n in roots):
            return dismissed
        for name in roots:
            if not any(kw in name for kw in self.POPUP_VIEW_KEYWORDS):
                continue
            # 定位弹窗子树内的确认/关闭按钮
            r = self.conn.find_ui(name_contains='Btn', max_results=40)
            btns = [(it['path'], it) for it in r.get('items', [])
                    if it.get('activeInHierarchy') and it.get('hasButton')
                    and name.split('.')[-1].rstrip('>') in it['path']]
            texts = {tp: str(tx.get('text') or '')
                     for tp, tx in self._popup_texts().items()}
            target = None
            for bp, it in sorted(btns):
                own = str(it.get('text') or '')
                if any(k in own for k in self.POPUP_CONFIRM_TEXTS):
                    target = bp
                    break
                for tp, txt in texts.items():
                    if tp.startswith(bp) and any(k in txt for k in
                                                 self.POPUP_CONFIRM_TEXTS):
                        target = bp
                        break
                if target:
                    break
            if target:
                self.conn.click_ui(path=target)
                time.sleep(1.0)
                dismissed.append(f'{name}:已点确认/关闭按钮')
            else:
                if self.close_top_window():
                    dismissed.append(f'{name}:走返回栈关闭')
        return dismissed

    def _popup_texts(self):
        out = {}
        for kw in self.POPUP_VIEW_KEYWORDS:
            resp = self.conn.get_ui_info(name_contains=kw, max_results=120)
            for it in resp.get('items', []):
                if it.get('activeInHierarchy') and it.get('text'):
                    out[it['path']] = it
        return out

    def active_view_roots(self):
        """返回当前激活的视图根名列表（ViewRoot<Game.XXX>）"""
        resp = self.conn.find_ui(name_contains='ViewRoot', max_results=80)
        return [it.get('name', '') for it in resp.get('items', [])
                if it.get('activeInHierarchy')]

    def capture(self, name):
        """截取当前画面到报告截图目录, 返回相对文件名(失败返回 None)"""
        try:
            root = os.path.join(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))), 'logs', 'battle_room')
            shot_dir = os.path.join(root, 'screenshots')
            fname = f'{datetime.datetime.now():%Y%m%d_%H%M%S}_{name}'
            path = self.conn.screenshot(shot_dir, fname)
            return f'screenshots/{fname}.png' if path else None
        except Exception:
            return None

        # ---- GM 面板操作(全自动：走 Model 层显隐，无需 F9 也无绑定反噬) ----

    def _wait_active(self, path, want=True, timeout=4.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = self.conn.get_ui_info(path=path)
            items = resp.get('items', [])
            if bool(items and items[0].get('activeInHierarchy')) == want:
                return True
            time.sleep(self.poll_interval)
        return False

    def open_gm_panel(self):
        """通过 Model 层显示 GM 面板并确认输入框可见。返回 (bool, msg)"""
        if self._wait_active(GM_INPUT_PATH, want=True):
            return True, 'GM 输入框已可见'
        resp = self.conn.reveal_gm_panel(show=True)
        if resp.get('status') != 'ok':
            return False, f'调用 reveal 失败: {resp.get("message", "")}'
        try:
            data = json.loads(resp.get('message', '{}'))
            if not data.get('success'):
                return False, f'reveal 未生效: {resp.get("message", "")[:80]}'
        except (json.JSONDecodeError, TypeError):
            pass
        if self._wait_active(GM_INPUT_PATH, want=True):
            return True, 'GM 输入框已激活'
        return False, 'reveal 后输入框仍未激活'

    def close_gm_panel(self):
        """收起 GM 面板(Model 层)，不再使用开关点击以避免 toggle 歧义"""
        resp = self.conn.reveal_gm_panel(show=False)
        ok = resp.get('status') == 'ok'
        self._wait_active(GM_INPUT_PATH, want=False, timeout=2.0)
        return ok

    def gm_add_item(self, item_id, count=1):
        """
        通过 GM 面板发放道具：AddItem={id}={count}

        Returns:
            (bool, msg)
        """
        opened, msg = self.open_gm_panel()
        if not opened:
            return False, msg
        try:
            cmd = f'AddItem={item_id}={count}'
            resp = self.conn.set_ui_input(cmd, path=GM_INPUT_PATH)
            if resp.get('status') != 'ok':
                return False, f'写入 GM 指令失败: {resp.get("message", "")}'
            resp = self.conn.click_ui(path=GM_SEND_PATH)
            if resp.get('status') != 'ok':
                return False, f'点击发送失败: {resp.get("message", "")}'
            time.sleep(1.0)   # 等服务端下发背包刷新
            return True, f'已发送 {cmd}'
        finally:
            self.close_gm_panel()

    def in_room(self):
        """当前是否处于搜打撤房间主界面"""
        return self.find_active('room_main_view') is not None

    # 已知的可能拦截操作的覆盖视图（引导/回房间确认等）
    BLOCKER_VIEW_KEYWORDS = ['SystemGuideView', 'GuideMask']

    def blocking_overlays(self):
        """返回当前激活的疑似拦截视图名（用于失败诊断）"""
        found = []
        for kw in self.BLOCKER_VIEW_KEYWORDS:
            resp = self.conn.find_ui(name_contains=kw, max_results=5)
            for it in resp.get('items', []):
                if it.get('activeInHierarchy') and it.get('name') not in found:
                    found.append(it.get('name'))
        return found

    # ---------- 发现模式 ----------

    def snapshot_ui(self, max_results=300):
        """
        抓取当前界面的 UI 对象快照（用于补充候选名）

        插件 find_ui 不支持无选择器全量扫描，这里按多个宽泛关键字
        分批查询后合并去重，重点覆盖视图根与按钮。

        Returns:
            list[dict]: [{name, path, activeInHierarchy, hasButton, ...}]
        """
        collected = {}
        for kw in ('ViewRoot', 'Btn', 'Window', 'Popup', 'SDC'):
            try:
                resp = self.conn.find_ui(name_contains=kw, max_results=max_results)
            except Exception:
                continue
            for it in resp.get('items', []):
                name = it.get('name', '')
                if name:
                    collected[it.get('path', name)] = it
        self.ui_snapshot = [
            {
                'name': it.get('name', ''),
                'path': it.get('path', ''),
                'activeInHierarchy': bool(it.get('activeInHierarchy')),
                'hasButton': bool(it.get('hasButton')),
                'hasToggle': bool(it.get('hasToggle')),
                'interactable': bool(it.get('interactable')),
            }
            for it in collected.values()
        ]
        return self.ui_snapshot

    # ---------- 运行时错误清扫 ----------

    def clear_runtime_errors(self):
        """清空 Unity 侧运行时错误缓冲区（用例执行前的基线）"""
        if not self.sweep_supported:
            return
        data = self.conn.get_battle_state(include_errors=True, clear_errors=True)
        if not data:
            self.sweep_supported = False

    def collect_runtime_errors(self):
        """
        读取并清空运行时错误缓冲区

        Returns:
            list[str]: 错误列表（清扫不可用时返回 []）
        """
        if not self.sweep_supported:
            return []
        data = self.conn.get_battle_state(include_errors=True, clear_errors=True)
        if not data:
            self.sweep_supported = False
            return []
        errors = data.get('errors') or []
        return [str(e) for e in errors][:20]
