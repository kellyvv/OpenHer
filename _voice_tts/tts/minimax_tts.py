"""
MiniMax TTS 封装 — 克隆音色 + 情绪控制

功能:
  1. speak()         — 用指定音色合成语音，支持情绪/语速/停顿/语气词
  2. clone_voice()   — 上传音频创建克隆音色
  3. list_emotions()  — 列出支持的情绪

API:
  - 模型: speech-2.8-turbo (默认) / speech-2.8-hd
  - 端点: https://api.minimax.io/v1/t2a_v2
  - 认证: Bearer API_KEY

环境变量:
  export MINIMAX_API_KEY="your-api-key"
"""

import os
import time
import json
import requests
from typing import Optional, List, Literal
from dataclasses import dataclass


@dataclass
class TTSResult:
    """TTS 生成结果"""
    audio_bytes: bytes      # 原始音频字节 (mp3/wav)
    sample_rate: int        # 采样率
    duration: float         # 时长(秒)
    elapsed: float          # 调用耗时(秒)
    format: str             # 音频格式 (mp3/wav)
    characters: int         # 消耗字符数
    model: str              # 使用的模型

    def save(self, path: str) -> str:
        """保存音频文件"""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(self.audio_bytes)
        return path


# 支持的情绪
EMOTIONS = [
    "happy", "sad", "angry", "fearful",
    "disgusted", "surprised", "neutral",
]

# Speech-2.8 专属语气词标签
INTERJECTIONS = [
    "(laughs)", "(chuckle)", "(coughs)", "(clear-throat)",
    "(groans)", "(breath)", "(pant)", "(inhale)", "(exhale)",
    "(gasps)", "(sniffs)", "(sighs)", "(snorts)", "(burps)",
    "(lip-smacking)", "(humming)", "(hissing)", "(emm)", "(sneezes)",
]

# 音效
SOUND_EFFECTS = [
    "spacious_echo", "auditorium_echo", "lofi_telephone", "robotic",
]

# 语言
LANGUAGES = [
    "Chinese", "English", "Japanese", "Korean", "French",
    "German", "Spanish", "Portuguese", "Russian", "Arabic",
    "Thai", "Vietnamese", "Indonesian", "auto",
]


class MiniMaxTTSClient:
    """
    MiniMax TTS API 客户端

    Usage:
        client = MiniMaxTTSClient(api_key="your-key")

        # 1. 基础合成（系统音色）
        result = client.speak(
            text="你好，今天天气真好。",
            voice_id="Chinese_female_anchor_3",
        )
        result.save("output.mp3")

        # 2. 带情绪控制
        result = client.speak(
            text="太开心了！终于收到录取通知了！",
            voice_id="Chinese_female_anchor_3",
            emotion="happy",
            speed=1.1,
        )

        # 3. 带语气词和停顿
        result = client.speak(
            text="(sighs)唉，又加班了<#1.5#>算了，习惯了。",
            voice_id="my_cloned_voice",
        )

        # 4. 克隆音色
        voice_id = client.clone_voice(
            audio_path="reference.wav",
            voice_id="my_custom_voice_001",
        )
    """

    API_BASE = "https://api.minimax.io/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "speech-2.8-turbo",
        default_language: str = "Chinese",
    ):
        """
        Args:
            api_key: MiniMax API Key (或设置环境变量 MINIMAX_API_KEY)
            model: 模型版本 ("speech-2.8-turbo" 或 "speech-2.8-hd")
            default_language: 默认语言
        """
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY", "")
        self.model = model
        self.default_language = default_language

        if not self.api_key:
            raise ValueError(
                "需要 MiniMax API Key。\n"
                "方式一: MiniMaxTTSClient(api_key='your-key')\n"
                "方式二: export MINIMAX_API_KEY='your-key'"
            )

    @property
    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def speak(
        self,
        text: str,
        voice_id: str,
        emotion: Optional[str] = None,
        speed: float = 1.0,
        volume: float = 1.0,
        pitch: int = 0,
        language: Optional[str] = None,
        audio_format: str = "mp3",
        sample_rate: int = 32000,
        bitrate: int = 128000,
        voice_modify: Optional[dict] = None,
    ) -> TTSResult:
        """
        文字转语音

        Args:
            text: 文本 (最大 10000 字符)
                  支持停顿标记: <#1.5#> (1.5秒停顿)
                  支持语气词 (2.8): (laughs) (sighs) (gasps) 等
            voice_id: 音色 ID (系统音色或克隆音色)
            emotion: 情绪 (happy/sad/angry/fearful/disgusted/surprised/neutral)
            speed: 语速 (0.5~2.0, 默认 1.0)
            volume: 音量 (0~10, 默认 1.0)
            pitch: 音调 (-12~12, 默认 0)
            language: 语言 (默认 Chinese)
            audio_format: 输出格式 (mp3/wav/flac)
            sample_rate: 采样率 (默认 32000)
            bitrate: 比特率 (默认 128000)
            voice_modify: 音效设置 {"pitch": 0, "intensity": 0, "timbre": 0,
                          "sound_effects": "spacious_echo"}

        Returns:
            TTSResult 包含音频数据
        """
        if emotion and emotion not in EMOTIONS:
            raise ValueError(f"不支持的情绪: {emotion}\n可选: {EMOTIONS}")

        payload = {
            "model": self.model,
            "text": text,
            "stream": False,
            "language_boost": language or self.default_language,
            "output_format": "hex",
            "voice_setting": {
                "voice_id": voice_id,
                "speed": speed,
                "vol": volume,
                "pitch": pitch,
            },
            "audio_setting": {
                "sample_rate": sample_rate,
                "bitrate": bitrate,
                "format": audio_format,
                "channel": 1,
            },
        }

        if emotion:
            payload["voice_setting"]["emotion"] = emotion

        if voice_modify:
            payload["voice_modify"] = voice_modify

        t0 = time.time()
        resp = requests.post(
            f"{self.API_BASE}/t2a_v2",
            headers=self._headers,
            json=payload,
            timeout=120,
        )
        elapsed = time.time() - t0

        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

        result = resp.json()
        base_resp = result.get("base_resp", {})
        if base_resp.get("status_code", -1) != 0:
            raise RuntimeError(
                f"API Error [{base_resp.get('status_code')}]: "
                f"{base_resp.get('status_msg', 'unknown')}"
            )

        audio_hex = result["data"]["audio"]
        audio_bytes = bytes.fromhex(audio_hex)

        extra = result.get("extra_info", {})

        return TTSResult(
            audio_bytes=audio_bytes,
            sample_rate=extra.get("audio_sample_rate", sample_rate),
            duration=extra.get("audio_length", 0) / 1000,
            elapsed=elapsed,
            format=extra.get("audio_format", audio_format),
            characters=extra.get("usage_characters", 0),
            model=self.model,
        )

    def speak_with_emotion(
        self,
        text: str,
        voice_id: str,
        emotion: str,
        **kwargs,
    ) -> TTSResult:
        """speak() 的便捷方法，必须指定情绪"""
        return self.speak(text=text, voice_id=voice_id, emotion=emotion, **kwargs)

    def clone_voice(
        self,
        audio_path: str,
        voice_id: str,
        language: str = "Chinese",
        noise_reduction: bool = True,
    ) -> str:
        """
        上传音频克隆音色

        3 步流程:
          1. 上传音频文件 → 获取 file_id
          2. 调用克隆接口 → 绑定 voice_id
          3. 返回 voice_id (可直接用于 speak())

        Args:
            audio_path: 音频文件路径 (mp3/wav/m4a, 10s~5min, <20MB)
            voice_id: 自定义音色 ID (8~256字符，字母开头，字母数字连字符下划线)
            language: 语言
            noise_reduction: 是否降噪

        Returns:
            voice_id (成功后可直接用于 speak)
        """
        # Step 1: 上传音频文件
        ext = os.path.splitext(audio_path)[1].lower()
        content_type_map = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
        }
        content_type = content_type_map.get(ext, "audio/mpeg")

        with open(audio_path, "rb") as f:
            upload_resp = requests.post(
                f"{self.API_BASE}/files/upload",
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (os.path.basename(audio_path), f, content_type)},
                data={"purpose": "voice_clone"},
                timeout=60,
            )

        if upload_resp.status_code != 200:
            raise RuntimeError(f"上传失败: HTTP {upload_resp.status_code}: {upload_resp.text[:300]}")

        upload_result = upload_resp.json()
        file_id = upload_result.get("file", {}).get("file_id")
        if not file_id:
            raise RuntimeError(f"上传返回无 file_id: {upload_result}")

        # Step 2: 克隆
        clone_payload = {
            "file_id": file_id,
            "voice_id": voice_id,
            "noise_reduction": noise_reduction,
        }

        clone_resp = requests.post(
            f"{self.API_BASE}/voice_clone",
            headers=self._headers,
            json=clone_payload,
            timeout=120,
        )

        if clone_resp.status_code != 200:
            raise RuntimeError(f"克隆失败: HTTP {clone_resp.status_code}: {clone_resp.text[:300]}")

        clone_result = clone_resp.json()
        base_resp = clone_result.get("base_resp", {})
        if base_resp.get("status_code", -1) != 0:
            raise RuntimeError(
                f"克隆 API Error: {base_resp.get('status_msg', 'unknown')}"
            )

        return voice_id

    @staticmethod
    def list_emotions() -> List[str]:
        """返回支持的情绪列表"""
        return EMOTIONS.copy()

    @staticmethod
    def list_interjections() -> List[str]:
        """返回支持的语气词标签 (Speech-2.8 专属)"""
        return INTERJECTIONS.copy()

    @staticmethod
    def list_sound_effects() -> List[str]:
        """返回支持的音效列表"""
        return SOUND_EFFECTS.copy()

    @staticmethod
    def add_emotion(text: str, emotion: str) -> str:
        """在文本前添加情绪标记 (便捷方法)"""
        # MiniMax 通过 API 参数控制情绪，不是文本标签
        # 这个方法仅用于记录意图，实际通过 emotion 参数传递
        return text

    @staticmethod
    def add_pause(text: str, position: int, seconds: float) -> str:
        """在文本指定位置插入停顿标记"""
        marker = f"<#{seconds}#>"
        return text[:position] + marker + text[position:]

    @staticmethod
    def format_text_with_pauses(segments: List[tuple]) -> str:
        """
        组合文本和停顿

        Args:
            segments: [(文本, 停顿秒数), ...]
                      最后一个元素停顿为 0 或省略

        Example:
            text = MiniMaxTTSClient.format_text_with_pauses([
                ("接下来", 1.5),
                ("我要宣布一个重要消息", 2.0),
                ("我们的项目成功了！", 0),
            ])
            # => "接下来<#1.5#>我要宣布一个重要消息<#2#>我们的项目成功了！"
        """
        parts = []
        for i, item in enumerate(segments):
            text = item[0]
            pause = item[1] if len(item) > 1 else 0
            parts.append(text)
            if pause > 0:
                parts.append(f"<#{pause}#>")
        return "".join(parts)
