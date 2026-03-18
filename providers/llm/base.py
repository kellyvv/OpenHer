"""
BaseLLMProvider — LLM 统一接口 + OpenAI-compat 共用基类.

所有 LLM provider (dashscope, openai, moonshot, ollama, gemini) 继承
OpenAICompatProvider，差异仅在默认 base_url / api_key_env / model。

公共类型 ChatMessage, ChatResponse 定义在此，原模块 re-export。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from openai import AsyncOpenAI


# ─────────────────────────────────────────────────────────────
# Public Types (facade 兼容契约 — 原位置 re-export)
# ─────────────────────────────────────────────────────────────

@dataclass
class ChatMessage:
    """A single chat message."""
    role: str       # system, user, assistant, tool
    content: str
    tool_call_id: Optional[str] = None  # Required when role="tool"
    name: Optional[str] = None          # Tool name when role="tool"


@dataclass
class ChatResponse:
    """Parsed LLM response."""
    content: str
    finish_reason: str = "stop"
    model: str = ""
    usage: Optional[dict] = None
    tool_calls: Optional[list[dict]] = None  # [{name, arguments}]


# ─────────────────────────────────────────────────────────────
# Abstract Base
# ─────────────────────────────────────────────────────────────

class BaseLLMProvider(ABC):
    """LLM provider 统一接口."""

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> ChatResponse:
        """Send a chat request and get a response."""
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Stream a chat response, yielding content chunks."""
        ...
        # NOTE: 必须是 async generator (yield)，不能只是 return
        yield  # type: ignore  # make this a generator


# ─────────────────────────────────────────────────────────────
# OpenAI-Compatible 共用基类
# ─────────────────────────────────────────────────────────────

class OpenAICompatProvider(BaseLLMProvider):
    """
    OpenAI-compatible LLM provider 共用实现.

    DashScope, OpenAI, Moonshot 均使用 OpenAI SDK，
    只是 base_url / api_key / model 不同。
    """

    # 子类覆盖这些默认值
    PROVIDER_NAME: str = "openai_compat"
    DEFAULT_BASE_URL: str = ""
    DEFAULT_API_KEY_ENV: str = ""
    DEFAULT_MODEL: str = ""
    NO_KEY_REQUIRED: bool = False
    # Models that require max_completion_tokens instead of max_tokens
    MAX_COMPLETION_TOKENS_MODELS: tuple = ()

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.92,
        max_tokens: int = 1024,
    ):
        self.model = model or self.DEFAULT_MODEL
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.provider_name = self.PROVIDER_NAME

        # Resolve API key
        resolved_key = api_key
        if not resolved_key and self.DEFAULT_API_KEY_ENV:
            resolved_key = os.getenv(self.DEFAULT_API_KEY_ENV, "")
        if not resolved_key and not self.NO_KEY_REQUIRED:
            raise ValueError(
                f"API key not found for provider '{self.PROVIDER_NAME}'. "
                f"Set {self.DEFAULT_API_KEY_ENV} in .env"
            )
        # Ollama 等不需要 key 的 provider，给一个 placeholder
        if not resolved_key:
            resolved_key = "no-key-required"

        # Resolve base URL
        resolved_url = base_url or self.DEFAULT_BASE_URL

        self.client = AsyncOpenAI(
            api_key=resolved_key,
            base_url=resolved_url,
        )

    def _token_param_name(self) -> str:
        """Return the API parameter name for max tokens.

        Newer OpenAI models (o1, o3, gpt-5.x) require 'max_completion_tokens'
        instead of 'max_tokens'. Subclasses set MAX_COMPLETION_TOKENS_MODELS
        with model prefix patterns to opt in.
        """
        for prefix in self.MAX_COMPLETION_TOKENS_MODELS:
            if self.model.startswith(prefix):
                return "max_completion_tokens"
        return "max_tokens"

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> ChatResponse:
        """Send a chat request and get a response (async)."""
        api_messages = []
        for m in messages:
            msg = {"role": m.role, "content": m.content}
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            if m.name:
                msg["name"] = m.name
            api_messages.append(msg)

        token_param = self._token_param_name()
        kwargs = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature if temperature is not None else self.temperature,
            token_param: max_tokens if max_tokens is not None else self.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice

        response = await self.client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        tc = choice.message.tool_calls
        parsed_tc = [{"id": t.id, "name": t.function.name, "arguments": t.function.arguments}
                     for t in tc] if tc else None
        return ChatResponse(
            content=choice.message.content or "",
            finish_reason=choice.finish_reason or "stop",
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            } if response.usage else None,
            tool_calls=parsed_tc,
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Stream a chat response, yielding content chunks (async)."""
        api_messages = [{"role": m.role, "content": m.content} for m in messages]

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=api_messages,
            temperature=temperature if temperature is not None else self.temperature,
            stream=True,
            **{self._token_param_name(): max_tokens if max_tokens is not None else self.max_tokens},
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
