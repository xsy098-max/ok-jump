"""
自动新手教程任务

使用YOLO模型实现完整的新手引导流程，包含：
- 状态机管理
- 多角色选择配置
- YOLO模型集成
- 自动战斗触发

流程：
新手教程开始 → 选角界面检测 → 第一次点击角色 → 确认对话框处理 → 第二次点击角色 
→ 加载界面 → 自身检测 → 目标检测 → 移动靠近 → 普攻检测 → 向下移动 → 自动战斗触发 
→ 第一阶段结束检测 → [预留:第二阶段] → [预留:收尾阶段] → 完成
"""

import time

from ok import og

from src.task.BaseJumpTask import BaseJumpTask
from src.tutorial.state_machine import TutorialState
from src.tutorial.character_selector import CharacterSelector, CharacterType
from src.tutorial.phase1_handler import Phase1Handler
from src.tutorial.phase2_handler import Phase2Handler
from src.utils import background_manager


class AutoTutorialTask(BaseJumpTask):
    """
    自动新手教程任务
    
    实现完整的新手引导流程，支持多角色选择
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "AutoTutorialTask"
        self.description = "自动新手教程 - 自动完成游戏新手教程"
        
        # 默认配置
        self.default_config = {
            '角色选择': '路飞',  # 悟空、路飞、小鸣人、全部
            '选角界面检测超时(秒)': 10.0,
            '自身检测超时(秒)': 30.0,
            '目标检测超时(秒)': 10.0,
            '普攻检测超时(秒)': 10.0,
            '第一阶段结束检测超时(秒)': 120.0,
            '加载后等待时间(秒)': 30.0,
            '向下移动时间(秒)': 1.0,
            '移动持续时间(秒)': 0.5,
            '点击后等待时间(秒)': 1.0,
            '详细日志': True,
        }
        
        # 配置类型定义（下拉框等）
        # 注意：double类型会由框架自动使用LabelAndDoubleSpinBox，无需显式定义
        self.config_type = {
            '角色选择': {'type': 'drop_down', 'options': ['悟空', '路飞', '小鸣人', '全部']},
            '选角界面检测超时(秒)': {'type': 'double_spin', 'min': 1.0, 'max': 300.0, 'decimals': 1},
            '自身检测超时(秒)': {'type': 'double_spin', 'min': 1.0, 'max': 300.0, 'decimals': 1},
            '目标检测超时(秒)': {'type': 'double_spin', 'min': 1.0, 'max': 300.0, 'decimals': 1},
            '普攻检测超时(秒)': {'type': 'double_spin', 'min': 1.0, 'max': 300.0, 'decimals': 1},
            '第一阶段结束检测超时(秒)': {'type': 'double_spin', 'min': 1.0, 'max': 600.0, 'decimals': 1},
            '加载后等待时间(秒)': {'type': 'double_spin', 'min': 1.0, 'max': 300.0, 'decimals': 1},
            '向下移动时间(秒)': {'type': 'double_spin', 'min': 0.1, 'max': 10.0, 'decimals': 1},
            '移动持续时间(秒)': {'type': 'double_spin', 'min': 0.1, 'max': 10.0, 'decimals': 1},
            '点击后等待时间(秒)': {'type': 'double_spin', 'min': 0.1, 'max': 10.0, 'decimals': 1},
        }
        
        # 配置描述
        self.config_description = {
            '角色选择': '选择要执行新手教程的角色，"全部"将依次执行所有角色',
            '选角界面检测超时(秒)': '检测选角界面的最长等待时间',
            '自身检测超时(秒)': 'YOLO检测自身的最长等待时间',
            '目标检测超时(秒)': '检测目标圈/猴子的最长等待时间',
            '普攻检测超时(秒)': 'OCR检测普攻按钮的最长等待时间',
            '第一阶段结束检测超时(秒)': '检测第一阶段结束标志的最长等待时间',
            '加载后等待时间(秒)': '加载完成后等待游戏稳定的缓冲时间',
            '向下移动时间(秒)': '检测到普攻按钮后向下移动的时间',
            '移动持续时间(秒)': '每次移动按键的持续时间',
            '点击后等待时间(秒)': '点击操作后的等待时间',
            '详细日志': '启用后输出详细的调试日志',
        }
        
        # 处理器
        self._phase1_handler: Phase1Handler = None
        self._phase2_handler: Phase2Handler = None
        
        # 内部状态
        self._current_character_index = 0
        self._completed_characters = []
    
    def run(self):
        """
        运行自动新手教程任务
        """
        self.logger.info("=" * 50)
        self.logger.info("自动新手教程任务启动")
        self.logger.info("=" * 50)
        
        # 初始化后台模式
        background_manager.update_config()
        self.logger.info(f"后台模式: {'启用' if background_manager.is_background_mode() else '禁用'}")
        
        # 更新分辨率
        self.update_resolution()
        res_info = self.get_resolution_info()
        self.logger.info(f"当前分辨率: {res_info['current'][0]}x{res_info['current'][1]}")
        
        # 获取角色选择
        character = self.config.get('角色选择', '路飞')
        self.logger.info(f"角色选择: {character}")
        
        # 判断是否为"全部"模式
        selector = CharacterSelector(character)
        
        if selector.is_all_mode:
            # 执行所有角色的新手教程
            return self._run_all_characters(selector)
        else:
            # 执行单个角色的新手教程
            return self._run_single_character(character)
    
    def _run_single_character(self, character: str) -> bool:
        """
        执行单个角色的新手教程
        
        Args:
            character: 角色名称
            
        Returns:
            bool: 是否成功完成
        """
        self.logger.info(f"开始执行角色 '{character}' 的新手教程")
        
        # ========== 第一阶段 ==========
        # 创建第一阶段处理器
        self._phase1_handler = Phase1Handler(self)
        self._phase1_handler.initialize(character)
        
        # 运行第一阶段
        phase1_success = self._phase1_handler.run()
        
        if not phase1_success:
            reason = self._phase1_handler.state_machine.failure_reason
            self.logger.error(f"角色 '{character}' 新手教程第一阶段失败: {reason}")
            self._save_error_screenshot(f"{character}_tutorial_failed")
            self._phase1_handler.cleanup()
            return False
        
        self.logger.info(f"角色 '{character}' 新手教程第一阶段完成")
        
        # ========== 第二阶段 ==========
        self.logger.info(f"开始执行角色 '{character}' 的新手教程第二阶段")
        
        # 创建第二阶段处理器（参照 Phase1Handler 的创建方式）
        self._phase2_handler = Phase2Handler(self)
        self._phase2_handler.set_verbose(self.config.get('详细日志', False))
        
        # 运行第二阶段
        phase2_success = self._phase2_handler.run()
        
        if not phase2_success:
            self.logger.error(f"角色 '{character}' 新手教程第二阶段失败")
            self._save_error_screenshot(f"{character}_phase2_failed")
            self._phase2_handler.cleanup()
            self._phase1_handler.cleanup()
            return False
        
        self.logger.info(f"角色 '{character}' 新手教程第二阶段完成")
        
        # ========== 任务结束处理 ==========
        # 更新状态机到 COMPLETED 状态
        self._phase1_handler.state_machine.transition_to(TutorialState.PHASE2_3V3)
        self._phase1_handler.state_machine.transition_to(TutorialState.COMPLETED)
        
        # 标记全局教程完成状态（延迟导入避免循环导入）
        from src import jump_globals
        if jump_globals is not None:
            jump_globals.set_tutorial_completed(True)
            self.logger.info("新手引导全局完成状态已标记")
        else:
            self.logger.info("jump_globals 未初始化，跳过全局状态标记")
        
        # 清理资源
        self._phase2_handler.cleanup()
        self._phase1_handler.cleanup()
        
        # 记录完成日志
        self.logger.info("=" * 50)
        self.logger.info(f"恭喜！角色 '{character}' 新手引导全流程完成！")
        self.logger.info("新手教程任务已成功结束")
        self.logger.info("GUI窗口保持打开，可以继续执行其他任务")
        self.logger.info("=" * 50)
        
        return True
    
    def _run_all_characters(self, selector: CharacterSelector) -> bool:
        """
        执行所有角色的新手教程（依次执行）
        
        执行顺序：悟空 → 小鸣人 → 路飞
        
        Args:
            selector: 角色选择器
            
        Returns:
            bool: 是否全部成功完成
        """
        self.logger.info("开始执行所有角色的新手教程")
        self.logger.info(f"执行顺序: 悟空 → 小鸣人 → 路飞")
        
        all_success = True
        self._completed_characters = []
        
        while selector.has_more_characters():
            config = selector.get_current_config()
            if not config:
                break
            
            character_name = config.name
            self.logger.info(f"\n{'='*50}")
            self.logger.info(f"开始角色: {character_name}")
            self.logger.info(f"{'='*50}")
            
            # 执行单个角色
            success = self._run_single_character(character_name)
            
            if success:
                self._completed_characters.append(character_name)
                self.logger.info(f"角色 '{character_name}' 完成")
            else:
                all_success = False
                self.logger.error(f"角色 '{character_name}' 失败")
                # 继续执行下一个角色
            
            # 移动到下一个角色
            selector.move_to_next_character()
            
            # 角色之间等待一段时间
            if selector.has_more_characters():
                wait_time = 5
                self.logger.info(f"等待 {wait_time} 秒后继续下一个角色...")
                time.sleep(wait_time)
        
        # 汇总结果
        self.logger.info("\n" + "=" * 50)
        self.logger.info("新手教程执行完成")
        self.logger.info(f"完成角色: {', '.join(self._completed_characters)}")
        self.logger.info(f"总体结果: {'成功' if all_success else '部分失败'}")
        self.logger.info("=" * 50)
        
        return all_success
    
    def _save_error_screenshot(self, error_name: str):
        """
        保存错误截图
        
        Args:
            error_name: 错误名称
        """
        import os
        import re
        import cv2
        
        screenshots_dir = "screenshots"
        if not os.path.exists(screenshots_dir):
            os.makedirs(screenshots_dir)
        
        # 将中文等非ASCII字符转换为安全的ASCII字符
        # 使用拼音或替换为英文标识
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', error_name)
        # 移除或替换非ASCII字符，避免编码问题
        safe_name = safe_name.encode('ascii', 'replace').decode('ascii')
        filename = f"{safe_name}_{time.strftime('%H-%M-%S')}.png"
        filepath = os.path.join(screenshots_dir, filename)
        
        if self.frame is not None:
            cv2.imwrite(filepath, self.frame)
            self.logger.error(f"错误截图已保存: {filepath}")
            return filepath
        return None
    
    def get_current_state(self) -> str:
        """
        获取当前状态名称
        
        Returns:
            str: 状态名称
        """
        if self._phase1_handler:
            return self._phase1_handler.state_machine.get_state_name()
        return "未开始"
    
    def get_completed_characters(self) -> list:
        """
        获取已完成的角色列表
        
        Returns:
            list: 已完成的角色名称列表
        """
        return self._completed_characters.copy()
