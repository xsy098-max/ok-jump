"""
Unity 工程连接 TCP 客户端

与 Unity Editor 的 com.unity-ai-custom TCP 服务器通信，
使用 NDJSON 协议发送命令并接收响应。
"""

import json
import socket
import threading
import time
import logging

logger = logging.getLogger(__name__)

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
