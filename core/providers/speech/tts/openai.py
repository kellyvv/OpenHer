"""OpenAI TTS — OpenAI gpt-4o-mini-tts provider."""

from __future__ import annotations

import os
from typing import Optional

from .base import BaseTTSProvider, TTSResult


class OpenAITTSProvider(BaseTTSProvider):
    """OpenAI TTS (gpt-4o-mini-tts, high quality, paid)."""

    PROVIDER_NAME = "openai"

    def __init__(self, cache_dir: str, api_key: Optional[str] = None, **kwargs):
        super().__init__(cache_dir=cache_dir, **kwargs)
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")

    async def synthesize(
        self,
        text: str,
        voice_preset: str = "default",
        voice_name: Optional[str] = None,
        emotion_instruction: Optional[str] = None,
        emotion: Optional[str] = None,
        speed: float = 1.0,
    ) -> TTSResult:
        """Synthesize using OpenAI TTS API."""
        if not self._api_key:
            return TTSResult(success=False, error="OpenAI API key not set")

        from openai import OpenAI

        client = OpenAI(api_key=self._api_key)
        voice = voice_name or "alloy"

        params = {
            "model": "gpt-4o-mini-tts",
            "voice": voice,
            "input": text,
        }
        if emotion_instruction:
            params["instructions"] = emotion_instruction

        response = client.audio.speech.create(**params)

        audio_path = self._cache_path(f"openai:{voice}:{text}:{emotion_instruction}", ext="mp3")
        response.stream_to_file(audio_path)

        return TTSResult(success=True, audio_path=audio_path)
