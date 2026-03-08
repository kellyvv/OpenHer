"""
AvatarService — 后台管理唯一入口.

组合 repository + image_provider + invalidation，
提供 Avatar 全生命周期 CRUD。

Usage:
    service = AvatarService(personas_dir="persona/personas", persona_loader=loader)
    status = service.get_config("iris")
    result = await service.generate("iris", force=True)
    service.delete("iris")
    all_status = service.list_all()
"""

from __future__ import annotations

import os
from typing import Optional

from .models import AvatarConfig, AvatarStatus
from .repository import AvatarRepository
from .prompt_builder import build_avatar_prompt
from .invalidation import reload_persona


class AvatarService:
    """Avatar management service (后台管理唯一入口)."""

    def __init__(self, personas_dir: str, persona_loader):
        """
        Args:
            personas_dir: Absolute path to personas data directory.
            persona_loader: PersonaLoader instance (for reading full Persona objects).
        """
        self.personas_dir = personas_dir
        self.persona_loader = persona_loader
        self.repo = AvatarRepository(personas_dir)

    # ─── Read ───

    def get_config(self, persona_id: str) -> AvatarStatus:
        """Get current avatar config + file status for a persona."""
        persona = self.persona_loader.get(persona_id)
        if not persona:
            raise ValueError(f"Persona '{persona_id}' not found")

        config = self.repo.read_config(persona_id)
        avatar_path = self.repo.get_avatar_path(persona_id)

        return AvatarStatus(
            persona_id=persona_id,
            persona_name=persona.name,
            config=config,
            has_avatar=avatar_path is not None,
            avatar_path=avatar_path,
        )

    def list_all(self) -> list[AvatarStatus]:
        """List avatar status for all personas (from PersonaLoader, not directory scan)."""
        personas = self.persona_loader.load_all()
        result = []
        for pid in personas:
            try:
                status = self.get_config(pid)
                result.append(status)
            except Exception as e:
                print(f"  ⚠ Failed to get avatar config for {pid}: {e}")
        return result

    # ─── Write ───

    def update_config(
        self,
        persona_id: str,
        prompt_base: Optional[str] = None,
        style: Optional[str] = None,
        negative_prompt: Optional[str] = None,
    ) -> AvatarConfig:
        """Update avatar config → write back to PERSONA.md → reload cache."""
        # Read current
        current = self.repo.read_config(persona_id)

        # Merge updates
        updated = AvatarConfig(
            prompt_base=prompt_base if prompt_base is not None else current.prompt_base,
            style=style if style is not None else current.style,
            negative_prompt=negative_prompt if negative_prompt is not None else current.negative_prompt,
        )

        # Write back to PERSONA.md
        self.repo.write_config(persona_id, updated)

        # Reload persona cache so loader returns fresh data
        reload_persona(self.persona_loader, persona_id)

        return updated

    # ─── Generate ───

    async def generate(self, persona_id: str, force: bool = False):
        """Generate avatar for a persona.

        Forces reload_persona() before prompt building to guarantee
        fresh image.* values from disk.
        """
        from providers.registry import get_image_gen
        from providers.image.base import ImageResult

        # Force reload to guarantee fresh data
        reload_persona(self.persona_loader, persona_id)
        persona = self.persona_loader.get(persona_id)
        if not persona:
            raise ValueError(f"Persona '{persona_id}' not found")

        # Skip if exists (unless forced)
        avatar_path = self.repo.get_avatar_path(persona_id)
        if not force and avatar_path:
            return ImageResult(
                success=True,
                image_path=avatar_path,
                provider="cached",
            )

        # Build prompt & generate
        prompt = build_avatar_prompt(persona)
        print(f"  🎨 生成头像: {persona.name} ({persona_id})")
        print(f"     Prompt: {prompt[:80]}...")

        provider = get_image_gen(
            cache_dir=os.path.join(self.personas_dir, ".cache", "avatar"),
        )
        result = await provider.generate(
            prompt=prompt,
            aspect_ratio="1:1",
            image_size="1K",
        )

        if result.success and result.image_path:
            saved = self.repo.save_avatar_file(persona_id, result.image_path)
            result.image_path = saved
            print(f"  ✅ 保存到: {saved}")
        else:
            print(f"  ❌ 生成失败: {result.error}")

        return result

    async def generate_all(self, force: bool = False) -> dict:
        """Generate avatars for all personas."""
        personas = self.persona_loader.load_all()
        results = {}

        for pid in personas:
            result = await self.generate(pid, force=force)
            results[pid] = result

        ok = sum(1 for r in results.values() if r.success)
        print(f"\n  📊 头像生成: {ok}/{len(results)} 成功")
        return results

    # ─── Delete ───

    def delete(self, persona_id: str) -> bool:
        """Delete avatar.png for a persona."""
        deleted = self.repo.delete_avatar_file(persona_id)
        if deleted:
            print(f"  🗑 已删除: {persona_id}/avatar.png")
        return deleted
