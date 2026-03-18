"""
Photo tools — atomic tools for selfie/photo generation.

Migrated from skills/modality/selfie_gen/handler.py.
Registered into ToolRegistry at startup.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from agent.skills.tool_registry import Tool, ToolRegistry


# ── Constants ──

_VALID_REFERENCE_TYPES = {"face", "fullbody", "multi_view", "last_generated"}
_VALID_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _is_valid_reference_type(ref_type: str) -> bool:
    """Check if a reference type is valid (includes scene: prefix)."""
    return ref_type in _VALID_REFERENCE_TYPES or ref_type.startswith("scene:")


# ── Internal helpers ──

def _get_idimage_dir(persona_id: str) -> Path:
    """Get the idimage directory for a persona."""
    base = Path(__file__).resolve().parents[3]  # openher-docker/
    return base / "persona" / "personas" / persona_id / "idimage"


def _find_reference_image(persona_id: str, reference_type: str) -> Optional[str]:
    """Find a specific reference image by type.

    Supports:
    - Standard types: face, fullbody, multi_view → {type}.{ext} in idimage/
    - last_generated → most recent file in .cache/selfie/{persona_id}/
    - scene:{name} → scene_{name}.{ext} in idimage/

    Returns absolute path or None.
    """
    # last_generated → find most recent cached photo
    if reference_type == "last_generated":
        base = Path(__file__).resolve().parents[3]  # openher-docker/
        cache_dir = base / ".cache" / "selfie" / persona_id
        if cache_dir.exists():
            files = sorted(
                [f for f in cache_dir.glob("*.*") if f.suffix.lower() in _VALID_EXTENSIONS],
                key=lambda f: f.stat().st_mtime, reverse=True,
            )
            return str(files[0]) if files else None
        return None

    # scene:{name} → scene_{name}.{ext} in idimage/
    if reference_type.startswith("scene:"):
        scene_name = reference_type.split(":", 1)[1]
        idimage_dir = _get_idimage_dir(persona_id)
        if not idimage_dir.exists():
            return None
        for ext in _VALID_EXTENSIONS:
            candidate = idimage_dir / f"scene_{scene_name}{ext}"
            if candidate.exists():
                return str(candidate)
        return None

    # Standard types: {reference_type}.{ext} in idimage/
    idimage_dir = _get_idimage_dir(persona_id)
    if not idimage_dir.exists():
        return None

    for ext in _VALID_EXTENSIONS:
        candidate = idimage_dir / f"{reference_type}{ext}"
        if candidate.exists():
            return str(candidate)
    return None


# ── Tool: get_reference_image ──

async def _get_reference_image(persona_id: str, reference_type: str) -> dict:
    """Retrieve a specific reference image for a persona.

    Args:
        persona_id: Persona identifier (e.g. "luna", "iris").
        reference_type: Type of reference image (face, fullbody, multi_view,
                        last_generated, scene:bedroom, scene:kitchen, etc.).

    Returns:
        {image_path: str | null, reference_type: str, available: bool}
    """
    if not _is_valid_reference_type(reference_type):
        return {
            "image_path": None,
            "reference_type": reference_type,
            "available": False,
            "error": f"Invalid reference_type '{reference_type}'. "
                     f"Valid: {sorted(_VALID_REFERENCE_TYPES)} or scene:{{name}}",
        }

    path = _find_reference_image(persona_id, reference_type)
    if path:
        print(f"  [tool] 🖼 get_reference_image: {persona_id}/{reference_type} → {os.path.basename(path)}")
    else:
        print(f"  [tool] ⚠ get_reference_image: {persona_id}/{reference_type} not found")

    return {
        "image_path": path,
        "reference_type": reference_type,
        "available": path is not None,
    }


# ── Tool: generate_photo ──

async def _generate_photo(
    prompt: str,
    persona_id: str = "",
    aspect_ratio: str = "",
    reference_images: list = None,
) -> dict:
    """Generate a photo using image generation API.

    Args:
        prompt: Scene description in third person.
        persona_id: Persona identifier (for cache path).
        aspect_ratio: Image aspect ratio (e.g. "9:16", "16:9", "3:4").
        reference_images: List of absolute paths to reference images.

    Returns:
        {success: bool, image_path: str | null, error: str | null, latency_ms: int}
    """
    if not prompt:
        return {"success": False, "image_path": None, "error": "No prompt provided"}

    from providers.registry import get_image_gen

    ref_count = len(reference_images) if reference_images else 0
    print(f"  [tool] 📷 generate_photo: ratio={aspect_ratio}, refs={ref_count}")

    try:
        cache_dir = str(
            Path(__file__).resolve().parents[3] / ".cache" / "selfie" / persona_id
        )
        provider = get_image_gen(cache_dir=cache_dir)

        result = await provider.generate(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            image_size="1K",
            reference_images=reference_images or None,
        )

        return {
            "success": result.success,
            "image_path": result.image_path,
            "error": result.error,
            "aspect_ratio": aspect_ratio,
            "latency_ms": result.latency_ms,
        }
    except Exception as e:
        print(f"  [tool] ❌ generate_photo error: {e}")
        return {"success": False, "image_path": None, "error": str(e)}


# ── Registration ──

def register_photo_tools(registry: ToolRegistry) -> None:
    """Register photo tools into the global registry."""

    registry.register(Tool(
        name="get_reference_image",
        description="获取角色的参考图。根据 reference_type 返回对应的参考图路径。",
        parameters={
            "type": "object",
            "properties": {
                "persona_id": {
                    "type": "string",
                    "description": "角色 ID（如 luna, iris）",
                },
                "reference_type": {
                    "type": "string",
                    "description": "参考图类型：face / fullbody / multi_view / last_generated / scene:{name}",
                },
            },
            "required": ["persona_id", "reference_type"],
        },
        handler=_get_reference_image,
    ))

    registry.register(Tool(
        name="generate_photo",
        description="使用图像生成 API 生成一张照片。可选传入多张参考图保持角色和场景一致性。",
        parameters={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "第三人称场景描述（含表情、动作、场景、光线、视角）",
                },
                "persona_id": {
                    "type": "string",
                    "description": "角色 ID，用于缓存路径",
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": "图片比例，如 9:16、16:9、3:4、4:3",
                },
                "reference_images": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "参考图绝对路径列表（角色参考图 + 上次照片 + 场景参考图等，可多张）",
                },
            },
            "required": ["prompt"],
        },
        handler=_generate_photo,
    ))
