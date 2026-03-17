import subprocess
import zipfile
from pathlib import Path

from config import config
from ok import OK, og
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
    from ok import Logger
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


StartCard.export_logs = staticmethod(export_logs)

if __name__ == '__main__':
    # Apply patch before starting
    patch_start_controller()
    ok = OK(config)
    ok.start()
