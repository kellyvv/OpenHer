"""DashScope TTS — Qwen3-TTS-Instruct via Realtime WebSocket API.

Uses qwen3-tts-instruct-flash-realtime model with instruction control
for natural language voice style/emotion guidance.

Protocol: wss://dashscope.aliyuncs.com/api-ws/v1/realtime
SDK:      dashscope.audio.qwen_tts_realtime.QwenTtsRealtime
"""

from __future__ import annotations

import asyncio
import base64
import os
import threading
import time
import wave
from typing import Optional

from .base import BaseTTSProvider, TTSResult


# Default voice → persona mapping (can be overridden per-persona)
DEFAULT_VOICE = "Cherry"  # 芊悦: 阳光积极、亲切自然小姐姐


class DashScopeTTSProvider(BaseTTSProvider):
    """DashScope Qwen3-TTS-Instruct (WebSocket Realtime API)."""

    PROVIDER_NAME = "dashscope"

    def __init__(
        self,
        cache_dir: str,
        api_key: Optional[str] = None,
        model: str = "qwen3-tts-instruct-flash-realtime",
        default_voice: str = DEFAULT_VOICE,
        **kwargs,
    ):
        super().__init__(cache_dir=cache_dir, **kwargs)
        self._api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self._model = model
        self._default_voice = default_voice

        # Set SDK-level API key
        if self._api_key:
            import dashscope
            dashscope.api_key = self._api_key

    async def synthesize(
        self,
        text: str,
        voice_preset: str = "default",
        voice_name: Optional[str] = None,
        emotion_instruction: Optional[str] = None,
        emotion: Optional[str] = None,
        speed: float = 1.0,
    ) -> TTSResult:
        """Synthesize using Qwen3-TTS-Instruct Realtime API.

        Args:
            text:                Text to synthesize.
            voice_name:          Qwen voice ID (Cherry/Serena/Chelsie/Momo/etc).
            emotion_instruction: Natural language instruction for voice control,
                                 e.g. "语速偏慢，音调温柔甜美，语气治愈温暖".
        """
        if not self._api_key:
            return TTSResult(success=False, error="DashScope API key not set")

        voice = voice_name or self._default_voice

        # Cache key includes voice + instructions + text
        cache_key = f"qwen-tts:{voice}:{emotion_instruction}:{text}"
        audio_path = self._cache_path(cache_key, ext="wav")

        if os.path.exists(audio_path):
            return TTSResult(success=True, audio_path=audio_path)

        # WebSocket synthesis is blocking — run in executor
        loop = asyncio.get_event_loop()
        start = time.time()
        result = await loop.run_in_executor(
            None,
            self._synthesize_sync,
            text, voice, emotion_instruction, audio_path,
        )
        result.latency_ms = (time.time() - start) * 1000
        return result

    def _synthesize_sync(
        self,
        text: str,
        voice: str,
        instructions: Optional[str],
        audio_path: str,
    ) -> TTSResult:
        """Synchronous WebSocket TTS — called via run_in_executor."""
        from dashscope.audio.qwen_tts_realtime import (
            AudioFormat,
            QwenTtsRealtime,
            QwenTtsRealtimeCallback,
        )

        audio_chunks: list[bytes] = []
        complete_event = threading.Event()
        error_holder: list[Optional[str]] = [None]

        class _Callback(QwenTtsRealtimeCallback):
            def on_open(self) -> None:
                pass

            def on_close(self, code, msg) -> None:
                pass

            def on_event(self, response: dict) -> None:
                try:
                    etype = response.get("type", "")
                    if etype == "response.audio.delta":
                        audio_chunks.append(base64.b64decode(response["delta"]))
                    elif etype == "session.finished":
                        complete_event.set()
                    elif etype == "error":
                        error_holder[0] = str(response.get("error", "Unknown"))
                        complete_event.set()
                except Exception as e:
                    error_holder[0] = str(e)
                    complete_event.set()

        try:
            tts = QwenTtsRealtime(
                model=self._model,
                callback=_Callback(),
                url="wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
            )
            tts.connect()

            # Configure session
            session_kwargs: dict = {
                "voice": voice,
                "response_format": AudioFormat.PCM_24000HZ_MONO_16BIT,
                "mode": "server_commit",
            }
            if instructions:
                session_kwargs["instructions"] = instructions
                session_kwargs["optimize_instructions"] = True

            tts.update_session(**session_kwargs)

            # Send text
            tts.append_text(text)
            time.sleep(0.1)  # brief delay per SDK examples
            tts.finish()

            # Wait for completion (30s timeout)
            complete_event.wait(timeout=30)

            if error_holder[0]:
                return TTSResult(success=False, error=error_holder[0])

            if not audio_chunks:
                return TTSResult(success=False, error="No audio data received")

            # Save PCM data as WAV (24kHz, mono, 16-bit)
            audio_data = b"".join(audio_chunks)
            with wave.open(audio_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(audio_data)

            print(f"  [tts] ✓ Qwen3-TTS: {len(audio_data)//1024}KB, voice={voice}")
            return TTSResult(success=True, audio_path=audio_path)

        except Exception as e:
            return TTSResult(success=False, error=str(e))
