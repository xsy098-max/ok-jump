"""
技能控制器

控制游戏技能释放（PC端使用键盘，手机端使用点击）

配置来源：
- 技能开关和间隔：从 AutoCombatTask.json 读取
- 按键映射：从 游戏热键配置.json 读取

支持后台模式：
- 使用 SendInput 发送按键，支持 Unity 游戏后台操作
"""

import time
import pydirectinput

from ok import og
from src.utils.BackgroundInputHelper import background_input

# 禁用 pydirectinput 的安全检查
pydirectinput.FAILSAFE = False


class SkillController:
    """
    技能控制器
    
    支持：
    - PC端：键盘按键释放技能（支持后台窗口）
    - 手机端：点击技能按钮位置（预留接口）
    
    配置驱动：
    - 技能启用开关：严格遵循GUI设置
    - 按键映射：从全局配置读取
    """
    
    # 手机端技能按钮相对位置
    MOBILE_SKILL_POSITIONS = {
        'attack': (0.85, 0.75),      # 普通攻击
        'skill1': (0.75, 0.65),      # 技能1
        'skill2': (0.90, 0.55),      # 技能2
        'ultimate': (0.85, 0.45),    # 大招
    }
    
    # 技能名称映射（GUI配置 -> 热键配置）
    SKILL_KEY_MAPPING = {
        '自动普攻': '普通攻击',
        '自动技能1': '技能1',
        '自动技能2': '技能2',
        '自动大招': '大招',
    }
    
    # 默认按键（备用）
    DEFAULT_KEYS = {
        '普通攻击': 'J',
        '技能1': 'K',
        '技能2': 'U',
        '大招': 'L',
    }
    
    def __init__(self, task):
        """
        初始化技能控制器
        
        Args:
            task: 关联的任务对象（用于读取配置和发送按键）
        """
        self.task = task
        
        # 技能冷却计时
        self.last_attack = 0
        self.last_skill1 = 0
        self.last_skill2 = 0
        self.last_ultimate = 0
        
        # 自动技能状态
        self.auto_skill_enabled = False
        self._background_input_initialized = False
    
    def is_adb(self):
        """检测是否为 ADB 模式（手机端）"""
        return hasattr(self.task, 'is_adb') and self.task.is_adb()
    
    def _init_background_input(self):
        """初始化后台输入助手"""
        if self._background_input_initialized:
            return
        
        hwnd = self._get_game_hwnd()
        if hwnd:
            background_input.set_hwnd(hwnd)
            background_input.set_logger(self.task.logger)
            self._background_input_initialized = True
    
    def _get_game_hwnd(self):
        """
        获取游戏窗口句柄
        
        Returns:
            int: 窗口句柄，获取失败返回 None
        """
        try:
            if hasattr(self.task, 'executor') and hasattr(self.task.executor, 'interaction'):
                interaction = self.task.executor.interaction
                if hasattr(interaction, 'hwnd_window') and interaction.hwnd_window:
                    return interaction.hwnd_window.hwnd
            # 备用方式：从 device_manager 获取
            if og and og.device_manager and og.device_manager.hwnd_window:
                return og.device_manager.hwnd_window.hwnd
        except Exception as e:
            self.task.logger.debug(f"[技能] 获取窗口句柄失败: {e}")
        return None
    
    def _send_skill_key(self, key, skill_name):
        """
        发送技能按键

        智能适配：
        - ADB 模式：使用框架的 send_key（通过 ADB 命令）
        - Windows 前台模式：使用 pydirectinput
        - Windows 后台模式：使用 SendInput

        Args:
            key: 按键字符
            skill_name: 技能名称（用于日志）
        """
        try:
            # 使用任务类的 send_key 方法（智能适配 ADB/Windows 模式）
            success = self.task.send_key(key)

            if success:
                mode = "ADB" if self.is_adb() else "Windows"
                self.task.logger.info(f"[技能] 释放{skill_name}: {key} ({mode})")
            else:
                self.task.logger.error(f"[技能] 释放{skill_name}失败")
        except Exception as e:
            self.task.logger.error(f"[技能] 释放{skill_name}失败: {e}")
    
    def start_auto_skills(self):
        """启动自动技能"""
        self.auto_skill_enabled = True
        self.task.logger.info("[技能] 自动技能已启动")
    
    def stop_auto_skills(self):
        """停止自动技能"""
        self.auto_skill_enabled = False
    
    def is_auto_skill_enabled(self):
        """检查自动技能是否启用"""
        return self.auto_skill_enabled
    
    def _get_task_config(self, key, default=None):
        """
        从任务配置读取设置（技能开关和间隔）
        
        Args:
            key: 配置键名
            default: 默认值
            
        Returns:
            配置值
        """
        if hasattr(self.task, 'config') and self.task.config:
            return self.task.config.get(key, default)
        return default
    
    def _get_hotkey_config(self, skill_name, default=None):
        """
        从全局热键配置读取按键映射
        
        Args:
            skill_name: 技能名称（如"普通攻击"、"技能1"）
            default: 默认按键
            
        Returns:
            str: 按键
        """
        try:
            if og and og.config:
                hotkey_config = og.config.get('游戏热键配置', {})
                return hotkey_config.get(skill_name, default or self.DEFAULT_KEYS.get(skill_name, 'J'))
        except Exception:
            pass
        return default or self.DEFAULT_KEYS.get(skill_name, 'J')
    
    def _is_skill_enabled(self, skill_switch_name):
        """
        检查技能是否启用
        
        Args:
            skill_switch_name: 技能开关名称（如"自动普攻"）
            
        Returns:
            bool: True 如果启用
        """
        return self._get_task_config(skill_switch_name, True)
    
    def _get_skill_interval(self, interval_name, default):
        """
        获取技能间隔时间
        
        Args:
            interval_name: 间隔配置名（如"普攻间隔(秒)"）
            default: 默认间隔
            
        Returns:
            float: 间隔时间（秒）
        """
        return self._get_task_config(interval_name, default)
    
    def update(self):
        """
        更新技能释放
        
        在自动技能启用时调用，按照配置间隔释放技能
        严格遵循GUI设置：先检查开关，再检查冷却，最后释放
        """
        if not self.auto_skill_enabled:
            return
        
        current_time = time.time()
        
        # 自动普攻
        if self._is_skill_enabled('自动普攻'):
            interval = self._get_skill_interval('普攻间隔(秒)', 0.5)
            if current_time - self.last_attack >= interval:
                self.do_attack()
                self.last_attack = current_time
        
        # 自动技能1
        if self._is_skill_enabled('自动技能1'):
            interval = self._get_skill_interval('技能1间隔(秒)', 2.0)
            if current_time - self.last_skill1 >= interval:
                self.do_skill1()
                self.last_skill1 = current_time
        
        # 自动技能2
        if self._is_skill_enabled('自动技能2'):
            interval = self._get_skill_interval('技能2间隔(秒)', 3.0)
            if current_time - self.last_skill2 >= interval:
                self.do_skill2()
                self.last_skill2 = current_time
        
        # 自动大招
        if self._is_skill_enabled('自动大招'):
            interval = self._get_skill_interval('大招间隔(秒)', 5.0)
            if current_time - self.last_ultimate >= interval:
                self.do_ultimate()
                self.last_ultimate = current_time
    
    def do_attack(self):
        """释放普通攻击"""
        if self.is_adb():
            self._click_skill_button('attack')
        else:
            key = self._get_hotkey_config('普通攻击', 'J')
            self._send_skill_key(key, '普通攻击')
    
    def do_skill1(self):
        """释放技能1"""
        if self.is_adb():
            self._click_skill_button('skill1')
        else:
            key = self._get_hotkey_config('技能1', 'K')
            self._send_skill_key(key, '技能1')
    
    def do_skill2(self):
        """释放技能2"""
        if self.is_adb():
            self._click_skill_button('skill2')
        else:
            key = self._get_hotkey_config('技能2', 'U')
            self._send_skill_key(key, '技能2')
    
    def do_ultimate(self):
        """释放大招"""
        if self.is_adb():
            self._click_skill_button('ultimate')
        else:
            key = self._get_hotkey_config('大招', 'L')
            self._send_skill_key(key, '大招')
    
    def _click_skill_button(self, skill_type):
        """
        点击技能按钮（手机端）
        
        Args:
            skill_type: 技能类型 ('attack', 'skill1', 'skill2', 'ultimate')
        """
        position = self.MOBILE_SKILL_POSITIONS.get(skill_type)
        if position is None:
            return
        
        frame = self.task.frame
        if frame is None:
            return
        
        height, width = frame.shape[:2]
        x = int(width * position[0])
        y = int(height * position[1])
        
        self.task.click(x, y)
        self.task.logger.debug(f"点击技能按钮 {skill_type}: ({x}, {y})")
    
    def reset_cooldowns(self):
        """重置所有技能冷却计时"""
        self.last_attack = 0
        self.last_skill1 = 0
        self.last_skill2 = 0
        self.last_ultimate = 0
    
    def get_skill_status(self):
        """
        获取技能状态信息
        
        Returns:
            dict: 技能状态字典
        """
        current_time = time.time()
        return {
            '普攻': {
                '启用': self._is_skill_enabled('自动普攻'),
                '按键': self._get_hotkey_config('普通攻击', 'J'),
                '间隔': self._get_skill_interval('普攻间隔(秒)', 0.5),
                '冷却剩余': max(0, self._get_skill_interval('普攻间隔(秒)', 0.5) - (current_time - self.last_attack)),
            },
            '技能1': {
                '启用': self._is_skill_enabled('自动技能1'),
                '按键': self._get_hotkey_config('技能1', 'K'),
                '间隔': self._get_skill_interval('技能1间隔(秒)', 2.0),
                '冷却剩余': max(0, self._get_skill_interval('技能1间隔(秒)', 2.0) - (current_time - self.last_skill1)),
            },
            '技能2': {
                '启用': self._is_skill_enabled('自动技能2'),
                '按键': self._get_hotkey_config('技能2', 'U'),
                '间隔': self._get_skill_interval('技能2间隔(秒)', 3.0),
                '冷却剩余': max(0, self._get_skill_interval('技能2间隔(秒)', 3.0) - (current_time - self.last_skill2)),
            },
            '大招': {
                '启用': self._is_skill_enabled('自动大招'),
                '按键': self._get_hotkey_config('大招', 'L'),
                '间隔': self._get_skill_interval('大招间隔(秒)', 5.0),
                '冷却剩余': max(0, self._get_skill_interval('大招间隔(秒)', 5.0) - (current_time - self.last_ultimate)),
            },
        }

