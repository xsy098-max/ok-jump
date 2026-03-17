"""
简繁中文转换工具

提供简体中文到繁体中文的转换功能，用于 OCR 文本匹配的多语言支持。
"""

import re


class LangConverter:
    """
    简繁中文转换工具类（单例模式）

    使用 OpenCC 库进行简繁转换，支持字符串和正则表达式模式转换。

    使用方式：
        # 转换字符串
        traditional = LangConverter.simplify_to_traditional("进入游戏")
        # 结果: "進入遊戲"

        # 转换正则表达式
        pattern = re.compile(r"进入游戏|开始游戏")
        converted = LangConverter.convert_regex_pattern(pattern, True)
    """

    _instance = None
    _converter = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def _init_converter(cls):
        """初始化 OpenCC 转换器"""
        if cls._initialized:
            return

        cls._initialized = True
        try:
            import opencc
            cls._converter = opencc.OpenCC('s2t.json')  # 简体转繁体
        except ImportError:
            cls._converter = None
        except Exception as e:
            cls._converter = None

    @staticmethod
    def simplify_to_traditional(text: str) -> str:
        """
        将简体中文转换为繁体中文

        Args:
            text: 简体中文文本

        Returns:
            str: 繁体中文文本，如果 OpenCC 未安装则返回原文
        """
        LangConverter._init_converter()

        if LangConverter._converter is None:
            return text

        try:
            return LangConverter._converter.convert(text)
        except Exception:
            return text

    @staticmethod
    def convert_regex_pattern(pattern, to_traditional: bool):
        """
        转换正则表达式模式中的中文文本

        Args:
            pattern: 正则表达式模式（re.Pattern 或 str）
            to_traditional: 是否转换为繁体中文

        Returns:
            转换后的正则表达式模式
        """
        if not to_traditional:
            return pattern

        if isinstance(pattern, str):
            return LangConverter.simplify_to_traditional(pattern)
        elif hasattr(pattern, 'pattern'):  # re.Pattern
            converted = LangConverter.simplify_to_traditional(pattern.pattern)
            return re.compile(converted, pattern.flags)

        return pattern

    @staticmethod
    def is_available() -> bool:
        """
        检查 OpenCC 是否可用

        Returns:
            bool: True 如果 OpenCC 已安装并可用
        """
        LangConverter._init_converter()
        return LangConverter._converter is not None
