from pathlib import Path

import pytest

from agent.skills.tools import voice_tools
from providers.speech.tts.base import TTSResult


class _SuccessfulTTS:
    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)

    async def synthesize(self, **_kwargs):
        path = self.cache_dir / "voice.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"RIFF")
        return TTSResult(success=True, audio_path=str(path))


@pytest.mark.asyncio
async def test_synthesize_voice_uses_persona_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_tools, "VOICE_CACHE_ROOT", tmp_path / "voice")
    monkeypatch.setattr(
        "providers.registry.get_tts",
        lambda cache_dir: _SuccessfulTTS(cache_dir),
    )

    result = await voice_tools._synthesize_voice(
        text="Hello",
        persona_id="iris",
        voice_preset="Cherry",
    )

    assert result["success"] is True
    assert Path(result["audio_path"]).parent == (tmp_path / "voice" / "iris").resolve()
