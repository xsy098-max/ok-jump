import os
import re
import time

import cv2

from ok import og

from src.task.BaseJumpTask import BaseJumpTask
from src.constants.features import Features
from src.utils.BackgroundManager import background_manager
from src.utils.BackgroundInputHelper import background_input


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
    """

    # 登录界面标识
    LOGIN_SCREEN_0 = 'login_screen_0'
    LOGIN_SCREEN_1 = 'login_screen_1'
    LOGIN_SCREEN_2 = 'login_screen_2'
    WENJUAN_SCREEN = 'wenjuan_screen'
    CHARACTER_SELECTION_SCREEN = 'character_selection_screen'

    # 账号输入相关常量
    ACCOUNT_INPUT_TEMPLATE_PATH = os.path.join('assets', 'images', 'login', 'input.png')
    ACCOUNT_INPUT_MATCH_THRESHOLD = 0.72
    ACCOUNT_INPUT_MATCH_TIMEOUT = 1.0
    ACCOUNT_INPUT_TOTAL_TIMEOUT = 3.0
    ACCOUNT_INPUT_KEY_DELAY_MIN = 0.05
    ACCOUNT_INPUT_KEY_DELAY_MAX = 0.15
    ACCOUNT_INPUT_VERIFY_TIMEOUT = 1.0
    WENJUAN_WAIT_TIMEOUT = 30.0

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
        self.default_config = {
            '启用': True,
            '自动启动游戏': False,
            '等待游戏启动(秒)': 120,
            '最大登录尝试次数': 5,
            '输入账号': False,
            '账号': '',
            '账号输入重试次数': 2,
            '输入校验超时(秒)': 1.0,
            '登录等待超时(秒)': 60,
            '点击后等待时间(秒)': 3,
        }
        self._ensure_screenshots_dir()

    def _cfg(self, key, default=None):
        """获取配置值"""
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

        self.info_set('登录状态', '登录成功')
        self.log_info("自动登录完成")
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
        """等待游戏窗口出现"""
        timeout = self._cfg('等待游戏启动(秒)', 120)
        self.log_info(f"等待游戏窗口... (最长 {timeout} 秒)")

        start_time = time.time()

        while time.time() - start_time < timeout:
            # 确保窗口可截图（后台模式下自动伪最小化）
            self.ensure_capturable()
            self.next_frame()
            if self.frame is not None:
                self.log_info("检测到游戏窗口")
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

    # ==================== 登录流程 ====================

    def _execute_login_flow(self):
        """执行登录流程"""
        timeout = self._cfg('登录等待超时(秒)', 60)
        max_attempts = self._cfg('最大登录尝试次数', 5)
        click_wait = self._cfg('点击后等待时间(秒)', 3)

        start_time = time.time()
        attempts = 0
        last_action = None
        last_action_time = 0

        while time.time() - start_time < timeout and attempts < max_attempts:
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
            
            self._clear_ocr_cache()

            if self._check_login_success():
                self._logged_in = True
                self.log_info("登录成功 - 已进入游戏")
                return True

            error_msg = self._check_login_error()
            if error_msg:
                self._last_error = error_msg
                self.log_error(f"检测到登录错误: {error_msg}")
                self._save_error_screenshot(error_msg)
                return False

            wenjuan_result = self._check_wenjuan_screen()
            if wenjuan_result:
                self.log_info("检测到问卷调查场景，开始处理...")
                if self._handle_wenjuan():
                    self.log_info("问卷调查处理完成，已进入角色选择界面")
                    self._logged_in = True
                    self.info_set('登录状态', '已登录')
                    return True
                else:
                    self.logger.warning(f"[{self.name}] 问卷调查处理失败，继续尝试...")

            current_screen = self._detect_login_screen()

            action = None
            if current_screen == self.LOGIN_SCREEN_0:
                action = self._handle_login_screen_0
            elif current_screen == self.LOGIN_SCREEN_1:
                action = self._handle_login_screen_1
            elif current_screen == self.LOGIN_SCREEN_2:
                action = self._handle_login_screen_2
            else:
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
                    return False
                if handled:
                    if self._logged_in:
                        self.log_info("登录成功 - 自动登录完成")
                        return True
                    attempts += 1
                    last_action = action
                    last_action_time = time.time()
                    self.log_info(f"执行点击操作，等待界面变化... (尝试 {attempts}/{max_attempts})")
                    self.info_set('登录状态', f'尝试 {attempts}/{max_attempts}')
                    self.sleep(click_wait)

        if attempts >= max_attempts:
            self._last_error = f"达到最大尝试次数 ({max_attempts})"

        return self._logged_in

    def _detect_login_screen(self):
        """检测当前登录界面类型"""
        texts = self._get_ocr_texts()

        if self._check_login_screen_0(texts):
            return self.LOGIN_SCREEN_0
        elif self._check_login_screen_1(texts):
            return self.LOGIN_SCREEN_1
        elif self._check_login_screen_2(texts):
            return self.LOGIN_SCREEN_2
        return None

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
            has_age_prompt = self.find_boxes(texts, match=re.compile(r"适龄提示"))
            has_enter_game = self.find_boxes(texts, match=re.compile(r"进入游戏"))
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
            has_start_game = self.find_boxes(texts, match=re.compile(r"开始游戏"))
            has_change_server = self.find_boxes(texts, match=re.compile(r"换区"))

            if has_start_game and has_change_server:
                return True

        return False

    # ==================== 协议勾选处理（公共方法） ====================

    def _handle_agreement_checkbox(self):
        """
        处理协议勾选框

        通过多种方式检测复选框状态：
        1. 多次模板匹配确认（提高准确性）
        2. OCR 文本定位作为备选方案
        3. 颜色特征辅助判断

        Returns:
            bool: True 如果协议已勾选或成功勾选
        """
        # 方法1：多次检测确认机制
        detection_result = self._detect_checkbox_with_confirmation()

        if detection_result['state'] == 'checked':
            self.log_info("协议勾选框已勾选（多次检测确认），跳过点击")
            return True
        elif detection_result['state'] == 'unchecked':
            self.log_info("协议勾选框未勾选（多次检测确认），尝试点击勾选...")
            if detection_result['box']:
                self.click(detection_result['box'], after_sleep=0.3)
                self.sleep(0.3)
            return True

        # 方法2：如果模板匹配不确定，使用 OCR 定位
        self.log_info("模板匹配置信度接近或均未检测到，尝试通过OCR定位...")
        checkbox_label = self._find_checkbox_label_by_ocr()
        if checkbox_label:
            click_x, click_y = self._calculate_checkbox_click_position(checkbox_label)
            self.log_info(f"OCR定位勾选框: 点击位置: ({click_x:.3f}, {click_y:.3f})")
            self.click_relative(click_x, click_y, after_sleep=0.3)
            self.sleep(0.3)

        return True

    def _detect_checkbox_with_confirmation(self, confirm_count=3):
        """
        多次检测确认复选框状态

        通过多次检测取多数结果来提高准确性

        Args:
            confirm_count: 确认次数

        Returns:
            dict: {'state': 'checked'|'unchecked'|'unknown', 'box': Box|None, 'confidence': float}
        """
        checked_count = 0
        unchecked_count = 0
        checked_boxes = []
        unchecked_boxes = []

        for i in range(confirm_count):
            self.next_frame()

            # 检测已勾选状态
            try:
                checked_box = self.find_one(Features.RENZHEN_CHECKED, threshold=0.6)
                if checked_box:
                    checked_conf = checked_box.confidence if hasattr(checked_box, 'confidence') else 0.8
                    if checked_conf > 0.6:
                        checked_count += 1
                        checked_boxes.append((checked_box, checked_conf))
                        self.log_info(f"检测[{i+1}] 已勾选框，置信度: {checked_conf:.3f}")
            except ValueError:
                pass

            # 检测未勾选状态
            try:
                unchecked_box = self.find_one(Features.RENZHEN_UNCHECKED, threshold=0.6)
                if unchecked_box:
                    unchecked_conf = unchecked_box.confidence if hasattr(unchecked_box, 'confidence') else 0.8
                    if unchecked_conf > 0.6:
                        unchecked_count += 1
                        unchecked_boxes.append((unchecked_box, unchecked_conf))
                        self.log_info(f"检测[{i+1}] 未勾选框，置信度: {unchecked_conf:.3f}")
            except ValueError:
                pass

            time.sleep(0.05)

        # 根据多数结果判断
        self.log_info(f"多次检测统计: 已勾选={checked_count}次, 未勾选={unchecked_count}次")

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
            input_box = self._locate_account_input_box(self.ACCOUNT_INPUT_MATCH_TIMEOUT)
            if input_box is None:
                self.log_info("模板匹配失败，尝试使用OCR定位输入框...")
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
        """通过 OCR 定位账号输入框"""
        texts = self._get_ocr_texts()
        if not texts:
            return None

        account_label = self.find_boxes(texts, match=re.compile(r"账户名|账号"))
        if not account_label:
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
                for box in texts:
                    if box.name == "提交":
                        click_x = (box.x + box.width / 2) / self.width
                        click_y = (box.y + box.height / 2) / self.height
                        self.log_info(f"OCR精确匹配找到{step_name}: '{box.name}' at ({box.x}, {box.y})，点击...")
                        self.click_relative(click_x, click_y, after_sleep=0.5)
                        return True

            time.sleep(0.0)

        return False
