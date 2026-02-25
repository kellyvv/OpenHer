"""
EverMemOS Client — 长期记忆适配器 (Async v2)

使用 AsyncEverMemOS，所有 API 调用均为 async/await，不阻塞 uvicorn 事件循环。

记忆涌现架构：
  1. 每轮对话结束后 → asyncio.create_task(store_turn(...)) 后台存储
  2. EverMemOS 自动提取 Episode / EventLog(atomic_fact) / Profile / Foresight
  3. Session 开始时一次性拉取 Profile → 注入 Critic → LLM 自然表达记忆
  4. Session 结束时 flush → 触发边界提取

不再使用关键词匹配。情感/意图/偏好的检测全部交给 EverMemOS 和 Critic+LLM。
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass
from typing import Optional

try:
    from evermemos import AsyncEverMemOS
except ImportError:
    AsyncEverMemOS = None


@dataclass
class SessionContext:
    """
    Per-session context pulled from EverMemOS at session start.
    Cached locally to avoid repeated API calls within the same session.
    """
    user_profile: str          # Human-readable profile text for Critic/Actor injection
    episode_summary: str       # Narrative episodes for "history recall" injection
    interaction_count: int     # Total past interactions with this user
    has_history: bool          # True if user has any stored memories
    relationship_depth: float  # 0~1, semantic richness-based (not pure count)


class EverMemOSClient:
    """
    Async EverMemOS adapter for OpenHer.

    All public methods are async. Use asyncio.create_task() for fire-and-forget
    storage operations to avoid blocking the main conversation flow.
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.environ.get("EVERMEMOS_API_KEY")
        self._client = None
        self._mem = None
        self._initialized = False

        if AsyncEverMemOS and self._api_key:
            try:
                self._client = AsyncEverMemOS(
                    api_key=self._api_key,
                    timeout=10.0,  # 10s global timeout prevents hangs
                )
                self._mem = self._client.v0.memories
                self._initialized = True
                print("✓ EverMemOS client initialized")
            except Exception as e:
                print(f"⚠ EverMemOS init failed: {e}")
        else:
            if not AsyncEverMemOS:
                print("⚠ EverMemOS not installed (pip install evermemos)")
            else:
                print("⚠ EVERMEMOS_API_KEY not set — long-term memory disabled")

    @property
    def available(self) -> bool:
        return self._initialized and self._mem is not None

    # ─────────────────────────────────────────────────────────────
    # Session Lifecycle
    # ─────────────────────────────────────────────────────────────

    async def load_session_context(
        self,
        user_id: str,
        persona_id: str,
    ) -> SessionContext:
        """
        Called once at session start. Pulls user profile + event logs from
        EverMemOS and builds a SessionContext for use throughout the session.

        Returns a zero-context SessionContext if unavailable or error.
        """
        empty = SessionContext(
            user_profile="",
            episode_summary="",
            interaction_count=0,
            has_history=False,
            relationship_depth=0.0,
        )

        if not self.available:
            return empty

        try:
            # Pull profile + event_log + episodic_memory for full context
            response = await self._mem.get(
                extra_query={
                    "user_id": user_id,
                    "memory_type": "profile,event_log,episodic_memory",
                },
                timeout=8.0,
            )

            if not response or not response.result or not response.result.memories:
                return empty

            memories = response.result.memories
            profile_lines = []
            fact_lines = []
            episode_lines = []
            interaction_count = 0

            for mem in memories:
                mem_type = getattr(mem, '__class__', None)
                type_name = mem_type.__name__ if mem_type else ""

                if "Profile" in type_name:
                    profile_data = getattr(mem, 'profile_data', None)
                    if profile_data:
                        for k, v in profile_data.items():
                            if v:
                                profile_lines.append(f"{k}: {v}")
                    interaction_count += getattr(mem, 'memcell_count', 0) or 0

                elif "EventLog" in type_name:
                    fact = getattr(mem, 'atomic_fact', None)
                    if fact and fact.strip():
                        fact_lines.append(fact.strip())

                elif "Episode" in type_name or "Episodic" in type_name:
                    # Episodic memory: narrative summary of past conversations
                    summary = (
                        getattr(mem, 'summary', None)
                        or getattr(mem, 'narrative', None)
                        or getattr(mem, 'content', None)
                    )
                    if summary and summary.strip():
                        episode_lines.append(summary.strip())

            # Build readable profile text (expanded limits for richer injection)
            parts = []
            if profile_lines:
                parts.append("【用户画像】" + "；".join(profile_lines[:8]))
            if fact_lines:
                parts.append("【已知偏好/事实】" + "；".join(fact_lines[:12]))

            user_profile = "\n".join(parts) if parts else ""

            # Episode summary: recent narrative memories (latest 3 episodes)
            episode_summary = ""
            if episode_lines:
                episode_summary = "；".join(episode_lines[-3:])

            # ── Semantic relationship depth ──
            # Based on DATA RICHNESS, not raw interaction count.
            # A user with 3 deep emotional episodes > 100 shallow chats.
            data_richness = (
                len(fact_lines) * 2       # Each fact = knew something specific
                + len(profile_lines) * 3  # Profile attrs = LLM understood the person
                + len(episode_lines) * 5  # Episodes = real narrative history
            )
            import math
            # Saturates at richness ~30 (depth ≈ 1.0)
            depth = 1.0 - math.exp(-data_richness / 30.0) if data_richness > 0 else 0.0
            # Fallback: if no episodes/facts yet, use light interaction count signal
            if data_richness == 0 and interaction_count > 0:
                depth = 1.0 - math.exp(-interaction_count / 40.0)

            ctx = SessionContext(
                user_profile=user_profile,
                episode_summary=episode_summary,
                interaction_count=interaction_count,
                has_history=bool(memories),
                relationship_depth=round(depth, 3),
            )

            if ctx.has_history:
                print(
                    f"  [evermemos] 📚 loaded: {interaction_count} interactions, "
                    f"depth={depth:.2f}, {len(fact_lines)} facts, "
                    f"{len(profile_lines)} profile attrs, {len(episode_lines)} episodes"
                )

            return ctx

        except Exception as e:
            print(f"  [evermemos] load_session_context error: {e}")
            return empty

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
        """
        Store one conversation turn (user + agent messages) to EverMemOS.
        Called as asyncio.create_task — fire and forget, never blocks.

        EverMemOS automatically extracts Episodes, EventLogs (atomic facts),
        Profiles, and Foresights from stored messages.
        """
        if not self.available:
            return

        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime())

        try:
            # Store user message
            await self._mem.add(
                content=user_message,
                create_time=now_iso,
                message_id=str(uuid.uuid4()),
                sender=user_id,
                sender_name=user_name,
                role="user",
                group_id=group_id,
            )

            # Store agent reply
            await self._mem.add(
                content=agent_reply,
                create_time=now_iso,
                message_id=str(uuid.uuid4()),
                sender=persona_id,
                sender_name=persona_name,
                role="assistant",
                group_id=group_id,
            )

        except Exception as e:
            print(f"  [evermemos] store_turn error: {e}")

    async def close_session(
        self,
        user_id: str,
        persona_id: str,
        group_id: str,
    ) -> None:
        """
        Signal session end to EverMemOS (flush = boundary trigger).
        Forces memory extraction from buffered messages.
        """
        if not self.available:
            return

        try:
            await self._mem.add(
                content="[session_end]",
                create_time=time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime()),
                message_id=str(uuid.uuid4()),
                sender=persona_id,
                sender_name="system",
                role="assistant",
                group_id=group_id,
                flush=True,
            )
            print(f"  [evermemos] 🔚 session flushed for {user_id}")
        except Exception as e:
            print(f"  [evermemos] close_session error: {e}")

    # ─────────────────────────────────────────────────────────────
    # Relationship Vector (for GenomeEngine 4D context)
    # ─────────────────────────────────────────────────────────────

    def relationship_vector(self, ctx: SessionContext) -> dict:
        """
        Build the 4D relationship vector from SessionContext.
        No keyword matching — pure numerical derivation.

        Returns dict with keys matching CONTEXT_FEATURES:
          - relationship_depth:  gradual growth curve (new user = 0)
          - emotional_valence:   0.0 (derived from Critic, not here)
          - trust_level:         proxy from interaction depth
          - pending_foresight:   0.0 (EverMemOS handles internally)
        """
        import math
        depth = ctx.relationship_depth
        # Trust grows slower than depth (needs more interactions to trust)
        trust = 1.0 - math.exp(-ctx.interaction_count / 40.0) if ctx.interaction_count > 0 else 0.0

        return {
            'relationship_depth': round(depth, 3),
            'emotional_valence': 0.0,   # Set by Critic, not memory
            'trust_level': round(trust, 3),
            'pending_foresight': 0.0,   # EverMemOS stores internally
        }

    # ─────────────────────────────────────────────────────────────
    # Drive Evolution (for ChatAgent Step 0.6)
    # ─────────────────────────────────────────────────────────────

    def compute_drive_evolution(self, ctx: SessionContext) -> dict:
        """
        Compute drive baseline shifts from SessionContext.
        No keyword matching — pure relationship depth curves.

        New user = all zeros (identical to vanilla v10 behavior).
        Returns dict of {drive_name: delta} — small adjustments (±0.15 max).
        """
        DRIVES = ['connection', 'play', 'novelty', 'expression', 'safety']
        deltas = {d: 0.0 for d in DRIVES}

        if not ctx.has_history or ctx.interaction_count < 3:
            return deltas  # Not enough history

        depth = ctx.relationship_depth
        n = ctx.interaction_count

        # As relationship deepens: more connection, braver (less safety)
        # These are gentle asymptotic curves, max ±0.15
        max_delta = 0.15
        deltas['connection'] = min(max_delta, depth * 0.12)
        deltas['safety'] = -min(max_delta, depth * 0.08)     # More daring

        # Mild novelty boost for long-term users (they expect surprises)
        if n > 20:
            deltas['novelty'] = min(0.08, (n - 20) / 200.0)

        return deltas
