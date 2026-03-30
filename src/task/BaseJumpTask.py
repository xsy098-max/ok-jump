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
        # 调用上下文（用于任务被其他任务调用时的状态管理）
        self._caller_task = None  # 调用者任务引用
        self._is_standalone = True  # 是否单独运行（默认True）

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
            # 使用 find_boxes 方法，它会自动调用 _convert_match_for_lang 进行简繁转换
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
        if is_traditional:
            # 繁体环境：优先繁体，其次简体
            search_order = [traditional_text, simplified_text]
            self.log_info(f"[OCR模糊匹配] 繁体环境，目标: '{target_text}', 繁体: '{traditional_text}', 简体: '{simplified_text}'")
        else:
            # 简体环境：优先简体，其次繁体
            search_order = [simplified_text, traditional_text]
            self.log_info(f"[OCR模糊匹配] 简体环境，目标: '{target_text}', 简体: '{simplified_text}', 繁体: '{traditional_text}'")

        # 方法1: 完整匹配 - 查找包含完整目标文字的文本框（支持简繁双语）
        matched_boxes = self.find_boxes(ocr_results, match=target_text)
        if matched_boxes:
            box = matched_boxes[0]
            self.log_info(f"[OCR模糊匹配] 完整匹配成功: '{box.name}'")
            if return_center:
                return (box.x + box.width // 2, box.y + box.height // 2)
            return box

        # 方法2: 分字匹配 - 按优先顺序尝试
        for search_text in search_order:
            chars = list(search_text)
            char_boxes = {}

            self.log_info(f"[OCR模糊匹配] 分字匹配: 尝试 '{search_text}' -> {chars}")

            for t in ocr_results:
                for char in chars:
                    if char in t.name and char not in char_boxes:
                        char_boxes[char] = t
                        self.log_info(f"[OCR模糊匹配] 找到字符 '{char}' 在 '{t.name}' 中")

            # 检查是否找到了所有单字
            if len(char_boxes) == len(chars):
                # 合并所有单字的位置
                total_x = sum(t.x + t.width // 2 for t in char_boxes.values())
                total_y = sum(t.y + t.height // 2 for t in char_boxes.values())
                center_x = total_x // len(char_boxes)
                center_y = total_y // len(char_boxes)

                self.log_info(f"[OCR模糊匹配] '{target_text}' 被分开识别为 {list(char_boxes.keys())}，合并位置: ({center_x}, {center_y})")

                if return_center:
                    return (center_x, center_y)

                # 创建虚拟 Box 对象
                class VirtualBox:
                    def __init__(self, x, y, w, h, name):
                        self.x = x
                        self.y = y
                        self.width = w
                        self.height = h
                        self.name = name
                        self.center_x = x + w // 2
                        self.center_y = y + h // 2

                # 使用第一个字符的尺寸作为虚拟Box的尺寸
                first_box = list(char_boxes.values())[0]
                return VirtualBox(center_x - first_box.width // 2,
                                center_y - first_box.height // 2,
                                first_box.width, first_box.height, target_text)

        # 方法3: 部分匹配 - 按优先顺序返回找到的第一个单字（最后尝试）
        for search_text in search_order:
            chars = list(search_text)
            char_boxes = {}

            for t in ocr_results:
                for char in chars:
                    if char in t.name and char not in char_boxes:
                        char_boxes[char] = t

            for char in chars:
                if char in char_boxes:
                    box = char_boxes[char]
                    self.log_info(f"[OCR模糊匹配] 仅找到 '{char}' 字，位置: ({box.x + box.width // 2}, {box.y + box.height // 2})")
                    if return_center:
                        return (box.x + box.width // 2, box.y + box.height // 2)
                    return box

        self.log_info(f"[OCR模糊匹配] 未找到 '{target_text}'")
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
        import time
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
        检查游戏文本语言是否为繁体中文

        Returns:
            bool: True 如果是繁体中文
        """
        try:
            from config import basic_config_option
            config = self.get_global_config(basic_config_option)
            lang = config.get('游戏文本语言', '简体中文')
            is_traditional = lang == '繁体中文'
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
