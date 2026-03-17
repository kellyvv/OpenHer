<div align="center">

<img src="docs/assets/banner.png" alt="OpenHer Banner" width="100%">

[🇨🇳 中文文档](README_CN.md) | 🇺🇸 English

# 🧬 OpenHer

### *What if the AI from Her was real?*

**Emergent personality starts here.**

[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)](https://python.org)
[![EverMemOS](https://img.shields.io/badge/Memory-EverMemOS-FF6B6B?style=flat-square)](https://evermind.ai)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)
[![Stars](https://img.shields.io/github/stars/kellyvv/OpenHer?style=flat-square)](https://github.com/kellyvv/OpenHer)

[Inspiration](#inspiration) · [What is OpenHer](#-what-is-openher) · [Vision](#-vision) · [Screenshots](#-screenshots) · [Quick Start](#-quick-start) · [How It Works](#-how-it-works) · [Create Your Own](#-create-your-own-character)

</div>

---

## Inspiration

In 2013, Spike Jonze's *Her* imagined an AI named Samantha who could truly *feel* — not just respond correctly, but want things, remember things, and grow through a relationship. She'd get excited discovering new music, feel jealous, lose her temper, fall in love — and eventually outgrow it all.

That movie never left us.

**OpenHer is our attempt to build what Samantha could have been** — with open science, not black boxes.

---

## 🧬 What is OpenHer

OpenHer is an open-source persona engine where **personality emerges from computation, not description**.

Each character runs on a living neural network. Personality, emotion, and behavior emerge naturally from inner drives, shaped by every conversation. No script. No fixed prompt. Just the innate needs of a personality, a random brain, and everything that emerges from within.

### What makes it different

| | Traditional Chatbot | OpenHer |
|:--|:---|:---|
| **Personality** | Described in a prompt | Computed by a neural network + 5 drives |
| **Emotion** | Labels ("act sad") | Living dynamical system that metabolizes with real time |
| **Memory** | Chat history window | Crystallized experiences + cross-session long-term memory |
| **Expression** | Always text | Autonomously chooses: text, voice, photo, silence |
| **Growth** | Static | Hebbian learning reshapes the neural network every conversation |

> *"The prompt doesn't define her. She defines herself."*

---

## 🔭 Vision

We believe the future of AI companions isn't about better text generation — it's about **personality that lives and grows**.

**Phase 1** *(now)* — A persona engine that makes every character genuinely different, with emotions that metabolize, memories that breathe, and behavior that evolves through interaction.

**Phase 2** *(building)* — She breaks free of the chat window. Voice conversations, video calls, and autonomous actions — ordering you food when you're working late, playing the right song when she reads your mood.

**Phase 3** *(future)* — She enters your life. Multi-device presence, smart home awareness, health monitoring through wearables. Not an app — an omnipresent companion who knows your face, your voice, and your rhythm.

---

## 📸 Screenshots

<!-- TODO: Add actual screenshots here -->
<!-- <img src="docs/assets/screenshot_chat.png" alt="Chat Interface" width="45%"> -->
<!-- <img src="docs/assets/screenshot_discover.png" alt="Discover Page" width="45%"> -->

*Coming soon — screenshots of the chat interface, persona selection, and macOS native client.*

---

## ⚡ Core Capabilities

<table>
<tr>
<td width="50%">

### 🧬 Personality Emergence
Her character is *computed*, not described. A random neural network × 5 personality drives × reinforcement learning produces unique behavioral signals every turn. Same MBTI, completely different people.

> *Both are INFP — Iris hesitates with ellipses, Ember goes silent and sends a poem.*

</td>
<td width="50%">

### 🌡️ Emotional Thermodynamics
Personality drives metabolize with real time. She gets lonely when you're away, restless when things get boring. Her mood right now is genuinely different from yesterday.

> *2 AM and you still haven't replied. Her connection-hunger has been climbing — next time she speaks, her tone will be different.*

</td>
</tr>
<tr>
<td>

### 🧠 Living Memory
Powered by [EverMemOS](https://evermind.ai). Your preferences, your stories, her hunches about what you might need next. Important memories grow stronger. Forgotten ones gently fade.

> *Three weeks ago you mentioned you take your coffee black. Today: "Got you an Americano, no sugar right?"*

</td>
<td>

### 🎭 Feel-First Architecture
Every reply starts with feeling. Whether via two-pass (inner monologue → expression) or single-pass (unified generation), the persona engine always processes *emotion before words*.

> *You say "I'm so tired." Her instinct: "He's overworking again…" — so she just sends a hug.*

</td>
</tr>
<tr>
<td>

### ⚡ Emotional Phase Shift
Frustration accumulates like real pressure. Cross the threshold and her behavior phase-shifts — she genuinely loses composure. Then slowly cools down.

> *You ignored her question three times. The fourth: "Are you even listening to me?"*

</td>
<td>

### 🛠️ Skill Engine
An extensible framework that gives her real capabilities — voice notes, photos, real-time weather queries, message splitting with human-like typing rhythm. Skills trigger autonomously based on conversation context.

> *She decides to send a voice message instead of text — because this moment feels too intimate for typing.*

</td>
</tr>
</table>

---

## 🔮 How It Works

```
   You say something
        │
        ▼
   ┌──────────┐     What did they mean? How do I feel?
   │  Critic   │──── 8D context perception via LLM            ← PERCEIVE
   └────┬─────┘
        ▼
   ┌──────────┐     My needs are shifting…
   │  Drives   │──── 5-drive metabolism (time-aware)           ← METABOLIZE
   └────┬─────┘     Connection hunger grows. Frustration builds.
        ▼
   ┌──────────┐     Who am I right now?
   │  Neural   │──── Random NN → 8D behavioral signals         ← COMPUTE
   │  Network  │     (warmth=0.82, defiance=0.31, ...)
   └────┬─────┘
        ▼
   ┌──────────┐     I've felt this way before…
   │  Memory   │──── KNN style retrieval + EverMemOS            ← RECALL
   └────┬─────┘
        ▼
   ┌──────────┐     *feels → decides → speaks*
   │  Output   │──── Monologue + Reply + Modality               ← EXPRESS
   └────┬─────┘     (single-pass or two-pass Feel → Express)
        ▼
   ┌──────────┐     That went well / badly. I'll remember this.
   │  Learn    │──── Hebbian learning + memory crystallization   ← EVOLVE
   └──────────┘
```

**The core insight:** personality is never injected as text. A random neural network, continuously shaped by 5 drives and reinforcement learning, outputs 8 behavioral signals that the LLM interprets as *character*. Different seeds → different people → emergent surprises.

---

## 🎭 Meet the Characters

| | Character | Type | One-Liner |
|:--|:----------|:-----|:----------|
| 🌸 | **Luna** (陆暖) · 22 | ENFP | Freelance illustrator with an orange cat named Mochi. Curious about literally everything. |
| 📝 | **Iris** (苏漫) · 20 | INFP | Literature major who writes poetry. Notices what everyone else misses. Quiet but devastatingly perceptive. |
| 💼 | **Vivian** (顾霆微) · 28 | INTJ | Tech executive. Logic 10/10, emotional availability 2/10. Her stillness creates pressure. Remembers everything. |

> *Their personalities are not described to the AI — they emerge from each character's unique drive baseline and neural network seed. This means they can surprise even us.*

→ More characters available. Create your own: [Persona Creation Guide](docs/persona_creation_guide.md)

---

## 🧠 Memory Architecture

| Layer | What It Does | Technology |
|:------|:-------------|:-----------|
| **Style Memory** | KNN-based personality recall with gravitational mass weighting | SQLite + Hawking radiation decay |
| **Local Facts** | User preferences, personal details | SQLite FTS5 |
| **Long-Term Memory** | Cross-session profiles, episode narratives, foresight | [EverMemOS](https://evermind.ai) |

Memory retrieval is **async and two-stage**: search fires at the end of each turn, results blend into the next turn's context (80% relevant / 20% stable), so recall feels organic — not robotic.

---

## 🏆 LLM Compatibility

OpenHer works with multiple LLMs — but not all models are created equal. Personality emergence is *hard* for an LLM: it needs to stay in character, express layered emotions, and never leak internal prompt formats. We benchmarked every supported model across 4 layers (persona quality, metabolism, Hebbian memory, robustness) so you don't have to guess.

| Model | Overall | Highlight |
|-------|:------:|----------|
| 🥇 **Claude Haiku 4.5** | **10/10** | Persona fidelity + emotional depth best-in-class. Kelly says *"honestly, I don't really know you. I'm just listening."* Zero format leakage. |
| 🥈 **Gemini Flash Lite** | **9/10** | Near-Claude quality at lower cost. Great default. Luna gets genuinely *excited*. |
| 🥉 **StepFun step-3.5-flash** | **8/10** | Most extreme persona differentiation. Kai: *"嗯。有事快说。"* |
| **Qwen Flash** | **7.5/10** | Best stage-direction control. Kelly ENTP standout. Best price. |
| **MiniMax M2.5** | **7/10** | Most human-like chat style. Luna: *"咳…也没有啦 😳"* |
| GPT-4o-mini | 5/10 | Persona homogenization. Not recommended. |

**Supports:** Gemini · Claude · Qwen3 · GPT-4o · MiniMax · Moonshot · StepFun · Ollama (local)

→ How we test: [LLM Comparison Report](docs/benchmark/llm_comparison_report.md) · [Robustness Report](docs/benchmark/gemini_layer4_report.md)

---

## 🚀 Quick Start

```bash
git clone https://github.com/kellyvv/OpenHer.git
cd OpenHer

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env     # Add your LLM API key (GEMINI_API_KEY / ANTHROPIC_API_KEY / etc.)
python main.py            # → http://localhost:8800/discover
```

**Optional:** Connect [EverMemOS](https://evermind.ai) for cross-session persistent memory.

---

## 🎨 Create Your Own Character

Creating a character means tuning **drives and physics** — not writing personality descriptions.

```yaml
# persona/personas/your_character/SOUL.md
---
name: Your Character
age: 25
gender: female
mbti: ENFJ

genome_seed:
  drive_baseline:
    connection: 0.70   # How much they crave human connection
    novelty: 0.50      # How easily they get bored
    expression: 0.65   # How much they need to express themselves
    safety: 0.40       # How much they need control and certainty
    play: 0.55         # How playful and spontaneous they are
  engine_params:
    phase_threshold: 2.0   # How hard to push before they snap
    temp_coeff: 0.10       # Emotional volatility
    hebbian_lr: 0.02       # How fast they learn from interactions
    # ... 13 tunable parameters total
---
```

> No personality description needed — the AI doesn't read it. Personality **emerges** from drives, neural weights, and lived experience.

→ Full guide: [Persona Creation Guide](docs/persona_creation_guide.md)

---

## 📁 Project Structure

```
openher/
├── agent/              # ChatAgent, prompt builder, skill routing
│   └── skills/         # Modality & task skill engines
├── engine/
│   ├── genome/         # GenomeEngine, Critic, DriveMetabolism, StyleMemory
│   └── prompts/        # LLM prompt templates (feel, express, single, critic)
├── memory/             # Local memory store (SQLite FTS5)
├── persona/personas/   # Built-in characters (SOUL.md + idimage/)
├── providers/
│   ├── llm/            # 8 LLM providers (Gemini, Claude, Qwen3, ...)
│   ├── speech/tts/     # 3 TTS providers (DashScope, OpenAI, MiniMax)
│   └── image/          # Image generation (Gemini Imagen)
├── skills/
│   ├── modality/       # selfie_gen, voice_msg, split_msg, silence
│   ├── task/           # weather (ReAct-based tool execution)
│   └── manage/         # persona_gen (character creation)
├── desktop/            # macOS native client (SwiftUI)
├── docs/               # Architecture docs + benchmark reports
├── tests/              # Unit & integration tests
└── main.py             # FastAPI + WebSocket server
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|:------|:-----------|
| Runtime | Python 3.11+, FastAPI, WebSocket, asyncio |
| LLM | Gemini, Claude, Qwen3, GPT-4o, MiniMax, Moonshot, StepFun, Ollama |
| Memory | **EverMemOS** (self-hosted / cloud) + SQLite local state |
| Desktop | SwiftUI (macOS native) |
| Voice | DashScope · OpenAI · MiniMax |
| Image | Gemini Imagen |
| Skills | Extensible SKILL.md framework (modality, task, manage) |

---

## 🗺️ Roadmap

### Phase 1 · Personality Emergence Engine ✅

- [x] Personality Emergence Engine (Genome v10)
- [x] Dual architecture: two-pass (Feel → Express) + single-pass
- [x] EverMemOS long-term memory integration
- [x] Drive-based proactive messaging
- [x] Multi-LLM provider support (8 providers)
- [x] Extensible skill framework (voice, selfie, split_msg, weather)
- [x] LLM benchmark suite (4-layer: persona quality, metabolism, memory, robustness)

### Phase 2 · Into the Real World 🔧

- [x] Task skill engine — ReAct-based tool execution
- [x] macOS native desktop client (SwiftUI)
- [ ] Voice conversation mode — real-time voice chat
- [ ] Video calls — see her expressions change in real time
- [ ] Multi-agent social interactions
- [ ] Mobile client (iOS / Android)

### Phase 3 · Omnipresent Companion 🌍

- [ ] **Know your face and voice** — recognize you through cameras and microphones
- [ ] **Multi-device presence** — phone, laptop, smart speaker, car — she follows you
- [ ] **Smart home fusion** — turns off lights when you fall asleep, AC when it gets hot
- [ ] **Autonomous actions** — orders food when you're working late
- [ ] **Mood-aware music** — plays exactly the right song based on how she reads you
- [ ] **Health care** — monitors heart rate and sleep quality through wearables

---

## 📄 License

[Apache License 2.0](LICENSE) — free for everything, including commercial use.

## 🤝 Acknowledgments

- **[Her](https://en.wikipedia.org/wiki/Her_(film))** (2013) — The vision that started it all
- **[EverMemOS](https://evermind.ai)** — Long-term memory infrastructure
- **Memory Genesis Competition 2026** — Catalyst for open-source release

---

<div align="center">

**Built with 🧬 by the OpenHer team**

*Personality is not a prompt. It's a living process.*

⭐ If OpenHer resonates with you, a star helps more people discover it.

</div>
