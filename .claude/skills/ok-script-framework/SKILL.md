---
name: ok-script-framework
description: ok-script自动化测试框架参考。当用户提到"ok-script"、"自动化框架"、"截图"、"键鼠控制"、"PostMessage"、"后台交互"、"模板匹配"、"OCR"时自动调用。提供截图、输入控制、设备管理等API参考。
---

# ok-script 自动化测试框架

ok-script 是基于图像识别技术、纯Python实现的自动化测试框架，支持Windows窗口和模拟器。

**本地路径**: `E:\python wuwa\ok-script`
**GitHub**: https://github.com/ok-oldking/ok-script
**Python版本**: 3.12

## 核心模块

```
E:\python wuwa\ok-script\ok\
├── capture/           # 截图模块
│   ├── adb/           # ADB截图(模拟器)
│   └── windows/       # Windows窗口截图
├── device/            # 设备与输入控制
│   ├── DeviceManager.py    # 设备管理器
│   └── intercation.py      # 交互方式实现
├── ocr/               # OCR识别
├── feature/           # 特征匹配
├── gui/               # GUI界面
├── task/              # 任务系统
└── util/              # 工具函数
```

## 交互方式 (intercation.py)

### 1. PostMessageInteraction - 后台交互 (推荐)

支持游戏窗口最小化/被遮挡时后台操作：

```python
class PostMessageInteraction(BaseInteraction):
    def send_key(self, key, down_time=0.01):
        # 使用 win32gui.PostMessage 发送按键

    def send_key_down(self, key, activate=True):
        vk_code = self.get_key_by_str(key)
        lparam = self.make_lparam(vk_code, is_up=False)
        self.post(win32con.WM_KEYDOWN, vk_code, lparam)

    def send_key_up(self, key):
        vk_code = self.get_key_by_str(key)
        lparam = self.make_lparam(vk_code, is_up=True)
        self.post(win32con.WM_KEYUP, vk_code, lparam)

    def click(self, x, y, key="left"):
        # WM_LBUTTONDOWN/WM_LBUTTONUP

    def move(self, x, y, down_btn=0):
        # WM_MOUSEMOVE

    def post(self, message, wParam=0, lParam=0):
        win32gui.PostMessage(self.hwnd, message, wParam, lParam)
```

### 2. PyDirectInteraction - 前台交互

需要窗口在前台，使用pydirectinput模拟输入。

### 3. PynputInteraction - 前台交互

使用pynput库模拟输入，需要窗口在前台。

### 4. GenshinInteraction - 原神专用

针对原神的特殊交互实现。

## 设备管理 (DeviceManager.py)

```python
class DeviceManager:
    def __init__(self, app_config, exit_event=None, global_config=None):
        # 根据配置选择交互方式
        if interaction == 'PostMessage':
            self.win_interaction_class = PostMessageInteraction
        elif interaction == 'Genshin':
            self.win_interaction_class = GenshinInteraction
        elif interaction == 'Pynput':
            self.win_interaction_class = PynputInteraction
        else:
            self.win_interaction_class = PyDirectInteraction
```

## 关键文件

| 文件 | 用途 |
|------|------|
| `ok/device/intercation.py` | 所有交互方式实现 |
| `ok/device/DeviceManager.py` | 设备管理、截图控制 |
| `ok/capture/windows/` | Windows窗口截图 |
| `ok/capture/adb/` | ADB截图(模拟器) |

## 使用方式

```python
# pip安装
pip install ok-script

# 本地开发 - 创建软链接
mklink /d "项目路径\ok" "E:\python wuwa\ok-script\ok"
```

## 配置交互方式

在项目配置中设置:

```python
app_config = {
    'windows': {
        'exe': 'game.exe',
        'title': 'Game Window',
        'interaction': 'PostMessage'  # 后台交互
    }
}
```

## 虚拟键码表 (vk_key_dict)

```python
vk_key_dict = {
    'F1-F12': win32con.VK_F1~VK_F12,
    'ESC': win32con.VK_ESCAPE,
    'ALT': win32con.VK_MENU,
    'CONTROL': win32con.VK_CONTROL,
    'SHIFT': win32con.VK_SHIFT,
    'TAB': win32con.VK_TAB,
    'ENTER': win32con.VK_RETURN,
    'SPACE': win32con.VK_SPACE,
    'LEFT/UP/RIGHT/DOWN': 方向键
}
```
