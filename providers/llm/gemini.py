"""Google Gemini — 原生 google-genai SDK LLM provider."""

from __future__ import annotations

import os
from typing import AsyncIterator, Optional

from .base import BaseLLMProvider, ChatMessage, ChatResponse


class GeminiLLMProvider(BaseLLMProvider):
    """
    Google Gemini LLM provider.

    使用 google-genai SDK（非 OpenAI-compatible），
    支持 chat / chat_stream，以及 thinking_config。
    """

    PROVIDER_NAME = "gemini"
    DEFAULT_API_KEY_ENV = "GEMINI_API_KEY"
    DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"

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

        from google import genai
        self._genai = genai
        self._types = genai.types
        self.client = genai.Client(api_key=resolved_key)

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> ChatResponse:
        """Send a chat request and get a response (async)."""
        contents = self._build_contents(messages)
        config = self._build_config(temperature, max_tokens)

        # google-genai is sync by default; use async wrapper
        import asyncio
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model,
            contents=contents,
            config=config,
        )

        text = response.text or ""
        usage = None
        if response.usage_metadata:
            usage = {
                "prompt_tokens": response.usage_metadata.prompt_token_count or 0,
                "completion_tokens": response.usage_metadata.candidates_token_count or 0,
                "total_tokens": response.usage_metadata.total_token_count or 0,
            }

        return ChatResponse(
            content=text,
            finish_reason="stop",
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
        contents = self._build_contents(messages)
        config = self._build_config(temperature, max_tokens)

        import asyncio

        # Run the sync streaming generator in a thread
        def _sync_stream():
            chunks = []
            for chunk in self.client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config,
            ):
                if chunk.text:
                    chunks.append(chunk.text)
            return chunks

        chunks = await asyncio.to_thread(_sync_stream)
        for text in chunks:
            yield text

    # ── internal helpers ──

    def _build_contents(self, messages: list[ChatMessage]) -> list:
        """Convert ChatMessage list to google-genai Contents."""
        types = self._types
        contents = []
        system_text = ""

        for msg in messages:
            if msg.role == "system":
                # Gemini handles system instructions via config, collect them
                system_text += msg.content + "\n"
            else:
                role = "user" if msg.role == "user" else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg.content)],
                    )
                )

        # If there's a system message, prepend as user context
        # (Gemini API uses system_instruction in config, handled in _build_config)
        self._pending_system = system_text.strip()
        return contents

    def _build_config(
        self,
        temperature: Optional[float],
        max_tokens: Optional[int],
    ):
        """Build GenerateContentConfig."""
        types = self._types
        kwargs = {
            "temperature": temperature if temperature is not None else self.temperature,
            "max_output_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }

        # Pass system instruction if collected
        if hasattr(self, "_pending_system") and self._pending_system:
            kwargs["system_instruction"] = self._pending_system
            self._pending_system = ""

        return types.GenerateContentConfig(**kwargs)
