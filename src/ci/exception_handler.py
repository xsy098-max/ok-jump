"""
智能异常处理模块

提供统一的异常捕获和智能恢复机制：
- 非致命错误继续执行
- 游戏画面变化检测
- 连续失败检测
"""

import functools
import json
import logging
import os
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from src.ci.exceptions import (
    CITestException,
    GameStagnantException,
    ContinuousFailureException,
    GameProcessExitedException,
)


logger = logging.getLogger(__name__)


@dataclass
class FailureInfo:
    """失败信息结构"""
    task_name: str
    timestamp: str
    error_type: str
    error_message: str
    stack_trace: str
    screenshot_path: Optional[str] = None
    log_path: Optional[str] = None
    context: dict = field(default_factory=dict)


class GameActivityDetector:
    """
    游戏活动状态检测器

    通过帧哈希对比检测游戏画面是否在变化，
    用于判断游戏是否还在正常运行。
    """

    def __init__(self, threshold: float = 0.95, history_size: int = 10):
        """
        初始化检测器

        Args:
            threshold: 帧相似度阈值，超过此值认为画面相同
            history_size: 保存的历史帧数量
        """
        self._hash_history = []
        self._threshold = threshold
        self._history_size = history_size
        self._last_change_time = time.time()

    def is_game_active(self, current_frame) -> bool:
        """
        检测游戏是否活跃

        Args:
            current_frame: 当前帧图像 (numpy array)

        Returns:
            bool: True 表示游戏画面有变化，还在运行
        """
        if current_frame is None:
            return False

        try:
            # 计算当前帧哈希
            current_hash = self._compute_frame_hash(current_frame)

            if self._hash_history:
                # 与历史帧对比
                similarity = self._compute_similarity(current_hash, self._hash_history[-1])

                if similarity < self._threshold:
                    # 画面有变化
                    self._last_change_time = time.time()
                    self._hash_history.append(current_hash)
                    if len(self._hash_history) > self._history_size:
                        self._hash_history.pop(0)
                    return True

            self._hash_history.append(current_hash)
            if len(self._hash_history) > self._history_size:
                self._hash_history.pop(0)
            return False

        except Exception as e:
            logger.debug(f"帧哈希计算失败: {e}")
            return False

    def get_stagnant_duration(self) -> float:
        """
        获取画面停滞时长（秒）

        Returns:
            float: 停滞时长
        """
        return time.time() - self._last_change_time

    def is_stagnant(self, timeout: float = 30.0) -> bool:
        """
        判断画面是否停滞超时

        Args:
            timeout: 超时时间(秒)

        Returns:
            bool: True 表示画面停滞超时
        """
        return self.get_stagnant_duration() > timeout

    def _compute_frame_hash(self, frame) -> bytes:
        """
        计算帧哈希（简化版均值哈希）

        Args:
            frame: 图像帧

        Returns:
            bytes: 帧哈希值
        """
        import cv2

        # 缩小图像后计算均值哈希
        small = cv2.resize(frame, (16, 16))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        avg = gray.mean()
        return (gray > avg).flatten().tobytes()

    def _compute_similarity(self, hash1: bytes, hash2: bytes) -> float:
        """
        计算哈希相似度

        Args:
            hash1: 第一个哈希值
            hash2: 第二个哈希值

        Returns:
            float: 相似度 (0-1)
        """
        if len(hash1) != len(hash2):
            return 0.0
        same = sum(a == b for a, b in zip(hash1, hash2))
        return same / len(hash1)

    def reset(self):
        """重置检测器状态"""
        self._hash_history.clear()
        self._last_change_time = time.time()


class SmartTaskExecutor:
    """
    智能任务执行器

    核心特性：
    - 非致命错误继续执行
    - 过滤 negative box 错误
    - 连续失败检测（阈值=10次）
    - 游戏画面停滞检测
    """

    def __init__(self, task, max_continuous_fails: int = 10):
        """
        初始化执行器

        Args:
            task: 任务实例
            max_continuous_fails: 连续失败阈值
        """
        self.task = task
        self.activity_detector = GameActivityDetector()
        self.error_history = []
        self.continuous_fail_count = 0
        self.max_continuous_fails = max_continuous_fails

    def execute_with_recovery(self, action: Callable, action_name: str = "操作"):
        """
        带恢复机制的执行

        Args:
            action: 要执行的操作函数
            action_name: 操作名称（用于日志）

        Returns:
            操作结果，如果无法恢复则返回 None

        Raises:
            ContinuousFailureException: 连续失败次数过多
            GameStagnantException: 游戏卡死
        """
        try:
            result = action()
            self.continuous_fail_count = 0  # 成功则重置失败计数
            return result

        except Exception as e:
            # 过滤 negative box 错误（OCR无害错误，不计入失败次数）
            if self._is_negative_box_error(e):
                logger.debug(f"过滤OCR negative box错误: {e}")
                return None  # 直接返回，不计入失败

            self.continuous_fail_count += 1
            self._record_error(e, action_name)

            # 检查连续失败次数
            if self.continuous_fail_count >= self.max_continuous_fails:
                logger.error(f"连续失败 {self.continuous_fail_count} 次，终止任务")
                raise ContinuousFailureException(f"连续失败次数过多 ({self.continuous_fail_count}次)")

            # 检查是否为致命错误
            if self._is_fatal_error(e):
                logger.error(f"致命错误: {e}")
                raise  # 抛出致命错误

            # 非致命错误：尝试恢复
            logger.warning(f"非致命错误({action_name}): {e}，尝试恢复...")

            # 检查游戏状态
            if self._check_game_stagnant():
                logger.error("游戏画面长时间无变化，确认卡死")
                raise GameStagnantException("游戏卡死")

            # 游戏还在运行，返回None表示此次失败但可继续
            return None

    def _is_negative_box_error(self, error: Exception) -> bool:
        """
        判断是否为 negative box 错误

        negative box 是OCR识别时产生的无效框，属于无害错误，不应计入失败次数

        Args:
            error: 异常对象

        Returns:
            bool: True 表示是 negative box 错误
        """
        error_msg = str(error).lower()
        negative_keywords = ['negative', 'negative box', '负坐标', 'invalid box']
        return any(kw in error_msg for kw in negative_keywords)

    def _is_fatal_error(self, error: Exception) -> bool:
        """
        判断是否为致命错误

        Args:
            error: 异常对象

        Returns:
            bool: True 表示是致命错误
        """
        fatal_exceptions = (
            GameProcessExitedException,
            GameStagnantException,
            KeyboardInterrupt,
        )
        return isinstance(error, fatal_exceptions)

    def _check_game_stagnant(self, timeout: float = 30.0) -> bool:
        """
        检查游戏是否停滞

        Args:
            timeout: 停滞超时时间(秒)

        Returns:
            bool: True 表示游戏停滞
        """
        try:
            # 尝试获取新帧
            if hasattr(self.task, 'next_frame'):
                self.task.next_frame()

            if hasattr(self.task, 'frame') and self.task.frame is not None:
                self.activity_detector.is_game_active(self.task.frame)
                return self.activity_detector.is_stagnant(timeout)
        except Exception as e:
            logger.debug(f"检测游戏状态失败: {e}")

        return False

    def _record_error(self, error: Exception, action_name: str):
        """
        记录错误（不中断任务）

        Args:
            error: 异常对象
            action_name: 操作名称
        """
        self.error_history.append({
            'timestamp': time.time(),
            'action': action_name,
            'error': str(error),
            'type': type(error).__name__
        })

    def reset(self):
        """重置执行器状态"""
        self.continuous_fail_count = 0
        self.error_history.clear()
        self.activity_detector.reset()

    def get_error_summary(self) -> dict:
        """
        获取错误摘要

        Returns:
            dict: 错误摘要信息
        """
        return {
            'total_errors': len(self.error_history),
            'continuous_fails': self.continuous_fail_count,
            'last_error': self.error_history[-1] if self.error_history else None
        }


class ExceptionHandler:
    """
    统一异常处理器

    提供异常捕获、截图保存、日志导出等功能
    """

    @staticmethod
    def capture_failure(
        exception: Exception,
        task,
        screenshots_dir: str = "test_results/failures"
    ) -> FailureInfo:
        """
        捕获失败信息

        Args:
            exception: 异常对象
            task: 任务实例
            screenshots_dir: 截图保存目录

        Returns:
            FailureInfo: 失败信息
        """
        # 确保目录存在
        os.makedirs(screenshots_dir, exist_ok=True)

        # 生成时间戳
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        task_name = getattr(task, 'name', 'UnknownTask')

        # 保存截图
        screenshot_path = None
        try:
            if hasattr(task, 'frame') and task.frame is not None:
                import cv2
                safe_name = task_name.replace(' ', '_')
                screenshot_path = os.path.join(screenshots_dir, f"{timestamp}_{safe_name}.png")
                cv2.imwrite(screenshot_path, task.frame)
                logger.info(f"错误截图已保存: {screenshot_path}")
        except Exception as e:
            logger.warning(f"保存截图失败: {e}")

        # 收集上下文
        context = ExceptionHandler._collect_context(task)

        return FailureInfo(
            task_name=task_name,
            timestamp=timestamp,
            error_type=type(exception).__name__,
            error_message=str(exception),
            stack_trace=traceback.format_exc(),
            screenshot_path=screenshot_path,
            log_path=None,
            context=context
        )

    @staticmethod
    def wrap_task(task_func: Callable) -> Callable:
        """
        任务装饰器：自动捕获异常并记录

        Args:
            task_func: 任务函数

        Returns:
            包装后的函数
        """
        @functools.wraps(task_func)
        def wrapper(self, *args, **kwargs):
            try:
                return task_func(self, *args, **kwargs)
            except Exception as e:
                failure = ExceptionHandler.capture_failure(e, self)
                self._last_failure = failure

                # 调用失败回调（如果存在）
                if hasattr(self, '_on_task_failure'):
                    try:
                        self._on_task_failure(failure)
                    except Exception as callback_error:
                        logger.error(f"失败回调执行错误: {callback_error}")

                raise
        return wrapper

    @staticmethod
    def _collect_context(task) -> dict:
        """
        收集任务执行上下文

        Args:
            task: 任务实例

        Returns:
            dict: 上下文信息
        """
        context = {}

        try:
            # 分辨率信息
            if hasattr(task, 'get_resolution_info'):
                context['resolution'] = task.get_resolution_info()
        except Exception:
            pass

        try:
            # 后台模式状态
            if hasattr(task, 'is_background_mode'):
                context['background_mode'] = task.is_background_mode()
        except Exception:
            pass

        try:
            # 配置快照
            if hasattr(task, 'config') and task.config:
                context['config_snapshot'] = dict(task.config)
        except Exception:
            pass

        return context

    @staticmethod
    def save_failure_report(failure: FailureInfo, output_dir: str) -> str:
        """
        保存失败报告

        Args:
            failure: 失败信息
            output_dir: 输出目录

        Returns:
            str: 报告文件路径
        """
        os.makedirs(output_dir, exist_ok=True)

        # 生成报告文件名
        filename = f"{failure.timestamp}_{failure.task_name}_failure.json"
        filepath = os.path.join(output_dir, filename)

        # 构建报告内容
        report = {
            'task_name': failure.task_name,
            'timestamp': failure.timestamp,
            'error_type': failure.error_type,
            'error_message': failure.error_message,
            'stack_trace': failure.stack_trace,
            'screenshot_path': failure.screenshot_path,
            'context': failure.context
        }

        # 保存JSON
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # 单独保存堆栈信息
        stack_file = os.path.join(output_dir, f"{failure.timestamp}_{failure.task_name}_stack.txt")
        with open(stack_file, 'w', encoding='utf-8') as f:
            f.write(failure.stack_trace)

        logger.info(f"失败报告已保存: {filepath}")
        return filepath
