"""MiniMax TTS — speech-2.8-turbo (clone + 7 emotions, production)."""

from __future__ import annotations

import os
from typing import Optional

from .base import BaseTTSProvider, TTSResult


# EmotionState → MiniMax emotion 映射
EMOTION_TO_MINIMAX = {
    "neutral": "neutral",
    "happy": "happy",
    "excited": "happy",      # MiniMax 没有 excited，映射到 happy
    "caring": "neutral",     # 关心用中性+语速放慢
    "sad": "sad",
    "worried": "sad",        # 担心映射到 sad
    "angry": "angry",
    "shy": "neutral",        # 害羞用中性
    "playful": "happy",      # 调皮映射到 happy
    "fearful": "fearful",
    "disgusted": "disgusted",
    "surprised": "surprised",
}


class MiniMaxTTSProvider(BaseTTSProvider):
    """MiniMax speech-2.8 (clone + emotion, recommended for production)."""

    PROVIDER_NAME = "minimax"

    def __init__(
        self,
        cache_dir: str,
        api_key: Optional[str] = None,
        model: str = "speech-2.8-turbo",
        **kwargs,
    ):
        super().__init__(cache_dir=cache_dir, **kwargs)
        self._api_key = api_key or os.getenv("MINIMAX_API_KEY", "")
        self._model = model
        self._client = None

    @property
    def client(self):
        """Lazy-load MiniMax client."""
        if self._client is None:
            import sys
            # MiniMax TTS client 位于项目根 tts/ 目录
            tts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
            tts_dir = os.path.abspath(tts_dir)
            if tts_dir not in sys.path:
                sys.path.insert(0, tts_dir)
            from tts.minimax_tts import MiniMaxTTSClient
            self._client = MiniMaxTTSClient(
                api_key=self._api_key,
                model=self._model,
            )
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
        """Synthesize using MiniMax speech-2.8 API."""
        if not self._api_key:
            return TTSResult(success=False, error="MiniMax API key not set")

        vid = voice_name or "Chinese_female_anchor_3"

        # Map emotion state to MiniMax emotion
        minimax_emotion = None
        if emotion:
            minimax_emotion = EMOTION_TO_MINIMAX.get(emotion, "neutral")

        result = self.client.speak(
            text=text,
            voice_id=vid,
            emotion=minimax_emotion,
            speed=speed,
        )

        # Save to cache
        ext = result.format or "mp3"
        audio_path = self._cache_path(f"minimax:{vid}:{minimax_emotion}:{speed}:{text}", ext=ext)

        with open(audio_path, "wb") as f:
            f.write(result.audio_bytes)

        return TTSResult(success=True, audio_path=audio_path)
