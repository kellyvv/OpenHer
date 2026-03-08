"""
AvatarService — 从 Persona 生成头像.

自动拼合 PERSONA.md 多个字段构建丰富 prompt：
  image.prompt_base  → 视觉核心描述 (外貌/穿搭/场景)
  image.style        → 风格 (realistic / anime / watercolor ...)
  tags               → 气质关键词 (gentle, poetic, dreamy)
  bio                → 性格/背景补充
  gender / age       → 确保人物一致性

使用方式：
    service = AvatarService(personas_dir="/path/to/personas")
    result = await service.generate_avatar(persona)     # 单个
    results = await service.generate_all(persona_loader) # 批量
"""

from __future__ import annotations

import os
from typing import Optional

from core.providers.registry import get_image_gen
from core.providers.image.base import ImageResult


# ─────────────────────────────────────────────────────────────
# Prompt Template
# ─────────────────────────────────────────────────────────────

_AVATAR_PROMPT_TEMPLATE = """Portrait of "{name}", {prompt_base}
Character traits: {traits}.
{bio_line}
Style: {style} portrait, high quality, detailed face, professional lighting.
Aspect ratio: 1:1 square portrait headshot."""

# Style mapping → additional prompt modifiers
_STYLE_MODIFIERS = {
    "realistic": "photorealistic, soft studio lighting, shallow depth of field",
    "anime": "anime style, cel shading, vibrant colors, clean lines",
    "watercolor": "watercolor painting, soft edges, artistic brush strokes",
    "illustration": "digital illustration, semi-realistic, artstation quality",
}


class AvatarService:
    """Persona avatar generation service (后台管理功能)."""

    AVATAR_FILENAME = "avatar.png"

    def __init__(self, personas_dir: str, cache_dir: Optional[str] = None):
        """
        Args:
            personas_dir: Root personas directory (e.g. /path/to/personas).
            cache_dir: Optional cache dir for image provider.
                       Defaults to personas_dir/.cache/avatar
        """
        self.personas_dir = personas_dir
        self.cache_dir = cache_dir or os.path.join(personas_dir, ".cache", "avatar")

    def _build_prompt(self, persona) -> str:
        """
        Build a rich image generation prompt from persona fields.

        Combines multiple PERSONA.md fields for better generation quality:
        - image.prompt_base (core visual description)
        - tags (personality traits)
        - bio (background context)
        - gender/age (physical consistency)
        - image.style (art style modifiers)
        """
        # Core visual description
        prompt_base = (persona.image.prompt_base or "").strip()
        if not prompt_base:
            # Fallback: construct from basic fields
            gender_word = "girl" if persona.gender == "female" else "boy"
            prompt_base = f"a {persona.age or 20}-year-old {gender_word}"

        # Traits from tags + mbti
        traits_parts = []
        if persona.tags:
            traits_parts.append(", ".join(persona.tags))
        if persona.mbti:
            traits_parts.append(f"{persona.mbti} personality type")
        traits = "; ".join(traits_parts) if traits_parts else "natural expression"

        # Bio (prefer Chinese for richer context, but use English if available)
        bio = ""
        if persona.bio:
            bio = persona.bio.get("zh") or persona.bio.get("en") or ""
        bio_line = f"Background: {bio}" if bio else ""

        # Style
        style = persona.image.style or "realistic"
        style_mod = _STYLE_MODIFIERS.get(style, style)

        prompt = _AVATAR_PROMPT_TEMPLATE.format(
            name=persona.name,
            prompt_base=prompt_base,
            traits=traits,
            bio_line=bio_line,
            style=f"{style}, {style_mod}",
        )

        # Negative prompt (if any)
        neg = persona.image.negative_prompt
        if neg:
            prompt += f"\nAvoid: {neg}"

        return prompt.strip()

    def get_avatar_path(self, persona_id: str) -> Optional[str]:
        """Get the avatar file path if it exists."""
        path = os.path.join(self.personas_dir, persona_id, self.AVATAR_FILENAME)
        return path if os.path.exists(path) else None

    async def generate_avatar(
        self,
        persona,
        force: bool = False,
    ) -> ImageResult:
        """
        Generate an avatar for a single persona.

        Args:
            persona: Loaded Persona object (from PersonaLoader).
            force: Regenerate even if avatar already exists.

        Returns:
            ImageResult with avatar_path.
        """
        avatar_path = os.path.join(
            self.personas_dir, persona.persona_id, self.AVATAR_FILENAME,
        )

        # Skip if already exists (unless forced)
        if not force and os.path.exists(avatar_path):
            return ImageResult(
                success=True,
                image_path=avatar_path,
                provider="cached",
            )

        # Build rich prompt
        prompt = self._build_prompt(persona)
        print(f"  🎨 生成头像: {persona.name} ({persona.persona_id})")
        print(f"     Prompt: {prompt[:80]}...")

        # Generate via image provider
        provider = get_image_gen(cache_dir=self.cache_dir)
        result = await provider.generate(
            prompt=prompt,
            aspect_ratio="1:1",
            image_size="1K",
        )

        if result.success and result.image_path:
            # Copy/move to persona directory as avatar.png
            import shutil
            os.makedirs(os.path.dirname(avatar_path), exist_ok=True)
            shutil.copy2(result.image_path, avatar_path)
            result.image_path = avatar_path
            print(f"  ✅ 保存到: {avatar_path}")
        else:
            print(f"  ❌ 生成失败: {result.error}")

        return result

    async def generate_all(
        self,
        persona_loader,
        force: bool = False,
    ) -> dict[str, ImageResult]:
        """
        Generate avatars for all loaded personas.

        Args:
            persona_loader: PersonaLoader instance.
            force: Regenerate existing avatars.

        Returns:
            Dict of persona_id → ImageResult.
        """
        personas = persona_loader.load_all()
        results = {}

        for pid, persona in personas.items():
            result = await self.generate_avatar(persona, force=force)
            results[pid] = result

        # Summary
        ok = sum(1 for r in results.values() if r.success)
        print(f"\n  📊 头像生成: {ok}/{len(results)} 成功")
        return results
