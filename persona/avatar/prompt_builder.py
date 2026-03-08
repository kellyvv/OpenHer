"""
Prompt builder — Persona 多字段 → 丰富的生图 prompt.

从 PERSONA.md 的多个字段自动构建高质量 prompt：
  image.prompt_base  → 视觉核心 (外貌/穿搭/场景)
  image.style        → 风格 (realistic/anime/watercolor...)
  tags               → 气质关键词
  bio                → 性格/背景补充
  gender / age       → 人物一致性
"""

from __future__ import annotations


_AVATAR_PROMPT_TEMPLATE = """Portrait of "{name}", {prompt_base}
Character traits: {traits}.
{bio_line}
Style: {style} portrait, high quality, detailed face, professional lighting.
Aspect ratio: 1:1 square portrait headshot."""

_STYLE_MODIFIERS = {
    "realistic": "photorealistic, soft studio lighting, shallow depth of field",
    "anime": "anime style, cel shading, vibrant colors, clean lines",
    "watercolor": "watercolor painting, soft edges, artistic brush strokes",
    "illustration": "digital illustration, semi-realistic, artstation quality",
}


def build_avatar_prompt(persona) -> str:
    """
    Build a rich image generation prompt from Persona object.

    Combines prompt_base + tags + bio + mbti + style for better quality.
    """
    # Core visual description
    prompt_base = (persona.image.prompt_base or "").strip()
    if not prompt_base:
        gender_word = "girl" if persona.gender == "female" else "boy"
        prompt_base = f"a {persona.age or 20}-year-old {gender_word}"

    # Traits from tags + mbti
    traits_parts = []
    if persona.tags:
        traits_parts.append(", ".join(persona.tags))
    if persona.mbti:
        traits_parts.append(f"{persona.mbti} personality type")
    traits = "; ".join(traits_parts) if traits_parts else "natural expression"

    # Bio
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

    neg = persona.image.negative_prompt
    if neg:
        prompt += f"\nAvoid: {neg}"

    return prompt.strip()
