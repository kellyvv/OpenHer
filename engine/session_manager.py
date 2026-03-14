"""
SessionManager — In-memory session pool + proactive heartbeat for Engine API.

Migrated from main.py's session management and proactive sweep logic.
WebSocket delivery replaced with asyncio.Queue → SSE push.

Key components:
  - _pool: Dict[session_id → ChatAgent] — active sessions
  - _lru: OrderedDict — LRU eviction when pool exceeds pool_max
  - _queues: Dict[session_id → asyncio.Queue] — SSE event delivery
  - _heartbeat_loop: Background task running proactive sweep
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import OrderedDict
from typing import Optional, Dict

from agent.chat_agent import ChatAgent
from engine.state_store import StateStore
from memory.memory_store import MemoryStore
from persona.loader import PersonaLoader


_INSTANCE_ID = str(uuid.uuid4())[:8]


class SessionManager:
    """
    Manages ChatAgent session lifecycle with LRU eviction and proactive tick.

    Usage:
        mgr = SessionManager(llm=llm, state_store=store, ...)
        await mgr.start()       # start proactive heartbeat
        agent = await mgr.get_or_create(sid, pid, uid, uname)
        await mgr.checkpoint(sid)
        await mgr.shutdown()    # persist all + cleanup
    """

    def __init__(
        self,
        llm,
        state_store: StateStore,
        memory_store: MemoryStore,
        persona_loader: PersonaLoader,
        genome_data_dir: str,
        tick_interval: int = 300,
        pool_max: int = 100,
    ):
        self.llm = llm
        self.state_store = state_store
        self.memory_store = memory_store
        self.persona_loader = persona_loader
        self.genome_data_dir = genome_data_dir
        self.tick_interval = tick_interval
        self.pool_max = pool_max

        self._pool: Dict[str, ChatAgent] = {}
        self._meta: Dict[str, dict] = {}      # session_id → {user_id, persona_id}
        self._lru: OrderedDict = OrderedDict()
        self._queues: Dict[str, asyncio.Queue] = {}
        self._task: Optional[asyncio.Task] = None

        # Proactive metrics (exposed via /api/engine/health)
        self.metrics = {
            'ticks_total': 0,
            'impulse_triggered': 0,
            'silence_chosen': 0,
            'outbox_enqueued': 0,
            'outbox_blocked': 0,
            'sse_push_ok': 0,
            'sse_push_fail': 0,
            'outbox_delivered': 0,
            'outbox_retries': 0,
        }

    # ──────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────

    async def start(self):
        """Start proactive heartbeat background task."""
        self._task = asyncio.create_task(self._heartbeat_loop())
        print(f"✓ SessionManager started (tick={self.tick_interval}s, pool_max={self.pool_max})")

    async def shutdown(self):
        """Persist all sessions and clean up."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # Persist all active sessions
        for sid in list(self._pool.keys()):
            await self.checkpoint(sid)
        self.state_store.close()
        self.memory_store.close()
        print("✓ SessionManager shutdown complete")

    # ──────────────────────────────────────────────
    # Session Pool
    # ──────────────────────────────────────────────

    async def get_or_create(
        self,
        session_id: str,
        persona_id: str,
        user_id: str = "default_user",
        user_name: Optional[str] = None,
    ) -> ChatAgent:
        """
        Get existing session or create new one.

        Full creation flow (mirrors main.py):
          1. persona_loader.get(persona_id) → Persona
          2. ChatAgent(persona, llm, ..., evermemos=None)
          3. state_store.load_session(user_id, persona_id) → restore W1/W2/drives
          4. If no prior state and age==0 → pre_warm(60 steps)
          5. Register in pool + LRU + queue
          6. LRU evict if over pool_max
        """
        if session_id in self._pool:
            self._lru.move_to_end(session_id)
            return self._pool[session_id]

        # Step 1: Load persona
        persona = self.persona_loader.get(persona_id)
        if not persona:
            raise ValueError(f"Persona not found: {persona_id}")

        # Step 2: Create ChatAgent (no EverMemOS, no skills, no TTS)
        agent = ChatAgent(
            persona=persona,
            llm=self.llm,
            user_id=user_id,
            user_name=user_name,
            memory_store=self.memory_store,
            genome_data_dir=self.genome_data_dir,
            evermemos=None,
        )

        # Step 3: Try to restore persisted state
        saved_agent, saved_metabolism = self.state_store.load_session(user_id, persona_id)
        if saved_agent:
            agent.agent = saved_agent
            agent.metabolism = saved_metabolism
            # Restore proactive meta
            last_active, cadence, _ = self.state_store.load_proactive_meta(user_id, persona_id)
            agent._last_active = last_active
            agent._interaction_cadence = cadence
            print(f"  [session] ♻ restored: {persona_id} ↔ {user_id} (age={saved_agent.age})")
        else:
            # Step 4: New agent — pre-warm if age is 0
            if agent.agent.age == 0:
                agent.pre_warm()
                print(f"  [session] 🌱 new agent pre-warmed: {persona_id} ↔ {user_id}")

        # Step 5: Register in pool
        self._pool[session_id] = agent
        self._meta[session_id] = {"user_id": user_id, "persona_id": persona_id}
        self._lru[session_id] = True
        self._queues[session_id] = asyncio.Queue()

        # Step 6: LRU eviction
        while len(self._pool) > self.pool_max:
            evicted_sid, _ = self._lru.popitem(last=False)
            print(f"  [session] ⏏ LRU evicting: {evicted_sid}")
            await self.checkpoint(evicted_sid)
            self._pool.pop(evicted_sid, None)
            self._meta.pop(evicted_sid, None)
            self._queues.pop(evicted_sid, None)

        return agent

    def get(self, session_id: str) -> Optional[ChatAgent]:
        """Get an active session (no creation)."""
        return self._pool.get(session_id)

    async def checkpoint(self, session_id: str):
        """Persist session state to SQLite."""
        agent = self._pool.get(session_id)
        meta = self._meta.get(session_id)
        if not agent or not meta:
            return
        self.state_store.save_session(
            meta["user_id"],
            meta["persona_id"],
            agent.agent,
            agent.metabolism,
        )

    def remove(self, session_id: str):
        """Remove session from pool (call checkpoint first!)."""
        self._pool.pop(session_id, None)
        self._meta.pop(session_id, None)
        self._lru.pop(session_id, None)
        self._queues.pop(session_id, None)

    def get_queue(self, session_id: str) -> Optional[asyncio.Queue]:
        """Get SSE event queue for a session."""
        return self._queues.get(session_id)

    # ──────────────────────────────────────────────
    # Proactive Heartbeat (migrated from main.py)
    # ──────────────────────────────────────────────

    async def _heartbeat_loop(self):
        """Background task: periodic proactive sweep."""
        await asyncio.sleep(60)  # Initial delay — let sessions warm up
        while True:
            try:
                await self._sweep()
            except Exception as e:
                print(f"[proactive] ❌ heartbeat error: {e}")
            await asyncio.sleep(self.tick_interval)

    async def _sweep(self):
        """
        Proactive sweep — mirrors main.py:_proactive_sweep().

        For each active session:
          1. Acquire per-user-persona lock (cross-instance safety)
          2. Run agent.proactive_tick()
          3. If result → outbox 3-layer guard → enqueue
          4. Deliver all pending outbox messages via Queue → SSE
          5. Checkpoint state
        """
        cooldown_h = 4
        max_pending = 3
        lock_ttl = 600

        for sid, agent in list(self._pool.items()):
            meta = self._meta.get(sid)
            if not meta:
                continue
            uid = meta["user_id"]
            pid = meta["persona_id"]

            # Cross-instance lock (prevents duplicate ticks in multi-instance)
            if not self.state_store.try_acquire_lock(uid, pid, _INSTANCE_ID, ttl=lock_ttl):
                continue

            try:
                # Phase 1: Generate new proactive message
                self.metrics['ticks_total'] += 1
                result = await agent.proactive_tick()

                if result is not None:
                    self.metrics['impulse_triggered'] += 1
                    drive_id = result.get('drive_id', 'unknown')

                    # Construct dedup_key (same logic as main.py)
                    depth = agent._relationship_ema.get('relationship_depth', 0.0)
                    band = 'deep' if depth > 0.6 else 'mid' if depth > 0.3 else 'shallow'
                    bucket = int(time.time() // (cooldown_h * 3600))
                    dedup_key = f"{drive_id}:{band}:{bucket}"

                    # 3-layer guard: cooldown + pending cap + dedup
                    if self.state_store.outbox_can_enqueue(
                        uid, pid, dedup_key,
                        cooldown_hours=cooldown_h,
                        max_pending=max_pending,
                    ):
                        self.state_store.outbox_insert(
                            uid, pid, result['tick_id'],
                            result['reply'],
                            result.get('modality', '文字'),
                            result.get('monologue', ''),
                            drive_id, dedup_key,
                        )
                        self.metrics['outbox_enqueued'] += 1
                    else:
                        self.metrics['outbox_blocked'] += 1

                elif result is None and agent._has_impulse():
                    # Actor chose silence despite having an impulse
                    self.metrics['silence_chosen'] += 1

                # Phase 2: Deliver all pending outbox messages (including retries)
                pending = self.state_store.outbox_get_pending(uid, pid)
                for row in pending:
                    await self._deliver(agent, sid, row)

                # Checkpoint state after tick
                await self.checkpoint(sid)

            finally:
                self.state_store.release_lock(uid, pid, _INSTANCE_ID)

    async def _deliver(self, agent: ChatAgent, session_id: str, row: dict):
        """
        Deliver outbox message via asyncio.Queue → SSE.

        Replaces main.py's WebSocket push with Queue-based delivery.
        If no consumer (SSE disconnected), mark failed → retry next sweep.
        """
        uid = row['user_id']
        pid = row['persona_id']
        tick_id = row['tick_id']

        # Atomically take pending → sending
        msg = self.state_store.outbox_try_send(uid, pid, tick_id)
        if not msg:
            return  # Already taken by another instance

        queue = self._queues.get(session_id)
        if not queue:
            # SSE disconnected — mark failed, retry next sweep
            self.state_store.outbox_mark_failed(uid, pid, tick_id)
            self.metrics['sse_push_fail'] += 1
            return

        try:
            await queue.put({
                "reply": row['reply'],
                "modality": row.get('modality', '文字'),
                "monologue": row.get('monologue', ''),
                "drive_id": row.get('drive_id', ''),
                "persona": agent.persona.name,
            })
            self.state_store.outbox_mark_delivered(uid, pid, tick_id)
            self.metrics['sse_push_ok'] += 1
            self.metrics['outbox_delivered'] += 1
        except Exception:
            self.state_store.outbox_mark_failed(uid, pid, tick_id)
            self.metrics['sse_push_fail'] += 1
