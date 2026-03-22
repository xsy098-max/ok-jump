"""
新手教程状态机

定义新手教程的所有状态和状态转换逻辑
"""

from enum import Enum


class TutorialState(Enum):
    """
    新手教程状态枚举
    
    状态流程：
    IDLE → CHECK_CHARACTER_SELECT → FIRST_CLICK → CONFIRM_DIALOG → SECOND_CLICK 
    → LOADING → SELF_DETECTION → TARGET_DETECTION → MOVE_TO_TARGET 
    → NORMAL_ATTACK_DETECTION → MOVE_DOWN → COMBAT_TRIGGER 
    → PHASE1_END → [预留] → COMPLETED
    
    注意：COMBAT_TRIGGER 阶段同时运行自动战斗和第一阶段结束检测，
    检测到 end01.png 和 end02.png 后直接进入 PHASE1_END。
    """
    
    # 初始状态
    IDLE = 'idle'
    
    # 第一阶段：选角流程
    CHECK_CHARACTER_SELECT = 'check_character_select'  # 检查选角界面
    FIRST_CLICK = 'first_click'                        # 第一次点击角色区域
    CONFIRM_DIALOG = 'confirm_dialog'                  # 处理确认对话框
    SECOND_CLICK = 'second_click'                      # 第二次点击角色区域
    
    # 第二阶段：加载与自身检测
    LOADING = 'loading'                                # 等待加载完成
    SELF_DETECTION = 'self_detection'                  # 自身检测(30秒超时)
    
    # 第三阶段：目标检测与移动
    TARGET_DETECTION = 'target_detection'              # 目标圈/猴子检测
    MOVE_TO_TARGET = 'move_to_target'                  # 移动靠近目标
    NORMAL_ATTACK_DETECTION = 'normal_attack_detection'  # 普攻按钮检测
    
    # 第四阶段：战斗触发
    MOVE_DOWN = 'move_down'                            # 向下移动1.5秒
    COMBAT_TRIGGER = 'combat_trigger'                  # 启动自动战斗
    PHASE1_END_DETECTION = 'phase1_end_detection'      # 第一阶段结束检测(2分钟)
    
    # 预留阶段
    PHASE1_END = 'phase1_end'                          # 第一阶段结束
    PHASE2_3V3 = 'phase2_3v3'                          # 第二阶段3V3(预留)
    PHASE3_FINISH = 'phase3_finish'                    # 收尾阶段(预留)
    
    # 终态
    COMPLETED = 'completed'                            # 全部完成
    FAILED = 'failed'                                  # 任务失败


class TutorialStateMachine:
    """
    新手教程状态机
    
    管理状态转换和状态历史
    """
    
    # 状态转换映射
    TRANSITIONS = {
        TutorialState.IDLE: [TutorialState.CHECK_CHARACTER_SELECT, TutorialState.FAILED],
        TutorialState.CHECK_CHARACTER_SELECT: [TutorialState.FIRST_CLICK, TutorialState.FAILED],
        TutorialState.FIRST_CLICK: [TutorialState.CONFIRM_DIALOG, TutorialState.FAILED],
        TutorialState.CONFIRM_DIALOG: [TutorialState.SECOND_CLICK, TutorialState.FAILED],
        TutorialState.SECOND_CLICK: [TutorialState.LOADING, TutorialState.FAILED],
        TutorialState.LOADING: [TutorialState.SELF_DETECTION, TutorialState.FAILED],
        TutorialState.SELF_DETECTION: [TutorialState.TARGET_DETECTION, TutorialState.FAILED],
        TutorialState.TARGET_DETECTION: [TutorialState.MOVE_TO_TARGET, TutorialState.FAILED],
        TutorialState.MOVE_TO_TARGET: [TutorialState.NORMAL_ATTACK_DETECTION, TutorialState.FAILED],
        TutorialState.NORMAL_ATTACK_DETECTION: [TutorialState.MOVE_DOWN, TutorialState.FAILED],
        TutorialState.MOVE_DOWN: [TutorialState.COMBAT_TRIGGER, TutorialState.FAILED],
        TutorialState.COMBAT_TRIGGER: [TutorialState.PHASE1_END, TutorialState.FAILED],
        TutorialState.PHASE1_END: [TutorialState.PHASE2_3V3, TutorialState.COMPLETED],
        TutorialState.PHASE2_3V3: [TutorialState.PHASE3_FINISH, TutorialState.FAILED],
        TutorialState.PHASE3_FINISH: [TutorialState.COMPLETED, TutorialState.FAILED],
    }
    
    def __init__(self):
        """初始化状态机"""
        self._current_state = TutorialState.IDLE
        self._history = [TutorialState.IDLE]
        self._failure_reason = None
    
    @property
    def current_state(self) -> TutorialState:
        """获取当前状态"""
        return self._current_state
    
    @property
    def failure_reason(self) -> str:
        """获取失败原因"""
        return self._failure_reason
    
    @property
    def history(self) -> list:
        """获取状态历史"""
        return self._history.copy()
    
    def can_transition_to(self, next_state: TutorialState) -> bool:
        """
        检查是否可以转换到目标状态
        
        Args:
            next_state: 目标状态
            
        Returns:
            bool: 是否可以转换
        """
        allowed = self.TRANSITIONS.get(self._current_state, [])
        return next_state in allowed
    
    def transition_to(self, next_state: TutorialState, reason: str = None) -> bool:
        """
        转换到目标状态
        
        Args:
            next_state: 目标状态
            reason: 转换原因（失败时记录原因）
            
        Returns:
            bool: 是否转换成功
        """
        if not self.can_transition_to(next_state):
            return False
        
        self._current_state = next_state
        self._history.append(next_state)
        
        if next_state == TutorialState.FAILED and reason:
            self._failure_reason = reason
        
        return True
    
    def fail(self, reason: str):
        """
        标记任务失败
        
        Args:
            reason: 失败原因
        """
        self.transition_to(TutorialState.FAILED, reason)
    
    def reset(self):
        """重置状态机"""
        self._current_state = TutorialState.IDLE
        self._history = [TutorialState.IDLE]
        self._failure_reason = None
    
    def is_terminal(self) -> bool:
        """
        检查是否处于终态
        
        Returns:
            bool: 是否处于终态
        """
        return self._current_state in [
            TutorialState.COMPLETED,
            TutorialState.FAILED
        ]
    
    def is_failed(self) -> bool:
        """
        检查是否失败
        
        Returns:
            bool: 是否失败
        """
        return self._current_state == TutorialState.FAILED
    
    def is_completed(self) -> bool:
        """
        检查是否完成
        
        Returns:
            bool: 是否完成
        """
        return self._current_state == TutorialState.COMPLETED
    
    def get_state_name(self) -> str:
        """
        获取当前状态名称（中文）
        
        Returns:
            str: 状态名称
        """
        names = {
            TutorialState.IDLE: '空闲',
            TutorialState.CHECK_CHARACTER_SELECT: '检查选角界面',
            TutorialState.FIRST_CLICK: '第一次点击角色',
            TutorialState.CONFIRM_DIALOG: '检测并点击返回按钮',
            TutorialState.SECOND_CLICK: '第二次点击角色并确认',
            TutorialState.LOADING: '等待加载',
            TutorialState.SELF_DETECTION: '自身检测',
            TutorialState.TARGET_DETECTION: '目标检测',
            TutorialState.MOVE_TO_TARGET: '移动靠近目标',
            TutorialState.NORMAL_ATTACK_DETECTION: '普攻按钮检测',
            TutorialState.MOVE_DOWN: '向下移动',
            TutorialState.COMBAT_TRIGGER: '启动自动战斗',
            TutorialState.PHASE1_END_DETECTION: '第一阶段结束检测',
            TutorialState.PHASE1_END: '第一阶段结束',
            TutorialState.PHASE2_3V3: '第二阶段3V3',
            TutorialState.PHASE3_FINISH: '收尾阶段',
            TutorialState.COMPLETED: '完成',
            TutorialState.FAILED: '失败',
        }
        return names.get(self._current_state, self._current_state.value)
