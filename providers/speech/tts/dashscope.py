"""DashScope TTS — CosyVoice / Qwen3-TTS API provider."""

from __future__ import annotations

import os
from typing import Optional

from .base import BaseTTSProvider, TTSResult


class DashScopeTTSProvider(BaseTTSProvider):
    """DashScope CosyVoice / Qwen3-TTS (via API)."""

    PROVIDER_NAME = "dashscope"

    def __init__(self, cache_dir: str, api_key: Optional[str] = None, **kwargs):
        super().__init__(cache_dir=cache_dir, **kwargs)
        self._api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")

    async def synthesize(
        self,
        text: str,
        voice_preset: str = "default",
        voice_name: Optional[str] = None,
        emotion_instruction: Optional[str] = None,
        emotion: Optional[str] = None,
        speed: float = 1.0,
    ) -> TTSResult:
        """Synthesize using DashScope CosyVoice API."""
        if not self._api_key:
            return TTSResult(success=False, error="DashScope API key not set")

        import httpx

        voice = voice_name or "longxiaochun"
        synth_text = f"[{emotion_instruction}]{text}" if emotion_instruction else text

        audio_path = self._cache_path(f"dashscope:{voice}:{synth_text}", ext="mp3")

        if os.path.exists(audio_path):
            return TTSResult(success=True, audio_path=audio_path)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2audio/text-synthesis",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",
                },
                json={
                    "model": "cosyvoice-v2",
                    "input": {"text": synth_text},
                    "parameters": {"voice": voice, "format": "mp3"},
                },
            )

            if response.status_code == 200:
                data = response.json()
                audio_url = data.get("output", {}).get("audio", "")
                if audio_url:
                    audio_resp = await client.get(audio_url)
                    with open(audio_path, "wb") as f:
                        f.write(audio_resp.content)
                    return TTSResult(success=True, audio_path=audio_path)

            return TTSResult(success=False, error=f"DashScope API error: {response.status_code}")
