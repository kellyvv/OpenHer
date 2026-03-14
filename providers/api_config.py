"""
Unified API Configuration Loader.

Single source of truth for all external API settings.
Reads config/api.yaml and merges with environment variable overrides.

Usage:
    from providers.api_config import get_llm_config, get_tts_config, get_memory_config

    llm = get_llm_config()
    # → {"provider": "dashscope", "model": "qwen-max", "api_key": "sk-...",
    #    "base_url": "https://...", "temperature": 0.92, "max_tokens": 1024,
    #    "providers": {...}}

    tts = get_tts_config()
    #    "api_keys": {"openai": "...", "dashscope": "...", "minimax": "..."}}

    mem = get_memory_config()
    # → {"enabled": True, "base_url": "http://localhost:1995/api/v1", "api_key": ""}
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
_CONFIG_PATH = Path(__file__).parent.parent / "providers" / "api.yaml"


def _load() -> dict:
    """Load config/api.yaml once. Returns empty dict on error."""
    global _config
    if _config is not None:
        return _config

    if not _YAML:
        print("  [api_config] ⚠ pyyaml not installed, using defaults")
        _config = {}
        return _config

    if not _CONFIG_PATH.exists():
        print(f"  [api_config] ⚠ {_CONFIG_PATH} not found, using env vars only")
        _config = {}
        return _config

    try:
        _config = yaml.safe_load(_CONFIG_PATH.read_text()) or {}
    except Exception as e:
        print(f"  [api_config] ⚠ parse error: {e}")
        _config = {}

    return _config


def reload():
    """Force reload of config (useful for testing)."""
    global _config
    _config = None
    return _load()


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def get_llm_config() -> dict:
    """
    Get LLM configuration.

    Priority: env var > api.yaml > hardcoded defaults.

    Returns dict with keys:
        provider, model, api_key, base_url, temperature, max_tokens, providers
    """
    cfg = _load()
    llm = cfg.get("llm", {})

    # Provider: env var > yaml "provider" > yaml "active_provider" > default
    provider = (
        os.getenv("DEFAULT_PROVIDER")
        or llm.get("provider")
        or llm.get("active_provider")
        or "dashscope"
    )

    # Provider presets
    providers = llm.get("providers", {})

    # Resolve active provider's settings
    preset = providers.get(provider, {})
    api_key_env = preset.get("api_key_env", "")
    api_key = os.getenv(api_key_env, "") if api_key_env else ""
    base_url = preset.get("base_url", "")

    # Model: env var > yaml top-level > provider default_model > per-provider fallback
    # Per-provider fallback ensures correct model even when api.yaml is missing
    _PROVIDER_DEFAULT_MODELS = {
        "dashscope": "qwen-max",
        "openai": "gpt-4o",
        "moonshot": "moonshot-v1-auto",
        "ollama": "qwen3.5:9b",
        "gemini": "gemini-3.1-flash-lite-preview",
        "stepfun": "step-3.5-flash",
    }
    model = (
        os.getenv("DEFAULT_MODEL")
        or llm.get("model")
        or preset.get("default_model")
        or _PROVIDER_DEFAULT_MODELS.get(provider, "qwen-max")
    )

    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "temperature": llm.get("temperature", 0.92),
        "max_tokens": llm.get("max_tokens", 1024),
        "providers": providers,
    }


def get_tts_config() -> dict:
    """
    Get TTS configuration.

    Returns dict with keys:
        provider, cache_dir, api_keys: {openai, dashscope, minimax},
        minimax_model
    """
    cfg = _load()
    tts = cfg.get("tts", {})
    providers = tts.get("providers", {})

    # Resolve all API keys from env
    api_keys = {}
    for name, pcfg in providers.items():
        env_var = pcfg.get("api_key_env", "")
        api_keys[name] = os.getenv(env_var, "") if env_var else ""

    # MiniMax model
    minimax_model = providers.get("minimax", {}).get("model", "speech-2.8-turbo")

    return {
        "provider": tts.get("provider", "dashscope"),
        "cache_dir": tts.get("cache_dir", ".cache/tts"),
        "api_keys": api_keys,
        "minimax_model": minimax_model,
    }


def get_memory_config() -> dict:
    """
    Get EverMemOS memory configuration.

    Supports both old flat format and new nested format:
      Old: memory.enabled / memory.base_url / memory.api_key_env
      New: memory.evermemos.enabled / memory.evermemos.base_url / memory.evermemos.api_key_env

    Setting EVERMEMOS_BASE_URL env var will auto-enable it.

    Returns dict with keys:
        enabled, base_url, api_key
    """
    cfg = _load()
    mem = cfg.get("memory", {})

    # Support new nested format (memory.evermemos.*)
    ever_cfg = mem.get("evermemos", {})

    # Env var overrides
    env_base_url = os.getenv("EVERMEMOS_BASE_URL", "")

    # Try new format first, fall back to old flat format
    base_url = env_base_url or ever_cfg.get("base_url", "") or mem.get("base_url", "")
    api_key_env = ever_cfg.get("api_key_env", "") or mem.get("api_key_env", "EVERMEMOS_API_KEY")
    api_key = os.getenv(api_key_env, "") if api_key_env else ""

    # Enabled: new format > old format, but auto-enable if env var provides URL
    enabled = ever_cfg.get("enabled", mem.get("enabled", False))
    if env_base_url:
        enabled = True

    return {
        "enabled": enabled,
        "base_url": base_url,
        "api_key": api_key,
    }

