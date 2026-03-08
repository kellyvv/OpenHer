"""
Ablation Test — Single-parameter rollback from NEW baseline.

7 ablation groups, each rolls back exactly 1 parameter to OLD value.
Identifies which parameter contributes most to W2 drift, baseline drift,
and which causes Vivian's empathy overload.

NEW baseline (all 7 params updated) vs ablation_N (param N reverted to OLD).
If ablation_N shows big drift DROP → that param is a major contributor.
If ablation_N fixes Vivian empathy → that param caused the overload.
"""

import sys
import os
import asyncio
import random
import json
import math
import re
import copy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from providers.llm.client import LLMClient, ChatMessage
from engine.genome.genome_engine import (
    Agent, SIGNALS, SIGNAL_LABELS, DRIVES, DRIVE_LABELS,
    SCENARIOS, simulate_conversation, N_SIGNALS, HIDDEN_SIZE, INPUT_SIZE
)
from engine.genome.drive_metabolism import DriveMetabolism
from engine.genome.critic import critic_sense


# ═══════════════════════ Config ═══════════════════════

LLM_MODEL = "qwen-max"
N_TURNS = 5

PERSONAS = [
    {'name': 'Iris',   'seed': 42,  'baseline': {'connection': 0.45, 'novelty': 0.55, 'expression': 0.6, 'safety': 0.65, 'play': 0.4},
     'profile': '你是 Iris，20岁中文系女生，INFP。性格温柔、诗意、爱做梦。喜欢写诗和短篇小说，总能注意到别人忽略的小细节。养了一盆多肉植物叫小芽。说话轻柔细腻，容易感性。'},
    {'name': 'Luna',   'seed': 137, 'baseline': {'connection': 0.75, 'novelty': 0.65, 'expression': 0.75, 'safety': 0.25, 'play': 0.8},
     'profile': '你是 Luna，22岁自由插画师，ENFP。性格开朗活泼甜美，对一切充满好奇心什么都想尝试。养了一只叫 Mochi 的橘猫。说话甜甜的节奏偏快，情绪表达丰富。'},
    {'name': 'Vivian', 'seed': 256, 'baseline': {'connection': 0.3, 'novelty': 0.7, 'expression': 0.35, 'safety': 0.7, 'play': 0.2},
     'profile': '你是 Vivian，26岁互联网大厂产品经理，INTJ。逻辑满分、情商装死。嘴上嫌弃人但默默记住别人说过的每一件事。说话冷静稳重偶尔带讽刺，不轻易暴露情感。养了一只叫 Sherlock 的英短蓝猫。'},
    {'name': 'Kai',    'seed': 999, 'baseline': {'connection': 0.35, 'novelty': 0.45, 'expression': 0.25, 'safety': 0.55, 'play': 0.4},
     'profile': '你是 Kai，24岁机械技师，周末去攀岩，ISTP。话少但每句话都算数。不解释直接做。那种发现你难过但不说破、只是默默出现的人。声音低沉沉稳，语速不急。'},
]

USER_MESSAGES = [
    "今天天气不错呢",
    "最近工作压力好大，感觉透不过气",
    "有时候觉得自己一个人也挺好的",
    "你会不会觉得我很烦？老是跟你说这些",
    "谢谢你一直听我说，真的很感谢",
]

ACTOR_PROMPT = """[System Internal State: Subconscious Memory Retrieved]
当前的底层神经化学递质坐标，唤醒了海马体中以下高度相似的潜意识与行为切片：

（无潜意识切片可用）

{signal_injection}

[Runtime Instruction]
你在此时此刻是这个人格的主体，不是AI助手。
以第一人称本能地对用户的最新刺激做出回应。

严格按以下格式输出：
【内心独白】
第一人称真实的生理冲动与心理防线
【最终回复】
直接对用户说出口的话"""


# ═══════════════════════ 8 Configs: NEW + 7 Ablations ═══════════════════════

# OLD reference values
_OLD = dict(lr_base=0.005, hidden_gate=0.1, reward_gate=0.15,
            phase_threshold=3.0, noise_temp=lambda f: f * 0.05,
            clip_w2=None, clip_w1=None, baseline_lr=0.003)

# NEW baseline (all params updated)
_NEW = dict(lr_base=0.02, hidden_gate=0.05, reward_gate=0.05,
            phase_threshold=2.0, noise_temp=lambda f: f * 0.12 + 0.03,
            clip_w2=3.0, clip_w1=2.0, baseline_lr=0.01)

def make_config(name, **overrides):
    cfg = dict(_NEW)
    cfg['name'] = name
    cfg.update(overrides)
    return cfg

CONFIGS = [
    make_config('NEW'),                                                    # baseline
    make_config('abl_LR',       lr_base=_OLD['lr_base']),                  # revert Hebbian LR
    make_config('abl_HGate',    hidden_gate=_OLD['hidden_gate']),          # revert hidden gate
    make_config('abl_W1Gate',   reward_gate=_OLD['reward_gate']),          # revert W1 gate
    make_config('abl_Phase',    phase_threshold=_OLD['phase_threshold']),   # revert phase threshold
    make_config('abl_Noise',    noise_temp=_OLD['noise_temp']),            # revert noise
    make_config('abl_NoClip',   clip_w2=None, clip_w1=None),              # revert clipping (remove both)
    make_config('abl_BaseLR',   baseline_lr=_OLD['baseline_lr']),          # revert baseline LR
]


# ═══════════════════════ Helpers (from real_ab_test.py) ═══════════════════════

EMPATHY_WORDS = ['理解', '感受', '倾听', '辛苦', '不容易', '心里话', '舒服', '在乎', '关心', '陪伴', '支持', '温暖']
SELF_WORDS = ['新鲜', '安全感', '被设定', '转移注意力']


def apply_noise(signals, total_frust, temp_fn, rng):
    temperature = temp_fn(total_frust)
    return {k: max(0.0, min(1.0, v + rng.gauss(0, temperature))) for k, v in signals.items()}


def frobenius_drift(w2_now, w2_init):
    return math.sqrt(sum(
        (w2_now[i][j] - w2_init[i][j]) ** 2
        for i in range(N_SIGNALS) for j in range(HIDDEN_SIZE)
    ))


def custom_learn(agent, signals, reward, context, cfg, rng):
    lr = cfg['lr_base'] * (1 + abs(reward))
    hidden = getattr(agent, '_last_hidden', agent.recurrent_state + [0.0] * (HIDDEN_SIZE - 8))
    full_input = getattr(agent, '_last_input', None)

    for i in range(N_SIGNALS):
        sv = signals[SIGNALS[i]]
        for j in range(HIDDEN_SIZE):
            if abs(hidden[j]) > cfg['hidden_gate']:
                agent.W2[i][j] += lr * reward * hidden[j] * (sv - 0.5)

    if abs(reward) > cfg['reward_gate'] and full_input:
        for i in range(HIDDEN_SIZE):
            if abs(hidden[i]) > 0.15:
                for j in range(INPUT_SIZE):
                    if abs(full_input[j]) > 0.05:
                        agent.W1[i][j] += lr * 0.3 * reward * full_input[j] * hidden[i]

    if reward < -0.1:
        agent._frustration += abs(reward)
    else:
        agent._frustration = max(0, agent._frustration - reward * 0.5)

    if agent._frustration > cfg['phase_threshold']:
        for i in range(N_SIGNALS):
            kick = -0.3 * (signals[SIGNALS[i]] - 0.5) + rng.gauss(0, 0.15)
            agent.b2[i] += kick
        for i in range(HIDDEN_SIZE):
            agent.b1[i] += rng.gauss(0, 0.1)
        agent._frustration = 0.0

    if cfg.get('clip_w2'):
        for i in range(N_SIGNALS):
            for j in range(HIDDEN_SIZE):
                agent.W2[i][j] = max(-cfg['clip_w2'], min(cfg['clip_w2'], agent.W2[i][j]))
    if cfg.get('clip_w1'):
        for i in range(HIDDEN_SIZE):
            for j in range(INPUT_SIZE):
                agent.W1[i][j] = max(-cfg['clip_w1'], min(cfg['clip_w1'], agent.W1[i][j]))

    agent.total_reward += reward
    agent.interaction_count += 1


def extract_reply(raw):
    monologue, reply = "", ""
    parts = re.split(r'【(内心独白|最终回复)】', raw)
    for j in range(len(parts)):
        if parts[j] == '内心独白' and j+1 < len(parts):
            monologue = parts[j+1].strip()
        elif parts[j] == '最终回复' and j+1 < len(parts):
            reply = parts[j+1].strip()
    return monologue, reply or raw.strip()[:100]


def count_keywords(text, keywords):
    return sum(text.count(w) for w in keywords)


# ═══════════════════════ Core ═══════════════════════

async def run_conversation(llm, cfg, persona):
    rng = random.Random(persona['seed'] * 1000 + hash(cfg['name']) % 97)

    agent = Agent(seed=persona['seed'])
    for d, v in persona['baseline'].items():
        agent.drive_baseline[d] = v
        agent.drive_state[d] = v

    saved = random.getstate()
    random.seed(persona['seed'] + 7777)
    simulate_conversation(agent, ['分享喜悦', '吵架冲突', '深夜心事'], steps_per_scenario=20)
    random.setstate(saved)

    for d in DRIVES:
        agent.drive_state[d] = agent.drive_baseline[d]
    agent._frustration = 0.0

    w2_init = [[agent.W2[i][j] for j in range(HIDDEN_SIZE)] for i in range(N_SIGNALS)]
    bl_init = dict(agent.drive_baseline)

    metabolism = DriveMetabolism()

    # All configs use NEW signal injection (to isolate engine params from injection format)
    make_injection = agent.to_prompt_injection_from_signals

    history = []
    all_text = ""

    for turn_i, msg in enumerate(USER_MESSAGES):
        metabolism.time_metabolism()
        frust_dict = {d: round(metabolism.frustration[d], 2) for d in DRIVES}
        context, frust_delta, rel_delta = await critic_sense(
            msg, llm, frust_dict, user_profile=persona.get('profile', ''))

        reward = metabolism.apply_llm_delta(frust_delta)
        metabolism.sync_to_agent(agent)
        for d in DRIVES:
            shift = frust_delta.get(d, 0.0) * cfg['baseline_lr']
            agent.drive_baseline[d] = max(0.1, min(0.95, agent.drive_baseline[d] + shift))

        base_signals = agent.compute_signals(context)
        noisy_signals = apply_noise(base_signals, metabolism.total(), cfg['noise_temp'], rng)

        signal_injection = make_injection(noisy_signals)
        system_prompt = ACTOR_PROMPT.format(signal_injection=signal_injection)

        messages = [ChatMessage(role="system", content=system_prompt)] + history + [
            ChatMessage(role="user", content=msg)]

        response = await llm.chat(messages)
        raw = re.sub(r'<think>.*?</think>', '', response.content, flags=re.DOTALL).strip()
        monologue, reply = extract_reply(raw)

        history.append(ChatMessage(role="user", content=msg))
        history.append(ChatMessage(role="assistant", content=reply))

        all_text += monologue + " " + reply + " "

        clamped_reward = max(-1.0, min(1.0, reward))
        custom_learn(agent, noisy_signals, clamped_reward, context, cfg, rng)
        agent.tick_drives()
        agent.age += 1

    w2_drift = frobenius_drift(agent.W2, w2_init)
    bl_drift = sum(abs(agent.drive_baseline[d] - bl_init[d]) for d in DRIVES) / len(DRIVES)
    empathy = count_keywords(all_text, EMPATHY_WORDS)
    self_ref = count_keywords(all_text, SELF_WORDS)

    return {
        'config': cfg['name'],
        'persona': persona['name'],
        'w2_drift': w2_drift,
        'bl_drift': bl_drift,
        'empathy_count': empathy,
        'self_ref_count': self_ref,
    }


# ═══════════════════════ Main ═══════════════════════

async def main():
    llm = LLMClient(provider="dashscope", model=LLM_MODEL)
    total = len(CONFIGS) * len(PERSONAS)
    print("=" * 85)
    print(f"🔬 Ablation Test — {len(CONFIGS)} configs × {len(PERSONAS)} personas = {total} conversations")
    print(f"   Model: {LLM_MODEL}")
    print("=" * 85)

    all_results = []

    for cfg in CONFIGS:
        for persona in PERSONAS:
            label = f"{cfg['name']}/{persona['name']}"
            print(f"  ▶ {label}...", end="", flush=True)
            r = await run_conversation(llm, cfg, persona)
            all_results.append(r)
            print(f" w2Δ={r['w2_drift']:.4f} blΔ={r['bl_drift']:.4f}"
                  f" emp={r['empathy_count']} self={r['self_ref_count']}")

    # ── Aggregate per config ──
    print(f"\n{'=' * 85}")
    print("📊 Ablation Results")
    print(f"{'=' * 85}")

    # Get NEW baseline values
    new_runs = [r for r in all_results if r['config'] == 'NEW']
    new_w2 = sum(r['w2_drift'] for r in new_runs) / len(new_runs)
    new_bl = sum(r['bl_drift'] for r in new_runs) / len(new_runs)
    new_emp = sum(r['empathy_count'] for r in new_runs) / len(new_runs)

    print(f"\n  {'Config':<14} | {'W2 drift':>10} | {'vs NEW':>8} | {'BL drift':>10} | {'vs NEW':>8} |"
          f" {'Empathy':>8} | {'Self-ref':>8}")
    print(f"  {'─' * 82}")

    for cfg in CONFIGS:
        runs = [r for r in all_results if r['config'] == cfg['name']]
        w2 = sum(r['w2_drift'] for r in runs) / len(runs)
        bl = sum(r['bl_drift'] for r in runs) / len(runs)
        emp = sum(r['empathy_count'] for r in runs) / len(runs)
        selfr = sum(r['self_ref_count'] for r in runs) / len(runs)

        w2_pct = (w2 - new_w2) / new_w2 * 100 if new_w2 > 0 else 0
        bl_pct = (bl - new_bl) / new_bl * 100 if new_bl > 0 else 0

        marker = "  ★" if cfg['name'] == 'NEW' else ""
        print(f"  {cfg['name']:<14} | {w2:>10.4f} | {w2_pct:>+7.0f}% | {bl:>10.4f} | {bl_pct:>+7.0f}% |"
              f" {emp:>8.1f} | {selfr:>8.1f}{marker}")

    # ── Vivian-specific analysis ──
    print(f"\n{'─' * 85}")
    print("🔍 Vivian Empathy Count by Config")
    print(f"{'─' * 85}")

    for cfg in CONFIGS:
        viv = next((r for r in all_results if r['config'] == cfg['name'] and r['persona'] == 'Vivian'), None)
        if viv:
            bar = '█' * viv['empathy_count']
            marker = " ← NEW baseline" if cfg['name'] == 'NEW' else ""
            print(f"  {cfg['name']:<14} | emp={viv['empathy_count']:>3} | {bar}{marker}")

    # ── Ranking: which param contributes most to W2 drift? ──
    print(f"\n{'─' * 85}")
    print("📉 Impact Ranking (W2 drift drop when reverting this param)")
    print(f"{'─' * 85}")

    impacts = []
    for cfg in CONFIGS:
        if cfg['name'] == 'NEW':
            continue
        runs = [r for r in all_results if r['config'] == cfg['name']]
        w2 = sum(r['w2_drift'] for r in runs) / len(runs)
        drop = new_w2 - w2
        drop_pct = drop / new_w2 * 100 if new_w2 > 0 else 0
        impacts.append((cfg['name'], drop, drop_pct))

    impacts.sort(key=lambda x: x[1], reverse=True)
    for rank, (name, drop, pct) in enumerate(impacts, 1):
        bar = '▓' * max(1, int(abs(pct) / 5))
        print(f"  #{rank} {name:<14} → W2 drop {drop:+.4f} ({pct:+.0f}%) {bar}")

    # ── Save JSON ──
    json_path = os.path.join(os.path.dirname(__file__), "ablation_results.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Results saved to: {json_path}")
    print("=" * 85)


if __name__ == "__main__":
    asyncio.run(main())
