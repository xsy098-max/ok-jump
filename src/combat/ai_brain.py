"""
分数效用评估 AI 引擎

复刻游戏内置 AIGraph 的决策机制：
  每 tick：清除分数 → 运行评估器 → RefreshMax(选最高分) → 执行对应动作

对应游戏代码：
  - AI_FrameUpdate:  tick 驱动
  - AI_Score:        SetScore / AddScore / CleanScore / RefreshMax
  - AI_Com_Evaluate: 各评估子树
  - AI_Com_Action:   各执行子树
  - AI_FastSearchActor: 目标搜索
"""

import math
import logging
from src.utils.UnityConnection import (
    SKILL_BUTTON_ATTACK, SKILL_BUTTON_SKILL1,
    SKILL_BUTTON_SKILL2, SKILL_BUTTON_ULTIMATE,
)

logger = logging.getLogger(__name__)

# 技能范围（像素），与 DistanceCalculator 一致
SKILL_RANGE = 225

# ===== EAIActionType（对应游戏 Actor.AIGraph.cs）=====
ACTION_ATK_HERO = 2
ACTION_PROTECT_SELF = 3
ACTION_PROTECT_FRIEND = 4
ACTION_RUN_AWAY = 5
ACTION_SKILL_ATTACK = 10001
ACTION_SKILL_1 = 10002
ACTION_SKILL_2 = 10003
ACTION_ULTIMATE = 10004

ACTION_NAMES = {
    ACTION_ATK_HERO: "攻击英雄",
    ACTION_PROTECT_SELF: "保护自己",
    ACTION_PROTECT_FRIEND: "保护队友",
    ACTION_RUN_AWAY: "逃跑",
    ACTION_SKILL_ATTACK: "普攻",
    ACTION_SKILL_1: "技能1",
    ACTION_SKILL_2: "技能2",
    ACTION_ULTIMATE: "大招",
}


def _distance(a, b):
    """计算两个 actor 之间的屏幕像素距离"""
    dx = a['screenX'] - b['screenX']
    dy = a['screenY'] - b['screenY']
    return math.sqrt(dx * dx + dy * dy)


def _hp_percent(actor):
    """计算 HP 百分比 (0.0 ~ 1.0)"""
    max_hp = actor.get('maxHp', 0)
    if max_hp <= 0:
        return 1.0
    return actor.get('hp', 0) / max_hp


class AIBrain:
    """
    分数效用评估 AI 引擎

    复刻游戏 AIGraph 的 CleanScore → Evaluate → RefreshMax → DoAction 循环。
    """

    def __init__(self, conn, config=None, verbose=False):
        self._conn = conn
        self._config = config or {}
        self._verbose = verbose
        self._scores = {}
        self._last_action = None
        self._locked_target = None
        self._locked_target_lost = 0

    def tick(self, actors, player_info):
        """
        执行一次 AI 决策循环。

        Args:
            actors: get_all_actors() 返回的 actor 列表
            player_info: get_player_info() 返回的玩家信息
        """
        if not player_info or not player_info.get('found'):
            return

        # 分类 actor
        player_camp = player_info.get('campType', 0)
        self_actor = self._find_self(actors, player_info)
        if self_actor is None:
            return

        enemies = [a for a in actors
                    if not a.get('isDead') and a.get('campType') != player_camp]
        allies = [a for a in actors
                   if not a.get('isDead') and a.get('campType') == player_camp
                   and not a.get('isPlayer')]

        # === CleanScore ===
        self._scores.clear()

        # === EvaluateTrees ===
        self._evaluate_attack_hero(self_actor, enemies)
        self._evaluate_skills(self_actor, enemies, player_info)
        self._evaluate_protect_self(self_actor, enemies)
        self._evaluate_protect_friend(self_actor, allies)
        self._evaluate_run_away(self_actor, enemies)

        # === RefreshMax ===
        action, score = self._refresh_max()
        if action is None:
            return

        # === DoAction ===
        if action != self._last_action:
            if self._verbose:
                logger.debug(f"AI 决策: {ACTION_NAMES.get(action, action)} (分数:{score:.0f})")
            self._last_action = action

        self._execute_action(action, self_actor, enemies, allies, player_info)

    # ==================== EvaluateTrees ====================

    def _evaluate_attack_hero(self, self_actor, enemies):
        """对应 AI_Com_Hero_Evaluate_AtkHero — 低优先级，仅作为"移动靠近"的兜底"""
        if not enemies:
            return

        score = 15
        nearest, dist = self._find_nearest(self_actor, enemies)

        if dist > SKILL_RANGE:
            # 不在攻击范围内，需要靠近
            score += 10

        self._add_score(ACTION_ATK_HERO, score)

    def _evaluate_skills(self, self_actor, enemies, player_info):
        """对应游戏技能评分（EAIActionType 10001-10004）"""
        if not enemies:
            return

        skills = player_info.get('skills', {})
        nearest, dist = self._find_nearest(self_actor, enemies)
        in_range = dist <= SKILL_RANGE

        # 普攻
        if self._config.get('自动普攻', True):
            atk = skills.get('attack', {})
            if not atk.get('isCD', False):
                score = 40
                if in_range:
                    score += 10
                self._add_score(ACTION_SKILL_ATTACK, score)

        # 技能1
        if self._config.get('自动技能1', True):
            s1 = skills.get('skill1', {})
            if not s1.get('isCD', False):
                score = 60
                if in_range:
                    score += 10
                self._add_score(ACTION_SKILL_1, score)

        # 技能2
        if self._config.get('自动技能2', True):
            s2 = skills.get('skill2', {})
            if not s2.get('isCD', False):
                score = 70
                if in_range:
                    score += 10
                self._add_score(ACTION_SKILL_2, score)

        # 大招
        if self._config.get('自动大招', True):
            ult = skills.get('ultimate', {})
            if not ult.get('isCD', False):
                score = 90
                if in_range:
                    score += 10
                self._add_score(ACTION_ULTIMATE, score)

    def _evaluate_protect_self(self, self_actor, enemies):
        """对应 AI_Com_Hero_Evaluate_ProtectSelfByHpRate"""
        hp_pct = _hp_percent(self_actor)
        threshold = self._config.get('低血撤退阈值(%)', 30) / 100.0

        score = 0
        if hp_pct < threshold:
            score += 50
        if hp_pct < 0.15:
            score += 30

        # 附近有敌人时更紧急
        if enemies:
            _, dist = self._find_nearest(self_actor, enemies)
            if dist < 300:
                score += 20

        if score > 0:
            self._add_score(ACTION_PROTECT_SELF, score)

    def _evaluate_protect_friend(self, self_actor, allies):
        """对应 AI_Com_Hero_Evaluate_ProtectFriendByHpRate"""
        if not allies:
            return

        for ally in allies:
            ally_hp = _hp_percent(ally)
            if ally_hp < 0.25:
                dist = _distance(self_actor, ally)
                if dist < 300:
                    self._add_score(ACTION_PROTECT_FRIEND, 40)
                    return

    def _evaluate_run_away(self, self_actor, enemies):
        """对应 AI_Com_Hero_Evaluate_ProtectSelfByDis（极端距离+低血）"""
        hp_pct = _hp_percent(self_actor)
        if hp_pct >= 0.20 or not enemies:
            return

        _, dist = self._find_nearest(self_actor, enemies)
        if dist < 150:
            self._add_score(ACTION_RUN_AWAY, 70)

    # ==================== RefreshMax ====================

    def _refresh_max(self):
        """对应 AI_Score HandleType=RefreshMax：选最高分动作"""
        if not self._scores:
            return None, 0
        best = max(self._scores, key=self._scores.get)
        return best, self._scores[best]

    # ==================== DoAction ====================

    def _execute_action(self, action, self_actor, enemies, allies, player_info):
        """对应游戏 AI_Com_Hero_Action 子树"""
        if action == ACTION_ULTIMATE:
            self._exec_skill(enemies, SKILL_BUTTON_ULTIMATE)
        elif action == ACTION_SKILL_2:
            self._exec_skill(enemies, SKILL_BUTTON_SKILL2)
        elif action == ACTION_SKILL_1:
            self._exec_skill(enemies, SKILL_BUTTON_SKILL1)
        elif action == ACTION_SKILL_ATTACK:
            self._exec_skill(enemies, SKILL_BUTTON_ATTACK)
        elif action == ACTION_ATK_HERO:
            self._exec_move_to_enemy(self_actor, enemies)
        elif action == ACTION_PROTECT_SELF:
            self._exec_flee(self_actor, enemies)
        elif action == ACTION_PROTECT_FRIEND:
            self._exec_protect_ally(self_actor, allies)
        elif action == ACTION_RUN_AWAY:
            self._exec_flee(self_actor, enemies)

    def _exec_skill(self, enemies, button):
        """对应 AI_ExecuteSkill：停止移动 → 释放技能"""
        self._conn.stop_move()
        resp = self._conn.use_skill(button)
        if resp.get('status') != 'ok':
            logger.warning(f"技能释放失败 button={button}: {resp.get('message', '')}")

    def _exec_move_to_enemy(self, self_actor, enemies):
        """对应 AI_Com_Hero_Action_AtkHero：向敌人移动"""
        target = self._get_locked_target(self_actor, enemies)
        if target is None:
            self._conn.stop_move()
            return

        dist = _distance(self_actor, target)
        if dist <= SKILL_RANGE:
            self._conn.stop_move()
            return

        dx = target['screenX'] - self_actor['screenX']
        dy = target['screenY'] - self_actor['screenY']
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1:
            return
        # 翻转 Y：屏幕 Y 向下，Unity Y 向上
        self._conn.set_move_dir(dx / length, -dy / length, length)

    def _exec_flee(self, self_actor, enemies):
        """远离最近敌人"""
        if not enemies:
            return
        nearest, _ = self._find_nearest(self_actor, enemies)
        dx = self_actor['screenX'] - nearest['screenX']
        dy = self_actor['screenY'] - nearest['screenY']
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1:
            return
        self._conn.set_move_dir(dx / length, -dy / length, length)

    def _exec_protect_ally(self, self_actor, allies):
        """移向低血友方"""
        if not allies:
            return
        weakest = min(allies, key=lambda a: _hp_percent(a))
        dx = weakest['screenX'] - self_actor['screenX']
        dy = weakest['screenY'] - self_actor['screenY']
        length = math.sqrt(dx * dx + dy * dy)
        if length < 100:
            self._conn.stop_move()
            return
        self._conn.set_move_dir(dx / length, -dy / length, length)

    # ==================== 目标锁定（对应 AI_FastSearchActor）====================

    def _get_locked_target(self, self_actor, enemies):
        """锁定最近敌人，丢失 3 帧后重选"""
        if not enemies:
            self._locked_target = None
            return None

        # 尝试匹配已锁定目标
        if self._locked_target is not None:
            matched = None
            for e in enemies:
                if e.get('actorIndex') == self._locked_target:
                    matched = e
                    break
            if matched is not None:
                self._locked_target_lost = 0
                return matched
            self._locked_target_lost += 1
            if self._locked_target_lost < 3:
                return None

        # 重选：最近敌人
        nearest, _ = self._find_nearest(self_actor, enemies)
        if nearest is not None:
            self._locked_target = nearest.get('actorIndex')
            self._locked_target_lost = 0
        return nearest

    # ==================== 工具方法 ====================

    def _find_self(self, actors, player_info):
        """从 actor 列表中找到玩家自己"""
        for a in actors:
            if a.get('isPlayer'):
                return a
        # 回退：用 player_info 的坐标构造
        if player_info.get('found'):
            return {
                'screenX': player_info.get('screenX', 0),
                'screenY': player_info.get('screenY', 0),
                'campType': player_info.get('campType', 0),
                'hp': 0, 'maxHp': 0,
                'isDead': player_info.get('isDead', False),
                'isPlayer': True,
            }
        return None

    def _find_nearest(self, self_actor, targets):
        """找最近的目标，返回 (target, distance)"""
        if not targets:
            return None, float('inf')
        best = None
        best_dist = float('inf')
        for t in targets:
            d = _distance(self_actor, t)
            if d < best_dist:
                best = t
                best_dist = d
        return best, best_dist

    def _add_score(self, action, score):
        """对应 AI_Score HandleType=AddScore"""
        if action in self._scores:
            self._scores[action] += score
        else:
            self._scores[action] = score

    def cleanup(self):
        """清理资源"""
        self._conn.stop_move()
        self._scores.clear()
        self._locked_target = None
