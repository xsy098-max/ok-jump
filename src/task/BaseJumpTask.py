import re
import time

from ok import BaseTask, og

from src.task.mixins import JumpTaskMixin
from src.constants.features import Features
from src.utils.BackgroundManager import background_manager
from src.utils.LangConverter import LangConverter


class _VirtualBox:
    """虚拟 Box 对象，用于合并分开识别的 OCR 文本位置"""
    __slots__ = ('x', 'y', 'width', 'height', 'name', 'center_x', 'center_y')

    def __init__(self, x, y, w, h, name):
        self.x = x
        self.y = y
        self.width = w
        self.height = h
        self.name = name
        self.center_x = x + w // 2
        self.center_y = y + h // 2


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
        # 调用上下文（用于任务被其他任务调用时的状态管理）
        self._caller_task = None  # 调用者任务引用
        self._is_standalone = True  # 是否单独运行（默认True）
        # 繁体中文配置缓存
        self._traditional_chinese_cache = None
        self._traditional_chinese_ts = 0

    def set_caller(self, caller_task):
        """
        设置调用者任务（由其他任务调用时使用）

        当任务被其他任务模块调用时，应调用此方法标记调用关系。
        这会影响任务完成后的行为（如自动登录任务是否主动结束）。

        Args:
            caller_task: 调用者任务实例
        """
        self._caller_task = caller_task
        self._is_standalone = False

    def get_task_by_class(self, task_class):
        """
        获取指定类的任务实例

        从 og.executor.onetime_tasks 中查找已注册的任务实例。
        注意：不能直接实例化任务类，因为 BaseTask 需要参数初始化。

        Args:
            task_class: 任务类

        Returns:
            任务实例，如果无法获取则返回None
        """
        try:
            # 从 og.executor.onetime_tasks 中查找已注册的任务实例
            if hasattr(og, 'executor') and og.executor:
                for task in og.executor.onetime_tasks:
                    if isinstance(task, task_class):
                        return task

            self.logger.warning(f"未在 executor 中找到 {task_class.__name__} 实例")
            return None

        except Exception as e:
            self.logger.error(f"获取任务实例失败: {e}")
            return None

    @property
    def is_standalone(self) -> bool:
        """
        是否单独运行

        Returns:
            bool: True 表示任务由用户直接启动，False 表示被其他任务调用
        """
        return self._is_standalone

    # ==================== 坐标提取辅助 ====================

    @staticmethod
    def _extract_click_coords(x, y=None):
        """
        从各种输入格式中提取点击坐标

        支持 DetectionResult、Box 对象和原始坐标。

        Args:
            x: X坐标、检测结果对象或 Box 对象
            y: Y坐标

        Returns:
            tuple: (click_x, click_y) 绝对坐标
        """
        if hasattr(x, 'center_x'):
            return x.center_x, x.center_y
        elif hasattr(x, 'x') and hasattr(x, 'width'):
            return x.x + x.width / 2, x.y + x.height / 2
        return x, y

    def click_relative(self, x, y, *args, **kwargs):
        """
        点击相对坐标位置（智能后台支持）

        Args:
            x: 相对 X 坐标 (0-1)
            y: 相对 Y 坐标 (0-1)
            *args, **kwargs: 传递给父类 click_relative 的参数

        Returns:
            点击操作的返回值
        """
        if self._need_background_click():
            after_sleep = kwargs.get('after_sleep', 0.5)
            return self.background_click_relative(x, y, after_sleep=after_sleep)
        return super().click_relative(x, y, *args, **kwargs)

    def click(self, x, y=None, *args, **kwargs):
        """
        智能点击：后台模式使用 SendInput，前台模式使用框架方法

        Args:
            x: X坐标、检测结果对象或 Box 对象
            y: Y坐标（当x是检测结果时可不传）
            *args, **kwargs: 传递给框架 click() 的其他参数

        Returns:
            点击操作的返回值
        """
        if self._need_background_click():
            click_x, click_y = self._extract_click_coords(x, y)
            after_sleep = kwargs.get('after_sleep', 0.5)
            return self.background_click(int(click_x), int(click_y), after_sleep=after_sleep)
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

    def _find_and_click_feature(self, feature_name, button_label, threshold=0.7, after_sleep=3):
        """
        查找特征按钮并点击

        Args:
            feature_name: 特征名称
            button_label: 按钮中文标签（用于日志）
            threshold: 匹配阈值
            after_sleep: 点击后等待时间

        Returns:
            bool: True 如果找到并点击了按钮
        """
        try:
            result = self.find_one(feature_name, threshold=threshold)
            if result:
                self.click(result)
                self.sleep(after_sleep)
                return True
        except ValueError:
            pass
        return False

    def _find_and_click_ocr(self, texts, pattern, button_label, after_sleep=3):
        """
        从OCR结果中查找文本并点击

        Args:
            texts: OCR识别结果列表
            pattern: 匹配正则表达式
            button_label: 按钮中文标签（用于日志）
            after_sleep: 点击后等待时间

        Returns:
            bool: True 如果找到并点击了文本
        """
        if not texts:
            return False
        boxes = self.find_boxes(texts, match=pattern)
        if boxes:
            self.click(boxes[0])
            self.sleep(after_sleep)
            return True
        return False

    def _handle_login_buttons(self):
        """
        处理登录按钮点击

        Returns:
            bool: True 如果点击了任何按钮
        """
        # 优先使用特征匹配
        for feature, label in [
            (Features.ENTER_GAME_BUTTON, '进入游戏'),
            (Features.START_GAME_BUTTON, '开始游戏'),
            (Features.LOGIN_BUTTON, '登录'),
        ]:
            if self._find_and_click_feature(feature, label):
                return True

        # 使用 OCR 匹配
        texts = self.ocr()
        for pattern, label in [
            (re.compile(r"进入游戏"), '进入游戏'),
            (re.compile(r"开始游戏"), '开始游戏'),
        ]:
            if self._find_and_click_ocr(texts, pattern, label):
                return True

        return False

    @staticmethod
    def _match_box_name(box_name, match):
        """
        检查 Box 名称是否匹配指定模式

        Args:
            box_name: OCR识别的文本
            match: 匹配模式（str、re.Pattern 或 list）

        Returns:
            bool: 是否匹配
        """
        if isinstance(match, re.Pattern):
            return match.search(box_name) is not None
        elif isinstance(match, str):
            return match in box_name
        elif isinstance(match, list):
            return any(
                (m.search(box_name) is not None if isinstance(m, re.Pattern) else m in box_name)
                for m in match
            )
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

        matched = [box for box in ocr_results if match and self._match_box_name(box.name, match)]

        if boundary and matched:
            if isinstance(boundary, str):
                if boundary == 'bottom_right':
                    screen_w, screen_h = self.screen_width, self.screen_height
                    matched = [b for b in matched if b.x > screen_w * 0.5 and b.y > screen_h * 0.5]
            else:
                bx, by, bw, bh = boundary
                matched = [b for b in matched if bx <= b.x <= bx + bw and by <= b.y <= by + bh]

        return matched

    def find_text_fuzzy(self, ocr_results, target_text, return_center=True):
        """
        模糊查找OCR文本（支持分开识别的容错机制）

        OCR有时会将多字词语分开识别，例如：
        - "返回" 可能被识别为 ['返', '回']
        - "确定" 可能被识别为 ['确', '定']

        此方法会依次尝试：
        1. 完整匹配：查找包含完整目标文字的文本框
        2. 分字匹配：查找所有单字，如果全部找到则合并位置
        3. 部分匹配：查找第一个找到的单字

        Args:
            ocr_results: OCR 识别结果列表
            target_text: 目标文字（如 "返回"、"确定"）
            return_center: 是否返回中心位置（True）或返回文本框对象（False）

        Returns:
            如果 return_center=True: 返回 (x, y) 元组，未找到返回 None
            如果 return_center=False: 返回 Box 对象或合并后的虚拟 Box 对象
        """
        if not ocr_results or not target_text:
            return None

        # 获取简体和繁体两种形式的目标文字
        simplified_text = target_text
        traditional_text = LangConverter.simplify_to_traditional(target_text)
        
        # 根据游戏语言设置决定优先顺序
        is_traditional = self._is_traditional_chinese()
        search_order = (
            [traditional_text, simplified_text] if is_traditional
            else [simplified_text, traditional_text]
        )
        # 方法1: 完整匹配 - 查找包含完整目标文字的文本框（支持简繁双语）
        matched_boxes = self.find_boxes(ocr_results, match=target_text)
        if matched_boxes:
            box = matched_boxes[0]
            if return_center:
                return (box.x + box.width // 2, box.y + box.height // 2)
            return box

        # 方法2+3: 分字匹配 + 部分匹配（按优先顺序尝试）
        for search_text in search_order:
            chars = list(search_text)
            char_boxes = {}

            for t in ocr_results:
                for char in chars:
                    if char in t.name and char not in char_boxes:
                        char_boxes[char] = t

            # 全部字符都找到 -> 合并位置（方法2）
            if len(char_boxes) == len(chars):
                total_x = sum(t.x + t.width // 2 for t in char_boxes.values())
                total_y = sum(t.y + t.height // 2 for t in char_boxes.values())
                center_x = total_x // len(char_boxes)
                center_y = total_y // len(char_boxes)

                if return_center:
                    return (center_x, center_y)
                first_box = next(iter(char_boxes.values()))
                return _VirtualBox(
                    center_x - first_box.width // 2,
                    center_y - first_box.height // 2,
                    first_box.width, first_box.height, target_text
                )

            # 部分 -> 返回第一个找到的字符（方法3）
            for char in chars:
                if char in char_boxes:
                    box = char_boxes[char]
                    if return_center:
                        return (box.x + box.width // 2, box.y + box.height // 2)
                    return box

        return None

    def find_text_fuzzy_with_retry(self, target_text, timeout=5.0, ocr_interval=0.1):
        """
        带重试的模糊文字查找（自动获取OCR结果）

        Args:
            target_text: 目标文字
            timeout: 超时时间（秒）
            ocr_interval: OCR检测间隔（秒）

        Returns:
            tuple: (x, y) 位置，未找到返回 None
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            self.next_frame()
            texts = self.ocr()
            if texts:
                result = self.find_text_fuzzy(texts, target_text)
                if result:
                    return result
            time.sleep(ocr_interval)

        return None

    def _convert_match_for_lang(self, match):
        """
        根据游戏文本语言转换匹配模式

        当游戏设置为繁体中文时，将正则表达式转换为同时匹配简体和繁体中文。
        例如：'适龄提示' -> '适龄提示|適齡提示'

        Args:
            match: 原始匹配模式

        Returns:
            转换后的匹配模式（双语模式）
        """
        if match is None:
            return match

        # 获取游戏文本语言设置
        if not self._is_traditional_chinese():
            return match

        # 转换为双语模式（同时匹配简体和繁体）
        if isinstance(match, re.Pattern):
            # 创建双语模式
            bilingual = LangConverter.create_bilingual_regex(match)
            return bilingual
        elif isinstance(match, str):
            converted = LangConverter.create_bilingual_pattern(match)
            return converted
        elif isinstance(match, list):
            return [self._convert_match_for_lang(m) for m in match]

        return match

    def _is_traditional_chinese(self) -> bool:
        """
        检查游戏文本语言是否为繁体中文（带 5 秒缓存）

        Returns:
            bool: True 如果是繁体中文
        """
        now = time.time()
        if self._traditional_chinese_cache is not None and (now - self._traditional_chinese_ts) < 5:
            return self._traditional_chinese_cache

        try:
            from config import basic_config_option
            config = self.get_global_config(basic_config_option)
            self._traditional_chinese_cache = config.get('游戏文本语言', '简体中文') == '繁体中文'
        except Exception as e:
            self.log_error(f"获取游戏文本语言配置失败: {e}")
            self._traditional_chinese_cache = False

        self._traditional_chinese_ts = now
        return self._traditional_chinese_cache

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
