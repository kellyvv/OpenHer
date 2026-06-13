import base64

from demo.media_test import build_demo_media_events


def test_builds_image_event_for_current_persona():
    events = build_demo_media_events("image", "iris")

    assert events == [
        {
            "type": "chat_end",
            "reply": "这是我的照片。",
            "modality": "照片",
            "image_url": "/api/persona/iris/media/face",
            "demo_media": True,
        }
    ]


def test_builds_voice_events_from_fixed_wav(tmp_path):
    voice_path = tmp_path / "media_test.wav"
    voice_path.write_bytes(b"RIFFtest-wave-data")

    events = build_demo_media_events("voice", "iris", voice_path=voice_path)

    assert events[0] == {
        "type": "chat_end",
        "reply": "你好，这是 OpenHer 网页端语音消息测试。",
        "modality": "语音",
        "demo_media": True,
    }
    assert events[1]["type"] == "tts_audio"
    assert events[1]["format"] == "wav"
    assert base64.b64decode(events[1]["audio"]) == b"RIFFtest-wave-data"
