# -*- coding: utf-8 -*-
"""ok-script 框架兼容层:运行时补丁与应用启动编排"""

from src.compat.patches import (
    SELF_MANAGED_TASKS,
    apply_post_init_patches,
    apply_pre_init_patches,
    _auto_enable_correct_combat_task,
    _is_unity_active,
    _is_unity_port_open,
    _unity_trigger_loop,
)
from src.compat.startup import (
    cleanup_logger,
    export_logs,
    init_scheduled_task_executor,
    pre_connect_adb,
    smart_device_selection,
)

__all__ = [
    'SELF_MANAGED_TASKS',
    'apply_pre_init_patches',
    'apply_post_init_patches',
    'smart_device_selection',
    'pre_connect_adb',
    'cleanup_logger',
    'export_logs',
    'init_scheduled_task_executor',
    '_auto_enable_correct_combat_task',
    '_is_unity_active',
    '_is_unity_port_open',
    '_unity_trigger_loop',
]
