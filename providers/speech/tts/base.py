"""
BaseTTSProvider — TTS 统一接口 + 公共类型.

公共类型 TTSProvider (enum), TTSResult (dataclass) 定义在此，
原模块 core/media/tts_engine.py re-export。
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ─────────────────────────────────────────────────────────────
# Public Types (facade 兼容契约)
# ─────────────────────────────────────────────────────────────

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
    audio_path: Optional[str] = None
    audio_bytes: Optional[bytes] = None
    provider: str = ""
    latency_ms: float = 0
    error: Optional[str] = None


# ─────────────────────────────────────────────────────────────
# Abstract Base
# ─────────────────────────────────────────────────────────────

class BaseTTSProvider(ABC):
    """TTS provider 统一接口."""

    PROVIDER_NAME: str = ""

    def __init__(self, cache_dir: str, **kwargs):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice_preset: str = "default",
        voice_name: Optional[str] = None,
        emotion_instruction: Optional[str] = None,
        emotion: Optional[str] = None,
        speed: float = 1.0,
    ) -> TTSResult:
        """Synthesize text to speech."""
        ...

    def _cache_path(self, key_parts: str, ext: str = "mp3") -> str:
        """Generate cache file path from key parts."""
        cache_key = hashlib.md5(key_parts.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{cache_key}.{ext}")
