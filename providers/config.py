"""
Provider Config — 统一读 config/api.yaml.

单一入口加载所有 provider 配置。
保留对 providers.api_config 的向后兼容 — 内部委托。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:
    import yaml
    _YAML = True
except ImportError:
    _YAML = False


# ─────────────────────────────────────────────────────────────
# Internal state
# ─────────────────────────────────────────────────────────────

_config: Optional[dict] = None
_CONFIG_PATH = Path(__file__).parent / "api.yaml"


def _load() -> dict:
    """Load config/api.yaml once. Returns empty dict on error."""
    global _config
    if _config is not None:
        return _config

    if not _YAML:
        print("  [providers/config] ⚠ pyyaml not installed, using defaults")
        _config = {}
        return _config

    if not _CONFIG_PATH.exists():
        print(f"  [providers/config] ⚠ {_CONFIG_PATH} not found, using env vars only")
        _config = {}
        return _config

    try:
        _config = yaml.safe_load(_CONFIG_PATH.read_text()) or {}
    except Exception as e:
        print(f"  [providers/config] ⚠ parse error: {e}")
        _config = {}

    return _config


def reload():
    """Force reload of config (useful for testing)."""
    global _config
    _config = None
    return _load()


# ─────────────────────────────────────────────────────────────
# LLM Config
# ─────────────────────────────────────────────────────────────

def get_llm_provider_config() -> dict:
    """
    Get LLM provider configuration.

    Returns dict with keys:
        active_provider, temperature, max_tokens, providers
    """
    cfg = _load()
    llm = cfg.get("llm", {})

    # Support both "provider" (current) and "active_provider" (future admin panel)
    active = (
        os.getenv("DEFAULT_PROVIDER")
        or llm.get("provider")
        or llm.get("active_provider")
        or "dashscope"
    )
    providers = llm.get("providers", {})
    preset = providers.get(active, {})

    # Model: env var > yaml top-level > provider default_model > per-provider fallback
    _PROVIDER_DEFAULT_MODELS = {
        "dashscope": "qwen-max",
        "openai": "gpt-4o",
        "moonshot": "moonshot-v1-auto",
        "ollama": "qwen3.5:9b",
        "gemini": "gemini-3.1-flash-lite-preview",
    }
    model = (
        os.getenv("DEFAULT_MODEL")
        or llm.get("model")
        or preset.get("default_model")
        or _PROVIDER_DEFAULT_MODELS.get(active, "qwen-max")
    )

    return {
        "active_provider": active,
        "model": model,
        "temperature": llm.get("temperature", 0.92),
        "max_tokens": llm.get("max_tokens", 1024),
        "providers": providers,
    }


# ─────────────────────────────────────────────────────────────
# Speech Config (TTS)
# ─────────────────────────────────────────────────────────────

def get_tts_provider_config() -> dict:
    """
    Get TTS provider configuration.

    Returns dict with keys:
        active_provider, cache_dir, providers
    """
    cfg = _load()
    # 兼容旧 key "tts" 和新 key "speech"
    speech = cfg.get("speech", cfg.get("tts", {}))

    return {
        "active_provider": speech.get("provider", speech.get("active_provider", "dashscope")),
        "cache_dir": speech.get("cache_dir", ".cache/tts"),
        "providers": speech.get("providers", {}),
    }


# ─────────────────────────────────────────────────────────────
# Memory Config
# ─────────────────────────────────────────────────────────────

def get_memory_provider_config() -> dict:
    """
    Get Memory provider configuration.

    Returns dict with keys:
        soulmem: {db_path}
        evermemos: {enabled, base_url, api_key}
    """
    cfg = _load()
    mem = cfg.get("memory", {})

    # SoulMem (常驻)
    soulmem_cfg = mem.get("soulmem", {})
    soulmem = {
        "db_path": soulmem_cfg.get("db_path", ".data/memory.db"),
    }

    # EverMemOS (可选增强)
    ever_cfg = mem.get("evermemos", {})
    env_base_url = os.getenv("EVERMEMOS_BASE_URL", "")
    base_url = env_base_url or ever_cfg.get("base_url", "")
    api_key_env = ever_cfg.get("api_key_env", "EVERMEMOS_API_KEY")
    api_key = os.getenv(api_key_env, "") if api_key_env else ""

    enabled = ever_cfg.get("enabled", False)
    if env_base_url:
        enabled = True

    evermemos = {
        "enabled": enabled,
        "base_url": base_url,
        "api_key": api_key,
    }

    return {
        "soulmem": soulmem,
        "evermemos": evermemos,
    }


# ─────────────────────────────────────────────────────────────
# Image Config
# ─────────────────────────────────────────────────────────────

def get_image_provider_config() -> dict:
    """
    Get Image generation provider configuration.

    Returns dict with keys:
        active_provider, cache_dir, providers
    """
    cfg = _load()
    image = cfg.get("image", {})

    return {
        "active_provider": (
            image.get("provider")
            or image.get("active_provider")
            or "gemini"
        ),
        "cache_dir": image.get("cache_dir", ".cache/image"),
        "providers": image.get("providers", {}),
    }
