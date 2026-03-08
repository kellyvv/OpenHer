"""DeepSeek — OpenAI-compatible LLM provider."""

from .base import OpenAICompatProvider


class DeepSeekLLMProvider(OpenAICompatProvider):
    """DeepSeek."""

    PROVIDER_NAME = "deepseek"
    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
    DEFAULT_API_KEY_ENV = "DEEPSEEK_API_KEY"
    DEFAULT_MODEL = "deepseek-chat"
