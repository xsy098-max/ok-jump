"""
测试 pydirectinput 是否能正常发送按键到游戏
运行方法: 以管理员身份运行，然后快速切换到游戏窗口
"""
import time
import pydirectinput

print("=" * 50)
print("pydirectinput 输入测试")
print("=" * 50)
print()
print("请在 5 秒内切换到游戏窗口...")
print("测试将依次发送: W(1秒), A(1秒), S(1秒), D(1秒)")
print()

for i in range(5, 0, -1):
    print(f"倒计时: {i}秒")
    time.sleep(1)

print()
print("开始测试...")

# 测试方法1: keyDown + sleep + keyUp
print("[测试1] 使用 keyDown + sleep + keyUp")
for key in ['w', 'a', 's', 'd']:
    print(f"  按下 {key.upper()}...")
    pydirectinput.keyDown(key)
    time.sleep(0.5)
    pydirectinput.keyUp(key)
    time.sleep(0.2)

print()

# 测试方法2: 直接使用 press
print("[测试2] 使用 press (按下并立即释放)")
for key in ['w', 'a', 's', 'd']:
    print(f"  按键 {key.upper()}...")
    pydirectinput.press(key)
    time.sleep(0.3)

print()

# 测试方法3: 使用 hold (上下文管理器)
print("[测试3] 使用 hold (持续按住)")
for key in ['w', 'a', 's', 'd']:
    print(f"  持续按住 {key.upper()} 0.5秒...")
    with pydirectinput.hold(key):
        time.sleep(0.5)
    time.sleep(0.2)

print()
print("测试完成！")
print("如果游戏角色移动了，说明 pydirectinput 工作正常")
print("如果没有移动，可能是:")
print("1. 游戏使用了反作弊机制")
print("2. 游戏窗口没有真正获得焦点")
print("3. 需要其他输入方式")
