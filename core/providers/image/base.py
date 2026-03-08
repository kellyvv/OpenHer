"""
BaseImageProvider — 图片生成统一接口.

公共类型 ImageResult 定义在此。
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ImageResult:
    """Result of an image generation."""
    success: bool
    image_path: Optional[str] = None    # Path to generated image file
    image_bytes: Optional[bytes] = None
    mime_type: str = "image/png"
    text: Optional[str] = None          # Model text response (if any)
    provider: str = ""
    latency_ms: float = 0
    error: Optional[str] = None


class BaseImageProvider(ABC):
    """Image generation provider 统一接口."""

    PROVIDER_NAME: str = ""

    def __init__(self, cache_dir: str, **kwargs):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        aspect_ratio: str = "",
        image_size: str = "1K",
        **kwargs,
    ) -> ImageResult:
        """Generate an image from a text prompt."""
        ...

    def _cache_path(self, key_parts: str, ext: str = "png") -> str:
        """Generate cache file path from key parts."""
        cache_key = hashlib.md5(key_parts.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{cache_key}.{ext}")
