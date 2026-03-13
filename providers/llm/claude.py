"""Anthropic Claude — 原生 anthropic SDK LLM provider."""

from __future__ import annotations

import os
from typing import AsyncIterator, Optional

from .base import BaseLLMProvider, ChatMessage, ChatResponse


class ClaudeLLMProvider(BaseLLMProvider):
    """
    Anthropic Claude LLM provider.

    使用 anthropic SDK（非 OpenAI-compatible），
    支持 chat / chat_stream。
    """

    PROVIDER_NAME = "claude"
    DEFAULT_API_KEY_ENV = "ANTHROPIC_API_KEY"
    DEFAULT_MODEL = "claude-haiku-4-5-20251001"

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,   # unused, kept for interface compat
        temperature: float = 0.92,
        max_tokens: int = 1024,
    ):
        self.model = model or self.DEFAULT_MODEL
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.provider_name = self.PROVIDER_NAME

        # Resolve API key
        resolved_key = api_key or os.getenv(self.DEFAULT_API_KEY_ENV, "")
        if not resolved_key:
            raise ValueError(
                f"API key not found for provider '{self.PROVIDER_NAME}'. "
                f"Set {self.DEFAULT_API_KEY_ENV} in .env"
            )

        import anthropic
        self.client = anthropic.Anthropic(api_key=resolved_key)
        self._async_client = anthropic.AsyncAnthropic(api_key=resolved_key)

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> ChatResponse:
        """Send a chat request and get a response (async)."""
        system_text, api_messages = self._split_messages(messages)

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "messages": api_messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if system_text:
            kwargs["system"] = system_text

        response = await self._async_client.messages.create(**kwargs)

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.input_tokens or 0,
                "completion_tokens": response.usage.output_tokens or 0,
                "total_tokens": (response.usage.input_tokens or 0)
                + (response.usage.output_tokens or 0),
            }

        return ChatResponse(
            content=text,
            finish_reason=response.stop_reason or "stop",
            model=self.model,
            usage=usage,
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Stream a chat response, yielding content chunks (async)."""
        system_text, api_messages = self._split_messages(messages)

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "messages": api_messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if system_text:
            kwargs["system"] = system_text

        async with self._async_client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    # ── internal helpers ──

    def _split_messages(
        self, messages: list[ChatMessage]
    ) -> tuple[str, list[dict]]:
        """Split ChatMessages into system text + API messages list."""
        system_parts = []
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
            else:
                api_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        return "\n".join(system_parts), api_messages
