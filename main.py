import atexit
import json
import subprocess
import sys
import time
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


def patch_start_controller():
    """
    Patch StartController to allow minimized/off-screen window for background mode
    and skip device checks for CITestTask (which handles its own deployment)
    """
    from ok.gui.StartController import StartController
    logger = Logger.get_logger(__name__)
    
    original_check_device_error = StartController.check_device_error
    original_do_start = StartController.do_start
    
    def patched_check_device_error(self):
        # Get the original result
        result = original_check_device_error(self)
        
        # If the error is about minimized/off-screen window, check if we should skip
        if result and 'minimized or out of screen' in result.lower():
            if self.config.get('windows', {}).get('skip_pos_check', False):
                logger.info('skip_pos_check is enabled, allowing minimized/off-screen window')
                return None  # Allow the task to start
        
        return result
    
    def patched_do_start(self, task=None, exit_after=False):
        """
        Patched do_start that skips device checks for CITestTask.
        CITestTask handles its own deployment flow (download -> emulator -> install -> game).
        """
        from ok.gui.Communicate import communicate
        from src.task.CITestTask import CITestTask
            
        # Determine if this is a CITestTask
        # task can be: None, int (index), or the task object itself
        is_ci_task = False
        task_obj = None
            
        if isinstance(task, int):
            # Task is specified by index
            if hasattr(og, 'executor') and og.executor:
                if task < len(og.executor.onetime_tasks):
                    task_obj = og.executor.onetime_tasks[task]
                    if isinstance(task_obj, CITestTask):
                        is_ci_task = True
                        logger.info(f'CITestTask detected by index {task}')
        elif task is not None:
            # Task is the object itself (from GUI click)
            if isinstance(task, CITestTask):
                is_ci_task = True
                task_obj = task
                logger.info(f'CITestTask detected by object: {task.name}')
            
        if is_ci_task:
            # For CITestTask, skip all device checks and run directly in a thread
            # We need TaskExecutor to run for frame capture support
            logger.info('CITestTask: bypassing device checks, running directly')
            communicate.starting_emulator.emit(True, None, 0)
            
            # Store exit_after flag on the task
            if exit_after:
                task_obj.exit_after_task = True
            
            # Start TaskExecutor for frame capture support
            # This is required for next_frame() to work in sub-tasks
            if hasattr(og, 'executor') and og.executor is not None:
                try:
                    og.executor.start()
                    logger.info('TaskExecutor started for frame capture support')
                except Exception as e:
                    logger.warning(f'TaskExecutor start failed (may already be running): {e}')
            
            # Run CITestTask in a separate thread
            import threading
            
            def run_ci_task():
                try:
                    logger.info(f'Starting CITestTask in dedicated thread')
                    communicate.task.emit(task_obj)
                    task_obj.running = True
                    task_obj.start_time = time.time()
                    result = task_obj.run()
                    logger.info(f'CITestTask completed with result: {result}')
                except Exception as e:
                    logger.error(f'CITestTask failed with exception: {e}', exc_info=True)
                finally:
                    task_obj.running = False
                    communicate.task_done.emit(task_obj)
                    communicate.task.emit(None)
                    
                    if task_obj.exit_after_task or task_obj.config.get('Exit After Task'):
                        logger.info('CITestTask finished, exiting app')
                        from ok.gui.util.Alert import alert_info
                        alert_info('Successfully Executed Task, Exiting App!')
                        time.sleep(3)
                        communicate.quit.emit()
            
            ci_thread = threading.Thread(target=run_ci_task, name='CITestTask', daemon=True)
            ci_thread.start()
            return
            
            
        # For other tasks, use the original logic
        original_do_start(self, task, exit_after)
    
    StartController.check_device_error = patched_check_device_error
    StartController.do_start = patched_do_start
    logger.info('StartController patched: skip_pos_check support and CITestTask bypass enabled')


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


def patch_task_executor_frame_logging():
    """
    Suppress harmless 'got no frame' error logs from TaskExecutor.
    This error occurs when the capture system temporarily cannot get a frame,
    which is expected behavior during window transitions, loading screens,
    or when the game window is not yet ready. The task will retry automatically.
    """
    import logging
    logger = Logger.get_logger(__name__)

    class TaskExecutorFrameFilter(logging.Filter):
        def filter(self, record):
            # Suppress 'got no frame' messages from TaskExecutor
            msg = record.getMessage()
            if 'got no frame' in msg.lower():
                # Downgrade to DEBUG level by suppressing the ERROR log
                return False
            return True

    # Add filter to the root logger's handlers (catches all loggers)
    for handler in logging.root.handlers:
        handler.addFilter(TaskExecutorFrameFilter())
    
    # Also add to ok logger's handlers
    ok_logger = logging.getLogger('ok')
    for handler in ok_logger.handlers:
        handler.addFilter(TaskExecutorFrameFilter())
    
    logger.info("TaskExecutor 'got no frame' error logging suppressed")


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

if __name__ == '__main__':
    # Register cleanup function to run on exit
    atexit.register(cleanup_logger)

    # Smart device selection (MUST be before OK(config)!)
    smart_device_selection()
    # Apply patches before starting
    patch_logger_handler()
    patch_start_controller()
    patch_adb_connect_error_handling()
    patch_task_buttons_alignment()
    # Initialize OK framework (will read devices.json)
    ok = OK(config)
    # Apply OCR logging patch AFTER OK is initialized (log handlers are set up then)
    patch_ocr_negative_box_logging()
    # Apply TaskExecutor frame logging patch
    patch_task_executor_frame_logging()
    ok.start()
