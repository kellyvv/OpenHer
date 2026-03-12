"""
ChatLogStore — Display-layer chat history persistence.

Stores raw chat messages in an independent SQLite database (chat.db)
for frontend history display across page refreshes and server restarts.

Design decisions (v5.1):
  - Uses `client_id` (frontend localStorage UUID) as identity key,
    completely separate from engine's `stable_user_id`.
  - Append-only, no CAS, multi-writer safe (multiple tabs OK).
  - Does NOT feed into agent.history or Express prompt.
  - Engine code (ChatAgent, StateStore, EverMemOS) is not touched.
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Optional


class ChatLogStore:
    """SQLite-backed chat log for display-layer persistence."""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        print(f"✓ ChatLogStore 初始化: {db_path}")

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                persona_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                modality TEXT DEFAULT '文字',
                image_url TEXT DEFAULT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chat_lookup
                ON chat_messages(client_id, persona_id, created_at);
        """)
        self._conn.commit()
        # Migration: add image_url column if missing (existing databases)
        try:
            self._conn.execute("SELECT image_url FROM chat_messages LIMIT 0")
        except sqlite3.OperationalError:
            self._conn.execute("ALTER TABLE chat_messages ADD COLUMN image_url TEXT DEFAULT NULL")
            self._conn.commit()

    def save_turn(
        self,
        client_id: str,
        persona_id: str,
        user_msg: str,
        agent_reply: str,
        modality: str = "文字",
        image_url: str | None = None,
    ) -> None:
        """Save one conversation turn (user + assistant messages)."""
        now = time.time()
        self._conn.executemany(
            """
            INSERT INTO chat_messages (client_id, persona_id, role, content, modality, image_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (client_id, persona_id, "user", user_msg, "文字", None, now),
                (client_id, persona_id, "assistant", agent_reply, modality, image_url, now),
            ],
        )
        self._conn.commit()

    def load_messages(
        self,
        client_id: str,
        persona_id: str,
        limit: int = 50,
        before_id: Optional[int] = None,
    ) -> list[dict]:
        """
        Load messages for display (newest first, reversed for chronological order).

        Args:
            client_id: Frontend client identity.
            persona_id: Persona to load history for.
            limit: Max messages to return.
            before_id: For pagination — only return messages with id < before_id.

        Returns:
            List of dicts with keys: id, role, content, modality, created_at
            (ordered chronologically, oldest first).
        """
        if before_id is not None:
            rows = self._conn.execute(
                """
                SELECT id, role, content, modality, image_url, created_at
                FROM chat_messages
                WHERE client_id = ? AND persona_id = ? AND id < ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (client_id, persona_id, before_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT id, role, content, modality, image_url, created_at
                FROM chat_messages
                WHERE client_id = ? AND persona_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (client_id, persona_id, limit),
            ).fetchall()

        # Reverse to chronological order (oldest first)
        return [
            {
                "id": r["id"],
                "role": r["role"],
                "content": r["content"],
                "modality": r["modality"],
                "image_url": r["image_url"],
                "created_at": r["created_at"],
            }
            for r in reversed(rows)
        ]

    def count_messages(self, client_id: str, persona_id: str) -> int:
        """Count total messages for a client-persona pair."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE client_id = ? AND persona_id = ?",
            (client_id, persona_id),
        ).fetchone()
        return row[0] if row else 0

    def close(self):
        self._conn.close()
