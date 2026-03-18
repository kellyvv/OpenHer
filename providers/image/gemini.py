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

    @staticmethod
    def _load_and_compress_reference(
        path: str,
        max_px: int = 1024,
        quality: int = 85,
        threshold_kb: int = 500,
    ) -> tuple[bytes, str]:
        """Load and auto-compress a reference image for Gemini API.

        Large PNGs (>500KB) cause Gemini to silently return empty responses.
        Compresses to JPEG with max longest-side 1024px.

        Returns: (image_bytes, mime_type)
        """
        raw_size = os.path.getsize(path)

        # Skip compression if already small enough
        if raw_size <= threshold_kb * 1024:
            with open(path, "rb") as f:
                data = f.read()
            ext = os.path.splitext(path)[1].lower()
            mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}
            return data, mime_map.get(ext, 'image/png')

        try:
            from PIL import Image
            import io

            img = Image.open(path)
            # Convert RGBA → RGB (JPEG doesn't support alpha)
            if img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')

            # Resize if larger than max_px on longest side
            w, h = img.size
            if max(w, h) > max_px:
                ratio = max_px / max(w, h)
                new_w, new_h = int(w * ratio), int(h * ratio)
                img = img.resize((new_w, new_h), Image.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=quality)
            compressed = buf.getvalue()

            print(
                f"  [gemini] 📦 Reference compressed: "
                f"{raw_size/1024:.0f}KB → {len(compressed)/1024:.0f}KB "
                f"({img.size[0]}x{img.size[1]})"
            )
            return compressed, 'image/jpeg'

        except ImportError:
            print("  [gemini] ⚠ Pillow not installed, using raw image")
            with open(path, "rb") as f:
                return f.read(), 'image/png'
        except Exception as e:
            print(f"  [gemini] ⚠ Compression failed ({e}), using raw image")
            with open(path, "rb") as f:
                data = f.read()
            ext = os.path.splitext(path)[1].lower()
            mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}
            return data, mime_map.get(ext, 'image/png')

    async def generate(
        self,
        prompt: str,
        aspect_ratio: str = "",
        image_size: str = "1K",
        person_generation: str = "",
        reference_images: Optional[list[str]] = None,
        **kwargs,
    ) -> ImageResult:
        """
        Generate an image from a text prompt using Gemini.

        Args:
            prompt: Text description of the image to generate.
            aspect_ratio: Aspect ratio (e.g. "16:9", "9:16"). Empty = omit.
            image_size: Output size ("1K", "2K"). Default "1K".
            person_generation: Person generation mode. Empty = omit.
            reference_images: List of paths to reference images for consistency.

        Returns:
            ImageResult with image_path and optional text.
        """
        if not self._api_key:
            return ImageResult(success=False, error="Gemini API key not set (GEMINI_API_KEY)")

        start_time = time.time()

        try:
            from google.genai import types

            # Backward compat: accept legacy reference_image kwarg
            if kwargs.get("reference_image") and not reference_images:
                reference_images = [kwargs["reference_image"]]

            # Build content parts: reference images (if any) + text prompt
            parts = []

            for ref_path in (reference_images or []):
                if ref_path and os.path.exists(ref_path):
                    # Auto-compress: large PNGs cause Gemini to silently return empty
                    image_bytes, mime = self._load_and_compress_reference(ref_path)
                    parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
                    print(f"  [gemini] 🖼 Reference image loaded: {os.path.basename(ref_path)} ({len(image_bytes)/1024:.0f}KB, {mime})")

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

            # Run sync stream in executor with retry for transient errors
            max_retries = 2
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self._generate_sync(contents, config, prompt),
                    )
                    result.latency_ms = (time.time() - start_time) * 1000
                    return result
                except (ConnectionError, OSError, TimeoutError) as e:
                    last_error = e
                    if attempt < max_retries:
                        wait = 2 ** attempt
                        print(f"  [gemini] ⚠ Retry {attempt+1}/{max_retries} after {type(e).__name__}: {e}")
                        await asyncio.sleep(wait)
                    continue

            return ImageResult(
                success=False,
                error=f"Failed after {max_retries} retries: {last_error}",
                provider=self.PROVIDER_NAME,
                latency_ms=(time.time() - start_time) * 1000,
            )

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
        chunk_count = 0

        print(f"  [gemini] 📡 Streaming from model={self._model}, prompt={prompt[:80]}...")

        for chunk in self.client.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=config,
        ):
            chunk_count += 1
            if chunk.parts is None:
                # Log blocked/empty chunks for debugging
                if hasattr(chunk, 'candidates') and chunk.candidates:
                    for c in chunk.candidates:
                        if hasattr(c, 'finish_reason') and c.finish_reason:
                            print(f"  [gemini] ⚠ chunk #{chunk_count} finish_reason: {c.finish_reason}")
                        if hasattr(c, 'safety_ratings') and c.safety_ratings:
                            blocked = [r for r in c.safety_ratings if getattr(r, 'blocked', False)]
                            if blocked:
                                print(f"  [gemini] 🚫 safety blocked: {blocked}")
                else:
                    print(f"  [gemini] ⚠ chunk #{chunk_count}: no parts, no candidates")
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
                    print(f"  [gemini] ✅ image received: {len(inline_data.data)/1024:.0f}KB, mime={mime_type}")

                elif part.text:
                    text_parts.append(part.text)
                    print(f"  [gemini] 📝 text: {part.text[:120]}")

        print(f"  [gemini] 📊 Stream done: {chunk_count} chunks, image={'YES' if image_path else 'NO'}, text_parts={len(text_parts)}")

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
