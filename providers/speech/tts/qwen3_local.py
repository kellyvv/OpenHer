"""Qwen3 TTS — 本地 Qwen3-TTS (voice design + clone)."""

from __future__ import annotations

import os
from typing import Optional

from .base import BaseTTSProvider, TTSResult


class Qwen3LocalTTSProvider(BaseTTSProvider):
    """Qwen3-TTS local (voice design, for persona creation)."""

    PROVIDER_NAME = "qwen3"

    def __init__(self, cache_dir: str, **kwargs):
        super().__init__(cache_dir=cache_dir, **kwargs)
        self._client = None

    @property
    def client(self):
        """Lazy-load Qwen3 local client."""
        if self._client is None:
            import sys
            # Qwen3 TTS client 位于项目根 tts/ 目录
            tts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
            tts_dir = os.path.abspath(tts_dir)
            if tts_dir not in sys.path:
                sys.path.insert(0, tts_dir)
            from tts.qwen3_tts import Qwen3TTSClient
            self._client = Qwen3TTSClient()
        return self._client

    async def synthesize(
        self,
        text: str,
        voice_preset: str = "default",
        voice_name: Optional[str] = None,
        emotion_instruction: Optional[str] = None,
        emotion: Optional[str] = None,
        speed: float = 1.0,
    ) -> TTSResult:
        """Synthesize using local Qwen3-TTS."""
        speaker = voice_name or "vivian"
        instruct = emotion_instruction or ""

        result = self.client.custom_voice(
            text=text,
            speaker=speaker,
            instruct=instruct,
        )

        audio_path = self._cache_path(f"qwen3:{speaker}:{instruct}:{text}", ext="wav")
        result.save(audio_path)

        return TTSResult(success=True, audio_path=audio_path)
