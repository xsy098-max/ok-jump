"""
第二阶段处理器

处理新手教程第二阶段的完整流程：
点击开始对战 → 双加载界面等待 → 战斗开始检测 → 自动战斗（并行结束检测） → 
战斗结束处理 → MVP场景处理（两次点击） → 新英雄场景处理 → 最终加载界面 → 主界面验证
"""

import re
import time
import threading
from typing import Optional, Tuple

from ok import og
from src.tutorial.tutorial_detector import TutorialDetector
from src.constants.features import Features


class Phase2Handler:
    """
    第二阶段处理器
    
    处理新手教程第二阶段的完整流程
    """
    
    def __init__(self, task):
        """
        初始化处理器
        
        Args:
            task: 关联的任务对象
        """
        self.task = task
        self.detector = TutorialDetector(task)
        self._verbose = False
        
        # 战斗相关
        self._combat_task = None
        self._combat_thread = None
        self._combat_start_time = None
        self._combat_end_detected = False
        self._combat_end_lock = threading.Lock()
        
        # 结束检测线程
        self._end_detection_thread = None
        self._end_detection_running = False
    
    def set_verbose(self, verbose: bool):
        """设置详细日志"""
        self._verbose = verbose
        self.detector.set_verbose(verbose)
    
    def _log(self, message: str):
        """输出日志"""
        if hasattr(self.task, 'logger'):
            self.task.logger.info(f"[第二阶段] {message}")
        else:
            print(f"[第二阶段] {message}")
    
    def _log_error(self, message: str):
        """输出错误日志"""
        if hasattr(self.task, 'logger'):
            self.task.logger.error(f"[第二阶段] {message}")
        else:
            print(f"[第二阶段] ERROR: {message}")
    
    def _log_verbose(self, message: str):
        """输出详细日志（仅在 verbose 模式下）"""
        if self._verbose:
            self._log(message)
    
    def _cfg(self, key: str, default=None):
        """获取配置值"""
        if self.task.config is not None:
            return self.task.config.get(key, default)
        return self.task.default_config.get(key, default)
    
    def run(self) -> bool:
        """
        运行第二阶段
        
        Returns:
            bool: 是否成功完成
        """
        self._log("=" * 50)
        self._log("开始执行第二阶段")
        self._log("=" * 50)
        
        try:
            # 步骤 2.1: 点击"开始对战"
            self._log("步骤 2.1: 点击开始对战")
            if not self._click_start_battle():
                self._log_error("点击开始对战失败")
                return False
            
            # 步骤 2.2: 双加载界面等待
            self._log("步骤 2.2: 双加载界面等待")
            if not self._wait_double_loading():
                self._log_error("双加载界面等待失败")
                return False
            
            # 步骤 2.3: 战斗开始检测
            self._log("步骤 2.3: 战斗开始检测")
            if not self._detect_battle_start():
                self._log_error("战斗开始检测失败")
                return False
            
            # 步骤 2.4 & 2.5: 启动自动战斗 + 并行结束检测
            self._log("步骤 2.4: 启动自动战斗")
            if not self._run_combat_with_end_detection():
                self._log_error("自动战斗失败")
                return False
            
            # 步骤 2.6: MVP场景处理（两次点击）
            self._log("步骤 2.6: MVP场景处理")
            if not self._handle_mvp_scene():
                self._log_error("MVP场景处理失败")
                return False
            
            # 步骤 2.7: 新英雄场景处理
            self._log("步骤 2.7: 新英雄场景处理")
            if not self._handle_new_hero_scene():
                self._log_error("新英雄场景处理失败")
                return False
            
            # 步骤 2.8: 最终加载界面
            self._log("步骤 2.8: 最终加载界面")
            if not self._wait_final_loading():
                self._log_error("最终加载界面等待失败")
                return False
            
            # 步骤 2.9: 主界面验证
            self._log("步骤 2.9: 主界面验证")
            if not self._verify_main_interface():
                self._log_error("主界面验证失败")
                return False
            
            self._log("=" * 50)
            self._log("第二阶段完成")
            self._log("=" * 50)
            return True
            
        except Exception as e:
            self._log_error(f"第二阶段异常: {e}")
            import traceback
            self._log_error(traceback.format_exc())
            self._save_error_screenshot(f"phase2_error_{time.strftime('%H-%M-%S')}")
            return False
    
    # ==================== 步骤 2.1: 点击开始对战 ====================
    
    def _click_start_battle(self) -> bool:
        """
        点击"开始对战"按钮
        
        主检测：模板匹配 end02.png
        备选检测：OCR 识别"开始对战"文字（简繁双语）
        
        Returns:
            bool: 是否成功
        """
        timeout = 10.0
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self._should_exit():
                return False
            
            self.task.next_frame()
            
            # 方法1: 模板匹配
            try:
                btn = self.task.find_one(Features.TUTORIAL_END02, threshold=0.6)
                if btn:
                    self._log(f"[模板匹配] 检测到开始对战按钮: ({btn.x}, {btn.y})")
                    self.task.click(btn, after_sleep=1.0)
                    
                    # 验证点击成功（按钮消失）
                    if self._verify_button_clicked(Features.TUTORIAL_END02, "开始对战"):
                        self._log("开始对战按钮点击成功")
                        return True
                    continue
            except (ValueError, Exception):
                pass
            
            # 方法2: OCR检测"开始对战"（简繁双语）
            pos = self._detect_text_bilingual("开始对战", "開始對戰")
            if pos:
                self._log(f"[OCR] 检测到开始对战文字: {pos}")
                self.task.click(pos[0], pos[1], after_sleep=1.0)
                
                # 验证点击成功
                if self._verify_button_clicked(Features.TUTORIAL_END02, "开始对战"):
                    self._log("开始对战按钮点击成功")
                    return True
                continue
            
            time.sleep(0.2)
        
        self._log_error("开始对战按钮检测超时")
        self._save_error_screenshot("start_battle_not_found")
        return False
    
    def _verify_button_clicked(self, feature, text_pattern: str, timeout: float = 3.0) -> bool:
        """验证按钮已被点击（按钮消失）"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            self.task.next_frame()
            
            # 检查模板是否消失
            try:
                btn = self.task.find_one(feature, threshold=0.6)
                if not btn:
                    return True
            except (ValueError, Exception):
                return True
            
            time.sleep(0.1)
        return False
    
    # ==================== 步骤 2.2: 双加载界面等待 ====================
    
    def _check_battle_start_sign(self) -> bool:
        """
        检测战斗开始标志（积分争夺）
        
        用于在加载过程中提前检测战斗是否已开始
        检测方式与步骤 2.3 战斗开始检测一致
        
        Returns:
            bool: 是否检测到战斗开始标志
        """
        # 方法1: 模板匹配 fight_start.png
        try:
            fight_start = self.task.find_one(Features.TUTORIAL_FIGHT_START, threshold=0.6)
            if fight_start:
                return True
        except (ValueError, Exception):
            pass
        
        # 方法2: OCR检测"积分争夺"（简繁双语）
        if self._detect_text_bilingual("积分争夺", "積分爭奪"):
            return True
        
        return False
    
    def _wait_loading_start_with_battle_check(self, timeout: float, phase_name: str) -> str:
        """
        等待加载开始，同时检测战斗开始标志
        
        Args:
            timeout: 超时时间
            phase_name: 阶段名称（用于日志）
            
        Returns:
            str: "success" - 检测到加载开始
                 "battle_started" - 检测到战斗开始标志
                 "timeout" - 超时
                 "exit" - 请求退出
        """
        start_time = time.time()
        check_interval = 1.0  # 每次检测加载的间隔
        
        while time.time() - start_time < timeout:
            if self._should_exit():
                return "exit"
            
            self.task.next_frame()
            
            # 检测战斗开始标志
            if self._check_battle_start_sign():
                self._log(f"[容错] {phase_name}等待期间检测到战斗开始标志（积分争夺）")
                return "battle_started"
            
            # 检测加载开始（使用短超时）
            if self.detector.detect_loading_start(timeout=check_interval):
                return "success"
        
        return "timeout"
    
    def _wait_loading_end_with_battle_check(self, timeout: float, stuck_timeout: float, phase_name: str) -> str:
        """
        等待加载结束，同时检测战斗开始标志
        
        Args:
            timeout: 总超时时间
            stuck_timeout: 停滞检测超时时间
            phase_name: 阶段名称（用于日志）
            
        Returns:
            str: "success" - 加载正常结束
                 "battle_started" - 检测到战斗开始标志
                 "timeout" - 超时或停滞
                 "exit" - 请求退出
        """
        start_time = time.time()
        check_interval = 5.0  # 每次分段检测的时长
        battle_check_interval = 2.0  # 战斗标志检测间隔
        last_battle_check = 0
        
        while time.time() - start_time < timeout:
            if self._should_exit():
                return "exit"
            
            current_time = time.time()
            
            # 定期检测战斗开始标志
            if current_time - last_battle_check >= battle_check_interval:
                self.task.next_frame()
                if self._check_battle_start_sign():
                    self._log(f"[容错] {phase_name}等待期间检测到战斗开始标志（积分争夺）")
                    return "battle_started"
                last_battle_check = current_time
            
            # 分段检测加载结束
            remaining_time = timeout - (current_time - start_time)
            segment_timeout = min(check_interval, remaining_time)
            segment_stuck = min(stuck_timeout, remaining_time)
            
            if self.detector.detect_loading_end(timeout=segment_timeout, stuck_timeout=segment_stuck):
                return "success"
            
            # 如果不是正常完成，继续循环检测
        
        return "timeout"
    
    def _wait_double_loading(self) -> bool:
        """
        等待双加载界面
        
        第一个加载 → 两个加载之间的容错窗口 → 第二个加载
        
        容错机制：如果在等待加载界面的过程中检测到了"积分争夺"文字/图片，
        则跳过当前加载界面的等待，直接进入战斗开始检测阶段
        
        Returns:
            bool: 是否成功
        """
        loading_gap_tolerance = self._cfg('加载界面间隔容错(秒)', 15.0)
        
        # ========== 第一个加载界面 ==========
        self._log("等待第一个加载界面...")
        self.detector.reset_loading_state()
        
        # 等待第一个加载开始（带战斗检测）
        result = self._wait_loading_start_with_battle_check(30.0, "第一个加载界面")
        if result == "exit":
            return False
        elif result == "battle_started":
            self._log("提前检测到战斗开始标志，跳过剩余加载等待")
            return True
        elif result == "timeout":
            self._log_error("第一个加载界面未检测到")
            self._save_error_screenshot("first_loading_not_found")
            return False
        
        # 等待第一个加载结束（带战斗检测）
        self._log("第一个加载界面开始，等待加载完成...")
        result = self._wait_loading_end_with_battle_check(120.0, 60.0, "第一个加载界面")
        if result == "exit":
            return False
        elif result == "battle_started":
            self._log("提前检测到战斗开始标志，跳过剩余加载等待")
            return True
        elif result == "timeout":
            self._log_error("第一个加载界面超时或停滞")
            self._save_error_screenshot("first_loading_timeout")
            return False
        
        self._log("第一个加载界面结束")
        
        # ========== 两个加载之间的容错窗口 ==========
        self._log(f"等待第二个加载界面（容错窗口: {loading_gap_tolerance}秒）...")
        self.detector.reset_loading_state()  # 重置状态，因为第二个加载百分比可能比第一个结束时小
        
        start_time = time.time()
        second_loading_found = False
        
        while time.time() - start_time < loading_gap_tolerance:
            if self._should_exit():
                return False
            
            self.task.next_frame()
            
            # 检测战斗开始标志
            if self._check_battle_start_sign():
                self._log("[容错] 容错窗口期间检测到战斗开始标志（积分争夺），跳过剩余加载等待")
                return True
            
            if self.detector.detect_loading_start(timeout=1.0):
                second_loading_found = True
                break
            
            time.sleep(0.2)
        
        if not second_loading_found:
            # 最后检查一次战斗开始标志
            self.task.next_frame()
            if self._check_battle_start_sign():
                self._log("[容错] 容错窗口结束时检测到战斗开始标志（积分争夺），跳过第二个加载等待")
                return True
            self._log_error(f"第二个加载界面未在 {loading_gap_tolerance}秒内出现")
            self._save_error_screenshot("second_loading_not_found")
            return False
        
        # ========== 第二个加载界面 ==========
        self._log("第二个加载界面开始，等待加载完成...")
        result = self._wait_loading_end_with_battle_check(120.0, 60.0, "第二个加载界面")
        if result == "exit":
            return False
        elif result == "battle_started":
            self._log("提前检测到战斗开始标志，跳过剩余加载等待")
            return True
        elif result == "timeout":
            self._log_error("第二个加载界面超时或停滞")
            self._save_error_screenshot("second_loading_timeout")
            return False
        
        self._log("第二个加载界面结束，双加载完成")
        return True
    
    # ==================== 步骤 2.3: 战斗开始检测 ====================
    
    def _detect_battle_start(self) -> bool:
        """
        检测战斗开始
        
        主检测：模板匹配 fight_start.png
        备选检测：OCR 识别"积分争夺"文字（简繁双语）
        
        Returns:
            bool: 是否检测到战斗开始
        """
        timeout = 30.0
        start_time = time.time()
        
        self._log("检测战斗开始标志...")
        
        while time.time() - start_time < timeout:
            if self._should_exit():
                return False
            
            self.task.next_frame()
            
            # 方法1: 模板匹配
            try:
                fight_start = self.task.find_one(Features.TUTORIAL_FIGHT_START, threshold=0.6)
                if fight_start:
                    self._log(f"[模板匹配] 检测到战斗开始标志: ({fight_start.x}, {fight_start.y})")
                    self._combat_start_time = time.time()
                    return True
            except (ValueError, Exception):
                pass
            
            # 方法2: OCR检测"积分争夺"（简繁双语）
            if self._detect_text_bilingual("积分争夺", "積分爭奪"):
                self._log("[OCR] 检测到积分争夺文字")
                self._combat_start_time = time.time()
                return True
            
            time.sleep(0.2)
        
        self._log_error("战斗开始检测超时")
        self._save_error_screenshot("battle_start_not_found")
        return False
    
    # ==================== 步骤 2.4 & 2.5: 自动战斗 + 并行结束检测 ====================
    
    def _run_combat_with_end_detection(self) -> bool:
        """
        运行自动战斗，同时并行检测战斗结束
    
        如果GUI中已开启自动战斗，则跳过启动战斗线程，只进行战斗结束检测
        但需要确保GUI自动战斗已进入战斗执行状态（检测到自身）
    
        Returns:
            bool: 是否成功
        """
        from src.task.AutoCombatTask import AutoCombatTask
    
        combat_timeout = self._cfg('第二阶段战斗超时(秒)', 210.0)
        gui_combat_running = AutoCombatTask.is_running()
    
        if gui_combat_running:
            self._log("检测到GUI自动战斗已运行")
            self._combat_task = AutoCombatTask.get_running_instance()
                
            # 【关键修复】等待GUI自动战斗进入战斗执行状态
            # GUI自动战斗使用状态感知主循环，需要检测到自身才会启动战斗线程
            # 这里需要等待它真正进入战斗状态
            if not self._wait_gui_combat_active(timeout=30.0):
                self._log("GUI自动战斗未能在超时内进入战斗状态，启动自己的战斗线程")
                gui_combat_running = False
                # 启动自己的战斗线程
                if not self._start_combat_thread():
                    return False
            else:
                self._log("GUI自动战斗已进入战斗执行状态，仅进行战斗结束检测")
        else:
            self._log(f"启动自动战斗线程（超时: {combat_timeout}秒）...")
            # 启动自动战斗线程
            if not self._start_combat_thread():
                return False
        
        # 启动结束检测线程
        self._start_end_detection_thread(combat_timeout)
        
        # 等待战斗结束
        start_time = time.time()
        while time.time() - start_time < combat_timeout:
            if self._should_exit():
                self._stop_combat()
                return False
            
            with self._combat_end_lock:
                if self._combat_end_detected:
                    break
            
            time.sleep(0.5)
        
        # 停止检测
        self._stop_end_detection()
        
        # 【关键修复】只停止自己启动的战斗实例，不影响 GUI 自动战斗触发器
        # GUI 触发器由用户控制启停，第二阶段不应干预
        self._stop_combat(stop_gui_combat=False)
        
        with self._combat_end_lock:
            if self._combat_end_detected:
                # 计算战斗持续时间
                if self._combat_start_time:
                    duration = time.time() - self._combat_start_time
                    self._log(f"战斗结束，持续时间: {duration:.1f}秒")
                else:
                    self._log("战斗结束")
                return True
            else:
                self._log_error("战斗结束检测超时")
                self._save_error_screenshot("combat_end_timeout")
                return False
    
    def _get_combat_config(self, key: str, default=None):
        """
        从 AutoCombatTask 配置中读取战斗参数
        
        确保新手教程中的自动战斗使用用户在GUI中配置的参数
        
        Args:
            key: 配置键名
            default: 默认值
            
        Returns:
            配置值
        """
        # 优先从全局配置中获取 AutoCombatTask 的配置
        try:
            if og and og.config:
                combat_config = og.config.get('AutoCombatTask', {})
                if combat_config and key in combat_config:
                    return combat_config[key]
        except Exception:
            pass
        
        # 回退：从配置文件直接读取
        try:
            import json
            import os
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'configs', 'AutoCombatTask.json'
            )
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    combat_config = json.load(f)
                    if key in combat_config:
                        return combat_config[key]
        except Exception:
            pass
        
        return default
    
    def _wait_gui_combat_active(self, timeout: float = 30.0) -> bool:
        """
        等待GUI自动战斗进入战斗执行状态

        GUI自动战斗使用状态感知主循环，需要通过YOLO检测到自身才会启动战斗线程。
        此方法等待战斗线程真正启动。

        Args:
            timeout: 超时时间（秒）

        Returns:
            bool: 是否成功进入战斗状态
        """
        if self._combat_task is None:
            return False

        start_time = time.time()
        check_count = 0

        self._log(f"等待GUI自动战斗进入战斗执行状态（超时: {timeout}秒）...")

        while time.time() - start_time < timeout:
            if self._should_exit():
                return False

            check_count += 1

            # 检查战斗线程是否激活
            if hasattr(self._combat_task, '_is_combat_active'):
                if self._combat_task._is_combat_active():
                    self._log(f"GUI自动战斗已激活战斗线程（检查{check_count}次后确认）")
                    return True

            # 每5次检查输出一次状态
            if check_count % 5 == 0:
                elapsed = time.time() - start_time
                self._log(f"等待中... 已检查{check_count}次, 耗时{elapsed:.1f}秒")

            # 更新帧，让GUI自动战斗能够检测到自身
            self.task.next_frame()
            time.sleep(0.1)

        self._log(f"等待超时，共检查{check_count}次")
        return False

    def _start_combat_thread(self) -> bool:
        """启动自动战斗线程"""
        try:
            from src.task.AutoCombatTask import AutoCombatTask
            
            # 直接创建新的任务实例（参照 phase1_handler.py 的创建方式）
            self._combat_task = AutoCombatTask(self.task.executor, self.task)
            self._combat_task._exit_requested = False
            
            # 【关键修复】手动加载 AutoCombatTask 的配置
            # 因为手动创建实例时，框架不会自动加载配置文件
            # 这确保了"移动持续时间(秒)"等配置能正确从配置文件读取
            if self._combat_task.config is None:
                self._combat_task.config = {}
            
            # 加载所有必要的配置（从配置文件或默认值）
            config_keys = [
                '测试模式', '详细日志',
                '自动普攻', '自动技能1', '自动技能2', '自动大招',
                '普攻间隔(秒)', '技能1间隔(秒)', '技能2间隔(秒)', '大招间隔(秒)',
                '移动持续时间(秒)'
            ]
            for key in config_keys:
                # 从配置文件读取，如果不存在则使用 default_config
                default_value = self._combat_task.default_config.get(key)
                self._combat_task.config[key] = self._get_combat_config(key, default_value)
            
            # 设置测试模式（跳过游戏场景检测）
            self._combat_task.config['测试模式'] = True
            
            # 记录当前配置（用于调试）
            move_duration = self._combat_task.config.get('移动持续时间(秒)', 0.5)
            self._log(f"已启用测试模式，移动持续时间: {move_duration}秒")
            
            # 在独立线程中运行
            self._combat_thread = threading.Thread(
                target=self._run_combat_task,
                name="Phase2CombatThread",
                daemon=True
            )
            self._combat_thread.start()
            self._log("自动战斗线程已启动")
            return True
            
        except Exception as e:
            self._log_error(f"启动自动战斗失败: {e}")
            return False
    
    def _run_combat_task(self):
        """在线程中运行自动战斗任务"""
        try:
            self._log("[Phase2CombatThread] 自动战斗开始运行")
            self._combat_task.run()
            self._log("[Phase2CombatThread] 自动战斗正常结束")
        except Exception as e:
            self._log_error(f"[Phase2CombatThread] 自动战斗异常: {e}")
    
    def _stop_combat(self, stop_gui_combat=False):
        """停止自动战斗
        
        Args:
            stop_gui_combat: 是否停止 GUI 自动战斗触发器（默认 False，不影响 GUI）
        
        注意：此方法默认只停止 phase2_handler 自己创建的战斗实例。
        GUI 自动战斗触发器由用户控制，不应在第二阶段结束时关闭。
        """
        # 如果是自己启动的战斗线程，停止它
        if self._combat_thread and self._combat_task:
            self._log("停止自己启动的战斗线程...")
            self._combat_task._exit_requested = True
            
            # 【关键修复】完整停止所有战斗相关组件
            
            # 1. 停止移动控制器
            if hasattr(self._combat_task, 'movement_ctrl') and self._combat_task.movement_ctrl:
                self._combat_task.movement_ctrl.stop()
            
            # 2. 完全关闭技能控制器（停止线程）
            if hasattr(self._combat_task, 'skill_ctrl') and self._combat_task.skill_ctrl:
                self._combat_task.skill_ctrl.shutdown()
            
            # 3. 重置战斗状态
            if hasattr(self._combat_task, 'state_detector') and self._combat_task.state_detector:
                self._combat_task.state_detector.reset_combat_state()
            
            # 4. 停止死亡监控线程
            if hasattr(self._combat_task, 'state_detector') and self._combat_task.state_detector:
                self._combat_task.state_detector.stop_death_monitor()
            
            # 等待线程结束
            if self._combat_thread.is_alive():
                self._combat_thread.join(timeout=3.0)
            
            self._log("自己启动的战斗线程已停止")
        
        
        # 【重要】默认不停止 GUI 自动战斗触发器
        # GUI 触发器由用户控制启停，第二阶段不应干预
        # 只有在明确需要时（stop_gui_combat=True）才停止 GUI 触发器
        # 这种情况极少见，通常只在程序退出时使用
        if stop_gui_combat:
            from src.task.AutoCombatTask import AutoCombatTask
            gui_combat_task = AutoCombatTask.get_running_instance()
            if gui_combat_task:
                # 确认是 GUI 触发器，不是自己创建的实例
                if gui_combat_task is not self._combat_task:
                    self._log("停止 GUI 自动战斗触发器...")
                    
                    # 设置退出标志
                    gui_combat_task._exit_requested = True
                    
                    # 停止战斗执行线程
                    if hasattr(gui_combat_task, '_stop_combat_thread'):
                        gui_combat_task._stop_combat_thread()
                    
                    # 停止移动控制器
                    if hasattr(gui_combat_task, 'movement_ctrl') and gui_combat_task.movement_ctrl:
                        gui_combat_task.movement_ctrl.stop()
                    
                    # 关闭技能控制器
                    if hasattr(gui_combat_task, 'skill_ctrl') and gui_combat_task.skill_ctrl:
                        gui_combat_task.skill_ctrl.shutdown()
                    
                    # 重置战斗状态
                    if hasattr(gui_combat_task, 'state_detector') and gui_combat_task.state_detector:
                        gui_combat_task.state_detector.reset_combat_state()
                    
                    # 停止死亡监控
                    if hasattr(gui_combat_task, 'state_detector') and gui_combat_task.state_detector:
                        gui_combat_task.state_detector.stop_death_monitor()
                    
                    
                    self._log("GUI 自动战斗触发器已停止")
    
    def _start_end_detection_thread(self, timeout: float):
        """启动结束检测线程"""
        self._end_detection_running = True
        self._combat_end_detected = False
        
        self._end_detection_thread = threading.Thread(
            target=self._end_detection_loop,
            args=(timeout,),
            name="Phase2EndDetectionThread",
            daemon=True
        )
        self._end_detection_thread.start()
        self._log("战斗结束检测线程已启动")
    
    def _stop_end_detection(self):
        """停止结束检测线程"""
        self._end_detection_running = False
        if self._end_detection_thread and self._end_detection_thread.is_alive():
            self._end_detection_thread.join(timeout=2.0)
        self._log("战斗结束检测线程已停止")
    
    def _end_detection_loop(self, timeout: float):
        """结束检测循环（在独立线程中运行）"""
        start_time = time.time()
        check_count = 0
        
        self._log(f"[结束检测] 线程开始运行，超时: {timeout}秒")
        
        while time.time() - start_time < timeout:
            if not self._end_detection_running:
                self._log("[结束检测] 检测被停止")
                return
            
            check_count += 1
            
            # 每20次循环输出一次状态
            if check_count % 20 == 0:
                elapsed = time.time() - start_time
                self._log(f"[结束检测] 已运行 {elapsed:.1f}秒，检测次数: {check_count}")
            
            try:
                self.task.next_frame()
            except Exception as e:
                if check_count % 20 == 0:
                    self._log(f"[结束检测] next_frame异常: {e}")
            
            # 方法1: 模板匹配 fight_end.png
            try:
                fight_end = self.task.find_one(Features.TUTORIAL_FIGHT_END, threshold=0.6)
                if fight_end:
                    self._log(f"[结束检测] 检测到战斗结束标志(模板): ({fight_end.x}, {fight_end.y})")
                    with self._combat_end_lock:
                        self._combat_end_detected = True
                    return
            except (ValueError, Exception):
                pass
            
            # 方法2: OCR检测"对战结束"（简繁双语）
            try:
                texts = self.task.ocr()
                if texts:
                    # 简繁双语匹配
                    patterns = [
                        re.compile(r"对战结束|對戰結束"),
                    ]
                    for pattern in patterns:
                        matched = self.task.find_boxes(texts, match=pattern)
                        if matched:
                            self._log(f"[结束检测] OCR匹配到结束文字: '{matched[0].name}'")
                            with self._combat_end_lock:
                                self._combat_end_detected = True
                            return
            except Exception as e:
                if check_count % 20 == 0:
                    self._log(f"[结束检测] OCR异常: {e}")
            
            # ========== 容错机制：检测 MVP 场景 ==========
            # 如果检测到 MVP 场景元素，说明战斗已经结束，游戏进入了结算流程
            try:
                # 容错1: 模板匹配 MVP 退出按钮 (out.png)
                mvp_out = self.task.find_one(Features.TUTORIAL_MVP_OUT, threshold=0.6)
                if mvp_out:
                    self._log(f"[结束检测-容错] 检测到MVP场景元素(模板out.png): ({mvp_out.x}, {mvp_out.y})")
                    with self._combat_end_lock:
                        self._combat_end_detected = True
                    return
            except (ValueError, Exception):
                pass
            
            try:
                # 容错2: OCR检测"点击荧幕退出" / "點擊螢幕退出"
                mvp_pattern = re.compile(r"点击荧幕退出|點擊螢幕退出")
                texts = self.task.ocr()
                if texts:
                    mvp_matched = self.task.find_boxes(texts, match=mvp_pattern)
                    if mvp_matched:
                        self._log(f"[结束检测-容错] OCR匹配到MVP场景文字: '{mvp_matched[0].name}'")
                        with self._combat_end_lock:
                            self._combat_end_detected = True
                        return
            except Exception as e:
                if check_count % 20 == 0:
                    self._log(f"[结束检测] MVP容错检测异常: {e}")
            
            time.sleep(0.1)
        
        self._log(f"[结束检测] 检测超时，共检测 {check_count} 次")
    
    # ==================== 步骤 2.6: MVP场景处理 ====================
    
    def _handle_mvp_scene(self) -> bool:
        """
        处理MVP场景（包含两次点击）
    
        第一次 MVP 点击 → 中间加载界面 → 第二次 MVP 点击
    
        容错机制：
        - 如果检测到已经是第二次MVP场景（點擊螢幕繼續），跳过第一次MVP点击
        - 如果检测到新英雄场景，跳过整个MVP处理
    
        Returns:
            bool: 是否成功
        """
        transition_timeout = self._cfg('战斗结束过渡容错(秒)', 20.0)
        mvp_timeout = self._cfg('MVP场景超时(秒)', 20.0)
    
        # 第一次 MVP 点击
        self._log(f"等待MVP场景出现（容错窗口: {transition_timeout}秒）...")
        time.sleep(2.0)  # 短暂等待战斗结束动画
    
        # 【关键修复】先检测是否已经是第二次MVP场景或新英雄场景
        # 这种情况可能发生在：战斗结束检测跳过了第一次MVP，或者游戏流程变化
        if self._check_mvp_out2():
            self._log("[容错] 检测到已是第二次MVP场景，跳过第一次MVP点击")
            # 直接进行第二次MVP点击
            self._log("检测第二次MVP场景...")
            if not self._detect_and_click_mvp(
                timeout=mvp_timeout,
                simplified_text="点击荧幕继续",
                traditional_text="點擊螢幕繼續",
                feature_name=Features.TUTORIAL_MVP_OUT2
            ):
                self._log_error("第二次MVP点击失败")
                self._save_error_screenshot("mvp_second_click_failed")
                return False
            self._log("第二次MVP点击成功，MVP场景处理完成")
            return True
    
        if self._check_new_hero_scene():
            self._log("[容错] 检测到新英雄场景，跳过MVP处理")
            return True
    
        if not self._detect_and_click_mvp(timeout=transition_timeout):
            # 【容错】第一次MVP点击失败后，再检测一次是否已经是第二次MVP
            if self._check_mvp_out2():
                self._log("[容错] 第一次MVP检测失败后发现已是第二次MVP场景")
                if not self._detect_and_click_mvp(
                    timeout=mvp_timeout,
                    simplified_text="点击荧幕继续",
                    traditional_text="點擊螢幕繼續",
                    feature_name=Features.TUTORIAL_MVP_OUT2
                ):
                    self._log_error("第二次MVP点击失败")
                    self._save_error_screenshot("mvp_second_click_failed")
                    return False
                self._log("第二次MVP点击成功，MVP场景处理完成")
                return True
    
            self._log_error("第一次MVP点击失败")
            self._save_error_screenshot("mvp_first_click_failed")
            return False
        
        self._log("第一次MVP点击成功，等待中间加载界面...")
        
        # 中间加载界面（带容错检测）
        self.detector.reset_loading_state()
        
        # 【容错机制】在等待加载界面的同时检测下一个界面
        # 如果检测到第二次MVP场景或新英雄场景，跳过加载等待
        loading_start = time.time()
        loading_started = False
        
        # 先尝试检测加载界面开始（最多10秒）
        while time.time() - loading_start < 10.0:
            if self._should_exit():
                return False
            
            self.task.next_frame()
            
            # 容错：检测第二次MVP场景（点击荧幕继续）
            if self._check_mvp_out2():
                self._log("[容错] 检测到第二次MVP场景，跳过中间加载等待")
                break
            
            # 容错：检测新英雄场景
            if self._check_new_hero_scene():
                self._log("[容错] 检测到新英雄场景，跳过中间加载等待")
                break
            
            # 检测加载界面开始
            if self.detector.detect_loading_start(timeout=1.0):
                loading_started = True
                break
            
            time.sleep(0.2)
        
        
        if loading_started:
            self._log("中间加载界面开始...")
            
            # 等待加载结束（带容错检测）
            loading_end_start = time.time()
            while time.time() - loading_end_start < 120.0:
                if self._should_exit():
                    return False
                
                self.task.next_frame()
                
                # 容错：检测第二次MVP场景
                if self._check_mvp_out2():
                    self._log("[容错] 加载期间检测到第二次MVP场景，跳过剩余加载等待")
                    break
                
                # 容错：检测新英雄场景
                if self._check_new_hero_scene():
                    self._log("[容错] 加载期间检测到新英雄场景，跳过剩余加载等待")
                    break
                
                # 检测加载结束
                if self.detector.detect_loading_end(timeout=5.0, stuck_timeout=60.0):
                    self._log("中间加载界面结束")
                    break
                
                time.sleep(0.3)
        else:
            self._log("未检测到中间加载界面，直接进行第二次检测...")
        
        # 第二次 MVP 点击（使用不同的文字：点击荧幕继续 / 點擊螢幕繼續，模板: out2.png）
        self._log("检测第二次MVP场景...")
        if not self._detect_and_click_mvp(
            timeout=mvp_timeout,
            simplified_text="点击荧幕继续",
            traditional_text="點擊螢幕繼續",
            feature_name=Features.TUTORIAL_MVP_OUT2
        ):
            self._log_error("第二次MVP点击失败")
            self._save_error_screenshot("mvp_second_click_failed")
            return False
        
        self._log("第二次MVP点击成功，MVP场景处理完成")
        return True
    
    def _detect_and_click_mvp(self, timeout: float, 
                                simplified_text: str = "点击荧幕退出", 
                                traditional_text: str = "點擊螢幕退出",
                                feature_name: str = None) -> bool:
        """
        检测并点击MVP场景
        
        主检测：模板匹配指定的特征图片
        备选检测：OCR 识别指定文字（简繁双语）
        
        Args:
            timeout: 超时时间
            simplified_text: 简体中文检测文字
            traditional_text: 繁体中文检测文字
            feature_name: 模板特征名，默认使用 Features.TUTORIAL_MVP_OUT
            
        Returns:
            bool: 是否成功
        """
        # 默认使用第一次 MVP 的模板
        if feature_name is None:
            feature_name = Features.TUTORIAL_MVP_OUT
        start_time = time.time()
        check_count = 0
        last_progress_log_time = start_time
        ocr_logged_once = False  # 控制OCR诊断日志只输出一次
        
        while time.time() - start_time < timeout:
            if self._should_exit():
                return False
            
            check_count += 1
            
            # 每5秒输出一次检测进度
            now = time.time()
            if now - last_progress_log_time >= 5:
                self._log(f"MVP检测进行中: 已检测{check_count}次, 耗时{now - start_time:.1f}秒")
                last_progress_log_time = now
            
            self.task.next_frame()
            
            # 方法1: 模板匹配
            try:
                mvp_btn = self.task.find_one(feature_name, threshold=0.6)
                if mvp_btn:
                    self._log(f"[模板匹配] 检测到MVP退出提示: ({mvp_btn.x}, {mvp_btn.y}), 模板: {feature_name}")
                    # 点击屏幕中心
                    center_x = self.task.width // 2
                    center_y = self.task.height // 2
                    self._log(f"点击屏幕中心: ({center_x}, {center_y})")
                    self.task.click(center_x, center_y, after_sleep=1.0)
                    return True
            except (ValueError, Exception):
                pass
            
            # 方法2: OCR检测指定文字（简繁双语）
            pos = self._detect_text_bilingual(simplified_text, traditional_text)
            if pos:
                self._log(f"[OCR] 检测到'{simplified_text}'文字: {pos}")
                # 点击屏幕中心
                center_x = self.task.width // 2
                center_y = self.task.height // 2
                self._log(f"点击屏幕中心: ({center_x}, {center_y})")
                self.task.click(center_x, center_y, after_sleep=1.0)
                return True
            else:
                # OCR诊断日志（只输出一次）
                if not ocr_logged_once:
                    try:
                        texts = self.task.ocr()
                        if texts:
                            text_names = [t.name for t in texts]
                            self._log(f"[OCR诊断] 首次OCR识别结果: {text_names}")
                            self._log(f"[OCR诊断] 目标文字: '{simplified_text}' / '{traditional_text}'")
                            ocr_logged_once = True
                    except Exception as e:
                        self._log(f"[OCR诊断] OCR检测异常: {e}")
            
            time.sleep(0.2)
        
        # 超时总结日志
        self._log_error(f"MVP检测超时: {timeout}秒内共检测{check_count}次均未匹配")
        return False
    
    def _check_mvp_out2(self) -> bool:
        """
        检测第二次MVP场景（点击荧幕继续）
        
        用于容错机制：在中间加载界面等待时检测下一个界面
        
        Returns:
            bool: 是否检测到第二次MVP场景
        """
        # 模板匹配 out2.png
        try:
            mvp_out2 = self.task.find_one(Features.TUTORIAL_MVP_OUT2, threshold=0.6)
            if mvp_out2:
                return True
        except (ValueError, Exception):
            pass
        
        # OCR检测"点击荧幕继续" / "點擊螢幕繼續"
        if self._detect_text_bilingual("点击荧幕继续", "點擊螢幕繼續"):
            return True
        
        return False
    
    def _check_new_hero_scene(self) -> bool:
        """
        检测新英雄场景
        
        用于容错机制：在加载界面等待时检测下一个界面
        
        Returns:
            bool: 是否检测到新英雄场景
        """
        # 模板匹配 new_hero.png
        try:
            new_hero = self.task.find_one(Features.TUTORIAL_NEW_HERO, threshold=0.6)
            if new_hero:
                return True
        except (ValueError, Exception):
            pass
        
        # OCR检测"新英雄"
        if self._detect_text_bilingual("新英雄", "新英雄"):
            return True
        
        return False
    
    # ==================== 步骤 2.7: 新英雄场景处理 ====================
    
    def _handle_new_hero_scene(self) -> bool:
        """
        处理新英雄场景
        
        需要同时检测到两个元素：
        - new_hero.png / "新英雄"
        - comfirm.png / "确定"
        
        Returns:
            bool: 是否成功
        """
        transition_timeout = self._cfg('MVP过渡容错(秒)', 15.0)
        new_hero_timeout = self._cfg('新英雄场景超时(秒)', 20.0)
        
        self._log(f"等待新英雄场景（容错窗口: {transition_timeout}秒）...")
        time.sleep(transition_timeout)
        
        self._log(f"检测新英雄场景（超时: {new_hero_timeout}秒）...")
        start_time = time.time()
        
        while time.time() - start_time < new_hero_timeout:
            if self._should_exit():
                return False
            
            self.task.next_frame()
            
            # 检测新英雄标志
            new_hero_found = False
            try:
                new_hero = self.task.find_one(Features.TUTORIAL_NEW_HERO, threshold=0.6)
                if new_hero:
                    new_hero_found = True
                    self._log_verbose(f"[模板匹配] 检测到新英雄标志: ({new_hero.x}, {new_hero.y})")
            except (ValueError, Exception):
                pass
            
            if not new_hero_found:
                # OCR备选
                if self._detect_text_bilingual("新英雄", "新英雄"):
                    new_hero_found = True
                    self._log_verbose("[OCR] 检测到新英雄文字")
            
            if not new_hero_found:
                time.sleep(0.2)
                continue
            
            # 检测确定按钮
            confirm_pos = None
            try:
                confirm_btn = self.task.find_one(Features.TUTORIAL_CONFIRM_BUTTON, threshold=0.6)
                if confirm_btn:
                    confirm_pos = (confirm_btn.x + confirm_btn.width // 2, 
                                   confirm_btn.y + confirm_btn.height // 2)
                    self._log_verbose(f"[模板匹配] 检测到确定按钮: {confirm_pos}")
            except (ValueError, Exception):
                pass
            
            if not confirm_pos:
                # OCR备选
                confirm_pos = self._detect_text_bilingual("确定", "確定")
                if confirm_pos:
                    self._log_verbose(f"[OCR] 检测到确定文字: {confirm_pos}")
            
            # 两个元素都检测到
            if new_hero_found and confirm_pos:
                self._log(f"检测到新英雄场景，点击确定按钮: {confirm_pos}")
                self.task.click(confirm_pos[0], confirm_pos[1], after_sleep=1.5)
                self._log("新英雄场景处理完成")
                return True
            
            time.sleep(0.2)
        
        self._log_error("新英雄场景检测超时")
        self._save_error_screenshot("new_hero_timeout")
        return False
    
    # ==================== 步骤 2.8: 最终加载界面 ====================
    
    def _wait_final_loading(self) -> bool:
        """
        等待最终加载界面
        
        容错机制：如果在等待过程中检测到主界面元素（漫斗赛/排位赛），
        则跳过加载等待，直接返回成功
        
        Returns:
            bool: 是否成功
        """
        final_loading_timeout = self._cfg('最终加载超时(秒)', 120.0)
        buffer_time = self._cfg('主界面检测容错(秒)', 10.0)
        
        self._log("等待最终加载界面...")
        self.detector.reset_loading_state()
        
        # 短暂等待，让加载界面出现
        time.sleep(2.0)
        
        # 检测加载开始（带主界面并行检测）
        start_time = time.time()
        loading_started = False
        
        while time.time() - start_time < 15.0:
            if self._should_exit():
                return False
            
            self.task.next_frame()
            
            # 容错：检测主界面元素
            if self._quick_check_main_interface():
                self._log("[容错] 检测到主界面元素，跳过最终加载界面等待")
                return True
            
            # 检测加载开始
            if self.detector.detect_loading_start(timeout=1.0):
                loading_started = True
                break
            
            time.sleep(0.2)
        
        
        if loading_started:
            self._log("最终加载界面开始...")
            
            # 等待加载结束（带主界面并行检测）
            loading_end_start = time.time()
            while time.time() - loading_end_start < final_loading_timeout:
                if self._should_exit():
                    return False
                
                self.task.next_frame()
                
                # 容错：检测主界面元素
                if self._quick_check_main_interface():
                    self._log("[容错] 检测到主界面元素，跳过剩余加载等待")
                    return True
                
                # 检测加载结束
                if self.detector.detect_loading_end(timeout=5.0, stuck_timeout=60.0):
                    self._log("最终加载界面结束")
                    break
                
                time.sleep(0.3)
            else:
                # 超时，最后检查一次主界面
                self.task.next_frame()
                if self._quick_check_main_interface():
                    self._log("[容错] 超时后检测到主界面元素，继续流程")
                    return True
                
                self._log_error("最终加载界面超时")
                self._save_error_screenshot("final_loading_timeout")
                return False
        else:
            self._log("未检测到最终加载界面，可能已加载完成")
        
        # 缓冲等待
        self._log(f"加载后缓冲等待 {buffer_time}秒...")
        time.sleep(buffer_time)
        
        return True
    
    def _quick_check_main_interface(self) -> bool:
        """
        快速检测主界面元素（漫斗赛/排位赛）
        
        Returns:
            bool: 是否检测到主界面
        """
        try:
            texts = self.task.ocr()
            if not texts:
                return False
            
            # 检测"漫斗赛"或"排位赛"（简繁双语）
            mandou_pattern = re.compile(r"漫斗赛|漫鬥賽")
            paiwei_pattern = re.compile(r"排位赛|排位賽")
            
            mandou_matched = self.task.find_boxes(texts, match=mandou_pattern)
            paiwei_matched = self.task.find_boxes(texts, match=paiwei_pattern)
            
            if mandou_matched or paiwei_matched:
                matched_texts = []
                if mandou_matched:
                    matched_texts.append(f"漫斗赛:{mandou_matched[0].name}")
                if paiwei_matched:
                    matched_texts.append(f"排位赛:{paiwei_matched[0].name}")
                self._log(f"[主界面检测] 检测到: {', '.join(matched_texts)}")
                return True
        except Exception as e:
            pass
        
        return False
    
    # ==================== 步骤 2.9: 主界面验证 ====================
    
    def _verify_main_interface(self) -> bool:
        """
        验证主界面
        
        OCR检测"漫斗赛" + "排位赛"，两个都检测到才算成功
        
        Returns:
            bool: 是否验证成功
        """
        main_timeout = self._cfg('主界面检测超时(秒)', 30.0)
        max_retry = self._cfg('主界面检测重试次数', 3)
        
        self._log(f"开始主界面验证（超时: {main_timeout}秒，最大重试: {max_retry}次）...")
        
        for retry in range(max_retry):
            self._log(f"主界面验证尝试 {retry + 1}/{max_retry}")
            
            start_time = time.time()
            check_count = 0
            while time.time() - start_time < main_timeout:
                if self._should_exit():
                    return False
                
                self.task.next_frame()
                check_count += 1
                
                # OCR检测
                texts = self.task.ocr()
                if not texts:
                    time.sleep(0.3)
                    continue
                
                # 每5次检测输出一次OCR识别结果（调试用）
                if check_count % 5 == 1:
                    text_names = [t.name for t in texts]
                    self._log(f"[OCR识别结果] {text_names}")
                
                # 检测"漫斗赛"（简繁双语）
                mandou_found = False
                mandou_pattern = re.compile(r"漫斗赛|漫鬥賽")
                mandou_matched = self.task.find_boxes(texts, match=mandou_pattern)
                if mandou_matched:
                    mandou_found = True
                    self._log(f"检测到'漫斗赛': {mandou_matched[0].name}")
                
                # 检测"排位赛"（简繁双语）
                paiwei_found = False
                paiwei_pattern = re.compile(r"排位赛|排位賽")
                paiwei_matched = self.task.find_boxes(texts, match=paiwei_pattern)
                if paiwei_matched:
                    paiwei_found = True
                    self._log(f"检测到'排位赛': {paiwei_matched[0].name}")
                
                # 两个都检测到
                if mandou_found and paiwei_found:
                    self._log("主界面验证成功：检测到'漫斗赛'和'排位赛'")
                    return True
                
                time.sleep(0.3)
            
            self._log(f"主界面验证尝试 {retry + 1} 超时，共检测 {check_count} 次")
            
            if retry < max_retry - 1:
                self._log("等待2秒后重试...")
                time.sleep(2.0)
        
        self._log_error("主界面验证失败：所有重试都已用完")
        self._save_error_screenshot("main_interface_verify_failed")
        return False
    
    # ==================== 辅助方法 ====================
    
    def _should_exit(self) -> bool:
        """检查是否应该退出"""
        if hasattr(self.task, '_should_exit') and self.task._should_exit():
            return True
        if hasattr(self.task, 'exit_is_set') and self.task.exit_is_set():
            return True
        return False
    
    def _extract_keywords(self, text: str) -> list:
        """
        从文字中提取关键词（用于分字容错匹配）
        
        取文字的后4个字符，分为两组关键词（每组2个字）
        例如："点击荧幕退出" -> ["荧幕", "退出"]
              "點擊熒幕繼續" -> ["熒幕", "繼續"]
        
        Args:
            text: 原始文字
            
        Returns:
            关键词列表
        """
        if len(text) < 4:
            return [text]
        # 取后4个字符，分为两组
        last4 = text[-4:]
        return [last4[:2], last4[2:]]
    
    def _detect_text_bilingual(self, simplified: str, traditional: str) -> Optional[Tuple[int, int]]:
        """
        检测文字（简繁双语）
        
        检测方式：
        1. 正则全文匹配（优先）
        2. 分字容错匹配（后备）- 检查关键词是否都出现在OCR结果中
        
        Args:
            simplified: 简体中文文字
            traditional: 繁体中文文字
            
        Returns:
            检测到的位置 (x, y)，未检测到返回 None
        """
        try:
            texts = self.task.ocr()
            if not texts:
                return None
            
            # 方法1: 正则全文匹配
            pattern = re.compile(f"{re.escape(simplified)}|{re.escape(traditional)}")
            matched = self.task.find_boxes(texts, match=pattern)
            
            if matched:
                t = matched[0]
                return (t.x + t.width // 2, t.y + t.height // 2)
            
            # 方法2: 分字容错匹配
            # 将所有 OCR 文字拼接成一个字符串
            all_text = ''.join([t.name for t in texts])
            
            # 提取关键词对（简体+繁体）进行检查
            simplified_keywords = self._extract_keywords(simplified)
            traditional_keywords = self._extract_keywords(traditional)
            
            # 简体关键词全部命中 或 繁体关键词全部命中
            simplified_match = all(kw in all_text for kw in simplified_keywords)
            traditional_match = all(kw in all_text for kw in traditional_keywords)
            
            if simplified_match or traditional_match:
                # 返回屏幕中心坐标（因为分字匹配无法确定精确位置）
                frame = self.task.frame
                if frame is not None:
                    h, w = frame.shape[:2]
                    center = (w // 2, h // 2)
                    matched_kws = simplified_keywords if simplified_match else traditional_keywords
                    self._log(f"[OCR分字匹配] 检测到关键词{matched_kws}, 返回屏幕中心: {center}")
                    return center
        except Exception as e:
            self._log(f"[OCR] 检测异常: {e}")
        
        return None
    
    def _save_error_screenshot(self, error_name: str):
        """保存错误截图"""
        import os
        import cv2
        import numpy as np
        
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', error_name)
        filename = f"{safe_name}_{time.strftime('%H-%M-%S')}.png"
        
        screenshots_dir = "screenshots"
        if not os.path.exists(screenshots_dir):
            os.makedirs(screenshots_dir)
        
        filepath = os.path.join(screenshots_dir, filename)
        
        frame = self.task.frame
        if frame is not None and isinstance(frame, np.ndarray):
            cv2.imwrite(filepath, frame)
            self._log(f"错误截图已保存: {filepath}")
        else:
            self._log_error("无法保存截图: frame 为空")
    
    def cleanup(self):
        """清理资源"""
        self._stop_end_detection()
        self._stop_combat()
        self.detector.reset_loading_state()
        self._log("第二阶段资源清理完成")
