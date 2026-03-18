import json
import subprocess
import zipfile
from pathlib import Path

from config import config
from ok import OK, og, Logger
from ok.gui.start.StartCard import StartCard


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
    """
    from ok.gui.StartController import StartController
    logger = Logger.get_logger(__name__)
    
    original_check_device_error = StartController.check_device_error
    
    def patched_check_device_error(self):
        # Get the original result
        result = original_check_device_error(self)
        
        # If the error is about minimized/off-screen window, check if we should skip
        if result and 'minimized or out of screen' in result.lower():
            if self.config.get('windows', {}).get('skip_pos_check', False):
                logger.info('skip_pos_check is enabled, allowing minimized/off-screen window')
                return None  # Allow the task to start
        
        return result
    
    StartController.check_device_error = patched_check_device_error
    logger.info('StartController patched: skip_pos_check support enabled')


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
    # Smart device selection (MUST be before OK(config)!)
    smart_device_selection()
    # Apply patches before starting
    patch_start_controller()
    patch_task_buttons_alignment()
    # Initialize OK framework (will read devices.json)
    ok = OK(config)
    ok.start()
