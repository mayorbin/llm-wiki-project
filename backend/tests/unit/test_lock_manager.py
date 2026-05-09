"""并发锁管理器测试。"""

import os
import json
import time
import pytest
from pathlib import Path
from app.services.lock_manager import LockManager, LockBusyError


@pytest.fixture
def lm(tmp_path):
    """创建使用临时目录的 LockManager。"""
    return LockManager(tmp_path)


class TestLockPath:
    """锁文件路径计算。"""

    def test_project锁路径(self, lm):
        path = lm._lock_path("project", "proj-abc")
        assert path.parent.name == "project"
        assert path.name == "proj-abc.lock"

    def test_page锁含project_id命名空间(self, lm):
        """page 锁路径应包含 project_id 分子目录（防止跨项目冲突）。"""
        path = lm._lock_path("page", "proj-abc", "sources/test.md")
        assert "proj-abc" in str(path)
        assert "sources_test.md.lock" == path.name

    def test_dir锁路径(self, lm):
        path = lm._lock_path("dir", "proj-xyz", "论文/2025")
        assert "proj-xyz" in str(path)
        assert path.name.endswith(".lock")

    def test_index锁路径(self, lm):
        path = lm._lock_path("index", "proj-abc")
        assert path.name == "proj-abc.lock"


class TestAcquireRelease:
    """锁的获取和释放。"""

    def test_获取并释放project锁(self, lm):
        lock = lm.acquire_project_write("test-proj", timeout=5)
        assert lock.is_locked
        lm.release(lock)

    def test_获取并释放page锁(self, lm):
        lock = lm.acquire_page_lock("proj", "sources/doc.md")
        assert lock.is_locked
        lm.release(lock)

    def test_同一锁不能重复获取(self, lm):
        """同一进程不能同时持有同一把锁两次。"""
        lock1 = lm.acquire_project_write("p1", timeout=2)
        with pytest.raises((LockBusyError, Exception)):
            lm.acquire_project_write("p1", timeout=1)
        lm.release(lock1)

    def test_不同项目的锁独立(self, lm):
        """不同项目的同类型锁应互不影响。"""
        lock1 = lm.acquire_project_write("p1", timeout=5)
        lock2 = lm.acquire_project_write("p2", timeout=5)
        assert lock1.is_locked
        assert lock2.is_locked
        lm.release(lock1)
        lm.release(lock2)

    def test_owner_info写入(self, lm):
        """获取锁后应写入 .info 文件。"""
        lock = lm.acquire_project_write("info-test", timeout=5)
        info_path = lm._lock_path("project", "info-test").with_suffix(".info")
        assert info_path.exists()
        info = json.loads(info_path.read_text(encoding="utf-8"))
        assert info["pid"] == os.getpid()
        lm.release(lock)


class TestDeadlockDetection:
    """死锁检测。"""

    def test_非残留锁不误判(self, lm):
        """当前进程持有的锁不应被判定为残留。"""
        lock = lm.acquire_project_write("alive-test", timeout=5)
        lock_path = lm._lock_path("project", "alive-test")
        assert lm._is_stale_lock(lock_path) is False
        lm.release(lock)

    def test_无info文件不是残留(self, lm):
        """没有 .info 文件的锁不应判定为残留。"""
        lock_path = lm._lock_path("project", "no-info")
        assert lm._is_stale_lock(lock_path) is False

    def test_不存在的PID判定残留(self, lm):
        """记录的 PID 不存在时应判定为残留锁。"""
        lock = lm.acquire_project_write("will-be-stale", timeout=5)
        lock_path = lm._lock_path("project", "will-be-stale")
        info_path = lock_path.with_suffix(".info")
        # 手动篡改 PID 为一个不存在的值
        info = json.loads(info_path.read_text(encoding="utf-8"))
        info["pid"] = 999999  # 不存在的 PID
        info_path.write_text(json.dumps(info), encoding="utf-8")
        lm.release(lock)

        # 现在 .info 指向一个不存在的进程
        assert lm._is_stale_lock(lock_path) is True

    def test_break_stale_lock清理文件(self, lm):
        """强制释放应删除 .lock 和 .info 文件。"""
        lock_path = lm._lock_path("project", "to-break")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.touch()
        info_path = lock_path.with_suffix(".info")
        info_path.write_text(json.dumps({"pid": 999999, "acquired_at": 0}), encoding="utf-8")

        lm._break_stale_lock(lock_path)
        assert not lock_path.exists()
        assert not info_path.exists()


class TestCleanup:
    """残留锁清理。"""

    def test_清理死进程残留(self, lm):
        """创建假的残留锁然后清理。"""
        # 创建假锁和 info 文件
        lock_path = lm._lock_path("project", "stale-proj")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.touch()
        info = {"pid": 999999, "acquired_at": time.time() - 7200}  # 2 小时前
        lock_path.with_suffix(".info").write_text(json.dumps(info), encoding="utf-8")

        cleaned = lm.cleanup_stale_locks(max_age_seconds=3600)
        assert cleaned >= 1
        assert not lock_path.exists()
