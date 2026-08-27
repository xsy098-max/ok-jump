import os
import sys

# 与 main.py 相同的 pythonw/pyappify 环境保护
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')
if 'PATH' not in os.environ:
    os.environ['PATH'] = ';'.join([
        os.environ.get('SystemRoot', r'C:\Windows') + r'\System32',
        os.environ.get('SystemRoot', r'C:\Windows'),
    ])

from config import config
from ok import OK

"""
Web UI 入口(ok-script 2.x 新特性,参考 ok-wuthering-waves 的 main_web.py)

与桌面版共享同一套任务/配置层,便于远程查看任务状态
(如从其他设备浏览器查看 Jenkins 测试进度,无需 RDP)。

首次使用需安装 Web 依赖(桌面 requirements 未默认包含):
    pip install fastapi uvicorn

launch_mode 可选:
    "pywebview" - 本地窗口壳展示(默认)
    "browser"   - 自动打开系统浏览器
    "server"    - 纯后台服务,手动访问 http://127.0.0.1:8080
"""

if __name__ == '__main__':
    from src.compat import apply_pre_init_patches, apply_post_init_patches, \
        export_logs, smart_device_selection, pre_connect_adb, cleanup_logger
    import atexit

    atexit.register(cleanup_logger)

    # 智能设备选择必须在 OK(config) 之前
    smart_device_selection()
    apply_pre_init_patches()
    pre_connect_adb()

    # 切换 GUI 后端为 Web(不影响桌面版入口的 use_gui 配置)
    config["gui"] = {"type": "web", "launch_mode": "pywebview"}

    ok = OK(config)
    apply_post_init_patches(export_logs)
    # 注: 定时调度器依赖 Qt 事件循环,Web 模式暂不启动;
    #     需要定时执行请用桌面版入口 main.py
    ok.start()
