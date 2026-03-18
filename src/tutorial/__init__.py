"""
新手教程模块

提供自动新手教程功能，包括：
- 状态机管理
- 角色选择器
- 检测器封装
- 各阶段处理器
"""

from src.tutorial.state_machine import TutorialState, TutorialStateMachine
from src.tutorial.character_selector import CharacterSelector, CharacterConfig
from src.tutorial.tutorial_detector import TutorialDetector
from src.tutorial.phase1_handler import Phase1Handler

__all__ = [
    'TutorialState',
    'TutorialStateMachine',
    'CharacterSelector',
    'CharacterConfig',
    'TutorialDetector',
    'Phase1Handler',
]
