"""DeepSeek OpenAI-compatible LLM provider."""

from .base import OpenAICompatProvider


class DeepSeekLLMProvider(OpenAICompatProvider):
    """DeepSeek API provider."""

    PROVIDER_NAME = "deepseek"
    DEFAULT_BASE_URL = "https://api.deepseek.com"
    DEFAULT_API_KEY_ENV = "DEEPSEEK_API_KEY"
    DEFAULT_MODEL = "deepseek-v4-pro"
