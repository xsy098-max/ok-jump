import sys

from config import config
from ok import OK

if __name__ == '__main__':
    from src.compat.patches import enforce_ok_script_compat
    enforce_ok_script_compat()

    config['debug'] = True
    config['use_gui'] = False
    
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is not None:
        QApplication.instance().quit()
    
    ok = OK(config)
    ok.start()
