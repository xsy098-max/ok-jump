import os

from qfluentwidgets import FluentIcon
from ok.util.config import ConfigOption

project_path = os.path.dirname(os.path.abspath(__file__))


def get_assets_path(*paths):
    return os.path.join(project_path, 'assets', *paths)


def get_config_path(*paths):
    return os.path.join(project_path, 'configs', *paths)


def calculate_pc_exe_path(install_path):
    if install_path:
        return os.path.join(install_path, 'Client-Win64-Shipping.exe')
    return None


key_config_option = ConfigOption(
    '游戏热键配置',
    {
        '普通攻击': 'J',
        '技能1': 'K',
        '技能2': 'L',
        '大招': 'U',
    },
    config_description={
        '普通攻击': '普通攻击按键',
        '技能1': '技能1按键',
        '技能2': '技能2按键',
        '大招': '大招按键',
    },
    icon=FluentIcon.GAME
)

basic_config_option = ConfigOption(
    '基本设置',
    {
        '关闭时最小化到系统托盘': False,
        '后台模式': True,
        '最小化时伪最小化': True,
        '后台时静音游戏': False,
        '自动调整游戏窗口大小': False,
        '游戏退出时关闭程序': False,
        '游戏文本语言': '简体中文',
        '触发间隔': 1,
        '启动/停止快捷键': 'F9',
    },
    config_type={
        '启动/停止快捷键': {'type': "drop_down", 'options': ['无', 'F9', 'F10', 'F11', 'F12']},
        '游戏文本语言': {'type': "drop_down", 'options': ['简体中文', '繁体中文']},
    },
    config_description={
        '后台模式': '启用后游戏窗口可最小化或被遮挡时继续运行',
        '最小化时伪最小化': '窗口最小化时自动移到屏幕外，支持后台截图',
        '后台时静音游戏': '游戏窗口在后台时自动静音',
        '游戏文本语言': '游戏内显示的语言，OCR识别将自动转换匹配关键词',
        '触发间隔': '触发任务之间的延迟(毫秒)，增加延迟可降低CPU/GPU使用率',
        '启动/停止快捷键': '启动/停止快捷键',
    },
    icon=FluentIcon.SETTING
)

config = {
    'debug': False,
    'use_gui': True,
    'config_folder': 'configs',
    'gui_icon': 'icons/icon.png',
    'gui_title': '漫画群星：大集结 - 自动化工具',
    'version': '1.4.38',
    
    # 自定义全局对象（用于 YOLO 检测等功能）
    'my_app': ['src.globals', 'Globals'],
    
    'global_configs': [basic_config_option, key_config_option],
    
    'ocr': {
        'lib': 'onnxocr',
        'params': {
            'use_openvino': True,
            'use_npu': False
        }
    },
    
    'template_matching': {
        'coco_feature_json': get_assets_path('coco_detection.json'),
        'default_threshold': 0.8,
    },
    
    'windows': {
        'title': '漫画群星：大集结',
        'exe': '漫画群星：大集结.exe',
        'hwnd_class': 'UnityWndClass',
        'interaction': 'PyDirect',  # Unity游戏需要PyDirect（DirectInput）
        'capture_method': ['WGC', 'BitBlt_RenderFull', 'BitBlt'],
        'skip_pos_check': True,  # 允许最小化/屏幕外窗口，支持后台模式
    },
    
    'adb': {
        'enabled': True,
        'packages': 'com.lmd.xproject.dev',
    },
    
    'supported_resolution': {
        'ratio': '16:9',
        'min_size': (1280, 720),
        'resize_to': [(2560, 1440), (1920, 1080), (1600, 900), (1280, 720)],
    },
    
    'window_size': {
        'width': 900,
        'height': 600,
        'min_width': 900,
        'min_height': 600,
    },
    
    'log_file': 'logs/ok-jump.log',
    'error_log_file': 'logs/ok-jump_error.log',
    
    'screenshots_folder': "screenshots",
    
    'onetime_tasks': [
        # ['src.task.MainWindowTask', 'MainWindowTask'],  # 已隐藏 - 不在GUI中显示
        ['src.task.CITestTask', 'CITestTask'],  # CI自动化测试任务（置顶）
        ['src.task.TestAllInOneTask', 'TestAllInOneTask'],  # 测试一条龙任务
        ['src.task.AutoLoginTask', 'AutoLoginTask'],
        ['src.task.AutoTutorialTask', 'AutoTutorialTask'],
        ['src.task.AutoMatchTask', 'AutoMatchTask'],
        ['src.task.DailyTask', 'DailyTask'],
    ],
    
    'trigger_tasks': [
        ['src.task.AutoCombatTask', 'AutoCombatTask'],
    ],
    
    'custom_tabs': [
        ['src.gui.log_tab', 'LogTab'],  # 实时日志监控面板
    ],
    
    'scene': ['src.scene.JumpScene', 'JumpScene'],
}
