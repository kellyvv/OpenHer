"""Moonshot (Kimi) — OpenAI-compatible LLM provider."""

from .base import OpenAICompatProvider


class MoonshotLLMProvider(OpenAICompatProvider):
    """Moonshot (Kimi)."""

    PROVIDER_NAME = "moonshot"
    DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
    DEFAULT_API_KEY_ENV = "MOONSHOT_API_KEY"
    DEFAULT_MODEL = "moonshot-v1-auto"
