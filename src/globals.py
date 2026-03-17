"""
全局资源管理器

参考 ok-wuthering-waves 的设计，提供：
- 登录状态管理
- OCR 缓存管理
- YOLO 模型管理
- 全局资源统一访问接口
"""

import os
import time
from PySide6.QtCore import QObject


class Globals(QObject):
    """
    全局资源管理器

    使用单例模式管理全局状态和共享资源：
    - 登录状态
    - OCR 缓存
    - YOLO 模型
    - 其他全局资源

    使用方式：
        from src import jump_globals

        # 检查登录状态
        if jump_globals.logged_in:
            ...

        # 使用 OCR 缓存
        cached = jump_globals.get_ocr_cache('login')
        if not cached:
            texts = self.ocr()
            jump_globals.set_ocr_cache('login', texts)
        
        # 使用 YOLO 检测
        detections = jump_globals.yolo_detect(frame, threshold=0.5, label=2)
    """

    def __init__(self, exit_event=None):
        super().__init__()
        self._exit_event = exit_event

        # 登录状态
        self._logged_in = False

        # OCR 缓存：{cache_key: (data, timestamp)}
        self._ocr_cache = {}

        # 游戏语言
        self._game_lang = None
        
        # YOLO 模型（延迟加载）
        self._yolo_model = None

    # ==================== 登录状态管理 ====================

    @property
    def logged_in(self) -> bool:
        """
        获取登录状态

        Returns:
            bool: True 如果已登录
        """
        return self._logged_in

    def set_logged_in(self, value: bool):
        """
        设置登录状态

        Args:
            value: 登录状态
        """
        self._logged_in = value

    def reset_login_state(self):
        """重置登录状态"""
        self._logged_in = False

    # ==================== 游戏语言管理 ====================

    @property
    def game_lang(self) -> str:
        """
        获取游戏语言

        Returns:
            str: 游戏语言代码 ('zh_CN' 或 'en_US')
        """
        return self._game_lang or 'zh_CN'

    def set_game_lang(self, lang: str):
        """
        设置游戏语言

        Args:
            lang: 语言代码 ('zh_CN' 或 'en_US')
        """
        self._game_lang = lang

    # ==================== OCR 缓存管理 ====================

    def get_ocr_cache(self, key: str, ttl: float = 1.0):
        """
        获取 OCR 缓存

        Args:
            key: 缓存键名
            ttl: 缓存有效期（秒），默认 1 秒

        Returns:
            缓存的数据，如果缓存不存在或已过期则返回 None
        """
        if key in self._ocr_cache:
            data, timestamp = self._ocr_cache[key]
            if time.time() - timestamp < ttl:
                return data
            # 缓存过期，删除
            del self._ocr_cache[key]
        return None

    def set_ocr_cache(self, key: str, data):
        """
        设置 OCR 缓存

        Args:
            key: 缓存键名
            data: 要缓存的数据
        """
        self._ocr_cache[key] = (data, time.time())

    def clear_ocr_cache(self, key: str = None):
        """
        清除 OCR 缓存

        Args:
            key: 要清除的缓存键名，如果为 None 则清除所有缓存
        """
        if key:
            self._ocr_cache.pop(key, None)
        else:
            self._ocr_cache.clear()

    def is_cache_valid(self, key: str, ttl: float = 1.0) -> bool:
        """
        检查缓存是否有效

        Args:
            key: 缓存键名
            ttl: 缓存有效期（秒）

        Returns:
            bool: True 如果缓存存在且未过期
        """
        if key in self._ocr_cache:
            _, timestamp = self._ocr_cache[key]
            return time.time() - timestamp < ttl
        return False

    # ==================== 全局重置 ====================

    def reset(self):
        """重置所有全局状态"""
        self._logged_in = False
        self._game_lang = None
        self._ocr_cache.clear()

    # ==================== YOLO 模型管理 ====================

    @property
    def yolo_model(self):
        """
        获取 YOLO 模型（延迟加载）
        
        Returns:
            OnnxYolo8Detect: YOLO 检测器实例
        """
        if self._yolo_model is None:
            from src.OnnxYolo8Detect import OnnxYolo8Detect
            
            # 获取项目根目录
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            weights_path = os.path.join(project_root, "assets", "Fight", "fight.onnx")
            
            if os.path.exists(weights_path):
                self._yolo_model = OnnxYolo8Detect(
                    weights=weights_path,
                    conf_threshold=0.25,
                    iou_threshold=0.45
                )
            else:
                raise FileNotFoundError(f"YOLO 模型文件不存在: {weights_path}")
        
        return self._yolo_model

    def yolo_detect(self, image, threshold=0.5, label=-1):
        """
        使用 YOLO 进行检测
        
        Args:
            image: BGR 图像 (numpy array)
            threshold: 置信度阈值
            label: 过滤特定标签 (-1 表示不过滤)
                   0: 自己
                   1: 友方
                   2: 敌军
                   3: 死亡状态
                   4: 目标圈
        
        Returns:
            list: 检测结果列表 [DetectionResult, ...]
        """
        try:
            return self.yolo_model.detect(image, threshold=threshold, label=label)
        except Exception as e:
            # 模型加载失败时返回空列表
            print(f"YOLO 检测失败: {e}")
            return []

    def reset_yolo_model(self):
        """重置 YOLO 模型（释放内存）"""
        self._yolo_model = None
