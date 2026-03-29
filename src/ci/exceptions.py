"""
CI测试自定义异常类

定义CI测试系统中使用的所有自定义异常类型
"""


class CITestException(Exception):
    """CI测试基础异常"""
    pass


class PackageDownloadException(CITestException):
    """包下载异常"""
    pass


class EmulatorStartException(CITestException):
    """模拟器启动异常"""
    pass


class GameStartTimeoutException(CITestException):
    """游戏启动超时异常"""
    pass


class TaskTriggerTimeoutException(CITestException):
    """任务触发超时异常"""
    pass


class GameStagnantException(CITestException):
    """游戏画面停滞异常"""
    pass


class ContinuousFailureException(CITestException):
    """连续失败次数过多异常"""
    pass


class GameProcessExitedException(CITestException):
    """游戏进程退出异常"""
    pass
