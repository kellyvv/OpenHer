"""DashScope (阿里 Qwen) — OpenAI-compatible LLM provider."""

from .base import OpenAICompatProvider


class DashScopeLLMProvider(OpenAICompatProvider):
    """阿里 DashScope (qwen-max)."""

    PROVIDER_NAME = "dashscope"
    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DEFAULT_API_KEY_ENV = "DASHSCOPE_API_KEY"
    DEFAULT_MODEL = "qwen-max"
