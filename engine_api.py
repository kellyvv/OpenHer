"""
Engine API — FastAPI gateway for the Persona Engine microservice.

Thin routing layer: all business logic delegated to SessionManager and PersonaFactory.
This file defines Pydantic models, route handlers, and lifespan management.

Endpoints (11):
  POST   /api/chat              — Synchronous dialogue
  POST   /api/chat/stream       — SSE streaming dialogue
  GET    /api/session/{id}/events — SSE proactive event stream
  POST   /api/session           — Create/resume session
  GET    /api/session/{id}/status — Engine state snapshot
  GET    /api/session/{id}/fingerprint — Persona consistency fingerprint
  DELETE /api/session/{id}      — Persist and clean up
  GET    /api/personas          — List all personas
  GET    /api/persona/{id}      — Persona details
  POST   /api/persona           — Create persona (Level 1)
  DELETE /api/persona/{id}      — Delete persona
  GET    /api/engine/health     — Health check + metrics
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from engine.session_manager import SessionManager
from engine.persona_factory import PersonaFactory
from persona.loader import PersonaLoader
from providers.llm.client import LLMClient
from providers.api_config import get_llm_config
from engine.state_store import StateStore
from memory.memory_store import MemoryStore


# ── Pydantic Request/Response Models ──

class MemoryContext(BaseModel):
    """External memory injection (EverMemOS / Qdrant / RAG results)."""
    profile: str = ""
    narrative: str = ""
    relevant: List[str] = []


class ChatRequest(BaseModel):
    persona_id: str
    session_id: Optional[str] = None
    user_id: str = "default_user"
    user_name: Optional[str] = None
    message: str
    memory_context: Optional[MemoryContext] = None


class SessionCreateRequest(BaseModel):
    persona_id: str
    user_id: str = "default_user"
    user_name: Optional[str] = None
    session_id: Optional[str] = None


class PersonaCreateRequest(BaseModel):
    persona_id: Optional[str] = None  # auto-derived from name if not given
    name: str
    name_zh: str = ""
    age: int = 25
    gender: str = "female"
    mbti: str = "INFJ"
    bio: str = ""


# ── Global Services (initialized in lifespan) ──

session_manager: Optional[SessionManager] = None
persona_factory: Optional[PersonaFactory] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize services on startup, persist on shutdown."""
    global session_manager, persona_factory

    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, ".data")
    genome_data_dir = os.path.join(data_dir, "genome")
    os.makedirs(genome_data_dir, exist_ok=True)

    # Initialize LLM client
    llm_cfg = get_llm_config()
    llm = LLMClient(
        provider=llm_cfg["provider"],
        model=llm_cfg["model"],
        api_key=llm_cfg.get("api_key"),
        base_url=llm_cfg.get("base_url"),
        temperature=llm_cfg.get("temperature", 0.92),
        max_tokens=llm_cfg.get("max_tokens", 1024),
    )

    # Initialize stores
    state_store = StateStore(os.path.join(data_dir, "openher.db"))
    memory_store = MemoryStore(os.path.join(data_dir, "soul_memory.db"))

    # Initialize persona loader & load all personas
    persona_loader = PersonaLoader(os.path.join(base_dir, "persona", "personas"))
    personas = persona_loader.load_all()
    print(f"✓ Loaded {len(personas)} personas: {', '.join(personas.keys())}")

    # Initialize managers
    session_manager = SessionManager(
        llm=llm,
        state_store=state_store,
        memory_store=memory_store,
        persona_loader=persona_loader,
        genome_data_dir=genome_data_dir,
        tick_interval=int(os.getenv("ENGINE_TICK_INTERVAL", "300")),
        pool_max=int(os.getenv("ENGINE_SESSION_POOL_MAX", "100")),
    )
    persona_factory = PersonaFactory(
        llm=llm,
        persona_loader=persona_loader,
        genome_data_dir=genome_data_dir,
        state_store=state_store,
        memory_store=memory_store,
    )

    await session_manager.start()
    print("=" * 60)
    print("  ✅ Persona Engine API ready on port 8800")
    print("=" * 60)

    yield

    await session_manager.shutdown()


app = FastAPI(
    title="Persona Engine",
    description="OpenHer Core Persona Engine as a Service",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════
# 1. Dialogue API
# ══════════════════════════════════════════════════

@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Synchronous dialogue — full Genome lifecycle.

    Returns reply, monologue, and engine_state.
    """
    sid = req.session_id or str(uuid.uuid4())

    agent = await session_manager.get_or_create(
        sid, req.persona_id, req.user_id, req.user_name,
    )

    # Call ChatAgent.chat() — signature: chat(user_message, on_feel_done=None)
    result = await agent.chat(req.message)

    # Build enriched response
    # chat() returns {reply, modality}; monologue is in _last_action
    monologue = ""
    if agent._last_action:
        monologue = agent._last_action.get("monologue", "")

    # Persist state after chat
    try:
        await session_manager.checkpoint(sid)
    except Exception as e:
        print(f"  ⚠ checkpoint failed for {sid}: {e}")

    return {
        "session_id": sid,
        "reply": result.get("reply", ""),
        "modality": result.get("modality", ""),
        "monologue": monologue,
        "engine_state": agent.get_status(),
    }


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    SSE streaming dialogue.

    Streams tokens from Express pass, then sends final done event with full state.
    """
    sid = req.session_id or str(uuid.uuid4())

    agent = await session_manager.get_or_create(
        sid, req.persona_id, req.user_id, req.user_name,
    )

    async def generator():
        # chat_stream() yields string chunks
        full_reply = ""
        async for chunk in agent.chat_stream(req.message):
            full_reply += chunk
            yield {
                "event": "token",
                "data": json.dumps({"token": chunk}, ensure_ascii=False),
            }

        # After streaming completes, send monologue and engine_state
        monologue = ""
        if agent._last_action:
            monologue = agent._last_action.get("monologue", "")

        try:
            await session_manager.checkpoint(sid)
        except Exception as e:
            print(f"  ⚠ checkpoint failed for {sid}: {e}")

        yield {
            "event": "done",
            "data": json.dumps({
                "reply": full_reply,
                "modality": agent._last_modality or "",
                "monologue": monologue,
                "engine_state": agent.get_status(),
            }, ensure_ascii=False),
        }

    return EventSourceResponse(generator())


# ══════════════════════════════════════════════════
# 2. Proactive Event Stream
# ══════════════════════════════════════════════════

@app.get("/api/session/{session_id}/events")
async def event_stream(session_id: str):
    """
    SSE persistent connection for proactive messages.

    Client keeps this connection open. Engine pushes:
    - event: proactive — drive-triggered autonomous messages
    - event: heartbeat — keep-alive every 30s
    """
    queue = session_manager.get_queue(session_id)
    if not queue:
        raise HTTPException(404, detail="Session not found")

    async def generator():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield {
                    "event": "proactive",
                    "data": json.dumps(event, ensure_ascii=False),
                }
            except asyncio.TimeoutError:
                yield {
                    "event": "heartbeat",
                    "data": json.dumps({"ts": int(time.time())}),
                }

    return EventSourceResponse(generator())


# ══════════════════════════════════════════════════
# 3. Session Management
# ══════════════════════════════════════════════════

@app.post("/api/session")
async def create_session(req: SessionCreateRequest):
    """Create or resume a session."""
    sid = req.session_id or str(uuid.uuid4())

    agent = await session_manager.get_or_create(
        sid, req.persona_id, req.user_id, req.user_name,
    )

    return {
        "session_id": sid,
        "is_new": agent.agent.age == 0,
        "engine_state": agent.get_status(),
    }


@app.get("/api/session/{session_id}/status")
async def session_status(session_id: str):
    """Engine state snapshot (no computation triggered)."""
    agent = session_manager.get(session_id)
    if not agent:
        raise HTTPException(404, detail="Session not found")
    return {
        "session_id": session_id,
        "engine_state": agent.get_status(),
    }


@app.get("/api/session/{session_id}/fingerprint")
async def session_fingerprint(session_id: str):
    """
    Persona consistency fingerprint.

    Based on last 30 turns of signal history:
    - traits: high/neutral/low classification for each signal
    - contradictions: high-value signal pairs (warmth+defiance, vulnerability+directness)
    """
    agent = session_manager.get(session_id)
    if not agent:
        raise HTTPException(404, detail="Session not found")

    # Extract signal history from style_memory._pool (crystallized memories)
    pool = getattr(agent.style_memory, '_pool', [])
    signals_log = [m.get('signals', {}) for m in pool if m.get('signals')]
    if len(signals_log) < 5:
        return {
            "error": "Need at least 5 conversation turns for fingerprint",
            "turn_count": len(signals_log),
        }

    recent = signals_log[-30:]

    # Compute averages across all 8 signal dimensions
    signal_keys = list(recent[0].keys()) if recent else []
    avg = {}
    for key in signal_keys:
        vals = [s.get(key, 0) for s in recent if isinstance(s.get(key), (int, float))]
        avg[key] = round(sum(vals) / max(len(vals), 1), 3)

    # Classify traits: >0.6 high, <0.35 low, else neutral
    traits = {}
    for k, v in avg.items():
        if v > 0.6:
            traits[k] = "high"
        elif v < 0.35:
            traits[k] = "low"
        else:
            traits[k] = "neutral"

    # Detect contradictions: high-value pairs that shouldn't coexist
    contradictions = []
    contradiction_pairs = [
        ("warmth", "defiance"),
        ("vulnerability", "directness"),
    ]
    for a, b in contradiction_pairs:
        if avg.get(a, 0) > 0.5 and avg.get(b, 0) > 0.5:
            contradictions.append([a, b])

    return {
        "traits": traits,
        "avg_signals": avg,
        "contradictions": contradictions,
        "turn_count": len(recent),
    }


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """Persist session state and remove from pool."""
    try:
        await session_manager.checkpoint(session_id)
    except Exception as e:
        print(f"  ⚠ checkpoint failed for {session_id}: {e}")
    session_manager.remove(session_id)
    return {"status": "ok", "session_id": session_id}


# ══════════════════════════════════════════════════
# 4. Persona Management
# ══════════════════════════════════════════════════

@app.get("/api/personas")
async def list_personas():
    """List all available personas with readiness status."""
    loader = session_manager.persona_loader
    result = []
    for pid in loader.list_ids():
        p = loader.get(pid)
        if not p:
            continue
        genesis_path = os.path.join(
            session_manager.genome_data_dir, f"genesis_{pid}.json"
        )
        result.append({
            "persona_id": pid,
            "name": p.name,
            "mbti": getattr(p, 'mbti', '') or '',
            "tags": getattr(p, 'tags', []) or [],
            "bio": getattr(p, 'bio', '') or '',
            "is_ready": os.path.exists(genesis_path),
        })
    return result


@app.get("/api/persona/{persona_id}")
async def get_persona(persona_id: str):
    """Get persona details."""
    persona = session_manager.persona_loader.get(persona_id)
    if not persona:
        raise HTTPException(404, detail=f"Persona not found: {persona_id}")

    return {
        "persona_id": persona_id,
        "name": persona.name,
        "name_zh": getattr(persona, 'name_zh', None),
        "age": getattr(persona, 'age', None),
        "gender": getattr(persona, 'gender', 'female'),
        "mbti": getattr(persona, 'mbti', ''),
        "tags": getattr(persona, 'tags', []) or [],
        "bio": getattr(persona, 'bio', '') or '',
    }


@app.post("/api/persona")
async def create_persona(req: PersonaCreateRequest):
    """Create a new persona (Level 1: 6 basic params → fully automated via SKILL)."""
    # Auto-derive persona_id from name if not given
    pid = req.persona_id or req.name.lower().replace(" ", "_")
    req_dict = req.model_dump()
    req_dict["persona_id"] = pid

    # Check if persona already exists
    existing = session_manager.persona_loader.get(pid)
    if existing:
        raise HTTPException(409, detail=f"Persona already exists: {pid}")

    result = await persona_factory.create_from_params(req_dict)
    return result


@app.post("/api/persona/{persona_id}/upload")
async def create_persona_from_file(
    persona_id: str,
    file: UploadFile = File(...),
):
    """Create a new persona (Level 2: upload SOUL.md)."""
    existing = session_manager.persona_loader.get(persona_id)
    if existing:
        raise HTTPException(409, detail=f"Persona already exists: {persona_id}")

    content = await file.read()
    persona_md = content.decode("utf-8")
    result = await persona_factory.create_from_file(persona_id, persona_md)
    return result


@app.delete("/api/persona/{persona_id}")
async def delete_persona(persona_id: str):
    """Delete a persona and all related data."""
    persona = session_manager.persona_loader.get(persona_id)
    if not persona:
        raise HTTPException(404, detail=f"Persona not found: {persona_id}")

    persona_factory.delete_persona(persona_id)
    # Clear from loader cache so it can be re-created
    session_manager.persona_loader._cache.pop(persona_id, None)
    return {"status": "ok", "persona_id": persona_id}


# ══════════════════════════════════════════════════
# 5. Diagnostics
# ══════════════════════════════════════════════════

@app.get("/api/engine/health")
async def health():
    """
    Deep health check with proactive metrics.

    Verifies LLM connectivity, SQLite writability, and reports
    proactive tick statistics.
    """
    # LLM connectivity check
    llm_ok = True
    try:
        from providers.llm.client import ChatMessage
        resp = await session_manager.llm.chat([
            ChatMessage(role="user", content="ping"),
        ], max_tokens=5)
        llm_ok = bool(resp and resp.content)
    except Exception:
        llm_ok = False

    # SQLite write check
    sqlite_ok = True
    try:
        session_manager.state_store._conn.execute("SELECT 1").fetchone()
    except Exception:
        sqlite_ok = False

    return {
        "status": "ok" if (llm_ok and sqlite_ok) else "degraded",
        "llm_reachable": llm_ok,
        "sqlite_writable": sqlite_ok,
        "personas_loaded": len(session_manager.persona_loader.list_ids()),
        "active_sessions": len(session_manager._pool),
        "proactive_metrics": session_manager.metrics,
    }
