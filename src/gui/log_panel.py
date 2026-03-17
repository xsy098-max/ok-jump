"""
实时日志监控面板

提供 GUI 中的实时日志查看功能
"""

import logging
from datetime import datetime
from collections import deque

from PySide6.QtCore import QObject, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QPushButton, QLabel, QFrame
)
from PySide6.QtGui import QTextCharFormat, QColor, QFont, QTextCursor

try:
    from qfluentwidgets import (
        CardWidget, PushButton, ToggleButton, ComboBox,
        TransparentPushButton, FluentIcon, LineEdit,
        InfoBar, InfoBarPosition
    )
    HAS_FLUENT = True
except ImportError:
    HAS_FLUENT = False


class LogSignalEmitter(QObject):
    """日志信号发射器 - 用于线程安全的日志传递"""
    log_received = Signal(str, str, str)  # level, message, timestamp


class GUILogHandler(logging.Handler):
    """
    GUI 日志处理器
    
    捕获日志并发送到 GUI 显示
    """
    
    def __init__(self, emitter: LogSignalEmitter):
        super().__init__()
        self.emitter = emitter
        self.setLevel(logging.DEBUG)
        
        # 日志格式
        self.setFormatter(logging.Formatter('%(message)s'))
    
    def emit(self, record):
        try:
            msg = self.format(record)
            timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S.%f')[:-3]
            self.emitter.log_received.emit(record.levelname, msg, timestamp)
        except Exception:
            self.handleError(record)


class LogPanel(QWidget):
    """
    实时日志监控面板
    
    功能：
    - 实时显示日志
    - 按级别过滤
    - 关键词搜索
    - 自动滚动
    - 清空日志
    - 暂停/恢复
    """
    
    # 日志级别颜色
    LEVEL_COLORS = {
        'DEBUG': '#808080',     # 灰色
        'INFO': '#00AA00',      # 绿色
        'WARNING': '#FFA500',   # 橙色
        'ERROR': '#FF0000',     # 红色
        'CRITICAL': '#FF00FF',  # 紫色
    }
    
    # 特殊标记颜色
    MARKER_COLORS = {
        '🔍': '#4A90D9',  # 蓝色 - 检测开始
        '✅': '#00AA00',  # 绿色 - 成功
        '❌': '#FF0000',  # 红色 - 失败
        '💀': '#8B0000',  # 深红 - 死亡
        '⚔️': '#FF6600',  # 橙色 - 战斗
        '👤': '#4169E1',  # 皇家蓝 - 自己
        '🟢': '#32CD32',  # 绿色 - 友方
        '🔴': '#DC143C',  # 红色 - 敌军
        '📊': '#9370DB',  # 紫色 - 统计
        '📷': '#20B2AA',  # 青色 - 帧信息
        '⚠️': '#FFD700',  # 金色 - 警告
    }
    
    def __init__(self, parent=None, max_lines=1000):
        super().__init__(parent)
        
        self.max_lines = max_lines
        self.log_buffer = deque(maxlen=max_lines)
        self.is_paused = False
        self.auto_scroll = True
        self.filter_level = 'DEBUG'
        self.filter_keyword = ''
        
        # 创建信号发射器和处理器
        self.emitter = LogSignalEmitter()
        self.handler = GUILogHandler(self.emitter)
        
        # 连接信号
        self.emitter.log_received.connect(self._on_log_received)
        
        self._init_ui()
        self._setup_styles()
    
    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # ===== 标题栏 =====
        title_layout = QHBoxLayout()
        
        title_label = QLabel("📋 实时日志监控")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        title_layout.addWidget(title_label)
        
        title_layout.addStretch()
        
        # 日志计数
        self.count_label = QLabel("0 条日志")
        self.count_label.setStyleSheet("color: #666;")
        title_layout.addWidget(self.count_label)
        
        layout.addLayout(title_layout)
        
        # ===== 工具栏 =====
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(8)
        
        # 级别过滤
        level_label = QLabel("级别:")
        toolbar_layout.addWidget(level_label)
        
        if HAS_FLUENT:
            self.level_combo = ComboBox()
        else:
            from PySide6.QtWidgets import QComboBox
            self.level_combo = QComboBox()
        
        self.level_combo.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR'])
        self.level_combo.setCurrentText('DEBUG')
        self.level_combo.currentTextChanged.connect(self._on_level_changed)
        self.level_combo.setFixedWidth(100)
        toolbar_layout.addWidget(self.level_combo)
        
        # 关键词搜索
        search_label = QLabel("搜索:")
        toolbar_layout.addWidget(search_label)
        
        if HAS_FLUENT:
            self.search_input = LineEdit()
            self.search_input.setPlaceholderText("输入关键词过滤...")
        else:
            from PySide6.QtWidgets import QLineEdit
            self.search_input = QLineEdit()
            self.search_input.setPlaceholderText("输入关键词过滤...")
        
        self.search_input.setFixedWidth(150)
        self.search_input.textChanged.connect(self._on_search_changed)
        toolbar_layout.addWidget(self.search_input)
        
        toolbar_layout.addStretch()
        
        # 控制按钮
        if HAS_FLUENT:
            self.pause_btn = ToggleButton("暂停")
            self.pause_btn.toggled.connect(self._on_pause_toggled)
            toolbar_layout.addWidget(self.pause_btn)
            
            self.clear_btn = PushButton("清空")
            self.clear_btn.clicked.connect(self._clear_logs)
            toolbar_layout.addWidget(self.clear_btn)
            
            self.scroll_btn = ToggleButton("自动滚动")
            self.scroll_btn.setChecked(True)
            self.scroll_btn.toggled.connect(self._on_scroll_toggled)
            toolbar_layout.addWidget(self.scroll_btn)
        else:
            self.pause_btn = QPushButton("暂停")
            self.pause_btn.setCheckable(True)
            self.pause_btn.toggled.connect(self._on_pause_toggled)
            toolbar_layout.addWidget(self.pause_btn)
            
            self.clear_btn = QPushButton("清空")
            self.clear_btn.clicked.connect(self._clear_logs)
            toolbar_layout.addWidget(self.clear_btn)
            
            self.scroll_btn = QPushButton("自动滚动")
            self.scroll_btn.setCheckable(True)
            self.scroll_btn.setChecked(True)
            self.scroll_btn.toggled.connect(self._on_scroll_toggled)
            toolbar_layout.addWidget(self.scroll_btn)
        
        layout.addLayout(toolbar_layout)
        
        # ===== 日志显示区域 =====
        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setMaximumBlockCount(self.max_lines)
        self.log_display.setLineWrapMode(QPlainTextEdit.NoWrap)
        
        # 设置等宽字体
        font = QFont("Consolas", 9)
        if not font.exactMatch():
            font = QFont("Courier New", 9)
        self.log_display.setFont(font)
        
        layout.addWidget(self.log_display)
        
        # ===== 状态栏 =====
        status_layout = QHBoxLayout()
        
        self.status_label = QLabel("✅ 日志监控已启动")
        self.status_label.setStyleSheet("color: #00AA00;")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        
        self.fps_label = QLabel("")
        self.fps_label.setStyleSheet("color: #666;")
        status_layout.addWidget(self.fps_label)
        
        layout.addLayout(status_layout)
    
    def _setup_styles(self):
        """设置样式"""
        self.log_display.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
                padding: 8px;
            }
        """)
    
    def get_handler(self):
        """获取日志处理器，用于注册到 logger"""
        return self.handler
    
    @Slot(str, str, str)
    def _on_log_received(self, level: str, message: str, timestamp: str):
        """处理接收到的日志"""
        # 存储到缓冲区
        self.log_buffer.append((level, message, timestamp))
        
        # 如果暂停，不显示
        if self.is_paused:
            return
        
        # 过滤检查
        if not self._should_display(level, message):
            return
        
        # 格式化并显示
        self._append_log(level, message, timestamp)
        
        # 更新计数
        self.count_label.setText(f"{len(self.log_buffer)} 条日志")
    
    def _should_display(self, level: str, message: str) -> bool:
        """检查是否应该显示该日志"""
        # 级别过滤
        level_order = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if level_order.index(level) < level_order.index(self.filter_level):
            return False
        
        # 关键词过滤
        if self.filter_keyword and self.filter_keyword.lower() not in message.lower():
            return False
        
        return True
    
    def _append_log(self, level: str, message: str, timestamp: str):
        """添加日志到显示区域"""
        # 获取颜色
        color = self.LEVEL_COLORS.get(level, '#D4D4D4')
        
        # 检查特殊标记
        for marker, marker_color in self.MARKER_COLORS.items():
            if marker in message:
                color = marker_color
                break
        
        # 格式化文本
        formatted = f"[{timestamp}] [{level:7}] {message}"
        
        # 添加带颜色的文本
        cursor = self.log_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        
        cursor.insertText(formatted + "\n", fmt)
        
        # 自动滚动
        if self.auto_scroll:
            self.log_display.verticalScrollBar().setValue(
                self.log_display.verticalScrollBar().maximum()
            )
    
    def _on_level_changed(self, level: str):
        """级别过滤变更"""
        self.filter_level = level
        self._refresh_display()
    
    def _on_search_changed(self, keyword: str):
        """搜索关键词变更"""
        self.filter_keyword = keyword
        self._refresh_display()
    
    def _on_pause_toggled(self, paused: bool):
        """暂停/恢复"""
        self.is_paused = paused
        if paused:
            self.status_label.setText("⏸️ 日志已暂停")
            self.status_label.setStyleSheet("color: #FFA500;")
        else:
            self.status_label.setText("✅ 日志监控已启动")
            self.status_label.setStyleSheet("color: #00AA00;")
            self._refresh_display()
    
    def _on_scroll_toggled(self, enabled: bool):
        """自动滚动开关"""
        self.auto_scroll = enabled
    
    def _clear_logs(self):
        """清空日志"""
        self.log_buffer.clear()
        self.log_display.clear()
        self.count_label.setText("0 条日志")
    
    def _refresh_display(self):
        """刷新显示（应用过滤器）"""
        self.log_display.clear()
        
        for level, message, timestamp in self.log_buffer:
            if self._should_display(level, message):
                self._append_log(level, message, timestamp)


# ===== 全局日志面板实例 =====
_log_panel_instance = None


def get_log_panel() -> LogPanel:
    """获取全局日志面板实例"""
    global _log_panel_instance
    if _log_panel_instance is None:
        _log_panel_instance = LogPanel()
    return _log_panel_instance


def setup_log_panel_handler(logger_name: str = None):
    """
    设置日志面板处理器
    
    Args:
        logger_name: 要监听的 logger 名称，None 表示 root logger
    """
    panel = get_log_panel()
    handler = panel.get_handler()
    
    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()
    
    # 避免重复添加
    for h in logger.handlers:
        if isinstance(h, GUILogHandler):
            return panel
    
    logger.addHandler(handler)
    return panel
