"""
Unity 工程连接专用登录任务

通过 TCP 命令驱动 Unity 端的 UI 操作完成自动登录，
不需要截图/OCR/模板匹配，纯组件模式。

登录流程状态机：
  BeforeLogin → 勾选隐私协议 → 点击"进入游戏"
  AccountLogin → 输入账号 → 点击"登录"
  BeginGame → 勾选隐私协议 → 点击"开始游戏"
  MainCity → 登录完成
"""

import time

from ok import og

from src.task.mixins import JumpTaskMixin
from ok import BaseTask


class AutoLoginTaskUnity(BaseTask, JumpTaskMixin):
    """
    Unity 工程连接专用登录任务

    通过 Unity TCP 命令 (GameObject.Find + Button.onClick.Invoke)
    自动完成登录流程，直到进入游戏主城。
    """

    def __init__(self, *args, **kwargs):
        BaseTask.__init__(self, *args, **kwargs)
        JumpTaskMixin._init_mixin_vars(self)
        self.name = "AutoLoginTask-Unity"
        self.description = "Unity 工程连接 - 自动登录测试"

    @property
    def default_config(self):
        return {
            '账号': '',
            '步骤间隔(秒)': 2,
            '最大等待(秒)': 120,
        }

    def run(self):
        """
        执行 Unity 模式自动登录

        通过 TCP 命令循环检测当前登录界面状态并执行对应操作，
        直到检测到主城界面（登录完成）或超时。
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

        while time.time() - start_time < max_wait:
            # 获取当前登录界面状态
            state = conn.get_login_state()

            # 状态变化时记录日志
            if state != last_state:
                self.logger.info(f"登录状态: {last_state or '起始'} → {state}")
                last_state = state

            if state == "BeforeLogin":
                # 隐私协议界面：勾选协议 → 点击进入游戏
                conn.click_privacy()
                time.sleep(0.5)
                conn.click_enter_game()
                time.sleep(step_interval)

            elif state == "AccountLogin":
                # 账号登录界面：输入账号 → 点击登录
                if account:
                    conn.set_account(account)
                    time.sleep(0.5)
                conn.click_login()
                time.sleep(step_interval)

            elif state == "BeginGame":
                # 开始游戏界面：勾选协议 → 点击开始游戏
                conn.click_privacy()
                time.sleep(0.5)
                conn.click_start_game()
                time.sleep(step_interval)

            elif state == "MainCity":
                # 已进入主城，登录完成
                self.logger.info("=" * 50)
                self.logger.info("Unity 自动登录完成！已进入主城")
                self.logger.info("=" * 50)
                return True

            else:
                # Unknown 状态，可能是加载中，等待重试
                time.sleep(1)

        self.logger.error(f"Unity 自动登录超时 ({max_wait}秒)，最后状态: {last_state}")
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
