"""StepFun — OpenAI-compatible LLM provider (step-3.5-flash)."""

from .base import OpenAICompatProvider


class StepFunLLMProvider(OpenAICompatProvider):
    """StepFun (step-3.5-flash)."""

    PROVIDER_NAME = "stepfun"
    DEFAULT_BASE_URL = "https://api.stepfun.com/v1"
    DEFAULT_API_KEY_ENV = "STEPFUN_API_KEY"
    DEFAULT_MODEL = "step-3.5-flash"
