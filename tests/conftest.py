"""共享 pytest 配置:让单元测试不真实等待。

两类时间黑洞都要处理:
1. 直接的 time.sleep(battle_room_checks 等几十处 UI 等待)——截断到至多
   5 毫秒,保留线程让出与先后顺序。
2. 墙上时钟死等循环(`deadline = time.time() + timeout; while time.time()
   < deadline`,见 battle_room_ui.wait_view / AutoLoginTask._handle_wenjuan /
   compat.patches)——截断 sleep 只会让空转变快,循环仍要转满真实截止时间。
   对这些模块注入 50 倍加速的时钟替身,截止时间即可快速到期。
"""

import importlib
import time

import pytest

_MAX_TEST_SLEEP_SECONDS = 0.005
_CLOCK_SCALE = 50
# 含墙上时钟死等循环、需要加速时钟的模块(模块内 `import time` 后以
# time.xxx 引用,替换其命名空间里的 time 模块即可生效)。
# 注意不能加速 src.task.AutoLoginTask:其 _input_account 用
# _assert_account_input_timeout 做真实耗时断言,加速会误判超时;
# 问卷等待改为在测试里把 WENJUAN_WAIT_TIMEOUT 常量调小。
_FAST_CLOCK_MODULES = [
    "src.task.battle_room_ui",
    "src.task.battle_room_checks",
    "src.compat.patches",
]


class _FastClock:
    """time 模块替身:time.time 按 _CLOCK_SCALE 加速流逝,sleep 等比缩短。"""

    def __init__(self):
        self._origin = time.time()

    def time(self):
        return self._origin + (time.time() - self._origin) * _CLOCK_SCALE

    def sleep(self, seconds):
        time.sleep(min(float(seconds) / _CLOCK_SCALE, _MAX_TEST_SLEEP_SECONDS))

    def __getattr__(self, name):
        return getattr(time, name)


@pytest.fixture(autouse=True)
def _fast_test_time(monkeypatch):
    real_sleep = time.sleep

    def _capped_sleep(seconds):
        real_sleep(min(float(seconds), _MAX_TEST_SLEEP_SECONDS))

    monkeypatch.setattr(time, "sleep", _capped_sleep)
    # ok-script 框架层 sleep(TaskExecutor.sleep)是按墙上时钟的循环,
    # 截断 time.sleep 对它无效,必须整体短路;BaseTask.sleep 只是转发。
    monkeypatch.setattr("ok.task.TaskExecutor.TaskExecutor.sleep",
                        lambda self, timeout: None)
    monkeypatch.setattr("ok.task.task.BaseTask.sleep",
                        lambda self, timeout: True)
    fast_clock = _FastClock()
    for module_name in _FAST_CLOCK_MODULES:
        # 不能用 "pkg.module.time" 字符串路径:src.task 包里有同名类遮蔽
        # 模块属性(如 AutoLoginTask),importlib 拿到的才是真模块
        module = importlib.import_module(module_name)
        monkeypatch.setattr(module, "time", fast_clock)
