# backend/tests/unit/test_llm_engine.py
"""LLM 引擎测试——使用 Mock 避免真实 API 调用。"""

import sys
import pytest
from unittest.mock import MagicMock, patch, ANY
from app.config import reset_settings
from app.engines.llm_engine import call_llm, call_llm_with_retry, verify_llm_connection


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    """每个测试前设置必要的环境变量。"""
    monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test-mock-key")
    monkeypatch.setenv("LLM_WIKI_SECRET_KEY", "test-secret-key-32chars-long!!")
    reset_settings()
    # 清理之前测试可能残留的 sys.modules mock
    sys.modules.pop("litellm", None)


class TestCallLLM:
    """call_llm 基础测试。"""

    @pytest.fixture(autouse=True)
    def inject_mock_litellm(self):
        """将 mock litellm 注入 sys.modules，使函数内的 import litellm 获取到 mock。"""
        mock_litellm = MagicMock()
        sys.modules["litellm"] = mock_litellm
        self.mock_litellm = mock_litellm
        yield
        sys.modules.pop("litellm", None)

    def test_正常调用返回文本内容(self):
        """模拟 litellm 正常响应，验证返回内容。"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "这是 LLM 生成的回答"
        self.mock_litellm.completion.return_value = mock_response

        result = call_llm(prompt="什么是 Transformer？")
        assert result == "这是 LLM 生成的回答"
        self.mock_litellm.completion.assert_called_once()

    def test_参数正确传递给litellm(self):
        """验证 model/temperature/max_tokens/api_base 等参数正确传递。"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "OK"
        self.mock_litellm.completion.return_value = mock_response

        call_llm(
            prompt="Hello", model="glm/glm-47", api_base="http://glm:8000/v1",
            temperature=0.5, max_tokens=4096, timeout=60,
        )

        call_kwargs = self.mock_litellm.completion.call_args[1]
        assert call_kwargs["model"] == "glm/glm-47"
        assert call_kwargs["api_base"] == "http://glm:8000/v1"
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 4096
        assert call_kwargs["timeout"] == 60

    def test_system_prompt注入(self):
        """system_prompt 应作为第一个消息出现。"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "OK"
        self.mock_litellm.completion.return_value = mock_response

        call_llm(prompt="问题", system_prompt="你是一个知识库助手")

        messages = self.mock_litellm.completion.call_args[1]["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "你是一个知识库助手"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "问题"

    def test_LLM返回空内容(self):
        """LLM 返回空字符串时不应报错。"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        self.mock_litellm.completion.return_value = mock_response

        result = call_llm(prompt="test")
        assert result == ""

    def test_API调用失败向上抛出(self):
        """litellm 抛出的异常应向上传递。"""
        self.mock_litellm.completion.side_effect = ConnectionError("无法连接到 API")

        with pytest.raises(ConnectionError, match="无法连接到 API"):
            call_llm(prompt="test")


class TestCallLLMWithRetry:
    """带重试的 LLM 调用测试。"""

    @pytest.fixture(autouse=True)
    def inject_mocks(self):
        """注入 mock litellm 和 time.sleep。"""
        mock_litellm = MagicMock()
        sys.modules["litellm"] = mock_litellm
        self.mock_litellm = mock_litellm
        yield
        sys.modules.pop("litellm", None)

    @patch("app.engines.llm_engine.time.sleep")
    def test_首次成功不重试(self, mock_sleep):
        """首次调用成功时不应触发重试。"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "OK"
        self.mock_litellm.completion.return_value = mock_response

        result = call_llm_with_retry(prompt="test", max_retries=3)
        assert result == "OK"
        mock_sleep.assert_not_called()
        assert self.mock_litellm.completion.call_count == 1

    @patch("app.engines.llm_engine.time.sleep")
    def test_两次失败后第三次成功(self, mock_sleep):
        """前两次失败、第三次成功时，应正确重试并返回结果。"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "第三次终于成功了"
        self.mock_litellm.completion.side_effect = [
            TimeoutError("超时"),
            ConnectionError("网络错误"),
            mock_response,
        ]

        result = call_llm_with_retry(prompt="test", max_retries=3)
        assert result == "第三次终于成功了"
        assert self.mock_litellm.completion.call_count == 3
        assert mock_sleep.call_count == 2  # 前两次失败后各 sleep 一次

    @patch("app.engines.llm_engine.time.sleep")
    def test_全部重试耗尽后抛出异常(self, mock_sleep):
        """所有重试都失败后应抛出最后一次的异常。"""
        self.mock_litellm.completion.side_effect = TimeoutError("持续超时")

        with pytest.raises(TimeoutError, match="持续超时"):
            call_llm_with_retry(prompt="test", max_retries=2)
        assert self.mock_litellm.completion.call_count == 3  # 1 initial + 2 retries


class TestVerifyLLMConnection:
    """LLM 连通性验证测试。"""

    @pytest.fixture(autouse=True)
    def inject_mock_litellm(self):
        """将 mock litellm 注入 sys.modules。"""
        mock_litellm = MagicMock()
        sys.modules["litellm"] = mock_litellm
        self.mock_litellm = mock_litellm
        yield
        sys.modules.pop("litellm", None)

    def test_LLM返回OK验证通过(self):
        """LLM 回复包含 OK 时验证通过。"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "OK"
        self.mock_litellm.completion.return_value = mock_response

        assert verify_llm_connection() is True

    def test_LLM返回错误内容验证失败(self):
        """LLM 回复不包含 OK 时验证失败。"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Something went wrong"
        self.mock_litellm.completion.return_value = mock_response

        assert verify_llm_connection() is False

    def test_LLM不可达验证失败(self):
        """API 调用异常时验证失败（不抛出）。"""
        self.mock_litellm.completion.side_effect = ConnectionError("无法连接")
        assert verify_llm_connection() is False
