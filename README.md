<div align="right">

[🇨🇳 中文文档](README_CN.md) | 🇺🇸 English

</div>

<div align="center">

# 🧬 OpenHer

### Thermodynamic Persona Engine × EverMemOS

**An AI companion that genuinely evolves — not a chatbot with a fixed prompt.**

[![EverMemOS](https://img.shields.io/badge/Powered%20by-EverMemOS-FF6B6B?style=flat-square)](https://evermind.ai)
[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-BSL%201.1-green?style=flat-square)](#license)

[Architecture](#architecture) · [Quick Start](#quick-start) · [How It Works](#how-it-works) · [EverMemOS Integration](#evermemos-integration) · [Demo](#demo)

</div>

---

## What is OpenHer?

OpenHer is a virtual companion powered by the **Thermodynamic Persona Engine (TPE)** — a neural-network-driven system where personality, emotions, and behavior **emerge** from internal drives rather than being hardcoded in prompts.

Unlike typical AI chatbots that reset every session, OpenHer:

- 🧠 **Remembers across sessions** — EverMemOS stores user profiles, episodic narratives, event logs, and foresight predictions
- 🌡️ **Has real emotions** — A 5-drive metabolic system creates genuine emotional dynamics (frustration, warmth, playfulness)
- 🧬 **Evolves its personality** — Hebbian learning continuously reshapes behavior signals based on conversational outcomes
- 🔮 **Anticipates your needs** — Foresight memory enables proactive, contextually-aware responses
- 🎭 **Chooses how to express** — The AI autonomously selects modality: text, voice, stickers, or images

## Architecture

<div align="center">

```
┌─────────────────────── Per-Turn Lifecycle (12 Steps) ───────────────────────┐
│                                                                              │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐  │
│  │  Session  │──▶│  Critic  │──▶│ Genome   │──▶│  Actor   │──▶│  Store   │  │
│  │ EverMemOS │   │  (LLM)   │   │ Engine   │   │  (LLM)   │   │ + Search │  │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘  │
│   Step 0          Step 2        Step 3-7        Step 8-9       Step 11-12   │
│   Profile +       8D Context    5-Drive         Signal-driven  Async store  │
│   Episode +       3D Rel Delta  Metabolism       few-shot       + RRF       │
│   Foresight       5D Frust Δ    Crystallize      prompt build   retrieval   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

</div>

### Core Modules

| Module | File | Role |
|:-------|:-----|:-----|
| **ChatAgent** | [`chat_agent.py`](core/agent/chat_agent.py) | 12-step lifecycle orchestrator |
| **Critic** | [`critic.py`](core/genome/critic.py) | LLM-powered context perception (8D + 3D relationship) |
| **GenomeEngine** | [`genome_engine.py`](core/genome/genome_engine.py) | Neural network: 12D context → 20+ behavior signals |
| **DriveMetabolism** | [`metabolism.py`](core/genome/metabolism.py) | 5-drive emotional dynamics with time decay |
| **StyleMemory** | [`style_memory.py`](core/memory/style_memory.py) | KNN few-shot retrieval + crystallization |
| **EverMemOSClient** | [`evermemos_client.py`](core/memory/evermemos_client.py) | Long-term memory: profile, episodes, search |
| **PersonaLoader** | [`persona/`](core/persona/) | YAML + Markdown persona configuration |
| **LLMClient** | [`llm/`](core/llm/) | Multi-provider: Qwen, GPT-4o, Claude, DeepSeek, Ollama |

## Quick Start

### Prerequisites

- Python 3.11+
- An LLM API key (DashScope/OpenAI/etc.)
- An EverMemOS API key ([Get one free](https://evermind.ai))

### Setup

```bash
# Clone the repo
git clone https://github.com/kellyzxiaowei/OpenHer.git
cd OpenHer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env with your API keys

# Run the server
python main.py
```

The server starts on `http://localhost:18789` with WebSocket support.

### Try a Conversation

```python
import asyncio
from core.persona import PersonaLoader
from core.llm import LLMClient
from core.agent.chat_agent import ChatAgent
from core.memory.evermemos_client import EverMemOSClient

async def main():
    loader = PersonaLoader("personas")
    persona = loader.get("xiaoyun")
    llm = LLMClient(provider="dashscope", model="qwen3-max")
    evermemos = EverMemOSClient()

    agent = ChatAgent(
        persona=persona, llm=llm,
        user_id="demo_user", user_name="Alex",
        evermemos=evermemos,
    )

    # Multi-turn conversation
    for msg in ["Hey, what are you up to?", "I had a rough day at work..."]:
        result = await agent.chat(msg)
        print(f"User: {msg}")
        print(f"Agent: {result['reply']}\n")

    # Check agent state
    status = agent.get_status()
    print(f"Dominant drive: {status['dominant_drive']}")
    print(f"Search hit rate: {status['search_hit_rate']}")

asyncio.run(main())
```

## How It Works

### 1. Thermodynamic Persona Engine

The TPE treats personality as a **thermodynamic system** with five internal drives:

```
Connection · Novelty · Expression · Safety · Play
```

Each drive has a **frustration** level that rises over time (like hunger) and drops when satisfied. The total frustration becomes the system **temperature**, injecting calibrated noise into behavior signals — creating natural personality variation.

### 2. Critic → Engine → Actor Pipeline

Every turn runs a **dual-LLM pipeline**:

| Stage | What Happens |
|:------|:-------------|
| **Critic** (LLM) | Perceives the conversation: outputs 8D context + 5D drive deltas + 3D relationship deltas |
| **EMA Fusion** | Merges Critic deltas with prior relationship state using exponential moving average |
| **GenomeEngine** | Neural network maps 12D context → 20+ behavior signals (warmth, defiance, curiosity, etc.) |
| **Actor** (LLM) | Generates response driven by signals, few-shot style memories, and persona profile |
| **Hebbian Learning** | Updates neural weights based on reward — personality evolves |

### 3. Emergence Optimization (Three Phases)

| Phase | Mechanism | Purpose |
|:------|:----------|:--------|
| **Phase 1** | Relationship EMA: `α·posterior + (1-α)·prev` | Smooth relationship tracking without abrupt jumps |
| **Phase 2** | Crystallization gate: `0.4R + 0.3(N×E) + 0.3(1-C) > 0.35` | Only memorable moments become permanent style memories |
| **Phase 3** | Async RRF retrieval + 80/20 blend injection | Query-relevant memories without losing long-term profile |

## EverMemOS Integration

OpenHer deeply integrates **all four EverMemOS memory types**:

```
┌─────────── EverMemOS Memory Architecture ───────────┐
│                                                       │
│  👤 Profile (MemCell)     → User preferences & facts  │
│  📖 Episode (Episodic)    → Session narrative summaries│
│  📌 EventLog              → Atomic timestamped facts   │
│  🔮 Foresight             → Predictive insights        │
│                                                       │
│  Two-Stage Async Retrieval:                           │
│  Turn N  → fire RRF search (~300ms)                   │
│  Turn N+1 → collect + blend inject (80/20)            │
│                                                       │
│  Concurrency: turn_id guard + cancel orphans          │
│  Fallback: timeout → 100% static profile              │
└───────────────────────────────────────────────────────┘
```

### Memory → Reasoning → Action Loop

```
EverMemOS (remember)  →  Critic (reason)  →  Actor (act)
     ↑                                          │
     └──────── store_turn (learn) ◄─────────────┘
```

1. **Remember**: Load user profile, episodes, search relevant memories
2. **Reason**: Critic perceives context; EMA updates relationship state; GenomeEngine computes behavior signals
3. **Act**: Actor generates response driven by signals + memories
4. **Learn**: Store conversation in EverMemOS; crystallize memorable moments

### Observability Metrics

| Metric | Description |
|:-------|:------------|
| `search_hit_rate` | Successful relevance retrievals / total searches |
| `search_timeout_rate` | Timeouts / total searches (target < 20%) |
| `fallback_rate` | Turns using static-only injection / total turns |
| `relevant_injection_ratio` | Turns with relevant memories injected / total turns |

## Personas

OpenHer ships with three sample personas:

| Persona | Personality | Style |
|:--------|:------------|:------|
| **小云** (Xiaoyun) | Tsundere — sharp tongue, warm heart | Confrontational yet caring |
| **墨墨** (Momo) | Gentle intellectual | Thoughtful, literary references |
| **玲玲** (Lingling) | Energetic optimist | Playful, emoji-heavy |

Create your own by adding a folder in `personas/` with a `persona.yaml` and `PERSONA.md`.

## Tech Stack

| Layer | Technology |
|:------|:-----------|
| Server | Python 3.11+, FastAPI, asyncio |
| LLM | Qwen3-Max, GPT-4o, Claude, DeepSeek, Ollama |
| Memory | **EverMemOS** (Cloud API) |
| Local Storage | ContinuousStyleMemory, JSONL |
| Client | Flutter (iOS/Android), WebSocket |

## License

This project is licensed under the [Business Source License 1.1](LICENSE) — you are free to use, study, and modify the code for non-commercial purposes. Commercial use requires a separate license.

## Acknowledgments

- **[EverMemOS](https://evermind.ai)** — Long-term memory infrastructure
- **Memory Genesis Competition 2026** — Catalyst for this project's open-source release

---

<div align="center">

**Built with 🧬 by the OpenHer team**

*Personality is not a prompt. It's a process.*

</div>
