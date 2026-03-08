"""OpenAI — OpenAI-compatible LLM provider."""

from .base import OpenAICompatProvider


class OpenAILLMProvider(OpenAICompatProvider):
    """OpenAI (gpt-4o)."""

    PROVIDER_NAME = "openai"
    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_API_KEY_ENV = "OPENAI_API_KEY"
    DEFAULT_MODEL = "gpt-4o"
