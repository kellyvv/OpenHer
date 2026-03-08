"""
AvatarRepository — Avatar 配置的唯一数据入口.

直接读写 PERSONA.md 的 image.* 字段，使用 python-frontmatter。
不经过 PersonaLoader。
"""

from __future__ import annotations

import os
import shutil
from typing import Optional

import frontmatter

from .models import AvatarConfig


class AvatarRepository:
    """Read/write PERSONA.md image.* fields and manage avatar.png files."""

    PERSONA_FILENAME = "PERSONA.md"
    AVATAR_FILENAME = "avatar.png"

    # Only these fields can be written back to PERSONA.md
    _WRITABLE_FIELDS = {"prompt_base", "style", "negative_prompt"}

    def __init__(self, personas_dir: str):
        """
        Args:
            personas_dir: Absolute path to the personas data directory
                          (e.g. /path/to/persona/personas/)
        """
        self.personas_dir = personas_dir

    def _persona_dir(self, persona_id: str) -> str:
        return os.path.join(self.personas_dir, persona_id)

    def _persona_file(self, persona_id: str) -> str:
        return os.path.join(self._persona_dir(persona_id), self.PERSONA_FILENAME)

    def _avatar_file(self, persona_id: str) -> str:
        return os.path.join(self._persona_dir(persona_id), self.AVATAR_FILENAME)

    # ─── Read ───

    def read_config(self, persona_id: str) -> AvatarConfig:
        """Read image.* fields from PERSONA.md → AvatarConfig."""
        path = self._persona_file(persona_id)
        if not os.path.exists(path):
            raise FileNotFoundError(f"PERSONA.md not found: {path}")

        post = frontmatter.load(path)
        image_data = post.metadata.get("image", {})
        if isinstance(image_data, str):
            image_data = {"prompt_base": image_data}

        return AvatarConfig(
            prompt_base=image_data.get("prompt_base", ""),
            style=image_data.get("style", "realistic"),
            negative_prompt=image_data.get("negative_prompt", ""),
        )

    def write_config(self, persona_id: str, config: AvatarConfig) -> None:
        """Write AvatarConfig back to PERSONA.md image.* fields.

        Only writes whitelisted fields. Creates .bak backup first.
        """
        path = self._persona_file(persona_id)
        if not os.path.exists(path):
            raise FileNotFoundError(f"PERSONA.md not found: {path}")

        # Backup
        backup_path = path + ".bak"
        shutil.copy2(path, backup_path)

        # Read → modify → write
        post = frontmatter.load(path)

        image_data = post.metadata.get("image", {})
        if isinstance(image_data, str):
            image_data = {"prompt_base": image_data}

        # Write all whitelisted fields unconditionally
        # (empty string = intentional clear, must persist to disk)
        image_data["prompt_base"] = config.prompt_base
        image_data["style"] = config.style
        image_data["negative_prompt"] = config.negative_prompt

        post.metadata["image"] = image_data

        with open(path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))

    # ─── Avatar file operations ───

    def get_avatar_path(self, persona_id: str) -> Optional[str]:
        """Return avatar.png path if it exists, else None."""
        path = self._avatar_file(persona_id)
        return path if os.path.exists(path) else None

    def delete_avatar_file(self, persona_id: str) -> bool:
        """Delete avatar.png. Returns True if file existed and was deleted."""
        path = self._avatar_file(persona_id)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def save_avatar_file(self, persona_id: str, source_path: str) -> str:
        """Copy a generated image to personas/{id}/avatar.png."""
        dest = self._avatar_file(persona_id)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(source_path, dest)
        return dest
