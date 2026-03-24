"""
特征名称常量类

统一管理所有在 coco_detection.json 中定义的特征名称
确保代码中使用的特征名称与配置文件一致
"""


class Features:
    """
    特征名称常量类

    所有特征名称必须与 assets/coco_detection.json 中的 categories 定义一致
    不可实例化，仅作为常量容器使用
    """

    def __init__(self):
        raise NotImplementedError("Features 类不可实例化，仅作为常量容器使用")

    # ==================== 登录界面相关 ====================

    # 登录界面指示器
    LOGIN_SCREEN_0_INDICATOR = 'login_screen_0_indicator'  # 适龄提示界面
    LOGIN_SCREEN_1_INDICATOR = 'login_screen_1_indicator'  # 账户登录界面
    LOGIN_SCREEN_2_INDICATOR = 'login_screen_2_indicator'  # 开始游戏界面

    # 登录按钮
    ENTER_GAME_BUTTON = 'enter_game_button'    # 进入游戏按钮
    START_GAME_BUTTON = 'start_game_button'    # 开始游戏按钮
    LOGIN_BUTTON = 'login_button'              # 登录按钮

    # 登录界面文本
    AGE_PROMPT_TEXT = 'age_prompt_text'        # 适龄提示文本
    AGREE_TEXT = 'agree_text'                  # 同意文本
    ACCOUNT_NAME_TEXT = 'account_name_text'    # 账户名文本
    CHANGE_SERVER_TEXT = 'change_server_text'  # 换区文本

    # 协议勾选框
    RENZHEN_UNCHECKED = 'renzhen01'  # 未勾选的协议框
    RENZHEN_CHECKED = 'renzhen02'    # 已勾选的协议框

    # 登录成功
    SUCCESS_ENTER = 'success_enter'  # 成功进入游戏

    # ==================== 问卷调查相关 ====================

    WENJUAN_ENTER = 'wenjuan_enter'  # 问卷调查入口
    WENJUAN_END = 'wenjuan_end'      # 问卷结束按钮
    WENJUAN_END2 = 'wenjuan_end2'    # 问卷结束按钮2
    WENJUAN_OPTION_1 = 'wenjuan1'    # 问卷选项1
    WENJUAN_OPTION_2 = 'wenjuan2'    # 问卷选项2
    WENJUAN_OPTION_3 = 'wenjuan3'    # 问卷选项3
    WENJUAN_SUBMIT = 'wenjuan_sub'   # 问卷提交按钮

    # ==================== 角色选择 ====================

    XUANREN = 'xuanren'  # 角色选择界面

    # ==================== 游戏状态相关 ====================

    # 主菜单
    MAIN_MENU_START = 'main_menu_start'  # 主菜单开始按钮

    # 大厅
    LOBBY_INDICATOR = 'lobby_indicator'  # 大厅指示器

    # 游戏中
    IN_GAME_INDICATOR = 'in_game_indicator'  # 游戏中指示器
    IN_GAME_HUD = 'in_game_hud'              # 游戏 HUD

    # 加载中
    LOADING_INDICATOR = 'loading_indicator'  # 加载指示器

    # ==================== 匹配和战斗相关 ====================

    HERO_SELECT_CONFIRM = 'hero_select_confirm'  # 英雄选择确认

    # ==================== 结算画面 ====================

    RESULT_VICTORY = 'result_victory'  # 胜利结算
    RESULT_DEFEAT = 'result_defeat'    # 失败结算

    # ==================== 新手教程相关 ====================

    TUTORIAL_BACK_BUTTON = 'tutorial_back_button'       # 返回按钮
    TUTORIAL_CONFIRM_BUTTON = 'tutorial_confirm_button' # 确定按钮
    TUTORIAL_END01 = 'tutorial_end01'                   # 第一阶段结束标志
    TUTORIAL_END02 = 'tutorial_end02'                   # 开始对战按钮
    TUTORIAL_FIGHT_START = 'fight_start'                # 战斗开始标志
    TUTORIAL_FIGHT_END = 'fight_end'                    # 战斗结束标志
    TUTORIAL_MVP_OUT = 'out'                            # MVP场景退出按钮
    TUTORIAL_NEW_HERO = 'new_hero'                      # 新英雄场景标志


# 便于导入的别名
F = Features
