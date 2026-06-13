"""Safe path helpers for persisted voice messages."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote


VOICE_MEDIA_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
}


def voice_url_from_path(audio_path: str | Path, voice_root: str | Path) -> str | None:
    """Convert a cached voice file to its public relative URL."""
    root = Path(voice_root).resolve()
    path = Path(audio_path).resolve()
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None

    if len(relative.parts) < 2 or path.suffix.lower() not in VOICE_MEDIA_TYPES:
        return None

    encoded = "/".join(quote(part, safe="") for part in relative.parts)
    return f"/api/voice/{encoded}"


def resolve_voice_file(
    voice_root: str | Path,
    persona_id: str,
    filename: str,
) -> tuple[Path, str]:
    """Resolve a public voice path while preventing cache-root traversal."""
    root = Path(voice_root).resolve()
    path = (root / persona_id / filename).resolve()

    try:
        path.relative_to(root)
    except ValueError as error:
        raise FileNotFoundError(filename) from error

    media_type = VOICE_MEDIA_TYPES.get(path.suffix.lower())
    if not media_type or not path.is_file():
        raise FileNotFoundError(filename)

    return path, media_type
