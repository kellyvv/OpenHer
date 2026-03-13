"""
Provider Registry — 按配置创建 provider 实例.

Public API:
    get_llm()       → BaseLLMProvider  (按 active_provider 创建)
    get_tts()       → BaseTTSProvider  (Phase 2)
    get_soulmem()   → BaseSoulMem      (Phase 3)
    get_evermemos() → Optional[...]    (Phase 3)
"""

from __future__ import annotations

import os
from typing import Optional

from .config import get_llm_provider_config, get_tts_provider_config
from .llm.base import BaseLLMProvider, OpenAICompatProvider
from .speech.tts.base import BaseTTSProvider


# ─────────────────────────────────────────────────────────────
# LLM Provider Registry
# ─────────────────────────────────────────────────────────────

# Map: provider name → class
_LLM_PROVIDERS: dict[str, type[BaseLLMProvider]] = {}


def _register_llm_providers():
    """Lazy-register all LLM provider classes."""
    if _LLM_PROVIDERS:
        return

    from .llm.dashscope import DashScopeLLMProvider
    from .llm.openai import OpenAILLMProvider
    from .llm.moonshot import MoonshotLLMProvider
    from .llm.ollama import OllamaLLMProvider
    from .llm.gemini import GeminiLLMProvider
    from .llm.claude import ClaudeLLMProvider

    _LLM_PROVIDERS.update({
        "dashscope": DashScopeLLMProvider,
        "openai": OpenAILLMProvider,
        "moonshot": MoonshotLLMProvider,
        "ollama": OllamaLLMProvider,
        "gemini": GeminiLLMProvider,
        "claude": ClaudeLLMProvider,
    })


def get_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> BaseLLMProvider:
    """
    Create an LLM provider instance.

    If arguments are not provided, they are resolved from config/api.yaml.
    This is the primary factory — LLMClient facade delegates here.

    Args:
        provider:    Provider name (dashscope/openai/moonshot/ollama/gemini).
                     Default: config active_provider.
        model:       Model name. Default: config model.
        api_key:     API key. Default: resolved from env var.
        base_url:    Base URL. Default: provider preset.
        temperature: Default: config temperature.
        max_tokens:  Default: config max_tokens.

    Returns:
        BaseLLMProvider instance ready for .chat() / .chat_stream().
    """
    _register_llm_providers()

    cfg = get_llm_provider_config()

    provider_name = provider or cfg["active_provider"]
    provider_cls = _LLM_PROVIDERS.get(provider_name)

    if provider_cls is None:
        raise ValueError(
            f"Unknown LLM provider: '{provider_name}'. "
            f"Available: {list(_LLM_PROVIDERS.keys())}"
        )

    # Resolve from provider presets in config
    preset = cfg["providers"].get(provider_name, {})

    resolved_model = model or cfg.get("model") or preset.get("default_model")
    resolved_temp = temperature if temperature is not None else cfg.get("temperature", 0.92)
    resolved_max = max_tokens if max_tokens is not None else cfg.get("max_tokens", 1024)

    # API key: explicit > env var from preset
    resolved_key = api_key
    if not resolved_key:
        key_env = preset.get("api_key_env", "")
        if key_env:
            resolved_key = os.getenv(key_env, "")

    # Base URL: explicit > preset
    resolved_url = base_url or preset.get("base_url")

    return provider_cls(
        model=resolved_model,
        api_key=resolved_key or None,
        base_url=resolved_url,
        temperature=resolved_temp,
        max_tokens=resolved_max,
    )


# ─────────────────────────────────────────────────────────────
# TTS Provider Registry
# ─────────────────────────────────────────────────────────────

_TTS_PROVIDERS: dict[str, type[BaseTTSProvider]] = {}


def _register_tts_providers():
    """Lazy-register all TTS provider classes."""
    if _TTS_PROVIDERS:
        return

    from .speech.tts.openai import OpenAITTSProvider
    from .speech.tts.dashscope import DashScopeTTSProvider
    from .speech.tts.minimax import MiniMaxTTSProvider

    _TTS_PROVIDERS.update({
        "openai": OpenAITTSProvider,
        "dashscope": DashScopeTTSProvider,
        "minimax": MiniMaxTTSProvider,
    })


def get_tts(
    provider: Optional[str] = None,
    cache_dir: Optional[str] = None,
    api_key: Optional[str] = None,
    minimax_model: Optional[str] = None,
) -> BaseTTSProvider:
    """
    Create a TTS provider instance.

    Args:
        provider:      Provider name (openai/dashscope/minimax).
        cache_dir:     Audio cache directory.
        api_key:       API key (for the active provider).
        minimax_model: MiniMax model name override.

    Returns:
        BaseTTSProvider instance ready for .synthesize().
    """
    _register_tts_providers()

    cfg = get_tts_provider_config()

    provider_name = provider or cfg["active_provider"]
    provider_cls = _TTS_PROVIDERS.get(provider_name)

    if provider_cls is None:
        raise ValueError(
            f"Unknown TTS provider: '{provider_name}'. "
            f"Available: {list(_TTS_PROVIDERS.keys())}"
        )

    # Build constructor kwargs
    resolved_cache = cache_dir or cfg.get("cache_dir", ".cache/tts")
    kwargs: dict = {"cache_dir": resolved_cache}

    # Resolve API key from provider's preset
    preset = cfg.get("providers", {}).get(provider_name, {})
    resolved_key = api_key
    if not resolved_key:
        key_env = preset.get("api_key_env", "")
        if key_env:
            resolved_key = os.getenv(key_env, "")
    if resolved_key:
        kwargs["api_key"] = resolved_key

    # MiniMax model
    if provider_name == "minimax":
        kwargs["model"] = minimax_model or preset.get("model", "speech-2.8-turbo")

    return provider_cls(**kwargs)


# ─────────────────────────────────────────────────────────────
# Image Provider Registry
# ─────────────────────────────────────────────────────────────

_IMAGE_PROVIDERS: dict[str, type] = {}


def _register_image_providers():
    """Lazy-register all Image provider classes."""
    if _IMAGE_PROVIDERS:
        return

    from .image.gemini import GeminiImageProvider
    _IMAGE_PROVIDERS["gemini"] = GeminiImageProvider


def get_image_gen(
    provider: Optional[str] = None,
    cache_dir: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> "BaseImageProvider":
    """
    Create an Image generation provider instance.

    Args:
        provider:   Provider name (gemini). Default: config active_provider.
        cache_dir:  Image cache directory.
        api_key:    API key.
        model:      Model name override.

    Returns:
        BaseImageProvider instance ready for .generate().
    """
    _register_image_providers()

    from .config import get_image_provider_config
    cfg = get_image_provider_config()

    provider_name = provider or cfg["active_provider"]
    provider_cls = _IMAGE_PROVIDERS.get(provider_name)

    if provider_cls is None:
        raise ValueError(
            f"Unknown Image provider: '{provider_name}'. "
            f"Available: {list(_IMAGE_PROVIDERS.keys())}"
        )

    resolved_cache = cache_dir or cfg.get("cache_dir", ".cache/image")
    kwargs: dict = {"cache_dir": resolved_cache}

    # Resolve API key
    preset = cfg.get("providers", {}).get(provider_name, {})
    resolved_key = api_key
    if not resolved_key:
        key_env = preset.get("api_key_env", "")
        if key_env:
            resolved_key = os.getenv(key_env, "")
    if resolved_key:
        kwargs["api_key"] = resolved_key

    # Model override
    if model or preset.get("model"):
        kwargs["model"] = model or preset.get("model")

    return provider_cls(**kwargs)
