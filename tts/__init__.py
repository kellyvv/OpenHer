# TTS API 模块
# Qwen3-TTS: 本地音色设计
# MiniMax TTS: 克隆 + 情绪控制

from .qwen3_tts import Qwen3TTSClient
from .minimax_tts import MiniMaxTTSClient

__all__ = ["Qwen3TTSClient", "MiniMaxTTSClient"]
