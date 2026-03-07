"""
LLM Client — Multi-provider LLM abstraction using OpenAI-compatible API.

Supports: DashScope (Qwen), OpenAI (GPT), DeepSeek, Moonshot.
Uses AsyncOpenAI SDK for non-blocking I/O in FastAPI context.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from openai import AsyncOpenAI

# ──────────────────────────────────────────────────────────────
# Provider presets — loaded from config/api.yaml
# ──────────────────────────────────────────────────────────────

# Fallback presets (used if config/api.yaml is missing)
_FALLBACK_PROVIDERS: dict[str, dict] = {
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "default_model": "qwen-max",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "api_key_env": "",
        "default_model": "qwen3.5:9b",
        "no_key_required": True,
    },
}


def _get_providers() -> dict[str, dict]:
    """Load provider presets from config/api.yaml, falling back to hardcoded defaults."""
    try:
        from core.config.api_config import get_llm_config
        cfg = get_llm_config()
        providers = cfg.get("providers", {})
        if providers:
            return providers
    except Exception:
        pass
    return _FALLBACK_PROVIDERS


@dataclass
class ChatMessage:
    """A single chat message."""
    role: str       # system, user, assistant
    content: str


@dataclass
class ChatResponse:
    """Parsed LLM response."""
    content: str
    finish_reason: str = "stop"
    model: str = ""
    usage: Optional[dict] = None


class LLMClient:
    """
    Async LLM client for OpenHer.

    All methods are async to avoid blocking the FastAPI event loop.

    Usage:
        client = LLMClient(provider="dashscope", model="qwen-max")
        response = await client.chat([
            ChatMessage("system", "You are a companion..."),
            ChatMessage("user", "你好呀"),
        ])
        print(response.content)
    """

    def __init__(
        self,
        provider: str = "dashscope",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.92,
        max_tokens: int = 1024,
    ):
        preset = _get_providers().get(provider, {})

        self.provider = provider
        self.model = model or preset.get("default_model", "qwen-max")
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Resolve API key
        resolved_key = api_key or os.getenv(preset.get("api_key_env", ""), "")
        if not resolved_key:
            raise ValueError(
                f"API key not found for provider '{provider}'. "
                f"Set {preset.get('api_key_env', 'API_KEY')} in .env"
            )

        # Resolve base URL
        resolved_url = base_url or preset.get("base_url")

        self.client = AsyncOpenAI(
            api_key=resolved_key,
            base_url=resolved_url,
        )
        print(f"✓ LLM 客户端: {self.model} ({self.provider}) [async]")

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        """Send a chat request and get a response (async)."""
        api_messages = [{"role": m.role, "content": m.content} for m in messages]

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=api_messages,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )

        choice = response.choices[0]
        return ChatResponse(
            content=choice.message.content or "",
            finish_reason=choice.finish_reason or "stop",
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            } if response.usage else None,
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
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
