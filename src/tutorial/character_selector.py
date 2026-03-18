"""
角色选择器

管理新手教程中的角色选择配置和点击区域计算
"""

from enum import Enum
from dataclasses import dataclass
from typing import Tuple, Optional


class CharacterType(Enum):
    """
    角色类型枚举
    """
    WUKONG = '悟空'      # 悟空 - 左侧区域，检测猴子
    LUFFY = '路飞'       # 路飞 - 中间区域，检测目标圈
    NARUTO = '小鸣人'    # 小鸣人 - 右侧区域，检测目标圈
    ALL = '全部'         # 全部 - 依次执行所有角色


@dataclass
class CharacterConfig:
    """
    角色配置数据类
    
    Attributes:
        name: 角色名称
        click_region: 点击区域（横向比例，如 (0, 1/3) 表示左侧1/3）
        target_type: 目标检测类型（'monkey' 或 'target_circle'）
        yolo_model: YOLO模型名称
        yolo_label: YOLO标签ID
    """
    name: str
    click_region: Tuple[float, float]  # (start_x_ratio, end_x_ratio)
    target_type: str
    yolo_model: str
    yolo_label: int
    
    def get_click_position(self, width: int, height: int) -> Tuple[int, int]:
        """
        计算点击位置（区域中心）
        
        Args:
            width: 屏幕宽度
            height: 屏幕高度
            
        Returns:
            Tuple[int, int]: 点击位置 (x, y)
        """
        start_x = int(width * self.click_region[0])
        end_x = int(width * self.click_region[1])
        center_x = (start_x + end_x) // 2
        center_y = height // 2
        return (center_x, center_y)
    
    def get_relative_click_position(self) -> Tuple[float, float]:
        """
        获取相对点击位置（0-1范围）
        
        Returns:
            Tuple[float, float]: 相对位置 (x_ratio, y_ratio)
        """
        center_x = (self.click_region[0] + self.click_region[1]) / 2
        center_y = 0.5
        return (center_x, center_y)


class CharacterSelector:
    """
    角色选择器
    
    管理角色配置和选择逻辑
    """
    
    # 角色配置映射
    CONFIGS = {
        CharacterType.WUKONG: CharacterConfig(
            name='悟空',
            click_region=(0.0, 1/3),      # 左侧1/3
            target_type='monkey',
            yolo_model='fight2.onnx',
            yolo_label=0
        ),
        CharacterType.LUFFY: CharacterConfig(
            name='路飞',
            click_region=(1/3, 2/3),      # 中间1/3
            target_type='target_circle',
            yolo_model='fight.onnx',
            yolo_label=4
        ),
        CharacterType.NARUTO: CharacterConfig(
            name='小鸣人',
            click_region=(2/3, 1.0),      # 右侧1/3
            target_type='target_circle',
            yolo_model='fight.onnx',
            yolo_label=4
        ),
    }
    
    # "全部"选项的执行顺序
    ALL_ORDER = [CharacterType.WUKONG, CharacterType.NARUTO, CharacterType.LUFFY]
    
    def __init__(self, character: str = '路飞'):
        """
        初始化角色选择器
        
        Args:
            character: 角色名称（'悟空', '路飞', '小鸣人', '全部'）
        """
        self._character_type = self._parse_character_type(character)
        self._current_index = 0  # 用于"全部"模式的当前执行索引
    
    def _parse_character_type(self, character: str) -> CharacterType:
        """
        解析角色类型
        
        Args:
            character: 角色名称
            
        Returns:
            CharacterType: 角色类型枚举
        """
        mapping = {
            '悟空': CharacterType.WUKONG,
            '路飞': CharacterType.LUFFY,
            '小鸣人': CharacterType.NARUTO,
            '全部': CharacterType.ALL,
        }
        return mapping.get(character, CharacterType.LUFFY)
    
    @property
    def character_type(self) -> CharacterType:
        """获取当前角色类型"""
        return self._character_type
    
    @property
    def is_all_mode(self) -> bool:
        """是否为"全部"模式"""
        return self._character_type == CharacterType.ALL
    
    def get_current_config(self) -> Optional[CharacterConfig]:
        """
        获取当前角色配置
        
        对于"全部"模式，返回当前正在执行的角色配置
        
        Returns:
            CharacterConfig: 角色配置，如果"全部"模式已完成则返回 None
        """
        if self.is_all_mode:
            if self._current_index >= len(self.ALL_ORDER):
                return None
            current_type = self.ALL_ORDER[self._current_index]
            return self.CONFIGS[current_type]
        else:
            return self.CONFIGS.get(self._character_type)
    
    def get_current_character_name(self) -> str:
        """
        获取当前角色名称
        
        Returns:
            str: 角色名称
        """
        config = self.get_current_config()
        return config.name if config else '未知'
    
    def move_to_next_character(self) -> bool:
        """
        移动到下一个角色（仅用于"全部"模式）
        
        Returns:
            bool: 是否成功移动到下一个角色，如果已全部完成返回 False
        """
        if not self.is_all_mode:
            return False
        
        self._current_index += 1
        return self._current_index < len(self.ALL_ORDER)
    
    def has_more_characters(self) -> bool:
        """
        是否还有更多角色需要执行（仅用于"全部"模式）
        
        Returns:
            bool: 是否还有更多角色
        """
        if not self.is_all_mode:
            return False
        
        return self._current_index < len(self.ALL_ORDER)
    
    def reset(self):
        """重置选择器状态"""
        self._current_index = 0
    
    def get_all_configs(self) -> list:
        """
        获取所有角色配置（按执行顺序）
        
        Returns:
            list: CharacterConfig 列表
        """
        return [self.CONFIGS[t] for t in self.ALL_ORDER]
    
    @classmethod
    def get_available_characters(cls) -> list:
        """
        获取所有可选角色列表
        
        Returns:
            list: 角色名称列表
        """
        return ['悟空', '路飞', '小鸣人', '全部']
    
    @classmethod
    def get_config_by_name(cls, name: str) -> Optional[CharacterConfig]:
        """
        根据名称获取角色配置
        
        Args:
            name: 角色名称
            
        Returns:
            CharacterConfig: 角色配置，未找到返回 None
        """
        for char_type, config in cls.CONFIGS.items():
            if config.name == name:
                return config
        return None
