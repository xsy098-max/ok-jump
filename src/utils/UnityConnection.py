"""
Unity 工程连接 TCP 客户端

与 Unity Editor 的 com.unity-ai-custom TCP 服务器通信，
使用 NDJSON 协议发送命令并接收响应。
"""

import json
import socket
import threading
import time

from ok import Logger

# 必须用 ok-script 的 Logger:标准 logging.getLogger 的记录不会进入
# ok 层级的文件 handler,连接失败的异常详情会完全丢失
logger = Logger.get_logger(__name__)

# ESkillButton 映射（与 Unity 端一致）
SKILL_BUTTON_ATTACK = 100
SKILL_BUTTON_SKILL1 = 1
SKILL_BUTTON_SKILL2 = 2
SKILL_BUTTON_ULTIMATE = 3


class UnityConnection:
    """
    Unity 工程连接客户端

    通过 TCP 连接 Unity Editor 的 com.unity-ai-custom 服务器，
    使用 NDJSON 协议通信。
    """

    def __init__(self, host='127.0.0.1', port=9876, timeout=5.0):
        self._host = host
        self._port = port
        self._timeout = timeout
        self._sock = None
        self._lock = threading.Lock()
        self._command_id = 0
        self._connected = False

    def connect(self):
        """
        连接 Unity TCP 服务器

        Returns:
            bool: 连接成功返回 True
        """
        try:
            self.disconnect()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self._timeout)
            sock.connect((self._host, self._port))
            self._sock = sock
            self._connected = True
            logger.info(f"Unity 连接成功: {self._host}:{self._port}")
            return True
        except Exception as e:
            logger.warning(f"Unity 连接失败: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """断开连接"""
        self._connected = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def is_connected(self):
        """检查连接状态"""
        return self._connected and self._sock is not None

    def send_command(self, command, payload=None, timeout=None):
        """
        发送命令并等待响应

        Args:
            command: 命令名称
            payload: 命令参数（dict 或 None）
            timeout: 超时时间（秒）

        Returns:
            dict: 响应数据，包含 status 和 message
        """
        if not self.is_connected():
            if not self.connect():
                return {'status': 'error', 'message': '未连接'}

        with self._lock:
            try:
                self._command_id += 1
                cmd_id = str(self._command_id)

                payload_str = json.dumps(payload) if payload else '{}'
                msg = json.dumps({
                    'command': command,
                    'commandId': cmd_id,
                    'payload': payload_str
                }) + '\n'

                self._sock.sendall(msg.encode('utf-8'))

                # 读取响应（NDJSON，一行一个 JSON）
                self._sock.settimeout(timeout or self._timeout)
                buf = b''
                while True:
                    chunk = self._sock.recv(4096)
                    if not chunk:
                        self._connected = False
                        return {'status': 'error', 'message': '连接断开'}
                    buf += chunk
                    if b'\n' in buf:
                        line = buf[:buf.index(b'\n')].decode('utf-8')
                        try:
                            resp = json.loads(line)
                            if resp.get('commandId') == cmd_id or resp.get('type') == 'cmd_res':
                                return {
                                    'status': resp.get('status', 'unknown'),
                                    'message': resp.get('message', '')
                                }
                        except json.JSONDecodeError:
                            continue
                        # 不是我们的响应，继续读

                return {'status': 'error', 'message': '超时'}
            except socket.timeout:
                return {'status': 'error', 'message': '超时'}
            except ConnectionError:
                self._connected = False
                return {'status': 'error', 'message': '连接断开'}
            except Exception as e:
                self._connected = False
                return {'status': 'error', 'message': str(e)}

    def ping(self):
        """
        连接健康检查

        Returns:
            bool: 连接正常返回 True
        """
        resp = self.send_command('automation_ping')
        return resp.get('status') == 'ok'

    def get_all_actors(self):
        """
        获取所有 Actor 信息（含屏幕坐标）

        Returns:
            list[dict]: Actor 列表，每个包含 screenX, screenY, campType, actorType, isDead, isPlayer
        """
        resp = self.send_command('get_all_actors')
        if resp.get('status') != 'ok':
            return []
        try:
            data = json.loads(resp.get('message', '{}'))
            return data.get('actors', [])
        except (json.JSONDecodeError, TypeError):
            return []

    def get_player_info(self):
        """
        获取玩家自身信息（位置、技能CD等）

        Returns:
            dict: 玩家信息
        """
        resp = self.send_command('get_player_info')
        if resp.get('status') != 'ok':
            logger.debug(f"get_player_info 响应: {resp}")
            return {}
        try:
            return json.loads(resp.get('message', '{}'))
        except (json.JSONDecodeError, TypeError):
            return {}

    def use_skill(self, skill_button, direction=None, target_pos=None):
        """
        释放技能

        Args:
            skill_button: 技能按钮编号 (SKILL_BUTTON_ATTACK/SKILL1/SKILL2/ULTIMATE)
            direction: 方向（可选）
            target_pos: 目标位置（可选）

        Returns:
            dict: 响应
        """
        payload = {'skillButton': skill_button}
        return self.send_command('use_skill', payload)

    def set_move_dir(self, dx, dy, dist=100.0):
        """
        设置移动方向

        Args:
            dx: X 方向分量 (-1.0 ~ 1.0)
            dy: Y 方向分量 (-1.0 ~ 1.0)
            dist: 屏幕距离

        Returns:
            dict: 响应
        """
        payload = {'dx': dx, 'dy': dy, 'dist': dist}
        return self.send_command('set_move_dir', payload)

    def stop_move(self):
        """
        停止移动

        Returns:
            dict: 响应
        """
        return self.send_command('stop_move')

    # ==================== 登录自动化 ====================

    def get_login_state(self):
        """
        获取当前登录界面状态

        Returns:
            str: "BeforeLogin" | "AccountLogin" | "BeginGame" | "MainCity" | "Unknown"
        """
        resp = self.send_command('automation_get_login_state')
        if resp.get('status') != 'ok':
            return 'Unknown'
        try:
            data = json.loads(resp.get('message', '{}'))
            return data.get('state', 'Unknown')
        except (json.JSONDecodeError, TypeError):
            return 'Unknown'

    def set_account(self, account):
        """
        设置账号名

        Args:
            account: 账号字符串

        Returns:
            bool: 设置成功返回 True
        """
        payload = {'account': account}
        resp = self.send_command('automation_set_account', payload)
        return resp.get('status') == 'ok'

    def click_privacy(self):
        """
        点击隐私协议复选框

        Returns:
            bool: 操作成功返回 True
        """
        resp = self.send_command('automation_click_privacy')
        return resp.get('status') == 'ok'

    def click_enter_game(self):
        """
        点击"进入游戏"按钮（BeforeLogin 界面）

        Returns:
            bool: 操作成功返回 True
        """
        resp = self.send_command('automation_click_enter_game')
        return resp.get('status') == 'ok'

    def click_login(self):
        """
        点击"登录"按钮（AccountLogin 界面）

        Returns:
            bool: 操作成功返回 True
        """
        resp = self.send_command('automation_click_login')
        return resp.get('status') == 'ok'

    def click_start_game(self):
        """
        点击"开始游戏"按钮（BeginGame 界面）

        Returns:
            bool: 操作成功返回 True
        """
        resp = self.send_command('automation_click_start_game')
        return resp.get('status') == 'ok'

    def set_new_guide(self, enabled=True):
        """
        设置新手引导开关状态（BeginGame 界面）

        Args:
            enabled: True 启用新手引导，False 关闭

        Returns:
            bool: 操作成功返回 True
        """
        payload = {'enabled': enabled}
        resp = self.send_command('automation_set_new_guide', payload)
        return resp.get('status') == 'ok'

    def analyze_screen(self):
        """
        分析当前画面像素统计，检测白块/粉块/黑屏等渲染异常

        Returns:
            dict: {'white': float, 'pink': float, 'black': float} 百分比，
                  失败时返回 {'white': -1, 'pink': -1, 'black': -1}
        """
        empty = {'white': -1, 'pink': -1, 'black': -1}
        resp = self.send_command('automation_analyze_screen')
        if resp.get('status') != 'ok':
            return empty
        try:
            return json.loads(resp.get('message', '{}'))
        except (json.JSONDecodeError, TypeError):
            return empty

    # ==================== UI 自动化（战备房间等界面测试） ====================

    def screenshot(self, save_dir, name, timeout=12):
        """
        截取 Game View 画面保存为 PNG（供 AI 视觉复核与报告留证）

        Returns:
            str|None: 成功返回保存路径, 失败返回 None
        """
        resp = self.send_command('automation_screenshot',
                                 {'dir': save_dir, 'name': name},
                                 timeout=timeout)
        if resp.get('status') != 'ok':
            return None
        try:
            data = json.loads(resp.get('message', '{}'))
            return data.get('path') if data.get('success') else None
        except (json.JSONDecodeError, TypeError):
            return None

    def sdc_fill_teammate(self, on=None, timeout=10):
        """
        读取/写回搜打撤"补齐队友"状态（官方接口反射，队长权限）

        Args:
            on: None=只读；True/False=写回目标状态并回读

        Returns:
            dict: {'success':bool, 'on':bool, 'inRoom':bool} 或 error 响应
        """
        payload = {'on': -1 if on is None else (1 if on else 0)}
        resp = self.send_command('automation_sdc_fill_teammate', payload,
                                 timeout=timeout)
        if resp.get('status') != 'ok':
            return resp
        try:
            return json.loads(resp.get('message', '{}'))
        except (json.JSONDecodeError, TypeError):
            return resp

    def go_back(self):
        """
        触发游戏返回栈（等价玩家按系统返回键），可关闭全屏窗口

        Returns:
            dict: 原始响应，ok 且 success=true 表示已执行返回
        """
        return self.send_command('automation_go_back')

    def find_ui(self, path=None, name_contains=None, max_results=None):
        """
        查找 UI 对象（GameObject.Find + 全层级扫描，含未激活节点）

        Args:
            path: 精确路径（可选）
            name_contains: 名称包含的关键字（可选）
            max_results: 最多返回条数

        Returns:
            dict: {'success': bool, 'count': int, 'items': [...]}，
                  item 含 name/path/activeSelf/activeInHierarchy/hasButton/hasToggle/interactable 等
        """
        payload = {}
        if path:
            payload['path'] = path
        if name_contains:
            payload['nameContains'] = name_contains
        if max_results:
            payload['maxResults'] = max_results
        resp = self.send_command('automation_find_ui', payload)
        if resp.get('status') != 'ok':
            return {'success': False, 'count': 0, 'items': []}
        try:
            data = json.loads(resp.get('message', '{}'))
            return {
                'success': bool(data.get('success')),
                'count': int(data.get('count', 0)),
                'items': data.get('items', []),
            }
        except (json.JSONDecodeError, TypeError, ValueError):
            return {'success': False, 'count': 0, 'items': []}

    def click_ui(self, path=None, name_contains=None):
        """
        点击 UI 按钮（Button.onClick.Invoke，回退 ExecuteEvents.pointerClick）

        Args:
            path: 精确路径（可选）
            name_contains: 名称包含的关键字（可选）

        Returns:
            dict: 原始响应，ok 时 message 含 {success, clickedBy, target}
        """
        payload = {}
        if path:
            payload['path'] = path
        if name_contains:
            payload['nameContains'] = name_contains
        return self.send_command('automation_click_ui', payload)

    def set_ui_toggle(self, is_on, path=None, name_contains=None):
        """
        设置 Toggle 开关状态

        Args:
            is_on: 目标状态
            path: 精确路径（可选）
            name_contains: 名称包含的关键字（可选）

        Returns:
            dict: 原始响应
        """
        payload = {'isOn': bool(is_on)}
        if path:
            payload['path'] = path
        if name_contains:
            payload['nameContains'] = name_contains
        return self.send_command('automation_set_ui_toggle', payload)

    def set_ui_input(self, text, path=None, name_contains=None):
        """
        设置 InputField 文本

        Args:
            text: 目标文本
            path: 精确路径（可选）
            name_contains: 名称包含的关键字（可选）

        Returns:
            dict: 原始响应
        """
        payload = {'text': text}
        if path:
            payload['path'] = path
        if name_contains:
            payload['nameContains'] = name_contains
        return self.send_command('automation_set_ui_input', payload)

    def get_ui_info(self, path=None, name_contains=None, max_results=None):
        """
        读取 UI 节点的文本/颜色/Toggle 状态

        Args:
            path: 精确路径（可选，单节点）
            name_contains: 名称包含的关键字（可选）
            max_results: 最多返回条数

        Returns:
            dict: {'success': bool, 'count': int, 'items': [...]}，
                  item 在 find_ui 基础上附加 text/color([r,g,b,a] 0~255)/isOn
        """
        payload = {}
        if path:
            payload['path'] = path
        if name_contains:
            payload['nameContains'] = name_contains
        if max_results:
            payload['maxResults'] = max_results
        resp = self.send_command('automation_get_ui_info', payload)
        if resp.get('status') != 'ok':
            return {'success': False, 'count': 0, 'items': []}
        try:
            data = json.loads(resp.get('message', '{}'))
            return {
                'success': bool(data.get('success')),
                'count': int(data.get('count', 0)),
                'items': data.get('items', []),
            }
        except (json.JSONDecodeError, TypeError, ValueError):
            return {'success': False, 'count': 0, 'items': []}

    def reveal_gm_panel(self, show=True):
        """
        显示/收起 GM 面板（操作 GMModel 数据绑定层）

        GMSwitch 等节点的显隐由 Model 绑定驱动，外部 SetActive 会被
        绑定复位；本命令等价于玩家按 F9 并点击"开启指令"（或反向收起）。

        Returns:
            dict: 原始响应，ok 且 success=true 表示已生效
        """
        return self.send_command('automation_reveal_gm_panel', {'show': bool(show)})

    def set_ui_active(self, is_active, path=None, name_contains=None):
        """
        直接设置 UI 节点激活状态(SetActive)。

        用于替代人工按键呼出类入口(如 GM 面板的 F9 →"开启指令")，
        全自动化流程中不需要真实键盘输入。

        Returns:
            dict: 原始响应，ok 时 message 含 {success,name,previous,active}
        """
        payload = {'isActive': bool(is_active)}
        if path:
            payload['path'] = path
        if name_contains:
            payload['nameContains'] = name_contains
        return self.send_command('automation_set_ui_active', payload)

    def get_battle_state(self, include_errors=False, clear_errors=False):
        """
        获取战斗状态快照（含运行时错误环形缓冲区）

        Args:
            include_errors: 返回期间捕获的运行时错误
            clear_errors: 读取后清空错误缓冲区

        Returns:
            dict: 状态快照，失败时返回 {}
        """
        payload = {'includeErrors': bool(include_errors), 'clearErrors': bool(clear_errors)}
        resp = self.send_command('automation_get_battle_state', payload)
        if resp.get('status') != 'ok':
            return {}
        try:
            return json.loads(resp.get('message', '{}'))
        except (json.JSONDecodeError, TypeError):
            return {}

    # ==================== 自动战斗（游戏内置 AI） ====================

    def start_auto_battle(self):
        """
        激活游戏内置 AI 接管玩家英雄战斗

        Returns:
            dict: 响应
        """
        return self.send_command('automation_start_auto_battle')

    def stop_auto_battle(self):
        """
        关闭游戏内置 AI，交还控制权

        Returns:
            dict: 响应
        """
        return self.send_command('automation_stop_auto_battle')
