"""
Unity 工程连接专用自动战斗触发任务

两种模式：
1. 游戏内置 AI（默认）：通过 GM 命令激活游戏自身的 AI 行为树，
   与电脑 AI 完全相同的战斗逻辑。
2. 外部 AI 引擎：分数效用评估决策机制，
   通过 TCP 命令读取数据并驱动操作。
"""

import json
import time

from ok import og
from ok import TriggerTask


class AutoCombatTaskUnity(TriggerTask):
    """
    Unity 工程连接专用自动战斗任务

    默认使用游戏内置 AI（通过 GM 命令），可选切换为外部 AI 引擎。
    """

    def __init__(self, *args, **kwargs):
        TriggerTask.__init__(self, *args, **kwargs)
        self.name = "AutoCombatTaskUnity"
        self.description = "Unity 工程连接 - AI 自动战斗"

        self.default_config = {
            '使用游戏内置AI': True,
            '自动普攻': True,
            '自动技能1': True,
            '自动技能2': True,
            '自动大招': True,
            '低血撤退阈值(%)': 30,
            '详细日志': False,
        }

        self.config_description = {
            '使用游戏内置AI': '激活游戏自身的 AI 行为树接管战斗（推荐）',
            '自动普攻': '自动释放普通攻击（外部 AI 模式）',
            '自动技能1': '自动释放技能1（外部 AI 模式）',
            '自动技能2': '自动释放技能2（外部 AI 模式）',
            '自动大招': '自动释放终极技能（外部 AI 模式）',
            '低血撤退阈值(%)': 'HP 低于此值时触发保护/撤退行为（外部 AI 模式）',
            '详细日志': '输出 AI 决策详细日志',
        }

    def enable(self):
        try:
            super().enable()
        except (AttributeError, TypeError):
            try:
                self._enabled = True
            except Exception:
                pass

    def disable(self):
        try:
            super().disable()
        except (AttributeError, TypeError):
            try:
                self._enabled = False
            except Exception:
                pass

    def should_trigger(self):
        """通过 TCP ping 检查是否在战斗中"""
        conn = self._get_unity_connection()
        if conn is None:
            return False
        resp = conn.send_command('automation_ping')
        if resp.get('status') != 'ok':
            return False
        try:
            data = json.loads(resp.get('message', '{}'))
            return data.get('inBattle', False)
        except (json.JSONDecodeError, TypeError):
            return False

    def run(self):
        conn = self._get_unity_connection()
        if conn is None:
            self.logger.error("Unity 连接不可用，无法执行战斗任务")
            return False

        use_builtin = self.config.get('使用游戏内置AI', True)

        self.logger.info("=" * 50)
        self.logger.info(f"Unity AI 自动战斗启动 (模式: {'游戏内置' if use_builtin else '外部引擎'})")
        self.logger.info("=" * 50)

        try:
            if use_builtin:
                self._run_builtin_ai(conn)
            else:
                self._run_external_ai(conn)
        except Exception as e:
            self.logger.error(f"战斗异常: {e}")
        finally:
            self.logger.info("Unity AI 自动战斗结束")

        return True

    # ==================== 模式一：游戏内置 AI ====================

    def _run_builtin_ai(self, conn):
        """通过 GM 命令激活游戏内置 AI，等待战斗结束"""
        resp = conn.start_auto_battle()
        if resp.get('status') != 'ok':
            self.logger.error(f"启动游戏内置 AI 失败: {resp.get('message', '')}")
            return

        msg = resp.get('message', '')
        self.logger.info(f"游戏内置 AI 响应: {msg}")

        self.logger.info("游戏内置 AI 已接管战斗")
        try:
            while not self._should_exit():
                resp = conn.send_command('automation_ping')
                try:
                    data = json.loads(resp.get('message', '{}'))
                    if not data.get('inBattle', False):
                        self.logger.info("战斗已结束")
                        break
                except (json.JSONDecodeError, TypeError):
                    pass
                time.sleep(1.0)
        finally:
            conn.stop_auto_battle()

    # ==================== 模式二：外部 AI 引擎 ====================

    def _run_external_ai(self, conn):
        """通过外部 AI 引擎驱动战斗操作"""
        from src.combat.ai_brain import AIBrain

        verbose = self.config.get('详细日志', False)
        ai = AIBrain(conn, self.config, verbose=verbose)

        try:
            tick_count = 0
            while not self._should_exit():
                actors = conn.get_all_actors()
                player_info = conn.get_player_info()

                if tick_count % 100 == 0 or tick_count < 3:
                    has_player = any(a.get('isPlayer') for a in actors)
                    self.logger.info(f"战斗数据: actors={len(actors)}, player_found={player_info.get('found', False)}, has_isPlayer={has_player}")
                tick_count += 1

                if player_info and player_info.get('isDead'):
                    if verbose:
                        self.logger.debug("玩家已死亡，等待复活...")
                    time.sleep(0.5)
                    continue

                # player_info 恢复：从 actors 列表找回自己
                if not player_info or not player_info.get('found'):
                    self_actor = next((a for a in actors if a.get('isPlayer')), None)
                    if self_actor and not self_actor.get('isDead'):
                        player_info = {
                            'found': True,
                            'screenX': self_actor.get('screenX', 0),
                            'screenY': self_actor.get('screenY', 0),
                            'isDead': False,
                            'campType': self_actor.get('campType', 0),
                            'skills': {},
                        }
                    else:
                        if not actors:
                            ping_resp = conn.send_command('automation_ping')
                            try:
                                ping_data = json.loads(ping_resp.get('message', '{}'))
                                if not ping_data.get('inBattle', False):
                                    self.logger.info("战斗已结束")
                                    break
                            except (json.JSONDecodeError, TypeError):
                                pass
                        time.sleep(0.2)
                        continue

                ai.tick(actors, player_info)
                time.sleep(0.05)

        finally:
            ai.cleanup()

    # ==================== 工具方法 ====================

    def _should_exit(self):
        try:
            if og and hasattr(og, 'executor') and og.executor.exit_event.is_set():
                return True
        except Exception:
            pass
        return False

    def _get_unity_connection(self):
        try:
            if og and hasattr(og, 'my_app') and hasattr(og.my_app, '_unity_connection'):
                conn = og.my_app._unity_connection
                if conn and conn.is_connected():
                    return conn
        except Exception:
            pass
        return None
