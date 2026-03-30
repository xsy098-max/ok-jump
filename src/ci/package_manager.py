"""
Jenkins包管理模块

从Jenkins服务器获取最新构建并下载APK包
"""

import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from src.ci.exceptions import PackageDownloadException


logger = logging.getLogger(__name__)


@dataclass
class PackageInfo:
    """APK包信息"""
    url: str                    # 下载链接
    filename: str               # 文件名
    version: str                # 版本号 (如 0.31.0)
    build_number: int           # 构建号 (如 99)
    size: int                   # 文件大小
    timestamp: int              # 构建时间戳
    svn_revision: int           # SVN版本号 (如 173687)
    version_code: int           # 版本码 (如 3100)
    date: str = ""              # 日期 (如 20260327)


class PackageManager:
    """
    Jenkins包管理器

    核心功能：
    - 从Jenkins REST API获取构建列表
    - 从最新构建开始向下遍历，找到Build文件夹下有APK的构建
    - 支持版本对比，避免重复下载
    - 自动清理旧版本APK

    使用示例:
        manager = PackageManager(
            jenkins_url="http://192.168.9.154:8080",
            job_name="P9_XProject_Android_BrawlStars_Release"
        )
        package_info = manager.find_latest_apk_build()
        local_path = manager.download_package(package_info.url, Path("packages"))
    """

    def __init__(
        self,
        jenkins_url: str,
        job_name: str,
        download_dir: str = "packages",
        max_builds_to_search: int = 20,
        download_timeout: int = 300,
        retry_count: int = 3
    ):
        """
        初始化包管理器

        Args:
            jenkins_url: Jenkins服务器地址
            job_name: Job名称
            download_dir: 下载目录
            max_builds_to_search: 最多向下查找多少个构建
            download_timeout: 下载超时(秒)
            retry_count: 重试次数
        """
        self.jenkins_url = jenkins_url.rstrip('/')
        self.job_name = job_name
        self.download_dir = Path(download_dir)
        self.max_builds_to_search = max_builds_to_search
        self.download_timeout = download_timeout
        self.retry_count = retry_count

        # 确保下载目录存在
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def find_latest_apk_build(self) -> PackageInfo:
        """
        查找最新的有APK的构建

        从最新构建开始向下遍历，找到Build文件夹下有APK文件的构建。

        Returns:
            PackageInfo: 最新可用构建的信息

        Raises:
            PackageDownloadException: 在max_builds_to_search范围内未找到APK
        """
        logger.info(f"开始从Jenkins查找最新APK构建: {self.jenkins_url}/job/{self.job_name}")

        # 1. 获取所有构建列表
        try:
            builds = self._get_all_builds()
        except Exception as e:
            raise PackageDownloadException(f"获取Jenkins构建列表失败: {e}")

        if not builds:
            raise PackageDownloadException("未找到任何构建记录")

        logger.info(f"获取到 {len(builds)} 个构建记录")

        # 2. 按构建号降序排列（最新的在前）
        builds.sort(key=lambda x: x['number'], reverse=True)

        # 3. 从最新构建开始查找
        searched_count = 0
        for build in builds[:self.max_builds_to_search]:
            build_number = build['number']
            searched_count += 1

            # 4. 获取该构建的产物列表
            try:
                artifacts = self._get_build_artifacts(build_number)
            except Exception as e:
                logger.warning(f"获取构建#{build_number}产物失败: {e}")
                continue

            # 5. 检查Build文件夹下是否有APK
            apk_artifact = self._find_apk_in_build_folder(artifacts)

            if apk_artifact:
                logger.info(f"找到APK: 构建#{build_number}, 文件: {apk_artifact['fileName']}")

                # 6. 构建下载URL
                download_url = (
                    f"{self.jenkins_url}/job/{self.job_name}/"
                    f"{build_number}/artifact/{apk_artifact['relativePath']}"
                )

                # 7. 解析版本信息
                version_info = self._parse_apk_filename(apk_artifact['fileName'])

                return PackageInfo(
                    url=download_url,
                    filename=apk_artifact['fileName'],
                    version=version_info['version'],
                    build_number=build_number,
                    size=apk_artifact.get('size', 0),
                    timestamp=build.get('timestamp', 0),
                    svn_revision=version_info['svn_revision'],
                    version_code=version_info['version_code'],
                    date=version_info['date']
                )

            logger.debug(f"构建#{build_number}的Build文件夹下没有APK文件")

        raise PackageDownloadException(
            f"在最近{searched_count}个构建中未找到APK文件"
        )

    def _get_all_builds(self) -> list:
        """
        获取所有构建列表

        Returns:
            list: 构建列表，每个元素包含 number, timestamp, result
        """
        url = f"{self.jenkins_url}/job/{self.job_name}/api/json?tree=builds[number,timestamp,result]"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json().get('builds', [])

    def _get_build_artifacts(self, build_number: int) -> list:
        """
        获取指定构建的产物列表

        Args:
            build_number: 构建号

        Returns:
            list: 产物列表
        """
        url = f"{self.jenkins_url}/job/{self.job_name}/{build_number}/api/json?tree=artifacts[*]"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json().get('artifacts', [])

    def _find_apk_in_build_folder(self, artifacts: list) -> Optional[dict]:
        """
        在Build文件夹下查找APK文件

        Args:
            artifacts: 产物列表

        Returns:
            APK产物信息，未找到返回None
        """
        for artifact in artifacts:
            relative_path = artifact.get('relativePath', '')
            filename = artifact.get('fileName', '')

            # 必须在Build文件夹下且是APK文件
            if relative_path.startswith('Build/') and filename.endswith('.apk'):
                return artifact

        return None

    def _parse_apk_filename(self, filename: str) -> dict:
        """
        解析APK文件名

        示例: P9_XProject_Android_20260327_99_SVN173687_dev_0.31.0_3100_SDK_NONE.apk

        Returns:
            {
                'version': '0.31.0',
                'build_number': 99,
                'svn_revision': 173687,
                'version_code': 3100,
                'date': '20260327'
            }
        """
        # 移除.apk后缀
        name = filename.replace('.apk', '')

        # 分割各部分
        parts = name.split('_')

        result = {
            'version': 'unknown',
            'build_number': 0,
            'svn_revision': 0,
            'version_code': 0,
            'date': ''
        }

        # 解析各字段
        for i, part in enumerate(parts):
            # 日期 (8位数字)
            if re.match(r'^\d{8}$', part):
                result['date'] = part
            # 构建号 (纯数字，较小)
            elif part.isdigit() and int(part) < 10000 and i > 2:
                if result['build_number'] == 0:
                    result['build_number'] = int(part)
            # SVN版本号 (以SVN开头)
            elif part.startswith('SVN'):
                svn_num = part.replace('SVN', '')
                if svn_num.isdigit():
                    result['svn_revision'] = int(svn_num)
            # 版本号 (x.x.x格式)
            elif re.match(r'^\d+\.\d+\.\d+$', part):
                result['version'] = part
            # 版本码 (纯数字，较大)
            elif part.isdigit() and int(part) >= 1000:
                result['version_code'] = int(part)

        return result

    def download_package(self, url: str, local_path: Optional[Path] = None) -> Path:
        """
        下载APK包

        Args:
            url: 下载链接
            local_path: 本地保存路径（可选，默认使用download_dir/filename）

        Returns:
            Path: 下载文件的本地路径

        Raises:
            PackageDownloadException: 下载失败
        """
        filename = url.split('/')[-1]
        if local_path is None:
            local_path = self.download_dir / filename

        logger.info(f"开始下载APK: {url}")
        logger.info(f"保存路径: {local_path}")

        for attempt in range(self.retry_count):
            try:
                # 流式下载，支持大文件
                # 处理超大超时值，超过 C timeval 限制时使用 None (无限制)
                # C timeval 最大约 2147 秒 (约 35 分钟)
                timeout = self.download_timeout
                if timeout is not None and timeout > 1800:  # 超过 30 分钟使用无限制
                    timeout = None
                response = requests.get(url, stream=True, timeout=timeout)
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            # 输出进度
                            if total_size > 0 and downloaded % (10 * 1024 * 1024) == 0:
                                progress = (downloaded / total_size) * 100
                                logger.info(f"下载进度: {progress:.1f}% ({downloaded}/{total_size})")

                logger.info(f"APK下载完成: {local_path}")
                return local_path

            except requests.RequestException as e:
                logger.warning(f"下载失败 (尝试 {attempt + 1}/{self.retry_count}): {e}")
                if attempt == self.retry_count - 1:
                    raise PackageDownloadException(f"APK下载失败: {e}")
                time.sleep(2)  # 重试前等待

        raise PackageDownloadException("APK下载失败")

    def compare_versions(self, local_build: int, remote_build: int) -> bool:
        """
        版本对比，判断是否需要更新

        Args:
            local_build: 本地已安装的构建号
            remote_build: 远程最新构建号

        Returns:
            bool: True 表示需要更新
        """
        return remote_build > local_build

    def get_local_build_number(self) -> int:
        """
        获取本地已下载的最新构建号

        通过扫描download_dir中的APK文件名来获取。

        Returns:
            int: 本地最新构建号，没有则返回0
        """
        if not self.download_dir.exists():
            return 0

        max_build = 0
        for apk_file in self.download_dir.glob('*.apk'):
            # 从文件名中提取构建号
            version_info = self._parse_apk_filename(apk_file.name)
            if version_info['build_number'] > max_build:
                max_build = version_info['build_number']

        return max_build

    def cleanup_old_packages(self, keep: int = 3):
        """
        清理旧版本APK

        Args:
            keep: 保留最近N个版本
        """
        if not self.download_dir.exists():
            return

        # 获取所有APK文件并按修改时间排序
        apk_files = list(self.download_dir.glob('*.apk'))
        apk_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        # 删除多余的文件
        if len(apk_files) > keep:
            for old_file in apk_files[keep:]:
                try:
                    old_file.unlink()
                    logger.info(f"删除旧版本APK: {old_file}")
                except Exception as e:
                    logger.warning(f"删除旧版本APK失败: {e}")

    def should_download(self, remote_build: int) -> bool:
        """
        判断是否需要下载新版本

        Args:
            remote_build: 远程构建号

        Returns:
            bool: True 表示需要下载
        """
        local_build = self.get_local_build_number()
        return self.compare_versions(local_build, remote_build)
