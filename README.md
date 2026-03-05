<div align="right">

[🇨🇳 中文文档](README_CN.md) | 🇺🇸 English

</div>

<div align="center">

# 🧬 OpenHer

### Thermodynamic Persona Engine × EverMemOS

**An AI companion that genuinely evolves — not a chatbot with a fixed prompt.**

[![EverMemOS](https://img.shields.io/badge/Powered%20by-EverMemOS-FF6B6B?style=flat-square)](https://evermind.ai)
[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)

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

![OpenHer Architecture](docs/assets/architecture.png)

</div>


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

The server starts on `http://localhost:8800` with WebSocket support.

### Try a Conversation

```python
import asyncio
from core.persona import PersonaLoader
from core.llm import LLMClient
from core.agent.chat_agent import ChatAgent
from core.memory.evermemos_client import EverMemOSClient

async def main():
    loader = PersonaLoader("personas")
    persona = loader.get("vivian")  # or "luna", "iris"
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

OpenHer ships with three sample personas, each defined by a unique **drive baseline** (genome seed):

| Persona | MBTI | Drive Signature | Emergent Style |
|:--------|:-----|:---------------|:---------------|
| **Vivian** | INTJ | Low connection, high safety | Sharp wit, secretly caring |
| **Luna** | ENFP | High connection, high play | Bright, bubbly, sweet |
| **Iris** | INFP | High expression, high safety | Gentle, poetic, dreamy |

Create your own by adding a folder in `personas/` with a `PERSONA.md` (pure YAML with display layer + genome seed).

## Tech Stack

| Layer | Technology |
|:------|:-----------|
| Server | Python 3.11+, FastAPI, asyncio |
| LLM | Qwen3-Max, GPT-4o, Claude, DeepSeek, Ollama |
| Memory | **EverMemOS** (Cloud API) |
| Local Storage | ContinuousStyleMemory, JSONL |
| Client | Flutter (iOS/Android), WebSocket |

## License

This project is licensed under the [Apache License 2.0](LICENSE) — you are free to use, study, and modify the code for any purpose, including commercial use, for free.

## Acknowledgments

- **[EverMemOS](https://evermind.ai)** — Long-term memory infrastructure
- **Memory Genesis Competition 2026** — Catalyst for this project's open-source release

---

<div align="center">

**Built with 🧬 by the OpenHer team**

*Personality is not a prompt. It's a process.*

</div>
