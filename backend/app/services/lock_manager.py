"""
并发锁管理器——基于 filelock 的跨进程文件锁。

四级锁作用域：
  - project: 项目级写锁（摄入 + 图谱构建互斥）
  - page:    Wiki 页面读写锁（多读单写）
  - dir:     目录操作锁（移动/删除时持有）
  - index:   索引文件写锁（index/log/overview 写入互斥）

锁文件结构：
  data/.locks/
    project/{project_id}.lock
    page/{project_id}/{page_path}.lock
    dir/{project_id}/{dir_path}.lock
    index/{project_id}.lock

每个锁文件附带 .info 文件记录持有者（pid + 时间），用于死锁检测。
"""

import json
import os
import time
import logging
from pathlib import Path
from typing import Optional
from filelock import FileLock, Timeout as FileLockTimeout

logger = logging.getLogger(__name__)


class LockBusyError(Exception):
    """锁被其他进程持有且未超时。"""
    pass


class LockManager:
    """跨进程文件锁管理器。

    所有 worker 共享 data/.locks/ 目录，filelock 基于内核 fcntl，
    进程崩溃时内核自动释放锁。
    """

    def __init__(self, data_dir: Path):
        self.lock_dir = data_dir / ".locks"
        self.lock_dir.mkdir(parents=True, exist_ok=True)

    # ── 路径计算 ──

    def _lock_path(self, scope: str, project_id: str, identifier: str = "") -> Path:
        """计算锁文件路径。

        project/index 锁：{scope}/{project_id}.lock
        page/dir 锁：    {scope}/{project_id}/{identifier}.lock
        """
        if scope in ("project", "index"):
            subdir = self.lock_dir / scope
            subdir.mkdir(parents=True, exist_ok=True)
            return subdir / f"{project_id}.lock"
        else:
            subdir = self.lock_dir / scope / project_id
            subdir.mkdir(parents=True, exist_ok=True)
            safe_id = identifier.replace("/", "_").replace("\\", "_")
            return subdir / f"{safe_id}.lock"

    # ── 锁获取/释放 ──

    def acquire(
        self, scope: str, project_id: str, identifier: str = "",
        timeout: float = 30,
    ) -> FileLock:
        """获取指定作用域的锁。

        Args:
            scope: 锁作用域（project/page/dir/index）
            project_id: 项目 ID（命名空间）
            identifier: 额外标识（page 路径等）
            timeout: 超时秒数

        Returns:
            FileLock 对象（用于 release）

        Raises:
            LockBusyError: 超时且死锁检测未通过
        """
        lock_path = self._lock_path(scope, project_id, identifier)
        lock = FileLock(str(lock_path), timeout=timeout)

        try:
            lock.acquire(timeout=timeout)
        except FileLockTimeout:
            # 死锁检测
            if self._is_stale_lock(lock_path):
                logger.warning(f"检测到残留锁，强制释放: {lock_path}")
                self._break_stale_lock(lock_path)
                lock.acquire(timeout=5)
            else:
                raise LockBusyError(
                    f"锁 {scope}/{project_id}/{identifier} 被其他进程持有，等待 {timeout}s 超时"
                ) from None

        self._write_owner_info(lock_path)
        return lock

    def release(self, lock: FileLock):
        """释放锁。"""
        try:
            lock.release()
        except Exception:
            pass  # 锁可能已被自动释放

    # ── 便捷方法 ──

    def acquire_project_write(self, project_id: str, timeout: float = 300) -> FileLock:
        """获取项目级写锁——摄入和图谱构建时持有。"""
        return self.acquire("project", project_id, timeout=timeout)

    def acquire_page_lock(self, project_id: str, page_path: str, timeout: float = 10) -> FileLock:
        """获取 Wiki 页面读写锁。"""
        return self.acquire("page", project_id, page_path, timeout=timeout)

    def acquire_directory_lock(self, project_id: str, dir_path: str, timeout: float = 5) -> FileLock:
        """获取目录操作锁——移动/删除时持有。"""
        return self.acquire("dir", project_id, dir_path, timeout=timeout)

    def acquire_index_lock(self, project_id: str, timeout: float = 10) -> FileLock:
        """获取索引文件写锁——更新 index/log/overview 时持有。"""
        return self.acquire("index", project_id, timeout=timeout)

    # ── 死锁检测 ──

    def _write_owner_info(self, lock_path: Path):
        """写入锁持有者信息（用于死锁诊断）。"""
        info_path = lock_path.with_suffix(".info")
        info_path.write_text(json.dumps({
            "pid": os.getpid(),
            "acquired_at": time.time(),
            "hostname": os.uname().nodename if hasattr(os, "uname") else "unknown",
        }), encoding="utf-8")

    def _is_stale_lock(self, lock_path: Path, max_age_seconds: float = 3600) -> bool:
        """判断锁是否已被死进程持有。"""
        info_path = lock_path.with_suffix(".info")
        if not info_path.exists():
            return False

        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return True  # 损坏的 info 视为残留

        pid = info.get("pid", -1)
        acquired = info.get("acquired_at", 0)

        # 检测 1: 进程是否存在
        try:
            os.kill(pid, 0)  # 信号 0 不杀进程，仅检查存在性
            process_alive = True
        except (OSError, ProcessLookupError):
            process_alive = False

        # 检测 2: 持有时间是否过长
        held_too_long = (time.time() - acquired) > max_age_seconds

        return not process_alive or held_too_long

    def _break_stale_lock(self, lock_path: Path):
        """强制释放残留锁。"""
        lock_path.unlink(missing_ok=True)
        info_path = lock_path.with_suffix(".info")
        if info_path.exists():
            info_path.unlink()

    # ── 清理 ──

    def cleanup_stale_locks(self, max_age_seconds: float = 3600) -> int:
        """清理所有残留锁文件和 info 文件。返回清理数量。"""
        cleaned = 0
        for info_file in self.lock_dir.rglob("*.info"):
            try:
                info = json.loads(info_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                info_file.unlink(missing_ok=True)
                info_file.with_suffix(".lock").unlink(missing_ok=True)
                cleaned += 1
                continue

            pid = info.get("pid", -1)
            try:
                os.kill(pid, 0)
                alive = True
            except (OSError, ProcessLookupError):
                alive = False

            age = time.time() - info.get("acquired_at", 0)
            if not alive or age > max_age_seconds:
                info_file.unlink(missing_ok=True)
                lock_file = info_file.with_suffix(".lock")
                lock_file.unlink(missing_ok=True)
                cleaned += 1
                logger.info(f"清理残留锁: {lock_file.name} (pid={pid}, age={age:.0f}s)")

        return cleaned
