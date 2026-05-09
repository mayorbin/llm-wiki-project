# backend/tests/unit/test_database.py
"""
数据库初始化测试。
"""

import sqlite3
import pytest
from pathlib import Path
from app.storage.database import init_db, get_db, close_all_db
from app.config import reset_settings


@pytest.fixture(autouse=True)
def setup_teardown(monkeypatch, tmp_path):
    """每个测试使用独立的临时数据目录，测试后关闭所有连接。"""
    monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
    reset_settings()  # 确保新设置读取 monkeypatched 的环境变量
    close_all_db()    # 确保无残留连接
    yield
    close_all_db()


class TestInitDB:
    """数据库建表测试。"""

    def test_users库四张表创建(self):
        """users.db 应包含 users/projects/project_members/project_settings 四张表。"""
        conn = get_db("users")
        init_db(str(Path.cwd()))
        # 需要重新获取连接以看到新表
        conn = get_db("users")
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {r["name"] for r in tables}
        assert "users" in table_names
        assert "projects" in table_names
        assert "project_members" in table_names
        assert "project_settings" in table_names

    def test_tasks库表创建(self):
        """tasks.db 应包含 task_queue 表。"""
        conn = get_db("tasks")
        init_db(str(Path.cwd()))
        conn = get_db("tasks")
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert any(r["name"] == "task_queue" for r in tables)

    def test_audit库表创建(self):
        """audit.db 应包含 audit_log 表及索引。"""
        conn = get_db("audit")
        init_db(str(Path.cwd()))
        conn = get_db("audit")
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert any(r["name"] == "audit_log" for r in tables)

    def test_幂等初始化(self):
        """多次调用 init_db 不应报错。"""
        init_db(str(Path.cwd()))
        init_db(str(Path.cwd()))  # 第二次不应抛异常

    def test_WAL模式启用(self):
        """数据库应启用 WAL journal 模式。"""
        init_db(str(Path.cwd()))
        conn = get_db("users")
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0].lower() == "wal"

    def test_外键约束启用(self):
        """外键约束应启用。"""
        init_db(str(Path.cwd()))
        conn = get_db("users")
        result = conn.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1

    def test_task_queue表索引存在(self):
        """task_queue 表应有 project_id+status 和 created_at 索引。"""
        init_db(str(Path.cwd()))
        conn = get_db("tasks")
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        names = [r["name"] for r in indexes]
        assert "idx_task_project" in names
        assert "idx_task_created" in names

    def test_audit_log表索引存在(self):
        """audit_log 表应有三个查询索引。"""
        init_db(str(Path.cwd()))
        conn = get_db("audit")
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        names = [r["name"] for r in indexes]
        assert "idx_audit_project_time" in names
        assert "idx_audit_user" in names
        assert "idx_audit_action" in names
