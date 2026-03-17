"""
漫画群星触发任务基类

继承 TriggerTask 和 JumpTaskMixin，提供触发型任务的通用功能。
此类通过 Mixin 模式复用 JumpTaskMixin 中的公共方法。
"""

from ok import TriggerTask

from src.task.mixins import JumpTaskMixin


class BaseJumpTriggerTask(TriggerTask, JumpTaskMixin):
    """
    漫画群星触发任务基类

    继承 TriggerTask 和 JumpTaskMixin，提供：
    - 游戏状态检测（in_game, in_lobby）
    - 分辨率自适应
    - 后台模式支持

    用于需要定期检查并触发的任务（如 AutoCombatTask）
    """

    def __init__(self, *args, **kwargs):
        TriggerTask.__init__(self, *args, **kwargs)
        self._init_mixin_vars()
        self.name = "BaseJumpTriggerTask"
        self.description = "漫画群星触发任务基类"
