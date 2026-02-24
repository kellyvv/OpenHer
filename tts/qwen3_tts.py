"""
Qwen3-TTS 封装 — 本地音色设计与克隆

功能:
  1. voice_design()  — 用文字描述创建自定义音色，返回音频
  2. voice_clone()   — 用参考音频克隆音色，生成新文本
  3. create_clone_prompt() — 创建可复用的克隆 prompt

依赖:
  - 需要在 Qwen3-TTS 的 venv 中运行 (transformers==4.57.3)
  - 模型路径需要预先下载好
"""

import os
import time
import torch
import numpy as np
import soundfile as sf
from typing import Optional, List, Tuple
from dataclasses import dataclass, field


@dataclass
class TTSResult:
    """TTS 生成结果"""
    audio: np.ndarray       # 音频数据
    sample_rate: int        # 采样率
    duration: float         # 时长(秒)
    elapsed: float          # 生成耗时(秒)
    model_name: str = ""    # 使用的模型

    def save(self, path: str):
        """保存为 wav 文件"""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        sf.write(path, self.audio, self.sample_rate)
        return path


# 默认模型路径
DEFAULT_MODELS = {
    "voice_design": "/Users/zxw/AITOOL/openher/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "base":         "/Users/zxw/AITOOL/openher/Qwen3-TTS-12Hz-1.7B-Base",
    "custom_voice": "/Users/zxw/AITOOL/openher/Qwen3-TTS-12Hz-1.7B-CustomVoice",
}

# 内置音色列表
BUILTIN_SPEAKERS = [
    "aiden", "dylan", "eric", "ono_anna", "ryan",
    "serena", "sohee", "uncle_fu", "vivian",
]


class Qwen3TTSClient:
    """
    Qwen3-TTS 本地推理客户端

    Usage:
        client = Qwen3TTSClient()

        # 1. 用文字描述设计音色
        result = client.voice_design(
            text="你好，欢迎来到我们的平台。",
            description="一个温柔知性的女性声音，语速适中",
            language="Chinese",
        )
        result.save("output.wav")

        # 2. 克隆音色说新文本
        result = client.voice_clone(
            text="今天天气真好。",
            ref_audio="reference.wav",
            ref_text="这是参考音频的文本。",
            language="Chinese",
        )
        result.save("clone_output.wav")
    """

    def __init__(
        self,
        model_paths: Optional[dict] = None,
        device: str = "auto",
        dtype: torch.dtype = torch.float32,
    ):
        """
        Args:
            model_paths: 模型路径字典 {"voice_design": ..., "base": ..., "custom_voice": ...}
            device: 设备 ("auto", "mps", "cuda", "cpu")
            dtype: 数据类型 (MPS 建议 torch.float32)
        """
        self.model_paths = {**DEFAULT_MODELS, **(model_paths or {})}
        self.dtype = dtype

        if device == "auto":
            if torch.cuda.is_available():
                self.device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
        else:
            self.device = device

        # 懒加载: 按需加载模型
        self._models = {}

    def _get_model(self, model_type: str):
        """懒加载模型"""
        if model_type not in self._models:
            from qwen_tts import Qwen3TTSModel

            path = self.model_paths.get(model_type)
            if not path or not os.path.exists(path):
                raise FileNotFoundError(
                    f"模型路径不存在: {path}\n"
                    f"请先下载模型或在 model_paths 中指定正确路径"
                )

            self._models[model_type] = Qwen3TTSModel.from_pretrained(
                path, device_map=self.device, dtype=self.dtype,
            )
        return self._models[model_type]

    def voice_design(
        self,
        text: str,
        description: str,
        language: str = "Chinese",
    ) -> TTSResult:
        """
        用文字描述设计一个新音色并生成语音

        Args:
            text: 要朗读的文本
            description: 音色描述 (例: "一个温柔知性的女性声音，语速适中，带有轻柔的气息感")
            language: 语言 ("Chinese", "English")

        Returns:
            TTSResult 包含音频数据
        """
        model = self._get_model("voice_design")

        t0 = time.time()
        wavs, sr = model.generate_voice_design(
            text=text,
            instruct=description,
            language=language,
        )
        elapsed = time.time() - t0

        audio = wavs[0] if isinstance(wavs, list) else wavs
        if isinstance(audio, torch.Tensor):
            audio = audio.cpu().numpy()

        return TTSResult(
            audio=audio,
            sample_rate=sr,
            duration=len(audio) / sr,
            elapsed=elapsed,
            model_name="Qwen3-TTS-VoiceDesign",
        )

    def create_clone_prompt(
        self,
        ref_audio: str,
        ref_text: str,
    ):
        """
        创建可复用的克隆 prompt（一次克隆，多次使用）

        Args:
            ref_audio: 参考音频文件路径
            ref_text: 参考音频的文本内容

        Returns:
            voice_clone_prompt 对象（可传给 voice_clone 的 prompt 参数）
        """
        model = self._get_model("base")
        return model.create_voice_clone_prompt(
            ref_audio=ref_audio,
            ref_text=ref_text,
        )

    def voice_clone(
        self,
        text: str,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        voice_clone_prompt=None,
        language: str = "Chinese",
    ) -> TTSResult:
        """
        用参考音频克隆音色，朗读新文本

        Args:
            text: 要朗读的新文本
            ref_audio: 参考音频文件路径 (与 voice_clone_prompt 二选一)
            ref_text: 参考音频的文本内容
            voice_clone_prompt: 预创建的 prompt (可选，来自 create_clone_prompt)
            language: 语言

        Returns:
            TTSResult
        """
        model = self._get_model("base")

        if voice_clone_prompt is None:
            if ref_audio is None or ref_text is None:
                raise ValueError("需要提供 ref_audio + ref_text，或 voice_clone_prompt")
            voice_clone_prompt = model.create_voice_clone_prompt(
                ref_audio=ref_audio, ref_text=ref_text,
            )

        t0 = time.time()
        wavs, sr = model.generate_voice_clone(
            text=text,
            voice_clone_prompt=voice_clone_prompt,
            language=language,
        )
        elapsed = time.time() - t0

        audio = wavs[0] if isinstance(wavs, list) else wavs
        if isinstance(audio, torch.Tensor):
            audio = audio.cpu().numpy()

        return TTSResult(
            audio=audio,
            sample_rate=sr,
            duration=len(audio) / sr,
            elapsed=elapsed,
            model_name="Qwen3-TTS-Base",
        )

    def custom_voice(
        self,
        text: str,
        speaker: str = "vivian",
        instruct: str = "",
        language: str = "Chinese",
    ) -> TTSResult:
        """
        使用内置音色 + 指令控制

        Args:
            text: 要朗读的文本
            speaker: 内置音色名 (见 BUILTIN_SPEAKERS)
            instruct: 指令 (例: "用开心兴奋的语气说")
            language: 语言

        Returns:
            TTSResult
        """
        if speaker not in BUILTIN_SPEAKERS:
            raise ValueError(
                f"不支持的音色: {speaker}\n可用音色: {BUILTIN_SPEAKERS}"
            )

        model = self._get_model("custom_voice")

        t0 = time.time()
        wavs, sr = model.generate_custom_voice(
            text=text,
            speaker=speaker,
            instruct=instruct or "",
            language=language,
        )
        elapsed = time.time() - t0

        audio = wavs[0] if isinstance(wavs, list) else wavs
        if isinstance(audio, torch.Tensor):
            audio = audio.cpu().numpy()

        return TTSResult(
            audio=audio,
            sample_rate=sr,
            duration=len(audio) / sr,
            elapsed=elapsed,
            model_name="Qwen3-TTS-CustomVoice",
        )

    @property
    def available_speakers(self) -> List[str]:
        """返回可用的内置音色列表"""
        return BUILTIN_SPEAKERS.copy()
