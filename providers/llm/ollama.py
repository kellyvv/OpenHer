"""Ollama — 本地 LLM provider (OpenAI-compatible, 无需 API key)."""

from .base import OpenAICompatProvider


class OllamaLLMProvider(OpenAICompatProvider):
    """Ollama 本地模型 (localhost:11434)."""

    PROVIDER_NAME = "ollama"
    DEFAULT_BASE_URL = "http://localhost:11434/v1"
    DEFAULT_API_KEY_ENV = ""
    DEFAULT_MODEL = "qwen3.5:9b"
    NO_KEY_REQUIRED = True
