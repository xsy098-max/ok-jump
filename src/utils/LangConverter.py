"""
简繁中文转换工具

提供简体中文到繁体中文的转换功能，用于 OCR 文本匹配的多语言支持。
支持两种转换方式：
1. OpenCC 库（推荐，需要安装 opencc）
2. 内置字典（备选方案，覆盖常用游戏文本）
"""

import re


# 简繁对照字典（常用游戏文本）
_SIMPLIFIED_TO_TRADITIONAL = {
    # 登录相关
    '进入游戏': '進入遊戲',
    '开始游戏': '開始遊戲',
    '登录': '登錄',
    '登陆': '登陸',
    '账号': '帳號',
    '账户名': '帳戶名',
    '账户': '帳戶',
    '换区': '換區',
    '适龄提示': '年齡分級',
    '年龄分级': '年齡分級',
    '我已详细阅读并同意': '我已詳細閱讀並同意',
    '我已詳細閱讀並同意': '我已詳細閱讀並同意',
    '游戏使用者协定': '遊戲使用者協定',
    '隐私保护声明': '隱私保護聲明',
    
    # 游戏状态
    '角色': '角色',
    '排位赛': '排位賽',
    '返回游戏': '返回遊戲',
    '返回': '返回',  # 繁简相同
    
    # 问卷相关
    '问卷调查': '問卷調查',
    '问卷': '問卷',
    '调查': '調查',
    '感谢您的耐心回答': '感謝您的耐心回答',
    '提交': '提交',  # 繁简相同
    '送出': '送出',  # 繁简相同
    '确认': '確認',
    '确定': '確定',
    
    # 角色选择
    '请选择一位你心仪的角色': '請選擇一位你心儀的角色',
    '心仪的角色': '心儀的角色',
    '选择角色': '選擇角色',
    
    # 错误信息
    '登陆失败': '登陸失敗',
    '登录失败': '登錄失敗',
    '网络错误': '網絡錯誤',
    '连接失败': '連接失敗',
    '账号或密码错误': '帳號或密碼錯誤',
    '服务器维护': '服務器維護',
    '连接超时': '連接超時',
    
    # 问卷选项
    '至少有一部': '至少有一部',
    '追到最新剧情': '追到最新劇情',
    '王者10星及以上': '王者10星及以上',
    '追求团队胜利': '追求團隊勝利',
    '段位和排名': '段位和排名',
    
    # 单字转换（用于正则表达式）
    '进': '進',
    '入': '入',
    '游': '遊',
    '戏': '戲',
    '开': '開',
    '始': '始',
    '登': '登',
    '录': '錄',
    '陆': '陸',
    '账': '帳',
    '号': '號',
    '户': '戶',
    '换': '換',
    '区': '區',
    '适': '適',
    '龄': '齡',
    '提': '提',
    '示': '示',
    '详': '詳',
    '细': '細',
    '阅': '閱',
    '读': '讀',
    '并': '並',
    '同': '同',
    '意': '意',
    '隐': '隱',
    '私': '私',
    '保': '保',
    '护': '護',
    '声': '聲',
    '明': '明',
    '排': '排',
    '位': '位',
    '赛': '賽',
    '返': '返',
    '回': '回',
    '问': '問',
    '卷': '卷',
    '调': '調',
    '查': '查',
    '感': '感',
    '谢': '謝',
    '您': '您',
    '的': '的',
    '耐': '耐',
    '心': '心',
    '答': '答',
    '请': '請',
    '选': '選',
    '择': '擇',
    '一': '一',
    '位': '位',
    '你': '你',
    '心': '心',
    '仪': '儀',
    '网': '網',
    '络': '絡',
    '错': '錯',
    '误': '誤',
    '连': '連',
    '接': '接',
    '败': '敗',
    '或': '或',
    '密': '密',
    '码': '碼',
    '服': '服',
    '务': '務',
    '器': '器',
    '维': '維',
    '修': '修',
    '超': '超',
    '时': '時',
    '团': '團',
    '队': '隊',
    '胜': '勝',
    '利': '利',
}


class LangConverter:
    """
    简繁中文转换工具类（单例模式）

    使用 OpenCC 库进行简繁转换，支持字符串和正则表达式模式转换。
    当 OpenCC 不可用时，使用内置字典进行转换。

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
        """初始化 OpenCC 转换器（台湾繁体）"""
        if cls._initialized:
            return

        cls._initialized = True
        try:
            import opencc
            # 使用台湾繁体转换（s2tw.json）
            # 游戏使用的是台湾繁体，如：帳戶名、帳號
            cls._converter = opencc.OpenCC('s2tw.json')
        except ImportError:
            cls._converter = None
        except Exception as e:
            cls._converter = None

    @staticmethod
    def _convert_by_dict(text: str) -> str:
        """
        使用内置字典进行简繁转换

        Args:
            text: 简体中文文本

        Returns:
            str: 繁体中文文本
        """
        result = text
        # 先尝试完整匹配
        if text in _SIMPLIFIED_TO_TRADITIONAL:
            return _SIMPLIFIED_TO_TRADITIONAL[text]

        # 逐字转换
        for simp, trad in _SIMPLIFIED_TO_TRADITIONAL.items():
            if len(simp) == 1:  # 只处理单字
                result = result.replace(simp, trad)

        return result

    @staticmethod
    def simplify_to_traditional(text: str) -> str:
        """
        将简体中文转换为繁体中文

        优先使用内置字典（游戏特定词汇），其次使用 OpenCC。

        Args:
            text: 简体中文文本

        Returns:
            str: 繁体中文文本
        """
        # 优先检查字典中的完整匹配（游戏特定词汇）
        if text in _SIMPLIFIED_TO_TRADITIONAL:
            return _SIMPLIFIED_TO_TRADITIONAL[text]

        # 使用 OpenCC 或字典逐字转换
        LangConverter._init_converter()

        if LangConverter._converter is not None:
            try:
                return LangConverter._converter.convert(text)
            except Exception:
                pass

        # 使用内置字典逐字转换
        return LangConverter._convert_by_dict(text)

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

    @staticmethod
    def create_bilingual_pattern(simplified: str) -> str:
        """
        创建简繁双语匹配模式

        Args:
            simplified: 简体中文文本

        Returns:
            str: 正则表达式模式，如 "进入游戏|進入遊戲"
        """
        traditional = LangConverter.simplify_to_traditional(simplified)
        if simplified == traditional:
            return simplified
        return f"{simplified}|{traditional}"

    @staticmethod
    def create_bilingual_regex(pattern) -> re.Pattern:
        """
        创建简繁双语正则表达式

        将正则表达式中的每个中文部分转换为简繁双语模式。
        例如：re.compile(r"适龄提示") -> re.compile(r"适龄提示|適齡提示")

        Args:
            pattern: 原始正则表达式（re.Pattern）

        Returns:
            re.Pattern: 双语正则表达式
        """
        if not hasattr(pattern, 'pattern'):
            return pattern

        original = pattern.pattern

        # 如果已经包含 |，需要分割处理每个部分
        if '|' in original:
            parts = original.split('|')
            converted_parts = []
            for part in parts:
                trad = LangConverter.simplify_to_traditional(part)
                if part != trad:
                    converted_parts.append(part)
                    converted_parts.append(trad)
                else:
                    converted_parts.append(part)
            new_pattern = '|'.join(converted_parts)
        else:
            traditional = LangConverter.simplify_to_traditional(original)
            if original == traditional:
                return pattern
            new_pattern = f"{original}|{traditional}"

        return re.compile(new_pattern, pattern.flags)
