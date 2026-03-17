import re
import time

from ok import BaseTask, og

from src.task.mixins import JumpTaskMixin
from src.constants.features import Features
from src.utils.BackgroundManager import background_manager
from src.utils.BackgroundInputHelper import background_input
from src.utils.PseudoMinimizeHelper import pseudo_minimize_helper
from src.utils.LangConverter import LangConverter


class BaseJumpTask(BaseTask, JumpTaskMixin):
    """
    漫画群星一次性任务基类

    继承 BaseTask 和 JumpTaskMixin，提供：
    - 游戏状态检测（in_game, in_lobby）
    - 分辨率自适应
    - 后台模式支持
    - 登录等待机制
    - 伪最小化处理
    """

    def __init__(self, *args, **kwargs):
        BaseTask.__init__(self, *args, **kwargs)
        self._init_mixin_vars()
        self.name = "BaseJumpTask"
        self.description = "漫画群星任务基类"
        self._logged_in = False

    # ==================== 截图功能 ====================

    def take_screenshot(self):
        """
        获取当前截图

        Returns:
            numpy.ndarray: 当前帧图像，如果不可用则返回 None
        """
        if self.frame is not None:
            self.screenshot = self.frame
            return self.frame
        return None

    def click_relative(self, x, y, *args, **kwargs):
        """
        点击相对坐标位置（智能后台支持）

        根据游戏窗口状态自动选择最优的点击方式：
        - 后台/伪最小化：使用 SendInput
        - 前台：使用框架方法

        Args:
            x: 相对 X 坐标 (0-1)
            y: 相对 Y 坐标 (0-1)
            *args, **kwargs: 传递给父类 click_relative 的参数

        Returns:
            点击操作的返回值
        """
        # 检查是否需要后台点击
        if self._need_background_click():
            after_sleep = kwargs.get('after_sleep', 0.5)
            return self.background_click_relative(x, y, after_sleep=after_sleep)
        
        # 前台模式使用框架方法
        return super().click_relative(x, y, *args, **kwargs)

    def click(self, x, y=None, *args, **kwargs):
        """
        智能点击：后台模式使用 SendInput，前台模式使用框架方法

        根据游戏窗口状态自动选择最优的点击方式：
        - 后台/伪最小化：使用 SendInput 发送鼠标事件
        - 前台：使用框架的点击方法

        Args:
            x: X坐标、检测结果对象或 Box 对象
            y: Y坐标（当x是检测结果时可不传）
            *args, **kwargs: 传递给框架 click() 的其他参数

        Returns:
            点击操作的返回值
        """
        # 检查是否需要后台点击
        if self._need_background_click():
            # 处理 DetectionResult 对象
            if hasattr(x, 'center_x'):
                click_x, click_y = x.center_x, x.center_y
            elif hasattr(x, 'x') and hasattr(x, 'width'):
                # Box 对象
                click_x = x.x + x.width / 2
                click_y = x.y + x.height / 2
            else:
                click_x, click_y = x, y
            
            after_sleep = kwargs.get('after_sleep', 0.5)
            return self.background_click(int(click_x), int(click_y), after_sleep=after_sleep)
        
        # 前台模式使用框架方法
        return super().click(x, y, *args, **kwargs)

    # ==================== 场景检测 ====================

    def in_main_menu(self):
        """
        检测是否在主菜单

        Returns:
            bool: True 如果在主菜单
        """
        return self.find_feature(Features.MAIN_MENU_START) is not None or \
               self.find_feature(Features.ENTER_GAME_BUTTON) is not None

    def in_login_screen(self):
        """
        检测是否在登录界面

        Returns:
            bool: True 如果在登录界面
        """
        return self.find_feature('login_screen_indicator') is not None or \
               self.find_feature(Features.LOGIN_BUTTON) is not None

    # ==================== 登录相关 ====================

    def wait_login(self, timeout=120):
        """
        等待登录完成

        Args:
            timeout: 超时时间（秒）

        Returns:
            bool: True 如果登录成功
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            self.next_frame()

            if self.in_lobby() or self.in_game():
                self._logged_in = True
                self.log_info("登录成功 - 已进入游戏")
                return True

            if self._handle_login_buttons():
                continue

            time.sleep(0.5)

        return self._logged_in

    def _handle_login_buttons(self):
        """
        处理登录按钮点击

        Returns:
            bool: True 如果点击了任何按钮
        """
        enter_game = self.find_one(Features.ENTER_GAME_BUTTON, threshold=0.7)
        if enter_game:
            self.log_info("找到'进入游戏'按钮")
            self.click(enter_game)
            self.sleep(3)
            return True

        start_game = self.find_one(Features.START_GAME_BUTTON, threshold=0.7)
        if start_game:
            self.log_info("找到'开始游戏'按钮")
            self.click(start_game)
            self.sleep(3)
            return True

        login_button = self.find_one(Features.LOGIN_BUTTON, threshold=0.7)
        if login_button:
            self.log_info("找到登录按钮")
            self.click(login_button)
            self.sleep(3)
            return True

        texts = self.ocr()
        if texts:
            enter_texts = self.find_boxes(texts, match=re.compile(r"进入游戏"))
            if enter_texts:
                self.log_info("OCR找到'进入游戏'")
                self.click(enter_texts[0])
                self.sleep(3)
                return True

            start_texts = self.find_boxes(texts, match=re.compile(r"开始游戏"))
            if start_texts:
                self.log_info("OCR找到'开始游戏'")
                self.click(start_texts[0])
                self.sleep(3)
                return True

        return False

    def find_boxes(self, ocr_results, match=None, boundary=None):
        """
        从 OCR 结果中查找匹配的文本框（支持简繁转换）

        Args:
            ocr_results: OCR 识别结果列表
            match: 匹配模式（字符串、正则表达式或列表）
            boundary: 边界限制

        Returns:
            list: 匹配的 Box 对象列表
        """
        if not ocr_results:
            return []

        # 根据游戏文本语言转换匹配模式
        match = self._convert_match_for_lang(match)

        matched = []
        for box in ocr_results:
            if match:
                if isinstance(match, re.Pattern):
                    if match.search(box.name):
                        matched.append(box)
                elif isinstance(match, str):
                    if match in box.name:
                        matched.append(box)
                elif isinstance(match, list):
                    for m in match:
                        if isinstance(m, re.Pattern):
                            if m.search(box.name):
                                matched.append(box)
                                break
                        elif m in box.name:
                            matched.append(box)
                            break

        if boundary and matched:
            if isinstance(boundary, str):
                if boundary == 'bottom_right':
                    screen_w = self.screen_width
                    screen_h = self.screen_height
                    matched = [b for b in matched if b.x > screen_w * 0.5 and b.y > screen_h * 0.5]
            else:
                bx, by, bw, bh = boundary
                matched = [b for b in matched if
                          bx <= b.x <= bx + bw and
                          by <= b.y <= by + bh]

        return matched

    def _convert_match_for_lang(self, match):
        """
        根据游戏文本语言转换匹配模式

        当游戏设置为繁体中文时，自动将简体中文匹配模式转换为繁体中文。

        Args:
            match: 原始匹配模式

        Returns:
            转换后的匹配模式
        """
        if match is None:
            return match

        # 获取游戏文本语言设置
        if not self._is_traditional_chinese():
            return match

        # 转换为繁体中文
        if isinstance(match, re.Pattern):
            converted = LangConverter.convert_regex_pattern(match, True)
            self.log_info(f"正则转换: '{match.pattern}' -> '{converted.pattern}'")
            return converted
        elif isinstance(match, str):
            converted = LangConverter.simplify_to_traditional(match)
            self.log_info(f"字符串转换: '{match}' -> '{converted}'")
            return converted
        elif isinstance(match, list):
            return [self._convert_match_for_lang(m) for m in match]

        return match

    def _is_traditional_chinese(self) -> bool:
        """
        检查游戏文本语言是否为繁体中文

        Returns:
            bool: True 如果是繁体中文
        """
        try:
            from config import basic_config_option
            config = self.get_global_config(basic_config_option)
            lang = config.get('游戏文本语言', '简体中文')
            is_traditional = lang == '繁体中文'
            # 添加调试日志
            self.log_info(f"游戏文本语言配置: '{lang}', 是否繁体: {is_traditional}")
            return is_traditional
        except Exception as e:
            self.log_error(f"获取游戏文本语言配置失败: {e}")
            return False

    def wait_until(self, condition, time_out=10, pre_action=None, post_action=None, raise_if_not_found=False):
        """
        等待条件满足

        Args:
            condition: 条件函数，返回非 None 值表示满足
            time_out: 超时时间（秒）
            pre_action: 等待前执行的操作
            post_action: 条件满足后执行的操作
            raise_if_not_found: 超时时是否抛出异常

        Returns:
            condition 的返回值，或 None（超时时）
        """
        start_time = time.time()

        if pre_action:
            pre_action()

        while time.time() - start_time < time_out:
            self.next_frame()
            result = condition()
            if result:
                if post_action:
                    post_action()
                return result
            time.sleep(0.1)

        if raise_if_not_found:
            raise Exception(f"等待条件超时")
        return None

    def ensure_main(self, esc=True, time_out=30):
        """
        确保在游戏主界面

        Args:
            esc: 是否使用 ESC 键返回
            time_out: 超时时间（秒）
        """
        self.info_set('current task', f'wait main esc={esc}')
        if not self._logged_in:
            time_out = 180
        if not self.wait_until(lambda: self.is_main(esc=esc), time_out=time_out, raise_if_not_found=False):
            raise Exception('请在游戏世界内开始!')
        self.sleep(0.5)
        self.info_set('current task', f'in main esc={esc}')

    def is_main(self, esc=True):
        """
        检查是否在游戏主界面

        Args:
            esc: 是否使用 ESC 键返回

        Returns:
            bool: True 如果在主界面
        """
        if self.in_lobby() or self.in_game():
            self._logged_in = True
            return True
        if self.wait_login():
            return True
        if esc:
            self.back(after_sleep=2)
        return False

    # ==================== 伪最小化功能 ====================

    def pseudo_minimize(self):
        """执行伪最小化"""
        background_manager.pseudo_minimize()

    def pseudo_restore(self):
        """从伪最小化恢复"""
        return background_manager.pseudo_restore()

    def toggle_pseudo_minimize(self):
        """切换伪最小化状态"""
        return background_manager.toggle_pseudo_minimize()

    def is_pseudo_minimized(self):
        """检查是否处于伪最小化状态"""
        return background_manager.is_pseudo_minimized()

    def ensure_visible_for_capture(self):
        """确保窗口可见以便截图"""
        return background_manager.ensure_visible_for_capture()
