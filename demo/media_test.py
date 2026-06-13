"""Fixed media payloads for end-to-end Demo WebSocket testing."""

from __future__ import annotations

import base64
from pathlib import Path


DEFAULT_VOICE_PATH = Path(__file__).resolve().parent / "assets" / "media_test.wav"
VOICE_TEST_TEXT = "你好，这是 OpenHer 网页端语音消息测试。"


def build_demo_media_events(
    media_type: str,
    persona_id: str,
    *,
    voice_path: Path | None = None,
) -> list[dict]:
    """Build fixed media events without invoking models or mutating agent state."""
    if media_type == "image":
        return [{
            "type": "chat_end",
            "reply": "这是我的照片。",
            "modality": "照片",
            "image_url": f"/api/persona/{persona_id}/media/face",
            "demo_media": True,
        }]

    if media_type == "voice":
        path = voice_path or DEFAULT_VOICE_PATH
        audio = base64.b64encode(path.read_bytes()).decode("ascii")
        return [
            {
                "type": "chat_end",
                "reply": VOICE_TEST_TEXT,
                "modality": "语音",
                "demo_media": True,
            },
            {
                "type": "tts_audio",
                "audio": audio,
                "format": "wav",
                "demo_media": True,
            },
        ]

    raise ValueError(f"Unsupported demo media type: {media_type}")
