# backend/tests/unit/test_config.py
"""
配置管理模块的单元测试。
"""

import os
import pytest
from pathlib import Path

# 确保每次测试前重置全局状态
from app.config import Settings, ConfigurationError, get_settings, reset_settings


@pytest.fixture(autouse=True)
def reset():
    """每个测试前重置全局配置状态。"""
    reset_settings()
    yield
    reset_settings()


class TestSettings:
    """测试 Settings 配置模型。"""

    def test_默认值(self):
        """未设置任何外部配置时，使用代码默认值。"""
        s = Settings()
        assert s.app_name == "LLM Wiki"
        assert s.port == 8000
        assert s.access_token_expire_hours == 24
        assert s.log_level == "INFO"
        assert s.llm_temperature == 0.3

    def test_环境变量覆盖(self, monkeypatch):
        """环境变量应覆盖默认值（LLM_WIKI_ 前缀）。"""
        monkeypatch.setenv("LLM_WIKI_PORT", "9999")
        monkeypatch.setenv("LLM_WIKI_LLM_MODEL", "glm/glm-47")
        monkeypatch.setenv("LLM_WIKI_LOG_LEVEL", "DEBUG")
        s = Settings()
        assert s.port == 9999
        assert s.llm_model == "glm/glm-47"
        assert s.log_level == "DEBUG"

    def test_必填项校验缺少secret_key(self):
        """缺少 secret_key 时校验应抛出异常。"""
        s = Settings(llm_api_key="sk-test-12345")
        with pytest.raises(ConfigurationError, match="SECRET_KEY"):
            s.validate_required()

    def test_必填项校验缺少api_key(self):
        """缺少 llm_api_key 时校验应抛出异常。"""
        s = Settings(secret_key="super-secret-32bytes-key")
        with pytest.raises(ConfigurationError, match="LLM_API_KEY"):
            s.validate_required()

    def test_必填项校验全部通过(self):
        """所有必填项齐全时校验不抛异常。"""
        s = Settings(llm_api_key="sk-test", secret_key="super-secret-32")
        s.validate_required()

    def test_cors_origins类型(self):
        """cors_origins 应为列表类型。"""
        s = Settings()
        assert isinstance(s.cors_origins, list)
        assert "*" in s.cors_origins

    def test_float字段类型(self):
        """temperature 应为 float 类型。"""
        s = Settings()
        assert isinstance(s.llm_temperature, float)
        assert 0.0 <= s.llm_temperature <= 2.0


class TestFromYAML:
    """测试 YAML 配置文件加载。"""

    def test_基本加载(self, tmp_path):
        """YAML 中 LLM 和服务配置应正确加载。"""
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(
            """
app_name: "测试知识库"
llm:
  model: "custom/model-v2"
  temperature: 0.5
service:
  port: 8080
        """,
            encoding="utf-8",
        )
        s = Settings.from_yaml(yaml_path)
        assert s.app_name == "测试知识库"
        assert s.llm_model == "custom/model-v2"
        assert s.llm_temperature == 0.5
        assert s.port == 8080

    def test_不存在的文件返回默认值(self, tmp_path):
        """YAML 文件不存在时不应崩溃。"""
        s = Settings.from_yaml(tmp_path / "nonexistent.yaml")
        assert s.port == 8000

    def test_空YAML返回默认值(self, tmp_path):
        """空 YAML 文件使用默认值。"""
        yaml_path = tmp_path / "empty.yaml"
        yaml_path.write_text("")
        s = Settings.from_yaml(yaml_path)
        assert s.app_name == "LLM Wiki"


class TestGetSettings:
    """测试全局 get_settings() 函数。"""

    def test_首次调用创建实例(self, monkeypatch, tmp_path):
        """首次调用 get_settings() 应创建全局配置单例。"""
        monkeypatch.chdir(tmp_path)
        s = get_settings()
        assert s is not None
        assert s.app_name == "LLM Wiki"

    def test_重复调用返回同一实例(self, monkeypatch, tmp_path):
        """连续调用应返回同一单例对象。"""
        monkeypatch.chdir(tmp_path)
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2


class TestStartupValidation:
    """启动时必填项校验场景。"""

    def test_所有必填项已设置则启动成功(self, monkeypatch):
        """设置了 LLM_API_KEY 和 SECRET_KEY 后 validate 不抛异常。"""
        s = Settings(llm_api_key="sk-xxx", secret_key="my-secret-32bytes!!")
        s.validate_required()

    def test_生产环境注意事项(self):
        """生产环境应使用强随机密钥。"""
        import secrets

        key = secrets.token_hex(32)
        s = Settings(llm_api_key="sk-xxx", secret_key=key)
        s.validate_required()
        assert len(key) == 64  # 32 bytes = 64 hex chars
