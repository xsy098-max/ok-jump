"""
YOLO 模型标签定义

用于战场单位识别的标签映射
"""


class CombatLabel:
    """
    战斗检测标签
    
    对应 YOLO 模型 (assets/Fight/fight.onnx) 的输出类别
    """
    
    # 自身检测
    SELF = 0        # 自己
    
    # 友方检测
    ALLY = 1        # 友方
    
    # 敌方检测
    ENEMY = 2       # 敌军
    
    # 状态检测
    DEATH = 3       # 死亡状态
    
    # 目标检测
    TARGET_CIRCLE = 4  # 目标圈
    
    # 标签名称映射
    LABEL_NAMES = {
        SELF: '自己',
        ALLY: '友方',
        ENEMY: '敌军',
        DEATH: '死亡状态',
        TARGET_CIRCLE: '目标圈',
    }
    
    @classmethod
    def get_name(cls, label_id):
        """
        获取标签名称
        
        Args:
            label_id: 标签 ID
            
        Returns:
            str: 标签名称
        """
        return cls.LABEL_NAMES.get(label_id, f'未知({label_id})')
