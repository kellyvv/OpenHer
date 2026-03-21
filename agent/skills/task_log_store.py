"""
TaskLogStore — Isolated persistence for task skill execution history.

Stores tool call metadata in an independent SQLite database (task.db),
completely separate from persona memory (EverMemOS) and chat display (chat.db).

Design decisions:
  - Append-only, no CAS, thread-safe (check_same_thread=False).
  - Does NOT feed into agent.history, Actor prompt, or EverMemOS.
  - Called from _chat_inner guard clause after successful tool execution.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Optional


class TaskLogStore:
    """SQLite-backed log for task skill executions (memory isolation layer)."""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS task_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                persona_id TEXT NOT NULL,
                skill_id TEXT NOT NULL,
                user_input TEXT NOT NULL,
                command TEXT DEFAULT '',
                stdout TEXT DEFAULT '',
                stderr TEXT DEFAULT '',
                success INTEGER NOT NULL DEFAULT 0,
                reply TEXT DEFAULT '',
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_task_persona
                ON task_executions(persona_id, created_at);
        """)
        self._conn.commit()

    def log_execution(
        self,
        persona_id: str,
        skill_id: str,
        user_input: str,
        command: str = "",
        stdout: str = "",
        stderr: str = "",
        success: bool = False,
        reply: str = "",
    ) -> None:
        """Log a single task skill execution."""
        self._conn.execute(
            """
            INSERT INTO task_executions
                (persona_id, skill_id, user_input, command, stdout, stderr, success, reply, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (persona_id, skill_id, user_input, command, stdout, stderr, int(success), reply, time.time()),
        )
        self._conn.commit()

    def get_recent(self, persona_id: str, limit: int = 10) -> list[dict]:
        """Get recent task executions for a persona (newest first)."""
        rows = self._conn.execute(
            """
            SELECT id, skill_id, user_input, command, stdout, success, reply, created_at
            FROM task_executions
            WHERE persona_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (persona_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self._conn.close()
