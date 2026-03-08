"""
LLM Client — Facade over core.providers.llm.

保留原有 API 面 (LLMClient, ChatMessage, ChatResponse)，
内部委托到 providers.registry.get_llm() 创建的 provider。

所有上层调用 (chat_agent, critic, main.py) 无需改动。
"""

from __future__ import annotations

from typing import AsyncIterator, Optional

# ─────────────────────────────────────────────────────────────
# Re-export public types (facade 兼容契约)
# ─────────────────────────────────────────────────────────────
from providers.llm.base import ChatMessage, ChatResponse  # noqa: F401


class LLMClient:
    """
    Async LLM client for OpenHer.

    Thin facade — 委托到 core.providers.llm 的具体 provider 实现。
    Constructor 签名不变，所有调用方无需改动。

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
        from providers.registry import get_llm

        self.provider = provider
        self._impl = get_llm(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        # Expose model name for observability  (main.py prints it)
        self.model = self._impl.model
        print(f"✓ LLM 客户端: {self.model} ({self.provider}) [async]")

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        """Send a chat request and get a response (async)."""
        return await self._impl.chat(messages, temperature, max_tokens)

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Stream a chat response, yielding content chunks (async)."""
        async for chunk in self._impl.chat_stream(messages, temperature, max_tokens):
            yield chunk
