"""
StateStore — SQLite persistence for Genome v8 agent state.

Stores per-user-per-persona state so that restarting the server
doesn't lose personality evolution (Agent weights + DriveMetabolism).

Extended with proactive tick infrastructure:
  - proactive_lock: cross-instance lease-based locking (R7/R13/R23/R28/R30)
  - proactive_outbox: message queue with state machine (R4/R10/R15/R21/R31)
  - CAS save_state: version-guarded writes (R24/R29)
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
        store.save_session("user123", "persona_a", agent, metabolism)
        agent, metabolism = store.load_session("user123", "persona_a")
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
                state_version INTEGER DEFAULT 0,
                last_active_at REAL DEFAULT 0,
                interaction_cadence REAL DEFAULT 0,
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

            CREATE TABLE IF NOT EXISTS proactive_lock (
                user_id TEXT NOT NULL,
                persona_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                acquired_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                PRIMARY KEY (user_id, persona_id)
            );

            CREATE TABLE IF NOT EXISTS proactive_outbox (
                user_id TEXT NOT NULL,
                persona_id TEXT NOT NULL,
                tick_id TEXT NOT NULL,
                reply TEXT NOT NULL,
                modality TEXT NOT NULL DEFAULT '文字',
                monologue TEXT DEFAULT '',
                drive_id TEXT DEFAULT '',
                dedup_key TEXT DEFAULT '',
                created_at REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                delivered_at REAL,
                PRIMARY KEY (user_id, persona_id, tick_id)
            );
        """)
        # Migrate: add columns if missing (for existing DBs)
        for col, typ, default in [
            ("state_version", "INTEGER", "0"),
            ("last_active_at", "REAL", "0"),
            ("interaction_cadence", "REAL", "0"),
        ]:
            try:
                self._conn.execute(
                    f"ALTER TABLE genome_state ADD COLUMN {col} {typ} DEFAULT {default}")
            except sqlite3.OperationalError:
                pass
        self._conn.commit()

    # ─────────────────────────────────────────────
    # Session state (original + CAS)
    # ─────────────────────────────────────────────

    def save_session(
        self,
        user_id: str,
        persona_id: str,
        agent: Agent,
        metabolism: DriveMetabolism,
    ) -> None:
        """Persist Agent + DriveMetabolism state to SQLite (legacy, non-CAS)."""
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
                user_id, persona_id,
                json.dumps(agent.to_dict(), ensure_ascii=False),
                json.dumps(metabolism.to_dict(), ensure_ascii=False),
                now,
            ),
        )
        self._conn.commit()

    def save_state(
        self,
        user_id: str,
        persona_id: str,
        *,
        agent_data: Optional[str] = None,
        metabolism_data: Optional[str] = None,
        last_active_at: Optional[float] = None,
        interaction_cadence: Optional[float] = None,
        expected_version: Optional[int] = None,
    ) -> bool:
        """
        Unified CAS write entry (R24/R29).
        Returns True if write succeeded, False if version mismatch.
        """
        now = time.time()
        if expected_version is not None:
            cur = self._conn.execute("""
                UPDATE genome_state SET
                    agent_data = COALESCE(?, agent_data),
                    metabolism_data = COALESCE(?, metabolism_data),
                    last_active_at = COALESCE(?, last_active_at),
                    interaction_cadence = COALESCE(?, interaction_cadence),
                    state_version = state_version + 1,
                    updated_at = ?
                WHERE user_id = ? AND persona_id = ? AND state_version = ?
            """, (agent_data, metabolism_data, last_active_at,
                  interaction_cadence, now, user_id, persona_id, expected_version))
            self._conn.commit()
            return cur.rowcount > 0
        else:
            self._conn.execute("""
                INSERT INTO genome_state
                    (user_id, persona_id, agent_data, metabolism_data,
                     last_active_at, interaction_cadence, updated_at)
                VALUES (?, ?, COALESCE(?, '{}'), COALESCE(?, '{}'),
                        COALESCE(?, 0), COALESCE(?, 0), ?)
                ON CONFLICT(user_id, persona_id) DO UPDATE SET
                    agent_data = COALESCE(excluded.agent_data, genome_state.agent_data),
                    metabolism_data = COALESCE(excluded.metabolism_data, genome_state.metabolism_data),
                    last_active_at = COALESCE(excluded.last_active_at, genome_state.last_active_at),
                    interaction_cadence = COALESCE(excluded.interaction_cadence, genome_state.interaction_cadence),
                    state_version = genome_state.state_version + 1,
                    updated_at = excluded.updated_at
            """, (user_id, persona_id, agent_data, metabolism_data,
                  last_active_at, interaction_cadence, now))
            self._conn.commit()
            return True

    def get_state_version(self, user_id: str, persona_id: str) -> int:
        """Get current state_version for CAS."""
        row = self._conn.execute(
            "SELECT state_version FROM genome_state WHERE user_id=? AND persona_id=?",
            (user_id, persona_id)).fetchone()
        return row["state_version"] if row else 0

    def load_session(
        self,
        user_id: str,
        persona_id: str,
    ) -> tuple[Optional[Agent], Optional[DriveMetabolism]]:
        """Load persisted state. Returns (None, None) if no prior session."""
        row = self._conn.execute(
            "SELECT agent_data, metabolism_data FROM genome_state WHERE user_id = ? AND persona_id = ?",
            (user_id, persona_id)).fetchone()

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

    def load_proactive_meta(
        self, user_id: str, persona_id: str
    ) -> tuple[float, float, int]:
        """Load last_active_at, interaction_cadence, state_version."""
        row = self._conn.execute(
            "SELECT last_active_at, interaction_cadence, state_version FROM genome_state WHERE user_id=? AND persona_id=?",
            (user_id, persona_id)).fetchone()
        if row:
            return row["last_active_at"], row["interaction_cadence"], row["state_version"]
        return 0.0, 0.0, 0

    # ─────────────────────────────────────────────
    # Proactive Lock (R7/R13/R23/R28/R30)
    # ─────────────────────────────────────────────

    def try_acquire_lock(
        self, user_id: str, persona_id: str, owner_id: str, ttl: float = 600
    ) -> bool:
        """
        Atomic lease-based lock via single UPSERT (R23/R28).
        Only acquires if no lock exists or existing lock expired.
        """
        now = time.time()
        with self._conn:
            cur = self._conn.execute("""
                INSERT INTO proactive_lock (user_id, persona_id, owner_id, acquired_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, persona_id) DO UPDATE SET
                    owner_id = excluded.owner_id,
                    acquired_at = excluded.acquired_at,
                    expires_at = excluded.expires_at
                WHERE proactive_lock.expires_at < ?
            """, (user_id, persona_id, owner_id, now, now + ttl, now))
            return cur.rowcount > 0

    def release_lock(self, user_id: str, persona_id: str, owner_id: str):
        """Release lock only if we own it (R30)."""
        self._conn.execute(
            "DELETE FROM proactive_lock WHERE user_id=? AND persona_id=? AND owner_id=?",
            (user_id, persona_id, owner_id))
        self._conn.commit()

    def renew_lock(
        self, user_id: str, persona_id: str, owner_id: str, ttl: float = 600
    ):
        """Renew lock TTL only if we own it (R27/R30)."""
        now = time.time()
        self._conn.execute("""
            UPDATE proactive_lock SET expires_at = ?
            WHERE user_id=? AND persona_id=? AND owner_id=?
        """, (now + ttl, user_id, persona_id, owner_id))
        self._conn.commit()

    # ─────────────────────────────────────────────
    # Proactive Outbox (R4/R10/R15/R21/R31)
    # ─────────────────────────────────────────────

    def outbox_insert(
        self, user_id: str, persona_id: str, tick_id: str,
        reply: str, modality: str, monologue: str,
        drive_id: str, dedup_key: str,
    ) -> bool:
        """Insert into outbox. Returns False if tick_id already exists (idempotent)."""
        try:
            self._conn.execute("""
                INSERT INTO proactive_outbox
                    (user_id, persona_id, tick_id, reply, modality, monologue,
                     drive_id, dedup_key, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """, (user_id, persona_id, tick_id, reply, modality,
                  monologue, drive_id, dedup_key, time.time()))
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def outbox_has_recent(self, user_id: str, persona_id: str, hours: float = 4) -> bool:
        """Check if any message was created within cooldown window."""
        cutoff = time.time() - hours * 3600
        row = self._conn.execute("""
            SELECT 1 FROM proactive_outbox
            WHERE user_id=? AND persona_id=? AND created_at > ? LIMIT 1
        """, (user_id, persona_id, cutoff)).fetchone()
        return row is not None

    def outbox_pending_count(self, user_id: str, persona_id: str) -> int:
        row = self._conn.execute("""
            SELECT COUNT(*) as cnt FROM proactive_outbox
            WHERE user_id=? AND persona_id=? AND status='pending'
        """, (user_id, persona_id)).fetchone()
        return row["cnt"] if row else 0

    def outbox_has_dedup(
        self, user_id: str, persona_id: str, dedup_key: str, hours: float = 4
    ) -> bool:
        cutoff = time.time() - hours * 3600
        row = self._conn.execute("""
            SELECT 1 FROM proactive_outbox
            WHERE user_id=? AND persona_id=? AND dedup_key=? AND created_at > ? LIMIT 1
        """, (user_id, persona_id, dedup_key, cutoff)).fetchone()
        return row is not None

    def outbox_try_send(self, user_id: str, persona_id: str, tick_id: str) -> Optional[dict]:
        """Atomically take pending → sending (R31)."""
        with self._conn:
            cur = self._conn.execute("""
                UPDATE proactive_outbox SET status='sending'
                WHERE user_id=? AND persona_id=? AND tick_id=? AND status='pending'
            """, (user_id, persona_id, tick_id))
            if cur.rowcount == 0:
                return None
        row = self._conn.execute("""
            SELECT * FROM proactive_outbox WHERE user_id=? AND persona_id=? AND tick_id=?
        """, (user_id, persona_id, tick_id)).fetchone()
        return dict(row) if row else None

    def outbox_mark_delivered(self, user_id: str, persona_id: str, tick_id: str):
        self._conn.execute("""
            UPDATE proactive_outbox SET status='delivered', delivered_at=?
            WHERE user_id=? AND persona_id=? AND tick_id=?
        """, (time.time(), user_id, persona_id, tick_id))
        self._conn.commit()

    def outbox_mark_failed(self, user_id: str, persona_id: str, tick_id: str):
        self._conn.execute("""
            UPDATE proactive_outbox SET status='pending'
            WHERE user_id=? AND persona_id=? AND tick_id=? AND status='sending'
        """, (user_id, persona_id, tick_id))
        self._conn.commit()

    def outbox_get_pending(self, user_id: str, persona_id: str, limit: int = 3) -> list[dict]:
        rows = self._conn.execute("""
            SELECT * FROM proactive_outbox
            WHERE user_id=? AND persona_id=? AND status='pending'
            ORDER BY created_at ASC LIMIT ?
        """, (user_id, persona_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def outbox_can_enqueue(
        self, user_id: str, persona_id: str, dedup_key: str,
        cooldown_hours: float = 4, max_pending: int = 3,
    ) -> bool:
        """3-layer guard: cooldown + pending cap + dedup (R15)."""
        if self.outbox_has_recent(user_id, persona_id, cooldown_hours):
            return False
        if self.outbox_pending_count(user_id, persona_id) >= max_pending:
            return False
        if self.outbox_has_dedup(user_id, persona_id, dedup_key, cooldown_hours):
            return False
        return True

    # ─────────────────────────────────────────────
    # Chat summary (unchanged)
    # ─────────────────────────────────────────────

    def save_chat_summary(
        self, user_id: str, persona_id: str,
        summary: str, message_count: int,
    ) -> None:
        """Save a chat summary for future context loading."""
        self._conn.execute("""
            INSERT INTO chat_summary (user_id, persona_id, summary, message_count, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, persona_id) DO UPDATE SET
                summary = excluded.summary,
                message_count = excluded.message_count,
                updated_at = excluded.updated_at
        """, (user_id, persona_id, summary, message_count, time.time()))
        self._conn.commit()

    def close(self):
        self._conn.close()
