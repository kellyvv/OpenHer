"""Edge TTS — 免费 TTS provider (edge_tts 库)."""

from __future__ import annotations

import os
from typing import Optional

import edge_tts

from .base import BaseTTSProvider, TTSResult


# Edge TTS voice presets for different persona vibes
EDGE_VOICE_PRESETS = {
    "sweet_female": "zh-CN-XiaoyiNeural",       # 甜美女声
    "gentle_female": "zh-CN-XiaoxiaoNeural",     # 温柔女声
    "lively_female": "zh-CN-XiaohanNeural",      # 活泼女声
    "cool_female": "zh-CN-XiaomengNeural",       # 酷飒女声
    "default": "zh-CN-XiaoyiNeural",
}


class EdgeTTSProvider(BaseTTSProvider):
    """Edge TTS (free, no API key needed)."""

    PROVIDER_NAME = "edge"

    async def synthesize(
        self,
        text: str,
        voice_preset: str = "default",
        voice_name: Optional[str] = None,
        emotion_instruction: Optional[str] = None,
        emotion: Optional[str] = None,
        speed: float = 1.0,
    ) -> TTSResult:
        """Synthesize using Edge TTS."""
        voice = voice_name or EDGE_VOICE_PRESETS.get(voice_preset, EDGE_VOICE_PRESETS["default"])

        audio_path = self._cache_path(f"{voice}:{text}", ext="mp3")

        if os.path.exists(audio_path):
            return TTSResult(success=True, audio_path=audio_path)

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(audio_path)

        return TTSResult(success=True, audio_path=audio_path)
