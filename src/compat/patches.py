# -*- coding: utf-8 -*-
"""
ok-script 2.x 运行时兼容补丁集合
=================================

所有对 ok-script 框架内部行为的 monkey-patch 集中在此模块,
每个补丁注明解决的问题与适用版本,便于框架升级时逐个核对。

目标框架版本: ok-script >= 2.0.5

升级 ok-script 2.0.5 时已退役的补丁(框架原生修复,勿再引入):
- SafeFileHandler.emit 静音补丁    → 2.0.5 已内置 closed-stream 保护
- TaskButtons.stop_clicked 修复    → 2.0.5 已实现 disable()+unpause()
- TaskButtons 按钮对齐补丁         → TaskButtons 类已合并进 TaskCard,新布局无此问题
- do_start 的 executor 争用绕行    → 2.0.5 _do_start 原生支持任务排队与暂停恢复

仍保留的补丁:
- check_device_error 跳过逻辑     (自管理任务 / Unity 模式 / skip_pos_check)
- start 任务追踪 + 模拟器预启动    (CITestTask 类任务依赖)
- adb_connect 超时日志降级         (无设备时超时是预期行为)
- OCR/capture 噪音日志过滤         (版本无关)
- DeviceManager Unity 设备注入     (框架不认识 Unity Editor 设备)
- StartTab.export_logs 重定向      (导出 ok-jump 自己的日志目录)
- Unity 触发任务线程绕行           (无截图设备时 executor 会跳过触发任务)
"""

import logging
import socket
import threading
import time

from ok import Logger, og

logger = Logger.get_logger(__name__)

# 这些任务自行管理模拟器/设备启动,不需要框架预检设备连接
SELF_MANAGED_TASKS = ['CITestTask']

# Unity Editor (com.unity-ai-custom) TCP 服务端口
UNITY_HOST = '127.0.0.1'
UNITY_PORT = 9876


# ---------------------------------------------------------------------------
# Unity 连接状态查询
# ---------------------------------------------------------------------------

def _is_unity_active():
    """检查 Unity 连接是否活跃(连接对象已创建且保持连接)"""
    try:
        if og and hasattr(og, 'my_app') and hasattr(og.my_app, '_unity_connection'):
            conn = og.my_app._unity_connection
            return conn is not None and conn.is_connected()
    except Exception:
        pass
    return False


def _is_unity_port_open():
    """检查 Unity TCP 端口是否可达(不需要已创建连接对象)"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((UNITY_HOST, UNITY_PORT))
        sock.close()
        return result == 0
    except Exception:
        return False


def _get_unity_connection():
    conn = getattr(og.my_app, '_unity_connection', None) if getattr(og, 'my_app', None) else None
    return conn


# ---------------------------------------------------------------------------
# 战斗触发器自动切换
# ---------------------------------------------------------------------------

def _auto_enable_correct_combat_task():
    """根据设备类型自动启用正确的战斗触发器:Unity 或 PC/模拟器"""
    try:
        if not og:
            return
        if not hasattr(og, 'executor') or not og.executor:
            return
        is_unity = _is_unity_port_open()
        trigger_tasks = og.executor.trigger_tasks
        logger.info(f'自动切换: is_unity={is_unity}, triggers={len(trigger_tasks)}')
        for task in trigger_tasks:
            name = getattr(task, 'name', '')
            changed = False
            if 'Unity' in name:
                if is_unity:
                    try:
                        task.enable()
                    except (AttributeError, TypeError):
                        task._enabled = True
                    changed = True
                    logger.info(f'自动启用 Unity 战斗触发器: {name}')
                else:
                    try:
                        task.disable()
                    except (AttributeError, TypeError):
                        task._enabled = False
                    changed = True
            elif 'Combat' in name:
                if not is_unity:
                    try:
                        task.enable()
                    except Exception:
                        pass
                    changed = True
                    logger.info(f'自动启用 PC/模拟器战斗触发器: {name}')
                else:
                    try:
                        task.disable()
                    except Exception:
                        pass
                    changed = True
            # 同步 GUI 开关状态
            if changed:
                try:
                    from ok.core.events import communicate
                    communicate.task.emit(task)
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f'自动切换战斗触发器失败: {e}')


# ---------------------------------------------------------------------------
# Unity 触发任务线程绕行
# ---------------------------------------------------------------------------

def _unity_trigger_loop(task):
    """
    Unity 模式下的 trigger task 循环,替代 TaskExecutor.execute()。

    Unity 纯组件模式没有截图设备,executor 的 execute 循环在
    next_frame() 返回 None 时会跳过所有触发任务(见 TaskExecutor.execute
    中 "no frame available, skip remaining trigger tasks" 分支),
    因此必须在独立线程中驱动触发逻辑。

    注:ok-script 2.x 的 TaskExecutor 已是纯 Python 类,理论上可以通过
    注入虚拟截图设备走回 executor,但线程绕行方案经过多个版本验证,
    保持不变以降低回归风险。
    """
    logger.info(f'Unity trigger 循环启动: {task.name}')
    consecutive_errors = 0
    try:
        while not og.executor.exit_event.is_set():
            try:
                if task.should_trigger():
                    # 直接调用 run() 而非 trigger(),避免与 executor 状态耦合
                    task.run()
                    consecutive_errors = 0
                    time.sleep(1.0)
                    continue
            except Exception as e:
                consecutive_errors += 1
                logger.error(f'Unity trigger 循环异常({consecutive_errors}): {e}')
                if consecutive_errors == 5:
                    _alert_unity_unhealthy(task, e)
                if consecutive_errors >= 20:
                    logger.error(f'Unity trigger 连续异常过多,退出循环: {task.name}')
                    _alert_unity_disconnected(task)
                    return
            time.sleep(0.5)
    finally:
        logger.info(f'Unity trigger 循环退出: {task.name}')


def _alert_unity_unhealthy(task, err):
    """Unity 触发循环连续异常时发出桌面通知"""
    try:
        from ok.core.notifications import alert_error
        alert_error(f'Unity 任务 {task.name} 连续异常: {err}', tray=True)
    except Exception:
        pass


def _alert_unity_disconnected(task):
    """Unity 连接疑似断开时发出桌面通知"""
    try:
        from ok.core.notifications import alert_error
        alert_error(f'Unity 连接异常,{task.name} 触发循环已停止,请检查 Unity Editor', tray=True)
    except Exception:
        pass


def _spawn_unity_thread(task, target, name):
    def _runner():
        try:
            target()
        except Exception as e:
            logger.error(f'{task.name} 执行异常: {e}')
        finally:
            try:
                task.disable()
            except (AttributeError, TypeError):
                try:
                    task._enabled = False
                except Exception:
                    pass
            try:
                from ok.core.events import communicate
                communicate.task.emit(task)
            except Exception:
                pass

    t = threading.Thread(target=_runner, name=name, daemon=True)
    t.start()
    return t


def _unity_do_start(controller, task=None, exit_after=False):
    """
    Unity 模式专用启动路径:绕过 executor,在独立线程中运行任务。
    Unity 设备就绪的唯一条件是 TCP 连接建立,无需 start_device 等待。
    """
    from ok import TriggerTask
    from ok.core.events import communicate

    communicate.starting_emulator.emit(False, None, controller.start_timeout)
    try:
        og.device_manager.do_refresh(True)
    except Exception as e:
        communicate.starting_emulator.emit(True, controller.tr(str(e)), 0)
        return False

    _auto_enable_correct_combat_task()

    if isinstance(task, int):
        task = og.executor.onetime_tasks[task]
        if exit_after and task:
            task.exit_after_task = True
            communicate.task.emit(task)

    if task:
        try:
            task.enable()
        except (AttributeError, TypeError) as e:
            logger.warning(f'Unity 模式 enable() 跳过: {e}')
            try:
                task._enabled = True
            except Exception:
                pass
        logger.info(f'Unity 模式:在独立线程中启动 {task.name}')

        if isinstance(task, TriggerTask):
            _spawn_unity_thread(task, lambda: _unity_trigger_loop(task), f'UnityTrigger-{task.name}')
        else:
            _spawn_unity_thread(task, task.run, f'UnityTask-{task.name}')
    else:
        # 没有指定具体任务,启动所有已启用的触发器任务
        executor = getattr(og, 'executor', None)
        if executor:
            for tt in executor.trigger_tasks:
                if tt._enabled:
                    logger.info(f'Unity 模式:启动触发器任务 {tt.name}')
                    _spawn_unity_thread(tt, lambda t=tt: _unity_trigger_loop(t), f'UnityTrigger-{tt.name}')

    communicate.starting_emulator.emit(True, None, 0)
    return True


# ---------------------------------------------------------------------------
# StartController 补丁
# ---------------------------------------------------------------------------

def patch_start_controller():
    """
    Patch StartController:
    1. check_device_error 跳过自管理任务(CITestTask)/ Unity 模式 / skip_pos_check
    2. start() 追踪当前任务,自管理任务先预启动模拟器
    3. do_start() 在 Unity 模式下走线程绕行;常规路径完全复用框架 2.x 原生逻辑
       (2.x 已原生支持暂停恢复与任务排队,旧的 executor 争用绕行已移除)

    补丁幂等:重复调用安全;原始实现挂在 __ok_jump_orig__ 上,便于测试替换。
    """
    from ok.core.start_controller import StartController

    if getattr(StartController.check_device_error, '__ok_jump_patch__', False):
        return

    original_check_device_error = StartController.check_device_error

    def patched_check_device_error(self):
        # 自管理任务(如 CITestTask)自己管理设备,跳过设备预检
        current_task = getattr(self, 'current_task', None)
        if current_task and current_task.__class__.__name__ in SELF_MANAGED_TASKS:
            logger.info(f'Skipping device check for self-managed task: {current_task.__class__.__name__}')
            return None

        # Unity 纯组件模式无需截图设备
        if _is_unity_active():
            logger.info('Unity connection active, skipping device error check')
            return None

        # 后台模式守卫:skip_pos_check 开启且窗口在屏幕外(伪最小化)时,
        # 直接放行而不调用原始检查——2.0.5 的 check_device_error 会把
        # 位置无效的窗口自动搬回屏幕中央(resize_window),破坏伪最小化后台模式
        if (og.config.get('windows') or {}).get('skip_pos_check', False):
            try:
                dm = getattr(og, 'device_manager', None)
                capture_method = getattr(dm, 'capture_method', None)
                hwnd_window = getattr(capture_method, 'hwnd_window', None)
                if hwnd_window is not None and not getattr(hwnd_window, 'pos_valid', True):
                    logger.info('后台模式: 窗口在屏幕外(伪最小化), 跳过设备检查与自动回正')
                    return None
            except Exception:
                pass

        result = patched_check_device_error.__ok_jump_orig__(self)

        # 后台模式:允许最小化/屏幕外窗口
        if result and 'minimized or out of screen' in str(result).lower():
            if (og.config.get('windows') or {}).get('skip_pos_check', False):
                logger.info('skip_pos_check is enabled, allowing minimized/off-screen window')
                return None

        return result

    patched_check_device_error.__ok_jump_patch__ = True
    patched_check_device_error.__ok_jump_orig__ = original_check_device_error
    StartController.check_device_error = patched_check_device_error

    original_do_start = StartController.do_start

    def patched_do_start(self, task=None, exit_after=False):
        if _is_unity_active():
            return _unity_do_start(self, task, exit_after)
        # 常规路径:框架 2.x do_start 原生处理暂停恢复与排队,无需干预
        return patched_do_start.__ok_jump_orig__(self, task, exit_after)

    patched_do_start.__ok_jump_patch__ = True
    patched_do_start.__ok_jump_orig__ = original_do_start
    StartController.do_start = patched_do_start

    original_start = StartController.start

    def patched_start(self, task=None, exit_after=False):
        if task is not None and not isinstance(task, int):
            self.current_task = task
            if task.__class__.__name__ in SELF_MANAGED_TASKS:
                logger.info(f'Self-managed task detected: {task.__class__.__name__}, '
                            f'device check will be skipped')
                _pre_start_emulator_for_task(task)
        return patched_start.__ok_jump_orig__(self, task, exit_after)

    patched_start.__ok_jump_patch__ = True
    patched_start.__ok_jump_orig__ = original_start
    StartController.start = patched_start

    logger.info('StartController patched: self-managed tasks + skip_pos_check + Unity bypass')


# ---------------------------------------------------------------------------
# 模拟器预启动(自管理任务)
# ---------------------------------------------------------------------------

def _pre_start_emulator_for_task(task):
    """
    在任务启动前启动模拟器并连接 ADB。

    对于 CITestTask 这样的任务,需要先启动模拟器,
    TaskExecutor 才能获取截图。
    """
    import json
    from pathlib import Path
    from adbutils import adb

    pre_logger = Logger.get_logger(__name__)
    pre_logger.info('预启动模拟器流程开始...')

    try:
        config_path = Path('configs/CITestTask.json')
        if not config_path.exists():
            pre_logger.warning('未找到 CITestTask.json 配置文件')
            return

        with open(config_path, 'r', encoding='utf-8') as f:
            ci_config = json.load(f)

        emulator_path = ci_config.get('模拟器路径', '')
        adb_port = ci_config.get('ADB端口', 5554)
        instance_index = ci_config.get('模拟器实例索引', 0)

        pre_logger.info(f'模拟器路径: {emulator_path}, ADB端口: {adb_port}, 实例索引: {instance_index}')

        if not emulator_path:
            pre_logger.warning('未配置模拟器路径')
            return

        import subprocess
        emulator_dir = Path(emulator_path).parent
        ldconsole_path = emulator_dir / 'ldconsole.exe'

        # 检查模拟器是否已运行
        try:
            adb.connect(f'127.0.0.1:{adb_port}', timeout=5)
            devices = adb.device_list()
            for device in devices:
                if f'emulator-{adb_port}' in device.serial or f'127.0.0.1:{adb_port}' in device.serial:
                    pre_logger.info(f'模拟器已运行: {device.serial}')
                    return  # 模拟器已在运行
        except Exception as e:
            pre_logger.debug(f'ADB检测失败: {e}')

        # 启动模拟器
        if ldconsole_path.exists():
            cmd = [str(ldconsole_path), 'launch', '--index', str(instance_index)]
            pre_logger.info(f'执行命令: {" ".join(cmd)}')
            subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
        else:
            pre_logger.warning(f'ldconsole.exe 不存在: {ldconsole_path}')

        # 等待模拟器启动并连接 ADB
        max_wait = 60
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                adb.connect(f'127.0.0.1:{adb_port}', timeout=5)
                devices = adb.device_list()
                for device in devices:
                    if f'emulator-{adb_port}' in device.serial or f'127.0.0.1:{adb_port}' in device.serial:
                        pre_logger.info(f'模拟器启动成功: {device.serial}')
                        return
            except Exception:
                pass
            time.sleep(2)

        pre_logger.warning(f'模拟器启动超时 ({max_wait}秒)')

    except Exception as e:
        pre_logger.error(f'预启动模拟器失败: {e}')


# ---------------------------------------------------------------------------
# DeviceManager 补丁(Unity 设备)
# ---------------------------------------------------------------------------

def patch_device_manager_for_unity():
    """
    Patch DeviceManager 支持 Unity 工程连接:

    - do_refresh 后探测 Unity TCP 端口,可达则注入 "unity" 虚拟设备
    - do_start 时若选择 unity 设备,建立 UnityConnection 并存入
      og.my_app._unity_connection,输入直接走 TCP 命令而非 Interaction
    """
    from ok.device.DeviceManager import DeviceManager

    if getattr(DeviceManager.do_refresh, '__ok_jump_patch__', False):
        return

    original_do_refresh = DeviceManager.do_refresh

    def patched_do_refresh(self, current=False):
        # 先执行原始刷新
        original_do_refresh(self, current)

        # 检测 Unity 连接并添加到设备列表
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((UNITY_HOST, UNITY_PORT))
            sock.close()

            if result == 0:
                self.device_dict['unity'] = {
                    "address": f"{UNITY_HOST}:{UNITY_PORT}",
                    "imei": "unity",
                    "device": "unity",
                    "model": "Unity Editor",
                    "nick": "Unity Editor",
                    "width": 1920,
                    "height": 1080,
                    "hwnd": "Unity Editor",
                    "capture": "windows",
                    "connected": True,
                    "resolution": "1920x1080",
                }
            else:
                self.device_dict.pop('unity', None)
        except Exception:
            self.device_dict.pop('unity', None)

        # 设备列表更新后,自动切换战斗触发器
        try:
            _auto_enable_correct_combat_task()
        except Exception as e:
            logger.debug(f'设备刷新时自动切换触发器异常: {e}')

    patched_do_refresh.__ok_jump_patch__ = True
    DeviceManager.do_refresh = patched_do_refresh

    original_do_start = DeviceManager.do_start

    def patched_do_start(self, notify=True):
        # 检查是否选择了 Unity 设备
        preferred = self.config.get('preferred', '')
        if preferred and isinstance(preferred, str) and 'unity' in preferred:
            logger.info('Unity 工程连接模式启动')

            # 初始化 UnityConnection
            from src.utils.UnityConnection import UnityConnection
            conn = UnityConnection()
            if conn.connect():
                if og and hasattr(og, 'my_app') and og.my_app:
                    og.my_app._unity_connection = conn
                    logger.info('Unity 连接已建立并存储到全局对象')
                else:
                    logger.warning('全局对象未就绪,Unity 连接未存储')

                logger.info('Unity 工程连接已就绪(纯组件模式)')
                return
            else:
                logger.error('Unity 连接失败,回退到标准模式')
                _alert_unity_disconnected(type('T', (), {'name': 'Unity 连接'})())

        # 非 Unity 模式或回退,走原始逻辑
        original_do_start(self, notify)

    patched_do_start.__ok_jump_patch__ = True
    DeviceManager.do_start = patched_do_start
    logger.info('DeviceManager patched: Unity 工程连接支持')


# ---------------------------------------------------------------------------
# ADB 连接日志降级
# ---------------------------------------------------------------------------

def patch_adb_connect_error_handling():
    """
    Patch DeviceManager.adb_connect 降低预期失败的日志级别。

    无设备连接时 ADB 超时是预期行为,不应以 ERROR 级别刷屏;
    同时保留框架对 AdbError 的 try_kill_adb 自愈逻辑。
    """
    from ok.device.DeviceManager import DeviceManager
    from adbutils import AdbError, AdbTimeout

    if getattr(DeviceManager.adb_connect, '__ok_jump_patch__', False):
        return

    original_adb_connect = DeviceManager.adb_connect

    def patched_adb_connect(self, addr, try_connect=True):
        try:
            for device in self.adb.list():
                if self.exit_event.is_set():
                    logger.debug("adb_connect exit_event is set")
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
                return self.adb_connect(addr, try_connect=False)
            else:
                logger.debug(f'adb_connect {addr} not in device list')
        except AdbTimeout:
            # 超时是预期行为(该地址没有设备)- DEBUG 级别
            logger.debug(f"adb connect timeout (no device at {addr})")
        except AdbError as e:
            # 其他 ADB 错误 - WARNING,但保留框架的 adb 自愈
            logger.warning(f"adb connect error {addr}: {e}")
            try:
                self.try_kill_adb(e)
            except Exception:
                pass
        except Exception as e:
            # 未预期错误 - WARNING(原框架为 ERROR,但多为环境噪音)
            logger.warning(f"adb connect unexpected error {addr}: {e}")

    patched_adb_connect.__ok_jump_patch__ = True
    DeviceManager.adb_connect = patched_adb_connect
    logger.info('DeviceManager.adb_connect patched: timeout errors suppressed')


# ---------------------------------------------------------------------------
# 日志噪音过滤
# ---------------------------------------------------------------------------

class _MessageFilter(logging.Filter):
    """按消息子串过滤日志记录"""

    def __init__(self, keywords):
        super().__init__()
        self.keywords = keywords

    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return not any(k in msg for k in self.keywords)


def _install_log_filter(log_filter, tag):
    installed = False
    for handler in logging.root.handlers:
        if not any(isinstance(f, type(log_filter)) for f in handler.filters):
            handler.addFilter(log_filter)
            installed = True
    ok_logger = logging.getLogger('ok')
    for handler in ok_logger.handlers:
        if not any(isinstance(f, type(log_filter)) for f in handler.filters):
            handler.addFilter(log_filter)
            installed = True
    if installed:
        logger.info(f'{tag} suppressed')


def patch_ocr_negative_box_logging():
    """抑制 PaddleOCR 的 negative box 噪音错误(旋转框负坐标,不影响功能)"""
    _install_log_filter(_MessageFilter(['negative box']), 'OCR negative box error logging')


def patch_capture_process_not_found_logging():
    """抑制截图模块的 process no longer exists 噪音错误(模拟器关闭时的预期行为)"""
    _install_log_filter(
        _MessageFilter(['process no longer exists', 'NoSuchProcess']),
        'Capture process not found error logging')


# ---------------------------------------------------------------------------
# 日志导出重定向
# ---------------------------------------------------------------------------

def patch_export_logs(export_logs_impl):
    """
    重定向 GUI 的"导出日志"按钮到 ok-jump 自己的实现
    (打包 ok-jump 的 logs 目录而不是框架默认路径)。

    ok-script 2.x 中该方法位于 StartTab(1.x 在 StartCard)。
    """
    try:
        from ok.ui.qt.start import StartTab
        StartTab.export_logs = staticmethod(export_logs_impl)
        logger.info('StartTab.export_logs patched')
    except ImportError:
        logger.warning('StartTab not found, export_logs patch skipped')


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------

def apply_pre_init_patches():
    """OK(config) 之前应用的补丁"""
    patch_start_controller()
    patch_adb_connect_error_handling()
    patch_device_manager_for_unity()


def apply_post_init_patches(export_logs_impl):
    """OK(config) 之后应用的补丁(需要日志 handler / GUI 组件已就绪)"""
    patch_ocr_negative_box_logging()
    patch_capture_process_not_found_logging()
    patch_export_logs(export_logs_impl)
