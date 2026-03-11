"""
Gemini Image Generation — Google Gemini gemini-3.1-flash-image-preview.

使用 google-genai SDK 通过 stream 方式生成图片。
支持 aspect_ratio、image_size、person_generation 参数。
"""

from __future__ import annotations

import asyncio
import mimetypes
import os
import time
from typing import Optional

from .base import BaseImageProvider, ImageResult


class GeminiImageProvider(BaseImageProvider):
    """Google Gemini image generation (gemini-3.1-flash-image-preview)."""

    PROVIDER_NAME = "gemini"
    DEFAULT_MODEL = "gemini-3.1-flash-image-preview"

    def __init__(
        self,
        cache_dir: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(cache_dir=cache_dir, **kwargs)
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self._model = model or self.DEFAULT_MODEL
        self._client = None

    @property
    def client(self):
        """Lazy-load Gemini client."""
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def generate(
        self,
        prompt: str,
        aspect_ratio: str = "",
        image_size: str = "1K",
        person_generation: str = "",
        reference_image: Optional[str] = None,
        **kwargs,
    ) -> ImageResult:
        """
        Generate an image from a text prompt using Gemini.

        Args:
            prompt: Text description of the image to generate.
            aspect_ratio: Aspect ratio (e.g. "16:9", "9:16"). Empty = omit.
            image_size: Output size ("1K", "2K"). Default "1K".
            person_generation: Person generation mode. Empty = omit.
            reference_image: Path to a reference image for consistency.

        Returns:
            ImageResult with image_path and optional text.
        """
        if not self._api_key:
            return ImageResult(success=False, error="Gemini API key not set (GEMINI_API_KEY)")

        start_time = time.time()

        try:
            from google.genai import types

            # Build content parts: reference image (if any) + text prompt
            parts = []

            if reference_image and os.path.exists(reference_image):
                # Load image as bytes
                with open(reference_image, "rb") as f:
                    image_bytes = f.read()
                # Detect MIME type
                ext = os.path.splitext(reference_image)[1].lower()
                mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}
                mime = mime_map.get(ext, 'image/png')
                parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
                print(f"  [gemini] 🖼 Reference image loaded: {os.path.basename(reference_image)}")

            parts.append(types.Part.from_text(text=prompt))

            contents = [
                types.Content(role="user", parts=parts),
            ]

            # Build image config dynamically (only include non-empty params)
            image_cfg_kwargs = {}
            if aspect_ratio:
                image_cfg_kwargs["aspect_ratio"] = aspect_ratio
            if image_size:
                image_cfg_kwargs["image_size"] = image_size
            if person_generation:
                image_cfg_kwargs["person_generation"] = person_generation

            config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
                image_config=types.ImageConfig(**image_cfg_kwargs),
                response_modalities=["IMAGE", "TEXT"],
            )

            # Run sync stream in executor to avoid blocking event loop
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._generate_sync(contents, config, prompt),
            )

            result.latency_ms = (time.time() - start_time) * 1000
            return result

        except Exception as e:
            return ImageResult(
                success=False,
                error=str(e),
                provider=self.PROVIDER_NAME,
                latency_ms=(time.time() - start_time) * 1000,
            )

    def _generate_sync(self, contents, config, prompt: str) -> ImageResult:
        """Synchronous generation (runs in executor)."""
        text_parts = []
        image_path = None
        mime_type = "image/png"

        for chunk in self.client.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=config,
        ):
            if chunk.parts is None:
                continue

            for part in chunk.parts:
                if part.inline_data and part.inline_data.data:
                    # Save image
                    inline_data = part.inline_data
                    mime_type = inline_data.mime_type or "image/png"
                    ext = mimetypes.guess_extension(mime_type) or ".png"
                    # Remove leading dot from ext if _cache_path already adds it
                    ext = ext.lstrip(".")

                    image_path = self._cache_path(
                        f"gemini:{prompt}:{self._model}", ext=ext,
                    )

                    with open(image_path, "wb") as f:
                        f.write(inline_data.data)

                elif part.text:
                    text_parts.append(part.text)

        if image_path:
            return ImageResult(
                success=True,
                image_path=image_path,
                mime_type=mime_type,
                text="".join(text_parts) if text_parts else None,
                provider=self.PROVIDER_NAME,
            )
        else:
            return ImageResult(
                success=False,
                error="No image generated" + (f": {''.join(text_parts)}" if text_parts else ""),
                text="".join(text_parts) if text_parts else None,
                provider=self.PROVIDER_NAME,
            )
