---
name: maaend-reference
description: MaaEnd项目技术参考，用于终末地游戏自动化开发。当用户提到"终末地"、"Endfield"、"后台运行"、"SendMessage"、"PostMessage"、"Win32后台控制"时自动调用。提供后台截图、后台键鼠操作等技术实现参考。
---

# MaaEnd 技术参考

MaaEnd 是基于 MaaFramework 开发的终末地游戏自动化工具，项目位于 `E:\python wuwa\MaaEnd`。

## 核心技术：后台运行

MaaEnd 实现了游戏窗口后台运行时仍可进行脚本操作，核心配置在 `assets/interface.json`:

```json
{
    "type": "Win32",
    "win32": {
        "class_regex": "UnityWndClass",
        "window_regex": "Endfield",
        "screencap": "Background",
        "mouse": "SendMessageWithWindowPos",
        "keyboard": "PostMessage"
    }
}
```

### 关键配置项

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `screencap` | `Background` | 后台截图，使用 Win32 BitBlt |
| `mouse` | `SendMessageWithWindowPos` | 后台鼠标，发送窗口坐标消息 |
| `mouse` | `SendMessageWithCursorPos` | 后台鼠标，发送光标坐标消息 |
| `keyboard` | `PostMessage` | 后台键盘，异步发送按键消息 |

### 控制器类型

1. **Win32-Window**: 后台运行，使用光标坐标
2. **Win32-Window-Background**: 后台运行，使用窗口坐标
3. **Win32-Front**: 前台运行，需要独占窗口

## 项目结构

```
E:\python wuwa\MaaEnd\
├── assets/
│   ├── interface.json          # 控制器和任务配置入口
│   ├── tasks/                  # 任务定义 JSON
│   ├── resource/
│   │   ├── pipeline/           # Pipeline 低代码逻辑
│   │   └── image/              # 图片资源 (720p基准)
│   └── misc/locales/           # 国际化文件
├── agent/
│   ├── go-service/             # Go 自定义服务
│   └── cpp-algo/               # C++ 算法模块
│       └── source/MapNavigator/
│           └── input_backend.cpp  # 输入后端实现
└── docs/zh_cn/developers/      # 开发文档
```

## 关键文件

| 文件 | 用途 |
|------|------|
| `AGENTS.md` | AI Agent 编码指南 |
| `assets/interface.json` | 控制器配置、任务列表 |
| `agent/cpp-algo/source/MapNavigator/input_backend.cpp` | 输入后端实现 |
| `docs/zh_cn/developers/development.md` | 开发手册 |

## 开发规范

### Pipeline 低代码

- 所有坐标和图片以 **720p (1280x720)** 为基准
- 遵循"识别 -> 操作 -> 识别"循环，避免盲目 delay
- 每步操作基于识别结果，不假设点击后状态

### 输入后端 (input_backend.cpp)

`IInputBackend` 接口定义了输入抽象:

```cpp
class IInputBackend {
    virtual void KeyDownSync(int key_code, int delay_millis) = 0;
    virtual void KeyUpSync(int key_code, int delay_millis) = 0;
    virtual void ClickKeySync(int key_code, int hold_millis) = 0;
    virtual void ClickMouseLeftSync() = 0;
    virtual void MouseRightDownSync(int delay_millis) = 0;
    virtual void MouseRightUpSync(int delay_millis) = 0;
    virtual void SendRelativeMoveSync(int dx, int dy) = 0;
};
```

## 使用方式

当需要参考 MaaEnd 技术实现时:

1. **后台运行配置**: 查看 `assets/interface.json` 的 controller 配置
2. **输入控制实现**: 查看 `agent/cpp-algo/source/MapNavigator/input_backend.cpp`
3. **Pipeline 逻辑**: 查看 `assets/resource/pipeline/` 目录
4. **开发规范**: 查看 `AGENTS.md` 和 `docs/zh_cn/developers/`
