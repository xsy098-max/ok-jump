import os
# pyappify 启动时会移除 PATH 环境变量，导致 PySide6 初始化失败
# 必须在导入其他模块前设置 PATH
if 'PATH' not in os.environ:
    # 使用常见的系统路径
    os.environ['PATH'] = ';'.join([
        os.environ.get('SystemRoot', r'C:\Windows') + r'\System32',
        os.environ.get('SystemRoot', r'C:\Windows'),
    ])

import atexit
import json
import subprocess
import zipfile
from pathlib import Path

from config import config
from ok import OK, og, Logger
from ok.gui.start.StartCard import StartCard


def patch_logger_handler():
    """
    Patch SafeFileHandler to prevent I/O errors on exit and during log rotation.
    The original implementation raises errors when:
    - The file is closed during program shutdown
    - The file is locked during log rotation (PermissionError)
    """
    from ok.util.logger import SafeFileHandler
    from logging.handlers import TimedRotatingFileHandler
    logger = Logger.get_logger(__name__)
    
    def patched_emit(self, record):
        """Silently skip if stream is closed or file is locked."""
        try:
            if self.stream is None or self.stream.closed:
                return  # Silently skip, don't raise error
            super(TimedRotatingFileHandler, self).emit(record)
        except PermissionError:
            # File is locked by another process (e.g., during rollover)
            self.handleError(record)
        except Exception:
            self.handleError(record)
    
    SafeFileHandler.emit = patched_emit
    logger.info('SafeFileHandler patched: I/O errors suppressed')


def cleanup_logger():
    """
    Clean up logger resources to prevent I/O errors on exit.
    Stops the QueueListener thread before file handles are closed.
    """
    import logging
    
    # Find and stop the QueueListener by checking all handlers
    ok_logger = logging.getLogger("ok")
    for handler in ok_logger.handlers:
        # QueueHandler wraps the actual handlers
        if hasattr(handler, 'queue'):
            # This is a QueueHandler, drain the queue
            try:
                while not handler.queue.empty():
                    handler.queue.get_nowait()
            except Exception:
                pass


def export_logs():
    app_name = og.config.get('gui_title')
    downloads_path = Path.home() / "Downloads"
    zip_path = downloads_path / f"{app_name}-log.zip"
    folders_to_archive = ["logs"]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for folder in folders_to_archive:
            source_dir = Path.cwd() / folder
            if not source_dir.is_dir():
                continue
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    zipf.write(file_path, file_path.relative_to(Path.cwd()))

    subprocess.Popen(r'explorer /select,"{}"'.format(zip_path))


def patch_task_buttons_stop():
    """
    Patch TaskButtons.stop_clicked to properly stop tasks
    
    问题: ok-script框架中TaskButtons.stop_clicked会调用task.unpause()
    而unpause()会调用executor.start()恢复执行器运行，可能导致任务意外重新启动
    
    修复: 停止任务时只禁用任务，不调用unpause()恢复执行器
    """
    from ok.gui.tasks.TaskCard import TaskButtons
    logger = Logger.get_logger(__name__)
    
    def patched_stop_clicked(self):
        logger.info(f'停止任务: {self.task.name}')
        # 禁用任务
        self.task.disable()
        # 设置_paused为False（不调用executor.start()）
        # 这样任务状态会被正确重置，但不会触发执行器恢复运行
        self.task._paused = False
        # 发送信号更新UI
        from ok.gui.Communicate import communicate
        communicate.task.emit(self.task)
    
    TaskButtons.stop_clicked = patched_stop_clicked
    logger.info('TaskButtons.stop_clicked patched: proper task stopping')


def patch_start_controller():
    """
    Patch StartController to allow minimized/off-screen window for background mode
    """
    from ok.gui.StartController import StartController
    logger = Logger.get_logger(__name__)
    
    original_check_device_error = StartController.check_device_error
    
    # 任务列表：这些任务会自己管理模拟器启动，不需要预先检查设备连接
    SELF_MANAGED_TASKS = ['CITestTask']
    
    def patched_check_device_error(self):
        # Check if current task is self-managed (like CITestTask)
        current_task = getattr(self, 'current_task', None)
        if current_task:
            task_class_name = current_task.__class__.__name__
            if task_class_name in SELF_MANAGED_TASKS:
                logger.info(f'Skipping device check for self-managed task: {task_class_name}')
                return None  # Allow the task to start without device check
        
        # Get the original result
        result = original_check_device_error(self)
        
        # If the error is about minimized/off-screen window, check if we should skip
        if result and 'minimized or out of screen' in result.lower():
            if self.config.get('windows', {}).get('skip_pos_check', False):
                logger.info('skip_pos_check is enabled, allowing minimized/off-screen window')
                return None  # Allow the task to start
        
        return result
    
    StartController.check_device_error = patched_check_device_error
    
    # Patch start method to track current task
    original_start = getattr(StartController, 'start', None)
    
    def patched_start(self, task):
        self.current_task = task
        # Check if this task is self-managed
        task_class_name = task.__class__.__name__
        if task_class_name in SELF_MANAGED_TASKS:
            logger.info(f'Self-managed task detected: {task_class_name}, device check will be skipped')
            # 对于自管理任务，先启动模拟器并连接 ADB
            # 这样 TaskExecutor 才能获取截图
            _pre_start_emulator_for_task(task)
        if original_start:
            return original_start(self, task)

    if original_start:
        StartController.start = patched_start

    logger.info('StartController patched: skip_pos_check + self-managed tasks support')


def _pre_start_emulator_for_task(task):
    """
    在任务启动前启动模拟器并连接 ADB
    
    对于 CITestTask 这样的任务，需要先启动模拟器
    TaskExecutor 才能获取截图
    """
    import json
    from pathlib import Path
    from adbutils import adb
    
    # 获取 logger
    pre_logger = Logger.get_logger(__name__)
    
    pre_logger.info('=' * 40)
    pre_logger.info('预启动模拟器流程开始...')
    
    try:
        # 从配置文件读取模拟器设置
        config_path = Path('configs/CITestTask.json')
        if not config_path.exists():
            pre_logger.warning('未找到 CITestTask.json 配置文件')
            return
        
        with open(config_path, 'r', encoding='utf-8') as f:
            ci_config = json.load(f)
        
        emulator_path = ci_config.get('模拟器路径', '')
        adb_port = ci_config.get('ADB端口', 5554)
        instance_index = ci_config.get('模拟器实例索引', 0)
        
        pre_logger.info(f'模拟器路径: {emulator_path}')
        pre_logger.info(f'ADB端口: {adb_port}')
        pre_logger.info(f'实例索引: {instance_index}')
        
        if not emulator_path:
            pre_logger.warning('未配置模拟器路径')
            return
        
        from pathlib import Path
        emulator_dir = Path(emulator_path).parent
        ldconsole_path = emulator_dir / 'ldconsole.exe'
        
        # 检查模拟器是否已运行
        try:
            adb.connect(f'127.0.0.1:{adb_port}', timeout=5)
            devices = adb.device_list()
            for device in devices:
                if f'emulator-{adb_port}' in device.serial or f'127.0.0.1:{adb_port}' in device.serial:
                    pre_logger.info(f'模拟器已运行: {device.serial}')
                    pre_logger.info('=' * 40)
                    return  # 模拟器已在运行
        except Exception as e:
            pre_logger.debug(f'ADB检测失败: {e}')
        
        # 启动模拟器
        if ldconsole_path.exists():
            import subprocess
            cmd = [str(ldconsole_path), 'launch', '--index', str(instance_index)]
            pre_logger.info(f'执行命令: {" ".join(cmd)}')
            subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
        else:
            pre_logger.warning(f'ldconsole.exe 不存在: {ldconsole_path}')
        
        # 等待模拟器启动并连接 ADB
        import time
        max_wait = 60
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                adb.connect(f'127.0.0.1:{adb_port}', timeout=5)
                devices = adb.device_list()
                for device in devices:
                    if f'emulator-{adb_port}' in device.serial or f'127.0.0.1:{adb_port}' in device.serial:
                        pre_logger.info(f'模拟器启动成功: {device.serial}')
                        pre_logger.info('=' * 40)
                        return
            except Exception:
                pass
            time.sleep(2)
        
        pre_logger.warning(f'模拟器启动超时 ({max_wait}秒)')
        pre_logger.info('=' * 40)
        
    except Exception as e:
        pre_logger.error(f'预启动模拟器失败: {e}')


def patch_adb_connect_error_handling():
    """
    Patch DeviceManager.adb_connect to reduce log level for expected connection failures.
    When no device is connected, ADB timeout is expected behavior, not an error.
    """
    from ok.device.DeviceManager import DeviceManager
    from adbutils import AdbError, AdbTimeout
    logger = Logger.get_logger(__name__)

    original_adb_connect = DeviceManager.adb_connect

    def patched_adb_connect(self, addr, try_connect=True):
        from adbutils import AdbError, AdbTimeout
        try:
            for device in self.adb.list():
                if self.exit_event.is_set():
                    logger.debug(f"adb_connect exit_event is set")
                    return None
                if device.serial == addr:
                    if device.state == 'offline':
                        logger.info(f'adb_connect offline disconnect first {addr}')
                        self.adb.disconnect(addr)
                    else:
                        logger.info(f'adb_connect already connected {addr}')
                        return self.adb.device(serial=addr)
            if try_connect:
                ret = self.adb.connect(addr, timeout=5)
                logger.info(f'adb_connect try_connect {addr} {ret}')
                return original_adb_connect(self, addr, try_connect=False)
            else:
                logger.debug(f'adb_connect {addr} not in device list')
        except AdbTimeout:
            # Timeout is expected when no device is connected - use DEBUG level
            logger.debug(f"adb connect timeout (no device at {addr})")
        except AdbError as e:
            # Other ADB errors - use WARNING level for expected failures
            logger.warning(f"adb connect error {addr}: {e}")
        except Exception as e:
            # Unexpected errors - keep as ERROR
            logger.error(f"adb connect unexpected error {addr}", e)

    DeviceManager.adb_connect = patched_adb_connect
    logger.info('DeviceManager.adb_connect patched: timeout errors suppressed')


def patch_ocr_negative_box_logging():
    """
    Suppress harmless PaddleOCR 'negative box' error logs.
    These occur when OCR detects text with negative coordinates in rotated boxes,
    which is internal framework behavior and does not affect functionality.
    """
    import logging
    logger = Logger.get_logger(__name__)

    class OCRNegativeBoxFilter(logging.Filter):
        def filter(self, record):
            # Suppress 'ocr result negative box' messages
            msg = record.getMessage()
            if 'negative box' in msg:
                return False
            return True

    # Add filter to the root logger's handlers (catches all loggers)
    for handler in logging.root.handlers:
        handler.addFilter(OCRNegativeBoxFilter())
    
    # Also add to ok logger's handlers
    ok_logger = logging.getLogger('ok')
    for handler in ok_logger.handlers:
        handler.addFilter(OCRNegativeBoxFilter())
    
    logger.info('OCR negative box error logging suppressed')


def patch_capture_process_not_found_logging():
    """
    Suppress harmless 'process no longer exists' error logs from capture module.
    
    These occur when the emulator is closed during cleanup, and the capture
    module tries to get process info from a window whose process has already exited.
    This is expected behavior and does not affect functionality.
    """
    import logging
    logger = Logger.get_logger(__name__)

    class ProcessNotFoundFilter(logging.Filter):
        def filter(self, record):
            # Suppress 'process no longer exists' and 'NoSuchProcess' messages from capture
            msg = record.getMessage()
            if 'process no longer exists' in msg or 'NoSuchProcess' in msg:
                # Check if it's from capture module
                if hasattr(record, 'name') and 'capture' in record.name:
                    return False
                # Also check the message content for capture-related keywords
                if 'get_exe_by_hwnd' in msg or 'dnplayer' in msg.lower():
                    return False
            return True

    # Add filter to the root logger's handlers (catches all loggers)
    for handler in logging.root.handlers:
        handler.addFilter(ProcessNotFoundFilter())
    
    # Also add to ok logger's handlers
    ok_logger = logging.getLogger('ok')
    for handler in ok_logger.handlers:
        handler.addFilter(ProcessNotFoundFilter())
    
    logger.info('Capture process not found error logging suppressed')


def patch_task_buttons_alignment():
    """
    Patch TaskButtons to fix button alignment issue
    Set a minimum width for the button container to ensure alignment
    """
    from ok.gui.tasks.TaskCard import TaskButtons
    logger = Logger.get_logger(__name__)

    original_init_ui = TaskButtons.init_ui

    def patched_init_ui(self):
        original_init_ui(self)
        # Set minimum width to ensure buttons are aligned across all task cards
        # This accounts for the maximum button combination (Start + Stop + Pause)
        self.setMinimumWidth(280)

    TaskButtons.init_ui = patched_init_ui
    logger.info('TaskButtons patched: button alignment fixed')


def smart_device_selection():
    """
    智能设备选择

    检测PC版和模拟器ADB连接状态，自动选择合适的设备：
    - 只有PC运行 → 选择PC
    - 只有模拟器连接 → 选择ADB
    - 两者都运行或都未运行 → 保持用户选择

    注意：此函数必须在 OK(config) 之前执行，否则配置修改不会生效
    """
    from src.utils.DeviceDetector import DeviceDetector

    # 获取设备状态（用于调试）
    status = DeviceDetector.get_device_status()
    print(f'[智能设备选择] PC运行: {status["pc_running"]}, ADB连接: {status["adb_connected"]}')

    smart_device = DeviceDetector.get_smart_default()
    if smart_device:
        # 读取当前配置
        devices_path = Path('configs/devices.json')
        if devices_path.exists():
            try:
                with open(devices_path, 'r', encoding='utf-8') as f:
                    devices_config = json.load(f)

                current_preferred = devices_config.get('preferred', 'pc')
                if current_preferred != smart_device:
                    # 更新配置
                    devices_config['preferred'] = smart_device
                    with open(devices_path, 'w', encoding='utf-8') as f:
                        json.dump(devices_config, f, indent=4, ensure_ascii=False)

                    print(f'[智能设备选择] 切换到 {smart_device}')
                else:
                    print(f'[智能设备选择] 当前设备 {smart_device} 已是最佳选择')
            except Exception as e:
                print(f'[智能设备选择] 失败: {e}')
    else:
        # 两者都运行或都未运行，保持用户选择
        print('[智能设备选择] 保持用户配置的设备选择')


StartCard.export_logs = staticmethod(export_logs)

# 全局定时器引用（防止垃圾回收）
_schedule_timer = None


def pre_connect_adb():
    """
    在 OK 框架初始化前预连接 ADB
    
    从 CITestTask.json 读取正确的 ADB 端口，提前连接，
    这样 ok 框架初始化时就能检测到设备。
    """
    from ok import Logger
    logger = Logger.get_logger(__name__)
    
    try:
        # 从 CITestTask.json 读取 ADB 端口
        config_path = Path('configs/CITestTask.json')
        if not config_path.exists():
            return
        
        with open(config_path, 'r', encoding='utf-8') as f:
            ci_config = json.load(f)
        
        adb_port = ci_config.get('ADB端口', 5555)
        logger.info(f'[ADB预连接] 配置端口: {adb_port}')
        
        # 尝试连接 ADB
        from adbutils import adb
        
        # 尝试两种连接格式
        for addr in [f'127.0.0.1:{adb_port}', f'emulator-{adb_port}']:
            try:
                result = adb.connect(addr, timeout=5)
                logger.info(f'[ADB预连接] 尝试 {addr}: {result}')
            except Exception as e:
                logger.debug(f'[ADB预连接] {addr} 连接失败: {e}')
        
        
        # 检查连接结果
        devices = adb.device_list()
        if devices:
            logger.info(f'[ADB预连接] 已连接设备: {[d.serial for d in devices]}')
        else:
            logger.info('[ADB预连接] 暂无设备连接（模拟器可能未启动）')
            
    except Exception as e:
        logger.warning(f'[ADB预连接] 失败: {e}')


def init_scheduled_task_executor():
    """
    初始化定时任务调度器
    
    读取 CITestTask 的定时配置，在指定时间自动执行任务。
    支持：每天、工作日、周末、特定星期几执行。
    支持配置文件热更新，修改配置后立即生效。
    """
    from PySide6.QtCore import QTimer, QFileSystemWatcher
    from datetime import datetime
    import json
    
    logger = Logger.get_logger(__name__)
    
    # 配置路径
    config_path = Path('configs/CITestTask.json')
    if not config_path.exists():
        logger.warning('CITestTask.json 不存在，跳过定时调度初始化')
        return None
    
    # 使用字典存储可变配置（支持热更新）
    schedule_config = {
        'enabled': False,
        'hour': 9,
        'minute': 0,
        'day': '每天'
    }
    
    # 记录上次执行的日期和时间组合（格式: "2024-03-31 15:30"），防止同一时间重复执行
    # 但不同时间可以多次执行
    last_execution_key = {'key': None}
    
    def get_execution_key():
        """获取当前执行键（日期+时间组合）"""
        now = datetime.now()
        return f"{now.strftime('%Y-%m-%d')} {schedule_config['hour']:02d}:{schedule_config['minute']:02d}"
    
    # 星期映射
    day_mapping = {
        '周一': 0, '周二': 1, '周三': 2, '周四': 3, '周五': 4, '周六': 5, '周日': 6,
        '工作日': 'weekday', '周末': 'weekend', '每天': 'everyday'
    }
    
    def load_schedule_config():
        """加载定时配置（支持热更新）"""
        nonlocal schedule_config
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            new_enabled = config.get('启用定时执行', False)
            new_hour = config.get('定时执行时间(时)', 9)
            new_minute = config.get('定时执行时间(分)', 0)
            new_day = config.get('定时执行日期', '每天')
            
            # 检测配置变化
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
        """配置文件变化回调（热更新）"""
        logger.info(f'检测到配置文件变化: {path}')
        if load_schedule_config():
            # 时间变化后，重置执行键，允许新时间执行
            last_execution_key['key'] = None
            logger.info(f'定时配置已热更新，执行键已重置，新时间: {schedule_config["hour"]:02d}:{schedule_config["minute"]:02d}')
    
    # 初始加载配置
    if not load_schedule_config():
        return None
    
    if not schedule_config['enabled']:
        logger.info('定时执行未启用，跳过调度初始化')
        return None
    
    logger.info(f'定时执行已启用: {schedule_config["day"]} {schedule_config["hour"]:02d}:{schedule_config["minute"]:02d}')
    
    def should_execute_today():
        """检查今天是否应该执行"""
        today_weekday = datetime.now().weekday()  # 0=周一, 6=周日
        day_config = day_mapping.get(schedule_config['day'], 'everyday')
        
        if day_config == 'everyday':
            return True
        elif day_config == 'weekday':
            return today_weekday < 5  # 周一到周五
        elif day_config == 'weekend':
            return today_weekday >= 5  # 周六周日
        else:
            # 特定星期几
            return today_weekday == day_config
    
    
    def check_and_execute():
        """检查时间并执行任务"""
        # 检查是否启用
        if not schedule_config['enabled']:
            return
        
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        
        # 获取当前执行键
        current_key = get_execution_key()
        
        # 检查是否已经执行过这个时间点（防止同一时间重复执行）
        if last_execution_key['key'] == current_key:
            return
        
        # 检查时间是否匹配
        if current_hour != schedule_config['hour'] or current_minute != schedule_config['minute']:
            return
        
        # 检查今天是否应该执行
        if not should_execute_today():
            logger.debug(f'今天不在执行日期范围内: {schedule_config["day"]}')
            return
        
        # 执行任务
        logger.info(f'定时触发 CITestTask 执行: {current_key}')
        last_execution_key['key'] = current_key
        
        # 启动 CITestTask
        try:
            from ok import og
            from src.task.CITestTask import CITestTask
            
            # 查找已注册的 CITestTask 实例
            if hasattr(og, 'executor') and og.executor:
                for task in og.executor.onetime_tasks:
                    if isinstance(task, CITestTask):
                        logger.info('定时调度器启动 CITestTask...')
                        # 通过 app.start_controller 启动任务
                        if hasattr(og, 'app') and og.app and hasattr(og.app, 'start_controller'):
                            og.app.start_controller.start(task)
                        else:
                            logger.warning('StartController 未初始化，无法启动任务')
                        return
                logger.warning('未找到已注册的 CITestTask 实例')
        except Exception as e:
            logger.error(f'定时执行任务失败: {e}')
    
    # 创建定时器，每分钟检查一次
    timer = QTimer()
    timer.timeout.connect(check_and_execute)
    timer.start(60000)  # 60秒 = 1分钟
    
    # 创建文件监听器，支持配置热更新
    watcher = QFileSystemWatcher()
    watcher.addPath(str(config_path))
    watcher.fileChanged.connect(on_config_changed)
    
    logger.info('定时任务调度器已启动（支持配置热更新），每分钟检查一次')
    
    # 返回定时器和监听器引用，防止被垃圾回收
    return {'timer': timer, 'watcher': watcher}


if __name__ == '__main__':
    # Register cleanup function to run on exit
    atexit.register(cleanup_logger)

    # Smart device selection (MUST be before OK(config)!)
    smart_device_selection()
    # Apply patches before starting
    patch_logger_handler()
    # Pre-connect ADB before OK framework initialization
    pre_connect_adb()
    patch_start_controller()
    patch_adb_connect_error_handling()
    patch_task_buttons_alignment()
    # Initialize OK framework (will read devices.json)
    ok = OK(config)
    # Apply OCR logging patch AFTER OK is initialized (log handlers are set up then)
    patch_ocr_negative_box_logging()
    # Suppress harmless 'process no longer exists' errors from capture module
    patch_capture_process_not_found_logging()
    # Patch TaskButtons.stop_clicked to properly stop tasks (必须在OK初始化后，GUI组件已加载)
    patch_task_buttons_stop()
    
    # 延迟初始化定时任务调度器（需要在 ok.start() 启动 GUI 后，StartController 才可用）
    def delayed_init_scheduler():
        global _schedule_timer
        _schedule_timer = init_scheduled_task_executor()
        if _schedule_timer:
            logger = Logger.get_logger(__name__)
            logger.info('定时任务调度器延迟初始化完成')
    
    from PySide6.QtCore import QTimer
    QTimer.singleShot(1000, delayed_init_scheduler)  # 1秒后初始化
    
    ok.start()
