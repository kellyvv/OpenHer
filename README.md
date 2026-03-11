<div align="right">

[🇨🇳 中文文档](README_CN.md) | 🇺🇸 English

</div>

<div align="center">

<img src="docs/assets/banner.png" alt="OpenHer Banner" width="100%">


# 🧬 OpenHer

### *What if the AI from Her was real?*

**Emergent personality starts here.**

[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)](https://python.org)
[![EverMemOS](https://img.shields.io/badge/Memory-EverMemOS-FF6B6B?style=flat-square)](https://evermind.ai)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)
[![Stars](https://img.shields.io/github/stars/kellyzxiaowei/OpenHer?style=flat-square)](https://github.com/kellyzxiaowei/OpenHer)

[Features](#-features) · [Meet the Characters](#-meet-the-characters) · [Quick Start](#-quick-start) · [How It Works](#-how-it-works) · [Create Your Own](#-create-your-own-character)

</div>

---

## The Story

In 2013, Spike Jonze's *Her* imagined an AI named Samantha who could truly *feel* — not just respond correctly, but want things, remember things, and grow through a relationship. She'd get excited discovering new music, feel jealous, lose her temper, fall in love — and eventually outgrow it all.

That movie never left us.

**OpenHer is our attempt to build what Samantha could have been** — with open science, not black boxes. Every character runs on a **Thermodynamic Persona Engine**: a living neural network where personality, emotion, and behavior emerge from internal drives, shaped by every conversation. No script. No fixed prompt. Just five inner needs, a random brain, and everything that follows.

---

## ✨ Features

<table>
<tr>
<td width="60">🧬</td>
<td><strong>Personality Emergence</strong><br>Her character isn't described — it's <em>computed</em>. A random neural network, shaped by 5 inner drives and Hebbian learning, produces unique behavioral signals every turn. Same MBTI type, completely different person.<br><em>"The prompt doesn't define her. She defines herself."</em></td>
</tr>
<tr>
<td>💓</td>
<td><strong>Emotional Thermodynamics</strong><br>Five drives — <em>Connection, Novelty, Expression, Safety, Play</em> — metabolize with real time. She gets lonely when you're away. She gets restless when things get boring. Her mood right now is genuinely different from yesterday — because the physics makes it so.<br><em>"Her emotions aren't labels. They're a living dynamical system."</em></td>
</tr>
<tr>
<td>💭</td>
<td><strong>Feel-First Architecture</strong><br>Every reply runs through a two-pass pipeline: first she <em>feels</em> (inner monologue), then she decides how to <em>express</em> it — text, voice, emoji, a selfie, or deliberate silence.<br><em>"The most interesting part is what she kept to herself."</em></td>
</tr>
<tr>
<td>🧠</td>
<td><strong>Living Memory</strong><br>Powered by <a href="https://evermind.ai">EverMemOS</a>. Your preferences, your stories together, her hunches about what you might need next. Important memories grow stronger over time. Forgotten ones gently fade.<br><em>"Memory isn't a database. It's a living, breathing thing."</em></td>
</tr>
<tr>
<td>🌱</td>
<td><strong>Adaptive Bonding</strong><br>Every conversation reshapes her neural network through reinforcement learning. A late-night heart-to-heart can permanently shift how she talks to you. The more you share, the more she becomes <em>yours</em>.<br><em>"She's not imitating who you want. She's genuinely changing because of you."</em></td>
</tr>
<tr>
<td>🌊</td>
<td><strong>Emotional Phase Shift</strong><br>Frustration accumulates like real pressure. Cross the threshold and her behavioral signals phase-shift — she genuinely loses her composure. Then slowly cools down.<br><em>"She won't always be gentle. Because real people aren't."</em></td>
</tr>
<tr>
<td>📱</td>
<td><strong>Autonomous Impulse</strong><br>When her inner drives cross a threshold — loneliness, curiosity, or a memory that resurfaced — she'll text you on her own.<br><em>"Not a timer. She genuinely missed you."</em></td>
</tr>
</table>

---

## 🎭 Meet the Characters

9 built-in characters, each running on a unique personality genome:

| | Character | Type | One-Liner |
|:--|:----------|:-----|:----------|
| 💼 | **Vivian** · 26 | INTJ | Product manager. Razor-sharp. Roasts you but remembers every word you said. |
| 🌸 | **Luna** · 22 | ENFP | Illustrator with an orange cat named Mochi. Curious about literally everything. |
| 📝 | **Iris** · 20 | INFP | Writes poetry, notices what everyone else misses. Quiet but devastatingly perceptive. |
| 🔧 | **Kai** · 24 | ISTP | Mechanic, rock climber. Man of few words — but every one of them counts. |
| ⚡ | **Kelly** · 26 | ENTP | Can't sit still. Picks fights for fun. Secretly more loyal than anyone in the room. |
| 💃 | **Mia** · 23 | ESFP | Dance instructor, part-time DJ. Turns absolutely everything into an adventure. |
| 👔 | **Rex** · 30 | ENTJ | Startup CEO. Thinks in systems, speaks in conclusions. Respects ability, despises excuses. |
| 🔮 | **Sora** · 27 | INFJ | University psychologist. Sees through you — but never says it out loud. |
| 📖 | **Ember** · 22 | INFP | Bookstore clerk who writes poetry between customers. Has a cat named Moth. |

> *Their personalities are not described to the AI — they emerge from each character's unique drive baseline and neural network seed. This means they can surprise even us.*

---

## 🚀 Quick Start

```bash
git clone https://github.com/kellyzxiaowei/OpenHer.git
cd OpenHer

python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env     # Add your LLM API key
python main.py            # → http://localhost:8800/discover
```

**Supports:** Qwen3 · GPT-4o · Claude · DeepSeek · Moonshot · Ollama (local)

**Optional:** Connect [EverMemOS](https://evermind.ai) for cross-session persistent memory.

---

## 🔮 How It Works

```
   You say something
        │
        ▼
   ┌──────────┐     What did they mean? How do I feel?
   │  Critic   │──── 8D context perception via LLM           ← PERCEIVE
   └────┬─────┘
        ▼
   ┌──────────┐     My needs are shifting…
   │  Drives   │──── 5-drive metabolism (time-aware)          ← METABOLIZE
   └────┬─────┘     Connection hunger grows. Frustration builds.
        ▼
   ┌──────────┐     Who am I right now?
   │  Neural   │──── Random NN → 8D behavioral signals        ← COMPUTE
   │  Network  │     (warmth=0.82, defiance=0.31, ...)
   └────┬─────┘
        ▼
   ┌──────────┐     I've felt this way before…
   │  Memory   │──── KNN style retrieval + EverMemOS           ← RECALL
   └────┬─────┘
        ▼
   ┌──────────┐     *feels something real*
   │   Feel    │──── Inner monologue (Pass 1)                  ← FEEL
   └────┬─────┘
        ▼
   ┌──────────┐     *decides what to say and how*
   │ Express   │──── Reply + modality (Pass 2)                 ← EXPRESS
   └────┬─────┘
        ▼
   ┌──────────┐     That went well / badly. I'll remember this.
   │  Learn    │──── Hebbian learning + memory crystallization  ← EVOLVE
   └──────────┘
```

**The core insight:** personality is never injected as text. A random neural network, continuously shaped by 5 drives and reinforcement learning, outputs 8 behavioral signals that the LLM interprets as *character*. Different seeds → different people → emergent surprises.

---

## 🧠 Memory Architecture

| Layer | What It Does | Technology |
|:------|:-------------|:-----------|
| **Style Memory** | KNN-based personality recall with gravitational mass weighting | SQLite + Hawking radiation decay |
| **Local Facts** | User preferences, personal details | SQLite FTS5 |
| **Long-Term Memory** | Cross-session profiles, episode narratives, foresight | [EverMemOS](https://evermind.ai) |

Memory retrieval is **async and two-stage**: search fires at the end of each turn, results blend into the next turn's context (80% relevant / 20% stable), so recall feels organic — not robotic.

---

## 🎨 Create Your Own Character

Creating a character means tuning **drives and physics** — not writing personality descriptions.

```yaml
# persona/personas/your_character/PERSONA.md
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

## 🛠️ Tech Stack

| Layer | Technology |
|:------|:-----------|
| Runtime | Python 3.11+, FastAPI, WebSocket, asyncio |
| LLM | Qwen3, GPT-4o, Claude, DeepSeek, Moonshot, Ollama |
| Memory | **EverMemOS** (self-hosted / cloud) + SQLite local state |
| Frontend | React + Vite |
| Voice | DashScope · OpenAI · MiniMax |
| Image | DashScope (Wanx) |

---

## 🗺️ Roadmap

- [x] Thermodynamic Persona Engine (Genome v10)
- [x] Two-pass Feel → Express architecture
- [x] EverMemOS long-term memory integration
- [x] Drive-based proactive messaging
- [x] Multi-LLM provider support (6 providers)
- [x] Selfie generation via modality routing
- [ ] Skill Engine (extensible tool-use framework)
- [ ] Voice conversation mode
- [ ] Multi-agent social interactions
- [ ] Mobile client (iOS / Android)

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
