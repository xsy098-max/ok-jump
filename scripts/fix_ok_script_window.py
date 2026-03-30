"""
修复 ok-script 框架中 get_exe_by_hwnd 函数的 NoSuchProcess 异常处理问题

当模拟器关闭后，进程已不存在，但代码还在尝试获取进程信息，
导致 NoSuchProcess 异常被打印到日志中。

此脚本会修改 site-packages 中的 window.py 文件，添加对 NoSuchProcess 的捕获。
"""

import re
import sys
from pathlib import Path


def find_ok_script_window_py():
    """找到 ok-script 框架中 window.py 的位置"""
    import ok
    ok_path = Path(ok.__file__).parent
    window_py = ok_path / "util" / "window.py"
    return window_py


def fix_window_py(window_py_path: Path):
    """修复 window.py 文件"""
    content = window_py_path.read_text(encoding='utf-8')
    
    # 检查是否已经修复过
    if "psutil.NoSuchProcess" in content:
        print("✓ 文件已经包含 NoSuchProcess 异常处理，无需修复")
        return False
    
    # 替换 process.name() 的异常处理
    content = re.sub(
        r'except psutil\.AccessDenied as e:\s*\n\s*name = ""\s*\n\s*logger\.error\("get_exe_by_hwnd process\.name\(\) AccessDenied", e\)',
        'except (psutil.AccessDenied, psutil.NoSuchProcess) as e:\n                name = ""\n                logger.error("get_exe_by_hwnd process.name() error", e)',
        content
    )
    
    # 替换 process.exe() 的异常处理
    content = re.sub(
        r'except psutil\.AccessDenied as e:\s*\n\s*exe = ""\s*\n\s*logger\.error\("get_exe_by_hwnd process\.exe\(\) AccessDenied", e\)',
        'except (psutil.AccessDenied, psutil.NoSuchProcess) as e:\n                exe = ""\n                logger.error("get_exe_by_hwnd process.exe() error", e)',
        content
    )
    
    # 替换 process.cmdline() 的异常处理
    content = re.sub(
        r'except psutil\.AccessDenied as e:\s*\n\s*cmdline = ""\s*\n\s*logger\.error\("get_exe_by_hwnd process\.cmdline\(\) AccessDenied", e\)',
        'except (psutil.AccessDenied, psutil.NoSuchProcess) as e:\n                cmdline = ""\n                logger.error("get_exe_by_hwnd process.cmdline() error", e)',
        content
    )
    
    # 写回文件
    window_py_path.write_text(content, encoding='utf-8')
    print(f"✓ 已修复文件: {window_py_path}")
    return True


def main():
    print("=" * 50)
    print("ok-script window.py 修复工具")
    print("=" * 50)
    
    try:
        window_py_path = find_ok_script_window_py()
        print(f"找到 window.py: {window_py_path}")
    except ImportError:
        print("错误: 未找到 ok-script 包，请确保已安装")
        sys.exit(1)
    
    if not window_py_path.exists():
        print(f"错误: 文件不存在: {window_py_path}")
        sys.exit(1)
    
    if fix_window_py(window_py_path):
        print("\n修复完成！")
        print("现在关闭模拟器时不会再出现 NoSuchProcess 错误日志了。")
    else:
        print("\n无需修复。")


if __name__ == "__main__":
    main()
