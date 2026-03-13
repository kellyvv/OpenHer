"""
EverMemOS Client — 长期记忆适配器 (Async v4 — Self-Hosted)

v4 改进：
  P0 — 从 evermemos SDK (Cloud) 迁移到 httpx 直连 (Self-Hosted Open Source)
  沿用 v3 全部功能：config 集中管理、超时可配、失败熔断、命中率指标
  Foresight / Profile / RRF 检索逻辑不变

记忆涌现架构：
  1. 每轮对话结束后 → asyncio.create_task(store_turn(...)) 后台存储
  2. EverMemOS 自动提取 Episode / EventLog(atomic_fact) / Profile / Foresight
  3. Session 开始时拉取 Profile + Foresight 文本 → 注入 Critic + Actor
  4. 每轮 RRF 检索：event_log + episodic_memory + profile → 注入 Actor
  5. Session 结束时 flush → 触发边界提取

API 变化 (Cloud → Self-Hosted):
  - Base URL:  api.evermind.ai/api/v0 → localhost:1995/api/v1
  - Auth:      Bearer token → 无需 (local)
  - SDK:       evermemos.AsyncEverMemOS → httpx.AsyncClient
  - 接口字段完全兼容，仅 URL path 不同
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
    import httpx
except ImportError:
    httpx = None


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
        "base_url": "http://localhost:1995/api/v1",
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
    config_path = Path(__file__).parent / "memory_config.yaml"
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
    Async EverMemOS adapter for OpenHer (Self-Hosted — httpx).

    All public methods are async. Use asyncio.create_task() for fire-and-forget
    storage operations to avoid blocking the main conversation flow.

    v4: Uses httpx.AsyncClient to call EverMemOS open-source REST API
    directly (localhost:1995/api/v1) instead of evermemos SDK cloud calls.
    """

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self._base_url = (
            base_url
            or os.environ.get("EVERMEMOS_BASE_URL")
            or _CFG.get("base_url")
            or "http://localhost:1995/api/v1"
        )
        # Normalize: strip trailing slash, ensure /api/v1 suffix
        self._base_url = self._base_url.rstrip("/")
        if not self._base_url.endswith("/api/v1"):
            # If user provides "http://localhost:1995", auto-append
            if "/api/" not in self._base_url:
                self._base_url += "/api/v1"

        # Optional API key (for cloud fallback or authenticated setups)
        self._api_key = api_key or os.environ.get("EVERMEMOS_API_KEY")

        self._client: Optional[httpx.AsyncClient] = None
        self._initialized = False

        # Circuit breaker
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

        if httpx is None:
            print("⚠ httpx not installed (pip install httpx)")
            return

        try:
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=10.0,
                trust_env=False,  # Bypass system/mac proxy for localhost
            )
            self._initialized = True
            print(f"✓ EverMemOS client initialized (base_url={self._base_url}, retrieve_method={_CFG['retrieve_method']})")
        except Exception as e:
            print(f"⚠ EverMemOS init failed: {e}")

    async def verify_connection(self) -> bool:
        """Validate API key by making a lightweight request.
        Call at server startup to fail fast on auth errors.
        Returns True if connection is valid, False otherwise.
        """
        if not self._initialized or not self._client:
            return False
        try:
            resp = await self._client.request(
                "GET", "/memories",
                json={"user_id": "__healthcheck__", "memory_type": "profile", "page_size": 1},
                timeout=8.0,
            )
            if resp.status_code == 401:
                print(f"✗ EverMemOS API key 无效 (HTTP 401) — 请检查 .env 中的 EVERMEMOS_API_KEY")
                self._initialized = False
                return False
            if resp.status_code == 200:
                print(f"  ↳ EverMemOS API key 验证通过 ✓")
                return True
            # Other status codes (e.g. 500) — warn but don't disable
            print(f"  ↳ EverMemOS health check: HTTP {resp.status_code} (non-fatal)")
            return True
        except Exception as e:
            print(f"  ↳ EverMemOS health check failed: {e} (non-fatal)")
            return True  # Network issue, don't disable — might be transient

    @property
    def available(self) -> bool:
        return self._initialized and self._client is not None and not self._cb.is_open

    # ─────────────────────────────────────────────────────────────
    # Session Lifecycle
    # ─────────────────────────────────────────────────────────────

    async def load_session_context(
        self,
        user_id: str,
        persona_id: str,
        group_id: str = "",
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
            timeout = _CFG["load_timeout_sec"]

            async def _get_type(mtype: str):
                try:
                    body = {"memory_type": mtype}
                    if group_id:
                        body["group_ids"] = [group_id]
                    else:
                        body["user_id"] = user_id
                    resp = await self._client.request(
                        "GET", "/memories",
                        json=body,
                        timeout=timeout,
                    )
                    if resp.status_code == 200:
                        return resp.json()
                    return None
                except Exception:
                    return None

            results = await asyncio.gather(
                _get_type("profile"),
                _get_type("event_log"),
                _get_type("episodic_memory"),
                _get_type("foresight"),
            )

            # Merge all memories from parallel responses
            all_memories = []
            for resp_data in results:
                if resp_data and resp_data.get("result"):
                    mems = resp_data["result"].get("memories", [])
                    if isinstance(mems, list):
                        all_memories.extend(mems)

            if not all_memories:
                self._cb.record_success()
                return empty

            profile_lines = []
            fact_lines = []
            episode_lines = []
            foresight_lines = []
            interaction_count = 0

            for mem in all_memories:
                # Determine memory type from response structure
                if "profile_data" in mem:
                    # Profile type
                    profile_data = mem.get("profile_data", {})
                    if profile_data:
                        for k, v in profile_data.items():
                            if v and k not in ("id", "memory_type", "user_id", "user_name"):
                                profile_lines.append(f"{k}: {v}")
                    interaction_count += mem.get("memcell_count", 0) or 0

                elif "atomic_fact" in mem:
                    # EventLog type
                    fact = mem.get("atomic_fact", "")
                    if fact and fact.strip():
                        fact_lines.append(fact.strip())

                elif "episode_id" in mem or "summary" in mem:
                    # Episodic memory type
                    summary = (
                        mem.get("summary")
                        or mem.get("narrative")
                        or mem.get("content")
                    )
                    if summary and summary.strip():
                        episode_lines.append(summary.strip())

                elif "foresight" in mem:
                    # Foresight type
                    content = (
                        mem.get("content")
                        or mem.get("foresight")
                        or mem.get("prediction")
                        or mem.get("summary")
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
                has_history=bool(all_memories),
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
            # Store user message
            r1 = await self._client.post("/memories", json={
                "content": user_message,
                "create_time": now_iso,
                "message_id": str(uuid.uuid4()),
                "sender": user_id,
                "sender_name": user_name,
                "role": "user",
                "group_id": group_id,
            })
            print(f"  [evermemos] POST user msg: HTTP {r1.status_code} gid={group_id} sender={user_id}")
            if r1.status_code not in (200, 202):
                print(f"  [evermemos] store user msg failed: {r1.text[:200]}")
                self._cb.record_failure()
                return
            # Store agent reply (flush=True → trigger immediate memory extraction)
            r2 = await self._client.post("/memories", json={
                "content": agent_reply,
                "create_time": now_iso,
                "message_id": str(uuid.uuid4()),
                "sender": persona_id,
                "sender_name": persona_name,
                "role": "assistant",
                "group_id": group_id,
                "flush": True,
            })
            print(f"  [evermemos] POST agent msg: HTTP {r2.status_code} gid={group_id} sender={persona_id} flush=True")
            if r2.status_code not in (200, 202):
                print(f"  [evermemos] store agent msg failed: {r2.text[:200]}")
                self._cb.record_failure()
                return
            self._cb.record_success()

        except Exception as e:
            self._cb.record_failure()
            print(f"  [evermemos] store_turn error: {e}")

    async def store_proactive_turn(
        self,
        persona_id: str,
        persona_name: str,
        group_id: str,
        reply: str,
        tick_id: str,
    ) -> None:
        """
        Store a proactive message (AI-initiated, no user_message).
        Uses message_id=tick_id for idempotent retry (R25).
        """
        if not self.available:
            return

        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime())
        msg_id = f"proactive_{tick_id}"

        try:
            await self._client.post("/memories", json={
                "content": reply,
                "create_time": now_iso,
                "message_id": msg_id,
                "sender": persona_id,
                "sender_name": persona_name,
                "role": "assistant",
                "group_id": group_id,
                "refer_list": ["proactive"],
            })
            self._cb.record_success()
            print(f"  [evermemos] stored proactive turn (tick={tick_id[:8]})")
        except Exception as e:
            self._cb.record_failure()
            print(f"  [evermemos] store_proactive error: {e}")

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
            await self._client.post("/memories", json={
                "content": "[session_end]",
                "create_time": time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime()),
                "message_id": str(uuid.uuid4()),
                "sender": persona_id,
                "sender_name": "system",
                "role": "assistant",
                "group_id": group_id,
                "flush": True,
            })
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
        group_id: str = "",
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

        try:
            # EverMemOS API: GET /memories/search with JSON body
            body = {
                "query": query,
                "retrieve_method": retrieve_method,
            }
            if group_id:
                body["group_ids"] = [group_id]
            else:
                body["user_id"] = user_id
            resp = await self._client.request(
                "GET",
                "/memories/search",
                json=body,
                timeout=_CFG["search_timeout_sec"],
            )

            elapsed_ms = (time.monotonic() - t0) * 1000

            if resp.status_code != 200:
                print(f"  [evermemos] 🔍 search: HTTP {resp.status_code}{_fmt_latency(elapsed_ms)}")
                self._cb.record_success()
                return "", "", ""

            data = resp.json()
            result = data.get("result", {})
            memories = result.get("memories", [])

            if not memories:
                print(f"  [evermemos] 🔍 search: 0 results{_fmt_latency(elapsed_ms)} [{retrieve_method}]")
                self._cb.record_success()
                return "", "", ""

            facts = []
            episodes = []
            profile_attrs = []

            max_facts = _CFG["facts_max_items"]
            max_eps = _CFG["episodes_max_items"]
            max_profile = _CFG["profile_max_items"]

            for mem in memories:
                if "atomic_fact" in mem and len(facts) < max_facts:
                    fact = mem.get("atomic_fact", "")
                    if fact and fact.strip():
                        facts.append(fact.strip())

                elif ("episode_id" in mem or "summary" in mem) and len(episodes) < max_eps:
                    summary = (
                        mem.get("summary")
                        or mem.get("narrative")
                        or mem.get("content")
                    )
                    if summary and summary.strip():
                        episodes.append(summary.strip())

                elif "profile_data" in mem and len(profile_attrs) < max_profile:
                    profile_data = mem.get("profile_data", {})
                    if profile_data:
                        for k, v in profile_data.items():
                            if v and len(profile_attrs) < max_profile:
                                if k not in ("id", "memory_type", "user_id", "user_name"):
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
