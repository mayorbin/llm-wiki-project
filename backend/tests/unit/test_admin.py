# backend/tests/unit/test_admin.py
"""Admin API 辅助测试（auth_service 底层逻辑）。"""
import pytest
from app.config import reset_settings
from app.storage.database import init_db, close_all_db, get_db
from app.services.auth_service import register_user


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_WIKI_SECRET_KEY", "test-key-32chars-long-enough!!")
    monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test")
    reset_settings()
    close_all_db()
    init_db(str(tmp_path))
    yield
    close_all_db()


def test_创建管理员用户():
    user = register_user("admin_user", "admin123", "管理员")
    assert user.username == "admin_user"


def test_用户注册后数据库有记录():
    register_user("testuser", "pw12345")
    db = get_db("users")
    row = db.execute("SELECT * FROM users WHERE username = ?", ("testuser",)).fetchone()
    assert row is not None
    assert row["username"] == "testuser"
