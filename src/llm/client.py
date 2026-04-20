"""LLM 客户端封装。

对 openai.OpenAI 做一层薄封装：
- 从全局 config 自动读取 API Key / Base URL / Model，支持覆盖
- 增加超时与简单重试（只对网络/限流类错误重试，不对模型业务错误重试）
- 暴露单一的 chat() 方法，同时支持普通对话与 function calling
"""

from __future__ import annotations

import time
from typing import Any

from openai import APIConnectionError, APITimeoutError, RateLimitError
from openai import OpenAI
from openai.types.chat import ChatCompletionMessage

from src.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


# 只对这些瞬时错误重试，其它错误（鉴权、参数等）立即抛出
_RETRIABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
)


class LLMClient:
    """LLM 客户端。

    通过 chat() 方法调用底层 chat.completions.create，
    返回 openai 原生的 ChatCompletionMessage 对象（含 content / tool_calls 等字段）。
    """

    def __init__(
        self,
        model: str = LLM_MODEL,
        api_key: str = LLM_API_KEY,
        base_url: str = LLM_BASE_URL,
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise ValueError(
                "LLM_API_KEY is not configured. Please set it in your .env file."
            )
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        tool_choice: str | dict | None = None,
    ) -> ChatCompletionMessage:
        """发起一次 chat completion 调用。

        Args:
            messages: OpenAI 格式的消息列表（含 system/user/assistant/tool 等角色）
            tools: OpenAI Function Calling schema 列表；为 None 时不开启工具调用
            temperature: 采样温度，默认 0.2 让工具调用更稳定
            tool_choice: 可选，控制是否强制调用工具（"auto" / "none" / {"type": "function", ...}）

        Returns:
            ChatCompletionMessage 对象。注意：返回的是 message 而非整个 completion，
            因为本项目里只关心 choices[0].message。
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice

        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.chat.completions.create(**payload)
                return response.choices[0].message
            except _RETRIABLE_EXCEPTIONS as e:
                last_err = e
                if attempt >= self.max_retries:
                    break
                # 指数退避：1s, 2s, 4s...
                time.sleep(2 ** attempt)
            except Exception:
                # 非瞬时错误直接抛出（鉴权失败、参数错误、模型不存在等）
                raise

        raise RuntimeError(
            f"LLM call failed after {self.max_retries + 1} attempts: {last_err}"
        )
