"""
Gateway — FastAPI WebSocket server for OpenHer (Genome v10 Hybrid).

Provides:
  - WebSocket endpoint for real-time chat with Genome v10 lifecycle
  - REST APIs for persona management, status
  - Agent state persistence (neural network weights + drive metabolism)
  - Session auto-cleanup with TTL
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import uuid
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import uuid as _uuid

from persona import PersonaLoader
from providers.llm import LLMClient
from agent.chat_agent import ChatAgent
from providers.media.tts_engine import TTSEngine, TTSProvider
from agent.skills import SkillEngine
from engine.state_store import StateStore
from engine.chat_log_store import ChatLogStore
from memory.memory_store import MemoryStore
from providers.memory.evermemos.evermemos_client import EverMemOSClient
from providers.api_config import get_llm_config, get_tts_config, get_memory_config
from cron_scheduler import CronScheduler
from output_router import stream_to_ws as _stream_to_ws
from engine.genome import DRIVE_LABELS

# ──────────────────────────────────────────────────────────────
# Load env
# ──────────────────────────────────────────────────────────────

load_dotenv()

# ──────────────────────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="OpenHer",
    description="AI Companion Server — Genome v10 Hybrid Engine",
    version="0.5.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────
# Global services (initialized at startup)
# ──────────────────────────────────────────────────────────────

persona_loader: PersonaLoader = None
llm_client: LLMClient = None
tts_engine: TTSEngine = None
skill_engine: SkillEngine = None
skills_prompt: str = ""
state_store: StateStore = None
chat_log_store: ChatLogStore = None
memory_store: MemoryStore = None
evermemos: EverMemOSClient = None
cron_scheduler: CronScheduler = None
genome_data_dir: str = ""

# Active chat sessions: session_id → (ChatAgent, last_active_time)
active_sessions: dict[str, tuple[ChatAgent, float]] = {}

# Session TTL: auto-clean sessions older than 30 minutes
SESSION_TTL_SECONDS = 30 * 60

# Proactive heartbeat
_proactive_task: Optional[asyncio.Task] = None
_INSTANCE_ID = str(_uuid.uuid4())[:8]  # unique per server instance
_PROACTIVE_INTERVAL = 300  # seconds between heartbeat sweeps

# WebSocket connections: session_id → WebSocket (for proactive push)
_ws_connections: dict[str, 'WebSocket'] = {}

# Proactive config (loaded from memory_config.yaml in startup)
_proactive_cfg: dict = {}

# Proactive metrics (online observability)
_proactive_metrics = {
    'ticks_total': 0,       # total proactive_tick() calls
    'impulse_triggered': 0, # _has_impulse() returned non-None
    'silence_chosen': 0,    # Actor chose 静默
    'outbox_enqueued': 0,   # messages entered outbox
    'outbox_blocked': 0,    # blocked by 3-layer guard
    'ws_push_ok': 0,        # WebSocket push succeeded
    'ws_push_fail': 0,      # WebSocket push failed (offline or error)
    'outbox_delivered': 0,  # final delivered count
    'outbox_retries': 0,    # retry attempts (re-delivery of failed messages)
}


@app.on_event("startup")
async def startup():
    """Initialize all services on server start."""
    global persona_loader, llm_client, tts_engine, skill_engine, skills_prompt
    global state_store, chat_log_store, memory_store, evermemos, cron_scheduler, genome_data_dir

    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Load personas
    persona_loader = PersonaLoader(os.path.join(base_dir, "persona", "personas"))
    personas = persona_loader.load_all()
    print(f"✓ 加载了 {len(personas)} 个角色: {list(personas.keys())}")

    # 2. Create LLM client (config/api.yaml → env var override)
    llm_cfg = get_llm_config()
    llm_client = LLMClient(
        provider=llm_cfg["provider"],
        model=llm_cfg["model"],
        temperature=llm_cfg.get("temperature", 0.92),
        max_tokens=llm_cfg.get("max_tokens", 1024),
    )

    # 3. Create TTS engine (config/api.yaml → env var override)
    tts_cfg = get_tts_config()
    tts_engine = TTSEngine(
        provider=TTSProvider(tts_cfg["provider"]),
        cache_dir=os.path.join(base_dir, tts_cfg["cache_dir"]),
        openai_api_key=tts_cfg["api_keys"].get("openai"),
        dashscope_api_key=tts_cfg["api_keys"].get("dashscope"),
        minimax_api_key=tts_cfg["api_keys"].get("minimax"),
        minimax_model=tts_cfg.get("minimax_model", "speech-2.8-turbo"),
    )

    # 4. Load skills
    skill_engine = SkillEngine(os.path.join(base_dir, "skills"))
    loaded_skills = skill_engine.load_all()
    skills_prompt = skill_engine.build_skills_prompt()
    cron_skills = skill_engine.get_cron_skills()
    print(f"✓ 加载了 {len(loaded_skills)} 个技能, {len(cron_skills)} 个定时任务")

    # 5. Data directories
    data_dir = os.path.join(base_dir, ".data")
    genome_data_dir = os.path.join(data_dir, "genome")
    os.makedirs(genome_data_dir, exist_ok=True)

    # 6. State persistence
    state_store = StateStore(os.path.join(data_dir, "openher.db"))

    # 6b. Chat log persistence (display-only, independent from engine state)
    chat_log_store = ChatLogStore(os.path.join(data_dir, "chat.db"))

    # 7. Memory store (config/api.yaml → memory.soulmem.db_path)
    from providers.config import get_memory_provider_config
    _mem_prov_cfg = get_memory_provider_config()
    _soulmem_db = os.path.join(base_dir, _mem_prov_cfg["soulmem"]["db_path"])
    os.makedirs(os.path.dirname(_soulmem_db) or ".", exist_ok=True)
    memory_store = MemoryStore(_soulmem_db)

    # 7b. EverMemOS long-term memory (config/api.yaml → env var override)
    mem_cfg = get_memory_config()
    if mem_cfg["enabled"] and (mem_cfg["base_url"] or mem_cfg["api_key"]):
        evermemos = EverMemOSClient(
            base_url=mem_cfg["base_url"] or None,
            api_key=mem_cfg["api_key"] or None,
        )
    else:
        evermemos = None
        print("ℹ EverMemOS: 未配置或已禁用，使用本地 MemoryStore")

    # 8. Cron scheduler
    if cron_skills:
        cron_scheduler = CronScheduler()
        cron_scheduler.set_message_generator(_cron_generate_message)
        cron_scheduler.set_message_callback(_cron_deliver_message)
        cron_scheduler.register_skills(cron_skills, persona_ids=list(personas.keys()))
        cron_scheduler.start()

    # 9. Mount static files
    static_dir = os.path.join(base_dir, "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # 10. Load proactive config + start heartbeat loop
    global _proactive_task, _proactive_cfg
    try:
        import yaml as _yaml_cfg
        from pathlib import Path as _PathCfg
        _cfg_path = _PathCfg(base_dir) / "providers" / "memory" / "evermemos" / "memory_config.yaml"
        _cfg_raw = _yaml_cfg.safe_load(_cfg_path.read_text()).get("evermemos", {}) if _cfg_path.exists() else {}
    except Exception:
        _cfg_raw = {}
    _proactive_cfg = {
        'cooldown_hours': _cfg_raw.get('proactive_cooldown_hours', 4),
        'max_pending': _cfg_raw.get('proactive_max_pending', 3),
        'lock_ttl': _cfg_raw.get('proactive_lock_ttl_sec', 600),
    }
    _proactive_task = asyncio.create_task(_proactive_heartbeat_loop())
    print(f"✓ 主动消息心跳已启动 (cooldown={_proactive_cfg['cooldown_hours']}h, ttl={_proactive_cfg['lock_ttl']}s)")

    print("✓ OpenHer 服务启动完成 (v0.5.0 — Genome v10 Hybrid Engine)")
    print("  → 演示页面: http://localhost:8800/discover")


@app.on_event("shutdown")
async def shutdown():
    """Save all active sessions and close DBs."""
    # Stop proactive heartbeat
    if _proactive_task and not _proactive_task.done():
        _proactive_task.cancel()
        try:
            await _proactive_task
        except asyncio.CancelledError:
            pass
    if cron_scheduler:
        cron_scheduler.stop()
    if state_store:
        for sid, (agent, _) in active_sessions.items():
            _persist_agent(agent)
        state_store.close()
    if memory_store:
        memory_store.close()
    if chat_log_store:
        chat_log_store.close()
    # Flush EverMemOS for all active sessions
    if evermemos and evermemos.available:
        tasks = [
            evermemos.close_session(
                user_id=agent.evermemos_uid,
                persona_id=agent.persona.persona_id,
                group_id=agent._group_id,
            )
            for _, (agent, _) in active_sessions.items()
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    print("✓ 状态已保存，服务关闭")


# ──────────────────────────────────────────────────────────────
# Cron message generation + delivery
# ──────────────────────────────────────────────────────────────

async def _cron_generate_message(skill_prompt: str, persona_id: str) -> str:
    """Generate a proactive cron message using an isolated ChatAgent."""
    persona = persona_loader.get(persona_id)
    if not persona:
        return ""
    from providers.llm.client import ChatMessage
    messages = [
        ChatMessage(role="system", content=f"你是{persona.name}。{skill_prompt}"),
        ChatMessage(role="user", content="请生成一条主动消息"),
    ]
    response = await llm_client.chat(messages)
    return response.content


async def _cron_deliver_message(persona_id: str, skill_id: str, message: str) -> None:
    """Deliver a cron message — store in memory for next session."""
    print(f"[cron] 📨 {persona_id}/{skill_id}: {message[:60]}...")
    if memory_store:
        memory_store.add(
            user_id="__broadcast__",
            persona_id=persona_id,
            content=f"[{skill_id}] {message}",
            category="event",
            importance=0.6,
        )


# ──────────────────────────────────────────────────────────────
# Proactive Heartbeat — Drive-driven autonomous messaging
# ──────────────────────────────────────────────────────────────

async def _proactive_heartbeat_loop():
    """
    Background loop: sweep active sessions, run proactive_tick,
    enqueue results to outbox, deliver pending messages.
    """
    await asyncio.sleep(60)  # Initial delay: let sessions warm up
    while True:
        try:
            await _proactive_sweep()
        except Exception as e:
            print(f"[proactive] ❌ heartbeat error: {e}")
        await asyncio.sleep(_PROACTIVE_INTERVAL)


async def _proactive_sweep():
    """One sweep: generate new proactive messages + retry pending outbox."""
    if not state_store or not active_sessions:
        return

    cooldown_h = _proactive_cfg.get('cooldown_hours', 4)
    max_pending = _proactive_cfg.get('max_pending', 3)
    lock_ttl = _proactive_cfg.get('lock_ttl', 600)

    for sid, (agent, _last) in list(active_sessions.items()):
        uid = agent.user_id
        pid = agent.persona.persona_id

        # Cross-instance lock (R7/R23/R28)
        if not state_store.try_acquire_lock(uid, pid, _INSTANCE_ID, ttl=lock_ttl):
            continue

        try:
            # ── Phase 1: Generate new proactive message ──
            _proactive_metrics['ticks_total'] += 1
            result = await agent.proactive_tick()
            if result is not None:
                _proactive_metrics['impulse_triggered'] += 1
                drive_id = result.get('drive_id', 'unknown')
                depth = agent._relationship_ema.get('relationship_depth', 0.0)
                band = 'deep' if depth > 0.6 else 'mid' if depth > 0.3 else 'shallow'
                bucket = int(time.time() // (cooldown_h * 3600))
                dedup_key = f"{drive_id}:{band}:{bucket}"

                if state_store.outbox_can_enqueue(
                    uid, pid, dedup_key,
                    cooldown_hours=cooldown_h, max_pending=max_pending,
                ):
                    state_store.outbox_insert(
                        uid, pid, result['tick_id'],
                        result['reply'], result.get('modality', '文字'),
                        result.get('monologue', ''), drive_id, dedup_key,
                    )
                    _proactive_metrics['outbox_enqueued'] += 1
                else:
                    _proactive_metrics['outbox_blocked'] += 1
                    print(f"  [proactive] 🛑 outbox guard blocked: {dedup_key}")
            elif result is None and agent._has_impulse():
                # Had impulse but Actor chose silence
                _proactive_metrics['silence_chosen'] += 1

            # ── Phase 2: Deliver all pending messages (incl. retries) ──
            pending = state_store.outbox_get_pending(uid, pid)
            for row in pending:
                is_retry = row.get('status') == 'pending' and row['tick_id'] != (result or {}).get('tick_id')
                if is_retry:
                    _proactive_metrics['outbox_retries'] += 1
                await _deliver_proactive_msg(agent, sid, row)

            # ── Persist proactive state via CAS (Bug 4) ──
            _persist_agent(agent)

        finally:
            state_store.release_lock(uid, pid, _INSTANCE_ID)


async def _deliver_proactive_msg(agent: ChatAgent, session_id: str, row: dict):
    """Deliver one proactive message: outbox SM + WebSocket push + EverMemOS."""
    uid = row['user_id']
    pid = row['persona_id']
    tick_id = row['tick_id']
    reply = row['reply']
    modality = row.get('modality', '文字')

    # Outbox: pending → sending (R31)
    msg = state_store.outbox_try_send(uid, pid, tick_id)
    if not msg:
        return  # Already taken by another instance

    # ── Push to user via WebSocket ──
    ws = _ws_connections.get(session_id)
    if not ws:
        # User offline: keep pending for next sweep
        state_store.outbox_mark_failed(uid, pid, tick_id)
        return

    try:
        await ws.send_json({
            "type": "proactive",
            "content": reply,
            "modality": modality,
            "drive": row.get('drive_id', ''),
            "persona": agent.persona.name,
        })
        print(f"  [proactive] 📨 WS pushed: {reply[:40]}")
        _proactive_metrics['ws_push_ok'] += 1
    except Exception as ws_err:
        # WS send failed: mark failed, do NOT proceed to delivered
        print(f"  [proactive] WS push failed: {ws_err}")
        _proactive_metrics['ws_push_fail'] += 1
        state_store.outbox_mark_failed(uid, pid, tick_id)
        return

    # WS push succeeded → store in EverMemOS (idempotent, R25)
    try:
        if evermemos and evermemos.available:
            await evermemos.store_proactive_turn(
                persona_id=pid,
                persona_name=agent.persona.name,
                group_id=agent._group_id,
                reply=reply,
                tick_id=tick_id,
            )
    except Exception as e:
        print(f"  [proactive] EverMemOS store failed (non-fatal): {e}")

    # Only mark delivered after successful WS push
    state_store.outbox_mark_delivered(uid, pid, tick_id)
    _proactive_metrics['outbox_delivered'] += 1
    print(f"  [proactive] ✅ delivered: {reply[:40]}")


@app.get("/api/proactive/metrics")
async def proactive_metrics():
    """Proactive messaging observability: rates and counters."""
    m = dict(_proactive_metrics)
    total = m['ticks_total'] or 1  # avoid div-by-zero
    m['impulse_rate'] = round(m['impulse_triggered'] / total, 4)
    m['silence_rate'] = round(m['silence_chosen'] / max(m['impulse_triggered'], 1), 4)
    ws_total = m['ws_push_ok'] + m['ws_push_fail'] or 1
    m['ws_success_rate'] = round(m['ws_push_ok'] / ws_total, 4)
    return m


# ── Serve React SPA ──
_base_dir = os.path.dirname(os.path.abspath(__file__))
_static_dir = os.path.join(_base_dir, "static")
_assets_dir = os.path.join(_static_dir, "assets")

if os.path.isdir(_assets_dir):
    app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

@app.get("/", include_in_schema=False)
@app.get("/app", include_in_schema=False)
@app.get("/discover", include_in_schema=False)
@app.get("/chat/{path:path}", include_in_schema=False)
async def serve_spa(path: str = ""):
    """Serve React SPA — all frontend routes return index.html."""
    html_path = os.path.join(_static_dir, "index.html")
    if not os.path.exists(html_path):
        return HTMLResponse("<h1>Please run: cd web && npm run build</h1>", status_code=503)
    return HTMLResponse(open(html_path, encoding="utf-8").read())


# ──────────────────────────────────────────────────────────────
# Message Protocol
# ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """REST API chat request."""
    message: str
    persona_id: str  # required, no default
    session_id: Optional[str] = None
    user_name: Optional[str] = None
    client_id: Optional[str] = None  # display-layer identity for chat log


class PersonaInfo(BaseModel):
    """Persona info response."""
    persona_id: str
    name: str
    name_zh: Optional[str] = None
    age: Optional[int]
    gender: str
    mbti: Optional[str]
    tags: list[str]
    description: str
    avatar_url: Optional[str] = None


# ──────────────────────────────────────────────────────────────
# Session Management (with TTL + persistence)
# ──────────────────────────────────────────────────────────────

def _persist_agent(agent: ChatAgent) -> None:
    """Save agent state via CAS with bootstrap fallback."""
    if not state_store:
        return
    import json as _json
    agent_data = _json.dumps(agent.agent.to_dict(), ensure_ascii=False)
    metabolism_data = _json.dumps(agent.metabolism.to_dict(), ensure_ascii=False)

    ok = state_store.save_state(
        user_id=agent.user_id,
        persona_id=agent.persona.persona_id,
        agent_data=agent_data,
        metabolism_data=metabolism_data,
        last_active_at=agent._last_active,
        interaction_cadence=agent._interaction_cadence,
        expected_version=agent._state_version,
    )
    if ok:
        agent._state_version += 1
    else:
        # CAS miss: either stale version or row doesn't exist yet.
        # Check if row exists to distinguish bootstrap vs conflict.
        _, _, db_ver = state_store.load_proactive_meta(agent.user_id, agent.persona.persona_id)
        if db_ver == 0 and agent._state_version == 0:
            # Bootstrap: first write, no row exists. Use UPSERT (no CAS).
            state_store.save_state(
                user_id=agent.user_id,
                persona_id=agent.persona.persona_id,
                agent_data=agent_data,
                metabolism_data=metabolism_data,
                last_active_at=agent._last_active,
                interaction_cadence=agent._interaction_cadence,
                expected_version=None,  # UPSERT, no version check
            )
            # Read actual DB version after write (INSERT = 0, ON CONFLICT = n+1)
            _, _, actual_v = state_store.load_proactive_meta(agent.user_id, agent.persona.persona_id)
            agent._state_version = actual_v
        else:
            # True conflict: another writer updated. Sync version.
            agent._state_version = db_ver
            print(f"  [persist] CAS conflict {agent.user_id}/{agent.persona.persona_id}, synced v={db_ver}")


def _cleanup_expired_sessions() -> int:
    """Remove sessions that haven't been active for SESSION_TTL_SECONDS."""
    now = time.time()
    expired = []
    for sid, (agent, last_active) in active_sessions.items():
        if now - last_active > SESSION_TTL_SECONDS:
            _persist_agent(agent)
            # Flush EverMemOS memory (fire-and-forget from sync context)
            if evermemos and evermemos.available:
                asyncio.create_task(
                    evermemos.close_session(
                        user_id=agent.evermemos_uid,
                        persona_id=agent.persona.persona_id,
                        group_id=agent._group_id,
                    )
                )
            expired.append(sid)
    for sid in expired:
        del active_sessions[sid]
    return len(expired)


def get_or_create_session(
    session_id: Optional[str],
    persona_id: str,
    user_name: Optional[str] = None,
) -> tuple[str, ChatAgent]:
    """Get existing session or create a new one (with state hydration)."""
    now = time.time()

    # Return existing session
    if session_id and session_id in active_sessions:
        agent, _ = active_sessions[session_id]
        active_sessions[session_id] = (agent, now)
        return session_id, agent

    # Periodic cleanup
    _cleanup_expired_sessions()

    # Create new session
    sid = session_id or str(uuid.uuid4())[:8]
    persona = persona_loader.get(persona_id)
    if not persona:
        raise ValueError(f"角色 '{persona_id}' 不存在")

    # Use persona_id hash as seed for deterministic personality per persona
    genome_seed = hash(persona_id) % 100000

    # Use user_name as stable user_id for EverMemOS cross-session identity.
    # Fallback to session_id (sid) if no user_name provided.
    stable_user_id = user_name if user_name else sid

    agent = ChatAgent(
        persona=persona,
        llm=llm_client,
        user_id=stable_user_id,
        user_name=user_name,
        skills_prompt=skills_prompt or None,
        skill_engine=skill_engine,
        memory_store=memory_store,
        genome_seed=genome_seed,
        genome_data_dir=genome_data_dir,
        evermemos=evermemos,
    )

    # Hydrate from persisted state (if available)
    is_new_agent = True
    if state_store:
        saved_agent, saved_metabolism = state_store.load_session(stable_user_id, persona_id)
        if saved_agent:
            agent.agent = saved_agent
            is_new_agent = False
            print(f"  ↳ 恢复 Agent: age={saved_agent.age}, interactions={saved_agent.interaction_count}")
        if saved_metabolism:
            agent.metabolism = saved_metabolism
            print(f"  ↳ 恢复代谢: total_frustration={saved_metabolism.total():.2f}")
        # Bug 4: Load proactive meta (last_active, cadence, state_version)
        la, cad, sv = state_store.load_proactive_meta(stable_user_id, persona_id)
        if la > 0:
            agent._last_active = la
            agent._interaction_cadence = cad
            agent._state_version = sv
            print(f"  ↳ 恢复 proactive: last_active={la:.0f}, cadence={cad:.0f}s, v={sv}")

    # V10 Pre-warm: only for genuinely new agents (no saved state).
    # Must run AFTER state restore so we don't waste 60 steps on agents
    # that will immediately have their weights overwritten.
    if is_new_agent:
        agent.pre_warm()
        print(f"  ↳ 新 Agent 预热: 60步完成 (seed={genome_seed})")


    active_sessions[sid] = (agent, now)
    return sid, agent


def remove_session(session_id: str) -> None:
    """Persist and remove a session."""
    if session_id and session_id in active_sessions:
        agent, _ = active_sessions.pop(session_id)
        _persist_agent(agent)
        print(f"  ↳ 会话 {session_id} 已保存并清理")


# ──────────────────────────────────────────────────────────────
# REST API Endpoints
# ──────────────────────────────────────────────────────────────

@app.get("/api/status")
async def api_status():
    return {
        "name": "OpenHer",
        "version": "0.5.0",
        "engine": "Genome v10",
        "status": "running",
        "personas": persona_loader.list_ids() if persona_loader else [],
        "active_sessions": len(active_sessions),
    }


@app.get("/api/personas")
async def list_personas():
    personas = persona_loader.load_all()
    result = []
    avatar_svc = _get_avatar_service()
    for pid, p in personas.items():
        avatar_path = avatar_svc.repo.get_avatar_path(pid)
        result.append(PersonaInfo(
            persona_id=pid,
            name=p.name,
            name_zh=p.name_zh,
            age=p.age,
            gender=p.gender,
            mbti=p.mbti,
            tags=p.tags,
            description=(p.bio.get("zh") or p.bio.get("en") or p.personality or "")[:120],
            avatar_url=f"/api/avatar/{pid}" if avatar_path else None,
        ))
    return {"personas": [r.model_dump() for r in result]}


@app.post("/api/chat")
async def chat_api(req: ChatRequest):
    try:
        session_id, agent = get_or_create_session(
            req.session_id, req.persona_id, req.user_name
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    result = await agent.chat(req.message)
    status = agent.get_status()

    _persist_agent(agent)

    # Chat log: display-layer persistence (no engine impact)
    if chat_log_store and req.client_id:
        try:
            chat_log_store.save_turn(
                client_id=req.client_id,
                persona_id=req.persona_id,
                user_msg=req.message,
                agent_reply=result['reply'],
                modality=result.get('modality', '文字'),
            )
        except Exception as e:
            print(f"  [chat_log] save error: {e}")

    return {
        "session_id": session_id,
        "response": result['reply'],
        "modality": result['modality'],
        "image_url": f"/api/selfie/{os.path.basename(result['image_path'])}" if result.get('image_path') else None,
        **status,
    }


@app.get("/api/session/{session_id}/status")
async def session_status(session_id: str):
    entry = active_sessions.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")
    agent, _ = entry
    return agent.get_status()


@app.get("/api/chat/history/{persona_id}")
async def get_chat_history(
    persona_id: str,
    client_id: str = Query(..., description="Frontend client identity (localStorage UUID)"),
    limit: int = Query(50, ge=1, le=500),
    before_id: int = Query(None, description="Pagination cursor — return messages before this id"),
):
    """Load chat history for display. Does not affect engine state."""
    if not chat_log_store:
        return {"messages": [], "total": 0}
    messages = chat_log_store.load_messages(client_id, persona_id, limit, before_id)
    total = chat_log_store.count_messages(client_id, persona_id)
    return {"messages": messages, "total": total}


@app.get("/api/tts")
async def tts_api(
    text: str = Query(..., description="Text to synthesize"),
    voice: str = Query("sweet_female", description="Voice preset"),
    emotion: str = Query("", description="Emotion instruction"),
):
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    result = await tts_engine.synthesize(
        text=text,
        voice_preset=voice,
        emotion_instruction=emotion or None,
    )

    if result.success and result.audio_path:
        return FileResponse(
            result.audio_path,
            media_type="audio/mpeg",
            filename="speech.mp3",
        )
    else:
        raise HTTPException(status_code=500, detail=result.error or "TTS failed")


# ──────────────────────────────────────────────────────────────
# Image Generation API
# ──────────────────────────────────────────────────────────────

@app.post("/api/image")
async def image_api(
    prompt: str = Query(..., description="Text prompt for image generation"),
    aspect_ratio: str = Query("", description="Aspect ratio (e.g. 16:9, 1:1)"),
    image_size: str = Query("1K", description="Image size (1K, 2K)"),
):
    """Generate an image from a text prompt."""
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    from providers.registry import get_image_gen

    try:
        provider = get_image_gen(
            cache_dir=os.path.join(
                os.path.dirname(os.path.abspath(__file__)), ".cache", "image"
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    result = await provider.generate(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
    )

    if result.success and result.image_path:
        # Determine media type
        media_type = result.mime_type or "image/png"
        ext = os.path.splitext(result.image_path)[1] or ".png"
        return FileResponse(
            result.image_path,
            media_type=media_type,
            filename=f"generated{ext}",
        )
    else:
        raise HTTPException(status_code=500, detail=result.error or "Image generation failed")


@app.get("/api/selfie/{filename:path}")
async def serve_selfie(filename: str):
    """Serve a generated selfie image from the cache."""
    selfie_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "selfie")
    file_path = os.path.join(selfie_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Image not found")
    media_type = "image/png"
    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        media_type = "image/jpeg"
    elif ext == ".webp":
        media_type = "image/webp"
    return FileResponse(file_path, media_type=media_type)


# ──────────────────────────────────────────────────────────────
# Avatar API (后台管理 + 前端获取)
# ──────────────────────────────────────────────────────────────


def _get_avatar_service():
    """Lazy-create AvatarService."""
    from persona.avatar.service import AvatarService
    return AvatarService(
        personas_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "persona", "personas"),
        persona_loader=persona_loader,
    )


@app.post("/api/admin/avatar/all")
async def generate_all_avatars(force: bool = Query(False)):
    """[Admin] Generate avatars for all personas."""
    service = _get_avatar_service()
    results = await service.generate_all(force=force)

    summary = []
    for pid, r in results.items():
        summary.append({
            "persona_id": pid,
            "success": r.success,
            "error": r.error,
        })

    ok = sum(1 for r in results.values() if r.success)
    return {"total": len(results), "success": ok, "details": summary}


@app.post("/api/admin/avatar/{persona_id}")
async def generate_avatar(persona_id: str, force: bool = Query(False)):
    """[Admin] Generate avatar for a single persona."""
    service = _get_avatar_service()
    try:
        result = await service.generate(persona_id, force=force)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if result.success:
        return {
            "persona_id": persona_id,
            "avatar_path": result.image_path,
            "provider": result.provider,
            "latency_ms": round(result.latency_ms, 1),
        }
    else:
        raise HTTPException(status_code=500, detail=result.error or "Avatar generation failed")


@app.get("/api/admin/avatar/{persona_id}/config")
async def get_avatar_config(persona_id: str):
    """[Admin] Get current avatar config for a persona."""
    service = _get_avatar_service()
    try:
        status = service.get_config(persona_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "persona_id": status.persona_id,
        "persona_name": status.persona_name,
        "prompt_base": status.config.prompt_base,
        "style": status.config.style,
        "negative_prompt": status.config.negative_prompt,
        "has_avatar": status.has_avatar,
    }


@app.put("/api/admin/avatar/{persona_id}/config")
async def update_avatar_config(persona_id: str, request: dict = Body(...)):
    """[Admin] Update avatar config → write back to PERSONA.md."""
    service = _get_avatar_service()
    try:
        updated = service.update_config(
            persona_id,
            prompt_base=request.get("prompt_base"),
            style=request.get("style"),
            negative_prompt=request.get("negative_prompt"),
        )
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "persona_id": persona_id,
        "prompt_base": updated.prompt_base,
        "style": updated.style,
        "negative_prompt": updated.negative_prompt,
    }


@app.delete("/api/admin/avatar/{persona_id}")
async def delete_avatar(persona_id: str):
    """[Admin] Delete avatar for a persona."""
    service = _get_avatar_service()
    deleted = service.delete(persona_id)
    return {"persona_id": persona_id, "deleted": deleted}


@app.get("/api/avatar/{persona_id}")
async def get_avatar(persona_id: str):
    """Get avatar image for a persona."""
    service = _get_avatar_service()
    path = service.repo.get_avatar_path(persona_id)
    if path:
        return FileResponse(path, media_type="image/png", filename=f"{persona_id}_avatar.png")
    raise HTTPException(status_code=404, detail="Avatar not found. Use POST /api/admin/avatar/{id} to generate.")


# ──────────────────────────────────────────────────────────────
# WebSocket Endpoint — Real-time chat with Genome v10
# ──────────────────────────────────────────────────────────────

@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    """
    WebSocket endpoint for real-time persona chat with Genome v10.

    Protocol:
      Client → Server: {"type": "chat", "content": "hello", "persona_id": "vivian"}
      Server → Client: {"type": "chat_start", "session_id": "abc123"}
      Server → Client: {"type": "chat_chunk", "content": "嘿～"}  (streamed)
      Server → Client: {"type": "chat_end", "dominant_drive": "🔗 联结", ...}
    """
    await ws.accept()
    session_id = None
    agent = None

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "content": "Invalid JSON"})
                continue

            msg_type = msg.get("type", "")

            # ── Chat message ──
            if msg_type == "chat":
                text = msg.get("content", "").strip()
                if not text:
                    continue

                persona_id = msg.get("persona_id", "")
                if not persona_id:
                    await ws.send_json({"type": "error", "content": "persona_id is required"})
                    continue
                user_name = msg.get("user_name")
                ws_client_id = msg.get("client_id")  # display-layer identity

                try:
                    session_id, agent = get_or_create_session(
                        session_id or msg.get("session_id"),
                        persona_id,
                        user_name,
                    )
                except ValueError as e:
                    await ws.send_json({"type": "error", "content": str(e)})
                    continue

                # Display-only greeting: store in chat_log for frontend history reload,
                # but do NOT inject into agent.history (preserves emergence purity).
                # Greeting in history[-4:] would seed Express positive-feedback drift from turn 0.
                greeting = msg.get("greeting")
                if greeting and agent and len(agent.history) == 0:
                    print(f"  [greeting] display-only (not in model state): {greeting[:40]}")
                    # Persist to display-layer chat log
                    if chat_log_store and ws_client_id:
                        try:
                            chat_log_store._conn.execute(
                                "INSERT INTO chat_messages (client_id, persona_id, role, content, modality, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                                (ws_client_id, persona_id, "assistant", greeting, "文字", time.time()),
                            )
                            chat_log_store._conn.commit()
                        except Exception as e:
                            print(f"  [greeting] chat_log save error: {e}")

                # Register WS connection for proactive push (Bug 1)
                _ws_connections[session_id] = ws

                await ws.send_json({
                    "type": "chat_start",
                    "session_id": session_id,
                })

                stream_error = False
                _clean_reply_text = ""
                try:
                    async def _ws_send(msg: dict):
                        await ws.send_json(msg)

                    async def _on_complete(reply: str, modality: str):
                        nonlocal _clean_reply_text
                        _clean_reply_text = reply

                    await _stream_to_ws(
                        agent.chat_stream(text),
                        _ws_send,
                        on_reply_complete=_on_complete,
                    )
                except Exception as e:
                    stream_error = True
                    print(f"[ws] stream 错误: {e}")
                    try:
                        await ws.send_json({
                            "type": "error",
                            "content": f"LLM 响应异常: {type(e).__name__}: {str(e)[:200]}",
                        })
                    except Exception:
                        break

                if not stream_error:
                    status = agent.get_status()
                    await ws.send_json({
                        "type": "chat_end",
                        "reply": _clean_reply_text,   # clean full reply for frontend
                        "modality": status.get("modality", ""),
                        **status,
                    })
                    # Log conversation for debugging
                    print(f"  [chat] 👤 {text}")
                    print(f"  [chat] 🤖 {_clean_reply_text[:120]}")

                _persist_agent(agent)

                # Chat log: display-layer persistence (no engine impact)
                if chat_log_store and ws_client_id and not stream_error:
                    try:
                        chat_log_store.save_turn(
                            client_id=ws_client_id,
                            persona_id=persona_id,
                            user_msg=text,
                            agent_reply=_clean_reply_text,
                            modality=status.get("modality", "文字") if not stream_error else "文字",
                        )
                    except Exception as e:
                        print(f"  [chat_log] save error: {e}")

            # ── TTS request ──
            elif msg_type == "tts_request":
                text = msg.get("content", "")
                if text and agent:
                    try:
                        voice_preset = agent.persona.voice.voice_preset or "sweet_female"
                        result = await tts_engine.synthesize(
                            text=text,
                            voice_preset=voice_preset,
                        )
                        if result.success and result.audio_path:
                            with open(result.audio_path, "rb") as f:
                                audio_b64 = base64.b64encode(f.read()).decode()
                            await ws.send_json({
                                "type": "tts_audio",
                                "audio": audio_b64,
                                "format": "mp3",
                            })
                        else:
                            await ws.send_json({
                                "type": "error",
                                "content": f"TTS 失败: {result.error}",
                            })
                    except Exception as e:
                        await ws.send_json({
                            "type": "error",
                            "content": f"TTS 异常: {str(e)[:200]}",
                        })

            # ── Status request ──
            elif msg_type == "status":
                if agent:
                    await ws.send_json({
                        "type": "status",
                        **agent.get_status(),
                    })

            # ── Switch persona ──
            elif msg_type == "switch_persona":
                new_persona_id = msg.get("persona_id", "")
                if new_persona_id:
                    # Clean up old session to prevent leak
                    old_session_id = session_id
                    if old_session_id:
                        if old_session_id in _ws_connections:
                            del _ws_connections[old_session_id]
                        remove_session(old_session_id)
                    try:
                        session_id, agent = get_or_create_session(
                            None,
                            new_persona_id,
                            msg.get("user_name"),
                        )
                        _ws_connections[session_id] = ws
                        await ws.send_json({
                            "type": "persona_switched",
                            "session_id": session_id,
                            "persona": agent.persona.name,
                        })
                    except ValueError as e:
                        await ws.send_json({"type": "error", "content": str(e)})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[ws] 未预期异常: {type(e).__name__}: {e}")
        try:
            await ws.send_json({"type": "error", "content": f"服务端异常: {str(e)[:200]}"})
        except Exception:
            pass
    finally:
        # Deregister WS connection
        if session_id and session_id in _ws_connections:
            del _ws_connections[session_id]
        if session_id:
            remove_session(session_id)
        print(f"[ws] 连接关闭: session={session_id}")
