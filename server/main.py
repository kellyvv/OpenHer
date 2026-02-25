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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.persona import PersonaLoader
from core.llm import LLMClient
from core.agent.chat_agent import ChatAgent
from core.media.tts_engine import TTSEngine, TTSProvider
from core.skills import SkillEngine
from core.state_store import StateStore
from core.memory.memory_store import MemoryStore
from core.memory.evermemos_client import EverMemOSClient
from core.cron_scheduler import CronScheduler
from core.genome import DRIVE_LABELS

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
memory_store: MemoryStore = None
evermemos: EverMemOSClient = None
cron_scheduler: CronScheduler = None
genome_data_dir: str = ""

# Active chat sessions: session_id → (ChatAgent, last_active_time)
active_sessions: dict[str, tuple[ChatAgent, float]] = {}

# Session TTL: auto-clean sessions older than 30 minutes
SESSION_TTL_SECONDS = 30 * 60


@app.on_event("startup")
async def startup():
    """Initialize all services on server start."""
    global persona_loader, llm_client, tts_engine, skill_engine, skills_prompt
    global state_store, memory_store, evermemos, cron_scheduler, genome_data_dir

    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Load personas
    persona_loader = PersonaLoader(os.path.join(base_dir, "personas"))
    personas = persona_loader.load_all()
    print(f"✓ 加载了 {len(personas)} 个角色: {list(personas.keys())}")

    # 2. Create LLM client
    provider = os.getenv("DEFAULT_PROVIDER", "dashscope")
    model = os.getenv("DEFAULT_MODEL", "qwen-max")
    llm_client = LLMClient(provider=provider, model=model)

    # 3. Create TTS engine
    tts_engine = TTSEngine(
        provider=TTSProvider.EDGE,
        cache_dir=os.path.join(base_dir, ".cache", "tts"),
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

    # 7. Memory store
    memory_store = MemoryStore(os.path.join(data_dir, "memory.db"))

    # 7b. EverMemOS long-term memory (cloud API)
    evermemos_key = os.getenv("EVERMEMOS_API_KEY", "")
    if evermemos_key:
        evermemos = EverMemOSClient(api_key=evermemos_key)
    else:
        evermemos = None
        print("ℹ EverMemOS: 未配置 EVERMEMOS_API_KEY，使用本地 MemoryStore")

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

    print("✓ OpenHer 服务启动完成 (v0.5.0 — Genome v10 Hybrid Engine)")
    print("  → 演示页面: http://localhost:8800/app")


@app.on_event("shutdown")
async def shutdown():
    """Save all active sessions and close DBs."""
    if cron_scheduler:
        cron_scheduler.stop()
    if state_store:
        for sid, (agent, _) in active_sessions.items():
            _persist_agent(agent)
        state_store.close()
    if memory_store:
        memory_store.close()
    print("✓ 状态已保存，服务关闭")


# ──────────────────────────────────────────────────────────────
# Cron message generation + delivery
# ──────────────────────────────────────────────────────────────

async def _cron_generate_message(skill_prompt: str, persona_id: str) -> str:
    """Generate a proactive cron message using an isolated ChatAgent."""
    persona = persona_loader.get(persona_id)
    if not persona:
        return ""
    from core.llm.client import ChatMessage
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


@app.get("/app")
async def demo_app():
    """Serve the demo web client."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, "static", "index.html")
    return HTMLResponse(open(html_path, encoding="utf-8").read())


# ──────────────────────────────────────────────────────────────
# Message Protocol
# ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """REST API chat request."""
    message: str
    persona_id: str = "xiaoyun"
    session_id: Optional[str] = None
    user_name: Optional[str] = None


class PersonaInfo(BaseModel):
    """Persona info response."""
    persona_id: str
    name: str
    age: Optional[int]
    gender: str
    mbti: Optional[str]
    tags: list[str]
    description: str


# ──────────────────────────────────────────────────────────────
# Session Management (with TTL + persistence)
# ──────────────────────────────────────────────────────────────

def _persist_agent(agent: ChatAgent) -> None:
    """Save agent's Genome v8 state (neural weights + metabolism)."""
    if state_store:
        state_store.save_session(
            user_id=agent.user_id,
            persona_id=agent.persona.persona_id,
            agent=agent.agent,
            metabolism=agent.metabolism,
        )


def _cleanup_expired_sessions() -> int:
    """Remove sessions that haven't been active for SESSION_TTL_SECONDS."""
    now = time.time()
    expired = []
    for sid, (agent, last_active) in active_sessions.items():
        if now - last_active > SESSION_TTL_SECONDS:
            _persist_agent(agent)
            expired.append(sid)
    for sid in expired:
        del active_sessions[sid]
    return len(expired)


def get_or_create_session(
    session_id: Optional[str],
    persona_id: str = "xiaoyun",
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

    agent = ChatAgent(
        persona=persona,
        llm=llm_client,
        user_id=sid,
        user_name=user_name,
        skills_prompt=skills_prompt or None,
        memory_store=memory_store,
        evermemos=evermemos,
        genome_seed=genome_seed,
        genome_data_dir=genome_data_dir,
    )

    # Hydrate from persisted state (if available)
    if state_store:
        saved_agent, saved_metabolism = state_store.load_session(sid, persona_id)
        if saved_agent:
            agent.agent = saved_agent
            print(f"  ↳ 恢复 Agent: age={saved_agent.age}, interactions={saved_agent.interaction_count}")
        if saved_metabolism:
            agent.metabolism = saved_metabolism
            print(f"  ↳ 恢复代谢: total_frustration={saved_metabolism.total():.2f}")

    active_sessions[sid] = (agent, now)
    return sid, agent


def remove_session(session_id: str) -> None:
    """Persist and remove a session."""
    if session_id and session_id in active_sessions:
        agent, _ = active_sessions.pop(session_id)
        _persist_agent(agent)
        # Flush EverMemOS to trigger memory extraction
        if evermemos and evermemos.available:
            evermemos.flush(
                user_id=agent.evermemos_uid,
                persona_id=agent.persona.persona_id,
            )
            print(f"  ↳ EverMemOS flush: {agent.evermemos_uid}")
        print(f"  ↳ 会话 {session_id} 已保存并清理")


# ──────────────────────────────────────────────────────────────
# REST API Endpoints
# ──────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "name": "OpenHer",
        "version": "0.4.0",
        "engine": "Genome v8",
        "status": "running",
        "personas": persona_loader.list_ids() if persona_loader else [],
        "active_sessions": len(active_sessions),
    }


@app.get("/api/personas")
async def list_personas():
    personas = persona_loader.load_all()
    result = []
    for pid, p in personas.items():
        result.append(PersonaInfo(
            persona_id=pid,
            name=p.name,
            age=p.age,
            gender=p.gender,
            mbti=p.mbti,
            tags=p.tags,
            description=p.personality[:100] + "..." if p.personality else "",
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

    return {
        "session_id": session_id,
        "response": result['reply'],
        "modality": result['modality'],
        **status,
    }


@app.get("/api/session/{session_id}/status")
async def session_status(session_id: str):
    entry = active_sessions.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")
    agent, _ = entry
    return agent.get_status()


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
# WebSocket Endpoint — Real-time chat with Genome v8
# ──────────────────────────────────────────────────────────────

@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    """
    WebSocket endpoint for real-time persona chat with Genome v8.

    Protocol:
      Client → Server: {"type": "chat", "content": "hello", "persona_id": "xiaoyun"}
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

                persona_id = msg.get("persona_id", "xiaoyun")
                user_name = msg.get("user_name")

                try:
                    session_id, agent = get_or_create_session(
                        session_id or msg.get("session_id"),
                        persona_id,
                        user_name,
                    )
                except ValueError as e:
                    await ws.send_json({"type": "error", "content": str(e)})
                    continue

                await ws.send_json({
                    "type": "chat_start",
                    "session_id": session_id,
                })

                stream_error = False
                try:
                    async for chunk in agent.chat_stream(text):
                        await ws.send_json({
                            "type": "chat_chunk",
                            "content": chunk,
                        })
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
                        "modality": status.get("modality", ""),
                        **status,
                    })

                _persist_agent(agent)

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
                    if agent and session_id:
                        _persist_agent(agent)
                    try:
                        session_id, agent = get_or_create_session(
                            None,
                            new_persona_id,
                            msg.get("user_name"),
                        )
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
        if session_id:
            remove_session(session_id)
        print(f"[ws] 连接关闭: session={session_id}")
