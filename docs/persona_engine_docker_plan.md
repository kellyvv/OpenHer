# OpenHer 人格核心引擎 Docker 化方案（完整实现细节）

> 人格引擎作为独立微服务对外输出。引擎代码冻结，通过纯 HTTP API 提供能力。

---

## 一、服务定位与边界

**Persona Engine as a Service**

调用方只需关心：给哪个角色发了什么消息、收到了什么回复、引擎现在处于什么情绪状态。完全不感知 NN 权重、驱力代谢、Hebbian 学习。

引擎的所有自主行为（状态演化、主动触达）在容器内部完成，结果通过 SSE 推给调用方。

### 排除列表（不进容器）

| 组件 | 原因 |
|------|------|
| `providers/media/tts_engine.py` | 语音合成属于应用层输出，调用方决定用什么 TTS |
| `agent/skills/` | 技能系统是应用层扩展，不是引擎核心 |
| `cron_scheduler.py` | APScheduler + 技能调度，和 proactive tick 无关 |
| `providers/memory/evermemos/` | 外部记忆服务，引擎通过 `memory_context` 接口接收注入 |
| `static/` 前端文件 | 前端属于调用方 |
| `output_router.py` | WebSocket 流式输出路由，容器改用 SSE |

### 代码前提（零重构）

`ChatAgent.__init__` 的签名是：
```python
def __init__(self, persona, llm, user_id, user_name=None,
             task_skill_engine=None, modality_skill_engine=None,
             skills_prompt=None, skill_engine=None,
             memory_store=None, genome_seed=42, genome_data_dir=None,
             max_history=40, evermemos=None, task_log_store=None)
```
Skills / EverMemOS / TTS 全部是 `=None` 默认值，直接不传即可。

---

## 二、架构全图

```
┌─────────────────────────── Engine Container ───────────────────────────────┐
│                                                                              │
│  engine_api.py                  ← FastAPI 网关（新建）                      │
│  engine/session_manager.py      ← 会话池 + proactive sweep（新建）          │
│  engine/persona_factory.py      ← MBTI→参数推算 + 预热（新建）              │
│                                                                              │
│  ┌─── asyncio background task（SessionManager._heartbeat_loop）──────┐     │
│  │  每 300s → _sweep()                                                 │     │
│  │    → agent.proactive_tick()  (chat_agent.py:1316, 零改动)           │     │
│  │    → state_store.outbox_insert()  (state_store.py:270, 零改动)      │     │
│  │    → _queues[sid].put(result)  → SSE 推出                           │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│  agent/chat_agent.py            ← 12步生命周期（不改）                      │
│  engine/genome/genome_engine.py ← Agent NN（不改）                          │
│  engine/genome/drive_metabolism.py ← 驱力代谢（不改）                       │
│  engine/genome/critic.py        ← Critic 感知（不改）                       │
│  engine/genome/style_memory.py  ← KNN 结晶记忆（不改）                      │
│  engine/genome/calibrate_genesis.py ← genesis 校准工具（不改，仅复用）      │
│  engine/prompts/                ← Feel/Express prompt 模板（不改）           │
│  engine/prompt_registry.py      ← 模板加载（不改）                          │
│  engine/state_store.py          ← SQLite 持久化 + outbox（不改）            │
│  persona/loader.py              ← PERSONA.md 解析器（不改）                 │
│  providers/llm/client.py        ← LLM 客户端抽象（不改）                    │
│  providers/api_config.py        ← api.yaml 解析（不改）                     │
│  memory/memory_store.py         ← SoulMem（不改）                           │
│                                                                              │
│  .data/          ← Volume：SQLite（核心资产，见第六节）                      │
│  persona/personas/ ← Volume：角色定义（支持热更新）                         │
│  providers/api.yaml ← Volume：LLM 配置（只读）                              │
└──────────────────────────────────────────────────────────────────────────────┘
         ↕ HTTP / SSE                         ↕ LLM API（外部）
┌────────────────────────┐          ┌────────────────────────────────┐
│  调用方                 │          │  dashscope / openai /           │
│  桌面App / 移动端       │          │  claude / gemini / ollama      │
│  第三方产品             │          └────────────────────────────────┘
└────────────────────────┘
```

---

## 三、Proactive Tick 完整链路

### 3.1 涌现机制（底层 → 上层）

**Step 1：时间代谢（`drive_metabolism.py:time_metabolism()`）**

容器 startup 后，SessionManager 的 asyncio 后台任务每 300 秒执行一次 sweep。每次 sweep 对池内每个活跃 session 调用 `agent.proactive_tick()`（`chat_agent.py:1316`）。

`proactive_tick` 第一步就是推进时间代谢：
```
connection.frustration += 0.15 × Δt_hours   ← 孤独感，线性累积
novelty.frustration   += 0.05 × Δt_hours   ← 无聊感，线性累积
其他驱力               *= e^(-0.08 × Δt)   ← 指数衰减
```

**Step 2：冲动检测（`chat_agent.py:1291`）**

```python
score = (norm_frust - baseline) / max(baseline, 0.05)
# norm_frust = frustration[d] / 5.0   → 0~1
# baseline   = agent.drive_baseline[d] → Hebbian 学习后动态演化的值

if max_score >= _IMPULSE_THRESHOLD (0.8):
    return (strongest_drive, "内心的联结冲动正在变强。")
```

**不是规则触发，而是涌现**：不同角色的 `drive_baseline` 不同，高 `baseline` 的角色需要更高的绝对饥饿值才能触发冲动。用得越多，baseline 演化越高，触发也越难，防止刷屏。

**Step 3：EverMemOS 记忆闪回（容器内 graceful degrade）**

原代码中 `if self.evermemos and self.evermemos.available` 保护，容器内 `evermemos=None` → 直接跳过，flashback_parts 为空，stimulus 里没有记忆闪回部分。可以通过 `memory_context` 注入补充（见第四节）。

**Step 4：Stimulus 自构建**

```
[内在状态] 已18小时未与小明互动。内心的联结冲动正在变强。
[预感] 他最近可能在忙重要的事       ← _foresight_text（上一轮对话后 LLM 生成的）
```

这段文字是引擎自己描述自己的内心状态，作为"无用户输入时的替代输入"进入 Critic。

**Step 5 → Step 10b：与正常对话完全相同的 Critic + NN + Feel + Express 流水线**

唯一的区别是：
- `R1 FROZEN`：不更新 relationship EMA（没有用户反馈）
- `R1 FROZEN`：不做 Hebbian 学习（没有用户刺激）
- `R1 FROZEN`：不演化 drive_baseline

Express 的 LLM 可以返回 modality = `"静默"` → `return None`（角色主动选择不说话）。

### 3.2 结果交付：outbox 状态机

```
proactive_tick() 返回结果
    ↓
outbox_can_enqueue() — 3 层守卫（state_store.py:351）
    ├── outbox_has_recent()     ← 冷却窗口（默认 4h），防止连续轰炸
    ├── outbox_pending_count()  ← 堆积上限（默认 3 条），防止离线堆积
    └── outbox_has_dedup()      ← dedup_key 去重（drive+关系深度+时间桶）
    ↓（通过）
outbox_insert() — 写入 SQLite，status='pending'（state_store.py:270）
    ↓
_queues[session_id].put(result) → asyncio.Queue
    ↓
SSE /api/session/{id}/events 流式推出
```

**dedup_key 构造逻辑（原 `main.py:332`）：**
```python
depth = agent._relationship_ema.get('relationship_depth', 0.0)
band = 'deep' if depth > 0.6 else 'mid' if depth > 0.3 else 'shallow'
bucket = int(time.time() // (cooldown_h * 3600))  # 时间桶：4小时一格
dedup_key = f"{drive_id}:{band}:{bucket}"
# → "connection:mid:110000" 在同一 4h 窗口内不重复
```

### 3.3 离线弹性：outbox 重试机制

调用方 SSE 断线时，消息不丢失：
```
SSE 断线时：
    → _queues[sid] 有消息但没有消费者
    → outbox 状态保持 pending
    → 下次 sweep 时 outbox_get_pending() 重新取出
    → 重试推送
    → 成功 → outbox_mark_delivered()
    → 失败 → outbox_mark_failed() → 重置为 pending（下次再试）
```

调用方重连后立即收到积压的主动消息。

### 3.4 Docker 容器中的变化对比

| 步骤 | 原 `main.py` | Docker 容器 | 改动 |
|------|-------------|-------------|------|
| 后台循环 | `_proactive_heartbeat_loop()` in main.py | `SessionManager._heartbeat_loop()` | **平移** |
| sweep 逻辑 | `_proactive_sweep()` in main.py | `SessionManager._sweep()` | **平移** |
| `proactive_tick()` | `chat_agent.py:1316` | 同上 | **零改动** |
| outbox 存储 | `state_store.outbox_*` | 同上 | **零改动** |
| 交付通道 | `ws.send_json()` WebSocket | `queue.put()` → SSE | **只改传输层** |

---

## 四、完整 API 设计（13 端点）

### 4.1 对话

#### `POST /api/chat` — 同步对话

```jsonc
// Request
{
  "persona_id": "vivian",
  "session_id": "abc123",        // 不传则服务端自动生成
  "user_id": "user_001",         // 用于区分多用户，默认 "default_user"
  "user_name": "小明",
  "message": "最近心情不太好",
  "memory_context": {            // 可选：调用方任意记忆后端的搜索结果
    "profile": "用户喜欢安静，不喜欢被催",
    "narrative": "上周聊到他工作压力很大",
    "relevant": ["他之前说过不喜欢被催", "他妈妈叫李华"]
  }
}

// Response
{
  "session_id": "abc123",
  "reply": "……怎么了，能说说吗？",
  "modality": "文字",
  "monologue": "他说心情不好。要不要问清楚？还是先陪着他？",
  "engine_state": {
    "dominant_drive": "connection",      // 当前最强驱力
    "temperature": 0.062,                // NN 输出温度
    "reward": 0.15,                      // 本轮奖励
    "turn_count": 3,
    "signals": {                         // 8个情感信号，0~1
      "warmth": 0.78, "depth": 0.65, "defiance": 0.31,
      "playfulness": 0.42, "vulnerability": 0.55,
      "directness": 0.61, "initiative": 0.48, "curiosity": 0.70
    },
    "drives": {                          // 5个驱力当前值
      "connection": 0.72, "novelty": 0.41,
      "expression": 0.58, "safety": 0.35, "play": 0.29
    },
    "drive_baseline": {                  // 5个驱力 Hebbian 演化后的基线
      "connection": 0.30, "novelty": 0.70,
      "expression": 0.45, "safety": 0.20, "play": 0.55
    },
    "relationship": {                    // 4D 关系 EMA
      "depth": 0.15, "trust": 0.12, "valence": 0.30, "foresight": 0.05
    }
  }
}
```

**`memory_context` 注入位置：**
引擎在 `chat_agent.py` Step 8.5（`_build_feel_prompt` 之后，LLM 调用之前）将 `memory_context` 的三个字段 blend 进 Feel prompt：
```
[关于小明的偏好] {memory_context.profile}
[与小明过去发生的事] {memory_context.narrative}
[相关记忆] {memory_context.relevant[0..2]}
```
调用方可以接任意记忆后端（EverMemOS、Qdrant、自研 RAG、静态文件），统一通过这个接口注入。引擎本身零依赖外部记忆系统。

#### `POST /api/chat/stream` — SSE 流式对话

Feel（Pass 1）完成后立即推送 `feel_done`，让前端显示"正在输入..."，然后流式推 Express：

```
event: feel_done
data: {"monologue": "他说心情不好。要不要问清楚？"}

event: token
data: {"token": "……"}

event: token
data: {"token": "怎么了，"}

event: done
data: {"reply": "……怎么了，能说说吗？", "modality": "文字", "engine_state": {...}}
```

### 4.2 事件流（Proactive）

#### `GET /api/session/{id}/events` — SSE 常驻连接

调用方保持这条连接，引擎自主推送主动消息和心跳：

```
// 主动消息（impulse 触发 + Actor 选择说话）
event: proactive
data: {
  "reply": "你最近还好吗？",
  "modality": "文字",
  "monologue": "好久没消息了，有点担心他。",
  "drive_id": "connection",
  "engine_state": { ... }
}

// 心跳（每 30s，防止代理/CDN 关闭空连接）
event: heartbeat
data: {"ts": 1710000000}
```

**离线处理：**
调用方断线时，SSE generator 结束，但 outbox 里的消息保持 `pending`。调用方重连时，立即从 outbox 取出积压消息推送。

### 4.3 会话管理

#### `POST /api/session` — 创建或恢复会话

```jsonc
// Request
{ "persona_id": "vivian", "user_id": "user_001", "user_name": "小明" }
// 或者传入 session_id 来恢复已有会话

// Response
{
  "session_id": "abc123",
  "is_new": false,              // false = 从 SQLite 热加载的历史会话
  "engine_state": { ... }       // 恢复后的引擎状态快照
}
```

**会话创建的完整流程（复用 `main.py` 的 session 创建逻辑）：**
```
1. persona_loader.get(persona_id) → Persona 对象
2. ChatAgent(persona, llm, user_id, user_name,
             memory_store=memory_store,
             genome_data_dir=genome_data_dir)   ← evermemos=None
3. state_store.load_session(user_id, persona_id) → (agent, metabolism)
   ├── 有记录 → 恢复 agent.W1/W2/drive_state + metabolism.frustration
   │            恢复 agent._last_active, interaction_cadence（来自 load_proactive_meta）
   └── 无记录 → agent.age == 0 → pre_warm(['分享喜悦','吵架冲突','深夜心事'], steps=20)
                                  → 60步NN预热，drive_state重置为baseline
4. SessionManager._pool[session_id] = agent
5. SessionManager._lru.move_to_end(session_id)
6. SessionManager._queues[session_id] = asyncio.Queue()
```

#### `GET /api/session/{id}/status` — 引擎状态快照（不触发计算）

返回与 `/api/chat` response 中相同结构的 `engine_state`。

#### `GET /api/session/{id}/fingerprint` — 人格指纹

基于最近 30 轮对话的 signal 历史，计算稳定特征和矛盾：

```jsonc
{
  "traits": { "warmth": "low", "defiance": "high", "depth": "neutral" },
  "avg_signals": { "warmth": 0.28, "defiance": 0.71, ... },
  "contradictions": [["vulnerability", "defiance"]],
  "turn_count": 30
}
```

判断规则：`avg > 0.6` → high，`< 0.35` → low，其余 neutral。矛盾检测：warmth+defiance、vulnerability+directness 高值共存。

#### `DELETE /api/session/{id}` — 持久化并清理

```
state_store.save_session(user_id, persona_id, agent.agent, agent.metabolism)
_pool.pop(session_id)
_lru.pop(session_id)
_queues.pop(session_id)
```

### 4.4 角色管理

#### `GET /api/personas` — 列出所有角色

```jsonc
[
  {
    "persona_id": "vivian", "name": "Vivian", "mbti": "INFJ",
    "tags": ["温柔", "细腻", "会撒娇"],
    "bio": "25岁的…",
    "is_ready": true      // genesis 种子已存在 + pre_warm 已完成
  }
]
```

#### `GET /api/persona/{id}` — 角色详情

```jsonc
{
  "persona_id": "vivian",
  "name": "Vivian", "age": 25, "gender": "female", "mbti": "INFJ",
  "tags": [...], "bio": "...",
  "engine_params": {
    "hebbian_lr": 0.014, "crystal_threshold": 0.45,
    "connection_hunger_k": 0.10, "novelty_hunger_k": 0.04,
    "temp_coeff": 0.10, "phase_threshold": 2.8, ...
  },
  "drive_baseline": { "connection": 0.45, "novelty": 0.55, ... },
  "image": {
    "prompt_base": "a beautiful 25-year-old Chinese woman with long black hair...",
    "assets": ["front.png", "face.png"]
  }
}
```

#### `POST /api/persona` — 创建角色（两级）

**Level 1 — 结构化输入：**

```jsonc
// Request
{
  "persona_id": "nova", "name": "Nova", "age": 24, "gender": "female",
  "mbti": "ENFP", "lang": "en",
  "tags": ["enthusiastic", "creative", "scattered"],
  "bio": "A 24-year-old indie game developer who talks to her plants."
}
```

引擎内部执行（`PersonaFactory.create_from_params()`）：
```
1. MBTI → engine_params 推算（见表格）
2. 构造 PERSONA.md 草稿并写入 persona/personas/nova/PERSONA.md
3. PersonaLoader.load(nova) → Persona 对象
4. LLM 生成 genesis 种子（35~40条，复用 calibrate_genesis.py 的 classify_input 逻辑）
5. calibrate_persona() → 用 Agent 正向传播校准信号向量
6. 写入 .data/genome/genesis_nova.json
7. ChatAgent(nova, llm, ...) + pre_warm(60步)
8. state_store.save_session() 持久化预热后状态
```

**MBTI → engine_params 推算规则：**

| MBTI 维度 | 参数 | E值 | I值 |
|-----------|------|-----|-----|
| E vs I | `connection_hunger_k` | 0.15 | 0.08 |
| E vs I | `drive_baseline.connection` | 0.55 | 0.35 |
| N vs S | `novelty_hunger_k` | 0.07 | 0.03 |
| N vs S | `drive_baseline.novelty` | 0.65 | 0.40 |
| F vs T | `temp_coeff` | 0.12 | 0.06 |
| F vs T | `drive_baseline.expression` | 0.55 | 0.30 |
| J vs P | `phase_threshold` | 3.0 | 1.5 |
| J vs P | `drive_baseline.play` | 0.25 | 0.65 |

固定参数（来自现有角色的中位数）：
```python
hebbian_lr = 0.014
baseline_lr = 0.01
elasticity = 0.05
crystal_threshold = 0.50
hawking_gamma = 0.85
```

**Level 2 — 上传 PERSONA.md（高级用户）：**

调用方传入完整的 PERSONA.md（包含手工调校的 engine_params），引擎只负责 genesis 生成 + 校准 + 预热。

```jsonc
// Request（multipart/form-data）
{ "persona_id": "nova" }
// file: nova_persona.md
```

两级都返回：
```jsonc
{
  "persona_id": "nova", "status": "ready",
  "genesis_count": 37,
  "engine_params": { ... },
  "drive_baseline": { ... }
}
```

#### `DELETE /api/persona/{id}` — 删除角色

```
os.remove(persona/personas/{id}/PERSONA.md)
os.remove(.data/genome/genesis_{id}.json)
state_store: DELETE FROM genome_state WHERE persona_id='{id}'
state_store: DELETE FROM proactive_outbox WHERE persona_id='{id}'
```

#### `POST /api/persona/{id}/assets` — 上传视觉资产

接受 `front.png`, `face.png`, `awakening.mp4` 等文件，存入 `persona/personas/{id}/assets/`。引擎不做计算，纯静态文件代管，省调用方搭文件服务。

#### `GET /api/persona/{id}/assets/{filename}` — 获取资产文件

返回 `FileResponse`。

#### `GET /api/persona/{id}/assets` — 列出资产文件

返回资产文件列表。

### 4.5 诊断

#### `GET /api/engine/health`

```jsonc
{
  "status": "ok",
  "llm_reachable": true,
  "sqlite_writable": true,
  "personas_loaded": 3,
  "active_sessions": 2,
  "proactive_metrics": {
    "ticks_total": 42, "impulse_triggered": 8,
    "silence_chosen": 5, "outbox_enqueued": 3,
    "outbox_delivered": 3, "ws_push_fail": 0
  }
}
```

---

## 五、三个新文件完整实现

### 5.1 `engine_api.py`

薄层，只做路由声明 + Pydantic 模型，所有业务逻辑委托给 `SessionManager` 和 `PersonaFactory`。

```python
from __future__ import annotations
import os, uuid, json, time
from contextlib import asynccontextmanager
from typing import Optional, List
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from engine.session_manager import SessionManager
from engine.persona_factory import PersonaFactory
from persona.loader import PersonaLoader
from providers.llm.client import LLMClient
from providers.api_config import get_llm_config
from engine.state_store import StateStore
from memory.memory_store import MemoryStore

# ── Pydantic 模型 ──

class MemoryContext(BaseModel):
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

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    modality: str
    monologue: str
    engine_state: dict

class SessionCreateRequest(BaseModel):
    persona_id: str
    user_id: str = "default_user"
    user_name: Optional[str] = None
    session_id: Optional[str] = None

class PersonaCreateRequest(BaseModel):
    persona_id: str
    name: str
    age: int
    gender: str
    mbti: str
    lang: str = "zh"
    tags: List[str] = []
    bio: str = ""

# ── 全局服务（startup 初始化） ──

session_manager: SessionManager = None
persona_factory: PersonaFactory = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global session_manager, persona_factory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, ".data")
    genome_data_dir = os.path.join(data_dir, "genome")
    os.makedirs(genome_data_dir, exist_ok=True)

    llm_cfg = get_llm_config()
    llm = LLMClient(
        provider=llm_cfg["provider"], model=llm_cfg["model"],
        temperature=llm_cfg.get("temperature", 0.92),
        max_tokens=llm_cfg.get("max_tokens", 1024),
    )
    state_store = StateStore(os.path.join(data_dir, "openher.db"))
    memory_store = MemoryStore(os.path.join(data_dir, "soul_memory.db"))
    persona_loader = PersonaLoader(os.path.join(base_dir, "persona", "personas"))

    session_manager = SessionManager(
        llm=llm, state_store=state_store, memory_store=memory_store,
        persona_loader=persona_loader, genome_data_dir=genome_data_dir,
        tick_interval=int(os.getenv("ENGINE_TICK_INTERVAL", 300)),
        pool_max=int(os.getenv("ENGINE_SESSION_POOL_MAX", 100)),
    )
    persona_factory = PersonaFactory(
        llm=llm, persona_loader=persona_loader,
        genome_data_dir=genome_data_dir, state_store=state_store,
    )

    await session_manager.start()   # 启动 proactive heartbeat loop
    yield
    await session_manager.shutdown()  # 持久化所有会话 + 关闭 DB

app = FastAPI(title="Persona Engine", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── 路由 ──

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    agent = await session_manager.get_or_create(
        req.session_id or str(uuid.uuid4()), req.persona_id,
        req.user_id, req.user_name,
    )
    result = await agent.chat(
        req.message, req.user_name,
        memory_context=req.memory_context.dict() if req.memory_context else None,
    )
    await session_manager.checkpoint(req.session_id)
    return ChatResponse(session_id=req.session_id, **result)

@app.get("/api/session/{session_id}/events")
async def event_stream(session_id: str):
    # SSE 常驻连接，推送 proactive 消息
    queue = session_manager.get_queue(session_id)
    if not queue:
        raise HTTPException(404, "session not found")
    async def generator():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield {"event": "proactive", "data": json.dumps(event, ensure_ascii=False)}
            except asyncio.TimeoutError:
                yield {"event": "heartbeat", "data": json.dumps({"ts": int(time.time())})}
    return EventSourceResponse(generator())

# ... 其余路由按 API 设计表格实现
```

### 5.2 `engine/session_manager.py`

**完整实现，对应 `main.py` 的会话管理逻辑：**

```python
from __future__ import annotations
import asyncio, uuid, time, json
from collections import OrderedDict
from typing import Optional, Dict
import os

from agent.chat_agent import ChatAgent
from engine.state_store import StateStore
from memory.memory_store import MemoryStore
from persona.loader import PersonaLoader
from providers.llm.client import LLMClient

_INSTANCE_ID = str(uuid.uuid4())[:8]

class SessionManager:

    def __init__(self, llm, state_store, memory_store, persona_loader,
                 genome_data_dir, tick_interval=300, pool_max=100):
        self.llm = llm
        self.state_store = state_store
        self.memory_store = memory_store
        self.persona_loader = persona_loader
        self.genome_data_dir = genome_data_dir
        self.tick_interval = tick_interval
        self.pool_max = pool_max

        self._pool: Dict[str, ChatAgent] = {}          # session_id → ChatAgent
        self._lru: OrderedDict = OrderedDict()          # LRU 顺序
        self._queues: Dict[str, asyncio.Queue] = {}    # SSE 事件队列
        self._task: Optional[asyncio.Task] = None

        # metrics（对应 main.py:_proactive_metrics）
        self.metrics = {
            'ticks_total': 0, 'impulse_triggered': 0, 'silence_chosen': 0,
            'outbox_enqueued': 0, 'outbox_blocked': 0,
            'sse_push_ok': 0, 'sse_push_fail': 0,
            'outbox_delivered': 0, 'outbox_retries': 0,
        }

    async def start(self):
        self._task = asyncio.create_task(self._heartbeat_loop())

    async def shutdown(self):
        if self._task:
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass
        for sid in list(self._pool.keys()):
            await self.checkpoint(sid)
        self.state_store.close()
        self.memory_store.close()

    # ── 会话池 ──

    async def get_or_create(self, session_id: str, persona_id: str,
                             user_id: str = "default_user",
                             user_name: Optional[str] = None) -> ChatAgent:
        if session_id in self._pool:
            self._lru.move_to_end(session_id)
            return self._pool[session_id]

        # 从 SQLite 热加载
        persona = self.persona_loader.get(persona_id)
        if not persona:
            raise ValueError(f"Persona not found: {persona_id}")

        agent = ChatAgent(
            persona=persona, llm=self.llm,
            user_id=user_id, user_name=user_name,
            memory_store=self.memory_store,
            genome_data_dir=self.genome_data_dir,
            evermemos=None,  # 容器内不使用 EverMemOS
        )

        # 尝试恢复已有状态
        saved_agent, saved_metabolism = self.state_store.load_session(user_id, persona_id)
        if saved_agent:
            agent.agent = saved_agent
            agent.metabolism = saved_metabolism
            last_active, cadence, _ = self.state_store.load_proactive_meta(user_id, persona_id)
            agent._last_active = last_active
            agent._interaction_cadence = cadence
        else:
            # 新会话：仅当 age==0 时预热（防止重复预热）
            if agent.agent.age == 0:
                agent.pre_warm()

        # 入池
        self._pool[session_id] = agent
        self._lru[session_id] = True
        self._queues[session_id] = asyncio.Queue()

        # LRU 淘汰
        while len(self._pool) > self.pool_max:
            evicted_sid, _ = self._lru.popitem(last=False)
            await self.checkpoint(evicted_sid)
            self._pool.pop(evicted_sid, None)
            self._queues.pop(evicted_sid, None)

        return agent

    async def checkpoint(self, session_id: str):
        agent = self._pool.get(session_id)
        if not agent:
            return
        self.state_store.save_session(
            agent.user_id, agent.persona.persona_id,
            agent.agent, agent.metabolism,
        )

    def get_queue(self, session_id: str) -> Optional[asyncio.Queue]:
        return self._queues.get(session_id)

    # ── Proactive Heartbeat（对应 main.py:_proactive_heartbeat_loop） ──

    async def _heartbeat_loop(self):
        await asyncio.sleep(60)   # 初始延迟，等会话预热
        while True:
            try:
                await self._sweep()
            except Exception as e:
                print(f"[proactive] ❌ heartbeat error: {e}")
            await asyncio.sleep(self.tick_interval)

    async def _sweep(self):
        """对应 main.py:_proactive_sweep，逻辑完全相同，WebSocket 换成 asyncio.Queue。"""
        cooldown_h = 4
        max_pending = 3
        lock_ttl = 600

        for sid, agent in list(self._pool.items()):
            uid = agent.user_id
            pid = agent.persona.persona_id

            # 跨实例锁（与原逻辑相同）
            if not self.state_store.try_acquire_lock(uid, pid, _INSTANCE_ID, ttl=lock_ttl):
                continue

            try:
                # Phase 1: 生成新的主动消息
                self.metrics['ticks_total'] += 1
                result = await agent.proactive_tick()

                if result is not None:
                    self.metrics['impulse_triggered'] += 1
                    drive_id = result.get('drive_id', 'unknown')
                    depth = agent._relationship_ema.get('relationship_depth', 0.0)
                    band = 'deep' if depth > 0.6 else 'mid' if depth > 0.3 else 'shallow'
                    bucket = int(time.time() // (cooldown_h * 3600))
                    dedup_key = f"{drive_id}:{band}:{bucket}"

                    if self.state_store.outbox_can_enqueue(
                        uid, pid, dedup_key,
                        cooldown_hours=cooldown_h, max_pending=max_pending,
                    ):
                        self.state_store.outbox_insert(
                            uid, pid, result['tick_id'],
                            result['reply'], result.get('modality', '文字'),
                            result.get('monologue', ''), drive_id, dedup_key,
                        )
                        self.metrics['outbox_enqueued'] += 1
                    else:
                        self.metrics['outbox_blocked'] += 1

                elif result is None and agent._has_impulse():
                    self.metrics['silence_chosen'] += 1

                # Phase 2: 交付所有 pending 消息（含重试）
                pending = self.state_store.outbox_get_pending(uid, pid)
                for row in pending:
                    await self._deliver(agent, sid, row)

                # 持久化
                await self.checkpoint(sid)

            finally:
                self.state_store.release_lock(uid, pid, _INSTANCE_ID)

    async def _deliver(self, agent: ChatAgent, session_id: str, row: dict):
        """对应 main.py:_deliver_proactive_msg，WebSocket 换成 asyncio.Queue。"""
        uid, pid, tick_id = row['user_id'], row['persona_id'], row['tick_id']

        msg = self.state_store.outbox_try_send(uid, pid, tick_id)
        if not msg:
            return  # 已被其他实例取走

        queue = self._queues.get(session_id)
        if not queue:
            # 调用方 SSE 断线：保持 pending，下次 sweep 重试
            self.state_store.outbox_mark_failed(uid, pid, tick_id)
            self.metrics['sse_push_fail'] += 1
            return

        # 推入 SSE 队列
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
        except Exception as e:
            self.state_store.outbox_mark_failed(uid, pid, tick_id)
            self.metrics['sse_push_fail'] += 1
```

### 5.3 `engine/persona_factory.py`

**注意：与 `persona/generator.py` 完全不同**

`generator.py` = 用 TTS+LLM 随机生成角色（应用层工具，不进容器）
`persona_factory.py` = 给定明确身份，自动推算引擎参数 + 生成 genesis 种子 + 预热

```python
from __future__ import annotations
import json, os
from typing import Optional
from engine.genome.genome_engine import Agent, simulate_conversation
from engine.genome.calibrate_genesis import (
    SCENARIO_CONTEXTS, KEYWORD_MAP, classify_input, calibrate_persona
)
from persona.loader import PersonaLoader, Persona
from engine.state_store import StateStore
from agent.chat_agent import ChatAgent

# MBTI → engine_params 推算表
_MBTI_PARAMS = {
    'E': {'connection_hunger_k': 0.15, 'drive_baseline.connection': 0.55},
    'I': {'connection_hunger_k': 0.08, 'drive_baseline.connection': 0.35},
    'N': {'novelty_hunger_k': 0.07,   'drive_baseline.novelty': 0.65},
    'S': {'novelty_hunger_k': 0.03,   'drive_baseline.novelty': 0.40},
    'F': {'temp_coeff': 0.12,          'drive_baseline.expression': 0.55},
    'T': {'temp_coeff': 0.06,          'drive_baseline.expression': 0.30},
    'P': {'phase_threshold': 1.5,      'drive_baseline.play': 0.65},
    'J': {'phase_threshold': 3.0,      'drive_baseline.play': 0.25},
}
_FIXED_PARAMS = {
    'hebbian_lr': 0.014, 'baseline_lr': 0.01,
    'elasticity': 0.05, 'crystal_threshold': 0.50,
    'hawking_gamma': 0.85,
}

class PersonaFactory:

    def __init__(self, llm, persona_loader, genome_data_dir, state_store):
        self.llm = llm
        self.persona_loader = persona_loader
        self.genome_data_dir = genome_data_dir
        self.state_store = state_store

    def mbti_to_engine_params(self, mbti: str) -> dict:
        """4个 MBTI 字符 → engine_params dict。"""
        params = dict(_FIXED_PARAMS)
        drive_baseline = {'connection': 0.45, 'novelty': 0.55,
                          'expression': 0.45, 'safety': 0.30, 'play': 0.45}
        for char in mbti.upper():
            if char in _MBTI_PARAMS:
                for k, v in _MBTI_PARAMS[char].items():
                    if k.startswith('drive_baseline.'):
                        drive_baseline[k.split('.')[1]] = v
                    else:
                        params[k] = v
        params['drive_baseline'] = drive_baseline
        return params

    async def generate_genesis_seeds(self, persona: Persona, count: int = 37) -> list:
        """
        用 LLM 为角色生成 genesis 种子对话片段。
        复用 calibrate_genesis.py 的场景分类逻辑。
        """
        scenes = list(SCENARIO_CONTEXTS.keys())  # 7个场景
        seeds = []
        prompts_per_scene = max(1, count // len(scenes))
        system = (
            f"你是{persona.name}。{persona.bio or ''}\n"
            f"性格标签：{', '.join(persona.tags or [])}\n"
            f"说话风格：{getattr(persona, 'speaking_style', '')}\n"
            "请用第一人称回应用户，体现你的人设特色。"
        )
        for scene, ctx in SCENARIO_CONTEXTS.items():
            scene_prompts = [k for k, v in KEYWORD_MAP.items() if v == scene][:prompts_per_scene]
            for user_input in scene_prompts:
                response = await self.llm.chat([
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_input},
                ])
                seeds.append({
                    "user_input": user_input,
                    "monologue": "",             # 校准时由 Agent 正向传播填充
                    "reply": response.content,
                    "context": ctx,              # 12D 场景上下文
                    "signals": None,             # 由 calibrate_persona() 填充
                })
        return seeds

    async def create_from_params(self, req: dict) -> dict:
        """
        Level 1 入口：结构化参数 → 完整角色（写 PERSONA.md + genesis + 预热）。
        """
        persona_id = req['persona_id']

        # 1. MBTI → engine_params
        engine_params = self.mbti_to_engine_params(req.get('mbti', 'INFJ'))

        # 2. 写 PERSONA.md（简单结构，供 PersonaLoader 解析）
        persona_dir = os.path.join(
            os.path.dirname(self.genome_data_dir), '..', 'persona', 'personas', persona_id
        )
        os.makedirs(persona_dir, exist_ok=True)
        persona_md = self._build_persona_md(req, engine_params)
        with open(os.path.join(persona_dir, 'PERSONA.md'), 'w', encoding='utf-8') as f:
            f.write(persona_md)

        # 3. 加载角色
        self.persona_loader.reload(persona_id)
        persona = self.persona_loader.get(persona_id)

        # 4. 生成 genesis 种子
        seeds = await self.generate_genesis_seeds(persona)

        # 5. 校准向量（复用 calibrate_persona 的 Agent 正向传播逻辑）
        calibrated = self._calibrate_seeds(persona, seeds)
        genesis_path = os.path.join(self.genome_data_dir, f"genesis_{persona_id}.json")
        with open(genesis_path, 'w', encoding='utf-8') as f:
            json.dump(calibrated, f, ensure_ascii=False, indent=2)

        # 6. 预热（60步）+ 持久化
        agent = ChatAgent(
            persona=persona, llm=self.llm,
            genome_data_dir=self.genome_data_dir,
            evermemos=None,
        )
        if agent.agent.age == 0:
            agent.pre_warm()
        self.state_store.save_session(
            "default_user", persona_id,
            agent.agent, agent.metabolism,
        )

        return {
            "persona_id": persona_id, "status": "ready",
            "genesis_count": len(calibrated),
            "engine_params": engine_params,
            "drive_baseline": engine_params.get('drive_baseline', {}),
        }

    def _calibrate_seeds(self, persona, seeds: list) -> list:
        """复用 calibrate_genesis.py 的向量校准逻辑。"""
        agent = Agent(seed=42, engine_params=persona.engine_params)
        if persona.drive_baseline:
            for d, v in persona.drive_baseline.items():
                if d in agent.drive_baseline:
                    agent.drive_baseline[d] = float(v)
                    agent.drive_state[d] = float(v)
        simulate_conversation(agent, ["分享喜悦", "吵架冲突", "深夜心事"], steps_per_scenario=20)
        for d in agent.drive_baseline:
            agent.drive_state[d] = agent.drive_baseline[d]

        calibrated = []
        for seed in seeds:
            ctx = seed.get('context', {})
            signals = agent.compute_signals(ctx)
            calibrated.append({**seed, "signals": signals})
        return calibrated

    def _build_persona_md(self, req: dict, engine_params: dict) -> str:
        """生成最小可用的 PERSONA.md 内容。"""
        # 格式对齐 persona/loader.py 解析的 frontmatter 结构
        db = engine_params.get('drive_baseline', {})
        tags_str = ", ".join(req.get('tags', []))
        return f"""---
name: {req['name']}
age: {req.get('age', 25)}
gender: {req.get('gender', 'female')}
mbti: {req.get('mbti', 'INFJ')}
lang: {req.get('lang', 'zh')}
tags: [{tags_str}]
drive_baseline:
  connection: {db.get('connection', 0.45)}
  novelty: {db.get('novelty', 0.55)}
  expression: {db.get('expression', 0.45)}
  safety: {db.get('safety', 0.30)}
  play: {db.get('play', 0.45)}
engine_params:
  hebbian_lr: {engine_params.get('hebbian_lr', 0.014)}
  connection_hunger_k: {engine_params.get('connection_hunger_k', 0.10)}
  novelty_hunger_k: {engine_params.get('novelty_hunger_k', 0.05)}
  temp_coeff: {engine_params.get('temp_coeff', 0.09)}
  phase_threshold: {engine_params.get('phase_threshold', 2.5)}
  crystal_threshold: {engine_params.get('crystal_threshold', 0.50)}
  hawking_gamma: {engine_params.get('hawking_gamma', 0.85)}
---

## bio
{req.get('bio', '')}

## speaking_style
{req.get('speaking_style', '')}
"""
```

---

## 六、Docker 配置

### `Dockerfile`（多阶段构建）

```dockerfile
# Stage 1: builder — 安装依赖，不进 runtime 镜像
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements-engine.txt .
RUN pip install --user --no-cache-dir -r requirements-engine.txt

# Stage 2: runtime — 最小化镜像
FROM python:3.11-slim
WORKDIR /app

# 从 builder 复制已安装的包
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# 复制源码（排除 .data、__pycache__、static）
COPY . .

# 数据目录（Volume 挂载点）
RUN mkdir -p .data/genome

EXPOSE 8800

# --workers 1：保证 SessionManager 内存池全局唯一
# --loop uvloop：asyncio 性能优化
CMD ["uvicorn", "engine_api:app", \
     "--host", "0.0.0.0", "--port", "8800", \
     "--workers", "1", "--loop", "uvloop"]
```

### `.dockerignore`

```
.data/
__pycache__/
*.pyc
*.pyo
static/
*.mp3
*.wav
*.png
*.jpg
node_modules/
.env
*.db
```

### `docker-compose.yml`

```yaml
services:
  engine:
    image: openher-engine:latest
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8800:8800"
    volumes:
      # 核心资产（持久化，引擎更新不丢失）
      - ./.data:/app/.data
      # 角色定义（Volume 挂载支持热更新，无需重启容器）
      - ./persona/personas:/app/persona/personas
      # LLM 配置（只读挂载）
      - ./providers/api.yaml:/app/providers/api.yaml:ro
    env_file: .env
    environment:
      ENGINE_TICK_INTERVAL: "300"        # proactive sweep 间隔（秒）
      ENGINE_SESSION_POOL_MAX: "100"     # 内存池上限（LRU 淘汰）
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8800/api/engine/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G     # SQLite + NN 矩阵常驻内存，1G 足够
```

### `requirements-engine.txt`

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
uvloop>=0.19.0
openai>=1.12.0
anthropic>=0.18.0
dashscope>=1.17.0
aiosqlite>=0.19.0
pyyaml>=6.0.1
python-frontmatter>=1.1.0
pydantic>=2.6.0
python-dotenv>=1.0.0
httpx>=0.27.0
python-multipart>=0.0.9
sse-starlette>=1.6.0
```

排除（和 `requirements.txt` 的差异）：
`edge-tts` / `evermemos` / `chromadb` / `python-jose` / `passlib` / `websockets` / `apscheduler` / `pytest` / `pytest-asyncio`

---

## 七、核心资产结构（Volume 内容）

```
.data/
├── openher.db                    ← 主 SQLite（WAL 模式）
│   ├── genome_state              ← 每角色×每用户的 NN 权重 + 驱力状态
│   │     columns: user_id, persona_id, agent_data(JSON), metabolism_data(JSON),
│   │              state_version, last_active_at, interaction_cadence
│   ├── proactive_outbox          ← 主动消息队列（状态机）
│   │     columns: user_id, persona_id, tick_id, reply, modality, monologue,
│   │              drive_id, dedup_key, created_at, status, delivered_at
│   ├── proactive_lock            ← 跨实例分布式锁
│   └── chat_summary              ← 对话摘要
├── soul_memory.db                ← SoulMem 行为记忆（FTS5 全文检索）
└── genome/
    ├── genesis_vivian.json       ← Vivian 的初始种子向量
    │     [{user_input, monologue, reply, context(12D), signals(8D)}, ...]
    ├── genesis_kai.json
    └── {persona_id}_{user_id}/   ← style_memory SQLite（每角色×每用户）
        └── style_memory.db       ← KNN 结晶记忆（对话积累，含 mass 值）
```

**四类核心资产的价值：**

| 资产 | 存储位置 | 价值 |
|------|---------|------|
| NN 权重（W1/W2）| `genome_state.agent_data` | Hebbian 学习积累，越聊越有个性 |
| 驱力基线（drive_baseline）| `genome_state.agent_data` | 反映角色与该用户交互后演化的"性格重心" |
| genesis 种子 | `genome/genesis_{id}.json` | 人格 DNA，决定 KNN 的初始检索空间 |
| 结晶记忆（style_memory）| `genome/{id}_{uid}/style_memory.db` | 高质量对话自然沉淀，mass 越高越难覆盖 |

引擎容器更新时，Volume 保留 → 角色不失忆。

---

## 八、调用方集成模式

```
调用方 App（桌面/移动/第三方）
│
├── 启动时：
│   ├── POST /api/session → 拿到 session_id
│   └── GET /api/session/{id}/events → 建立 SSE 长连接（持续接收主动消息）
│
├── 用户发消息时：
│   ├── （可选）查询 EverMemOS/Qdrant/RAG → memory_context
│   └── POST /api/chat { message, memory_context }
│       └── 同步收到 reply + monologue + engine_state
│
├── 需要流式回复时：
│   └── POST /api/chat/stream → SSE 流，先收 feel_done，再收 token*，最后收 done
│
├── 收到 SSE proactive 事件时：
│   └── 直接展示给用户（角色主动发来的消息）
│
└── 创建新角色时：
    └── POST /api/persona { mbti, tags, bio, ... }
        └── 等待响应（异步 LLM 生成 genesis + 预热，约 30~60s）
```

---

## 九、验证

```bash
# 1. 构建镜像
docker build -t openher-engine .

# 2. 启动容器
docker compose up -d

# 3. 健康检查（确认 LLM 连通 + SQLite 可写）
curl http://localhost:8800/api/engine/health

# 4. 列出已加载角色
curl http://localhost:8800/api/personas

# 5. 创建会话
SESSION=$(curl -s -X POST http://localhost:8800/api/session \
  -H "Content-Type: application/json" \
  -d '{"persona_id":"vivian","user_name":"test"}' | jq -r '.session_id')

# 6. 对话（核心验证）
curl -X POST http://localhost:8800/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"persona_id\":\"vivian\",\"session_id\":\"$SESSION\",\"message\":\"你好\",\"user_name\":\"test\"}"
# 验证：reply 符合人设，monologue 非空，engine_state.signals 数值合理

# 7. SSE 事件流（等待 proactive 推送）
curl -N "http://localhost:8800/api/session/$SESSION/events"

# 8. 5 轮对话后验证 Hebbian 学习
curl "http://localhost:8800/api/session/$SESSION/status"
# 验证：drive_baseline 与 5 轮对话前有微量变化

# 9. 创建新角色（Level 1）
curl -X POST http://localhost:8800/api/persona \
  -H "Content-Type: application/json" \
  -d '{"persona_id":"nova","name":"Nova","age":24,"gender":"female","mbti":"ENFP","lang":"en","tags":["creative","scattered"],"bio":"indie game developer"}'
# 验证：status="ready"，genesis_count 35+

# 10. 验证新角色对话（人设一致性）
curl -X POST http://localhost:8800/api/chat \
  -H "Content-Type: application/json" \
  -d '{"persona_id":"nova","message":"hey!","user_name":"test"}'
```
