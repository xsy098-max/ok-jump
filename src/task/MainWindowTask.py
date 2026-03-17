from ok import og
from src.task.BaseJumpTask import BaseJumpTask


class MainWindowTask(BaseJumpTask):
    
    FEATURE_CATEGORIES = {
        'core': {
            'name': '核心功能',
            'name_en': 'Core Features',
            'tasks': [
                {'name': 'WindowCapture', 'desc': '窗口识别与截图', 'status': 'done'},
                {'name': 'ResolutionAdapter', 'desc': '自适应分辨率', 'status': 'done'},
                {'name': 'CocoManager', 'desc': 'COCO图片匹配素材管理', 'status': 'planned'},
                {'name': 'BackgroundMode', 'desc': '后台模式', 'status': 'done'},
            ]
        },
        'game': {
            'name': '游戏功能',
            'name_en': 'Game Features',
            'tasks': [
                {'name': 'AutoLogin', 'desc': '自动登录', 'status': 'planned'},
                {'name': 'AutoMatch', 'desc': '自动匹配', 'status': 'planned'},
                {'name': 'AutoCombat', 'desc': '自动战斗', 'status': 'planned'},
                {'name': 'AutoSkill', 'desc': '技能释放', 'status': 'planned'},
            ]
        },
        'moba': {
            'name': 'MOBA功能',
            'name_en': 'MOBA Features',
            'tasks': [
                {'name': 'LaneControl', 'desc': '对线控制', 'status': 'planned'},
                {'name': 'JunglePath', 'desc': '打野路线', 'status': 'planned'},
                {'name': 'TeamFight', 'desc': '团战辅助', 'status': 'planned'},
                {'name': 'TowerPush', 'desc': '推塔策略', 'status': 'planned'},
            ]
        },
        'utility': {
            'name': '实用工具',
            'name_en': 'Utility Tools',
            'tasks': [
                {'name': 'DailyTask', 'desc': '日常任务', 'status': 'planned'},
                {'name': 'ResourceCollector', 'desc': '资源收集', 'status': 'planned'},
                {'name': 'EventHelper', 'desc': '活动辅助', 'status': 'planned'},
            ]
        },
    }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "MainWindowTask"
        self.description = "主窗口 - 功能开发索引"
        self.feature_index = self._build_feature_index()
    
    def run(self):
        self.logger.info("=" * 60)
        self.logger.info("漫画群星：大集结 - 自动化工具 v1.0.0")
        self.logger.info("=" * 60)
        self.logger.info("")
        
        self._print_feature_index()
        
        self.logger.info("")
        self.logger.info("正在检测游戏窗口...")
        
        if self._detect_game_window():
            self.logger.info("游戏窗口检测成功！")
            self._test_screenshot()
            self._check_resolution()
            self._check_background_mode()
        else:
            self.logger.warning("未检测到游戏窗口，请确保游戏已启动")
            self.logger.info("支持的窗口标题关键词: '漫画群星', 'Jump'")
            self.logger.info("支持的模拟器ADB包名: com.fivecross.mhqdjj")
        
        self.logger.info("")
        self.logger.info("核心功能模块初始化完成")
        self.logger.info("后续功能开发将在独立任务窗口中进行")
        
        return True
    
    def _build_feature_index(self):
        index = {}
        for category_key, category_info in self.FEATURE_CATEGORIES.items():
            index[category_key] = {
                'name': category_info['name'],
                'name_en': category_info['name_en'],
                'tasks': {}
            }
            for task in category_info['tasks']:
                index[category_key]['tasks'][task['name']] = {
                    'desc': task['desc'],
                    'status': task['status']
                }
        return index
    
    def _print_feature_index(self):
        self.logger.info("功能开发索引:")
        self.logger.info("-" * 60)
        
        for category_key, category_info in self.FEATURE_CATEGORIES.items():
            self.logger.info(f"")
            self.logger.info(f"【{category_info['name']}】({category_info['name_en']})")
            
            for task in category_info['tasks']:
                status_icon = self._get_status_icon(task['status'])
                self.logger.info(f"  {status_icon} {task['name']}: {task['desc']}")
        
        self.logger.info("")
        self.logger.info("-" * 60)
        self.logger.info("状态说明: [✓]已完成 [○]开发中 [×]计划中")
    
    def _get_status_icon(self, status):
        status_map = {
            'done': '[✓]',
            'in_progress': '[○]',
            'planned': '[×]'
        }
        return status_map.get(status, '[?]')
    
    def _detect_game_window(self):
        try:
            self.next_frame()
            if self.frame is not None:
                height, width = self.frame.shape[:2]
                self.logger.info(f"截图成功: {width}x{height}")
                
                if hasattr(self, 'hwnd_title') and self.hwnd_title:
                    self.logger.info(f"窗口标题: {self.hwnd_title}")
                
                return True
            return False
        except Exception as e:
            self.logger.error(f"窗口检测失败: {e}")
            return False
    
    def _test_screenshot(self):
        try:
            self.next_frame()
            if self.frame is not None:
                self.screenshot = self.frame
                self.logger.info("截图功能测试通过")
                return True
            return False
        except Exception as e:
            self.logger.error(f"截图测试失败: {e}")
            return False
    
    def _check_resolution(self):
        self.update_resolution()
        res_info = self.get_resolution_info()
        
        self.logger.info("")
        self.logger.info("分辨率信息:")
        self.logger.info(f"  当前分辨率: {res_info['current'][0]}x{res_info['current'][1]}")
        self.logger.info(f"  参考分辨率: {res_info['reference'][0]}x{res_info['reference'][1]}")
        self.logger.info(f"  缩放比例: X={res_info['scale_x']:.3f}, Y={res_info['scale_y']:.3f}")
        
        if res_info['is_valid']:
            self.logger.info("  比例检查: ✓ 16:9 比例正确")
        else:
            from src.utils.resolution_adapter import resolution_adapter
            recommended = resolution_adapter.get_recommended_resize()
            self.logger.warning(f"  比例检查: × 不是 16:9 比例")
            self.logger.warning(f"  建议分辨率: {recommended[0]}x{recommended[1]}")
    
    def _check_background_mode(self):
        self.check_background_mode()
        bg_status = self.get_background_status()
        
        self.logger.info("")
        self.logger.info("后台模式信息:")
        
        if bg_status['background_mode_enabled']:
            self.logger.info("  后台模式: ✓ 已启用")
            self.logger.info("  游戏窗口可最小化或被遮挡时继续运行")
            
            if bg_status['auto_pseudo_minimize']:
                self.logger.info("  伪最小化: ✓ 已启用")
                self.logger.info("  窗口最小化时自动移到屏幕外，支持后台截图")
            else:
                self.logger.info("  伪最小化: × 未启用")
            
            if bg_status['is_pseudo_minimized']:
                self.logger.info("  当前状态: 窗口已伪最小化")
            elif bg_status['is_in_background']:
                self.logger.info("  当前状态: 游戏窗口在后台运行中")
            else:
                self.logger.info("  当前状态: 游戏窗口在前台")
        else:
            self.logger.info("  后台模式: × 未启用")
            self.logger.info("  游戏窗口需要保持前台才能正常运行")
        
        if bg_status['should_mute']:
            self.logger.info("  静音设置: 后台时自动静音游戏")
    
    def get_feature_status(self, category, task_name):
        if category in self.feature_index:
            tasks = self.feature_index[category]['tasks']
            if task_name in tasks:
                return tasks[task_name]['status']
        return None
    
    def update_feature_status(self, category, task_name, status):
        if category in self.feature_index:
            tasks = self.feature_index[category]['tasks']
            if task_name in tasks:
                tasks[task_name]['status'] = status
                self.logger.info(f"更新功能状态: {category}.{task_name} -> {status}")
                return True
        return False
    
    def get_all_features(self):
        return self.feature_index
