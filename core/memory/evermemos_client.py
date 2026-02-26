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
    pending_foresight: float   # 0~1, whether there are active foresight memories


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
            pending_foresight=0.0,
        )

        if not self.available:
            return empty

        try:
            # Pull profile + event_log + episodic_memory + foresight for full context
            response = await self._mem.get(
                extra_query={
                    "user_id": user_id,
                    "memory_type": "profile,event_log,episodic_memory,foresight",
                },
                timeout=8.0,
            )

            if not response or not response.result or not response.result.memories:
                return empty

            memories = response.result.memories
            profile_lines = []
            fact_lines = []
            episode_lines = []
            foresight_count = 0
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

                elif "Foresight" in type_name:
                    # Foresight: predictive/pending memories with validity windows
                    foresight_count += 1

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

            # Foresight signal: saturates at 3 foresights → 1.0
            pending_fs = 1.0 - math.exp(-foresight_count / 1.5) if foresight_count > 0 else 0.0

            ctx = SessionContext(
                user_profile=user_profile,
                episode_summary=episode_summary,
                interaction_count=interaction_count,
                has_history=bool(memories),
                relationship_depth=round(depth, 3),
                pending_foresight=round(pending_fs, 3),
            )

            if ctx.has_history:
                print(
                    f"  [evermemos] 📚 loaded: {interaction_count} interactions, "
                    f"depth={depth:.2f}, {len(fact_lines)} facts, "
                    f"{len(profile_lines)} profile attrs, {len(episode_lines)} episodes, "
                    f"{foresight_count} foresights"
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
        Build the 4D relationship PRIOR vector from SessionContext.
        These are deterministic priors; Critic provides deltas each turn.

        Returns dict with keys matching CONTEXT_FEATURES:
          - relationship_depth:  gradual growth curve (new user = 0)
          - emotional_valence:   0.0 (Critic provides delta each turn)
          - trust_level:         proxy from interaction depth
          - pending_foresight:   from foresight query
        """
        import math
        depth = ctx.relationship_depth
        # Trust grows slower than depth (needs more interactions to trust)
        trust = 1.0 - math.exp(-ctx.interaction_count / 40.0) if ctx.interaction_count > 0 else 0.0

        return {
            'relationship_depth': round(depth, 3),
            'emotional_valence': 0.0,   # Prior=0; Critic delta activates each turn
            'trust_level': round(trust, 3),
            'pending_foresight': round(ctx.pending_foresight, 3),
        }

    # ─────────────────────────────────────────────────────────────
    # Query-Based Relevance Retrieval (Phase 3)
    # ─────────────────────────────────────────────────────────────

    async def search_relevant_memories(
        self,
        query: str,
        user_id: str,
    ) -> tuple[str, str]:
        """
        Search for memories most relevant to the current user message.

        Uses EverMemOS RRF (hybrid keyword+vector) retrieval to find
        event_log facts and episodic_memory summaries relevant to the
        query. ~300ms typical latency with 3s hard timeout.

        Returns: (relevant_facts, relevant_episodes) as formatted strings.
                 Empty strings on error or no results.
        """
        if not self.available or not query.strip():
            return "", ""

        import time as _time
        t0 = _time.monotonic()

        try:
            # Primary query params (matches KI docs)
            query_params = {
                "query": query,
                "user_id": user_id,
                "retrieve_method": "rrf",
                "memory_types": "event_log,episodic_memory",
            }
            try:
                response = await self._mem.search(
                    extra_query=query_params,
                    timeout=3.0,
                )
            except Exception:
                # SDK compat: some versions use singular param names
                query_params_alt = {
                    "query": query,
                    "user_id": user_id,
                    "search_method": "rrf",
                    "memory_type": "event_log,episodic_memory",
                }
                response = await self._mem.search(
                    extra_query=query_params_alt,
                    timeout=3.0,
                )

            elapsed_ms = (_time.monotonic() - t0) * 1000

            if not response or not response.result or not response.result.memories:
                print(f"  [evermemos] 🔍 search: 0 results ({elapsed_ms:.0f}ms)")
                return "", ""

            memories = response.result.memories
            facts = []
            episodes = []

            for mem in memories:
                mem_type = getattr(mem, '__class__', None)
                type_name = mem_type.__name__ if mem_type else ""

                if "EventLog" in type_name:
                    fact = getattr(mem, 'atomic_fact', None)
                    if fact and fact.strip():
                        facts.append(fact.strip())

                elif "Episode" in type_name or "Episodic" in type_name:
                    summary = (
                        getattr(mem, 'summary', None)
                        or getattr(mem, 'narrative', None)
                        or getattr(mem, 'content', None)
                    )
                    if summary and summary.strip():
                        episodes.append(summary.strip())

            relevant_facts = "；".join(facts) if facts else ""
            relevant_episodes = "；".join(episodes) if episodes else ""

            print(
                f"  [evermemos] 🔍 search: {len(facts)} facts, "
                f"{len(episodes)} episodes ({elapsed_ms:.0f}ms)"
            )
            return relevant_facts, relevant_episodes

        except Exception as e:
            elapsed_ms = (_time.monotonic() - t0) * 1000
            print(f"  [evermemos] 🔍 search error ({elapsed_ms:.0f}ms): {e}")
            return "", ""
