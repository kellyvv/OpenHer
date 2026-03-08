"""
SoulMem Provider — 行为记忆 (指导怎么做).

SQLite FTS5 本地记忆存储。常驻层，总是启用。
当前阶段仅定义接口，facade (memory_store.py) 保留不动。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .types import Memory


class BaseSoulMem(ABC):
    """SoulMem 行为记忆接口 — 常驻层."""

    @abstractmethod
    def add(
        self,
        user_id: str,
        persona_id: str,
        content: str,
        category: str = "conversation",
        importance: float = 0.5,
        source_turn: int = 0,
    ) -> int:
        """Add a memory entry. Returns the memory ID."""
        ...

    @abstractmethod
    def search(
        self,
        user_id: str,
        persona_id: str,
        query: str,
        limit: int = 5,
    ) -> list[Memory]:
        """Search memories using FTS5 full-text search."""
        ...

    @abstractmethod
    def build_memory_context(
        self,
        user_id: str,
        persona_id: str,
        current_query: str = "",
        max_items: int = 8,
    ) -> Optional[str]:
        """Build a memory context string for prompt injection."""
        ...

    @abstractmethod
    def close(self):
        """Close the memory store."""
        ...
