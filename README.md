# ok-jump (漫画群星：大集结 - 自动化工具)

本项目是基于 `ok-script` 框架构建的针对 MOBA 手游《漫画明星：大集结》（Jump: Assemble）的自动化测试与辅助工具。旨在通过图像识别、OCR 和自动化脚本技术，实现游戏日常任务、自动战斗和流程测试的自动化。

## ✨ 主要功能

当前版本支持以下核心功能：

*   **自动登录 (AutoLoginTask)**: 支持游戏自动启动与登录流程。
*   **主界面交互 (MainWindowTask)**: 识别主界面状态，处理弹窗与导航。
*   **新手引导 (AutoTutorialTask)**: 自动化完成新手教程流程。
*   **自动匹配 (AutoMatchTask)**: 支持自动进行游戏匹配。
*   **自动战斗 (AutoCombatTask)**:
    *   支持基础的战斗逻辑。
    *   自定义按键映射（普通攻击、技能释放）。
*   **日常任务 (DailyTask)**: 自动完成每日签到、领取邮件等日常操作。
*   **后台挂机**: 支持游戏窗口后台运行、伪最小化模式，不影响前台工作。

## 🛠️ 技术栈

*   **核心框架**: [ok-script](https://github.com/ok-script/ok-script)
*   **图像识别**: OpenCV, Template Matching
*   **文字识别 (OCR)**: onnxocr (PP-OCRv5)
*   **GUI 界面**: PySide6, Fluent Widgets
*   **设备连接**: adbutils (Android ADB), pywin32 (Windows Client)

## 🚀 快速开始

### 环境要求

*   Windows 10/11
*   Python 3.10 或 3.11

### 安装步骤

1.  **克隆项目**

    ```bash
    git clone https://github.com/your-repo/ok-jump.git
    cd ok-jump
    ```

2.  **创建虚拟环境 (推荐)**

    ```bash
    python -m venv .venv
    # 激活虚拟环境
    # Windows PowerShell:
    .\.venv\Scripts\Activate.ps1
    # Windows CMD:
    .\.venv\Scripts\activate.bat
    ```

3.  **安装依赖**

    ```bash
    pip install -r requirements.txt
    ```

### 运行

直接运行 `main.py` 启动图形化界面：

```bash
python main.py
```

## ⚙️ 配置说明

项目启动后会显示图形化配置界面，支持以下设置：

*   **基础选项**:
    *   `后台模式`: 允许游戏窗口被遮挡或最小化时继续运行。
    *   `启动/停止快捷键`: 默认为 **F9**。
*   **游戏热键配置**:
    *   普通攻击: `J`
    *   技能1: `U`
    *   技能2: `I`
    *   大招: `O`

配置文件位于 `configs/` 目录下，也可通过 GUI 直接修改。

## 📅 开发计划

详见 [开发计划.MD](开发计划.MD) 文档，了解项目的详细架构设计与路线图。

## 📄 许可证

MIT License
