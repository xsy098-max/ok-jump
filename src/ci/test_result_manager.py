"""
测试结果管理模块

管理测试结果的存储、查询和报告生成
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict

from src.ci.exception_handler import FailureInfo


logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """单个任务执行结果"""
    task_name: str                                    # 任务名称
    status: str                                       # success/failed/skipped
    start_time: str                                   # 开始时间
    end_time: str                                     # 结束时间
    duration: float                                   # 耗时(秒)
    error_info: Optional[Dict] = None                 # 错误信息
    screenshots: List[str] = field(default_factory=list)  # 截图路径列表
    metrics: Dict = field(default_factory=dict)       # 任务特定指标

    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)


@dataclass
class TestReport:
    """测试报告"""
    report_id: str                                    # 报告ID
    timestamp: str                                    # 时间戳
    version: str                                      # 测试包版本
    build_number: int                                 # 构建号
    total_tasks: int                                  # 总任务数
    passed: int                                       # 通过数
    failed: int                                       # 失败数
    skipped: int                                      # 跳过数
    duration: float                                   # 总耗时(秒)
    task_results: List[TaskResult] = field(default_factory=list)
    summary: str = ""                                 # 摘要

    def to_dict(self) -> dict:
        """转换为字典"""
        result = asdict(self)
        result['task_results'] = [t.to_dict() for t in self.task_results]
        return result


@dataclass
class DailyReport:
    """每日报告"""
    date: str                                         # 日期
    total_runs: int                                   # 总运行次数
    success_count: int                                # 成功次数
    fail_count: int                                   # 失败次数
    success_rate: float                               # 成功率
    avg_duration: float                               # 平均耗时
    failure_types: Dict[str, int] = field(default_factory=dict)  # 失败类型统计


class TestResultManager:
    """
    测试结果管理器

    功能：
    - 保存每次测试的完整结果
    - 生成每日汇总报告
    - 历史记录查询
    - 数据清理
    """

    def __init__(
        self,
        results_dir: str = "test_results",
        history_file: str = "test_results/history.json"
    ):
        """
        初始化结果管理器

        Args:
            results_dir: 结果存储目录
            history_file: 历史记录文件路径
        """
        self.results_dir = Path(results_dir)
        self.history_file = Path(history_file)

        # 确保目录存在
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def save_test_report(self, report: TestReport) -> Path:
        """
        保存测试报告

        Args:
            report: 测试报告

        Returns:
            Path: 报告文件路径
        """
        # 创建日期目录
        date_dir = self.results_dir / datetime.now().strftime('%Y-%m-%d')
        date_dir.mkdir(parents=True, exist_ok=True)

        # 创建时间目录
        time_dir = date_dir / datetime.now().strftime('%H-%M-%S')
        time_dir.mkdir(parents=True, exist_ok=True)

        # 保存JSON报告
        report_path = time_dir / "report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

        logger.info(f"测试报告已保存: {report_path}")

        # 更新历史记录
        self._update_history(report, report_path)

        return report_path

    def save_task_result(self, result: TaskResult) -> Path:
        """
        保存任务结果

        Args:
            result: 任务结果

        Returns:
            Path: 结果文件路径
        """
        # 创建日期目录
        date_dir = self.results_dir / datetime.now().strftime('%Y-%m-%d')
        date_dir.mkdir(parents=True, exist_ok=True)

        # 保存结果
        timestamp = datetime.now().strftime('%H-%M-%S')
        result_path = date_dir / f"{timestamp}_{result.task_name}.json"

        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)

        return result_path

    def generate_daily_report(self, target_date: Optional[date] = None) -> DailyReport:
        """
        生成每日报告

        Args:
            target_date: 目标日期，默认今天

        Returns:
            DailyReport: 每日报告
        """
        if target_date is None:
            target_date = date.today()

        date_str = target_date.strftime('%Y-%m-%d')
        date_dir = self.results_dir / date_str

        total_runs = 0
        success_count = 0
        fail_count = 0
        total_duration = 0.0
        failure_types = {}

        if date_dir.exists():
            for time_dir in date_dir.iterdir():
                if time_dir.is_dir():
                    report_file = time_dir / "report.json"
                    if report_file.exists():
                        try:
                            with open(report_file, 'r', encoding='utf-8') as f:
                                report_data = json.load(f)

                            total_runs += 1
                            if report_data.get('failed', 0) == 0:
                                success_count += 1
                            else:
                                fail_count += 1
                            total_duration += report_data.get('duration', 0)

                            # 统计失败类型
                            for task_result in report_data.get('task_results', []):
                                if task_result.get('status') == 'failed' and task_result.get('error_info'):
                                    error_type = task_result['error_info'].get('error_type', 'Unknown')
                                    failure_types[error_type] = failure_types.get(error_type, 0) + 1

                        except Exception as e:
                            logger.warning(f"读取报告失败: {report_file}, {e}")

        # 计算成功率和平均耗时
        success_rate = (success_count / total_runs * 100) if total_runs > 0 else 0
        avg_duration = total_duration / total_runs if total_runs > 0 else 0

        return DailyReport(
            date=date_str,
            total_runs=total_runs,
            success_count=success_count,
            fail_count=fail_count,
            success_rate=success_rate,
            avg_duration=avg_duration,
            failure_types=failure_types
        )

    def get_test_history(self, days: int = 7) -> List[dict]:
        """
        获取历史测试记录

        Args:
            days: 查询天数

        Returns:
            list: 历史记录列表
        """
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                return history.get('records', [])[:days * 10]  # 假设每天最多10次测试
            except Exception as e:
                logger.warning(f"读取历史记录失败: {e}")

        return []

    def _update_history(self, report: TestReport, report_path: Path):
        """
        更新历史记录

        Args:
            report: 测试报告
            report_path: 报告路径
        """
        # 读取现有历史
        history = {'records': [], 'last_updated': ''}
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except Exception:
                pass

        # 添加新记录
        record = {
            'id': report.report_id,
            'timestamp': report.timestamp,
            'version': report.version,
            'build_number': report.build_number,
            'status': 'success' if report.failed == 0 else 'failed',
            'duration': report.duration,
            'passed': report.passed,
            'failed': report.failed,
            'report_path': str(report_path)
        }

        history['records'].insert(0, record)
        history['last_updated'] = datetime.now().isoformat()

        # 只保留最近100条记录
        history['records'] = history['records'][:100]

        # 保存
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def cleanup_old_results(self, keep_days: int = 30):
        """
        清理旧数据

        Args:
            keep_days: 保留天数
        """
        from datetime import timedelta

        cutoff_date = date.today() - timedelta(days=keep_days)

        for date_dir in self.results_dir.iterdir():
            if date_dir.is_dir() and date_dir.name != 'daily_reports':
                try:
                    dir_date = datetime.strptime(date_dir.name, '%Y-%m-%d').date()
                    if dir_date < cutoff_date:
                        # 删除目录
                        import shutil
                        shutil.rmtree(date_dir)
                        logger.info(f"清理旧数据: {date_dir}")
                except ValueError:
                    # 不是日期格式的目录，跳过
                    pass

    def get_statistics(self) -> dict:
        """
        获取统计信息

        Returns:
            dict: 统计信息
        """
        history = self.get_test_history(days=30)

        if not history:
            return {
                'total_tests': 0,
                'success_rate': 0,
                'avg_duration': 0
            }

        total = len(history)
        success = sum(1 for r in history if r.get('status') == 'success')
        total_duration = sum(r.get('duration', 0) for r in history)

        return {
            'total_tests': total,
            'success_rate': (success / total * 100) if total > 0 else 0,
            'avg_duration': total_duration / total if total > 0 else 0,
            'success_count': success,
            'fail_count': total - success
        }
