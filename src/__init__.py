"""
漫画群星自动化工具 - 源代码包

提供全局资源管理和任务模块导出
"""

from .task.MainWindowTask import MainWindowTask
from .scene.JumpScene import JumpScene
from .globals import Globals

__all__ = ['MainWindowTask', 'JumpScene', 'Globals', 'init_globals', 'jump_globals']

# 全局实例（在 OK 初始化后通过 init_globals 创建）
jump_globals: Globals = None


def init_globals(exit_event=None) -> Globals:
    """
    初始化全局资源管理器

    应在 OK 框架启动后调用，创建全局资源管理器实例。

    Args:
        exit_event: 退出事件对象

    Returns:
        Globals: 全局资源管理器实例
    """
    global jump_globals
    jump_globals = Globals(exit_event)
    return jump_globals
