"""
日志监控标签页

提供 GUI 中的实时日志查看功能
"""

import logging

from PySide6.QtWidgets import QWidget, QVBoxLayout
from qfluentwidgets import FluentIcon, NavigationItemPosition

from src.gui.log_panel import LogPanel


class LogTab(QWidget):
    """
    日志监控标签页
    
    用于在 ok-script 框架的 GUI 中显示实时日志
    """
    
    # 必须属性（ok-script 框架要求）
    name = "日志"
    icon = FluentIcon.HISTORY
    position = NavigationItemPosition.BOTTOM
    add_after_default_tabs = True
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.executor = None  # 会被框架设置
        
        # 设置 objectName（qfluentwidgets 要求）
        self.setObjectName("LogTab")
        
        self._init_ui()
        self._setup_logger()
    
    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 添加日志面板
        self.log_panel = LogPanel(self, max_lines=2000)
        layout.addWidget(self.log_panel)
    
    def _setup_logger(self):
        """设置日志处理器"""
        # 获取 root logger 和所有子 logger
        handler = self.log_panel.get_handler()
        
        # 添加到 root logger
        root_logger = logging.getLogger()
        
        # 避免重复添加
        from src.gui.log_panel import GUILogHandler
        for h in root_logger.handlers:
            if isinstance(h, GUILogHandler):
                return
        
        root_logger.addHandler(handler)
        
        # 确保 level 足够低以捕获所有日志
        if root_logger.level > logging.DEBUG:
            root_logger.setLevel(logging.DEBUG)
    
    def get_log_panel(self):
        """获取日志面板实例"""
        return self.log_panel
