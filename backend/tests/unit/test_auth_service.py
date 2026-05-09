# backend/tests/unit/test_auth_service.py
"""认证服务测试。"""

import pytest
from app.config import reset_settings
from app.storage.database import init_db, close_all_db
from app.services.auth_service import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, decode_token, register_user, login,
    refresh_access_token,
)


@pytest.fixture(autouse=True)
def setup_teardown(monkeypatch, tmp_path):
    """每个测试使用独立的临时数据和密钥。"""
    monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_WIKI_SECRET_KEY", "test-secret-key-must-be-32-chars!!")
    monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test-dummy")
    reset_settings()
    close_all_db()
    init_db(str(tmp_path))
    yield
    close_all_db()


class TestPassword:
    def test_哈希后可正确验证(self):
        """bcrypt 哈希后应能正确验证原始密码。"""
        h = hash_password("my-password")
        assert verify_password("my-password", h)

    def test_错误密码验证失败(self):
        """错误密码必须验证失败。"""
        h = hash_password("correct")
        assert not verify_password("wrong", h)

    def test_相同明文产生不同哈希(self):
        """相同密码两次哈希结果应不同（salt 随机）。"""
        assert hash_password("same") != hash_password("same")


class TestJWT:
    def test_access_token含用户信息(self):
        """access_token 负载应包含 user_id + username + role。"""
        token = create_access_token("u_1", "张三", "editor")
        payload = decode_token(token)
        assert payload["sub"] == "u_1"
        assert payload["username"] == "张三"
        assert payload["role"] == "editor"
        assert payload["type"] == "access"

    def test_refresh_token不含用户名(self):
        """refresh_token 不应包含用户名等敏感信息。"""
        token = create_refresh_token("u_1")
        payload = decode_token(token)
        assert payload["type"] == "refresh"
        assert "username" not in payload
        assert "role" not in payload

    def test_无效token返回None(self):
        """无效的 token 解码应返回 None。"""
        assert decode_token("not.a.valid.token") is None
        assert decode_token("") is None


class TestLogin:
    def test_注册后登录成功(self):
        """注册新用户后应立即可以登录。"""
        register_user("alice", "secure123", "Alice")
        token = login("alice", "secure123")
        assert token.access_token
        assert token.refresh_token
        assert token.token_type == "bearer"
        assert token.expires_in == 24 * 3600

    def test_错误密码登录失败(self):
        """错误密码应抛出 ValueError。"""
        register_user("bob", "correct-pw")
        with pytest.raises(ValueError, match="用户名或密码错误"):
            login("bob", "wrong-pw")

    def test_不存在用户登录失败(self):
        """不存在的用户登录应抛出 ValueError。"""
        with pytest.raises(ValueError, match="用户名或密码错误"):
            login("nonexistent", "any")

    def test_Token刷新成功(self):
        """refresh_token 应能换取新 Token 对。"""
        register_user("carol", "pw123")
        original = login("carol", "pw123")
        new_tokens = refresh_access_token(original.refresh_token)
        assert new_tokens.access_token
        assert new_tokens.refresh_token != original.refresh_token  # 滚动刷新

    def test_重复使用同一refresh_token失败(self):
        """每次刷新后旧 refresh_token 应即时失效（黑名单）。"""
        register_user("dave", "pw123")
        original = login("dave", "pw123")
        refresh_access_token(original.refresh_token)  # 第一次成功
        with pytest.raises(ValueError, match="Token 已被撤销"):
            refresh_access_token(original.refresh_token)  # 第二次失败
