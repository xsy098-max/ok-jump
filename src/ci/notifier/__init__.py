"""
通知模块

提供多种通知方式：
- 企业微信通知
"""

from src.ci.notifier.wecom_notifier import WeComNotifier

__all__ = [
    'WeComNotifier',
]
