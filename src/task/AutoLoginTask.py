import os
import re
import time

import cv2

from ok import og

from src.task.BaseJumpTask import BaseJumpTask
from src.constants.features import Features
from src.utils.BackgroundManager import background_manager
from src.utils.BackgroundInputHelper import background_input
from src.OnnxYoloDetect import OnnxYoloDetect


class AutoLoginInputException(Exception):
    """账号输入异常"""
    pass


class AutoLoginTask(BaseJumpTask):
    """
    自动登录任务

    负责自动启动游戏并完成登录流程，包括：
    - 处理登录界面（适龄提示、账户登录、开始游戏）
    - 处理问卷调查
    - 账号输入（可选）
    - 加载界面检测与处理
    """

    # 界面状态标识
    LOGIN_SCREEN_EX = 'login_screen_ex'      # 快进按钮界面（新增）
    LOGIN_SCREEN_0 = 'login_screen_0'      # 适龄提示界面
    LOGIN_SCREEN_1 = 'login_screen_1'      # 账户登录界面
    LOGIN_SCREEN_2 = 'login_screen_2'      # 开始游戏界面
    LOADING_SCREEN = 'loading_screen'      # 加载界面（新增）
    WENJUAN_SCREEN = 'wenjuan_screen'      # 问卷调查界面
    CHARACTER_SELECTION_SCREEN = 'character_selection_screen'  # 角色选择界面
    UNKNOWN_SCREEN = 'unknown_screen'      # 未知界面

    # 未知界面检测常量
    UNKNOWN_SCREEN_MAX_COUNT = 3           # 连续检测到未知界面的最大次数

    # 账号输入相关常量
    ACCOUNT_INPUT_TEMPLATE_PATH = os.path.join('assets', 'images', 'login', 'input.png')
    ACCOUNT_INPUT_MATCH_THRESHOLD = 0.72
    ACCOUNT_INPUT_MATCH_TIMEOUT = 1.0
    ACCOUNT_INPUT_TOTAL_TIMEOUT = 3.0
    ACCOUNT_INPUT_KEY_DELAY_MIN = 0.05
    ACCOUNT_INPUT_KEY_DELAY_MAX = 0.15
    ACCOUNT_INPUT_VERIFY_TIMEOUT = 1.0
    WENJUAN_WAIT_TIMEOUT = 30.0

    # 勾选框检测相关常量
    CHECKBOX_MODEL_PATH = os.path.join('assets', 'select', 'select.onnx')
    CHECKBOX_LABEL_CHECKED = 0    # 已勾选
    CHECKBOX_LABEL_UNCHECKED = 1  # 未勾选
    CHECKBOX_CONF_THRESHOLD = 0.45  # YOLO置信度阈值

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "AutoLoginTask"
        self.description = "自动登录 - 自动启动游戏并登录"
        self._logged_in = False
        self._error_count = 0
        self._screenshots_dir = "screenshots"
        self._cached_ocr = None
        self._last_error = None
        self._account_input_done = False

        # 加载界面检测相关属性
        self._loading_percentage = None  # 当前检测到的加载百分比
        self._loading_start_time = None  # 加载开始时间
        self._last_percentage = None  # 上一次检测到的百分比
        self._last_percentage_time = None  # 上一次检测到百分比的时间
        self._is_loading = False  # 是否处于加载状态
        self._paused_time = 0  # 因加载暂停的累计时间
        self._loading_just_ended = False  # 加载界面刚结束的标志

        # 登录状态容错相关属性
        self._failure_time = None  # 判定失败的时间
        self._grace_period = 5.0  # 容错缓冲期（秒）
        self._final_status = None  # 最终状态

        # 未知界面检测相关属性
        self._unknown_screen_count = 0  # 连续检测到未知界面的次数

        self.default_config = {
            '自动启动游戏': False,
            '等待游戏启动(秒)': 120,
            '最大登录尝试次数': 8,
            '输入账号': False,
            '账号': '',
            '账号输入重试次数': 2,
            '输入校验超时(秒)': 1.0,
            '登录等待超时(秒)': 60,
            '点击后等待时间(秒)': 3,
            '加载停滞超时(秒)': 60,  # 加载停滞检测超时
            '启用加载检测': True,  # 是否启用加载界面检测
            '启用状态容错': True,  # 是否启用状态容错
        }
        self._ensure_screenshots_dir()
        self._checkbox_detector = None
        self._init_checkbox_detector()

    def _init_checkbox_detector(self):
        """初始化勾选框 YOLO 检测器"""
        try:
            model_path = self._resolve_model_path(self.CHECKBOX_MODEL_PATH)
            if os.path.exists(model_path):
                self._checkbox_detector = OnnxYoloDetect(
                    weights=model_path,
                    conf_threshold=self.CHECKBOX_CONF_THRESHOLD
                )
                self.log_info(f"勾选框检测器初始化成功: {model_path}")
            else:
                self.log_error(f"勾选框模型文件不存在: {model_path}")
        except Exception as e:
            self.log_error(f"勾选框检测器初始化失败: {e}")

    def _resolve_model_path(self, relative_path):
        """解析模型文件路径"""
        if os.path.isabs(relative_path):
            return relative_path
        candidates = [
            relative_path,
            os.path.join(os.getcwd(), relative_path),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), relative_path),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return candidates[-1]

    def _cfg(self, key, default=None):
        """获取配置值"""
        # 优先从 og.config 获取 CI 传递的账号配置
        if key == '账号':
            try:
                from ok import og
                if hasattr(og, 'config') and og.config and 'ci_account' in og.config:
                    return og.config['ci_account']
            except Exception:
                pass
        elif key == '输入账号':
            try:
                from ok import og
                if hasattr(og, 'config') and og.config and 'ci_input_account' in og.config:
                    return og.config['ci_input_account']
            except Exception:
                pass
        
        if self.config is not None:
            return self.config.get(key, default)
        return self.default_config.get(key, default)

    def _resolve_account_input_template_path(self):
        """解析账号输入框模板路径"""
        if os.path.isabs(self.ACCOUNT_INPUT_TEMPLATE_PATH):
            return self.ACCOUNT_INPUT_TEMPLATE_PATH
        candidates = [
            self.ACCOUNT_INPUT_TEMPLATE_PATH,
            os.path.join(os.getcwd(), self.ACCOUNT_INPUT_TEMPLATE_PATH),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), self.ACCOUNT_INPUT_TEMPLATE_PATH),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return candidates[-1]

    def _ensure_screenshots_dir(self):
        """确保截图目录存在"""
        if not os.path.exists(self._screenshots_dir):
            os.makedirs(self._screenshots_dir)

    def _init_background_mode(self):
        """
        初始化后台模式
        
        设置后台管理器和后台输入助手的窗口句柄
        """
        # 更新后台模式配置
        background_manager.update_config()
        
        # 获取游戏窗口句柄
        hwnd = self._get_game_hwnd()
        if hwnd:
            # 设置后台管理器的窗口句柄
            background_manager.on_game_window_change(hwnd)
            # 设置后台输入助手的窗口句柄
            background_input.set_hwnd(hwnd)
            background_input.set_logger(self.logger)
            self.log_info(f"后台模式已初始化, hwnd={hwnd}")
        else:
            self.log_info("后台模式初始化: 未获取到窗口句柄，将在首次操作时重试")
        
        # 记录后台模式状态
        status = background_manager.get_background_status()
        self.log_info(f"后台模式状态: 启用={status['background_mode_enabled']}, "
                      f"伪最小化={status['is_pseudo_minimized']}, "
                      f"在后台={status['is_in_background']}")

    def _log_window_state(self):
        """记录窗口状态（调试用）"""
        from src.utils.PseudoMinimizeHelper import pseudo_minimize_helper
        import ctypes
        
        hwnd = self._get_game_hwnd()
        if not hwnd:
            self.log_info("窗口状态: 未获取到 hwnd")
            return
        
        pseudo_minimize_helper.set_hwnd(hwnd)
        
        is_minimized = pseudo_minimize_helper.is_window_minimized()
        is_visible = pseudo_minimize_helper.is_window_visible()
        is_foreground = pseudo_minimize_helper.is_window_in_foreground()
        is_pseudo = pseudo_minimize_helper.is_pseudo_minimized()
        
        self.log_info(f"窗口状态: hwnd={hwnd}, "
                      f"minimized={is_minimized}, visible={is_visible}, "
                      f"foreground={is_foreground}, pseudo_minimized={is_pseudo}")

    # ==================== 主流程 ====================

    def run(self):
        """执行自动登录任务"""
        self.log_info("=" * 50)
        self.log_info("自动登录任务启动")
        self.log_info("=" * 50)

        # 初始化后台模式
        self._init_background_mode()

        self._last_error = None
        self._account_input_done = False
        self._account_input_finish_time = 0
        self.info_set('登录状态', '开始登录')

        if not self._cfg('启用', True):
            self.log_info("自动登录已禁用")
            self.info_set('登录状态', '已禁用')
            return False

        if self._logged_in:
            if self._check_login_success():
                self.log_info("已经登录完成 - 已在游戏中")
                self.info_set('登录状态', '已登录')
                return True
            else:
                self.log_info("之前登录状态已失效，重新登录...")
                self._logged_in = False

        if self._cfg('自动启动游戏', False):
            if not self._start_game():
                self._last_error = "启动游戏失败"
                self.info_set('登录状态', f'错误: {self._last_error}')
                return False

        if not self._wait_for_game_window():
            self._last_error = "等待游戏窗口超时"
            self.info_set('登录状态', f'错误: {self._last_error}')
            return False

        if not self._execute_login_flow():
            if self._last_error:
                self.info_set('登录状态', f'错误: {self._last_error}')
            else:
                self.info_set('登录状态', '登录失败')
            return False

        # 登录成功
        self.info_set('登录状态', '登录成功')
        self._logged_in = True
        self.log_info("自动登录完成")

        # 单独运行时主动结束任务
        if self._is_standalone:
            self.log_info("单独运行模式，登录成功后结束任务")
            # 设置全局状态，通知任务已完成
            try:
                from src import jump_globals
                if jump_globals:
                    jump_globals.set_login_task_completed(True)
            except ImportError:
                pass

        return True

    def _start_game(self):
        """启动游戏进程"""
        self.log_info("启动游戏...")

        game_exe = og.config.get('game_exe_path')

        if game_exe:
            import subprocess
            try:
                subprocess.Popen([game_exe])
                self.log_info(f"游戏进程已启动: {game_exe}")
                return True
            except Exception as e:
                self.log_error(f"启动游戏失败: {e}")
                return False
        else:
            self.logger.warning(f"[{self.name}] 未配置游戏路径，请手动启动游戏")
            return True

    def _wait_for_game_window(self):
        """
        等待游戏窗口出现
        
        如果检测到已进入登录界面（界面EX/0/1/2），则提前退出等待
        """
        timeout = self._cfg('等待游戏启动(秒)', 120)
        self.log_info(f"等待游戏窗口... (最长 {timeout} 秒)")

        start_time = time.time()

        while time.time() - start_time < timeout:
            # 确保窗口可截图（后台模式下自动伪最小化）
            self.ensure_capturable()
            self.next_frame()
            if self.frame is not None:
                self.log_info("检测到游戏窗口")
                
                # 检查是否已进入登录界面，如果是则提前退出等待
                self._clear_ocr_cache()
                current_screen = self._detect_login_screen()
                if current_screen in [
                    self.LOGIN_SCREEN_EX,
                    self.LOGIN_SCREEN_0,
                    self.LOGIN_SCREEN_1,
                    self.LOGIN_SCREEN_2,
                    self.CHARACTER_SELECTION_SCREEN
                ]:
                    self.log_info(f"已检测到登录界面: {current_screen}，跳过等待")
                    return True
                
                return True
            time.sleep(1)

        return False

    # ==================== OCR 缓存管理 ====================

    def _get_ocr_texts(self):
        """获取 OCR 文本（带缓存）"""
        if self._cached_ocr is None:
            self._cached_ocr = self.ocr()
            if self._cached_ocr:
                self.log_info(f"OCR识别到 {len(self._cached_ocr)} 个文字:")
                for box in self._cached_ocr:
                    self.log_info(f"  - '{box.name}' at ({box.x}, {box.y})")
        return self._cached_ocr

    def _clear_ocr_cache(self):
        """清除 OCR 缓存"""
        self._cached_ocr = None

    # ==================== 加载界面检测 ====================

    def _detect_loading_percentage(self):
        """
        检测右下角的加载百分比

        Returns:
            int | None: 检测到的百分比数值（0-100），未检测到返回 None
        """
        if self.frame is None:
            return None

        try:
            frame_h, frame_w = self.frame.shape[:2]

            # 定义右下角区域（右下角 1/4 区域）
            roi_x = int(frame_w * 0.75)
            roi_y = int(frame_h * 0.75)

            # 方法1：使用已缓存的OCR结果（优先）
            texts = self._get_ocr_texts()
            if texts:
                import re
                percentage_pattern = re.compile(r'(\d{1,3})\s*%')
                
                for result in texts:
                    try:
                        text = getattr(result, 'name', str(result))
                        # 检查是否在右下角区域
                        if hasattr(result, 'x') and hasattr(result, 'y'):
                            # 检查位置是否在右下角1/4区域
                            if result.x >= roi_x and result.y >= roi_y:
                                self.log_debug(f"右下角OCR文本: '{text}' at ({result.x}, {result.y})")
                                match = percentage_pattern.search(text)
                                if match:
                                    percentage = int(match.group(1))
                                    if 0 <= percentage <= 100:
                                        self.log_info(f"检测到加载百分比: {percentage}%")
                                        return percentage
                    except (ValueError, AttributeError) as e:
                        self.log_debug(f"解析失败: {e}")
                        continue

            # 方法2：对ROI区域单独进行OCR（备选）
            roi_w = frame_w - roi_x
            roi_h = frame_h - roi_y
            roi = self.frame[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]

            self.log_debug(f"加载百分比检测区域: ({roi_x},{roi_y}) {roi_w}x{roi_h}")

            try:
                # 尝试使用框架提供的ocr方法
                ocr_results = self.ocr(roi)
                if ocr_results:
                    self.log_debug(f"ROI-OCR检测到 {len(ocr_results)} 个结果")
                    import re
                    percentage_pattern = re.compile(r'(\d{1,3})\s*%')
                    
                    for result in ocr_results:
                        try:
                            text = getattr(result, 'name', str(result))
                            self.log_debug(f"ROI-OCR文本: '{text}'")
                            
                            match = percentage_pattern.search(text)
                            if match:
                                percentage = int(match.group(1))
                                if 0 <= percentage <= 100:
                                    self.log_info(f"检测到加载百分比: {percentage}%")
                                    return percentage
                        except (ValueError, AttributeError) as e:
                            self.log_debug(f"解析失败: {e}")
                            continue
            except Exception as e:
                self.log_debug(f"ROI-OCR失败: {e}")

            return None

        except Exception as e:
            self.log_error(f"加载百分比检测失败: {e}")
            return None

    def _check_loading_state(self):
        """
        检查加载状态并更新计时器

        Returns:
            tuple: (is_loading: bool, is_stuck: bool, percentage: int|None)
        """
        if not self._cfg('启用加载检测', True):
            return False, False, None

        current_time = time.time()
        percentage = self._detect_loading_percentage()

        if percentage is not None:
            # 检测到百分比
            self._is_loading = True
            self._loading_percentage = percentage

            # 检查是否停滞
            if self._last_percentage == percentage:
                # 百分比未变化
                if self._last_percentage_time is not None:
                    stuck_duration = current_time - self._last_percentage_time
                    stuck_timeout = self._cfg('加载停滞超时(秒)', 60)
                    if stuck_duration > stuck_timeout:
                        self.log_error(f"加载停滞超时：卡在 {percentage}% 超过 {stuck_timeout} 秒")
                        return True, True, percentage
            else:
                # 百分比变化，重置停滞计时
                self._last_percentage = percentage
                self._last_percentage_time = current_time

            if self._loading_start_time is None:
                self._loading_start_time = current_time
                self.log_info(f"检测到加载界面: {percentage}%")

            return True, False, percentage
        else:
            # 未检测到百分比
            if self._is_loading:
                # 从加载状态退出
                self.log_info("加载界面结束，恢复正常计时")
                if self._loading_start_time is not None:
                    self._paused_time += current_time - self._loading_start_time
                self._is_loading = False
                self._loading_start_time = None
                self._last_percentage = None
                self._last_percentage_time = None
                self._loading_just_ended = True  # 标记加载刚结束
                self._clear_ocr_cache()  # 清空OCR缓存
                self.log_debug("加载结束，已设置重新截图标志")

            return False, False, None

    def _get_effective_timeout(self, start_time, original_timeout):
        """
        获取有效的超时时间（扣除加载暂停时间）

        Args:
            start_time: 开始时间
            original_timeout: 原始超时时间

        Returns:
            float: 剩余有效时间
        """
        elapsed = time.time() - start_time
        effective_elapsed = elapsed - self._paused_time
        remaining = original_timeout - effective_elapsed
        return max(0, remaining)

    # ==================== 登录状态容错 ====================

    def _check_success_after_failure(self):
        """
        在判定失败后检查是否实际已成功

        Returns:
            bool: True 如果检测到成功状态
        """
        if not self._cfg('启用状态容错', True):
            return False

        if self._failure_time is None:
            return False

        # 检查是否在容错缓冲期内
        if time.time() - self._failure_time > self._grace_period:
            return False

        # 重新检查成功条件
        try:
            if self._check_login_success():
                self.log_info("状态容错：检测到登录成功，修正最终状态")
                return True
        except Exception:
            pass

        return False

    def _record_failure(self):
        """记录失败时间，启动容错缓冲期"""
        self._failure_time = time.time()

    def _clear_failure(self):
        """清除失败记录"""
        self._failure_time = None

    # ==================== 登录流程 ====================

    def _execute_login_flow(self):
        """执行登录流程（支持加载检测和状态容错）"""
        timeout = self._cfg('登录等待超时(秒)', 60)
        max_attempts = self._cfg('最大登录尝试次数', 8)
        click_wait = self._cfg('点击后等待时间(秒)', 3)

        start_time = time.time()
        attempts = 0
        last_action = None
        last_action_time = 0

        # 重置加载检测状态
        self._paused_time = 0
        self._loading_start_time = None
        self._last_percentage = None
        self._last_percentage_time = None
        self._is_loading = False
        self._failure_time = None
        self._unknown_screen_count = 0  # 重置未知界面计数

        while True:
            # 检查有效超时（扣除加载暂停时间）
            remaining_time = self._get_effective_timeout(start_time, timeout)
            if remaining_time <= 0:
                self._last_error = f"登录超时 (总超时: {timeout}秒, 加载暂停: {self._paused_time:.1f}秒)"
                self.log_error(self._last_error)
                self._save_error_screenshot("login_timeout")
                self._record_failure()
                break

            if attempts >= max_attempts:
                self._last_error = f"达到最大尝试次数 ({max_attempts})"
                self.log_error(self._last_error)
                self._save_error_screenshot("max_attempts_exceeded")
                self._record_failure()
                break

            # 检查窗口状态（调试日志）
            self._log_window_state()

            # 记录后台模式状态
            bg_enabled = background_manager.is_background_mode()
            bg_in_bg = background_manager.is_game_in_background()
            self.log_info(f"后台模式: 启用={bg_enabled}, 在后台={bg_in_bg}")

            # 确保窗口可截图（仅在最小化时伪最小化）
            self.ensure_capturable()

            # 获取截图
            self.log_info("开始截图...")
            self.next_frame()

            # 检查截图是否有效
            if self.frame is None:
                self.log_info("截图失败: frame 为 None")
                time.sleep(0.5)
                continue

            frame_h, frame_w = self.frame.shape[:2] if self.frame is not None else (0, 0)
            self.log_info(f"截图成功: {frame_w}x{frame_h}")

            # 清空OCR缓存，准备新的检测
            self._clear_ocr_cache()

            # 检查加载界面状态（优先级最高）
            # 注意：此检测会触发OCR，结果会被缓存供后续使用
            is_loading, is_stuck, percentage = self._check_loading_state()
            if is_stuck:
                # 加载停滞，保存错误截图
                self._last_error = f"加载停滞超时：卡在 {percentage}% 超过 {self._cfg('加载停滞超时(秒)', 60)} 秒"
                self._save_error_screenshot(f"loading_stuck_{percentage}")
                self._record_failure()
                break

            if is_loading:
                # 处于加载状态，跳过其他检测
                self.log_info(f"加载中: {percentage}% (剩余有效时间: {remaining_time:.1f}秒)")
                self.info_set('登录状态', f'加载中 {percentage}%')
                time.sleep(0.5)
                continue

            # 加载界面刚结束，等待界面稳定后重新截图
            if self._loading_just_ended:
                self.log_info("加载界面刚结束，等待界面稳定...")
                self._loading_just_ended = False
                time.sleep(1.0)  # 增加等待时间，确保界面完全渲染
                self.next_frame()  # 重新截图
                self._clear_ocr_cache()  # 清空OCR缓存
                self.log_info("界面稳定后重新截图完成，继续登录流程")

            # 检查登录成功
            if self._check_login_success():
                self._logged_in = True
                self._clear_failure()
                self.log_info("登录成功 - 已进入游戏")
                return True

            # 检查错误
            error_msg = self._check_login_error()
            if error_msg:
                self._last_error = error_msg
                self.log_error(f"检测到登录错误: {error_msg}")
                self._save_error_screenshot(error_msg)
                self._record_failure()
                # 不立即返回，允许容错检查
                break

            # 检查问卷调查
            wenjuan_result = self._check_wenjuan_screen()
            if wenjuan_result:
                self.log_info("检测到问卷调查场景，开始处理...")
                if self._handle_wenjuan():
                    self.log_info("问卷调查处理完成，已进入角色选择界面")
                    self._logged_in = True
                    self._clear_failure()
                    self.info_set('登录状态', '已登录')
                    return True
                else:
                    self.logger.warning(f"[{self.name}] 问卷调查处理失败，继续尝试...")

            current_screen = self._detect_login_screen()

            action = None
            if current_screen == self.LOADING_SCREEN:
                # 加载界面 - 特殊处理，不增加尝试次数
                action = self._handle_loading_screen
                self._unknown_screen_count = 0  # 重置未知界面计数
            elif current_screen == self.CHARACTER_SELECTION_SCREEN:
                # 角色选择界面 - 登录成功
                self.log_info("检测到角色选择界面，登录成功")
                self._logged_in = True
                self._clear_failure()
                self._unknown_screen_count = 0  # 重置未知界面计数
                self.info_set('登录状态', '已登录')
                return True
            elif current_screen == self.LOGIN_SCREEN_EX:
                # 快进按钮界面 - 点击跳过
                action = self._handle_login_screen_ex
                self._unknown_screen_count = 0  # 重置未知界面计数
            elif current_screen == self.LOGIN_SCREEN_0:
                action = self._handle_login_screen_0
                self._unknown_screen_count = 0  # 重置未知界面计数
            elif current_screen == self.LOGIN_SCREEN_1:
                action = self._handle_login_screen_1
                self._unknown_screen_count = 0  # 重置未知界面计数
            elif current_screen == self.LOGIN_SCREEN_2:
                action = self._handle_login_screen_2
                self._unknown_screen_count = 0  # 重置未知界面计数
            else:
                # 未知界面检测
                self._unknown_screen_count += 1
                self.logger.warning(f"检测到未知界面 (连续第{self._unknown_screen_count}次)")
                
                if self._unknown_screen_count >= self.UNKNOWN_SCREEN_MAX_COUNT:
                    error_msg = f"连续{self._unknown_screen_count}次检测到未知界面，登录流程终止"
                    self._last_error = error_msg
                    self.log_error(error_msg)
                    self._save_error_screenshot("unknown_screen_limit")
                    self._record_failure()
                    break
                
                action = self._handle_unknown_screen

            if action == last_action and time.time() - last_action_time < click_wait:
                time.sleep(0.5)
                continue

            if action:
                try:
                    handled = action()
                except AutoLoginInputException as e:
                    self._last_error = str(e)
                    self.log_error(f"账号输入失败: {e}")
                    self._record_failure()
                    return False
                    
                # 加载界面不增加尝试次数
                if current_screen == self.LOADING_SCREEN:
                    time.sleep(0.5)
                    continue
                    
                if handled:
                    if self._logged_in:
                        self._clear_failure()
                        self.log_info("登录成功 - 自动登录完成")
                        return True
                    attempts += 1
                    last_action = action
                    last_action_time = time.time()
                    self.log_info(f"执行点击操作，等待界面变化... (尝试 {attempts}/{max_attempts})")
                    self.info_set('登录状态', f'尝试 {attempts}/{max_attempts}')
                    self.sleep(click_wait)

        # 容错检查：在判定失败后再次确认
        if self._check_success_after_failure():
            self._logged_in = True
            self._clear_failure()
            self.info_set('登录状态', '登录成功')
            return True

        return self._logged_in

    def _reset_loading_state(self):
        """重置加载检测相关状态"""
        self._paused_time = 0
        self._loading_start_time = None
        self._loading_percentage = None
        self._last_percentage = None
        self._last_percentage_time = None
        self._is_loading = False
        self._paused_time_at_entry = 0
        self._login_start_time = None

    def _get_login_action(self, screen_type):
        """根据屏幕类型获取对应的处理动作"""
        action_map = {
            self.LOGIN_SCREEN_0: self._handle_login_screen_0,
            self.LOGIN_SCREEN_1: self._handle_login_screen_1,
            self.LOGIN_SCREEN_2: self._handle_login_screen_2,
            self.LOADING_SCREEN: self._handle_loading_screen,
        }
        return action_map.get(screen_type, self._handle_unknown_screen)

    def _handle_loading_screen(self):
        """
        处理加载界面
        
        加载界面处理逻辑：
        1. 检测当前百分比
        2. 检查是否停滞（同一百分比超过配置时间则抛错）
        3. 更新加载状态和计时器
        4. 不执行任何点击操作，等待加载完成
        
        Returns:
            bool: 总是返回True（表示已处理）
        """
        current_time = time.time()
        percentage = self._detect_loading_percentage()
        
        if percentage is not None:
            # 检测到百分比
            self._is_loading = True
            self._loading_percentage = percentage
            
            # 检查是否停滞（同一百分比超过配置时间）
            if self._last_percentage == percentage:
                if self._last_percentage_time is not None:
                    stuck_duration = current_time - self._last_percentage_time
                    stuck_timeout = self._cfg('加载停滞超时(秒)', 60)
                    if stuck_duration > stuck_timeout:
                        error_msg = f"加载停滞超时：卡在 {percentage}% 超过 {stuck_timeout} 秒"
                        self.log_error(error_msg)
                        self._save_error_screenshot(f"loading_stuck_{percentage}")
                        self._last_error = error_msg
                        # 抛出异常，让上层处理
                        raise AutoLoginInputException(error_msg)
            else:
                # 百分比变化，重置停滞计时
                if self._last_percentage is not None:
                    self.log_info(f"加载进度: {self._last_percentage}% → {percentage}%")
                self._last_percentage = percentage
                self._last_percentage_time = current_time
            
            # 记录加载开始时间
            if self._loading_start_time is None:
                self._loading_start_time = current_time
                self._paused_time_at_entry = self._paused_time
                self.log_info(f"进入加载界面: {percentage}%")
            
            # 更新暂停时间
            self._paused_time = (current_time - self._loading_start_time) + self._paused_time_at_entry
            
            self.info_set('登录状态', f'加载中 {percentage}%')
            self.log_debug(f"加载中: {percentage}%")
        else:
            # 未检测到百分比，可能加载已完成
            if self._is_loading:
                loading_duration = current_time - self._loading_start_time if self._loading_start_time else 0
                self.log_info(f"加载界面结束，加载持续时间: {loading_duration:.1f}秒")
                self._is_loading = False
                self._loading_start_time = None
                self._loading_percentage = None
                self._loading_just_ended = True  # 标记加载刚结束
                # 清空OCR缓存，确保下一次检测使用新的截图
                self._clear_ocr_cache()
                self.log_debug("加载结束，已清空OCR缓存")
        
        return True

    def _detect_login_screen(self):
        """
        检测当前界面类型
    
        检测优先级（从高到低）：
        1. 加载界面 - 最高优先级，避免其他检测干扰
        2. 角色选择界面 - 登录成功后的界面
        3. 登录界面EX（快进按钮）- 优先于登录界面0
        4. 登录界面0（适龄提示）
        5. 登录界面1（账户登录）
        6. 登录界面2（开始游戏）
        7. 未知界面
    
        Returns:
            str | None: 界面类型标识
        """
        # 优先检测加载界面（最高优先级）
        if self._check_loading_screen():
            return self.LOADING_SCREEN
    
        texts = self._get_ocr_texts()
    
        # 检测角色选择界面（登录成功）
        if self._check_character_selection_screen(texts):
            return self.CHARACTER_SELECTION_SCREEN
    
        # 检测登录界面EX（快进按钮）- 优先于登录界面0
        if self._check_login_screen_ex():
            return self.LOGIN_SCREEN_EX
    
        if self._check_login_screen_0(texts):
            return self.LOGIN_SCREEN_0
        elif self._check_login_screen_1(texts):
            return self.LOGIN_SCREEN_1
        elif self._check_login_screen_2(texts):
            return self.LOGIN_SCREEN_2
    
        return None

    def _check_login_screen_ex(self):
        """
        检测是否为登录界面EX（快进按钮）

        快进按钮通常位于屏幕右上角，用于跳过开场动画

        Returns:
            bool: True 如果检测到快进按钮
        """
        try:
            # 使用模板匹配检测快进按钮
            skip_button = self.find_one(Features.SKIP_BUTTON, threshold=0.55)
            if skip_button:
                self.log_debug("检测到快进按钮(特征匹配)")
                return True
        except ValueError:
            pass

        return False

    def _check_loading_screen(self):
        """
        检测是否为加载界面
        
        加载界面特征：屏幕右下角1/4区域存在数字百分比文本（如"15%"、"50%"、"100%"）
        
        Returns:
            bool: True 如果检测到加载界面
        """
        if not self._cfg('启用加载检测', True):
            return False
            
        percentage = self._detect_loading_percentage()
        if percentage is not None:
            self.log_debug(f"检测到加载界面: {percentage}%")
            return True
        return False

    def _check_character_selection_screen(self, texts=None):
        """
        检测是否为角色选择界面
        
        角色选择界面特征：
        - OCR识别到"请选择一位你心仪的角色"或类似文本
        
        Returns:
            bool: True 如果检测到角色选择界面
        """
        if texts is None:
            texts = self._get_ocr_texts()
        
        if not texts:
            return False
        
        # 只需写简体中文，find_boxes会自动调用LangConverter转换为双语模式
        patterns = [
            re.compile(r"请选择一位你心仪的角色"),
            re.compile(r"请选择.*心仪的角色"),
            re.compile(r"选择.*角色"),
            re.compile(r"心仪的角色"),
        ]
        
        for pattern in patterns:
            select_char = self.find_boxes(texts, match=pattern)
            if select_char and len(select_char) > 0:
                self.log_debug(f"OCR检测到角色选择界面")
                return True
        
        return False

    def _check_login_screen_0(self, texts=None):
        """检测是否为登录界面0（适龄提示）"""
        try:
            if self.find_one(Features.LOGIN_SCREEN_0_INDICATOR, threshold=0.6):
                return True
        except ValueError:
            pass

        if texts is None:
            texts = self._get_ocr_texts()
        if texts:
            # 匹配适龄提示文本（同时匹配简体和繁体）
            # 简体: 适龄提示、年龄分级
            # 繁体: 年齡分級
            has_age_prompt = self.find_boxes(texts, match=re.compile(r"适龄提示|年龄分级|年齡分級"))
            has_enter_game = self.find_boxes(texts, match=re.compile(r"进入游戏"))
            # 匹配协议同意文本
            has_agree = self.find_boxes(texts, match=re.compile(r"我已详细阅读并同意"))

            if has_age_prompt and has_enter_game and has_agree:
                return True

        return False

    def _check_login_screen_1(self, texts=None):
        """检测是否为登录界面1（账户登录）"""
        try:
            if self.find_one(Features.LOGIN_SCREEN_1_INDICATOR, threshold=0.6):
                return True
        except ValueError:
            pass

        if texts is None:
            texts = self._get_ocr_texts()
        if texts:
            # 只需写简体中文，find_boxes会自动调用LangConverter转换为双语模式
            has_login = self.find_boxes(texts, match=re.compile(r"登陆|登录"))
            has_account = self.find_boxes(texts, match=re.compile(r"账户名|账号"))
            has_enter_game = self.find_boxes(texts, match=re.compile(r"进入游戏"))

            if has_login and has_account:
                return True
            if has_login and has_enter_game:
                return True

        return False

    def _check_login_screen_2(self, texts=None):
        """检测是否为登录界面2（开始游戏）"""
        try:
            if self.find_one(Features.LOGIN_SCREEN_2_INDICATOR, threshold=0.6):
                return True
        except ValueError:
            pass

        if texts is None:
            texts = self._get_ocr_texts()
        if texts:
            # 只需写简体中文，find_boxes会自动转换为双语模式
            has_start_game = self.find_boxes(texts, match=re.compile(r"开始游戏"))
            has_change_server = self.find_boxes(texts, match=re.compile(r"换区"))

            if has_start_game and has_change_server:
                return True

        return False

    # ==================== 协议勾选处理（公共方法） ====================

    def _handle_agreement_checkbox(self):
        """
        处理协议勾选框

        通过 YOLO 检测复选框状态：
        1. YOLO 多次检测确认（提高准确性）
        2. OCR 文本定位作为备选方案

        Returns:
            bool: True 如果协议已勾选或成功勾选
        """
        # 方法1：YOLO 多次检测确认机制
        detection_result = self._detect_checkbox_with_confirmation()

        if detection_result['state'] == 'checked':
            self.log_info("协议勾选框已勾选（YOLO检测确认），跳过点击")
            return True
        elif detection_result['state'] == 'unchecked':
            self.log_info("协议勾选框未勾选（YOLO检测确认），尝试点击勾选...")
            if detection_result['box']:
                box = detection_result['box']
                # 计算勾选框中心点的相对坐标
                click_x = (box.x + box.width / 2) / self.width
                click_y = (box.y + box.height / 2) / self.height
                self.log_info(f"YOLO定位勾选框: 点击位置: ({click_x:.3f}, {click_y:.3f})")
                self.click_relative(click_x, click_y, after_sleep=0.3)
                self.sleep(0.3)
            return True

        # 方法2：如果 YOLO 检测不确定，使用 OCR 定位
        self.log_info("YOLO检测置信度不足，尝试通过OCR定位...")
        checkbox_label = self._find_checkbox_label_by_ocr()
        if checkbox_label:
            click_x, click_y = self._calculate_checkbox_click_position(checkbox_label)
            self.log_info(f"OCR定位勾选框: 点击位置: ({click_x:.3f}, {click_y:.3f})")
            self.click_relative(click_x, click_y, after_sleep=0.3)
            self.sleep(0.3)

        return True

    def _detect_checkbox_with_confirmation(self, confirm_count=3):
        """
        多次检测确认复选框状态（使用 YOLO 检测）

        通过多次检测取多数结果来提高准确性

        Args:
            confirm_count: 确认次数

        Returns:
            dict: {'state': 'checked'|'unchecked'|'unknown', 'box': Box|None, 'confidence': float}
        """
        # 检查 YOLO 检测器是否可用
        if self._checkbox_detector is None:
            self.log_info("YOLO勾选框检测器未初始化，尝试初始化...")
            self._init_checkbox_detector()
            if self._checkbox_detector is None:
                self.log_error("YOLO勾选框检测器初始化失败，使用OCR备选方案")
                return {'state': 'unknown', 'box': None, 'confidence': 0.0}

        checked_count = 0
        unchecked_count = 0
        checked_boxes = []
        unchecked_boxes = []

        for i in range(confirm_count):
            self.next_frame()
            if self.frame is None:
                continue

            # 使用 YOLO 检测勾选框
            try:
                detections = self._checkbox_detector.detect(
                    self.frame,
                    threshold=self.CHECKBOX_CONF_THRESHOLD
                )

                for det in detections:
                    if det.class_id == self.CHECKBOX_LABEL_CHECKED:
                        # 已勾选
                        checked_count += 1
                        # 创建兼容的 Box 对象
                        box = self._create_box_from_detection(det)
                        checked_boxes.append((box, det.confidence))
                        self.log_info(f"YOLO检测[{i+1}] 已勾选框，置信度: {det.confidence:.3f}")
                    elif det.class_id == self.CHECKBOX_LABEL_UNCHECKED:
                        # 未勾选
                        unchecked_count += 1
                        box = self._create_box_from_detection(det)
                        unchecked_boxes.append((box, det.confidence))
                        self.log_info(f"YOLO检测[{i+1}] 未勾选框，置信度: {det.confidence:.3f}")
            except Exception as e:
                self.log_error(f"YOLO检测异常: {e}")

            time.sleep(0.05)

        # 根据多数结果判断
        self.log_info(f"YOLO多次检测统计: 已勾选={checked_count}次, 未勾选={unchecked_count}次")

        if checked_count > unchecked_count:
            # 已勾选占多数
            best_box = max(checked_boxes, key=lambda x: x[1])[0] if checked_boxes else None
            return {'state': 'checked', 'box': best_box, 'confidence': checked_count / confirm_count}
        elif unchecked_count > checked_count:
            # 未勾选占多数
            best_box = max(unchecked_boxes, key=lambda x: x[1])[0] if unchecked_boxes else None
            return {'state': 'unchecked', 'box': best_box, 'confidence': unchecked_count / confirm_count}
        else:
            # 无法确定，使用置信度比较
            if checked_boxes and unchecked_boxes:
                avg_checked = sum(c for _, c in checked_boxes) / len(checked_boxes)
                avg_unchecked = sum(c for _, c in unchecked_boxes) / len(unchecked_boxes)
                if avg_checked > avg_unchecked + 0.1:
                    return {'state': 'checked', 'box': checked_boxes[0][0], 'confidence': avg_checked}
                elif avg_unchecked > avg_checked + 0.1:
                    return {'state': 'unchecked', 'box': unchecked_boxes[0][0], 'confidence': avg_unchecked}
            return {'state': 'unknown', 'box': None, 'confidence': 0.0}

    def _create_box_from_detection(self, detection):
        """
        从 YOLO 检测结果创建兼容的 Box 对象

        Args:
            detection: DetectionResult 对象

        Returns:
            Box: 兼容的 Box 对象
        """
        class Box:
            def __init__(self, x, y, width, height, confidence):
                self.x = x
                self.y = y
                self.width = width
                self.height = height
                self.confidence = confidence

        return Box(
            x=detection.x,
            y=detection.y,
            width=detection.width,
            height=detection.height,
            confidence=detection.confidence
        )

    def _find_checkbox_label_by_ocr(self):
        """通过 OCR 查找复选框标签文本"""
        texts = self._get_ocr_texts()
        checkbox_label = self.find_boxes(texts, match=re.compile(r"我已详细阅读并同意"))
        return checkbox_label[0] if checkbox_label else None

    def _calculate_checkbox_click_position(self, label):
        """计算复选框点击位置"""
        click_x = (label.x - int(label.height * 2)) / self.width
        click_y = (label.y + label.height * 0.5) / self.height
        return click_x, click_y

    # ==================== 登录界面处理 ====================

    def _click_button_by_ocr(self, button_name, regex_pattern, relative_y=0.78):
        """通过 OCR 查找并点击按钮"""
        texts = self._get_ocr_texts()
        boxes = self.find_boxes(texts, match=regex_pattern)

        if boxes:
            box = boxes[0]
            self.log_info(f"找到'{button_name}'按钮(OCR)")
            self.log_info(f"  原始位置: x={box.x}, y={box.y}, width={box.width}, height={box.height}")
            self.log_info(f"  屏幕尺寸: width={self.width}, height={self.height}")

            click_x = (box.x + box.width / 2) / self.width
            click_y = (box.y + box.height / 2) / self.height
            self.log_info(f"  相对位置: ({click_x:.4f}, {click_y:.4f})")

            abs_x = int(box.x + box.width / 2)
            abs_y = int(box.y + box.height / 2)
            self.log_info(f"  绝对位置: ({abs_x}, {abs_y})")

            try:
                interaction = self.executor.interaction
                self.log_info(f"  interaction 类型: {type(interaction).__name__}")
                self.log_info(f"  interaction.hwnd: {interaction.hwnd if hasattr(interaction, 'hwnd') else 'N/A'}")

                if hasattr(interaction, 'hwnd_window'):
                    hwnd_window = interaction.hwnd_window
                    self.log_info(f"  hwnd_window.visible: {hwnd_window.visible if hwnd_window else 'N/A'}")
                    self.log_info(f"  hwnd_window.exists: {hwnd_window.exists if hwnd_window else 'N/A'}")
                    if hwnd_window:
                        self.log_info(f"  hwnd_window.x: {hwnd_window.x}, hwnd_window.y: {hwnd_window.y}")
                        self.log_info(f"  hwnd_window.width: {hwnd_window.width}, hwnd_window.height: {hwnd_window.height}")

                        if not hwnd_window.visible:
                            self.log_info("  窗口不可见，尝试恢复窗口...")
                            self._ensure_window_visible(hwnd_window)
            except Exception as e:
                self.log_error(f"  获取 interaction 信息失败: {e}")

            self.log_info(f"  调用 click_relative...")
            result = self.click_relative(click_x, click_y, after_sleep=1)
            self.log_info(f"  click_relative 返回值: {result}")
            return True

        return False

    def _ensure_window_visible(self, hwnd_window):
        """
        确保窗口可见
        
        注意：在后台模式下不执行窗口恢复操作
        """
        # 后台模式下不恢复窗口
        if background_manager.is_background_mode():
            self.log_info("  后台模式：跳过窗口恢复操作")
            return True
        
        try:
            import win32gui
            import win32con

            hwnd = hwnd_window.hwnd
            if not hwnd:
                return False

            is_minimized = hwnd_window.is_minimized() if hasattr(hwnd_window, 'is_minimized') else False

            if is_minimized or not hwnd_window.visible:
                self.log_info(f"  恢复窗口: hwnd={hwnd}, minimized={is_minimized}, visible={hwnd_window.visible}")
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.5)

                self.log_info(f"  窗口已恢复: visible={win32gui.IsWindowVisible(hwnd)}")
                return True
        except Exception as e:
            self.log_error(f"  恢复窗口失败: {e}")

        return False

    def _handle_login_screen_ex(self):
        """处理登录界面EX - 快进按钮"""
        self.log_info("处理登录界面EX - 点击快进按钮")

        # 尝试点击快进按钮
        try:
            skip_button = self.find_one(Features.SKIP_BUTTON, threshold=0.55)
            if skip_button:
                self.log_info("找到快进按钮(特征)，点击...")
                self.click(skip_button, after_sleep=1)
                return True
        except ValueError:
            pass

        self.logger.warning(f"[{self.name}] 未找到快进按钮")
        return False

    def _handle_login_screen_0(self):
        """处理登录界面0 - 适龄提示"""
        self.log_info("处理登录界面0 - 检查协议勾选并点击进入游戏")

        # 使用公共方法处理协议勾选
        self._handle_agreement_checkbox()

        # 尝试点击进入游戏按钮
        try:
            enter_game = self.find_one(Features.ENTER_GAME_BUTTON, threshold=0.7)
            if enter_game:
                self.log_info("找到'进入游戏'按钮(特征)，点击...")
                self.click(enter_game, after_sleep=1)
                return True
        except ValueError:
            pass

        # 只需写简体中文，find_boxes会自动转换为双语模式
        if self._click_button_by_ocr("进入游戏", re.compile(r"进入游戏")):
            return True

        self.logger.warning(f"[{self.name}] 未找到'进入游戏'按钮")
        return False

    def _handle_login_screen_1(self):
        """处理登录界面1 - 账户登录"""
        self.log_info("处理登录界面1 - 点击进入游戏")

        # 处理账号输入（如需要）
        if self._cfg('输入账号', False) and not self._account_input_done:
            account = self._cfg('账号', '')
            if account:
                self._input_account(account)
                self._account_input_done = True
                self.log_info("账号输入完成，立即尝试点击'进入游戏'")
                # 不再返回，直接继续尝试点击按钮

        # 尝试点击进入游戏按钮
        try:
            enter_game = self.find_one(Features.ENTER_GAME_BUTTON, threshold=0.7)
            if enter_game:
                self.log_info("找到'进入游戏'按钮(特征)，点击...")
                self.click(enter_game, after_sleep=1)
                return True
        except ValueError:
            pass

        if self._click_button_by_ocr("进入游戏", re.compile(r"进入游戏")):
            return True

        self.logger.warning(f"[{self.name}] 未找到'进入游戏'按钮")
        return False

    def _handle_login_screen_2(self):
        """处理登录界面2 - 开始游戏"""
        self.log_info("处理登录界面2 - 检查协议勾选并点击开始游戏")

        # 使用公共方法处理协议勾选
        self._handle_agreement_checkbox()

        # 尝试点击开始游戏按钮
        try:
            start_game = self.find_one(Features.START_GAME_BUTTON, threshold=0.7)
            if start_game:
                self.log_info("找到'开始游戏'按钮(特征)，点击...")
                self.click(start_game, after_sleep=2)

                if self._wait_for_character_selection():
                    self.log_info("检测到角色选择界面，登录成功")
                    self._logged_in = True
                    self.info_set('登录状态', '已登录')
                    return True
                return True
        except ValueError:
            pass

        if self._click_button_by_ocr("开始游戏", re.compile(r"开始游戏")):
            self.sleep(2)
            if self._wait_for_character_selection():
                self.log_info("检测到角色选择界面，登录成功")
                self._logged_in = True
                self.info_set('登录状态', '已登录')
                return True
            return True

        self.logger.warning(f"[{self.name}] 未找到'开始游戏'按钮")
        return False

    def _wait_for_character_selection(self, timeout=5.0):
        """
        等待角色选择界面

        Args:
            timeout: 超时时间（秒）

        Returns:
            bool: True 如果检测到角色选择界面
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                xuanren = self.find_one(Features.XUANREN, threshold=0.6)
                if xuanren:
                    self.log_info("模板匹配检测到角色选择界面")
                    return True
            except ValueError:
                pass

            self.next_frame()
            self._clear_ocr_cache()
            texts = self._get_ocr_texts()

            patterns = [
                re.compile(r"请选择一位你心仪的角色"),
                re.compile(r"请选择.*心仪的角色"),
                re.compile(r"选择.*角色"),
                re.compile(r"心仪的角色"),
            ]

            for pattern in patterns:
                select_char = self.find_boxes(texts, match=pattern)
                if select_char and len(select_char) > 0:
                    self.log_info("OCR检测到角色选择界面")
                    return True

            time.sleep(0.5)

        return False

    def _handle_unknown_screen(self):
        """处理未知界面"""
        self.log_info("处理未知界面 - 尝试通用按钮")

        # 只需写简体中文，find_boxes会自动转换为双语模式
        if self._click_button_by_ocr("进入游戏", re.compile(r"进入游戏")):
            return True

        if self._click_button_by_ocr("开始游戏", re.compile(r"开始游戏")):
            return True

        if self._click_button_by_ocr("登录", re.compile(r"登陆|登录")):
            return True

        self.logger.warning(f"[{self.name}] 未找到任何可点击的按钮")
        return False

    # ==================== 账号输入 ====================

    def _set_clipboard(self, text):
        """设置剪贴板内容"""
        try:
            import win32clipboard
            import win32con
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, str(text))
            win32clipboard.CloseClipboard()
            return True
        except Exception as e:
            self.log_error(f"设置剪贴板失败: {e}")
            return False

    def _input_account(self, account):
        """输入账号"""
        self.log_info("尝试输入账号...")
        start_time = time.time()

        try:
            # 强制重新截图和清空OCR缓存，确保使用最新的界面
            self.log_debug("账号输入前重新截图...")
            self.next_frame()
            self._clear_ocr_cache()
            
            input_box = self._locate_account_input_box(self.ACCOUNT_INPUT_MATCH_TIMEOUT)
            if input_box is None:
                self.log_info("模板匹配失败，尝试使用OCR定位输入框...")
                # 再次清空缓存，确保OCR使用最新截图
                self._clear_ocr_cache()
                input_box = self._locate_account_input_box_by_ocr()

            if input_box is None:
                raise AutoLoginInputException("账号输入框识别超时")

            screen_width, screen_height = self._get_screen_size()
            self._assert_account_input_timeout(start_time)
            click_x = (input_box['x'] + input_box['width'] / 2) / screen_width
            click_y = (input_box['y'] + input_box['height'] / 2) / screen_height
            self.log_info(f"点击输入框位置: ({click_x:.3f}, {click_y:.3f})")
            click_result = self.click_relative(click_x, click_y)
            if click_result is False:
                raise AutoLoginInputException("账号输入框激活失败")

            self.sleep(0.5)

            max_retries = max(1, int(self._cfg('账号输入重试次数', 3)))
            for attempt in range(1, max_retries + 1):
                self._assert_account_input_timeout(start_time)

                # 使用 input_text_with_clear 方法（自动清空后输入）
                self.log_info(f"开始输入账号(第{attempt}次): {account[:3]}***")

                if self._is_adb_interaction():
                    self.log_info("ADB模式: 使用 input_text_with_clear...")
                    success = self.input_text_with_clear(str(account), clear_first=True)
                else:
                    self.log_info("PC模式: 先清空后输入...")
                    # PC 模式也使用 input_text_with_clear
                    success = self.input_text_with_clear(str(account), clear_first=True)

                self.sleep(0.5)

                if self._verify_account_input(account):
                    self.send_key('tab')
                    self.log_info(f"账号已输入(精确校验成功): {account[:3]}***")
                    return True
                self.logger.warning(f"[{self.name}] 账号输入校验失败，重试 {attempt}/{max_retries}")
                self.sleep(0.5)

            raise AutoLoginInputException("账号输入校验失败，内容与GUI配置不匹配")
        except AutoLoginInputException as e:
            self._save_error_screenshot(str(e))
            self.log_error(f"输入账号失败: {e}")
            raise
        except Exception as e:
            self._save_error_screenshot("账号输入异常")
            self.log_error(f"输入账号失败: {e}")
            raise AutoLoginInputException(f"账号输入异常: {e}") from e

    def _clear_input_pc(self):
        """
        PC 模式下清空输入框

        使用 Ctrl+A 全选 + Backspace 删除

        Returns:
            bool: True 如果清空成功
        """
        try:
            self.log_info("执行全选操作...")
            self.send_key_down('ctrl')
            self.send_key('a')
            self.send_key_up('ctrl')
            self.sleep(0.2)

            self.log_info("执行清除操作...")
            self.send_key('backspace')
            self.sleep(0.3)
            return True
        except Exception as e:
            self.log_error(f"PC模式清空失败: {e}")
            return False

    def _clear_input_adb(self):
        """
        ADB 模式下清空输入框

        模拟器环境下 Ctrl+A 可能不生效，使用多种方法尝试：
        1. 使用 uiautomator2 直接清空（最可靠）
        2. 多次发送删除键
        3. 双击选中 + 删除

        Returns:
            bool: True 如果清空成功
        """
        # 方法1：使用 uiautomator2 直接设置空文本（最可靠）
        try:
            self.log_info("ADB清空方法1: 使用 uiautomator2 清空...")
            if self._clear_with_u2():
                self.log_info("uiautomator2 清空成功")
                return True
        except Exception as e:
            self.log_info(f"uiautomator2 清空失败: {e}")

        # 方法2：多次发送删除键（简单可靠）
        try:
            self.log_info("ADB清空方法2: 多次删除键清空...")
            self._clear_with_multiple_backspace()
            self.log_info("多次删除键清空完成")
            return True
        except Exception as e:
            self.log_info(f"多次删除键清空失败: {e}")

        # 方法3：双击选中 + 删除
        try:
            self.log_info("ADB清空方法3: 双击选中+删除...")
            self._clear_with_double_click()
            self.log_info("双击选中+删除完成")
            return True
        except Exception as e:
            self.log_info(f"双击选中+删除失败: {e}")

        return False

    def _clear_with_u2(self):
        """
        使用 uiautomator2 清空输入框

        通过点击输入框后使用 u2.clear_text() 清空

        Returns:
            bool: True 如果成功
        """
        try:
            # 获取 uiautomator2 实例
            interaction = self.executor.interaction
            if hasattr(interaction, 'u2'):
                u2 = interaction.u2
                # 点击输入框获取焦点
                # 然后使用 u2 清空文本
                # 注意：需要先点击输入框获取焦点
                u2.clear_text()
                self.log_info("u2.clear_text() 执行成功")
                return True
            else:
                self.log_info("uiautomator2 不可用")
                return False
        except Exception as e:
            self.log_error(f"uiautomator2 清空异常: {e}")
            return False

    def _clear_with_multiple_backspace(self, count=50):
        """
        通过多次发送删除键清空输入框

        这是最简单但相对可靠的方法

        Args:
            count: 删除键发送次数
        """
        try:
            # Android KEYCODE_DEL = 67
            # 使用框架的 send_key 方法
            for i in range(count):
                self.send_key('KEYCODE_DEL', after_sleep=0.01)
                # 每10次输出一次进度
                if (i + 1) % 10 == 0:
                    self.log_info(f"已发送 {i + 1} 次删除键")
        except Exception as e:
            self.log_error(f"多次删除键异常: {e}")

    def _clear_with_double_click(self):
        """
        通过双击选中输入框内容后删除

        双击通常会选中输入框中的所有文本
        """
        try:
            # 获取输入框位置
            texts = self._get_ocr_texts()
            # 只需写简体中文，find_boxes会自动转换为双语模式
            account_boxes = self.find_boxes(texts, match=re.compile(r"账户名|账号"))

            if account_boxes:
                box = account_boxes[0]
                # 输入框通常在标签下方
                click_x = (box.x + box.width / 2) / self.width
                click_y = (box.y + box.height * 2.5) / self.height
            else:
                # 使用默认位置（屏幕中上部）
                click_x, click_y = 0.5, 0.35

            self.log_info(f"双击位置: ({click_x:.3f}, {click_y:.3f})")

            # 双击选中
            self.click_relative(click_x, click_y)
            time.sleep(0.1)
            self.click_relative(click_x, click_y)
            time.sleep(0.3)

            # 删除选中的内容
            self.send_key('KEYCODE_DEL', after_sleep=0.2)

        except Exception as e:
            self.log_error(f"双击选中+删除异常: {e}")

    def _get_screen_size(self):
        """获取屏幕尺寸"""
        width = None
        height = None
        try:
            width = self.width
            height = self.height
        except Exception:
            pass

        if width and height:
            return width, height

        if self.frame is not None:
            frame_height, frame_width = self.frame.shape[:2]
            return frame_width, frame_height

        raise AutoLoginInputException("无法获取屏幕尺寸")

    def _assert_account_input_timeout(self, start_time):
        """检查账号输入是否超时"""
        elapsed = time.time() - start_time
        if elapsed > self.ACCOUNT_INPUT_TOTAL_TIMEOUT:
            raise AutoLoginInputException(f"账号输入超时({elapsed:.2f}s)")

    def _verify_account_input(self, expected_account):
        """验证账号输入"""
        expected = str(expected_account).strip()
        if not expected:
            return False

        verify_timeout = self._cfg('输入校验超时(秒)', self.ACCOUNT_INPUT_VERIFY_TIMEOUT)
        verify_timeout = max(0.2, min(float(verify_timeout), 1.5))
        start_time = time.time()

        while time.time() - start_time < verify_timeout:
            try:
                self.next_frame()
                texts = self._get_ocr_texts()
                if not texts:
                    self.sleep(0.05)
                    continue

                for text_box in texts:
                    if text_box.name and expected in text_box.name:
                        self.log_info(f"OCR验证成功，找到账号: {text_box.name}")
                        return True

                self.sleep(0.1)
            except Exception:
                self.sleep(0.05)

        self.log_info("OCR验证未找到匹配账号，跳过校验继续执行")
        return True

    def _locate_account_input_box(self, timeout):
        """定位账号输入框（模板匹配）"""
        template_path = self._resolve_account_input_template_path()
        self.log_info(f"账号输入框模板路径: {template_path}")
        template = cv2.imread(template_path)
        if template is None:
            raise AutoLoginInputException(f"无法加载输入框模板: {template_path}")

        template_gray = self._to_gray(template)
        template_height, template_width = template_gray.shape[:2]

        start_time = time.time()

        while time.time() - start_time <= timeout:
            self.next_frame()
            if self.frame is None:
                time.sleep(0.02)
                continue

            frame_gray = self._to_gray(self.frame)
            result = cv2.matchTemplate(frame_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            _, confidence, _, top_left = cv2.minMaxLoc(result)

            if confidence >= self.ACCOUNT_INPUT_MATCH_THRESHOLD:
                self.log_info(f"识别到账号输入框，置信度: {confidence:.3f}")
                return {
                    'x': top_left[0],
                    'y': top_left[1],
                    'width': template_width,
                    'height': template_height,
                    'confidence': confidence
                }

            time.sleep(0.02)

        return None

    def _locate_account_input_box_by_ocr(self):
        """通过 OCR 定位账号输入框（自动支持简繁中文）"""
        texts = self._get_ocr_texts()
        if not texts:
            self.log_debug("OCR未识别到任何文本")
            return None

        # 只需写简体中文，find_boxes会自动调用LangConverter转换为双语模式
        account_label = self.find_boxes(texts, match=re.compile(r"账户名|账号"))
        if not account_label:
            self.log_debug("未找到账户名标签，尝试备用标签...")
            # 尝试查找其他可能的标签
            alt_labels = [
                self.find_boxes(texts, match=re.compile(r"账户")),
                self.find_boxes(texts, match=re.compile(r"用户名")),
                self.find_boxes(texts, match=re.compile(r"账号输入")),
            ]
            for labels in alt_labels:
                if labels:
                    account_label = labels
                    self.log_info(f"找到备用标签: {labels[0].name}")
                    break
        
        if not account_label:
            self.log_debug("所有账户名标签查找均失败")
            return None

        label = account_label[0]
        self.log_info(f"找到账户名标签: {label.name} at ({label.x}, {label.y})")

        input_box_y = label.y + label.height + int(self.height * 0.02)
        input_box_x = label.x
        input_box_width = int(self.width * 0.25)
        input_box_height = int(self.height * 0.035)

        self.log_info(f"通过OCR定位输入框: x={input_box_x}, y={input_box_y}, width={input_box_width}, height={input_box_height}")

        return {
            'x': input_box_x,
            'y': input_box_y,
            'width': input_box_width,
            'height': input_box_height,
            'confidence': 0.9
        }

    def _to_gray(self, image):
        """将图像转换为灰度"""
        if image is None:
            return None
        if len(image.shape) == 2:
            return image
        if image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # ==================== 状态检测 ====================

    def _check_login_success(self):
        """检查是否登录成功"""
        if self.in_lobby():
            return True

        if self.in_game():
            return True

        try:
            success_indicator = self.find_one(Features.SUCCESS_ENTER, threshold=0.7)
            if success_indicator:
                self.log_info("检测到成功进入游戏界面(特征匹配)")
                return True
        except ValueError:
            pass

        texts = self._get_ocr_texts()

        role_text = self.find_boxes(texts, match=re.compile(r"角色"))
        rank_text = self.find_boxes(texts, match=re.compile(r"排位赛"))

        if role_text is not None and len(role_text) > 0 and rank_text is not None and len(rank_text) > 0:
            self.log_info("检测到成功进入游戏界面(OCR: 角色 + 排位赛)")
            return True

        return False

    def _check_login_error(self):
        """检查是否有登录错误"""
        texts = self._get_ocr_texts()

        error_keywords = ['登陆失败', '登录失败', '网络错误', '连接失败', '账号或密码错误', '服务器维护', '连接超时']

        for keyword in error_keywords:
            error_box = self.find_boxes(texts, match=re.compile(keyword))
            if error_box:
                return keyword

        return None

    # ==================== 错误处理 ====================

    def _save_error_screenshot(self, error_text):
        """保存错误截图"""
        self._error_count += 1

        safe_name = re.sub(r'[\\/:*?"<>|]', '_', error_text)
        filename = f"{safe_name}{self._error_count}.png"
        filepath = os.path.join(self._screenshots_dir, filename)

        if self.frame is not None:
            cv2.imwrite(filepath, self.frame)
            self.log_error(f"错误截图已保存: {filepath}")

            self._send_error_report(error_text, filepath)

        return filepath

    def _send_error_report(self, error_text, screenshot_path):
        """发送错误报告"""
        self.log_error(f"=" * 50)
        self.log_error(f"登录错误报告")
        self.log_error(f"=" * 50)
        self.log_error(f"错误类型: {error_text}")
        self.log_error(f"截图文件: {screenshot_path}")
        self.log_error(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log_error(f"=" * 50)

        self.log_info(f"通知: 登录错误 - {error_text}")

    def reset_login_state(self):
        """重置登录状态"""
        self._logged_in = False
        self._error_count = 0
        self._cached_ocr = None
        self._last_error = None
        self._account_input_done = False
        self._unknown_screen_count = 0  # 重置未知界面计数

    # ==================== 问卷调查处理 ====================

    def _check_wenjuan_screen(self):
        """检测是否为问卷调查界面"""
        try:
            wenjuan_enter = self.find_one(Features.WENJUAN_ENTER, threshold=0.7)
            if wenjuan_enter:
                return True
        except ValueError:
            pass

        texts = self._get_ocr_texts()
        wenjuan_keywords = ['问卷调查', '问卷', '调查', '感谢您的耐心回答']
        for keyword in wenjuan_keywords:
            boxes = self.find_boxes(texts, match=re.compile(keyword))
            if boxes and len(boxes) > 0:
                return True

        return False

    def _handle_wenjuan(self):
        """处理问卷调查"""
        self.log_info("开始处理问卷调查场景...")

        # 等待问卷加载
        start_time = time.time()
        while time.time() - start_time < self.WENJUAN_WAIT_TIMEOUT:
            self.next_frame()
            self._clear_ocr_cache()

            try:
                wenjuan_end = self.find_one(Features.WENJUAN_END, threshold=0.6)
                if wenjuan_end:
                    self.log_info("检测到'返回游戏'按钮，问卷内容已加载")
                    break
            except ValueError:
                pass

            texts = self._get_ocr_texts()
            return_game = self.find_boxes(texts, match=re.compile(r"返回游戏"))
            if return_game and len(return_game) > 0:
                self.log_info("OCR检测到'返回游戏'按钮")
                break

            time.sleep(0.5)
        else:
            self.logger.warning(f"[{self.name}] 等待问卷加载超时")
            return False

        self.sleep(3)

        # 处理问卷选项
        wenjuan_steps = [
            (Features.WENJUAN_OPTION_1, '问卷选项1'),
            (Features.WENJUAN_OPTION_2, '问卷选项2'),
            (Features.WENJUAN_OPTION_3, '问卷选项3'),
            (Features.WENJUAN_SUBMIT, '提交按钮'),
        ]

        for template_name, step_name in wenjuan_steps:
            if not self._click_wenjuan_option(template_name, step_name):
                self.logger.warning(f"[{self.name}] {step_name}识别失败，跳过")
            self.sleep(0.5)

        # 等待感谢界面
        start_time = time.time()
        while time.time() - start_time < 10:
            self.next_frame()
            self._clear_ocr_cache()

            try:
                wenjuan_end2 = self.find_one(Features.WENJUAN_END2, threshold=0.6)
                if wenjuan_end2:
                    self.log_info("检测到'感谢您的耐心回答'")
                    break
            except ValueError:
                pass

            texts = self._get_ocr_texts()
            thanks = self.find_boxes(texts, match=re.compile(r"感谢您的耐心回答"))
            if thanks and len(thanks) > 0:
                self.log_info("OCR检测到'感谢您的耐心回答'")
                break

            time.sleep(0.5)

        # 点击返回游戏
        clicked_return = False
        try:
            wenjuan_end = self.find_one(Features.WENJUAN_END, threshold=0.6)
            if wenjuan_end:
                self.log_info("点击'返回游戏'按钮")
                self.click(wenjuan_end, after_sleep=1)
                clicked_return = True
        except ValueError:
            pass

        if not clicked_return:
            texts = self._get_ocr_texts()
            return_game = self.find_boxes(texts, match=re.compile(r"返回游戏"))
            if return_game and len(return_game) > 0:
                box = return_game[0]
                click_x = (box.x + box.width / 2) / self.width
                click_y = (box.y + box.height / 2) / self.height
                self.log_info(f"OCR定位点击'返回游戏': ({click_x:.3f}, {click_y:.3f})")
                self.click_relative(click_x, click_y, after_sleep=1)
                clicked_return = True

        if not clicked_return:
            self.logger.warning(f"[{self.name}] 未找到'返回游戏'按钮")
            return False

        self.sleep(2)

        # 等待角色选择界面
        start_time = time.time()
        while time.time() - start_time < 15:
            self.next_frame()
            self._clear_ocr_cache()

            try:
                xuanren = self.find_one(Features.XUANREN, threshold=0.6)
                if xuanren:
                    self.log_info("检测到角色选择界面，问卷调查完成")
                    return True
            except ValueError:
                pass

            texts = self._get_ocr_texts()
            select_char = self.find_boxes(texts, match=re.compile(r"请选择一位你心仪的角色"))
            if select_char and len(select_char) > 0:
                self.log_info("OCR检测到角色选择界面，问卷调查完成")
                return True

            time.sleep(0.5)

        self.logger.warning(f"[{self.name}] 未检测到角色选择界面")
        return False

    def _click_wenjuan_option(self, template_name, step_name):
        """点击问卷选项"""
        start_time = time.time()
        timeout = 10

        while time.time() - start_time < timeout:
            self.next_frame()
            self._clear_ocr_cache()

            clicked = False

            if template_name in [Features.WENJUAN_OPTION_1, Features.WENJUAN_OPTION_2, Features.WENJUAN_OPTION_3]:
                texts = self._get_ocr_texts()

                if template_name == Features.WENJUAN_OPTION_1:
                    patterns = [re.compile(r"至少有一部.*追到最新剧情")]
                elif template_name == Features.WENJUAN_OPTION_2:
                    patterns = [re.compile(r"王者10星及以上")]
                elif template_name == Features.WENJUAN_OPTION_3:
                    patterns = [re.compile(r"追求团队胜利.*段位和排名")]

                for pattern in patterns:
                    boxes = self.find_boxes(texts, match=pattern)
                    if boxes and len(boxes) > 0:
                        box = boxes[0]
                        click_x = (box.x + box.width / 2) / self.width
                        click_y = (box.y + box.height / 2) / self.height
                        self.log_info(f"OCR找到{step_name}: '{box.name}' at ({box.x}, {box.y})，点击...")
                        self.click_relative(click_x, click_y, after_sleep=0.5)
                        return True

            elif template_name == Features.WENJUAN_SUBMIT:
                try:
                    submit_btn = self.find_one(template_name, threshold=0.6)
                    if submit_btn:
                        self.log_info(f"模板匹配找到{step_name}，点击...")
                        self.click(submit_btn, after_sleep=0.5)
                        return True
                except ValueError:
                    pass

                texts = self._get_ocr_texts()
                # 使用 find_boxes 进行简繁双语匹配
                submit_boxes = self.find_boxes(texts, match=re.compile(r"提交|送出|确认"))
                if submit_boxes:
                    box = submit_boxes[0]
                    click_x = (box.x + box.width / 2) / self.width
                    click_y = (box.y + box.height / 2) / self.height
                    self.log_info(f"OCR匹配找到{step_name}: '{box.name}' at ({box.x}, {box.y})，点击...")
                    self.click_relative(click_x, click_y, after_sleep=0.5)
                    return True

            time.sleep(0.0)

        return False
