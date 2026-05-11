"""
Unity 工程连接专用登录任务

通过 TCP 命令驱动 Unity 端的 UI 操作完成自动登录，
不需要截图/OCR/模板匹配，纯组件模式。

登录流程状态机：
  BeforeLogin → 勾选隐私协议 → 点击"进入游戏"
  AccountLogin → 输入账号 → 点击"登录"
  BeginGame → 设置新手教程开关 → 勾选隐私协议 → 点击"开始游戏"
  CharacterSelection / MainCity → 登录完成
"""

import time

from ok import og

from src.task.mixins import JumpTaskMixin
from ok import BaseTask

# 登录状态的预期顺序（用于检测回退）
_STATE_ORDER = {
    'BeforeLogin': 0,
    'AccountLogin': 1,
    'BeginGame': 2,
    'CharacterSelection': 3,
    'MainCity': 3,
}

_MAX_STATE_RETRIES = 5
_MAX_TCP_FAILURES = 3
_MAX_UNKNOWN_SECONDS = 30

# 画面异常阈值（百分比）
_WHITE_THRESHOLD = 80.0   # 白色像素占比超过此值视为白屏
_PINK_THRESHOLD = 5.0     # 粉色像素占比超过此值视为材质缺失
_BLACK_THRESHOLD = 90.0   # 黑色像素占比超过此值视为黑屏


class AutoLoginTaskUnity(BaseTask, JumpTaskMixin):
    """
    Unity 工程连接专用登录任务

    通过 Unity TCP 命令 (GameObject.Find + Button.onClick.Invoke)
    自动完成登录流程，直到进入游戏主城或角色选择界面。
    """

    def __init__(self, *args, **kwargs):
        BaseTask.__init__(self, *args, **kwargs)
        JumpTaskMixin._init_mixin_vars(self)
        self.name = "AutoLoginTask-Unity"
        self.description = "Unity 工程连接 - 自动登录测试"

        self.default_config = {
            '账号': '',
            '勾选新手教程': True,
            '步骤间隔(秒)': 2,
            '最大等待(秒)': 120,
        }

        self.config_description = {
            '账号': '登录账号名称',
            '勾选新手教程': '开始游戏前勾选新手引导开关',
            '步骤间隔(秒)': '登录流程每步之间的等待时间',
            '最大等待(秒)': '登录超时时间',
        }

    def run(self):
        """
        执行 Unity 模式自动登录

        通过 TCP 命令循环检测当前登录界面状态并执行对应操作，
        直到检测到主城/角色选择界面（登录完成）或超时。
        """
        conn = self._get_unity_connection()
        if conn is None:
            self.logger.error("Unity 连接不可用，无法执行登录任务")
            return False

        account = self.config.get('账号', '')
        step_interval = self.config.get('步骤间隔(秒)', 2)
        max_wait = self.config.get('最大等待(秒)', 120)

        self.logger.info("=" * 50)
        self.logger.info("Unity 自动登录任务启动")
        self.logger.info(f"账号: {account or '(未设置)'}")
        self.logger.info("=" * 50)

        start_time = time.time()
        last_state = None
        state_retry_count = 0
        tcp_fail_count = 0
        unknown_seconds = 0

        while time.time() - start_time < max_wait:
            # 获取当前登录界面状态
            state = conn.get_login_state()

            # TCP 连接健康检查：如果状态查询后连接已断开，视为 TCP 失败
            if not conn.is_connected():
                tcp_fail_count += 1
                self.logger.error(f"TCP 连接中断 (连续第 {tcp_fail_count} 次)")
                if tcp_fail_count >= _MAX_TCP_FAILURES:
                    self.logger.error(f"Unity 连接丢失，连续 {_MAX_TCP_FAILURES} 次 TCP 中断")
                    return False
                time.sleep(2)
                continue
            else:
                tcp_fail_count = 0

            # 状态变化检测
            if state != last_state:
                # 状态回退检测
                if (state in _STATE_ORDER and last_state in _STATE_ORDER
                        and _STATE_ORDER[state] < _STATE_ORDER[last_state]):
                    self.logger.warning(f"状态回退: {last_state} → {state}")
                self.logger.info(f"登录状态: {last_state or '起始'} → {state}")
                last_state = state
                state_retry_count = 0
                unknown_seconds = 0

                # 状态切换时检测画面渲染异常
                if state not in ("Unknown", "MainCity"):
                    self._check_screen_anomaly(conn, state)
            else:
                state_retry_count += 1

            # === 各状态处理 ===

            if state == "BeforeLogin":
                if state_retry_count >= _MAX_STATE_RETRIES:
                    self.logger.error(f"BeforeLogin 连续 {_MAX_STATE_RETRIES} 次无进展，隐私协议或进入按钮可能失效")
                    return False

                self._exec(conn, 'automation_click_privacy', log_level='warning')
                time.sleep(0.5)

                self._exec(conn, 'automation_click_enter_game')
                time.sleep(step_interval)

            elif state == "AccountLogin":
                if not account:
                    self.logger.error("到达账号登录界面但未配置账号，任务终止")
                    return False

                if state_retry_count >= _MAX_STATE_RETRIES:
                    self.logger.error(f"AccountLogin 连续 {_MAX_STATE_RETRIES} 次无进展，登录按钮可能失效或账号错误")
                    return False

                self._exec(conn, 'automation_set_account', {'account': account})
                time.sleep(0.5)

                self._exec(conn, 'automation_click_login')
                time.sleep(step_interval)

            elif state == "BeginGame":
                if state_retry_count >= _MAX_STATE_RETRIES:
                    self.logger.error(f"BeginGame 连续 {_MAX_STATE_RETRIES} 次无进展，开始按钮可能失效")
                    return False

                enable_tutorial = self.config.get('勾选新手教程', True)
                self._exec(conn, 'automation_set_new_guide', {'enabled': enable_tutorial}, log_level='warning')
                time.sleep(0.3)

                self._exec(conn, 'automation_click_privacy', log_level='warning')
                time.sleep(0.5)

                self._exec(conn, 'automation_click_start_game')
                time.sleep(step_interval)

            elif state == "MainCity":
                self.logger.info("=" * 50)
                self.logger.info("Unity 自动登录完成！已进入主城")
                self.logger.info(f"耗时: {time.time() - start_time:.1f} 秒")
                self.logger.info("=" * 50)
                return True

            elif state == "CharacterSelection":
                self.logger.info("=" * 50)
                self.logger.info("Unity 自动登录完成！已到达角色选择界面")
                self.logger.info(f"耗时: {time.time() - start_time:.1f} 秒")
                self.logger.info("=" * 50)
                return True

            else:
                # Unknown 状态
                unknown_seconds += 1
                if unknown_seconds == 15:
                    self.logger.warning("Unknown 状态已持续 15 秒，游戏可能在加载中")
                if unknown_seconds >= _MAX_UNKNOWN_SECONDS:
                    self.logger.error(f"Unknown 状态持续 {_MAX_UNKNOWN_SECONDS} 秒，界面可能崩溃或卡死")
                    return False
                time.sleep(1)

        elapsed = time.time() - start_time
        self.logger.error(f"Unity 自动登录超时 ({max_wait}秒，实际 {elapsed:.1f} 秒)，最后状态: {last_state}")
        return False

    def _get_unity_connection(self):
        """获取 Unity 连接实例"""
        try:
            if og and hasattr(og, 'my_app') and hasattr(og.my_app, '_unity_connection'):
                conn = og.my_app._unity_connection
                if conn and conn.is_connected():
                    return conn
        except Exception:
            pass
        return None

    def _exec(self, conn, command, payload=None, log_level='error'):
        """
        执行 TCP 命令并检查结果，失败时记录 Unity 返回的详细错误。

        Returns:
            bool: 成功返回 True
        """
        resp = conn.send_command(command, payload)
        if resp.get('status') == 'ok':
            return True
        msg = resp.get('message', '未知错误')
        logger_fn = self.logger.error if log_level == 'error' else self.logger.warning
        logger_fn(f"[{command}] 失败: {msg}")
        return False

    def _check_screen_anomaly(self, conn, state):
        """
        检测当前画面是否存在渲染异常（白屏/粉块/黑屏）。

        以 320x180 低分辨率分析画面像素分布，
        不需要参考图片，仅检测通用异常特征。
        """
        stats = conn.analyze_screen()
        if stats.get('white', -1) < 0:
            return

        white = stats['white']
        pink = stats['pink']
        black = stats['black']
        self.logger.info(f"[{state}] 画面分析: 白={white:.1f}% 粉={pink:.1f}% 黑={black:.1f}%")

        errors = []
        if white > _WHITE_THRESHOLD:
            errors.append(f"白色占比 {white:.1f}% (>{_WHITE_THRESHOLD}%)，疑似白屏或资源未加载")
        if pink > _PINK_THRESHOLD:
            errors.append(f"粉色占比 {pink:.1f}% (>{_PINK_THRESHOLD}%)，疑似材质/Shader 缺失")
        if black > _BLACK_THRESHOLD:
            errors.append(f"黑色占比 {black:.1f}% (>{_BLACK_THRESHOLD}%)，疑似黑屏或渲染失败")

        if errors:
            for err in errors:
                self.logger.error(f"[{state}] 画面异常: {err}")
