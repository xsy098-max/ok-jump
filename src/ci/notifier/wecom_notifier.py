"""
企业微信通知模块

通过企业微信机器人Webhook发送测试报告通知
"""

import base64
import json
import logging
import time
from typing import Optional, List

import requests

from src.ci.test_result_manager import TestReport, DailyReport


logger = logging.getLogger(__name__)


class WeComNotifier:
    """
    企业微信通知器

    功能：
    - 发送Markdown格式消息
    - 支持发送图片（失败截图）
    - 测试报告推送
    - 每日报告推送

    使用示例:
        notifier = WeComNotifier(webhook_url="https://qyapi.weixin.qq.com/...")
        notifier.send_test_result(report)
    """

    def __init__(
        self,
        webhook_url: str,
        timeout: int = 30,
        retry_count: int = 3
    ):
        """
        初始化通知器

        Args:
            webhook_url: 企业微信机器人Webhook URL
            timeout: 请求超时(秒)
            retry_count: 重试次数
        """
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.retry_count = retry_count

    def send_message(self, title: str, content: str) -> bool:
        """
        发送文本消息

        Args:
            title: 消息标题
            content: 消息内容

        Returns:
            bool: 发送成功返回True
        """
        return self.send_markdown(title, content)

    def send_markdown(self, title: str, content: str) -> bool:
        """
        发送Markdown格式消息

        Args:
            title: 消息标题
            content: Markdown格式内容

        Returns:
            bool: 发送成功返回True
        """
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"## {title}\n\n{content}"
            }
        }

        return self._send_request(payload)

    def send_test_result(self, report: TestReport) -> bool:
        """
        发送测试结果通知

        Args:
            report: 测试报告

        Returns:
            bool: 发送成功返回True
        """
        # 构建状态图标
        status_icon = "✅ 通过" if report.failed == 0 else "❌ 失败"

        # 格式化耗时
        duration_str = self._format_duration(report.duration)

        # 构建任务统计
        task_lines = []
        for task_result in report.task_results:
            if task_result.status == 'success':
                task_lines.append(f"• {task_result.task_name}: ✅ 成功")
            elif task_result.status == 'failed':
                task_lines.append(f"• {task_result.task_name}: ❌ 失败")
            else:
                task_lines.append(f"• {task_result.task_name}: ⏭ 跳过")

        # 构建失败详情
        failure_lines = []
        if report.failed > 0:
            for task_result in report.task_results:
                if task_result.status == 'failed' and task_result.error_info:
                    error_msg = task_result.error_info.get('error_message', '未知错误')
                    failure_lines.append(f"• {task_result.task_name}: {error_msg}")

        # 构建消息内容
        content = f"""版本: v{report.version} (#{report.build_number})
状态: {status_icon}
耗时: {duration_str}
────────────────────────────────
任务统计 ({report.passed}/{report.total_tasks} 通过):
{chr(10).join(task_lines)}
────────────────────────────────"""
        if failure_lines:
            content += f"""
失败详情:
{chr(10).join(failure_lines)}"""

        return self.send_markdown("📊 CI测试报告", content)

    def send_daily_report(self, report: DailyReport) -> bool:
        """
        发送每日报告

        Args:
            report: 每日报告

        Returns:
            bool: 发送成功返回True
        """
        # 格式化平均耗时
        avg_duration_str = self._format_duration(report.avg_duration)

        # 构建消息内容
        content = f"""日期: {report.date}
总运行次数: {report.total_runs}
成功次数: {report.success_count}
失败次数: {report.fail_count}
成功率: {report.success_rate:.1f}%
平均耗时: {avg_duration_str}
────────────────────────────────"""
        if report.failure_types:
            content += """
失败类型统计:"""
            for error_type, count in report.failure_types.items():
                content += f"\n• {error_type}: {count}次"

        return self.send_markdown("📊 每日测试报告", content)

    def send_alert(
        self,
        title: str,
        message: str,
        mentioned_list: Optional[List[str]] = None
    ) -> bool:
        """
        发送告警通知

        Args:
            title: 标题
            message: 消息内容
            mentioned_list: @人员列表 (如 ["@all"])

        Returns:
            bool: 发送成功返回True
        """
        if mentioned_list is None:
            mentioned_list = []

        content = f"⚠️ **{title}**\n\n{message}"

        if mentioned_list:
            content += f"\n\n{' '.join(mentioned_list)}"

        return self.send_markdown("🚨 测试告警", content)

    def send_image(self, image_path: str) -> bool:
        """
        发送图片消息

        Args:
            image_path: 图片路径

        Returns:
            bool: 发送成功返回True
        """
        try:
            # 读取图片并转为base64
            with open(image_path, 'rb') as f:
                image_data = f.read()

            base64_data = base64.b64encode(image_data).decode('utf-8')

            # 计算MD5
            import hashlib
            md5 = hashlib.md5(image_data).hexdigest()

            payload = {
                "msgtype": "image",
                "image": {
                    "base64": base64_data,
                    "md5": md5
                }
            }

            return self._send_request(payload)

        except Exception as e:
            logger.error(f"发送图片失败: {e}")
            return False

    def send_error_report(
        self,
        title: str,
        error_message: str,
        screenshots_dir: Optional[str] = None,
        max_images: int = 3,
        since_timestamp: Optional[float] = None
    ) -> bool:
        """
        发送错误报告（错误消息 + 截图）

        Args:
            title: 报告标题
            error_message: 错误消息
            screenshots_dir: 截图目录（可选）
            max_images: 最大发送图片数量
            since_timestamp: 只发送此时间戳之后创建的截图（可选）

        Returns:
            bool: 发送成功返回True
        """
        success = True

        # 1. 发送错误消息
        if not self.send_alert(title, error_message):
            success = False

        # 2. 发送截图（只发送指定时间之后的截图）
        if screenshots_dir:
            from pathlib import Path
            screenshots_path = Path(screenshots_dir)
            logger.info(f"检查截图目录: {screenshots_path.absolute()}")
            if screenshots_path.exists():
                # 获取所有截图文件
                all_screenshots = list(screenshots_path.glob('*.png'))
                logger.info(f"目录中共有 {len(all_screenshots)} 张截图")
                
                # 如果指定了时间戳，只筛选该时间之后的截图
                if since_timestamp:
                    from datetime import datetime
                    filter_time = datetime.fromtimestamp(since_timestamp)
                    logger.info(f"筛选时间戳: {filter_time}")
                    filtered_screenshots = [
                        s for s in all_screenshots 
                        if s.stat().st_mtime >= since_timestamp
                    ]
                    logger.info(f"筛选后剩余 {len(filtered_screenshots)} 张截图")
                else:
                    filtered_screenshots = all_screenshots
                
                # 按修改时间排序，取最新的N张
                screenshot_files = sorted(
                    filtered_screenshots,
                    key=lambda x: x.stat().st_mtime,
                    reverse=True
                )[:max_images]
                
                if screenshot_files:
                    logger.info(f"筛选到 {len(screenshot_files)} 张本次任务的截图")
                else:
                    logger.warning("未找到符合条件的截图")
                
                for screenshot in screenshot_files:
                    if self.send_image(str(screenshot)):
                        logger.info(f"发送截图: {screenshot.name}")
                    else:
                        success = False
                    time.sleep(0.5)  # 避免发送过快
            else:
                logger.warning(f"截图目录不存在: {screenshots_path}")
        else:
            logger.info("未指定截图目录，跳过截图发送")

        return success

    def _send_request(self, payload: dict) -> bool:
        """
        发送HTTP请求

        Args:
            payload: 请求体

        Returns:
            bool: 发送成功返回True
        """
        if not self.webhook_url:
            logger.warning("未配置企业微信Webhook URL，跳过发送通知")
            return False

        for attempt in range(self.retry_count):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout
                )
                response.raise_for_status()

                result = response.json()
                if result.get('errcode') == 0:
                    logger.info("企业微信通知发送成功")
                    return True
                else:
                    logger.warning(f"企业微信通知发送失败: {result}")

            except requests.RequestException as e:
                logger.warning(f"发送请求失败 (尝试 {attempt + 1}/{self.retry_count}): {e}")

                if attempt < self.retry_count - 1:
                    time.sleep(1)

        logger.error("企业微信通知发送失败")
        return False

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """
        格式化耗时

        Args:
            seconds: 秒数

        Returns:
            str: 格式化后的字符串
        """
        if seconds < 60:
            return f"{seconds:.0f}秒"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}分{secs}秒"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}小时{minutes}分"
