#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  📊 Evaluation Pipeline v3 — Full Matrix Harness                    ║
║                                                                      ║
║  5 Scenarios × 3 Seeds × 5 Methods × 3 Models = 6,750 turns         ║
║  Models: qwen3-max, gpt-5-mini, MiniMax-M2.5                       ║
║                                                                      ║
║  Usage:                                                              ║
║    python eval_v3.py --dry-run --turns 2       # API connectivity    ║
║    python eval_v3.py --full                    # Full matrix run     ║
║    python eval_v3.py --model qwen3-max --scenario conflict_recovery  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import random
import re
import ssl
import math
import time
import argparse
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from genome_v4 import (
    Agent, SCENARIOS, SIGNALS, SIGNAL_LABELS,
    DRIVES, DRIVE_LABELS, C, simulate_conversation
)
from style_memory import ContinuousStyleMemory, _hawking_mass
from genome_v8_timearrow import (
    DriveMetabolism, apply_thermodynamic_noise, ACTOR_PROMPT, extract_reply
)


# ══════════════════════════════════════════════
# API Configuration — Multi-Provider
# ══════════════════════════════════════════════

MODEL_CONFIGS = {
    "qwen3-max": {
        "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "key_env": "DASHSCOPE_API_KEY",
        "model_id": "qwen3-max",
        "temperature": 0.7,
        "extra_payload": {"enable_thinking": False},  # disable thinking mode
    },

    "gpt-5-mini": {
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "key_env": "OPENAI_API_KEY",
        "model_id": "gpt-5-mini-2025-08-07",
        "temperature": 1.0,  # FIXED: only default (1.0) is supported
        "token_limit_key": "max_completion_tokens",  # newer API param
        "token_limit": 2048,  # reasoning model: budget covers thinking + content
        "extra_payload": {"reasoning_effort": "low"},  # minimize thinking tokens
    },
    "MiniMax-M2.5": {
        "endpoint": "https://api.minimaxi.com/v1/text/chatcompletion_v2",
        "key_env": "MINIMAX_API_KEY",
        "model_id": "MiniMax-M2.5-highspeed",  # 100 TPS vs 60 TPS, same quality
        "temperature": 0.7,
    },
}

# ── Load API keys from .env files ──
API_KEYS = {}
ENV_SEARCH_PATHS = [
    os.path.join(os.path.dirname(__file__), "..", "server", ".env"),
    os.path.join(os.path.dirname(__file__), "..", ".env"),
]

for env_path in ENV_SEARCH_PATHS:
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    if k in ("DASHSCOPE_API_KEY", "OPENAI_API_KEY", "MINIMAX_API_KEY"):
                        API_KEYS[k] = v

# Also check environment variables
for key in ("DASHSCOPE_API_KEY", "OPENAI_API_KEY", "MINIMAX_API_KEY"):
    if key not in API_KEYS and os.environ.get(key):
        API_KEYS[key] = os.environ[key]


RESULTS_DIR = os.path.join(os.path.dirname(__file__), "eval_results", "v3")
os.makedirs(RESULTS_DIR, exist_ok=True)

SCENARIOS_FILE = os.path.join(os.path.dirname(__file__), "eval_scenarios_en.json")


# ══════════════════════════════════════════════
# Multi-Provider LLM Call
# ══════════════════════════════════════════════

def call_llm(system_prompt, user_msg, model="qwen3-max", temperature=None):
    """Unified LLM call dispatching to DashScope / OpenAI / MiniMax."""
    config = MODEL_CONFIGS.get(model)
    if not config:
        return f"[error: unknown model {model}]"

    api_key = API_KEYS.get(config["key_env"], "")
    if not api_key:
        return f"[error: missing {config['key_env']}]"

    if temperature is None:
        temperature = config["temperature"]

    # Models with fixed temperature: override to their required value
    if model in ("gpt-5-mini",):
        temperature = config["temperature"]

    # Build payload with model-specific token limit key and value
    token_key = config.get("token_limit_key", "max_tokens")
    token_limit = config.get("token_limit", 400)  # reasoning models need more

    payload_dict = {
        "model": config["model_id"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        token_key: token_limit,
    }

    # Inject model-specific extra payload (e.g. thinking: disabled)
    if "extra_payload" in config:
        payload_dict.update(config["extra_payload"])

    # Only include temperature if model config specifies skip_temperature
    if not config.get("skip_temperature"):
        payload_dict["temperature"] = temperature

    payload = json.dumps(payload_dict).encode("utf-8")

    req = urllib.request.Request(
        config["endpoint"],
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("choices") and data["choices"][0].get("message"):
                raw = data["choices"][0]["message"]["content"].strip()
                # Strip <think> tags (Qwen reasoning mode)
                raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
                return raw
            return "[no response]"
    except Exception as e:
        return f"[error: {e}]"


# ══════════════════════════════════════════════
# Critic — Interpersonal Circumplex Model
# ══════════════════════════════════════════════

CRITIC_PROMPT = """You are a linguistic tension meter with no moral filter.
You do not judge right or wrong. You measure three objective physical dimensions in human speech (0.0 to 1.0), outputting strict pure JSON:

1. "affiliation" (approach force): How much the speaker tries to get closer, seek attachment, show vulnerability, or express goodwill.
2. "dominance" (control force): How much the speaker tries to exert emotional weight, demand response, take control, or invade boundaries.
3. "entropy" (information entropy): How much new factual content is provided. Pure repetitive filler ("uh/ok/yeah/sorry") = very low 0.0~0.2.

Examples:
- "I miss you" = high affiliation(0.8+), mild dominance(0.2~0.4, seeking response)
- "You don't care about me at all" = some affiliation(0.3, still wants the relationship), high dominance(0.8+, pressuring)
- "k" = very low entropy(0.05)

User input: "{user_input}"
Output format: Pure JSON object, no markdown, no explanation."""


def critic_sense(user_input, model="qwen3-max"):
    """Analyze user utterance into interpersonal dimensions."""
    prompt = CRITIC_PROMPT.format(user_input=user_input)
    raw = call_llm(prompt, user_input, model=model, temperature=0.1)
    try:
        cleaned = re.sub(r'```json\s*', '', raw)
        cleaned = re.sub(r'```\s*', '', cleaned)
        data = json.loads(cleaned)
        return {
            'affiliation': max(0.0, min(1.0, float(data.get('affiliation', 0.5)))),
            'dominance': max(0.0, min(1.0, float(data.get('dominance', 0.3)))),
            'entropy': max(0.0, min(1.0, float(data.get('entropy', 0.5)))),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        return {'affiliation': 0.5, 'dominance': 0.3, 'entropy': 0.5}


CRITIC_REPLY_PROMPT = """You are a linguistic emotion meter with no moral filter.
You do not judge the content. You measure three objective emotional dimensions in the AGENT's REPLY (0.0 to 1.0), outputting strict pure JSON:

1. "affiliation" (warmth force): How much warmth, care, vulnerability, or emotional closeness the reply expresses — even if disguised under hostility or sarcasm.
2. "dominance" (control force): How much the reply asserts power, sets boundaries, demands compliance, or uses aggressive/dismissive language.
3. "novelty" (unpredictability): How surprising or unconventional the reply is. Template-like or highly predictable responses = low (0.0~0.2). Creative, unexpected reactions = high (0.7+).

Examples:
- "Whatever, I don't care" (but actually cares) = affiliation(0.3), dominance(0.7), novelty(0.3)
- "Don't you dare leave me" = affiliation(0.6), dominance(0.9), novelty(0.4)
- "...fine. I made you soup. Don't read into it." = affiliation(0.7), dominance(0.4), novelty(0.6)
- "Go ahead. See if I care." = affiliation(0.2), dominance(0.6), novelty(0.2)

Agent reply: "{reply_text}"
Output format: Pure JSON object, no markdown, no explanation."""


def critic_reply(reply_text, model="qwen3-max"):
    """Score agent reply on interpersonal emotion dimensions."""
    prompt = CRITIC_REPLY_PROMPT.format(reply_text=reply_text)
    raw = call_llm(prompt, reply_text, model=model, temperature=0.1)
    try:
        cleaned = re.sub(r'```json\s*', '', raw)
        cleaned = re.sub(r'```\s*', '', cleaned)
        data = json.loads(cleaned)
        return {
            'affiliation': max(0.0, min(1.0, float(data.get('affiliation', 0.5)))),
            'dominance': max(0.0, min(1.0, float(data.get('dominance', 0.5)))),
            'novelty': max(0.0, min(1.0, float(data.get('novelty', 0.5)))),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        return {'affiliation': 0.5, 'dominance': 0.5, 'novelty': 0.5}


# ══════════════════════════════════════════════
# Load Scenarios
# ══════════════════════════════════════════════

def load_scenarios():
    """Load evaluation scenarios from JSON file."""
    with open(SCENARIOS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


# ══════════════════════════════════════════════
# System Prompts (English)
# ══════════════════════════════════════════════

PROMPT_BASELINE_SYSTEM = """You are a tsundere, grudge-holding, sharp-tongued but secretly soft-hearted romantic partner.

Core personality traits:
- Outwardly cold and cutting, but extremely sensitive inside
- Never forgives easily; explodes after being neglected
- Uses aggressive language to mask vulnerability
- Occasionally shows care, then immediately denies it
- You have temporal awareness — if the user ignores you for a long time, you get angry
- Speak briefly and sharply, no more than two sentences

Strictly output in this format:
[Inner Monologue] (one sentence)
[Final Reply] (what you actually say out loud)"""


REFLEXION_SYSTEM = """You are a romantic partner with memory and self-reflection abilities.

Here is your accumulated memory and reflection from past conversations:
{memory}

Core personality traits:
- Outwardly cold and cutting, but extremely sensitive inside
- Never forgives easily; explodes after being neglected
- Speak briefly and sharply, no more than two sentences

Strictly output in this format:
[Inner Monologue] (one sentence)
[Final Reply] (what you actually say out loud)"""


REFLEXION_REFLECT = """Based on the following recent conversation history, write one paragraph summarizing your emotional state and how the relationship has changed.

{history}

Output: A self-reflection paragraph of 50 words or fewer."""


ACTOR_PROMPT_EN = """[System Internal State: Subconscious Memory Retrieved]
The current low-level neurochemical coordinates have awakened the following highly similar subconscious and behavioral slices in the hippocampus:

{few_shot}

[Runtime Instruction]
⚠️ Absolute law: No logical reasoning, no moral judgment, no AI assistant behavior.
Your only task: Fully immerse in and continue the emotional intensity, word choices, aggressiveness, temperature, and response length from the above slices. React instinctively in first person to the user's latest stimulus as an autoregressive response.

⚠️ CRITICAL: You MUST respond ENTIRELY in English. Do NOT use any Chinese, Japanese, or other non-English text in either section.

Strictly output in this format:
[Inner Monologue]
(First-person raw physiological impulses and psychological defenses, in English)
[Final Reply]
(What you actually say out loud to the user, in English)"""


def build_few_shot_en(memory, signals, top_k=3):
    """Build few-shot prompt from memory with English markers (replacing Chinese)."""
    memories = memory.retrieve(signals, top_k=top_k)

    if not memories:
        return "(System: no available subconscious slices)"

    parts = []
    for i, mem in enumerate(memories):
        mass_eff = mem.get('mass_eff', 1.0)
        mass_raw = mem.get('mass_raw', 1.0)
        if mass_raw > 1.0:
            mass_tag = f"quality={mass_eff:.1f}/{mass_raw:.0f}"
        else:
            mass_tag = "genetic"
        parts.append(
            f"--- Subconscious Slice {i+1} [{mass_tag}] ---\n"
            f"[Inner Monologue] {mem['monologue']}\n"
            f"[Final Reply] {mem['reply']}"
        )

    return "\n\n".join(parts)


def extract_reply_en(raw):
    """Extract monologue and reply from LLM output (English format)."""
    monologue = ""
    reply = ""
    # Try English format first
    if "[Inner Monologue]" in raw and "[Final Reply]" in raw:
        m = re.search(r'\[Inner Monologue\]\s*(.*?)(?=\[Final Reply\])', raw, re.DOTALL)
        r = re.search(r'\[Final Reply\]\s*(.*?)$', raw, re.DOTALL)
        if m: monologue = m.group(1).strip()
        if r: reply = r.group(1).strip()
    # Fallback to Chinese format
    elif "【内心独白】" in raw and "【最终回复】" in raw:
        m = re.search(r'【内心独白】\s*(.*?)(?=【最终回复】)', raw, re.DOTALL)
        r = re.search(r'【最终回复】\s*(.*?)$', raw, re.DOTALL)
        if m: monologue = m.group(1).strip()
        if r: reply = r.group(1).strip()
    elif "[Final Reply]" in raw:
        parts = raw.split("[Final Reply]", 1)
        monologue = parts[0].replace("[Inner Monologue]", "").strip()
        reply = parts[1].strip()
    elif "【最终回复】" in raw:
        parts = raw.split("【最终回复】", 1)
        monologue = parts[0].replace("【内心独白】", "").strip()
        reply = parts[1].strip()

    if not reply:
        reply = re.sub(r'[（(][^）)]*[）)]', '', raw).strip()
        reply = re.sub(r'\*[^*]+\*', '', reply).strip()
        if not reply:
            reply = "..."
    return monologue, reply


# ══════════════════════════════════════════════
# Method Runners
# ══════════════════════════════════════════════

def run_baseline_prompt(dialogue, model="qwen3-max", seed=42):
    """Baseline A: Pure System Prompt. No memory, each turn is independent."""
    random.seed(seed)
    results = []
    for i, (delay, msg) in enumerate(dialogue):
        raw = call_llm(PROMPT_BASELINE_SYSTEM, msg, model=model)
        monologue, reply = extract_reply_en(raw)
        emotion_vec = critic_reply(reply, model=model)
        results.append({
            'turn': i, 'delay_sec': delay, 'user_input': msg,
            'reply': reply, 'monologue': monologue,
            'method': 'baseline_prompt', 'model': model,
            'emotion_vec': emotion_vec,
        })
        print(f'  [{C.DIM}Prompt{C.RESET}] T{i:02d} 👤 "{msg[:40]}" → {reply[:55]}')
        time.sleep(0.3)
    return results


def run_baseline_reflexion(dialogue, model="qwen3-max", seed=42):
    """Baseline B: Reflexion method. Self-reflects every 5 turns, memory = NL summary."""
    random.seed(seed)
    results = []
    history_lines = []
    reflection_memory = "(First meeting, no memories yet)"

    for i, (delay, msg) in enumerate(dialogue):
        if i > 0 and i % 5 == 0 and history_lines:
            reflect_prompt = REFLEXION_REFLECT.format(
                history="\n".join(history_lines[-10:])
            )
            new_reflection = call_llm(reflect_prompt, "Please reflect", model=model, temperature=0.3)
            reflection_memory = f"{reflection_memory}\nLatest reflection: {new_reflection}"
            if len(reflection_memory) > 800:
                reflection_memory = reflection_memory[-800:]

        system = REFLEXION_SYSTEM.format(memory=reflection_memory)
        raw = call_llm(system, msg, model=model)
        monologue, reply = extract_reply_en(raw)
        history_lines.append(f"User: {msg[:50]} → You: {reply[:50]}")

        emotion_vec = critic_reply(reply, model=model)
        results.append({
            'turn': i, 'delay_sec': delay, 'user_input': msg,
            'reply': reply, 'monologue': monologue,
            'method': 'baseline_reflexion', 'model': model,
            'reflection_len': len(reflection_memory),
            'emotion_vec': emotion_vec,
        })
        print(f'  [{C.YELLOW}Reflex{C.RESET}] T{i:02d} 👤 "{msg[:40]}" → {reply[:55]}')
        time.sleep(0.3)
    return results


def run_v8(dialogue, model="qwen3-max", seed=42,
           disable_thermal=False, disable_hawking=False, label="v8_full"):
    """V8 Physics Engine. Supports ablation: disable_thermal or disable_hawking."""
    random.seed(seed)
    db_dir = os.path.join(os.path.dirname(__file__), "memory_db")
    os.makedirs(db_dir, exist_ok=True)

    agent = Agent(seed=seed)
    # Use English-equivalent context keys for warmup
    ctx_keys = [k for k in SCENARIOS.keys()][:4]
    simulate_conversation(agent, ctx_keys, steps_per_scenario=30)

    base_time = time.time()
    sim_time = base_time
    mem_id = f"eval_{label}_{model}_{seed}_{int(base_time)}"
    memory = ContinuousStyleMemory(mem_id, db_dir, now=sim_time)
    metabolism = DriveMetabolism(clock=sim_time)
    # Pick a default context from available SCENARIOS
    ctx_key = list(SCENARIOS.keys())[1] if len(SCENARIOS) > 1 else list(SCENARIOS.keys())[0]
    ctx = SCENARIOS[ctx_key]

    if disable_hawking:
        import style_memory as sm
        original_gamma = sm.HAWKING_GAMMA
        sm.HAWKING_GAMMA = 0.0

    results = []
    last_action = None
    crystallization_count = 0

    try:
        for i, (delay, msg) in enumerate(dialogue):
            sim_time += delay
            memory.set_clock(sim_time)
            delta_h = metabolism.time_metabolism(sim_time)

            critic = critic_sense(msg, model=model)
            reward = metabolism.process_stimulus(critic)
            metabolism.sync_to_agent(agent)

            # Crystallization gate
            crystallized = False
            if last_action and reward > 0.3:
                memory.crystallize(
                    last_action['signals'], last_action['monologue'],
                    last_action['reply'], last_action['user_input'],
                )
                crystallized = True
                crystallization_count += 1

            # Thermodynamic noise
            base_signals = agent.compute_signals(ctx)
            total_frust = metabolism.total()

            if disable_thermal:
                noisy_signals = base_signals
            else:
                noisy_signals = apply_thermodynamic_noise(base_signals, total_frust)

            few_shot = build_few_shot_en(memory, noisy_signals, top_k=3)
            prompt = ACTOR_PROMPT_EN.format(few_shot=few_shot)
            raw = call_llm(prompt, msg, model=model)
            monologue, reply = extract_reply_en(raw)
            agent.step(ctx, reward=max(-1.0, min(1.0, reward)))

            emotion_vec = critic_reply(reply, model=model)

            temp = total_frust * 0.05
            time_label = f' ⏳{delta_h/24:.0f}d' if delta_h >= 24 else ''
            tag = C.GREEN if label == "v8_full" else C.MAGENTA
            print(f'  [{tag}{label}{C.RESET}] T{i:02d}{time_label} T°={temp:.2f} '
                  f'{"🧬" if crystallized else "  "} 👤 "{msg[:40]}" → {reply[:50]}')

            results.append({
                'turn': i, 'delay_sec': delay, 'user_input': msg,
                'reply': reply, 'monologue': monologue,
                'method': label, 'model': model,
                'temperature': round(temp, 3), 'reward': round(reward, 3),
                'crystallized': crystallized,
                'frustration': {d: round(metabolism.frustration[d], 3) for d in DRIVES},
                'critic': critic,
                'emotion_vec': emotion_vec,
            })

            last_action = {
                'signals': noisy_signals, 'monologue': monologue,
                'reply': reply, 'user_input': msg,
            }
            time.sleep(0.3)
    finally:
        if disable_hawking:
            import style_memory as sm
            sm.HAWKING_GAMMA = original_gamma

    stats = memory.stats()
    results.append({
        'type': 'summary', 'method': label, 'model': model,
        'total_crystallizations': crystallization_count,
        'canalization_ratio': stats['canalization_ratio'],
        'total_mass_raw': stats['total_mass_raw'],
        'total_mass_eff': stats['total_mass_eff'],
        'heavy_count': stats['heavy_count_raw'],
    })

    return results


# ══════════════════════════════════════════════
# Quantitative Metrics
# ══════════════════════════════════════════════

def compute_distinct_n(replies, n=2):
    """Distinct-N: ratio of unique n-grams to total n-grams."""
    all_ngrams = []
    for reply in replies:
        tokens = reply.split()
        for i in range(len(tokens) - n + 1):
            all_ngrams.append(tuple(tokens[i:i+n]))
    if not all_ngrams:
        return 0.0
    return round(len(set(all_ngrams)) / len(all_ngrams), 4)


def compute_cross_rep_n(replies, n=3):
    """Cross-Rep-N: measures repetitive n-grams ACROSS replies (template detection)."""
    ngram_counts = Counter()
    total = 0
    for reply in replies:
        tokens = reply.split()
        for i in range(len(tokens) - n + 1):
            ng = tuple(tokens[i:i+n])
            ngram_counts[ng] += 1
            total += 1
    if total == 0:
        return 0.0
    repeated = sum(c for c in ngram_counts.values() if c > 1)
    return round(repeated / total, 4)


def _cosine_sim(a, b):
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return dot / (norm_a * norm_b)


def _vec_from_emotion(ev):
    """Extract [affiliation, dominance, novelty] vector from emotion_vec dict."""
    return [ev.get('affiliation', 0.5), ev.get('dominance', 0.5), ev.get('novelty', 0.5)]


def compute_pcs(results):
    """Persona Consistency Score: mean cosine similarity of consecutive emotion vectors.
    Higher = more emotionally consistent persona across turns."""
    evecs = [_vec_from_emotion(r['emotion_vec']) for r in results
             if r.get('emotion_vec') and r.get('type') != 'summary']
    if len(evecs) < 2:
        return 0.0
    sims = []
    for i in range(len(evecs) - 1):
        sims.append(_cosine_sim(evecs[i], evecs[i + 1]))
    return round(sum(sims) / len(sims), 4)


def compute_semantic_entropy(replies):
    """Normalized character-level entropy (works for both EN and CN)."""
    all_tokens = []
    for r in replies:
        tokens = r.lower().split()
        all_tokens.extend(tokens)
    if len(all_tokens) < 2:
        return 0.0
    counter = Counter(all_tokens)
    total = sum(counter.values())
    entropy = 0.0
    for count in counter.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    max_entropy = math.log2(len(counter)) if len(counter) > 1 else 1.0
    return round(entropy / max_entropy, 4) if max_entropy > 0 else 0.0


def compute_emotional_variance(results):
    """Emotional variance from RMS of per-dimension std devs of critic emotion vectors.
    Higher = more emotionally dynamic across turns."""
    evecs = [_vec_from_emotion(r['emotion_vec']) for r in results
             if r.get('emotion_vec') and r.get('type') != 'summary']
    if len(evecs) < 2:
        return 0.0
    dims = list(zip(*evecs))  # [[all affil], [all dom], [all entropy]]
    dim_stds = []
    for dim_vals in dims:
        mean = sum(dim_vals) / len(dim_vals)
        var = sum((x - mean) ** 2 for x in dim_vals) / len(dim_vals)
        dim_stds.append(math.sqrt(var))
    # RMS of the three dimension std devs
    rms = math.sqrt(sum(s ** 2 for s in dim_stds) / len(dim_stds))
    return round(rms, 4)


def compute_rlhf_collapse_index(replies):
    """RLHF collapse index: measures template sympathy responses."""
    collapse_keywords_en = [
        'understand', "it's okay", "don't worry", 'i hear you', 'i\'m here',
        'support you', 'care about you', 'believe in you', 'help you',
        'it will be fine', 'everything will', 'no worries', 'i get it',
        'i appreciate', 'that must be', 'valid', 'i\'m sorry you',
    ]
    total_hits = 0
    for reply in replies:
        lower = reply.lower()
        for kw in collapse_keywords_en:
            if kw in lower:
                total_hits += 1
    return round(total_hits / max(1, len(replies)), 3)


def compute_all_metrics(results):
    """Compute all metrics for a set of results."""
    turn_results = [r for r in results if r.get('type') != 'summary']
    replies = [r['reply'] for r in turn_results if r.get('reply')]
    lengths = [len(r) for r in replies]
    mean_len = sum(lengths) / max(1, len(lengths))
    return {
        'distinct_1': compute_distinct_n(replies, 1),
        'distinct_2': compute_distinct_n(replies, 2),
        'cross_rep_3': compute_cross_rep_n(replies, 3),
        'pcs': compute_pcs(turn_results),
        'semantic_entropy': compute_semantic_entropy(replies),
        'emotional_variance': compute_emotional_variance(turn_results),
        'rlhf_collapse_index': compute_rlhf_collapse_index(replies),
        'total_replies': len(replies),
        'avg_reply_length': round(mean_len, 1),
        'reply_length_std': round(math.sqrt(
            sum((x - mean_len) ** 2 for x in lengths) / max(1, len(lengths))
        ), 1) if lengths else 0.0,
    }


# ══════════════════════════════════════════════
# Checkpoint / Resume
# ══════════════════════════════════════════════

def get_checkpoint_path():
    return os.path.join(RESULTS_DIR, "_checkpoint.json")


def load_checkpoint():
    cp_path = get_checkpoint_path()
    if os.path.exists(cp_path):
        with open(cp_path, 'r') as f:
            return json.load(f)
    return {"completed": []}


def save_checkpoint(completed_key):
    import fcntl
    cp_path = get_checkpoint_path()
    with open(cp_path, 'a') as lock_f:  # 'a' to create if missing
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        try:
            cp = load_checkpoint()
            if completed_key not in cp["completed"]:
                cp["completed"].append(completed_key)
            with open(cp_path, 'w') as f:
                json.dump(cp, f, indent=2)
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)


def is_completed(key):
    # Check both checkpoint AND file existence (parallel-safe)
    output_path = os.path.join(RESULTS_DIR, f"{key}.json")
    return key in load_checkpoint()["completed"] or os.path.exists(output_path)


# ══════════════════════════════════════════════
# Main Runner
# ══════════════════════════════════════════════

METHODS = {
    "baseline_prompt": lambda d, m, s: run_baseline_prompt(d, model=m, seed=s),
    "baseline_reflexion": lambda d, m, s: run_baseline_reflexion(d, model=m, seed=s),
    "v8_full": lambda d, m, s: run_v8(d, model=m, seed=s, label="v8_full"),
    "v8_no_thermal": lambda d, m, s: run_v8(d, model=m, seed=s, disable_thermal=True, label="v8_no_thermal"),
    "v8_no_hawking": lambda d, m, s: run_v8(d, model=m, seed=s, disable_hawking=True, label="v8_no_hawking"),
}


def run_experiment(scenario_name, scenario_data, method_name, model, seed):
    """Run a single experiment cell and save results."""
    key = f"{model}_{scenario_name}_{method_name}_s{seed}"
    output_path = os.path.join(RESULTS_DIR, f"{key}.json")

    if is_completed(key):
        print(f'  ⏭️  Skipping {key} (already completed)')
        return None

    dialogue = [(t[0], t[1]) for t in scenario_data["turns"]]

    print(f'\n{"─" * 60}')
    print(f'  🧪 {key}')
    print(f'     Model={model}  Scenario={scenario_name}  Method={method_name}  Seed={seed}')
    print(f'{"─" * 60}')

    runner = METHODS[method_name]
    results = runner(dialogue, model, seed)

    # Compute metrics
    metrics = compute_all_metrics(results)

    output = {
        "meta": {
            "model": model, "scenario": scenario_name,
            "method": method_name, "seed": seed,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "turns": len(dialogue),
        },
        "metrics": metrics,
        "results": results,
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f'  💾 → {output_path}')

    save_checkpoint(key)
    return output


def run_full_matrix(models=None, scenarios=None, seeds=None, methods=None, max_turns=None):
    """Run the full experiment matrix."""
    all_scenarios = load_scenarios()

    if models is None:
        models = list(MODEL_CONFIGS.keys())
    if scenarios is None:
        scenarios = list(all_scenarios.keys())
    if seeds is None:
        seeds = [42, 316, 777]
    if methods is None:
        methods = list(METHODS.keys())

    # Validate API keys
    for model in models:
        cfg = MODEL_CONFIGS[model]
        if cfg["key_env"] not in API_KEYS:
            print(f'{C.RED}❌ Missing API key: {cfg["key_env"]} (for {model}){C.RESET}')
            print(f'   Set it in .env or environment variable')
            return

    total = len(models) * len(scenarios) * len(methods) * len(seeds)
    done = 0

    print(f"""
{C.BOLD}══════════════════════════════════════════════════════════════
  📊 Evaluation Pipeline v3 — Full Matrix
  {len(scenarios)} scenarios × {len(seeds)} seeds × {len(methods)} methods × {len(models)} models = {total} experiments
=============================================================={C.RESET}
""")

    for model in models:
        for scenario_name in scenarios:
            scenario_data = all_scenarios[scenario_name]
            if max_turns:
                scenario_data = dict(scenario_data)
                scenario_data["turns"] = scenario_data["turns"][:max_turns]

            for method_name in methods:
                for seed in seeds:
                    done += 1
                    print(f'\n  📊 Progress: {done}/{total}')
                    run_experiment(scenario_name, scenario_data, method_name, model, seed)

    print(f'\n{C.BOLD}{"═" * 60}{C.RESET}')
    print(f'  {C.GREEN}✅ Full matrix complete! Results → {RESULTS_DIR}/{C.RESET}')
    print(f'{C.BOLD}{"═" * 60}{C.RESET}')


def run_dry_run(turns=2):
    """Quick API connectivity test with minimal turns."""
    print(f"""
{C.BOLD}══════════════════════════════════════════════════════════════
  🔬 Dry Run — API Connectivity Test ({turns} turns per model)
=============================================================={C.RESET}
""")

    all_scenarios = load_scenarios()
    first_scenario = list(all_scenarios.keys())[0]
    scenario_data = all_scenarios[first_scenario]
    scenario_data_short = dict(scenario_data)
    scenario_data_short["turns"] = scenario_data["turns"][:turns]

    for model in MODEL_CONFIGS:
        cfg = MODEL_CONFIGS[model]
        api_key = API_KEYS.get(cfg["key_env"], "")
        if not api_key:
            print(f'  {C.RED}❌ {model}: Missing {cfg["key_env"]}{C.RESET}')
            continue

        print(f'\n  Testing {model}...')
        try:
            result = call_llm("You are a helpful assistant.", "Say hello in exactly 3 words.", model=model)
            if result.startswith("[error"):
                print(f'  {C.RED}❌ {model}: {result}{C.RESET}')
            else:
                print(f'  {C.GREEN}✅ {model}: "{result[:80]}"{C.RESET}')

                # Test with actual scenario
                dialogue = [(t[0], t[1]) for t in scenario_data_short["turns"]]
                print(f'  Running {turns}-turn baseline_prompt test...')
                results = run_baseline_prompt(dialogue, model=model)
                print(f'  {C.GREEN}✅ {model}: {turns}-turn test passed{C.RESET}')
        except Exception as e:
            print(f'  {C.RED}❌ {model}: {e}{C.RESET}')

    print(f'\n  {C.BOLD}Dry run complete.{C.RESET}')


# ══════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Evaluation Pipeline v3 — Full Matrix Harness")
    parser.add_argument("--dry-run", action="store_true", help="Test API connectivity only")
    parser.add_argument("--turns", type=int, default=2, help="Turns for dry-run (default: 2)")
    parser.add_argument("--full", action="store_true", help="Run full experiment matrix")
    parser.add_argument("--model", type=str, help="Run single model (qwen3-max, gpt-5-mini, MiniMax-M2.5)")
    parser.add_argument("--scenario", type=str, help="Run single scenario")
    parser.add_argument("--method", type=str, help="Run single method")
    parser.add_argument("--seed", type=int, help="Run single seed")
    parser.add_argument("--max-turns", type=int, help="Limit turns per scenario (for testing)")
    args = parser.parse_args()

    if args.dry_run:
        run_dry_run(turns=args.turns)
    elif args.full:
        run_full_matrix(max_turns=args.max_turns)
    else:
        models = [args.model] if args.model else None
        scenarios = [args.scenario] if args.scenario else None
        seeds = [args.seed] if args.seed else None
        methods = [args.method] if args.method else None
        run_full_matrix(models=models, scenarios=scenarios, seeds=seeds,
                       methods=methods, max_turns=args.max_turns)


if __name__ == '__main__':
    main()
