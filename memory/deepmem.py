"""
DeepMem Provider — 陈述记忆 (记住做了什么).

深层记忆增强层。当前供应商: EverMemOS (HTTP)。
接口定义，facade (evermemos_client.py) 保留不动。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .types import SessionContext


class BaseDeepMem(ABC):
    """DeepMem 陈述记忆接口 — 可选增强层."""

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether the DeepMem backend is available."""
        ...

    @abstractmethod
    async def load_session_context(
        self,
        user_id: str,
        persona_id: str,
    ) -> SessionContext:
        """Load session context (profile, episodes, foresight)."""
        ...

    @abstractmethod
    def relationship_vector(self, ctx: SessionContext) -> dict:
        """Build 4D relationship prior vector from session context."""
        ...

    @abstractmethod
    async def store_turn(
        self,
        user_id: str,
        persona_id: str,
        persona_name: str,
        user_name: str,
        group_id: str,
        user_message: str,
        agent_reply: str,
    ) -> None:
        """Store one conversation turn (fire-and-forget)."""
        ...

    @abstractmethod
    async def store_proactive_turn(
        self,
        persona_id: str,
        persona_name: str,
        group_id: str,
        reply: str,
        tick_id: str,
    ) -> None:
        """Store a proactive message (AI-initiated)."""
        ...

    @abstractmethod
    async def close_session(
        self,
        user_id: str,
        persona_id: str,
        group_id: str,
    ) -> None:
        """Signal session end to DeepMem backend."""
        ...

    @abstractmethod
    async def search_relevant_memories(
        self,
        query: str,
        user_id: str,
    ) -> tuple:
        """
        Search for memories relevant to current user message.

        Returns: (relevant_facts, relevant_episodes, relevant_profile)
        """
        ...
