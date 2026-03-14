"""
Selfie Generation Handler — 角色自拍/照片生成。

职责：只做解析 + 传参。
- 从 Actor Express 输出中解析：场景描述、比例
- 选择合适的 idimage/ 参考图
- 传递给图像生成 API

所有 prompt 约束（风格、构图等）由 SKILL.md 注入，
LLM 在 Actor 阶段已经完成了场景描述和比例选择。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional


# ── Parsing regex ──
# 照片｜比例：9:16  or  照片：xxx
_RATIO_RE = re.compile(r'比例[：:]\s*([\d]+[：:]\d+)')
_DESC_RE = re.compile(r'描述[：:]\s*(.+?)(?:\n|理由[：:]|$)', re.DOTALL)
_PHOTO_SIMPLE_RE = re.compile(r'照片[：:]\s*(.+?)(?:\n|理由[：:]|$)', re.DOTALL)


def parse_photo_output(modality_text: str) -> dict:
    """Parse Actor's photo modality output.

    Returns:
        {
            'description': str,   # scene description
            'aspect_ratio': str,  # e.g. '9:16', '' if not specified
        }
    """
    # Try structured format first: 照片｜比例：9:16  描述：xxx
    ratio_m = _RATIO_RE.search(modality_text)
    aspect_ratio = ratio_m.group(1).replace('：', ':') if ratio_m else ''

    desc_m = _DESC_RE.search(modality_text)
    if desc_m:
        description = desc_m.group(1).strip()
    else:
        # Fallback: simple format 照片：xxx
        simple_m = _PHOTO_SIMPLE_RE.search(modality_text)
        description = simple_m.group(1).strip() if simple_m else ''

    return {
        'description': description,
        'aspect_ratio': aspect_ratio,
    }


# Keep backward compat alias
def parse_photo_description(modality_text: str) -> Optional[str]:
    """Extract photo scene description (backward compat)."""
    result = parse_photo_output(modality_text)
    return result['description'] or None


def get_idimage_dir(persona_id: str) -> Path:
    """Get the idimage directory for a persona."""
    base = Path(__file__).resolve().parents[2]
    return base / "persona" / "personas" / persona_id / "idimage"


def list_reference_images(persona_id: str) -> dict[str, str]:
    """List available reference images for a persona.

    Returns:
        Dict of {name: absolute_path}, e.g. {"face": "/path/to/face.png"}
    """
    idimage_dir = get_idimage_dir(persona_id)
    if not idimage_dir.exists():
        return {}

    refs = {}
    for f in idimage_dir.iterdir():
        if f.is_file() and f.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
            refs[f.stem] = str(f)
    return refs


def select_reference_image(persona_id: str) -> Optional[str]:
    """Select the best reference image for generation.

    Priority: face > fullbody > multi_view > front > any
    """
    refs = list_reference_images(persona_id)
    if not refs:
        return None

    for preference in ['face', 'fullbody', 'multi_view', 'front']:
        if preference in refs:
            return refs[preference]

    return next(iter(refs.values()))


async def generate_selfie(
    persona_id: str,
    raw_output: str = "",
    persona_name: str = "",
    # Backward compat params (used if raw_output is empty)
    scene_description: str = "",
    image_size: str = "1K",
    aspect_ratio: str = "",
    **kwargs,
) -> dict:
    """Generate a selfie/photo for the persona.

    Unified handler interface — called by ModalitySkillEngine.execute().
    Accepts raw_output (LLM structured text) and parses internally.
    Also accepts legacy params (scene_description, aspect_ratio) for backward compat.

    Args:
        persona_id: Persona identifier
        raw_output: LLM structured output to parse (new unified interface)
        persona_name: Display name
        scene_description: Legacy: direct scene description (fallback if raw_output empty)
        image_size: Output size (default "1K")
        aspect_ratio: Legacy: direct aspect ratio (fallback)

    Returns:
        Dict with keys: success, image_path, error, aspect_ratio, reference_used
    """
    from providers.registry import get_image_gen

    # Parse from raw_output (unified interface) if available
    if raw_output and not scene_description:
        parsed = parse_photo_output(raw_output)
        scene_description = parsed['description']
        aspect_ratio = aspect_ratio or parsed['aspect_ratio']

    if not scene_description:
        return {"success": False, "image_path": None, "error": "No scene description"}

    # Select reference image
    ref_image_path = select_reference_image(persona_id)
    if ref_image_path:
        print(f"  [selfie] 🖼 Reference: {os.path.basename(ref_image_path)}")
    else:
        print(f"  [selfie] ⚠ No reference images for {persona_id}")

    if aspect_ratio:
        print(f"  [selfie] 📐 Aspect ratio: {aspect_ratio}")

    # Get image provider
    try:
        provider = get_image_gen(
            cache_dir=str(
                Path(__file__).resolve().parents[2] / ".cache" / "selfie" / persona_id
            ),
        )
    except ValueError as e:
        return {"success": False, "error": str(e)}

    # Generate: scene description as prompt, reference image for consistency
    result = await provider.generate(
        prompt=scene_description,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        reference_image=ref_image_path,
    )

    return {
        "success": result.success,
        "image_path": result.image_path,
        "error": result.error,
        "aspect_ratio": aspect_ratio,
        "reference_used": os.path.basename(ref_image_path) if ref_image_path else None,
        "latency_ms": result.latency_ms,
    }
