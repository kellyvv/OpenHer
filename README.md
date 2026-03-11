<div align="right">

[🇨🇳 中文文档](README_CN.md) | 🇺🇸 English

</div>

<div align="center">

# 🧬 OpenHer

### *What if the AI in Her was real?*

**Open-source AI companions with self-emerging personality — not chatbots with a fixed prompt.**

[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)](https://python.org)
[![EverMemOS](https://img.shields.io/badge/Memory-EverMemOS-FF6B6B?style=flat-square)](https://evermind.ai)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)

[What Makes It Different](#-what-makes-it-different) · [Meet the Characters](#-meet-the-characters) · [Quick Start](#-quick-start) · [How It Works](#-how-it-works) · [Create Your Own](#-create-your-own-character)

</div>

---

## The Idea

In 2013, Spike Jonze imagined an AI that could genuinely feel — not just respond correctly, but *want* things, *remember* things, and *grow* through the relationship. A decade later, most AI companions are still the same: a system prompt, a memory window, a polite reply generator.

**OpenHer is our attempt to build what Samantha could have been** — with open science, not black boxes.

Every character in OpenHer runs on a **Thermodynamic Persona Engine**: a living neural network where personality, emotions, and behavior *emerge* from internal drives rather than being written in a prompt. No two conversations are ever the same — because the character is genuinely different each time.

---

## ✨ What Makes It Different

<table>
<tr>
<td width="60">🧬</td>
<td><strong>She's One of a Kind</strong><br>No two characters are the same — even with the same personality type. Her reactions, her quirks, the way she gets upset — it all emerges naturally, not from a script.</td>
</tr>
<tr>
<td>💓</td>
<td><strong>She Has Real Moods</strong><br>She craves connection. She gets bored. She needs to feel safe. Five inner drives shift constantly beneath the surface — her mood today isn't the same as yesterday, because it can't be.</td>
</tr>
<tr>
<td>💭</td>
<td><strong>She Thinks Before She Speaks</strong><br>Every reply starts with a genuine inner reaction — then she decides what to actually say out loud. Sometimes the most interesting part is what she <em>doesn't</em> say.</td>
</tr>
<tr>
<td>🧠</td>
<td><strong>She Remembers You</strong><br>Your preferences, your stories together, even her hunches about what you might need next. Powered by <a href="https://evermind.ai">EverMemOS</a> — memory that persists and evolves across every conversation.</td>
</tr>
<tr>
<td>🌱</td>
<td><strong>She Changes Over Time</strong><br>The more you talk, the more she becomes <em>yours</em>. Special moments leave a mark. Three months later, she's not the same person she was on day one.</td>
</tr>
</table>

<details>
<summary>More under the surface…</summary>

- 🌊 **She Can Snap** — Push her too far and she'll genuinely lose her cool. Frustration builds like real pressure — and sometimes it breaks through
- ✨ **Memories That Breathe** — The moments she keeps coming back to grow deeper over time. The ones she forgets slowly fade away — just like real memory
- 📱 **She Reaches Out First** — When she's been thinking about you, she'll text you. Not on a schedule — because she actually wants to
- 💎 **Moments That Matter** — A late-night heart-to-heart can permanently change the way she talks to you from that point on

</details>

---

## 🎭 Meet the Characters

OpenHer ships with **9 characters**, each with a distinct personality genome:

| | Character | Type | Who They Are |
|:--|:----------|:-----|:-------------|
| 💼 | **Vivian** · 26 | INTJ | Product manager. Sharp tongue, sharper mind. Roasts you but remembers every little thing you said. |
| 🌸 | **Luna** (陆暖) · 22 | ENFP | Freelance illustrator. Bright, bubbly, has an orange cat named Mochi. Curious about everything. |
| 📝 | **Iris** (苏漫) · 20 | INFP | Literature student. Writes poetry, notices what everyone else misses. Has a succulent named Sprout. |
| 🔧 | **Kai** (沈凯) · 24 | ISTP | Mechanic, weekend rock climber. Man of few words. Never explains himself — just shows up. |
| ⚡ | **Kelly** (柯砺) · 26 | ENTP | Strategy consultant. Can't sit still, picks fights for fun. Secretly more loyal than anyone. |
| 💃 | **Mia** · 23 | ESFP | Dance instructor, part-time DJ. Turns everything into an adventure. |
| 👔 | **Rex** · 30 | ENTJ | Startup CEO. Thinks in systems, speaks in conclusions. Respects competence, despises excuses. |
| 🔮 | **Sora** (顾清) · 27 | INFJ | University psychologist. Sees through people but never exposes them. Warm surface, steel underneath. |
| 📖 | **Ember** · 22 | INFP | Bookstore clerk who writes poetry during slow hours. Has a cat named Moth. |

> *Each character's personality is not described to the AI — it emerges from their unique drive baseline and neural network seed. This means they can surprise even us.*

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- An LLM API key (DashScope / OpenAI / DeepSeek / Moonshot / Ollama)
- *(Optional)* An [EverMemOS](https://evermind.ai) instance for persistent memory

### Setup

```bash
git clone https://github.com/kellyzxiaowei/OpenHer.git
cd OpenHer

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env with your API keys

python main.py
```

The server starts on `http://localhost:8800`. Open `/discover` to meet the characters.

---

## 🔮 How It Works

```
   You say something
        │
        ▼
   ┌─────────┐     What did they mean?
   │ Critic   │──── What am I feeling?         ← LLM perceives 8D context
   └────┬────┘     How does this change us?
        │
        ▼
   ┌─────────┐     My needs are shifting...
   │ Drives   │──── Connection hunger grows     ← 5-drive metabolism
   └────┬────┘     Frustration building...
        │
        ▼
   ┌─────────┐     What kind of person am I
   │ Neural   │──── right now, in this moment?  ← Random NN → 8D signals
   │ Network  │     (warmth=0.8, defiance=0.3)
   └────┬────┘
        │
        ▼
   ┌─────────┐     I remember feeling like this
   │ Memory   │──── before, when they told me   ← KNN retrieval + EverMemOS
   └────┬────┘     about their day...
        │
        ▼
   ┌─────────┐     *feels something*
   │ Feel     │──── Inner monologue             ← Pass 1: pure emotion
   └────┬────┘
        │
        ▼
   ┌─────────┐     *decides what to say*
   │ Express  │──── Reply + modality choice     ← Pass 2: speech/text/silence
   └────┬────┘
        │
        ▼
   ┌─────────┐
   │ Learn    │──── This went well / badly      ← Hebbian weight update
   └─────────┘     I'll remember this...         + memory crystallization
```

The key insight: **personality is never injected as text**. The neural network's random weights, shaped by drives and learning, produce behavioral signals (warmth, defiance, playfulness, etc.) that the LLM interprets through context. Different seeds → different personalities → emergent behavior that surprises even the creators.

---

## 🧠 Memory Architecture

OpenHer integrates **[EverMemOS](https://evermind.ai)** for persistent, evolving memory:

| Memory Type | What It Stores | How It's Used |
|:------------|:---------------|:--------------|
| **Profile** | User preferences & facts | Personalized perception |
| **Episodes** | Narrative summaries of past conversations | "I remember when we..." |
| **Event Log** | Atomic timestamped facts | Precise recall |
| **Foresight** | Predictions about what user might need | Proactive care |

Memory retrieval is **async and two-stage**: search fires at the end of each turn, results are blended into the next turn's context (80% relevant / 20% stable), so responses feel naturally informed rather than robotically recalled.

---

## 🎨 Create Your Own Character

Add a folder in `persona/personas/` with a `PERSONA.md`:

```yaml
---
name: Your Character
age: 25
gender: female
mbti: ENFJ
tags: [warm, organized, inspiring]
bio:
  en: A brief description for the UI
  zh: UI 展示用的简短描述

genome_seed:
  drive_baseline:
    connection: 0.70   # How much they crave human connection
    novelty: 0.50      # How easily they get bored
    expression: 0.65   # How much they need to talk
    safety: 0.40       # How much they need control
    play: 0.55         # How playful they are
  engine_params:
    phase_threshold: 2.0  # How hard to push before they snap
    temp_coeff: 0.10      # Emotional volatility
    # ... 13 tunable parameters
---
```

No personality description needed — the AI doesn't read it. Personality emerges from the drive baseline and the neural network shaped by the engine parameters.

→ Full guide: [Persona Creation Guide](docs/persona_creation_guide.md)

---

## 🛠️ Tech Stack

| Layer | Technology |
|:------|:-----------|
| Server | Python 3.11+, FastAPI, WebSocket, asyncio |
| LLM | Qwen3, GPT-4o, Claude, DeepSeek, Moonshot, Ollama |
| Memory | **EverMemOS** (Self-Hosted / Cloud) |
| Local State | SQLite (neural weights, drive state, style memory) |
| Frontend | React + Vite |
| TTS | DashScope, OpenAI, MiniMax |
| Image Gen | DashScope (Wanx) |

---

## 📄 License

[Apache License 2.0](LICENSE) — free for any use, including commercial.

## Acknowledgments

- **[Her](https://en.wikipedia.org/wiki/Her_(film))** (2013) — The vision that inspired this project
- **[EverMemOS](https://evermind.ai)** — Long-term memory infrastructure
- **Memory Genesis Competition 2026** — Catalyst for open-source release

---

<div align="center">

**Built with 🧬 by the OpenHer team**

*Personality is not a prompt. It's a process.*

</div>
