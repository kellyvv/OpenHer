"""
Invalidation — persona_loader 缓存刷新.

Avatar 配置写回 PERSONA.md 后，调用此模块刷新 loader 缓存，
使后续 persona_loader.get() 返回最新数据。
"""

from __future__ import annotations


def reload_persona(persona_loader, persona_id: str) -> None:
    """Reload a single persona from disk into loader cache."""
    persona_loader.reload(persona_id)
    print(f"  ↻ Persona '{persona_id}' reloaded from disk")
