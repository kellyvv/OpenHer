"""
PersonaLoader — Parse PERSONA.md files and manage character definitions.

Each persona is a directory containing a PERSONA.md with YAML frontmatter
(name, age, mbti, tags, voice config, image config) and markdown body
(personality description, speaking style, background story, behavioral rules).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import frontmatter
import yaml


@dataclass
class VoiceConfig:
    """Voice cloning and synthesis configuration for a persona."""
    ref_audio: Optional[str] = None       # Path to reference audio (3s clip)
    ref_text: Optional[str] = None        # Transcript of reference audio
    description: Optional[str] = None     # Natural language voice description (fallback)
    provider: str = "qwen3-tts"           # TTS provider to use
    emotion_enabled: bool = True          # Whether to inject emotion in TTS
    voice_preset: str = "default"         # Edge TTS voice preset key


@dataclass
class ImageConfig:
    """Image generation configuration for a persona."""
    prompt_base: Optional[str] = None     # Base prompt describing the character's appearance
    style: str = "realistic"              # Art style: realistic / anime / illustration
    negative_prompt: str = ""             # Things to avoid in generation


@dataclass
class Persona:
    """Loaded persona with all configuration and content."""
    # Identity
    name: str
    persona_id: str                       # Directory name, used as unique ID
    age: Optional[int] = None
    gender: str = "female"
    mbti: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    # Configs
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    image: ImageConfig = field(default_factory=ImageConfig)

    # Display layer
    bio: dict = field(default_factory=dict)  # {"en": ..., "zh": ...}

    # Content sections (from markdown body, legacy)
    personality: str = ""                 # 性格描述
    speaking_style: str = ""              # 说话风格
    background: str = ""                  # 背景故事
    behavioral_rules: str = ""            # 行为规则
    raw_content: str = ""                 # Full markdown body (fallback)

    # Engine seed
    drive_baseline: dict = field(default_factory=dict)   # genome_seed.drive_baseline
    engine_params: dict = field(default_factory=dict)    # genome_seed.engine_params (per-persona tuning)
    signal_overrides: dict = field(default_factory=dict) # genome_seed.signal_buckets (per-persona desc overrides)

    # Source
    base_dir: str = ""                    # Absolute path to persona directory

    def get_voice_ref_audio_path(self) -> Optional[str]:
        """Resolve voice reference audio to absolute path."""
        if self.voice.ref_audio and self.base_dir:
            ref = self.voice.ref_audio
            if not os.path.isabs(ref):
                return os.path.join(self.base_dir, ref)
            return ref
        return None

    def build_system_prompt_section(self) -> str:
        """Build the persona section for system prompt injection."""
        parts = [f"# 你的身份：{self.name}"]
        if self.age:
            parts.append(f"- 年龄：{self.age}岁")
        if self.gender:
            parts.append(f"- 性别：{self.gender}")
        if self.mbti:
            parts.append(f"- MBTI：{self.mbti}")
        if self.tags:
            parts.append(f"- 特点：{'、'.join(self.tags)}")

        if self.personality:
            parts.append(f"\n## 性格\n{self.personality}")
        if self.speaking_style:
            parts.append(f"\n## 说话风格\n{self.speaking_style}")
        if self.background:
            parts.append(f"\n## 背景故事\n{self.background}")
        if self.behavioral_rules:
            parts.append(f"\n## 行为规则\n{self.behavioral_rules}")

        # If no structured sections, use raw content
        if not any([self.personality, self.speaking_style, self.background]):
            if self.raw_content:
                parts.append(f"\n{self.raw_content}")

        return "\n".join(parts)


class PersonaLoader:
    """Load and manage persona definitions from PERSONA.md files."""

    PERSONA_FILENAME = "PERSONA.md"

    # Known H2 sections in PERSONA.md body
    SECTION_MAPPING = {
        "性格": "personality",
        "personality": "personality",
        "说话风格": "speaking_style",
        "speaking style": "speaking_style",
        "背景故事": "background",
        "background": "background",
        "背景": "background",
        "行为规则": "behavioral_rules",
        "behavioral rules": "behavioral_rules",
        "rules": "behavioral_rules",
    }

    def __init__(self, personas_dir: str):
        """
        Args:
            personas_dir: Root directory containing persona subdirectories.
                          Each subdirectory should contain a PERSONA.md.
        """
        self.personas_dir = Path(personas_dir)
        self._cache: dict[str, Persona] = {}

    def load_all(self) -> dict[str, Persona]:
        """Load all personas from the personas directory."""
        self._cache.clear()
        if not self.personas_dir.exists():
            return {}

        for entry in sorted(self.personas_dir.iterdir()):
            if entry.is_dir():
                persona_file = entry / self.PERSONA_FILENAME
                if persona_file.exists():
                    try:
                        persona = self._load_one(entry)
                        self._cache[persona.persona_id] = persona
                    except Exception as e:
                        print(f"[persona] Failed to load {entry.name}: {e}")
        return self._cache

    def get(self, persona_id: str) -> Optional[Persona]:
        """Get a loaded persona by ID."""
        if not self._cache:
            self.load_all()
        return self._cache.get(persona_id)

    def list_ids(self) -> list[str]:
        """List all available persona IDs."""
        if not self._cache:
            self.load_all()
        return list(self._cache.keys())

    def reload(self, persona_id: str) -> Optional[Persona]:
        """Reload a specific persona from disk."""
        persona_dir = self.personas_dir / persona_id
        if not (persona_dir / self.PERSONA_FILENAME).exists():
            return None
        persona = self._load_one(persona_dir)
        self._cache[persona.persona_id] = persona
        return persona

    def _load_one(self, persona_dir: Path) -> Persona:
        """Load a single persona from its directory."""
        persona_file = persona_dir / self.PERSONA_FILENAME
        post = frontmatter.load(str(persona_file))

        # Parse frontmatter
        meta = post.metadata
        persona_id = persona_dir.name

        # Voice config
        voice_meta = meta.get("voice", {})
        if isinstance(voice_meta, str):
            voice_meta = {"description": voice_meta}
        voice = VoiceConfig(
            ref_audio=voice_meta.get("ref_audio"),
            ref_text=voice_meta.get("ref_text"),
            description=voice_meta.get("description"),
            provider=voice_meta.get("provider", "qwen3-tts"),
            emotion_enabled=voice_meta.get("emotion_enabled", True),
            voice_preset=voice_meta.get("voice_preset", "default"),
        )

        # Image config
        image_meta = meta.get("image", {})
        if isinstance(image_meta, str):
            image_meta = {"prompt_base": image_meta}
        image = ImageConfig(
            prompt_base=image_meta.get("prompt_base"),
            style=image_meta.get("style", "realistic"),
            negative_prompt=image_meta.get("negative_prompt", ""),
        )

        # Parse body sections
        sections = self._parse_sections(post.content)

        # Genome seed (engine layer)
        genome_seed = meta.get("genome_seed", {})
        drive_baseline = genome_seed.get("drive_baseline", {}) if isinstance(genome_seed, dict) else {}

        # Bio (display layer, may be dict or string)
        bio_raw = meta.get("bio", {})
        bio = bio_raw if isinstance(bio_raw, dict) else {"en": str(bio_raw)}

        persona = Persona(
            name=meta.get("name", persona_id),
            persona_id=persona_id,
            age=meta.get("age"),
            gender=meta.get("gender", "female"),
            mbti=meta.get("mbti"),
            tags=meta.get("tags", []),
            voice=voice,
            image=image,
            bio=bio,
            personality=sections.get("personality", ""),
            speaking_style=sections.get("speaking_style", ""),
            background=sections.get("background", ""),
            behavioral_rules=sections.get("behavioral_rules", ""),
            raw_content=post.content,
            base_dir=str(persona_dir),
            drive_baseline=drive_baseline,
            engine_params=genome_seed.get("engine_params", {}) if isinstance(genome_seed, dict) else {},
            signal_overrides=genome_seed.get("signal_buckets", {}) if isinstance(genome_seed, dict) else {},
        )
        return persona

    def _parse_sections(self, content: str) -> dict[str, str]:
        """Parse markdown H2 sections into a dict."""
        sections: dict[str, str] = {}
        current_key: Optional[str] = None
        current_lines: list[str] = []

        for line in content.split("\n"):
            if line.startswith("## "):
                # Save previous section
                if current_key:
                    sections[current_key] = "\n".join(current_lines).strip()
                # Start new section
                heading = line[3:].strip().lower()
                current_key = self.SECTION_MAPPING.get(heading)
                current_lines = []
            elif current_key is not None:
                current_lines.append(line)

        # Save last section
        if current_key:
            sections[current_key] = "\n".join(current_lines).strip()

        return sections
