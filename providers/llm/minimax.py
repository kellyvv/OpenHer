"""MiniMax — OpenAI-compatible LLM provider (MiniMax-M2.7)."""

from .base import OpenAICompatProvider


class MiniMaxLLMProvider(OpenAICompatProvider):
    """MiniMax (MiniMax-M2.7)."""

    PROVIDER_NAME = "minimax"
    DEFAULT_BASE_URL = "https://api.minimax.io/v1"
    DEFAULT_API_KEY_ENV = "MINIMAX_LLM_API_KEY"
    DEFAULT_MODEL = "MiniMax-M2.7"
