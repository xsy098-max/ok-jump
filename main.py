import os
import sys

# pythonw 模式下 sys.stdout/stderr 为 None,第三方库的 print() 会抛 OSError
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

# pyappify 启动时会移除 PATH 环境变量,导致 PySide6 初始化失败
# 必须在导入其他模块前设置 PATH
if 'PATH' not in os.environ:
    os.environ['PATH'] = ';'.join([
        os.environ.get('SystemRoot', r'C:\Windows') + r'\System32',
        os.environ.get('SystemRoot', r'C:\Windows'),
    ])

import atexit

from config import config
from ok import OK

from src.compat import (
    apply_post_init_patches,
    apply_pre_init_patches,
    cleanup_logger,
    export_logs,
    init_scheduled_task_executor,
    pre_connect_adb,
    smart_device_selection,
    _auto_enable_correct_combat_task,
)
from ok import Logger

logger = Logger.get_logger(__name__)

# 全局定时器引用(防止垃圾回收)
_schedule_timer = None


if __name__ == '__main__':
    # Register cleanup function to run on exit
    atexit.register(cleanup_logger)

    # 智能设备选择(必须在 OK(config) 之前执行,否则配置修改不会生效)
    smart_device_selection()
    # 应用框架补丁(OK 初始化前)
    apply_pre_init_patches()
    # 在 OK 框架初始化前预连接 ADB
    pre_connect_adb()
    # 初始化 OK 框架(会读取 devices.json)
    ok = OK(config)
    # 应用需要日志 handler / GUI 就绪后的补丁
    apply_post_init_patches(export_logs)

    # 延迟初始化定时任务调度器(需要在 GUI 启动后,StartController 才可用)
    def delayed_init_scheduler():
        global _schedule_timer
        _schedule_timer = init_scheduled_task_executor()
        if _schedule_timer:
            logger.info('定时任务调度器延迟初始化完成')

    def delayed_auto_enable_combat():
        """延迟自动启用正确的战斗触发器(等 executor 和 GUI 就绪)"""
        _auto_enable_correct_combat_task()

    from PySide6.QtCore import QTimer
    QTimer.singleShot(1000, delayed_init_scheduler)  # 1秒后初始化
    QTimer.singleShot(2000, delayed_auto_enable_combat)  # 2秒后自动切换触发器

    ok.start()
