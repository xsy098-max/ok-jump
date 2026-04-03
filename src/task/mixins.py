"""
任务混入类模块

提供所有任务共享的通用功能，消除 BaseJumpTask 与 BaseJumpTriggerTask 之间的代码重复
"""

from src.constants.features import Features
from src.utils.ResolutionAdapter import resolution_adapter
from src.utils.BackgroundManager import background_manager
from src.utils.BackgroundInputHelper import background_input
from src.utils.PseudoMinimizeHelper import pseudo_minimize_helper
import time


class JumpTaskMixin:
    """
    任务混入类 - 提供所有任务共享的通用功能

    此类通过混入模式(Mixin)为 BaseTask 和 TriggerTask 提供共同的功能方法，
    避免 BaseJumpTask 和 BaseJumpTriggerTask 之间的代码重复。

    使用方式：
        class BaseJumpTask(BaseTask, JumpTaskMixin):
            pass

        class BaseJumpTriggerTask(TriggerTask, JumpTaskMixin):
            pass
    """

    # ==================== 初始化 ====================

    def _init_mixin_vars(self):
        """初始化混入类的实例变量"""
        self._resolution_checked = False
        self._background_mode_logged = False
        self._adb_cache = None
        self._adb_cache_ts = 0

    # ==================== 游戏语言检测 ====================

    @property
    def game_lang(self):
        """
        检测游戏语言

        通过窗口标题判断当前游戏语言版本

        Returns:
            str: 'zh_CN' (中文) 或 'en_US' (英文)
        """
        if self.hwnd_title:
            if '漫画群星' in self.hwnd_title:
                return 'zh_CN'
            elif 'Jump' in self.hwnd_title:
                return 'en_US'
        return 'zh_CN'

    # ==================== 场景状态检测 ====================

    def in_game(self):
        """
        检测是否在游戏中

        Returns:
            bool: True 如果在游戏中
        """
        try:
            return self.find_feature(Features.IN_GAME_INDICATOR) is not None
        except ValueError:
            return False

    def in_lobby(self):
        """
        检测是否在大厅

        Returns:
            bool: True 如果在大厅
        """
        try:
            return self.find_feature(Features.LOBBY_INDICATOR) is not None
        except ValueError:
            return False

    # ==================== 日志封装 ====================

    def log_info(self, message):
        """
        输出信息日志

        Args:
            message: 日志消息
        """
        self.logger.info(f"[{self.name}] {message}")

    def log_error(self, message):
        """
        输出错误日志

        Args:
            message: 日志消息
        """
        self.logger.error(f"[{self.name}] {message}")

    # ==================== 分辨率适配 ====================

    def update_resolution(self):
        """
        更新分辨率信息

        从当前屏幕尺寸更新分辨率适配器

        Returns:
            bool: True 如果更新成功
        """
        width = self.screen_width
        height = self.screen_height

        if width > 0 and height > 0:
            resolution_adapter.update_resolution(width, height)
            self._resolution_checked = True
            self.logger.debug(f"分辨率已更新: {width}x{height}")
            return True
        return False

    def check_and_warn_resolution(self):
        """
        检查并警告分辨率问题

        Returns:
            bool: True 如果分辨率有效
        """
        if not self._resolution_checked:
            self.update_resolution()

        if resolution_adapter.is_valid_resolution():
            return True

        width, height = resolution_adapter.get_current_resolution()
        is_valid, ratio_diff = resolution_adapter.check_aspect_ratio()

        if not is_valid:
            recommended = resolution_adapter.get_recommended_resize()
            self.logger.warning(
                f"当前分辨率 {width}x{height} 不是 16:9 比例，"
                f"可能导致识别问题。建议调整为 {recommended[0]}x{recommended[1]}"
            )
            return False
        return True

    def scale_point(self, x, y):
        """
        缩放坐标点

        将参考分辨率下的坐标缩放到当前分辨率

        Args:
            x: 参考分辨率下的 X 坐标
            y: 参考分辨率下的 Y 坐标

        Returns:
            tuple: 缩放后的 (x, y) 坐标
        """
        if not self._resolution_checked:
            self.update_resolution()
        return resolution_adapter.scale_point(x, y)

    def scale_box(self, x, y, width, height):
        """
        缩放矩形框

        将参考分辨率下的矩形框缩放到当前分辨率

        Args:
            x: 矩形左上角 X 坐标
            y: 矩形左上角 Y 坐标
            width: 矩形宽度
            height: 矩形高度

        Returns:
            tuple: 缩放后的 (x, y, width, height)
        """
        if not self._resolution_checked:
            self.update_resolution()
        return resolution_adapter.scale_box(x, y, width, height)

    def click_scaled(self, ref_x, ref_y, *args, **kwargs):
        """
        点击缩放后的坐标

        将参考分辨率下的坐标缩放后点击

        Args:
            ref_x: 参考分辨率下的 X 坐标
            ref_y: 参考分辨率下的 Y 坐标
            *args, **kwargs: 传递给 click() 的其他参数

        Returns:
            click() 的返回值
        """
        if not self._resolution_checked:
            self.update_resolution()
        scaled_x, scaled_y = resolution_adapter.scale_point(ref_x, ref_y)
        return self.click(scaled_x, scaled_y, *args, **kwargs)

    def box_from_reference(self, ref_x, ref_y, ref_width=0, ref_height=0, name=None):
        """
        从参考分辨率创建 Box 对象

        Args:
            ref_x: 参考分辨率下的 X 坐标
            ref_y: 参考分辨率下的 Y 坐标
            ref_width: 参考分辨率下的宽度
            ref_height: 参考分辨率下的高度
            name: Box 名称

        Returns:
            Box: 缩放后的 Box 对象
        """
        if not self._resolution_checked:
            self.update_resolution()

        ref_w = resolution_adapter.REFERENCE_WIDTH
        ref_h = resolution_adapter.REFERENCE_HEIGHT

        return super().box_of_screen_scaled(
            original_screen_width=ref_w,
            original_screen_height=ref_h,
            x_original=ref_x,
            y_original=ref_y,
            width_original=ref_width,
            height_original=ref_height,
            name=name
        )

    def get_resolution_info(self):
        """
        获取分辨率信息

        Returns:
            dict: 包含当前分辨率、参考分辨率、缩放因子等信息
        """
        if not self._resolution_checked:
            self.update_resolution()

        current = resolution_adapter.get_current_resolution()
        reference = resolution_adapter.get_reference_resolution()
        scale = resolution_adapter.get_scale_factor()

        return {
            'current': current,
            'reference': reference,
            'scale_x': scale[0],
            'scale_y': scale[1],
            'is_valid': resolution_adapter.is_valid_resolution()
        }

    # ==================== 后台模式 ====================

    def is_background_mode(self):
        """
        检查是否启用后台模式

        Returns:
            bool: True 如果启用了后台模式
        """
        return background_manager.update_config()

    def is_game_in_background(self):
        """
        检查游戏是否在后台运行

        Returns:
            bool: True 如果游戏窗口在后台
        """
        return background_manager.is_game_in_background()

    def check_background_mode(self):
        """
        检查并记录后台模式状态

        首次调用时会输出日志信息

        Returns:
            bool: True 如果启用了后台模式
        """
        background_manager.update_config()

        if not self._background_mode_logged:
            status = background_manager.get_background_status()
            if status['background_mode_enabled']:
                self.logger.info("后台模式已启用 - 游戏窗口可最小化或被遮挡")
            else:
                self.logger.info("后台模式未启用 - 游戏窗口需要保持前台")
            self._background_mode_logged = True

        return background_manager.is_background_mode()

    def get_background_status(self):
        """
        获取后台模式详细状态

        Returns:
            dict: 后台模式状态信息
        """
        return background_manager.get_background_status()

    def ensure_capturable(self):
        """
        确保窗口可以被截图

        仅当窗口被最小化时，执行伪最小化（将窗口移到屏幕外）
        后台模式（被遮挡）不需要伪最小化

        Returns:
            bool: True 如果窗口已可截图
        """
        # 检查后台模式是否启用
        if not background_manager.is_background_mode():
            return True

        # 获取窗口句柄
        hwnd = self._get_game_hwnd()
        if not hwnd:
            return True

        # 设置伪最小化助手的窗口句柄
        pseudo_minimize_helper.set_hwnd(hwnd)

        # 仅当窗口被最小化时，才执行伪最小化
        # 后台模式（被遮挡）不需要伪最小化
        if pseudo_minimize_helper.is_window_minimized() and not pseudo_minimize_helper.is_pseudo_minimized():
            self.logger.info("窗口已最小化，执行伪最小化以支持后台截图")
            # 保存原始位置
            pseudo_minimize_helper.save_original_position()
            # 执行伪最小化
            if pseudo_minimize_helper.pseudo_minimize():
                self.logger.info("窗口已伪最小化（移到屏幕外）")
                background_input.set_hwnd(hwnd)
                return True
            else:
                self.logger.warning("伪最小化失败")
                return False

        return True

    # ==================== 后台点击操作 ====================

    def _init_background_input(self):
        """
        初始化后台输入助手

        设置窗口句柄和日志器
        """
        # 获取窗口句柄
        hwnd = self._get_game_hwnd()
        if hwnd:
            background_input.set_hwnd(hwnd)
        
        # 设置日志器
        background_input.set_logger(self.logger)

    def _get_game_hwnd(self):
        """
        获取游戏窗口句柄

        Returns:
            int: 窗口句柄，失败返回 None
        """
        try:
            from ok import og
            # 从 executor.interaction 获取
            if hasattr(self, 'executor') and hasattr(self.executor, 'interaction'):
                interaction = self.executor.interaction
                if hasattr(interaction, 'hwnd_window') and interaction.hwnd_window:
                    return interaction.hwnd_window.hwnd
            # 备用方式：从 device_manager 获取
            if og and og.device_manager and og.device_manager.hwnd_window:
                return og.device_manager.hwnd_window.hwnd
        except Exception as e:
            self.logger.debug(f"获取窗口句柄失败: {e}")
        return None

    def _need_background_click(self):
        """
        检查是否需要使用后台点击

        注意：当使用 ADB 交互（模拟器）时，不使用 SendInput 后台点击，
        而是让框架使用 ADB 的点击方法（input tap）。

        Returns:
            bool: True 如果游戏在后台或伪最小化状态，且不是 ADB 模式
        """
        # 检查是否使用 ADB 交互（模拟器模式）
        if self._is_adb_interaction():
            # ADB 模式下不需要后台点击，直接使用 ADB 命令
            return False

        return background_manager.is_game_in_background() or pseudo_minimize_helper.is_pseudo_minimized()

    def _is_adb_interaction(self):
        """
        检查当前是否使用 ADB 交互（模拟器模式），带缓存

        Returns:
            bool: True 如果使用 ADB 交互
        """
        # 10秒缓存，运行期间不会切换交互模式
        now = time.time()
        if self._adb_cache is not None and (now - self._adb_cache_ts) < 10:
            return self._adb_cache

        try:
            from ok.device.intercation import ADBInteraction
            from ok import og

            result = False
            # 方法1：检查 executor.interaction 是否为 ADBInteraction
            if hasattr(self, 'executor') and self.executor is not None:
                if hasattr(self.executor, 'interaction') and self.executor.interaction is not None:
                    interaction = self.executor.interaction
                    if isinstance(interaction, ADBInteraction):
                        result = True

            # 方法2（备用）：检查全局设备管理器的设备类型
            if not result and og is not None and hasattr(og, 'device_manager') and og.device_manager is not None:
                dm = og.device_manager
                if hasattr(dm, 'device') and dm.device is not None:
                    result = True
                elif hasattr(dm, 'config') and dm.config.get('capture') == 'adb':
                    result = True
                elif hasattr(dm, 'adb_capture_config') and not dm.hwnd_window:
                    result = True

            self._adb_cache = result
            self._adb_cache_ts = now
            return result

        except Exception as e:
            try:
                self.logger.debug(f"_is_adb_interaction 检测异常: {e}")
            except Exception:
                pass
            return False

    def is_adb(self):
        """
        检查当前是否为 ADB 模式（模拟器/手机端）

        这是公共方法，供 MovementController 和 SkillController 调用。

        Returns:
            bool: True 如果使用 ADB 交互
        """
        return self._is_adb_interaction()

    def send_key(self, key, down_time=0.02, after_sleep=0):
        """
        发送按键（智能适配 ADB/Windows 模式）

        Args:
            key: 按键
            down_time: 按下持续时间
            after_sleep: 按键后等待时间

        Returns:
            bool: 发送成功返回 True
        """
        if self._is_adb_interaction():
            # ADB 模式：使用框架的 send_key（通过 ADB 命令）
            return super().send_key(key, down_time=down_time, after_sleep=after_sleep)
        else:
            # Windows 模式：检查是否需要后台输入
            if self._need_background_click():
                self._init_background_input()
                return background_input.send_key(key, duration=down_time)
            else:
                return super().send_key(key, down_time=down_time, after_sleep=after_sleep)

    def send_key_down(self, key):
        """
        发送按键按下（智能适配 ADB/Windows 模式）

        Args:
            key: 按键

        Returns:
            bool: 发送成功返回 True
        """
        if self._is_adb_interaction():
            # ADB 模式：使用框架方法
            return super().send_key_down(key)
        else:
            # Windows 模式：检查是否需要后台输入
            if self._need_background_click():
                self._init_background_input()
                return background_input.send_key_down(key)
            else:
                return super().send_key_down(key)

    def send_key_up(self, key):
        """
        发送按键释放（智能适配 ADB/Windows 模式）

        Args:
            key: 按键

        Returns:
            bool: 发送成功返回 True
        """
        if self._is_adb_interaction():
            # ADB 模式：使用框架方法
            return super().send_key_up(key)
        else:
            # Windows 模式：检查是否需要后台输入
            if self._need_background_click():
                self._init_background_input()
                return background_input.send_key_up(key)
            else:
                return super().send_key_up(key)

    def swipe(self, from_x, from_y, to_x, to_y, duration=0.3, after_sleep=0.1):
        """
        滑动操作（智能适配 ADB/Windows 模式）

        Args:
            from_x, from_y: 起始坐标
            to_x, to_y: 结束坐标
            duration: 滑动持续时间
            after_sleep: 滑动后等待时间
        """
        is_adb = self._is_adb_interaction()
        if is_adb:
            # ADB 模式：使用框架的 swipe（通过 ADB 命令）
            self.logger.debug(f"[swipe] ADB模式: ({from_x},{from_y}) -> ({to_x},{to_y}), 持续{duration}秒")
            return super().swipe(from_x, from_y, to_x, to_y, duration, after_sleep=after_sleep)
        else:
            # Windows 模式：使用后台输入助手的拖拽
            self.logger.debug(f"[swipe] Windows模式: ({from_x},{from_y}) -> ({to_x},{to_y}), 持续{duration}秒")
            if self._need_background_click():
                self._init_background_input()
                return background_input.drag(from_x, from_y, to_x, to_y, duration=duration)
            else:
                # 前台模式：使用框架方法
                return super().swipe(from_x, from_y, to_x, to_y, duration, after_sleep=after_sleep)

    def input_text(self, text):
        """
        输入文本（智能适配 ADB/Windows 模式）

        ADB 模式：使用 input text 命令
        Windows 模式：逐字符发送按键

        Args:
            text: 要输入的文本
        """
        if self._is_adb_interaction():
            # ADB 模式：使用框架的 input_text 方法
            try:
                if hasattr(self.executor, 'interaction') and hasattr(self.executor.interaction, 'input_text'):
                    self.executor.interaction.input_text(text)
                    return True
            except Exception as e:
                self.logger.error(f"ADB input_text 失败: {e}")
                return False
        else:
            # Windows 模式：逐字符发送按键
            for char in str(text):
                if char:
                    self.send_key(char, down_time=0.05)
                    time.sleep(0.02)
            return True

    def input_text_with_clear(self, text, clear_first=True):
        """
        输入文本（支持先清空再输入）

        对于 ADB 模式，使用多次删除键清空后输入

        Args:
            text: 要输入的文本
            clear_first: 是否先清空输入框

        Returns:
            bool: True 如果成功
        """
        if self._is_adb_interaction():
            try:
                interaction = self.executor.interaction

                # 先清空输入框
                if clear_first:
                    self._adb_clear_input_robust()

                time.sleep(0.2)

                # 使用普通 input_text
                if hasattr(interaction, 'input_text'):
                    interaction.input_text(text)
                    return True

            except Exception as e:
                self.logger.error(f"ADB input_text_with_clear 失败: {e}")
                return False
        else:
            # Windows 模式
            if clear_first:
                # Ctrl+A 全选
                self.send_key_down('ctrl')
                self.send_key('a')
                self.send_key_up('ctrl')
                time.sleep(0.1)
                # 删除
                self.send_key('backspace')
                time.sleep(0.2)

            # 输入文本
            for char in str(text):
                if char:
                    self.send_key(char, down_time=0.05)
                    time.sleep(0.02)
            return True

    def _adb_clear_input_simple(self, count=30):
        """
        ADB 模式下简单清空输入框

        通过多次发送删除键实现

        Args:
            count: 删除键次数
        """
        try:
            for _ in range(count):
                self.send_key('KEYCODE_DEL', after_sleep=0.01)
        except Exception as e:
            self.logger.warning(f"ADB 清空输入框失败: {e}")

    def _adb_clear_input_robust(self):
        """
        ADB 模式下可靠地清空输入框

        使用多种方法组合确保清空成功
        """
        try:
            # 方法1：Ctrl+A 全选 + 删除（优先）
            self.send_key_down('ctrl')
            time.sleep(0.05)
            self.send_key('a')
            time.sleep(0.05)
            self.send_key_up('ctrl')
            time.sleep(0.1)
            self.send_key('KEYCODE_DEL', after_sleep=0.1)

            # 方法2：多次删除键（备选，确保清空）
            for i in range(15):
                self.send_key('KEYCODE_DEL', after_sleep=0.01)

        except Exception as e:
            self.logger.warning(f"ADB 清空输入框异常: {e}")

    def background_click(self, x, y, relative=False, after_sleep=0.5):
        """
        后台模式下的点击操作

        使用 SendInput 实现，支持游戏在后台或伪最小化状态下点击

        Args:
            x, y: 坐标（绝对或相对）
            relative: 是否为相对坐标 (0-1)
            after_sleep: 点击后等待时间（秒）

        Returns:
            bool: 点击成功返回 True
        """
        # 初始化后台输入
        self._init_background_input()

        # 转换相对坐标为绝对坐标
        if relative:
            abs_x = int(x * self.width)
            abs_y = int(y * self.height)
        else:
            abs_x, abs_y = int(x), int(y)

        # 使用后台输入助手点击
        result = background_input.click(abs_x, abs_y)

        if after_sleep > 0:
            time.sleep(after_sleep)

        return result

    def background_click_relative(self, x, y, after_sleep=0.5):
        """
        后台模式下的相对坐标点击

        Args:
            x, y: 相对坐标 (0-1)
            after_sleep: 点击后等待时间（秒）

        Returns:
            bool: 点击成功返回 True
        """
        return self.background_click(x, y, relative=True, after_sleep=after_sleep)

    def background_click_scaled(self, ref_x, ref_y, after_sleep=0.5):
        """
        后台模式下的缩放坐标点击

        将参考分辨率下的坐标缩放后点击

        Args:
            ref_x, ref_y: 参考分辨率下的坐标
            after_sleep: 点击后等待时间（秒）

        Returns:
            bool: 点击成功返回 True
        """
        if not self._resolution_checked:
            self.update_resolution()
        scaled_x, scaled_y = resolution_adapter.scale_point(ref_x, ref_y)
        return self.background_click(int(scaled_x), int(scaled_y), after_sleep=after_sleep)

    def background_drag(self, start_x, start_y, end_x, end_y, duration=0.3, relative=False):
        """
        后台模式下的拖拽操作

        Args:
            start_x, start_y: 起始坐标
            end_x, end_y: 结束坐标
            duration: 拖拽持续时间（秒）
            relative: 是否为相对坐标 (0-1)

        Returns:
            bool: 拖拽成功返回 True
        """
        # 初始化后台输入
        self._init_background_input()

        # 转换相对坐标为绝对坐标
        if relative:
            start_x = int(start_x * self.width)
            start_y = int(start_y * self.height)
            end_x = int(end_x * self.width)
            end_y = int(end_y * self.height)
        else:
            start_x, start_y = int(start_x), int(start_y)
            end_x, end_y = int(end_x), int(end_y)

        # 使用后台输入助手拖拽
        return background_input.drag(start_x, start_y, end_x, end_y, duration=duration)

    def smart_click(self, x, y=None, *args, **kwargs):
        """
        智能点击（委托给 self.click()，已包含后台模式支持）
    
        Args:
            x: X坐标/检测结果对象/Box对象
            y: Y坐标
            *args, **kwargs: 传递给 click() 的其他参数
    
        Returns:
            点击操作的返回值
        """
        return self.click(x, y, *args, **kwargs)
    
    def smart_click_relative(self, x, y, *args, **kwargs):
        """
        智能相对坐标点击（委托给 self.click_relative()，已包含后台模式支持）
    
        Args:
            x, y: 相对坐标 (0-1)
            *args, **kwargs: 传递给 click_relative() 的其他参数
    
        Returns:
            点击操作的返回值
        """
        return self.click_relative(x, y, *args, **kwargs)
