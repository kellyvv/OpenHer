"""
Avatar data models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class AvatarConfig:
    """Avatar configuration read from PERSONA.md image.* fields."""
    prompt_base: str = ""
    style: str = "realistic"
    negative_prompt: str = ""


@dataclass
class AvatarStatus:
    """Full avatar status for a persona (config + file state)."""
    persona_id: str
    persona_name: str
    config: AvatarConfig
    has_avatar: bool
    avatar_path: Optional[str] = None
