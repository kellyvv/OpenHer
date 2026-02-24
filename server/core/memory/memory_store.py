"""
MemoryStore — Long-term memory with keyword search for OpenHer.

Stores and retrieves conversation memories per user-persona pair.
Uses SQLite FTS5 for full-text search (no external vector DB dependency).

Future upgrade path: add sqlite-vec for embedding-based hybrid search.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class Memory:
    """A single memory entry."""
    memory_id: int = 0
    user_id: str = ""
    persona_id: str = ""
    content: str = ""              # The memory text
    category: str = "conversation" # conversation | fact | event | preference
    importance: float = 0.5        # 0.0 - 1.0
    source_turn: int = 0           # Which conversation turn this came from
    created_at: float = 0.0


class MemoryStore:
    """
    SQLite FTS5-backed memory store.

    Usage:
        store = MemoryStore("/path/to/memory.db")
        store.add("user1", "xiaoyun", "用户说他叫小明", category="fact", importance=0.9)
        memories = store.search("user1", "xiaoyun", "小明")
        context = store.build_memory_context("user1", "xiaoyun", "今天过得怎么样")
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        print(f"✓ 记忆存储: {db_path}")

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                persona_id TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'conversation',
                importance REAL DEFAULT 0.5,
                source_turn INTEGER DEFAULT 0,
                created_at REAL DEFAULT 0
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content,
                content='memories',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.id, old.content);
            END;

            CREATE INDEX IF NOT EXISTS idx_memories_user_persona
                ON memories(user_id, persona_id);
        """)
        self._conn.commit()

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
        cursor = self._conn.execute(
            """
            INSERT INTO memories (user_id, persona_id, content, category, importance, source_turn, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, persona_id, content, category, importance, source_turn, time.time()),
        )
        self._conn.commit()
        return cursor.lastrowid

    def add_facts(
        self,
        user_id: str,
        persona_id: str,
        facts: dict[str, str],
    ) -> None:
        """Add extracted facts as high-importance memories."""
        fact_labels = {
            "user_name": "用户的名字是",
            "birthday": "用户的生日是",
            "location": "用户在",
            "pet": "用户养了",
            "food_preference": "用户喜欢",
        }
        for key, value in facts.items():
            label = fact_labels.get(key, key)
            content = f"{label}{value}"
            # Check for existing similar fact to avoid duplicates
            existing = self.search(user_id, persona_id, value, limit=1)
            if not existing:
                self.add(
                    user_id=user_id,
                    persona_id=persona_id,
                    content=content,
                    category="fact",
                    importance=0.9,
                )

    def search(
        self,
        user_id: str,
        persona_id: str,
        query: str,
        limit: int = 5,
    ) -> list[Memory]:
        """Search memories using FTS5 full-text search."""
        try:
            rows = self._conn.execute(
                """
                SELECT m.id, m.user_id, m.persona_id, m.content, m.category,
                       m.importance, m.source_turn, m.created_at
                FROM memories m
                JOIN memories_fts ON memories_fts.rowid = m.id
                WHERE memories_fts MATCH ?
                  AND m.user_id = ? AND m.persona_id = ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, user_id, persona_id, limit),
            ).fetchall()
        except Exception:
            # FTS match can fail on special characters
            rows = []

        return [self._row_to_memory(r) for r in rows]

    def get_recent(
        self,
        user_id: str,
        persona_id: str,
        limit: int = 10,
    ) -> list[Memory]:
        """Get the most recent memories."""
        rows = self._conn.execute(
            """
            SELECT id, user_id, persona_id, content, category,
                   importance, source_turn, created_at
            FROM memories
            WHERE user_id = ? AND persona_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, persona_id, limit),
        ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def get_important(
        self,
        user_id: str,
        persona_id: str,
        min_importance: float = 0.7,
        limit: int = 10,
    ) -> list[Memory]:
        """Get high-importance memories (facts, key events)."""
        rows = self._conn.execute(
            """
            SELECT id, user_id, persona_id, content, category,
                   importance, source_turn, created_at
            FROM memories
            WHERE user_id = ? AND persona_id = ? AND importance >= ?
            ORDER BY importance DESC, created_at DESC
            LIMIT ?
            """,
            (user_id, persona_id, min_importance, limit),
        ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def build_memory_context(
        self,
        user_id: str,
        persona_id: str,
        current_query: str = "",
        max_items: int = 8,
    ) -> Optional[str]:
        """
        Build a memory context string for system prompt injection.

        Strategy:
        1. Always include high-importance facts (name, birthday, etc.)
        2. If there's a current query, include relevant search hits
        3. Fill remaining slots with recent memories
        """
        memories: list[Memory] = []
        seen_ids: set[int] = set()

        # 1. Key facts (importance >= 0.8)
        facts = self.get_important(user_id, persona_id, min_importance=0.8, limit=4)
        for m in facts:
            if m.memory_id not in seen_ids:
                memories.append(m)
                seen_ids.add(m.memory_id)

        # 2. Relevant to current query
        if current_query and len(memories) < max_items:
            relevant = self.search(user_id, persona_id, current_query, limit=3)
            for m in relevant:
                if m.memory_id not in seen_ids and len(memories) < max_items:
                    memories.append(m)
                    seen_ids.add(m.memory_id)

        # 3. Recent memories to fill
        if len(memories) < max_items:
            recent = self.get_recent(user_id, persona_id, limit=max_items)
            for m in recent:
                if m.memory_id not in seen_ids and len(memories) < max_items:
                    memories.append(m)
                    seen_ids.add(m.memory_id)

        if not memories:
            return None

        lines = []
        for m in memories:
            tag = f"[{m.category}]" if m.category != "conversation" else ""
            lines.append(f"- {tag}{m.content}")

        return "\n".join(lines)

    def count(self, user_id: str, persona_id: str) -> int:
        """Count total memories for a user-persona pair."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM memories WHERE user_id = ? AND persona_id = ?",
            (user_id, persona_id),
        ).fetchone()
        return row[0] if row else 0

    def _row_to_memory(self, row) -> Memory:
        return Memory(
            memory_id=row["id"],
            user_id=row["user_id"],
            persona_id=row["persona_id"],
            content=row["content"],
            category=row["category"],
            importance=row["importance"],
            source_turn=row["source_turn"],
            created_at=row["created_at"],
        )

    def close(self):
        self._conn.close()
