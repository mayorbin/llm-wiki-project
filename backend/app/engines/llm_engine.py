# backend/app/engines/llm_engine.py
"""
LLM 调用引擎——基于 litellm 的统一入口。

支持所有 OpenAI Chat Completions 兼容协议的模型：
  - DeepSeek v4 flash:  model="deepseek/deepseek-v4-flash"
  - GLM-47:             model="glm/glm-47"
  - vLLM / Ollama:      model="openai/<name>"

所有调用经过 call_llm() 统一方法，自动注入 api_base/api_key/temperature 等配置。
配置优先级：方法参数 > 项目设置 > 全局默认配置。
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional
from app.config import get_settings

logger = logging.getLogger(__name__)


def call_llm(
    prompt: str,
    system_prompt: str = "",
    model: Optional[str] = None,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: Optional[int] = None,
    task_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> str:
    """
    调用 LLM 的统一入口。

    Args:
        prompt: 用户提示词（必填）
        system_prompt: 系统提示词（可选，附加在 messages[0]）
        model: litellm 模型标识，默认使用全局配置
        api_base: API 地址，默认使用全局配置
        api_key: API 密钥，默认使用全局配置
        temperature: 温度参数（0.0-2.0）
        max_tokens: 最大输出 token 数
        timeout: 超时秒数
        task_id: 关联的摄入任务 ID（日志用）
        project_id: 关联的项目 ID（日志用）

    Returns:
        模型响应的纯文本内容。

    Raises:
        RuntimeError: litellm 未安装
        Exception: litellm API 调用失败
    """
    settings = get_settings()

    # 参数合并——显式参数优先，否则使用全局默认
    model = model or settings.llm_model
    api_base = api_base or settings.llm_api_base
    api_key = api_key or settings.llm_api_key
    temperature = temperature if temperature is not None else settings.llm_temperature
    max_tokens = max_tokens or settings.llm_max_tokens
    timeout = timeout or settings.llm_timeout

    try:
        import litellm
    except ImportError:
        raise RuntimeError("litellm 未安装，请执行: pip install litellm")

    t0 = time.time()

    # 构建消息列表
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    logger.info("LLM 调用开始",
        extra={
            "task_id": task_id, "project_id": project_id,
            "model": model, "prompt_len": len(prompt),
        })

    # 构建 litellm 参数
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "api_base": api_base,
        "api_key": api_key,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    if timeout:
        kwargs["timeout"] = timeout

    # 注入自定义 HTTP 头（如 GLM 需要的 X-Auth-Token）
    if settings.llm_extra_headers:
        kwargs["extra_headers"] = dict(settings.llm_extra_headers)

    try:
        response = litellm.completion(**kwargs)
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        logger.error("LLM 调用失败",
            extra={"task_id": task_id, "duration_ms": int(elapsed), "error": str(e)})
        raise

    elapsed = (time.time() - t0) * 1000
    content = response.choices[0].message.content

    logger.info("LLM 调用完成",
        extra={
            "task_id": task_id, "duration_ms": int(elapsed),
            "response_len": len(content) if content else 0,
        })

    return content or ""


def call_llm_with_retry(
    prompt: str,
    max_retries: Optional[int] = None,
    task_id: Optional[str] = None,
    **kwargs,
) -> str:
    """
    带自动重试的 LLM 调用。

    瞬时故障自动指数退避重试（5s → 15s → 45s → ...），
    重试耗尽后抛出最后捕获的异常。

    Args:
        prompt: 用户提示词
        max_retries: 最大重试次数，默认使用全局配置
        task_id: 关联任务 ID（日志用）
        **kwargs: 传递给 call_llm() 的其他参数

    Returns:
        模型响应的纯文本内容。

    Raises:
        重试耗尽后抛出最后一次失败的异常。
    """
    settings = get_settings()
    max_retries = max_retries if max_retries is not None else settings.llm_max_retries

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return call_llm(prompt=prompt, task_id=task_id, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = 5 * (3 ** attempt)  # 5s → 15s → 45s
                logger.warning(
                    f"LLM 调用第 {attempt + 1}/{max_retries} 次重试",
                    extra={"task_id": task_id, "delay_seconds": delay, "error": str(e)},
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"LLM 调用重试耗尽（{max_retries} 次全部失败）",
                    extra={"task_id": task_id, "final_error": str(e)},
                )

    raise last_error


def verify_llm_connection(settings=None) -> bool:
    """健康检查：发送极短请求验证 LLM 接口连通性。

    Returns:
        True 如果 LLM 正确回复 "OK"，否则 False。
    """
    if settings is None:
        settings = get_settings()
    try:
        result = call_llm(
            prompt="回复'OK'，只回复这两个字母，不要加任何其他内容。",
            max_tokens=5,
            timeout=10,
        )
        return "OK" in result
    except Exception:
        return False
