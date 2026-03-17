"""
距离计算器

用于计算战场单位之间的距离和判断移动方向

特性：
- 带缓冲区的边界检测，避免在边界值附近频繁切换状态
- 滞后效应：进入范围和离开范围使用不同的阈值
"""

import math


class DistanceCalculator:
    """
    距离计算器
    
    用于：
    - 计算两单位间距离
    - 判断是否在最佳攻击范围内
    - 获取移动方向建议
    
    缓冲区机制：
    - 使用滞后效应避免边界值附近频繁切换
    - 进入范围阈值：MIN_DISTANCE ~ MAX_DISTANCE
    - 离开范围阈值：MIN_DISTANCE - BUFFER ~ MAX_DISTANCE + BUFFER
    """
    
    # 最佳攻击距离范围（像素）
    MIN_DISTANCE = 0  # 最小距离
    MAX_DISTANCE = 200  # 最大距离
    
    # 边界缓冲区（像素）- 避免在边界值附近频繁切换
    BUFFER = 15
    
    def __init__(self, min_distance=0, max_distance=200, buffer=15):
        """
        初始化距离计算器
        
        Args:
            min_distance: 最小距离（像素）
            max_distance: 最大距离（像素）
            buffer: 边界缓冲区大小（像素）
        """
        self.min_distance = min_distance
        self.max_distance = max_distance
        self.buffer = buffer
        
        # 当前状态（用于滞后效应）
        self._in_optimal_range = None
    
    @staticmethod
    def calculate(unit1, unit2):
        """
        计算两单位间的距离
        
        Args:
            unit1: 第一个单位（需有 center_x, center_y 属性）
            unit2: 第二个单位（需有 center_x, center_y 属性）
            
        Returns:
            float: 两单位间的距离（像素）
        """
        dx = unit1.center_x - unit2.center_x
        dy = unit1.center_y - unit2.center_y
        return math.sqrt(dx * dx + dy * dy)
    
    @staticmethod
    def calculate_from_coords(x1, y1, x2, y2):
        """
        根据坐标计算距离
        
        Args:
            x1, y1: 第一个点坐标
            x2, y2: 第二个点坐标
            
        Returns:
            float: 两点间的距离
        """
        dx = x1 - x2
        dy = y1 - y2
        return math.sqrt(dx * dx + dy * dy)
    
    def is_in_optimal_range(self, distance):
        """
        判断是否在最佳攻击范围内（带滞后效应）
        
        使用缓冲区机制避免在边界值附近频繁切换：
        - 如果当前在范围内，需要距离超出 (MIN - BUFFER, MAX + BUFFER) 才判定为离开
        - 如果当前在范围外，需要距离进入 (MIN, MAX) 才判定为进入
        
        Args:
            distance: 距离（像素）
            
        Returns:
            bool: True 如果在最佳范围内
        """
        # 内部边界（进入范围）
        inner_min = self.min_distance
        inner_max = self.max_distance
        
        # 外部边界（离开范围）
        outer_min = self.min_distance - self.buffer
        outer_max = self.max_distance + self.buffer
        
        if self._in_optimal_range is None:
            # 首次判断，使用内部边界
            self._in_optimal_range = inner_min <= distance <= inner_max
        elif self._in_optimal_range:
            # 当前在范围内，使用外部边界判断是否离开
            if distance < outer_min or distance > outer_max:
                self._in_optimal_range = False
        else:
            # 当前在范围外，使用内部边界判断是否进入
            if inner_min <= distance <= inner_max:
                self._in_optimal_range = True
        
        return self._in_optimal_range
    
    def get_movement_direction(self, self_pos, target_pos, distance=None):
        """
        获取移动方向建议（带滞后效应）
        
        根据距离判断应该：
        - 靠近目标 ("towards")
        - 远离目标 ("away")
        - 停止移动 ("stop")
        
        Args:
            self_pos: 自身位置
            target_pos: 目标位置
            distance: 距离（可选，如果提供则不重新计算）
            
        Returns:
            str: 移动方向 ("towards", "away", "stop")
        """
        if distance is None:
            distance = self.calculate(self_pos, target_pos)
        
        # 使用带缓冲区的判断
        if self.is_in_optimal_range(distance):
            return "stop"  # 距离合适，停止移动
        
        # 根据当前状态决定方向
        if self._in_optimal_range is False:
            # 明确在范围外，判断方向
            if distance < self.min_distance - self.buffer:
                return "away"  # 太近，需要远离
            elif distance > self.max_distance + self.buffer:
                return "towards"  # 太远，需要靠近
        
        # 默认判断（无状态时）
        if distance < self.min_distance:
            return "away"
        elif distance > self.max_distance:
            return "towards"
        else:
            return "stop"
    
    def reset_state(self):
        """重置内部状态（用于切换目标时）"""
        self._in_optimal_range = None
    
    def get_movement_vector(self, self_pos, target_pos):
        """
        获取从自身到目标的单位向量
        
        Args:
            self_pos: 自身位置
            target_pos: 目标位置
            
        Returns:
            tuple: (dx, dy) 单位向量
        """
        dx = target_pos.center_x - self_pos.center_x
        dy = target_pos.center_y - self_pos.center_y
        
        length = math.sqrt(dx * dx + dy * dy)
        if length < 0.001:  # 避免除零
            return (0, 0)
        
        return (dx / length, dy / length)
    
    def get_reverse_vector(self, self_pos, target_pos):
        """
        获取从目标到自身的单位向量（远离方向）
        
        Args:
            self_pos: 自身位置
            target_pos: 目标位置
            
        Returns:
            tuple: (dx, dy) 单位向量
        """
        dx, dy = self.get_movement_vector(self_pos, target_pos)
        return (-dx, -dy)
