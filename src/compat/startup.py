# -*- coding: utf-8 -*-
"""
启动辅助逻辑:智能设备选择、ADB 预连接、定时任务调度器、日志导出与清理。

这些不是框架补丁,而是 ok-jump 应用层的启动编排代码,
从 main.py 收敛到此以便测试与维护。
"""

import json
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

from ok import Logger, og

logger = Logger.get_logger(__name__)


# ---------------------------------------------------------------------------
# 智能设备选择
# ---------------------------------------------------------------------------

def smart_device_selection():
    """
    智能设备选择。

    检测 PC 版、模拟器 ADB 和 Unity 工程连接状态,自动选择合适的设备:
    - 只有 Unity 可达 → 选择 Unity
    - 只有 PC 运行 → 选择 PC
    - 只有模拟器连接 → 选择 ADB
    - 多个或没有 → 保持用户选择

    注意:此函数必须在 OK(config) 之前执行,否则配置修改不会生效。
    """
    from src.utils.DeviceDetector import DeviceDetector

    # 获取设备状态(用于调试)
    status = DeviceDetector.get_device_status()
    print(f'[智能设备选择] PC运行: {status["pc_running"]}, '
          f'ADB连接: {status["adb_connected"]}, Unity: {status["unity_running"]}')

    smart_device = DeviceDetector.get_smart_default()
    if smart_device:
        devices_path = Path('configs/devices.json')
        if devices_path.exists():
            try:
                with open(devices_path, 'r', encoding='utf-8') as f:
                    devices_config = json.load(f)

                current_preferred = devices_config.get('preferred', 'pc')
                if current_preferred != smart_device:
                    devices_config['preferred'] = smart_device
                    with open(devices_path, 'w', encoding='utf-8') as f:
                        json.dump(devices_config, f, indent=4, ensure_ascii=False)
                    print(f'[智能设备选择] 切换到 {smart_device}')
                else:
                    print(f'[智能设备选择] 当前设备 {smart_device} 已是最佳选择')
            except Exception as e:
                print(f'[智能设备选择] 失败: {e}')
    else:
        print('[智能设备选择] 保持用户配置的设备选择')


# ---------------------------------------------------------------------------
# ADB 预连接
# ---------------------------------------------------------------------------

def pre_connect_adb():
    """
    在 OK 框架初始化前预连接 ADB。

    从 CITestTask.json 读取正确的 ADB 端口提前连接,
    这样 ok 框架初始化时就能检测到设备。
    """
    try:
        config_path = Path('configs/CITestTask.json')
        if not config_path.exists():
            return

        with open(config_path, 'r', encoding='utf-8') as f:
            ci_config = json.load(f)

        adb_port = ci_config.get('ADB端口', 5555)
        logger.info(f'[ADB预连接] 配置端口: {adb_port}')

        from adbutils import adb

        for addr in [f'127.0.0.1:{adb_port}', f'emulator-{adb_port}']:
            try:
                result = adb.connect(addr, timeout=5)
                logger.info(f'[ADB预连接] 尝试 {addr}: {result}')
            except Exception as e:
                logger.debug(f'[ADB预连接] {addr} 连接失败: {e}')

        devices = adb.device_list()
        if devices:
            logger.info(f'[ADB预连接] 已连接设备: {[d.serial for d in devices]}')
        else:
            logger.info('[ADB预连接] 暂无设备连接(模拟器可能未启动)')

    except Exception as e:
        logger.warning(f'[ADB预连接] 失败: {e}')


# ---------------------------------------------------------------------------
# 日志导出与清理
# ---------------------------------------------------------------------------

def export_logs():
    """打包 logs 目录到下载文件夹并打开资源管理器定位"""
    app_name = og.config.get('gui_title')
    downloads_path = Path.home() / "Downloads"
    zip_path = downloads_path / f"{app_name}-log.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for folder in ["logs"]:
            source_dir = Path.cwd() / folder
            if not source_dir.is_dir():
                continue
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    zipf.write(file_path, file_path.relative_to(Path.cwd()))

    subprocess.Popen(rf'explorer /select,"{zip_path}"')


def cleanup_logger():
    """
    退出前清理日志资源,防止退出时的 I/O 错误:
    排空 QueueHandler 队列,避免文件句柄关闭后仍尝试写入。
    """
    import logging

    ok_logger = logging.getLogger("ok")
    for handler in ok_logger.handlers:
        if hasattr(handler, 'queue'):
            try:
                while not handler.queue.empty():
                    handler.queue.get_nowait()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 定时任务调度器
# ---------------------------------------------------------------------------

def init_scheduled_task_executor():
    """
    初始化定时任务调度器。

    读取 CITestTask 的定时配置,在指定时间自动执行任务。
    支持:每天、工作日、周末、特定星期几执行。
    支持配置文件热更新,修改配置后立即生效。
    """
    from PySide6.QtCore import QTimer, QFileSystemWatcher

    config_path = Path('configs/CITestTask.json')
    if not config_path.exists():
        logger.warning('CITestTask.json 不存在,跳过定时调度初始化')
        return None

    # 使用字典存储可变配置(支持热更新)
    schedule_config = {
        'enabled': False,
        'hour': 9,
        'minute': 0,
        'day': '每天'
    }

    # 记录上次执行的日期和时间组合(格式: "2024-03-31 15:30"),防止同一时间重复执行
    last_execution_key = {'key': None}

    def get_execution_key():
        now = datetime.now()
        return f"{now.strftime('%Y-%m-%d')} {schedule_config['hour']:02d}:{schedule_config['minute']:02d}"

    # 星期映射
    day_mapping = {
        '周一': 0, '周二': 1, '周三': 2, '周四': 3, '周五': 4, '周六': 5, '周日': 6,
        '工作日': 'weekday', '周末': 'weekend', '每天': 'everyday'
    }

    def load_schedule_config():
        nonlocal schedule_config
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                new_config = json.load(f)

            new_enabled = new_config.get('启用定时执行', False)
            new_hour = new_config.get('定时执行时间(时)', 9)
            new_minute = new_config.get('定时执行时间(分)', 0)
            new_day = new_config.get('定时执行日期', '每天')

            changed = (
                schedule_config['enabled'] != new_enabled or
                schedule_config['hour'] != new_hour or
                schedule_config['minute'] != new_minute or
                schedule_config['day'] != new_day
            )

            if changed:
                logger.info(f'定时配置已更新: {new_day} {new_hour:02d}:{new_minute:02d} (启用={new_enabled})')

            schedule_config['enabled'] = new_enabled
            schedule_config['hour'] = new_hour
            schedule_config['minute'] = new_minute
            schedule_config['day'] = new_day

            return True
        except Exception as e:
            logger.error(f'读取 CITestTask.json 失败: {e}')
            return False

    def on_config_changed(path):
        logger.info(f'检测到配置文件变化: {path}')
        if load_schedule_config():
            # 时间变化后,重置执行键,允许新时间执行
            last_execution_key['key'] = None
            logger.info(f'定时配置已热更新,执行键已重置,'
                        f'新时间: {schedule_config["hour"]:02d}:{schedule_config["minute"]:02d}')

    # 初始加载配置
    if not load_schedule_config():
        return None

    if not schedule_config['enabled']:
        logger.info('定时执行未启用,跳过调度初始化')
        return None

    logger.info(f'定时执行已启用: {schedule_config["day"]} '
                f'{schedule_config["hour"]:02d}:{schedule_config["minute"]:02d}')

    def should_execute_today():
        today_weekday = datetime.now().weekday()  # 0=周一, 6=周日
        day_config = day_mapping.get(schedule_config['day'], 'everyday')

        if day_config == 'everyday':
            return True
        elif day_config == 'weekday':
            return today_weekday < 5  # 周一到周五
        elif day_config == 'weekend':
            return today_weekday >= 5  # 周六周日
        else:
            return today_weekday == day_config

    def check_and_execute():
        if not schedule_config['enabled']:
            return

        now = datetime.now()

        current_key = get_execution_key()
        if last_execution_key['key'] == current_key:
            return

        if now.hour != schedule_config['hour'] or now.minute != schedule_config['minute']:
            return

        if not should_execute_today():
            logger.debug(f'今天不在执行日期范围内: {schedule_config["day"]}')
            return

        logger.info(f'定时触发 CITestTask 执行: {current_key}')
        last_execution_key['key'] = current_key

        try:
            from src.task.CITestTask import CITestTask

            if hasattr(og, 'executor') and og.executor:
                for task in og.executor.onetime_tasks:
                    if isinstance(task, CITestTask):
                        logger.info('定时调度器启动 CITestTask...')
                        if hasattr(og, 'app') and og.app and hasattr(og.app, 'start_controller'):
                            og.app.start_controller.start(task)
                        else:
                            logger.warning('StartController 未初始化,无法启动任务')
                        return
                logger.warning('未找到已注册的 CITestTask 实例')
        except Exception as e:
            logger.error(f'定时执行任务失败: {e}')

    # 创建定时器,每分钟检查一次
    timer = QTimer()
    timer.timeout.connect(check_and_execute)
    timer.start(60000)

    # 创建文件监听器,支持配置热更新
    watcher = QFileSystemWatcher()
    watcher.addPath(str(config_path))
    watcher.fileChanged.connect(on_config_changed)

    logger.info('定时任务调度器已启动(支持配置热更新),每分钟检查一次')

    # 返回定时器和监听器引用,防止被垃圾回收
    return {'timer': timer, 'watcher': watcher}
