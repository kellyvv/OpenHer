"""
StateStore — SQLite persistence for Genome v8 agent state.

Stores per-user-per-persona state so that restarting the server
doesn't lose personality evolution (Agent weights + DriveMetabolism).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Optional

from core.genome.genome_engine import Agent
from core.genome.drive_metabolism import DriveMetabolism


class StateStore:
    """
    SQLite-backed state persistence for Genome v8 agents.

    Usage:
        store = StateStore("/path/to/openher.db")
        store.save_session("user123", "xiaoyun", agent, metabolism)
        agent, metabolism = store.load_session("user123", "xiaoyun")
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        print(f"✓ 状态存储: {db_path}")

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS genome_state (
                user_id TEXT NOT NULL,
                persona_id TEXT NOT NULL,
                agent_data TEXT DEFAULT '{}',
                metabolism_data TEXT DEFAULT '{}',
                updated_at REAL DEFAULT 0,
                PRIMARY KEY (user_id, persona_id)
            );

            CREATE TABLE IF NOT EXISTS chat_summary (
                user_id TEXT NOT NULL,
                persona_id TEXT NOT NULL,
                summary TEXT DEFAULT '',
                message_count INTEGER DEFAULT 0,
                updated_at REAL DEFAULT 0,
                PRIMARY KEY (user_id, persona_id)
            );
        """)
        self._conn.commit()

    def save_session(
        self,
        user_id: str,
        persona_id: str,
        agent: Agent,
        metabolism: DriveMetabolism,
    ) -> None:
        """Persist Agent + DriveMetabolism state to SQLite."""
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO genome_state (user_id, persona_id, agent_data, metabolism_data, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, persona_id) DO UPDATE SET
                agent_data = excluded.agent_data,
                metabolism_data = excluded.metabolism_data,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                persona_id,
                json.dumps(agent.to_dict(), ensure_ascii=False),
                json.dumps(metabolism.to_dict(), ensure_ascii=False),
                now,
            ),
        )
        self._conn.commit()

    def load_session(
        self,
        user_id: str,
        persona_id: str,
    ) -> tuple[Optional[Agent], Optional[DriveMetabolism]]:
        """Load persisted state. Returns (None, None) if no prior session."""
        row = self._conn.execute(
            "SELECT agent_data, metabolism_data FROM genome_state WHERE user_id = ? AND persona_id = ?",
            (user_id, persona_id),
        ).fetchone()

        if not row:
            return None, None

        try:
            agent_data = json.loads(row["agent_data"])
            metabolism_data = json.loads(row["metabolism_data"])
            agent = Agent.from_dict(agent_data)
            metabolism = DriveMetabolism.from_dict(metabolism_data)
            return agent, metabolism
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[state] 加载状态失败 ({user_id}/{persona_id}): {e}")
            return None, None

    def save_chat_summary(
        self,
        user_id: str,
        persona_id: str,
        summary: str,
        message_count: int,
    ) -> None:
        """Save a chat summary for future context loading."""
        self._conn.execute(
            """
            INSERT INTO chat_summary (user_id, persona_id, summary, message_count, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, persona_id) DO UPDATE SET
                summary = excluded.summary,
                message_count = excluded.message_count,
                updated_at = excluded.updated_at
            """,
            (user_id, persona_id, summary, message_count, time.time()),
        )
        self._conn.commit()

    def close(self):
        self._conn.close()
