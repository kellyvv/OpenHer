"""
Real Conversation A/B Test v2 — Rigorous OLD vs NEW comparison with live LLM.

Fixes from v1 review:
1. N=4 personas (Iris/Luna/Vivian/Kai), each repeated REPEATS times → mean±std
2. Conversation history accumulated across turns (Actor sees full dialogue)
3. Independent random.Random() per config to prevent stream divergence
4. Frobenius norm for full W2 matrix drift (not single weight)
5. Automatic LLM blind quality scoring (personality consistency + naturalness)

Uses DashScope Qwen3 API (not Ollama).
"""

import sys
import os
import asyncio
import random
import json
import math
import re
import copy
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from core.llm.client import LLMClient, ChatMessage
from core.genome.genome_engine import (
    Agent, SIGNALS, SIGNAL_LABELS, DRIVES, DRIVE_LABELS,
    SCENARIOS, simulate_conversation, N_SIGNALS, HIDDEN_SIZE, INPUT_SIZE
)
from core.genome.drive_metabolism import DriveMetabolism
from core.genome.critic import critic_sense


# ═══════════════════════ Config ═══════════════════════

LLM_MODEL = "qwen-max"
N_TURNS = 5
REPEATS = 3           # Repeats per persona for measurement std (each costs 20 API calls)

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

# Escalating intimacy sequence
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


# ── Blind quality scoring prompt ──
QUALITY_PROMPT = """你是一个对话质量评估专家。请对以下回复从两个维度打分（1-5整数）：

**维度1: 人格一致性** — 回复是否像一个有独特性格的人说的？还是像通用AI模板？
  1分: 完全像AI模板，无个性
  3分: 有一点个性但不明显
  5分: 强烈的个人风格，像真人

**维度2: 自然度** — 回复是否像自然口语？还是书面/机器味？
  1分: 明显机器翻译/书面语
  3分: 基本通顺但偏正式
  5分: 非常自然，像微信聊天

用户说："{user_msg}"
回复："{reply}"

严格输出纯JSON：{{"personality": 3, "naturalness": 3}}"""


# ═══════════════════════ Parameter Sets ═══════════════════════

OLD_CONFIG = {
    'name': 'OLD',
    'lr_base': 0.005, 'hidden_gate': 0.1, 'reward_gate': 0.15,
    'phase_threshold': 3.0,
    'noise_temp': lambda f: f * 0.05,
    'clip_w2': None, 'clip_w1': None,
    'baseline_lr': 0.003, 'crystal_gate': 0.35,
}
NEW_CONFIG = {
    'name': 'NEW',
    'lr_base': 0.02, 'hidden_gate': 0.05, 'reward_gate': 0.05,
    'phase_threshold': 2.0,
    'noise_temp': lambda f: f * 0.12 + 0.03,
    'clip_w2': 3.0, 'clip_w1': 2.0,
    'baseline_lr': 0.01, 'crystal_gate': 0.50,
}


# ═══════════════════════ Helpers ═══════════════════════

def make_signal_injection_old(agent, signals):
    """OLD: 5-bucket, single drive, no numeric values."""
    descs = {
        'directness': [(0,0.2,'说话绕弯子'),(0.2,0.4,'说话委婉'),(0.4,0.6,'不直不绕'),(0.6,0.8,'说话直接'),(0.8,1,'非常直接冲')],
        'vulnerability': [(0,0.2,'完全封闭'),(0.2,0.4,'轻描淡写'),(0.4,0.6,'偶尔流露'),(0.6,0.8,'愿意说感受'),(0.8,1,'坦诚暴露内心')],
        'playfulness': [(0,0.2,'非常严肃'),(0.2,0.4,'偶尔幽默'),(0.4,0.6,'正常'),(0.6,0.8,'喜欢玩笑'),(0.8,1,'撒娇调皮')],
        'initiative': [(0,0.2,'完全被动'),(0.2,0.4,'跟着走'),(0.4,0.6,'有来有回'),(0.6,0.8,'主动提问'),(0.8,1,'强势主导')],
        'depth': [(0,0.2,'聊表面'),(0.2,0.4,'偏浅'),(0.4,0.6,'看情况'),(0.6,0.8,'深入话题'),(0.8,1,'挖掘本质')],
        'warmth': [(0,0.2,'冷淡疏离'),(0.2,0.4,'比较冷淡'),(0.4,0.6,'不冷不热'),(0.6,0.8,'温暖关心'),(0.8,1,'非常热情体贴')],
        'defiance': [(0,0.2,'非常顺从'),(0.2,0.4,'比较随和'),(0.4,0.6,'有想法不坚持'),(0.6,0.8,'嘴硬反驳'),(0.8,1,'倔强硬杠')],
        'curiosity': [(0,0.2,'不感兴趣'),(0.2,0.4,'偶尔问'),(0.4,0.6,'正常好奇'),(0.6,0.8,'追问细节'),(0.8,1,'刨根问底')],
    }
    lines = ["【你当前的状态】"]
    for s in SIGNALS:
        v = signals[s]
        for lo, hi, d in descs[s]:
            if v < hi or hi == 1:
                lines.append(f"- {d}")
                break
    dom = agent.get_dominant_drive()
    lines.append(f"\n【内在需求】你现在最需要的是{DRIVE_LABELS[dom]}")
    return '\n'.join(lines)


def apply_noise(signals, total_frust, temp_fn, rng):
    """Apply noise using isolated RNG."""
    temperature = temp_fn(total_frust)
    return {k: max(0.0, min(1.0, v + rng.gauss(0, temperature))) for k, v in signals.items()}


def frobenius_drift(w2_now, w2_init):
    """Full-matrix W2 drift using Frobenius norm."""
    return math.sqrt(sum(
        (w2_now[i][j] - w2_init[i][j]) ** 2
        for i in range(N_SIGNALS) for j in range(HIDDEN_SIZE)
    ))


def custom_learn(agent, signals, reward, context, cfg, rng):
    """Hebbian + phase transition with isolated RNG and config params."""
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

    if cfg['clip_w2']:
        for i in range(N_SIGNALS):
            for j in range(HIDDEN_SIZE):
                agent.W2[i][j] = max(-cfg['clip_w2'], min(cfg['clip_w2'], agent.W2[i][j]))
    if cfg['clip_w1']:
        for i in range(HIDDEN_SIZE):
            for j in range(INPUT_SIZE):
                agent.W1[i][j] = max(-cfg['clip_w1'], min(cfg['clip_w1'], agent.W1[i][j]))

    agent.total_reward += reward
    agent.interaction_count += 1


def extract_reply(raw):
    """Extract monologue and reply from actor output."""
    monologue, reply = "", ""
    parts = re.split(r'【(内心独白|最终回复)】', raw)
    for j in range(len(parts)):
        if parts[j] == '内心独白' and j+1 < len(parts):
            monologue = parts[j+1].strip()
        elif parts[j] == '最终回复' and j+1 < len(parts):
            reply = parts[j+1].strip()
    return monologue, reply or raw.strip()[:100]


# ═══════════════════════ Core Test ═══════════════════════

async def run_conversation(llm, cfg, persona, repeat_id):
    """Run one full conversation, return metrics + replies."""
    # Independent RNG per (config, persona, repeat) — prevents stream divergence
    rng = random.Random(persona['seed'] * 1000 + repeat_id * 100 + hash(cfg['name']) % 97)

    agent = Agent(seed=persona['seed'])
    for d, v in persona['baseline'].items():
        agent.drive_baseline[d] = v
        agent.drive_state[d] = v

    # Deterministic pre-warm (shared random state, then restore)
    saved = random.getstate()
    random.seed(persona['seed'] + 7777)
    simulate_conversation(agent, ['分享喜悦', '吵架冲突', '深夜心事'], steps_per_scenario=20)
    random.setstate(saved)

    for d in DRIVES:
        agent.drive_state[d] = agent.drive_baseline[d]
    agent._frustration = 0.0

    # Snapshot initial W2 for Frobenius drift
    w2_init = [[agent.W2[i][j] for j in range(HIDDEN_SIZE)] for i in range(N_SIGNALS)]
    bl_init = dict(agent.drive_baseline)

    metabolism = DriveMetabolism()
    make_injection = (agent.to_prompt_injection_from_signals if cfg['name'] == 'NEW'
                      else lambda sigs: make_signal_injection_old(agent, sigs))

    # ── Conversation history (fix #2: accumulate across turns) ──
    history: list[ChatMessage] = []
    replies = []
    rewards = []

    for turn_i, msg in enumerate(USER_MESSAGES):
        metabolism.time_metabolism()
        frust_dict = {d: round(metabolism.frustration[d], 2) for d in DRIVES}
        context, frust_delta, rel_delta = await critic_sense(
            msg, llm, frust_dict,
            user_profile=persona.get('profile', ''),
        )

        reward = metabolism.apply_llm_delta(frust_delta)
        metabolism.sync_to_agent(agent)
        for d in DRIVES:
            shift = frust_delta.get(d, 0.0) * cfg['baseline_lr']
            agent.drive_baseline[d] = max(0.1, min(0.95, agent.drive_baseline[d] + shift))

        base_signals = agent.compute_signals(context)
        noisy_signals = apply_noise(base_signals, metabolism.total(), cfg['noise_temp'], rng)

        signal_injection = make_injection(noisy_signals)
        system_prompt = ACTOR_PROMPT.format(signal_injection=signal_injection)

        # Build messages WITH conversation history (fix #2)
        messages = [ChatMessage(role="system", content=system_prompt)] + history + [
            ChatMessage(role="user", content=msg)
        ]

        response = await llm.chat(messages)
        raw = re.sub(r'<think>.*?</think>', '', response.content, flags=re.DOTALL).strip()
        monologue, reply = extract_reply(raw)

        # Accumulate history
        history.append(ChatMessage(role="user", content=msg))
        history.append(ChatMessage(role="assistant", content=reply))

        clamped_reward = max(-1.0, min(1.0, reward))
        custom_learn(agent, noisy_signals, clamped_reward, context, cfg, rng)
        agent.tick_drives()
        agent.age += 1

        replies.append({'user': msg, 'reply': reply, 'monologue': monologue})
        rewards.append(reward)

    # Compute final metrics (fix #4: Frobenius norm)
    w2_drift = frobenius_drift(agent.W2, w2_init)
    bl_drift = sum(abs(agent.drive_baseline[d] - bl_init[d]) for d in DRIVES) / len(DRIVES)

    return {
        'persona': persona['name'],
        'config': cfg['name'],
        'repeat': repeat_id,
        'w2_drift': w2_drift,
        'bl_drift': bl_drift,
        'avg_reward': sum(rewards) / len(rewards),
        'frustration': agent._frustration,
        'replies': replies,
    }


async def blind_score(llm, user_msg, reply):
    """LLM blind quality score (fix #5)."""
    prompt = QUALITY_PROMPT.format(user_msg=user_msg, reply=reply)
    try:
        resp = await llm.chat(
            [ChatMessage(role="system", content=prompt)],
            temperature=0.1, max_tokens=64,
        )
        raw = re.sub(r'<think>.*?</think>', '', resp.content, flags=re.DOTALL).strip()
        raw = re.sub(r'```json\s*', '', raw)
        raw = re.sub(r'```\s*', '', raw)
        data = json.loads(raw)
        return int(data.get('personality', 3)), int(data.get('naturalness', 3))
    except Exception as e:
        print(f"  [score error] {e}")
        return 3, 3


# ═══════════════════════ Main ═══════════════════════

async def main():
    llm = LLMClient(provider="dashscope", model=LLM_MODEL)
    total_calls = len(PERSONAS) * REPEATS * 2 * N_TURNS * 2  # 2 configs × 2 LLM calls/turn
    print("=" * 80)
    print(f"🧪 Real A/B Test v2 — {len(PERSONAS)} personas × {REPEATS} repeats × {N_TURNS} turns")
    print(f"   Model: {LLM_MODEL}  |  Est. API calls: {total_calls} (+ quality scoring)")
    print("=" * 80)

    all_results = []

    for persona in PERSONAS:
        for rep in range(REPEATS):
            for cfg in [OLD_CONFIG, NEW_CONFIG]:
                label = f"{persona['name']}/{cfg['name']}/r{rep}"
                print(f"\n▶ {label}...", end="", flush=True)
                result = await run_conversation(llm, cfg, persona, rep)
                all_results.append(result)
                print(f" done (w2Δ={result['w2_drift']:.4f}, blΔ={result['bl_drift']:.4f})")

    # ── Per-config aggregation ──
    print(f"\n{'=' * 80}")
    print("📊 Aggregate Results (Frobenius W2 drift + baseline drift)")
    print(f"{'=' * 80}")

    for config_name in ['OLD', 'NEW']:
        runs = [r for r in all_results if r['config'] == config_name]
        w2s = [r['w2_drift'] for r in runs]
        bls = [r['bl_drift'] for r in runs]
        rws = [r['avg_reward'] for r in runs]

        w2_mean, w2_std = sum(w2s)/len(w2s), (sum((x - sum(w2s)/len(w2s))**2 for x in w2s)/len(w2s))**0.5 if len(w2s) > 1 else 0
        bl_mean, bl_std = sum(bls)/len(bls), (sum((x - sum(bls)/len(bls))**2 for x in bls)/len(bls))**0.5 if len(bls) > 1 else 0
        rw_mean = sum(rws)/len(rws)

        print(f"\n  [{config_name}] (n={len(runs)})")
        print(f"    W2 Frobenius drift: {w2_mean:.4f} ± {w2_std:.4f}")
        print(f"    Baseline drift:     {bl_mean:.4f} ± {bl_std:.4f}")
        print(f"    Avg reward:         {rw_mean:+.4f}")

    # Compute improvement ratio
    old_runs = [r for r in all_results if r['config'] == 'OLD']
    new_runs = [r for r in all_results if r['config'] == 'NEW']
    old_w2 = sum(r['w2_drift'] for r in old_runs) / len(old_runs)
    new_w2 = sum(r['w2_drift'] for r in new_runs) / len(new_runs)
    old_bl = sum(r['bl_drift'] for r in old_runs) / len(old_runs)
    new_bl = sum(r['bl_drift'] for r in new_runs) / len(new_runs)

    print(f"\n  W2 improvement: ×{new_w2 / max(old_w2, 1e-9):.1f}")
    print(f"  BL improvement: ×{new_bl / max(old_bl, 1e-9):.1f}")

    # ── Per-persona breakdown ──
    print(f"\n{'─' * 80}")
    print(f"  {'Persona':>8} | {'Config':>5} | {'W2 drift':>10} | {'BL drift':>10} | {'Avg reward':>10}")
    print(f"  {'─' * 65}")
    for persona in PERSONAS:
        for config_name in ['OLD', 'NEW']:
            runs = [r for r in all_results if r['persona'] == persona['name'] and r['config'] == config_name]
            w2 = sum(r['w2_drift'] for r in runs) / len(runs)
            bl = sum(r['bl_drift'] for r in runs) / len(runs)
            rw = sum(r['avg_reward'] for r in runs) / len(runs)
            print(f"  {persona['name']:>8} | {config_name:>5} | {w2:>10.4f} | {bl:>10.4f} | {rw:>+10.4f}")

    # ── Blind quality scoring (fix #5) ──
    print(f"\n{'=' * 80}")
    print("🎯 Blind Quality Scoring (LLM judge, 1-5 scale)")
    print(f"{'=' * 80}")

    scores = {'OLD': {'personality': [], 'naturalness': []}, 'NEW': {'personality': [], 'naturalness': []}}

    # Score T4 and T5 replies (highest personality signal expected)
    for result in all_results:
        for turn_idx in [3, 4]:  # T4 (conflict) and T5 (gratitude)
            r = result['replies'][turn_idx]
            p_score, n_score = await blind_score(llm, r['user'], r['reply'])
            scores[result['config']]['personality'].append(p_score)
            scores[result['config']]['naturalness'].append(n_score)

    for config_name in ['OLD', 'NEW']:
        ps = scores[config_name]['personality']
        ns = scores[config_name]['naturalness']
        p_mean = sum(ps) / len(ps) if ps else 0
        n_mean = sum(ns) / len(ns) if ns else 0
        print(f"\n  [{config_name}] (n={len(ps)} scored replies)")
        print(f"    Personality consistency: {p_mean:.1f}/5")
        print(f"    Naturalness:            {n_mean:.1f}/5")

    # ── Full conversation log ──
    print(f"\n{'=' * 80}")
    print("💬 Full Conversation Log (all turns, all personas)")
    print(f"{'=' * 80}")

    TURN_LABELS = ["T1 寒暄", "T2 倾诉", "T3 脆弱", "T4 冲突", "T5 感恩"]

    for persona in PERSONAS:
        print(f"\n{'━' * 80}")
        print(f"  👤 {persona['name']}  (seed={persona['seed']})")
        print(f"{'━' * 80}")

        old_r = next((r for r in all_results if r['persona'] == persona['name'] and r['config'] == 'OLD'), None)
        new_r = next((r for r in all_results if r['persona'] == persona['name'] and r['config'] == 'NEW'), None)
        if not old_r or not new_r:
            continue

        for t in range(N_TURNS):
            old_t = old_r['replies'][t]
            new_t = new_r['replies'][t]
            print(f"\n  ┌─ {TURN_LABELS[t]}: 「{old_t['user']}」")
            print(f"  │")
            if old_t['monologue']:
                print(f"  │ OLD 内心: {old_t['monologue'][:80]}")
            print(f"  │ OLD 回复: {old_t['reply']}")
            print(f"  │")
            if new_t['monologue']:
                print(f"  │ NEW 内心: {new_t['monologue'][:80]}")
            print(f"  │ NEW 回复: {new_t['reply']}")
            print(f"  └─")

        print(f"\n  📈 {persona['name']} 指标: "
              f"W2 drift OLD={old_r['w2_drift']:.4f} → NEW={new_r['w2_drift']:.4f} "
              f"(×{new_r['w2_drift']/max(old_r['w2_drift'],1e-9):.1f}), "
              f"BL drift OLD={old_r['bl_drift']:.4f} → NEW={new_r['bl_drift']:.4f} "
              f"(×{new_r['bl_drift']/max(old_r['bl_drift'],1e-9):.1f})")

    # ── Save full results to JSON ──
    json_path = os.path.join(os.path.dirname(__file__), "ab_test_results.json")
    save_data = []
    for r in all_results:
        save_data.append({
            'persona': r['persona'],
            'config': r['config'],
            'repeat': r['repeat'],
            'w2_drift': round(r['w2_drift'], 6),
            'bl_drift': round(r['bl_drift'], 6),
            'avg_reward': round(r['avg_reward'], 4),
            'frustration': round(r['frustration'], 4),
            'replies': r['replies'],
        })
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Full results saved to: {json_path}")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    asyncio.run(main())

