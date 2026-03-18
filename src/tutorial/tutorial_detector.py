"""
新手教程检测器

封装新手教程中使用的各种检测方法，包括：
- YOLO模型检测
- OCR文字识别
- 模板匹配
"""

import re
import time
import threading
from typing import Optional, List, Tuple

from ok import og

from src.constants.features import Features
from src.combat.labels import CombatLabel


class TutorialDetector:
    """
    新手教程检测器
    
    提供统一的检测接口，封装YOLO、OCR和模板匹配
    """
    
    def __init__(self, task):
        """
        初始化检测器
        
        Args:
            task: 关联的任务对象（用于获取截图帧、日志等）
        """
        self.task = task
        self._verbose = False
        self._cached_ocr = None
        
        # 第一阶段结束检测相关
        self._end_detection_running = False
        self._end_detection_thread = None
        self._end_detected = False
        self._end_lock = threading.Lock()
    
    def set_verbose(self, verbose: bool):
        """设置是否输出详细日志"""
        self._verbose = verbose
    
    def _log(self, message: str):
        """输出日志"""
        if self._verbose and hasattr(self.task, 'logger'):
            self.task.logger.info(f"[检测器] {message}")
    
    # ==================== 选角界面检测 ====================
    
    def detect_character_select_screen(self, timeout: float = 10.0) -> bool:
        """
        检测是否在选角界面
        
        使用OCR检测"请选择一位你心仪的角色"文字
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            bool: 是否检测到选角界面
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # 检查退出信号
            if hasattr(self.task, '_should_exit') and self.task._should_exit():
                return False
            
            self.task.next_frame()
            texts = self._get_ocr_texts()
            
            # 定义匹配模式（简体中文）
            patterns = [
                re.compile(r"请选择一位你心仪的角色"),
                re.compile(r"请选择.*心仪的角色"),
                re.compile(r"选择.*角色"),
            ]
            
            # 根据游戏语言设置转换匹配模式
            converted_patterns = [self.task._convert_match_for_lang(p) for p in patterns]
            
            for pattern in converted_patterns:
                if self.task.find_boxes(texts, match=pattern):
                    self._log("检测到选角界面")
                    return True
            
            time.sleep(0.5)
        
        self._log("选角界面检测超时")
        return False
    
    # ==================== 按钮检测 ====================
    
    def detect_back_button(self, timeout: float = 5.0) -> Optional[Tuple[int, int]]:
        """
        检测返回按钮
        
        优先使用模板匹配，失败时使用OCR检测"返回"文字
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            Optional[Tuple[int, int]]: 按钮中心位置，未检测到返回 None
        """
        import re
        start_time = time.time()
        check_count = 0
        
        self._log(f"开始检测返回按钮，超时: {timeout}秒")
        
        while time.time() - start_time < timeout:
            check_count += 1
            
            try:
                self.task.next_frame()
                frame = self.task.frame
                
                if frame is None:
                    self._log(f"[{check_count}] frame is None, 跳过")
                    time.sleep(0.1)
                    continue
                
                # 第一次检测时输出OCR结果用于调试
                if check_count == 1:
                    try:
                        texts = self.task.ocr()
                        if texts:
                            text_names = [t.name for t in texts]
                            self._log(f"[{check_count}] OCR检测到文本: {text_names}")
                    except Exception as e:
                        self._log(f"[{check_count}] OCR检测失败: {e}")
                
                # 方法1: 模板匹配
                back_btn = self.task.find_one(Features.TUTORIAL_BACK_BUTTON, threshold=0.5)
                if back_btn:
                    self._log(f"[模板匹配] 检测到返回按钮: ({back_btn.x}, {back_btn.y}), 尺寸: {back_btn.width}x{back_btn.height}")
                    return (back_btn.x + back_btn.width // 2, back_btn.y + back_btn.height // 2)
                
                # 方法2: OCR检测"返回"文字
                try:
                    texts = self.task.ocr()
                    if texts:
                        # 查找包含"返"和"回"的文本框
                        for i, t in enumerate(texts):
                            if t.name == '返' and i + 1 < len(texts):
                                # 检查下一个是否是"回"
                                next_t = texts[i + 1]
                                if next_t.name == '回':
                                    # 合并两个框的位置，取中间点
                                    center_x = (t.x + t.width // 2 + next_t.x + next_t.width // 2) // 2
                                    center_y = (t.y + t.height // 2 + next_t.y + next_t.height // 2) // 2
                                    self._log(f"[OCR] 检测到返回文字: 合并位置 ({center_x}, {center_y})")
                                    return (center_x, center_y)
                        
                        # 也尝试匹配"返回"作为一个整体
                        back_texts = self.task.find_boxes(texts, match=re.compile(r"返回"))
                        if back_texts:
                            t = back_texts[0]
                            center_x = t.x + t.width // 2
                            center_y = t.y + t.height // 2
                            self._log(f"[OCR] 检测到返回文字: ({center_x}, {center_y})")
                            return (center_x, center_y)
                except Exception as e:
                    self._log(f"[{check_count}] OCR检测异常: {e}")
                
            except ValueError as e:
                # find_one 抛出 ValueError 表示未找到
                self._log(f"[{check_count}] ValueError: {e}")
            except Exception as e:
                self._log(f"[{check_count}] 检测异常: {type(e).__name__}: {e}")
            
            time.sleep(0.1)
        
        self._log(f"返回按钮检测超时 (共检测{check_count}次, 耗时{time.time()-start_time:.1f}秒)")
        return None
    
    def detect_confirm_button(self, timeout: float = 5.0) -> Optional[Tuple[int, int]]:
        """
        检测确定按钮
        
        优先使用模板匹配，失败时使用OCR检测"确定"文字
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            Optional[Tuple[int, int]]: 按钮中心位置，未检测到返回 None
        """
        import re
        start_time = time.time()
        check_count = 0
        
        self._log(f"开始检测确定按钮，超时: {timeout}秒")
        
        while time.time() - start_time < timeout:
            check_count += 1
            
            try:
                self.task.next_frame()
                frame = self.task.frame
                
                if frame is None:
                    self._log(f"[{check_count}] frame is None, 跳过")
                    time.sleep(0.1)
                    continue
                
                # 方法1: 模板匹配
                confirm_btn = self.task.find_one(Features.TUTORIAL_CONFIRM_BUTTON, threshold=0.5)
                if confirm_btn:
                    self._log(f"[模板匹配] 检测到确定按钮: ({confirm_btn.x}, {confirm_btn.y}), 尺寸: {confirm_btn.width}x{confirm_btn.height}")
                    return (confirm_btn.x + confirm_btn.width // 2, confirm_btn.y + confirm_btn.height // 2)
                
                # 方法2: OCR检测"确定"文字（支持繁体"確定"）
                try:
                    texts = self.task.ocr()
                    if texts:
                        # 匹配"确定"或"確定"
                        confirm_texts = self.task.find_boxes(texts, match=re.compile(r"确定|確定"))
                        if confirm_texts:
                            t = confirm_texts[0]
                            center_x = t.x + t.width // 2
                            center_y = t.y + t.height // 2
                            self._log(f"[OCR] 检测到确定文字: ({center_x}, {center_y})")
                            return (center_x, center_y)
                except Exception as e:
                    self._log(f"[{check_count}] OCR检测异常: {e}")
                
            except ValueError as e:
                if check_count % 10 == 0:
                    self._log(f"[{check_count}] ValueError: {e}")
            except Exception as e:
                self._log(f"[{check_count}] 检测异常: {type(e).__name__}: {e}")
            
            time.sleep(0.1)
        
        self._log(f"确定按钮检测超时 (共检测{check_count}次, 耗时{time.time()-start_time:.1f}秒)")
        return None
    
    # ==================== 加载界面检测 ====================
    
    def detect_loading_start(self, timeout: float = 10.0) -> bool:
        """
        检测加载界面开始
        
        通过检测画面变化判断
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            bool: 是否检测到加载开始
        """
        start_time = time.time()
        prev_frame = None
        
        while time.time() - start_time < timeout:
            self.task.next_frame()
            frame = self.task.frame
            
            if frame is None:
                time.sleep(0.1)
                continue
            
            # 简单判断：如果画面很暗（黑屏），认为进入加载
            import cv2
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            avg_brightness = gray.mean()
            
            if avg_brightness < 30:  # 亮度阈值
                self._log(f"检测到加载界面开始，亮度: {avg_brightness:.1f}")
                return True
            
            time.sleep(0.1)
        
        return False
    
    def detect_loading_end(self, timeout: float = 60.0) -> bool:
        """
        检测加载界面结束
        
        通过检测画面变化或YOLO可检测判断
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            bool: 是否检测到加载结束
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if hasattr(self.task, '_should_exit') and self.task._should_exit():
                return False
            
            self.task.next_frame()
            frame = self.task.frame
            
            if frame is None:
                time.sleep(0.1)
                continue
            
            # 检测画面亮度恢复
            import cv2
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            avg_brightness = gray.mean()
            
            if avg_brightness > 50:  # 亮度恢复
                self._log(f"检测到加载界面结束，亮度: {avg_brightness:.1f}")
                return True
            
            time.sleep(0.2)
        
        self._log("加载界面结束检测超时")
        return False
    
    # ==================== YOLO检测 ====================
    
    def detect_self(self, timeout: float = 30.0) -> Optional[object]:
        """
        检测自身位置
        
        使用 fight.onnx 检测
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            DetectionResult: 自身位置，超时返回 None
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if hasattr(self.task, '_should_exit') and self.task._should_exit():
                return None
            
            self.task.next_frame()
            frame = self.task.frame
            
            if frame is None:
                time.sleep(0.05)
                continue
            
            # 使用 fight.onnx 检测自己
            results = og.my_app.yolo_detect(
                frame,
                threshold=0.5,
                label=CombatLabel.SELF
            )
            
            if results:
                self._log(f"检测到自身: ({results[0].center_x}, {results[0].center_y})")
                return results[0]
            
            time.sleep(0.03)
        
        self._log("自身检测超时")
        return None
    
    def detect_target_circle(self, timeout: float = 10.0) -> Optional[object]:
        """
        检测目标圈
        
        使用 fight.onnx 检测
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            DetectionResult: 目标圈位置，超时返回 None
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if hasattr(self.task, '_should_exit') and self.task._should_exit():
                return None
            
            self.task.next_frame()
            frame = self.task.frame
            
            if frame is None:
                time.sleep(0.05)
                continue
            
            # 使用 fight.onnx 检测目标圈
            results = og.my_app.yolo_detect(
                frame,
                threshold=0.5,
                label=CombatLabel.TARGET_CIRCLE
            )
            
            if results:
                self._log(f"检测到目标圈: ({results[0].center_x}, {results[0].center_y})")
                return results[0]
            
            time.sleep(0.03)
        
        self._log("目标圈检测超时")
        return None
    
    def detect_monkey(self, timeout: float = 10.0) -> Optional[object]:
        """
        检测猴子
        
        使用 fight2.onnx 检测（悟空专用）
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            DetectionResult: 猴子位置，超时返回 None
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if hasattr(self.task, '_should_exit') and self.task._should_exit():
                return None
            
            self.task.next_frame()
            frame = self.task.frame
            
            if frame is None:
                time.sleep(0.05)
                continue
            
            # 使用 fight2.onnx 检测猴子（标签0）
            # 注意：需要切换模型
            try:
                results = og.my_app.yolo_detect(
                    frame,
                    threshold=0.5,
                    label=0  # 猴子标签
                )
                
                if results:
                    self._log(f"检测到猴子: ({results[0].center_x}, {results[0].center_y})")
                    return results[0]
            except Exception as e:
                self._log(f"猴子检测异常: {e}")
            
            time.sleep(0.03)
        
        self._log("猴子检测超时")
        return None
    
    # ==================== 普攻按钮检测 ====================
    
    def detect_normal_attack_button(self, timeout: float = 10.0) -> bool:
        """
        检测普攻按钮文字
        
        使用OCR检测"普攻按钮"
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            bool: 是否检测到普攻按钮
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if hasattr(self.task, '_should_exit') and self.task._should_exit():
                return False
            
            self.task.next_frame()
            texts = self._get_ocr_texts()
            
            # 检测"普攻按钮"相关文字（简体中文）
            patterns = [
                re.compile(r"普攻按钮"),
                re.compile(r"普攻"),
            ]
            
            # 根据游戏语言设置转换匹配模式
            converted_patterns = [self.task._convert_match_for_lang(p) for p in patterns]
            
            for pattern in converted_patterns:
                if self.task.find_boxes(texts, match=pattern):
                    self._log("检测到普攻按钮")
                    return True
            
            time.sleep(0.1)
        
        self._log("普攻按钮检测超时")
        return False
    
    # ==================== 第一阶段结束检测 ====================
    
    def start_phase1_end_detection(self, timeout: float = 120.0):
        """
        启动第一阶段结束检测（独立线程）
        
        同时检测 end01.png 和 end02.png
        
        Args:
            timeout: 超时时间（秒）
        """
        with self._end_lock:
            if self._end_detection_running:
                return
            
            self._end_detection_running = True
            self._end_detected = False
        
        self._end_detection_thread = threading.Thread(
            target=self._phase1_end_detection_loop,
            args=(timeout,),
            name="Phase1EndDetectionThread",
            daemon=True
        )
        self._end_detection_thread.start()
        self._log("第一阶段结束检测线程已启动")
    
    def stop_phase1_end_detection(self):
        """停止第一阶段结束检测"""
        with self._end_lock:
            self._end_detection_running = False
        
        if self._end_detection_thread and self._end_detection_thread.is_alive():
            self._end_detection_thread.join(timeout=1.0)
            self._log("第一阶段结束检测线程已停止")
    
    def is_phase1_end_detected(self) -> bool:
        """
        检查是否检测到第一阶段结束
        
        Returns:
            bool: 是否检测到
        """
        with self._end_lock:
            return self._end_detected
    
    def _phase1_end_detection_loop(self, timeout: float):
        """
        第一阶段结束检测循环（在独立线程中运行）
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            with self._end_lock:
                if not self._end_detection_running:
                    return
            
            if hasattr(self.task, '_should_exit') and self.task._should_exit():
                return
            
            self.task.next_frame()
            
            # 检测 end01.png
            try:
                end01 = self.task.find_one(Features.TUTORIAL_END01, threshold=0.6)
                if end01:
                    self._log("检测到第一阶段结束标志(end01)")
            except ValueError:
                end01 = None
            
            # 检测 end02.png（开始对战按钮）
            try:
                end02 = self.task.find_one(Features.TUTORIAL_END02, threshold=0.6)
                if end02:
                    self._log(f"检测到开始对战按钮(end02): ({end02.x}, {end02.y})")
                    
                    # 点击开始对战按钮
                    self.task.click(end02, after_sleep=1)
                    
                    with self._end_lock:
                        self._end_detected = True
                    return
            except ValueError:
                pass
            
            time.sleep(0.1)
        
        self._log("第一阶段结束检测超时")
    
    # ==================== 辅助方法 ====================
    
    def _get_ocr_texts(self):
        """获取OCR文本（带缓存）"""
        self._cached_ocr = self.task.ocr()
        return self._cached_ocr
    
    def _clear_ocr_cache(self):
        """清除OCR缓存"""
        self._cached_ocr = None
    
    def save_screenshot(self, filename: str) -> str:
        """
        保存当前截图
        
        Args:
            filename: 文件名（不含路径）
            
        Returns:
            str: 保存的文件路径
        """
        import os
        import cv2
        import numpy as np
        
        screenshots_dir = "screenshots"
        if not os.path.exists(screenshots_dir):
            os.makedirs(screenshots_dir)
        
        filepath = os.path.join(screenshots_dir, filename)
        
        frame = self.task.frame
        if frame is not None and isinstance(frame, np.ndarray):
            cv2.imwrite(filepath, frame)
            self._log(f"截图已保存: {filepath}")
            return filepath
        
        self._log("无法保存截图: frame 为空或不是有效的图像")
        return ""
