"""
EverMemOS Client — 长期记忆适配器 (Async v3)

v3 改进：
  P0 — 控制面：config 集中管理、超时可配、失败熔断、命中率指标
  P1 — Foresight 内容注入：从"有 foresight"升级为"注入预测文本"
  P1 — Profile 加入 RRF 检索：按预算混合 facts + episodes + profile

记忆涌现架构：
  1. 每轮对话结束后 → asyncio.create_task(store_turn(...)) 后台存储
  2. EverMemOS 自动提取 Episode / EventLog(atomic_fact) / Profile / Foresight
  3. Session 开始时拉取 Profile + Foresight 文本 → 注入 Critic + Actor
  4. 每轮 RRF 检索：event_log + episodic_memory + profile → 注入 Actor
  5. Session 结束时 flush → 触发边界提取
"""

from __future__ import annotations

import asyncio
import math
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml
    _YAML = True
except ImportError:
    _YAML = False

try:
    from evermemos import AsyncEverMemOS
except ImportError:
    AsyncEverMemOS = None


# ─────────────────────────────────────────────────────────────
# Config Loader
# ─────────────────────────────────────────────────────────────

def _load_memory_config() -> dict:
    """Load config/memory_config.yaml; fall back to safe defaults.
    ENV override: OPENHER_MEMORY__<KEY>=value overrides any key.
    Example: OPENHER_MEMORY__RETRIEVE_METHOD=agentic
    """
    defaults = {
        "enabled": True,
        "retrieve_method": "rrf",
        "agentic_rollout_pct": 0,
        "search_timeout_sec": 3.0,
        "load_timeout_sec": 5.0,
        "foresight_max_items": 3,
        "foresight_max_chars": 200,   # P2b: per-item char budget
        "profile_max_items": 5,
        "facts_max_items": 5,
        "episodes_max_items": 3,
        "circuit_breaker_enabled": True,
        "failure_threshold": 5,
        "recovery_timeout_sec": 60,
        "log_hit_rates": True,
        "log_latency": True,
    }
    config_path = Path(__file__).parent.parent.parent / "config" / "memory_config.yaml"
    if _YAML and config_path.exists():
        try:
            data = yaml.safe_load(config_path.read_text()) or {}
            cfg = data.get("evermemos", data)
            merged = {**defaults, **cfg}
        except Exception as e:
            print(f"  [evermemos] config load error: {e} — using defaults")
            merged = dict(defaults)
    else:
        merged = dict(defaults)

    # P2a: OPENHER_MEMORY__<KEY> env overrides (case-insensitive key)
    prefix = "OPENHER_MEMORY__"
    for env_key, env_val in os.environ.items():
        if env_key.upper().startswith(prefix):
            cfg_key = env_key[len(prefix):].lower()
            if cfg_key in merged:
                # Coerce type from existing default
                orig = merged[cfg_key]
                try:
                    if isinstance(orig, bool):
                        merged[cfg_key] = env_val.lower() in ("1", "true", "yes")
                    elif isinstance(orig, int):
                        merged[cfg_key] = int(env_val)
                    elif isinstance(orig, float):
                        merged[cfg_key] = float(env_val)
                    else:
                        merged[cfg_key] = env_val
                except ValueError:
                    pass  # Keep original on parse error

    return merged

_CFG = _load_memory_config()


# ─────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────

@dataclass
class SessionContext:
    """
    Per-session context pulled from EverMemOS at session start.
    Cached locally to avoid repeated API calls within the same session.
    """
    user_profile: str          # Human-readable profile text for Critic/Actor injection
    episode_summary: str       # Narrative episodes for "history recall" injection
    foresight_text: str        # P1: Foresight prediction text for Actor injection
    interaction_count: int     # Total past interactions with this user
    has_history: bool          # True if user has any stored memories
    relationship_depth: float  # 0~1, semantic richness-based (not pure count)
    pending_foresight: float   # 0~1, whether there are active foresight memories
    # Metrics
    _fact_count: int = field(default=0, repr=False)
    _profile_count: int = field(default=0, repr=False)
    _episode_count: int = field(default=0, repr=False)
    _foresight_count: int = field(default=0, repr=False)


# ─────────────────────────────────────────────────────────────
# Circuit Breaker
# ─────────────────────────────────────────────────────────────

class _CircuitBreaker:
    """Simple consecutive-failure circuit breaker."""

    def __init__(self, threshold: int = 5, recovery_sec: float = 60.0):
        self._threshold = threshold
        self._recovery_sec = recovery_sec
        self._failures = 0
        self._open_at: Optional[float] = None

    @property
    def is_open(self) -> bool:
        if self._open_at is None:
            return False
        if time.monotonic() - self._open_at > self._recovery_sec:
            self._open_at = None
            self._failures = 0
            print("  [evermemos] 🔄 circuit breaker reset (recovery timeout)")
            return False
        return True

    def record_success(self):
        self._failures = 0

    def record_failure(self):
        self._failures += 1
        if self._failures >= self._threshold and self._open_at is None:
            self._open_at = time.monotonic()
            print(f"  [evermemos] ⚡ circuit OPEN after {self._failures} failures")


class _NoOpBreaker:
    """No-op breaker for when circuit_breaker_enabled=false."""
    is_open = False
    def record_success(self): pass
    def record_failure(self): pass


def _fmt_latency(elapsed_ms: float) -> str:
    """Format latency string, respecting log_latency config flag."""
    if _CFG.get("log_latency", True):
        return f" ({elapsed_ms:.0f}ms)"
    return ""


# ─────────────────────────────────────────────────────────────
# Main Client
# ─────────────────────────────────────────────────────────────

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
        # Circuit breaker: true no-op when disabled
        cb_enabled = _CFG.get("circuit_breaker_enabled", True)
        if cb_enabled:
            self._cb = _CircuitBreaker(
                threshold=_CFG["failure_threshold"],
                recovery_sec=_CFG["recovery_timeout_sec"],
            )
        else:
            self._cb = _NoOpBreaker()

        if not _CFG.get("enabled", True):
            print("⚠ EverMemOS disabled via config")
            return

        if AsyncEverMemOS and self._api_key:
            try:
                self._client = AsyncEverMemOS(
                    api_key=self._api_key,
                    timeout=10.0,
                )
                self._mem = self._client.v0.memories
                self._initialized = True
                print(f"✓ EverMemOS client initialized (retrieve_method={_CFG['retrieve_method']})")
            except Exception as e:
                print(f"⚠ EverMemOS init failed: {e}")
        else:
            if not AsyncEverMemOS:
                print("⚠ EverMemOS not installed (pip install evermemos)")
            else:
                print("⚠ EVERMEMOS_API_KEY not set — long-term memory disabled")

    @property
    def available(self) -> bool:
        return self._initialized and self._mem is not None and not self._cb.is_open

    # ─────────────────────────────────────────────────────────────
    # Session Lifecycle
    # ─────────────────────────────────────────────────────────────

    async def load_session_context(
        self,
        user_id: str,
        persona_id: str,
    ) -> SessionContext:
        """
        Called once at session start. Pulls user profile + episodes + foresight
        content from EverMemOS and builds a SessionContext for use throughout
        the session.

        Returns a zero-context SessionContext if unavailable or error.
        """
        empty = SessionContext(
            user_profile="",
            episode_summary="",
            foresight_text="",
            interaction_count=0,
            has_history=False,
            relationship_depth=0.0,
            pending_foresight=0.0,
        )

        if not self.available:
            return empty

        t0 = time.monotonic()
        try:
            # EverMemOS v0 API only supports single memory_type per call.
            # Fire 4 parallel queries for max throughput.
            timeout = _CFG["load_timeout_sec"]

            async def _get_type(mtype: str):
                try:
                    return await self._mem.get(
                        extra_query={"user_id": user_id, "memory_type": mtype},
                        timeout=timeout,
                    )
                except Exception:
                    return None

            results = await asyncio.gather(
                _get_type("profile"),
                _get_type("event_log"),
                _get_type("episodic_memory"),
                _get_type("foresight"),
            )

            # Merge all memories from parallel responses
            memories = []
            for resp in results:
                if resp and resp.result and resp.result.memories:
                    memories.extend(resp.result.memories)

            if not memories:
                # P1b: healthy request (0 results) — reset failure count
                self._cb.record_success()
                return empty

            profile_lines = []
            fact_lines = []
            episode_lines = []
            foresight_lines = []
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
                    summary = (
                        getattr(mem, 'summary', None)
                        or getattr(mem, 'narrative', None)
                        or getattr(mem, 'content', None)
                    )
                    if summary and summary.strip():
                        episode_lines.append(summary.strip())

                elif "Foresight" in type_name:
                    # P1: Extract foresight CONTENT (not just count)
                    content = (
                        getattr(mem, 'content', None)
                        or getattr(mem, 'prediction', None)
                        or getattr(mem, 'summary', None)
                    )
                    if content and content.strip():
                        foresight_lines.append(content.strip())

            # Build readable profile text
            max_facts = _CFG["facts_max_items"]
            max_profile = _CFG["profile_max_items"]
            parts = []
            if profile_lines:
                parts.append("【用户画像】" + "；".join(profile_lines[:max_profile]))
            if fact_lines:
                parts.append("【已知偏好/事实】" + "；".join(fact_lines[:max_facts]))
            user_profile = "\n".join(parts) if parts else ""

            # Episode summary (latest 3)
            max_eps = _CFG["episodes_max_items"]
            episode_summary = "；".join(episode_lines[-max_eps:]) if episode_lines else ""

            # P1+P2b: Foresight text with item count AND per-item char budget
            max_fs = _CFG["foresight_max_items"]
            max_fs_chars = _CFG.get("foresight_max_chars", 200)
            foresight_text = ""
            if foresight_lines:
                fs_items = [s[:max_fs_chars] for s in foresight_lines[:max_fs]]
                foresight_text = "；".join(fs_items)

            # Semantic relationship depth (data richness based)
            data_richness = (
                len(fact_lines) * 2
                + len(profile_lines) * 3
                + len(episode_lines) * 5
            )
            depth = 1.0 - math.exp(-data_richness / 30.0) if data_richness > 0 else 0.0
            if data_richness == 0 and interaction_count > 0:
                depth = 1.0 - math.exp(-interaction_count / 40.0)

            foresight_count = len(foresight_lines)
            pending_fs = 1.0 - math.exp(-foresight_count / 1.5) if foresight_count > 0 else 0.0

            self._cb.record_success()
            elapsed_ms = (time.monotonic() - t0) * 1000

            ctx = SessionContext(
                user_profile=user_profile,
                episode_summary=episode_summary,
                foresight_text=foresight_text,
                interaction_count=interaction_count,
                has_history=bool(memories),
                relationship_depth=round(depth, 3),
                pending_foresight=round(pending_fs, 3),
                _fact_count=len(fact_lines),
                _profile_count=len(profile_lines),
                _episode_count=len(episode_lines),
                _foresight_count=foresight_count,
            )

            if ctx.has_history and _CFG["log_hit_rates"]:
                print(
                    f"  [evermemos] 📚 loaded{_fmt_latency(elapsed_ms)}: "
                    f"{interaction_count} interactions, depth={depth:.2f}, "
                    f"facts={len(fact_lines)}, profile={len(profile_lines)}, "
                    f"episodes={len(episode_lines)}, foresights={foresight_count}"
                    + (f" [foresight_text: {foresight_text[:40]}...]" if foresight_text else "")
                )

            return ctx

        except Exception as e:
            self._cb.record_failure()
            elapsed_ms = (time.monotonic() - t0) * 1000
            print(f"  [evermemos] load_session_context error{_fmt_latency(elapsed_ms)}: {e}")
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
            await self._mem.add(
                content=user_message,
                create_time=now_iso,
                message_id=str(uuid.uuid4()),
                sender=user_id,
                sender_name=user_name,
                role="user",
                group_id=group_id,
            )
            await self._mem.add(
                content=agent_reply,
                create_time=now_iso,
                message_id=str(uuid.uuid4()),
                sender=persona_id,
                sender_name=persona_name,
                role="assistant",
                group_id=group_id,
            )
            self._cb.record_success()

        except Exception as e:
            self._cb.record_failure()
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
        """
        depth = ctx.relationship_depth
        trust = 1.0 - math.exp(-ctx.interaction_count / 40.0) if ctx.interaction_count > 0 else 0.0

        return {
            'relationship_depth': round(depth, 3),
            'emotional_valence': 0.0,
            'trust_level': round(trust, 3),
            'pending_foresight': round(ctx.pending_foresight, 3),
        }

    # ─────────────────────────────────────────────────────────────
    # Query-Based Relevance Retrieval (Phase 3) — P1 enhanced
    # ─────────────────────────────────────────────────────────────

    async def search_relevant_memories(
        self,
        query: str,
        user_id: str,
    ) -> tuple[str, str, str]:
        """
        Search for memories most relevant to the current user message.

        P1 improvement: Also searches profile type and returns profile context.
        Uses retrieve_method from config (rrf / hybrid / agentic).

        Returns: (relevant_facts, relevant_episodes, relevant_profile)
                 Empty strings on error or no results.
        """
        if not self.available or not query.strip():
            return "", "", ""

        t0 = time.monotonic()
        retrieve_method = _CFG.get("retrieve_method", "rrf")

        # P2: Agentic rollout percentage
        agentic_pct = _CFG.get("agentic_rollout_pct", 0)
        if agentic_pct > 0:
            import random
            if random.randint(1, 100) <= agentic_pct:
                retrieve_method = "agentic"

        # Search doesn't need memory_type filter — EverMemOS returns
        # relevant results across all types by default.

        try:
            query_params = {
                "query": query,
                "user_id": user_id,
                "retrieve_method": retrieve_method,
            }
            try:
                response = await self._mem.search(
                    extra_query=query_params,
                    timeout=_CFG["search_timeout_sec"],
                )
            except Exception:
                # SDK compat fallback: try search_method key
                query_params["search_method"] = query_params.pop("retrieve_method")
                response = await self._mem.search(
                    extra_query=query_params,
                    timeout=_CFG["search_timeout_sec"],
                )

            elapsed_ms = (time.monotonic() - t0) * 1000

            if not response or not response.result or not response.result.memories:
                print(f"  [evermemos] 🔍 search: 0 results{_fmt_latency(elapsed_ms)} [{retrieve_method}]")
                self._cb.record_success()
                return "", "", ""

            memories = response.result.memories
            facts = []
            episodes = []
            profile_attrs = []

            max_facts = _CFG["facts_max_items"]
            max_eps = _CFG["episodes_max_items"]
            max_profile = _CFG["profile_max_items"]

            for mem in memories:
                mem_type = getattr(mem, '__class__', None)
                type_name = mem_type.__name__ if mem_type else ""

                if "EventLog" in type_name and len(facts) < max_facts:
                    fact = getattr(mem, 'atomic_fact', None)
                    if fact and fact.strip():
                        facts.append(fact.strip())

                elif ("Episode" in type_name or "Episodic" in type_name) and len(episodes) < max_eps:
                    summary = (
                        getattr(mem, 'summary', None)
                        or getattr(mem, 'narrative', None)
                        or getattr(mem, 'content', None)
                    )
                    if summary and summary.strip():
                        episodes.append(summary.strip())

                elif "Profile" in type_name and len(profile_attrs) < max_profile:
                    profile_data = getattr(mem, 'profile_data', None)
                    if profile_data:
                        for k, v in profile_data.items():
                            if v and len(profile_attrs) < max_profile:
                                profile_attrs.append(f"{k}: {v}")

            relevant_facts = "；".join(facts) if facts else ""
            relevant_episodes = "；".join(episodes) if episodes else ""
            relevant_profile = "；".join(profile_attrs) if profile_attrs else ""

            self._cb.record_success()

            if _CFG["log_hit_rates"]:
                print(
                    f"  [evermemos] 🔍 search{_fmt_latency(elapsed_ms)} [{retrieve_method}]: "
                    f"facts={len(facts)}, episodes={len(episodes)}, profile={len(profile_attrs)}"
                )

            return relevant_facts, relevant_episodes, relevant_profile

        except Exception as e:
            self._cb.record_failure()
            elapsed_ms = (time.monotonic() - t0) * 1000
            print(f"  [evermemos] 🔍 search error{_fmt_latency(elapsed_ms)}: {e}")
            return "", "", ""
