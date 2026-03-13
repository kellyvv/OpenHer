"""
TTSEngine — Facade over core.providers.speech.tts.

保留原有 API 面 (TTSEngine, TTSProvider, TTSResult)，
内部委托到 providers.speech.tts 的具体 provider 实现。

所有上层调用 (main.py) 无需改动。
"""

from __future__ import annotations

import os
import tempfile
import time
from typing import Optional

# ─────────────────────────────────────────────────────────────
# Re-export public types (facade 兼容契约)
# ─────────────────────────────────────────────────────────────
from providers.speech.tts.base import TTSProvider, TTSResult  # noqa: F401

# Re-export constants (used by external code)
from providers.speech.tts.minimax import EMOTION_TO_MINIMAX  # noqa: F401


class TTSEngine:
    """
    Multi-provider TTS engine — façade.

    Delegates to core.providers.speech.tts 的具体 provider。
    Constructor 签名与原版完全一致，所有调用方无需改动。

    Usage:
        # 基础用法 (DashScope CosyVoice)
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
        provider: TTSProvider = TTSProvider.DASHSCOPE,
        cache_dir: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        dashscope_api_key: Optional[str] = None,
        minimax_api_key: Optional[str] = None,
        minimax_model: str = "speech-2.8-turbo",
    ):
        self.provider = provider
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), "openher_tts")
        os.makedirs(self.cache_dir, exist_ok=True)

        # Store per-provider API keys for provider-override calls
        self._api_keys = {
            "openai": openai_api_key or os.getenv("OPENAI_API_KEY", ""),
            "dashscope": dashscope_api_key or os.getenv("DASHSCOPE_API_KEY", ""),
            "minimax": minimax_api_key or os.getenv("MINIMAX_API_KEY", ""),
        }
        self._minimax_model = minimax_model

        # Lazy-loaded provider instances (one per provider name)
        self._providers: dict[str, object] = {}

        print(f"✓ TTS 引擎: {self.provider.value}, 缓存: {self.cache_dir}")

    def _get_provider(self, provider_name: str):
        """Get or create provider instance for given name."""
        if provider_name not in self._providers:
            from providers.registry import get_tts

            kwargs = {
                "provider": provider_name,
                "cache_dir": self.cache_dir,
            }
            api_key = self._api_keys.get(provider_name, "")
            if api_key:
                kwargs["api_key"] = api_key
            if provider_name == "minimax":
                kwargs["minimax_model"] = self._minimax_model

            self._providers[provider_name] = get_tts(**kwargs)

        return self._providers[provider_name]

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
            voice_preset: Voice preset name
            voice_name: Voice ID (MiniMax voice_id, OpenAI voice, etc.)
            emotion_instruction: Free-text instruction (OpenAI/DashScope)
            emotion: Emotion state name → auto-mapped to MiniMax emotion
            speed: Speech speed (0.5~2.0, MiniMax only)
            provider: Override the default provider for this call
        """
        actual_provider = provider or self.provider
        provider_name = actual_provider.value
        start_time = time.time()

        try:
            impl = self._get_provider(provider_name)
            result = await impl.synthesize(
                text=text,
                voice_preset=voice_preset,
                voice_name=voice_name,
                emotion_instruction=emotion_instruction,
                emotion=emotion,
                speed=speed,
            )
            result.provider = provider_name
            result.latency_ms = (time.time() - start_time) * 1000
            return result

        except Exception as e:
            return TTSResult(
                success=False,
                error=str(e),
                provider=provider_name,
                latency_ms=(time.time() - start_time) * 1000,
            )

    # ──────────────────────────────────────────────────────────
    # Utility (保持原有 API)
    # ──────────────────────────────────────────────────────────

    def get_available_voices(self) -> dict[str, str]:
        """List available voice presets."""
        return {"default": "default"}

    @staticmethod
    def get_available_emotions() -> list[str]:
        """List all emotion states supported."""
        return list(EMOTION_TO_MINIMAX.keys())
