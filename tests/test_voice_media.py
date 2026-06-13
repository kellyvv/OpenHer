from pathlib import Path

import httpx
import pytest

from engine.media_paths import resolve_voice_file, voice_url_from_path


def test_builds_voice_url_for_persona_cache(tmp_path):
    root = tmp_path / "voice"
    audio_path = root / "iris" / "hello.wav"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"RIFF")

    assert voice_url_from_path(audio_path, root) == "/api/voice/iris/hello.wav"


def test_rejects_voice_url_outside_cache(tmp_path):
    root = tmp_path / "voice"
    outside = tmp_path / "secret.wav"
    outside.write_bytes(b"RIFF")

    assert voice_url_from_path(outside, root) is None


def test_resolves_supported_voice_file(tmp_path):
    root = tmp_path / "voice"
    audio_path = root / "iris" / "hello.wav"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"RIFF")

    resolved, media_type = resolve_voice_file(root, "iris", "hello.wav")

    assert resolved == audio_path.resolve()
    assert media_type == "audio/wav"


@pytest.mark.parametrize("filename", ["missing.wav", "hello.txt"])
def test_rejects_missing_or_unsupported_voice_file(tmp_path, filename):
    root = tmp_path / "voice"
    target = root / "iris" / filename
    target.parent.mkdir(parents=True)
    if target.suffix == ".txt":
        target.write_text("not audio", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        resolve_voice_file(root, "iris", filename)


def test_rejects_voice_path_traversal(tmp_path):
    root = tmp_path / "voice"
    root.mkdir()
    outside = tmp_path / "secret.wav"
    outside.write_bytes(b"RIFF")

    with pytest.raises(FileNotFoundError):
        resolve_voice_file(root, "iris", "../../secret.wav")


@pytest.mark.asyncio
async def test_voice_endpoint_serves_audio_with_range_support(monkeypatch, tmp_path):
    import main

    audio_path = tmp_path / "hello.wav"
    audio_path.write_bytes(b"RIFF0123456789")
    monkeypatch.setattr(
        main,
        "resolve_voice_file",
        lambda _root, _persona, _filename: (audio_path, "audio/wav"),
    )
    transport = httpx.ASGITransport(app=main.app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/voice/iris/hello.wav",
            headers={"Range": "bytes=4-7"},
        )

    assert response.status_code == 206
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == b"0123"


@pytest.mark.asyncio
async def test_voice_endpoint_returns_404_for_missing_audio(monkeypatch):
    import main

    def missing(*_args):
        raise FileNotFoundError

    monkeypatch.setattr(main, "resolve_voice_file", missing)
    transport = httpx.ASGITransport(app=main.app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/voice/iris/missing.wav")

    assert response.status_code == 404
