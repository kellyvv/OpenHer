"""
EverMemOS Client — 长期记忆适配器

将 EverMemOS Cloud API 接入 OpenHer 养成系统。
提供与 MemoryStore 兼容的接口，同时利用 EverMemOS 的高级能力：
  - Episode Memory（叙事性记忆摘要）
  - Profile（用户画像自动构建）
  - 语义 + 关键词混合检索
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Optional

try:
    from evermemos import EverMemOS
except ImportError:
    EverMemOS = None


@dataclass
class MemorySearchResult:
    """A single memory search result."""
    content: str
    memory_type: str = ""
    score: float = 0.0


class EverMemOSClient:
    """
    EverMemOS Cloud API adapter for OpenHer.

    Drop-in enhancement alongside the existing MemoryStore.
    Provides the same `build_memory_context()` interface
    that ChatAgent uses for prompt injection.
    """

    def __init__(self, api_key: Optional[str] = None):
        api_key = api_key or os.getenv("EVERMEMOS_API_KEY", "")
        if not api_key:
            print("⚠ EverMemOS: No API key found. Set EVERMEMOS_API_KEY in .env")
            self.client = None
            self.memory = None
            return

        if EverMemOS is None:
            print("⚠ EverMemOS: SDK not installed. Run: pip install evermemos")
            self.client = None
            self.memory = None
            return

        self.client = EverMemOS(api_key=api_key)
        self.memory = self.client.v0.memories
        print("✓ EverMemOS client initialized")

    @property
    def available(self) -> bool:
        return self.memory is not None

    # ──────────────────────────────────────────────
    # Store: Save conversation messages
    # ──────────────────────────────────────────────

    def store_message(
        self,
        user_id: str,
        persona_id: str,
        sender: str,
        sender_name: str,
        content: str,
        is_flush: bool = False,
    ) -> bool:
        """
        Store a single conversation message to EverMemOS.

        Args:
            user_id: The user's ID
            persona_id: The persona's ID (used as group_id for conversation boundary)
            sender: Who sent this message (user_id or persona_id)
            sender_name: Display name of the sender
            content: Message text
            is_flush: If True, marks end of conversation → triggers memory extraction
        """
        if not self.available:
            return False

        msg_id = f"msg_{user_id}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"

        try:
            kwargs = {
                "message_id": msg_id,
                "create_time": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                "sender": sender,
                "sender_name": sender_name,
                "group_id": f"{user_id}_{persona_id}",
                "content": content,
            }
            if is_flush:
                kwargs["flush"] = "true"

            response = self.memory.add(**kwargs)
            return True
        except Exception as e:
            print(f"⚠ EverMemOS store error: {e}")
            return False

    def store_conversation(
        self,
        user_id: str,
        persona_id: str,
        user_name: str,
        persona_name: str,
        user_message: str,
        agent_response: str,
        is_session_end: bool = False,
    ) -> bool:
        """
        Store a complete user-agent exchange (both messages).
        Called after each chat turn.
        """
        if not self.available:
            return False

        # Store user message
        self.store_message(
            user_id=user_id,
            persona_id=persona_id,
            sender=user_id,
            sender_name=user_name or "用户",
            content=user_message,
        )

        # Store agent response (flush if session ending)
        self.store_message(
            user_id=user_id,
            persona_id=persona_id,
            sender=persona_id,
            sender_name=persona_name,
            content=agent_response,
            is_flush=is_session_end,
        )

        return True

    # ──────────────────────────────────────────────
    # Search: Retrieve relevant memories
    # ──────────────────────────────────────────────

    @staticmethod
    def _extract_memory(mem_obj) -> Optional[MemorySearchResult]:
        """
        Extract a MemorySearchResult from an EverMemOS SDK response object.

        SDK returns objects like ResultMemoryEpisodicMemoryModel with:
          .episode / .summary — the narrative text
          .subject — short title
          .memory_type — "episodic_memory", "event_log", etc.
          .score — relevance score (search only)
        """
        # Try known SDK object attributes
        content = (
            getattr(mem_obj, "episode", None)
            or getattr(mem_obj, "summary", None)
            or getattr(mem_obj, "content", None)
            or getattr(mem_obj, "subject", None)
        )

        # Fallback for dict format
        if content is None and isinstance(mem_obj, dict):
            content = (
                mem_obj.get("episode")
                or mem_obj.get("summary")
                or mem_obj.get("content")
                or mem_obj.get("subject", "")
            )

        if not content:
            return None

        # Get memory type
        mem_type = getattr(mem_obj, "memory_type", None)
        if mem_type is None and hasattr(mem_obj, "metadata") and mem_obj.metadata:
            mem_type = getattr(mem_obj.metadata, "memory_type", "")
        if mem_type is None and isinstance(mem_obj, dict):
            mem_type = mem_obj.get("memory_type", "")

        score = getattr(mem_obj, "score", 0.0) or 0.0

        return MemorySearchResult(
            content=str(content),
            memory_type=str(mem_type or ""),
            score=float(score),
        )

    def search(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[MemorySearchResult]:
        """
        Search for relevant memories using hybrid retrieval.
        """
        if not self.available:
            return []

        try:
            response = self.memory.search(
                extra_query={
                    "user_id": user_id,
                    "query": query,
                }
            )

            results = []
            seen_ids = set()
            if response.result and response.result.memories:
                for mem_obj in response.result.memories:
                    # Deduplicate by episode_id
                    eid = getattr(mem_obj, "episode_id", None) or getattr(mem_obj, "id", None)
                    if eid and eid in seen_ids:
                        continue
                    if eid:
                        seen_ids.add(eid)

                    result = self._extract_memory(mem_obj)
                    if result:
                        results.append(result)

            return results[:top_k]
        except Exception as e:
            print(f"⚠ EverMemOS search error: {e}")
            return []

    def get_profile(self, user_id: str) -> list[MemorySearchResult]:
        """
        Get the user's profile/core memories (direct key-value lookup).
        """
        if not self.available:
            return []

        try:
            response = self.memory.get(
                extra_query={"user_id": user_id}
            )

            results = []
            seen_ids = set()
            if response.result and response.result.memories:
                for mem_obj in response.result.memories:
                    eid = getattr(mem_obj, "episode_id", None) or getattr(mem_obj, "id", None)
                    if eid and eid in seen_ids:
                        continue
                    if eid:
                        seen_ids.add(eid)

                    result = self._extract_memory(mem_obj)
                    if result:
                        results.append(result)

            return results
        except Exception as e:
            print(f"⚠ EverMemOS profile error: {e}")
            return []

    # ──────────────────────────────────────────────
    # build_memory_context: Compatible interface
    # ──────────────────────────────────────────────

    def build_memory_context(
        self,
        user_id: str,
        persona_id: str,
        current_query: str = "",
        max_items: int = 6,
        max_chars_per_item: int = 120,
        max_total_chars: int = 800,
    ) -> Optional[str]:
        """
        Build memory context string for system prompt injection.
        Drop-in compatible with MemoryStore.build_memory_context().

        Controls to prevent prompt bloat:
        - max_items: max number of memory entries (default 6)
        - max_chars_per_item: truncate each memory to this length (default 120)
        - max_total_chars: total context cap (default 800 ≈ ~400 tokens)

        Strategy:
        1. Get user profile (core facts, max 3)
        2. Search for query-relevant memories (fill remaining slots)
        3. Truncate and format
        """
        if not self.available:
            return None

        lines = []
        seen = set()
        total_chars = 0

        def _truncate(text: str) -> str:
            if len(text) <= max_chars_per_item:
                return text
            return text[:max_chars_per_item - 3] + "..."

        def _add_line(label: str, content: str) -> bool:
            nonlocal total_chars
            truncated = _truncate(content)
            line = f"- {label}{truncated}"
            if total_chars + len(line) > max_total_chars:
                return False
            lines.append(line)
            total_chars += len(line)
            seen.add(content[:60])  # dedup by prefix
            return True

        # 1. Profile / core facts (max 3)
        profile = self.get_profile(user_id)
        for mem in profile[:3]:
            if mem.content[:60] not in seen and len(lines) < max_items:
                if not _add_line("[画像] ", mem.content):
                    break

        # 2. Query-relevant memories
        if current_query and len(lines) < max_items:
            relevant = self.search(user_id, current_query, top_k=max_items - len(lines))
            for mem in relevant:
                if mem.content[:60] not in seen and len(lines) < max_items:
                    type_label = f"[{mem.memory_type}] " if mem.memory_type else ""
                    if not _add_line(type_label, mem.content):
                        break

        if not lines:
            return None

        return "\n".join(lines)
