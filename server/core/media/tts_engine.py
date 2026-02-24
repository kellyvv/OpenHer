"""
TTSEngine — Multi-provider text-to-speech with emotion control.

Supports:
  - Edge TTS (free, decent quality, many voices)
  - OpenAI TTS (gpt-4o-mini-tts, high quality)
  - DashScope / Qwen3-TTS (via API, emotion control)
  - MiniMax speech-2.8 (clone + 7 emotions, recommended for production)
  - Qwen3-TTS local (voice design + clone, for persona creation)

Design inspired by OpenClaw's multi-provider TTS architecture.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import edge_tts


class TTSProvider(str, Enum):
    EDGE = "edge"             # Free, built-in, decent Chinese
    OPENAI = "openai"         # High quality, paid
    DASHSCOPE = "dashscope"   # Qwen3-TTS via DashScope API
    MINIMAX = "minimax"       # MiniMax speech-2.8 (clone + emotion)
    QWEN3_LOCAL = "qwen3"     # Qwen3-TTS local (voice design)


@dataclass
class TTSResult:
    """Result of a TTS synthesis."""
    success: bool
    audio_path: Optional[str] = None   # Path to generated audio file
    audio_bytes: Optional[bytes] = None
    provider: str = ""
    latency_ms: float = 0
    error: Optional[str] = None


# ──────────────────────────────────────────────────────────────
# Edge TTS voice presets for different persona vibes
# ──────────────────────────────────────────────────────────────

EDGE_VOICE_PRESETS = {
    "sweet_female": "zh-CN-XiaoyiNeural",       # 甜美女声
    "gentle_female": "zh-CN-XiaoxiaoNeural",     # 温柔女声
    "lively_female": "zh-CN-XiaohanNeural",      # 活泼女声
    "cool_female": "zh-CN-XiaomengNeural",       # 酷飒女声
    "default": "zh-CN-XiaoyiNeural",
}

# ──────────────────────────────────────────────────────────────
# EmotionState → MiniMax emotion 映射
# ──────────────────────────────────────────────────────────────

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


class TTSEngine:
    """
    Multi-provider TTS engine with persona voice binding.

    Usage:
        # 基础用法 (Edge TTS, 免费)
        engine = TTSEngine()
        result = await engine.synthesize(text="你好呀！")

        # MiniMax 用法 (需要 API Key, 支持克隆+情绪)
        engine = TTSEngine(
            provider=TTSProvider.MINIMAX,
            minimax_api_key="your-key",
        )
        result = await engine.synthesize(
            text="今天心情真好！",
            voice_name="your_cloned_voice_id",
            emotion="happy",
        )
    """

    def __init__(
        self,
        provider: TTSProvider = TTSProvider.EDGE,
        cache_dir: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        dashscope_api_key: Optional[str] = None,
        minimax_api_key: Optional[str] = None,
        minimax_model: str = "speech-2.8-turbo",
    ):
        self.provider = provider
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), "openher_tts")
        os.makedirs(self.cache_dir, exist_ok=True)

        self._openai_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self._dashscope_key = dashscope_api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self._minimax_key = minimax_api_key or os.getenv("MINIMAX_API_KEY", "")
        self._minimax_model = minimax_model

        # Lazy-loaded clients
        self._minimax_client = None
        self._qwen3_client = None

        print(f"✓ TTS 引擎: {self.provider.value}, 缓存: {self.cache_dir}")

    @property
    def minimax_client(self):
        """Lazy-load MiniMax client"""
        if self._minimax_client is None:
            import sys
            tts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..")
            if tts_dir not in sys.path:
                sys.path.insert(0, tts_dir)
            from tts.minimax_tts import MiniMaxTTSClient
            self._minimax_client = MiniMaxTTSClient(
                api_key=self._minimax_key,
                model=self._minimax_model,
            )
        return self._minimax_client

    @property
    def qwen3_client(self):
        """Lazy-load Qwen3 local client"""
        if self._qwen3_client is None:
            import sys
            tts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..")
            if tts_dir not in sys.path:
                sys.path.insert(0, tts_dir)
            from tts.qwen3_tts import Qwen3TTSClient
            self._qwen3_client = Qwen3TTSClient()
        return self._qwen3_client

    async def synthesize(
        self,
        text: str,
        voice_preset: str = "default",
        voice_name: Optional[str] = None,
        emotion_instruction: Optional[str] = None,
        emotion: Optional[str] = None,
        speed: float = 1.0,
        provider: Optional[TTSProvider] = None,
    ) -> TTSResult:
        """
        Synthesize text to speech.

        Args:
            text: Text to speak
            voice_preset: Preset name from EDGE_VOICE_PRESETS
            voice_name: Voice ID (MiniMax voice_id, OpenAI voice, etc.)
            emotion_instruction: Free-text instruction (OpenAI/DashScope)
            emotion: Emotion state name → auto-mapped to MiniMax emotion
            speed: Speech speed (0.5~2.0, MiniMax only)
            provider: Override the default provider for this call
        """
        actual_provider = provider or self.provider
        start_time = time.time()

        # Map emotion state to MiniMax emotion if using MiniMax
        minimax_emotion = None
        if emotion:
            minimax_emotion = EMOTION_TO_MINIMAX.get(emotion, "neutral")

        try:
            if actual_provider == TTSProvider.EDGE:
                result = await self._synthesize_edge(text, voice_preset, voice_name)
            elif actual_provider == TTSProvider.OPENAI:
                result = await self._synthesize_openai(text, voice_name, emotion_instruction)
            elif actual_provider == TTSProvider.DASHSCOPE:
                result = await self._synthesize_dashscope(text, voice_name, emotion_instruction)
            elif actual_provider == TTSProvider.MINIMAX:
                result = await self._synthesize_minimax(
                    text, voice_name, minimax_emotion, speed,
                )
            elif actual_provider == TTSProvider.QWEN3_LOCAL:
                result = await self._synthesize_qwen3_local(
                    text, voice_name, emotion_instruction,
                )
            else:
                return TTSResult(success=False, error=f"Unknown provider: {actual_provider}")

            result.provider = actual_provider.value
            result.latency_ms = (time.time() - start_time) * 1000
            return result

        except Exception as e:
            return TTSResult(
                success=False,
                error=str(e),
                provider=actual_provider.value,
                latency_ms=(time.time() - start_time) * 1000,
            )

    # ──────────────────────────────────────────────────────────
    # MiniMax speech-2.8 (recommended for production)
    # ──────────────────────────────────────────────────────────

    async def _synthesize_minimax(
        self,
        text: str,
        voice_id: Optional[str] = None,
        emotion: Optional[str] = None,
        speed: float = 1.0,
    ) -> TTSResult:
        """Synthesize using MiniMax speech-2.8 API (clone + emotion)."""
        if not self._minimax_key:
            return TTSResult(success=False, error="MiniMax API key not set")

        vid = voice_id or "Chinese_female_anchor_3"
        result = self.minimax_client.speak(
            text=text,
            voice_id=vid,
            emotion=emotion,
            speed=speed,
        )

        # Save to cache
        ext = result.format or "mp3"
        cache_key = hashlib.md5(
            f"minimax:{vid}:{emotion}:{speed}:{text}".encode()
        ).hexdigest()
        audio_path = os.path.join(self.cache_dir, f"{cache_key}.{ext}")

        with open(audio_path, "wb") as f:
            f.write(result.audio_bytes)

        return TTSResult(success=True, audio_path=audio_path)

    # ──────────────────────────────────────────────────────────
    # Qwen3-TTS local (for voice design during persona creation)
    # ──────────────────────────────────────────────────────────

    async def _synthesize_qwen3_local(
        self,
        text: str,
        speaker: Optional[str] = None,
        instruct: Optional[str] = None,
    ) -> TTSResult:
        """Synthesize using local Qwen3-TTS (CustomVoice with built-in speakers)."""
        result = self.qwen3_client.custom_voice(
            text=text,
            speaker=speaker or "vivian",
            instruct=instruct or "",
        )

        cache_key = hashlib.md5(
            f"qwen3:{speaker}:{instruct}:{text}".encode()
        ).hexdigest()
        audio_path = os.path.join(self.cache_dir, f"{cache_key}.wav")
        result.save(audio_path)

        return TTSResult(success=True, audio_path=audio_path)

    # ──────────────────────────────────────────────────────────
    # Edge TTS (free fallback)
    # ──────────────────────────────────────────────────────────

    async def _synthesize_edge(
        self,
        text: str,
        voice_preset: str = "default",
        voice_name: Optional[str] = None,
    ) -> TTSResult:
        """Synthesize using Edge TTS (free, no API key needed)."""
        voice = voice_name or EDGE_VOICE_PRESETS.get(voice_preset, EDGE_VOICE_PRESETS["default"])

        cache_key = hashlib.md5(f"{voice}:{text}".encode()).hexdigest()
        audio_path = os.path.join(self.cache_dir, f"{cache_key}.mp3")

        if os.path.exists(audio_path):
            return TTSResult(success=True, audio_path=audio_path)

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(audio_path)

        return TTSResult(success=True, audio_path=audio_path)

    # ──────────────────────────────────────────────────────────
    # OpenAI TTS
    # ──────────────────────────────────────────────────────────

    async def _synthesize_openai(
        self,
        text: str,
        voice_name: Optional[str] = None,
        emotion_instruction: Optional[str] = None,
    ) -> TTSResult:
        """Synthesize using OpenAI TTS API."""
        if not self._openai_key:
            return TTSResult(success=False, error="OpenAI API key not set")

        from openai import OpenAI

        client = OpenAI(api_key=self._openai_key)
        voice = voice_name or "alloy"

        params = {
            "model": "gpt-4o-mini-tts",
            "voice": voice,
            "input": text,
        }
        if emotion_instruction:
            params["instructions"] = emotion_instruction

        response = client.audio.speech.create(**params)

        cache_key = hashlib.md5(f"openai:{voice}:{text}:{emotion_instruction}".encode()).hexdigest()
        audio_path = os.path.join(self.cache_dir, f"{cache_key}.mp3")
        response.stream_to_file(audio_path)

        return TTSResult(success=True, audio_path=audio_path)

    # ──────────────────────────────────────────────────────────
    # DashScope (Qwen3-TTS API / CosyVoice)
    # ──────────────────────────────────────────────────────────

    async def _synthesize_dashscope(
        self,
        text: str,
        voice_name: Optional[str] = None,
        emotion_instruction: Optional[str] = None,
    ) -> TTSResult:
        """Synthesize using DashScope CosyVoice / Qwen3-TTS API."""
        if not self._dashscope_key:
            return TTSResult(success=False, error="DashScope API key not set")

        import httpx

        voice = voice_name or "longxiaochun"
        synth_text = f"[{emotion_instruction}]{text}" if emotion_instruction else text

        cache_key = hashlib.md5(f"dashscope:{voice}:{synth_text}".encode()).hexdigest()
        audio_path = os.path.join(self.cache_dir, f"{cache_key}.mp3")

        if os.path.exists(audio_path):
            return TTSResult(success=True, audio_path=audio_path)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2audio/text-synthesis",
                headers={
                    "Authorization": f"Bearer {self._dashscope_key}",
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

    # ──────────────────────────────────────────────────────────
    # Utility
    # ──────────────────────────────────────────────────────────

    def get_available_voices(self) -> dict[str, str]:
        """List available voice presets."""
        return dict(EDGE_VOICE_PRESETS)

    @staticmethod
    def get_available_emotions() -> list[str]:
        """List all emotion states supported."""
        return list(EMOTION_TO_MINIMAX.keys())
