"""
移动控制器

控制游戏角色移动（PC端使用WASD键盘，手机端使用虚拟摇杆）

特性：
- 支持伪后台模式：游戏窗口在后台时仍可发送按键
- 使用 SendInput 向游戏发送按键（支持 Unity 游戏后台操作）
- 使用 pydirectinput 作为回退方案（前台模式）
"""

import time
import math

import pydirectinput

from ok import og
from src.utils.BackgroundInputHelper import background_input

# 禁用 pydirectinput 的安全检查
pydirectinput.FAILSAFE = False


class MovementController:
    """
    移动控制器
    
    支持：
    - PC端：WASD 键盘控制（支持后台窗口）
    - 手机端：虚拟摇杆滑动控制（预留接口）
    """
    
    # 移动键位（PC端）
    KEY_UP = 'W'
    KEY_DOWN = 'S'
    KEY_LEFT = 'A'
    KEY_RIGHT = 'D'
    
    def __init__(self, task, move_duration=0.5):
        """
        初始化移动控制器
        
        Args:
            task: 关联的任务对象
            move_duration: 每次移动持续的时间（秒），默认0.5秒
        """
        self.task = task
        self.move_duration = move_duration  # 移动持续时间（秒）
        self._current_direction = None
        self._is_moving = False
        self._pressed_keys = set()  # 当前按下的键
        self._background_input_initialized = False
        
        # 手机端虚拟摇杆配置（相对位置）
        self.joystick_center = (0.15, 0.7)  # 摇杆中心相对位置
        self.joystick_radius = 50  # 摇杆半径（像素）
    
    def set_move_duration(self, duration):
        """
        设置移动持续时间
        
        Args:
            duration: 移动持续时间（秒）
        """
        self.move_duration = duration
        self.task.logger.info(f"[移动] 移动持续时间已更新为 {duration}秒")
    
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
            self.task.logger.debug(f"[移动] 获取窗口句柄失败: {e}")
        return None
    
    def move_towards(self, target_x, target_y, self_x=None, self_y=None):
        """
        向目标移动
        
        Args:
            target_x, target_y: 目标坐标
            self_x, self_y: 自身坐标（可选，用于计算方向）
        """
        if self.is_adb():
            self._move_adb_towards(target_x, target_y)
        else:
            self._move_pc_towards(target_x, target_y, self_x, self_y)
    
    def move_away(self, target_x, target_y, self_x=None, self_y=None):
        """
        远离目标
        
        Args:
            target_x, target_y: 目标坐标
            self_x, self_y: 自身坐标（可选）
        """
        if self.is_adb():
            self._move_adb_away(target_x, target_y)
        else:
            self._move_pc_away(target_x, target_y, self_x, self_y)
    
    def move_left_right(self, duration=1):
        """
        左右来回移动
        
        Args:
            duration: 每个方向的移动时间（秒）
        """
        if self.is_adb():
            self._move_adb_left_right(duration)
        else:
            self._move_pc_left_right(duration)
    
    def move_up(self, duration=1):
        """
        向上移动
        
        Args:
            duration: 移动时间（秒）
        """
        if self.is_adb():
            self._move_adb_up(duration)
        else:
            self._move_pc_up(duration)
    
    def stop(self):
        """停止移动"""
        if self.is_adb():
            self._stop_adb()
        else:
            self._stop_pc()
        
        self._is_moving = False
        self._current_direction = None
    
    # ==================== PC端移动（WASD键盘） ====================
    
    def _move_pc_towards(self, target_x, target_y, self_x=None, self_y=None):
        """PC端向目标移动"""
        # 获取自身位置
        if self_x is None or self_y is None:
            frame = self.task.frame
            if frame is not None:
                self_x = frame.shape[1] // 2
                self_y = frame.shape[0] // 2
                self.task.logger.info(f"[移动] 使用屏幕中心作为自身位置: ({self_x}, {self_y})")
            else:
                self.task.logger.warning("[移动] 无法获取帧，跳过移动")
                return
        
        # 计算方向
        dx = target_x - self_x
        dy = target_y - self_y
        
        # 根据方向按键
        keys = self._calculate_keys(dx, dy)
        if keys:
            self.task.logger.info(f"[移动] 向目标移动: 自身({self_x}, {self_y}) -> 目标({target_x}, {target_y}), 偏移=({dx}, {dy}), 按键={'+'.join(keys)}")
            self._press_movement_keys(keys)
            self.task.logger.info(f"[移动] 移动执行完成: 按键 {'+'.join(keys)} 持续 {self.move_duration}秒")
        else:
            self.task.logger.info(f"[移动] 偏移太小，不移动: dx={dx}, dy={dy}")
    
    def _move_pc_away(self, target_x, target_y, self_x=None, self_y=None):
        """PC端远离目标"""
        # 获取自身位置
        if self_x is None or self_y is None:
            frame = self.task.frame
            if frame is not None:
                self_x = frame.shape[1] // 2
                self_y = frame.shape[0] // 2
                self.task.logger.info(f"[移动] 使用屏幕中心作为自身位置: ({self_x}, {self_y})")
            else:
                self.task.logger.warning("[移动] 无法获取帧，跳过移动")
                return
        
        # 计算相反方向
        dx = self_x - target_x
        dy = self_y - target_y
        
        self.task.logger.info(f"[移动] 远离目标: 自身({self_x}, {self_y}) <- 目标({target_x}, {target_y}), 偏移=({dx}, {dy})")
        
        keys = self._calculate_keys(dx, dy)
        if keys:
            self._press_movement_keys(keys)
        else:
            self.task.logger.info("[移动] 偏移太小，不移动")
    
    def _move_pc_left_right(self, duration=1):
        """PC端左右来回移动"""
        self.task.logger.info(f"[移动] 左右移动: 向左 {duration}秒")
        self.task.send_key_down(self.KEY_LEFT)
        time.sleep(duration)
        self.task.send_key_up(self.KEY_LEFT)
        
        self.task.logger.info(f"[移动] 左右移动: 向右 {duration}秒")
        self.task.send_key_down(self.KEY_RIGHT)
        time.sleep(duration)
        self.task.send_key_up(self.KEY_RIGHT)
    
    def _move_pc_up(self, duration=1):
        """PC端向上移动"""
        self.task.logger.info(f"[移动] 向上移动 {duration}秒")
        self.task.send_key_down(self.KEY_UP)
        time.sleep(duration)
        self.task.send_key_up(self.KEY_UP)
    
    def _stop_pc(self):
        """PC端停止移动"""
        self.task.logger.info("[移动] 停止移动，释放所有按键")
        hwnd = self._get_game_hwnd()
        
        # 释放所有移动键
        for key in [self.KEY_UP, self.KEY_DOWN, self.KEY_LEFT, self.KEY_RIGHT]:
            try:
                if hwnd:
                    self._send_key_up_to_window(hwnd, key)
                else:
                    pydirectinput.keyUp(key.lower())
            except:
                pass
        
        self._pressed_keys.clear()
    
    def _calculate_keys(self, dx, dy):
        """
        根据方向计算需要按下的键（支持八方向移动）
        
        坐标系说明：
        - 屏幕坐标系 Y 轴向下为正
        - dx > 0 表示目标在右边，应按 D
        - dx < 0 表示目标在左边，应按 A
        - dy > 0 表示目标在下方，应按 S
        - dy < 0 表示目标在上方，应按 W
        
        Args:
            dx: x方向偏移（正=右，负=左）
            dy: y方向偏移（正=下，负=上）
            
        Returns:
            list: 需要按下的键列表（可包含1-2个键）
        """
        keys = []
        
        # 偏移阈值：小于此值视为不需要移动
        THRESHOLD = 30
        
        # 偏移太小，不移动
        if abs(dx) < THRESHOLD and abs(dy) < THRESHOLD:
            self.task.logger.debug(f"[移动] 偏移太小，不移动: dx={dx}, dy={dy}")
            return keys
        
        # 计算角度（用于日志）
        angle = math.atan2(dy, dx)
        angle_deg = math.degrees(angle)
        
        # 根据偏移量直接判断方向（支持八方向）
        # 水平方向判断
        if abs(dx) >= THRESHOLD:
            if dx > 0:
                keys.append(self.KEY_RIGHT)  # 目标在右边，按 D
            else:
                keys.append(self.KEY_LEFT)   # 目标在左边，按 A
        
        # 垂直方向判断
        if abs(dy) >= THRESHOLD:
            if dy > 0:
                keys.append(self.KEY_DOWN)   # 目标在下方，按 S
            else:
                keys.append(self.KEY_UP)     # 目标在上方，按 W
        
        self.task.logger.info(f"[移动] 方向计算: dx={dx}, dy={dy}, 角度={angle_deg:.1f}°, 按键={'+'.join(keys) if keys else '无'}")
        
        return keys
    
    def _press_movement_keys(self, keys):
        """
        按下移动键并持续一段时间

        智能适配：
        - ADB 模式：使用框架的 swipe（虚拟摇杆）
        - Windows 前台模式：使用 pydirectinput
        - Windows 后台模式：使用 SendInput

        Args:
            keys: 需要按下的键列表
        """
        if not keys:
            return

        # ADB 模式：使用虚拟摇杆
        if self.is_adb():
            self.task.logger.info(f"[移动] ADB模式移动: {'+'.join(keys)}, 持续{self.move_duration}秒")
            self._press_movement_keys_adb(keys, self.move_duration)
            return

        # 只有方向改变时才停止（减少停顿）
        if self._current_direction is not None and self._current_direction != keys:
            self._stop_pc()

        key_str = '+'.join(keys)
        self.task.logger.info(f"[移动] PC模式移动: 按键 {key_str}, 持续 {self.move_duration}秒")

        try:
            # 使用任务类的 send_key_down/up 方法（智能适配后台模式）
            for key in keys:
                self.task.logger.info(f"[移动] 按下按键: {key}")
                self.task.send_key_down(key)

            self.task.logger.info(f"[移动] 等待 {self.move_duration}秒...")
            time.sleep(self.move_duration)

            for key in keys:
                self.task.logger.info(f"[移动] 释放按键: {key}")
                self.task.send_key_up(key)

            self._current_direction = keys
            self._is_moving = True
            self.task.logger.info(f"[移动] 移动完成: 按键 {key_str}")

        except Exception as e:
            self.task.logger.error(f"[移动] 按键异常: {e}")
            import traceback
            self.task.logger.error(traceback.format_exc())
            raise

    def move_with_interrupt_check(self, keys, should_stop_callback, check_interval=0.05):
        """
        可中断的移动：在移动过程中定期检测是否应该停止
        
        Args:
            keys: 需要按下的键列表
            should_stop_callback: 回调函数，返回 True 时立即停止移动
            check_interval: 检测间隔（秒），默认 0.05 秒
            
        Returns:
            bool: True 表示被中断停止，False 表示正常完成
        """
        if not keys:
            return False

        # ADB 模式：暂时不支持中断，使用普通移动
        if self.is_adb():
            self._press_movement_keys_adb(keys, self.move_duration)
            return False

        # 只有方向改变时才停止（减少停顿）
        if self._current_direction is not None and self._current_direction != keys:
            self._stop_pc()

        key_str = '+'.join(keys)
        self.task.logger.debug(f"[移动] 可中断移动: {key_str}, 最大持续 {self.move_duration}秒")

        try:
            # 按下按键
            for key in keys:
                self.task.send_key_down(key)
            
            self._current_direction = keys
            self._is_moving = True
            
            # 分段检测是否应该停止
            elapsed = 0.0
            interrupted = False
            
            while elapsed < self.move_duration:
                # 短暂休眠
                sleep_time = min(check_interval, self.move_duration - elapsed)
                time.sleep(sleep_time)
                elapsed += sleep_time
                
                # 检测是否应该停止
                if should_stop_callback():
                    interrupted = True
                    self.task.logger.info(f"[移动] 检测到停止条件，中断移动 (已移动 {elapsed:.2f}秒)")
                    break
            
            # 释放按键
            for key in keys:
                self.task.send_key_up(key)
            
            self._is_moving = False
            return interrupted

        except Exception as e:
            self.task.logger.error(f"[移动] 可中断移动异常: {e}")
            # 确保释放按键
            for key in keys:
                try:
                    self.task.send_key_up(key)
                except:
                    pass
            self._is_moving = False
            raise

    def _press_movement_keys_for_duration(self, keys, duration):
        """
        按下移动键并持续指定时间（用于随机移动搜索）

        Args:
            keys: 需要按下的键列表
            duration: 持续时间（秒）
        """
        if not keys:
            return

        # ADB 模式：使用虚拟摇杆
        if self.is_adb():
            self._press_movement_keys_adb(keys, duration)
            return

        key_str = '+'.join(keys)
        self.task.logger.debug(f"[移动] 按下按键: {key_str}, 持续 {duration}秒")

        try:
            # 使用任务类的 send_key_down/up 方法（智能适配后台模式）
            for key in keys:
                self.task.send_key_down(key)

            time.sleep(duration)

            for key in keys:
                self.task.send_key_up(key)

            self._current_direction = keys
            self._is_moving = True

        except Exception as e:
            self.task.logger.error(f"[移动] 按键异常: {e}")

    def _press_movement_keys_adb(self, keys, duration):
        """
        ADB 模式下的移动（虚拟摇杆）

        Args:
            keys: 方向键列表
            duration: 持续时间
        """
        cx, cy = self._get_joystick_center_px()
        if cx is None:
            return

        # 计算摇杆偏移方向
        dx, dy = 0, 0
        for key in keys:
            if key == self.KEY_UP:
                dy -= self.joystick_radius
            elif key == self.KEY_DOWN:
                dy += self.joystick_radius
            elif key == self.KEY_LEFT:
                dx -= self.joystick_radius
            elif key == self.KEY_RIGHT:
                dx += self.joystick_radius

        # 执行滑动（按住摇杆）
        end_x = int(cx + dx)
        end_y = int(cy + dy)

        key_str = '+'.join(keys)
        self.task.logger.debug(f"[移动] ADB 摇杆: {key_str}, 持续 {duration}秒")

        # 使用 swipe 来模拟按住摇杆
        self.task.swipe(cx, cy, end_x, end_y, duration=duration)

        self._current_direction = keys
        self._is_moving = True
    
    # ==================== 手机端移动（虚拟摇杆） ====================
    
    def _get_joystick_center_px(self):
        """获取摇杆中心的像素坐标"""
        frame = self.task.frame
        if frame is None:
            return None, None
        
        height, width = frame.shape[:2]
        cx = int(width * self.joystick_center[0])
        cy = int(height * self.joystick_center[1])
        return cx, cy
    
    def _move_adb_towards(self, target_x, target_y):
        """手机端向目标移动（虚拟摇杆）"""
        cx, cy = self._get_joystick_center_px()
        if cx is None:
            return

        # 获取屏幕中心作为自身参考
        frame = self.task.frame
        self_x = frame.shape[1] // 2
        self_y = frame.shape[0] // 2

        # 计算滑动方向
        dx = target_x - self_x
        dy = target_y - self_y
        length = math.sqrt(dx * dx + dy * dy)

        if length < 1:
            return

        # 归一化并缩放到摇杆半径
        dx = dx / length * self.joystick_radius
        dy = dy / length * self.joystick_radius

        # 执行滑动（使用配置的移动持续时间）
        self.task.swipe(cx, cy, int(cx + dx), int(cy + dy), duration=self.move_duration)

    def _move_adb_away(self, target_x, target_y):
        """手机端远离目标"""
        cx, cy = self._get_joystick_center_px()
        if cx is None:
            return

        frame = self.task.frame
        self_x = frame.shape[1] // 2
        self_y = frame.shape[0] // 2

        # 计算相反方向
        dx = self_x - target_x
        dy = self_y - target_y
        length = math.sqrt(dx * dx + dy * dy)

        if length < 1:
            return

        dx = dx / length * self.joystick_radius
        dy = dy / length * self.joystick_radius

        # 执行滑动（使用配置的移动持续时间）
        self.task.swipe(cx, cy, int(cx + dx), int(cy + dy), duration=self.move_duration)
    
    def _move_adb_left_right(self, duration=1):
        """手机端左右来回移动"""
        cx, cy = self._get_joystick_center_px()
        if cx is None:
            return
        
        # 向左滑动
        self.task.swipe(cx, cy, cx - self.joystick_radius, cy, duration=duration)
        time.sleep(0.1)
        
        # 向右滑动
        self.task.swipe(cx, cy, cx + self.joystick_radius, cy, duration=duration)
    
    def _move_adb_up(self, duration=1):
        """手机端向上移动"""
        cx, cy = self._get_joystick_center_px()
        if cx is None:
            return
        
        self.task.swipe(cx, cy, cx, cy - self.joystick_radius, duration=duration)
    
    def _stop_adb(self):
        """手机端停止移动（释放摇杆）"""
        # ADB 模式下滑动结束即自动停止
        pass
