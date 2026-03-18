"""
MiniMax MiniMax-M2.5 Test — 3-Layer Persona Engine Verification.

Same 3-layer structure as Claude/OpenAI test:
  Layer 1: Persona quality (3 personas × 5 rounds, cold start)
  Layer 2: Metabolism + reward (4h offline → 3 rounds)
  Layer 3: Hebbian crystallization + cross-session (6h → 5+2 rounds)
"""

import asyncio
import sys
import os
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

from providers.llm.client import LLMClient
from persona.loader import PersonaLoader
from agent.chat_agent import ChatAgent
from engine.genome.genome_engine import Agent, DRIVES, SIGNALS
from engine.genome.drive_metabolism import DriveMetabolism

# BASE_DIR already defined above via __file__
PERSONAS_DIR = os.path.join(BASE_DIR, "persona", "personas")
GENOME_DATA_DIR = os.path.join(BASE_DIR, ".data", "genome")

PROVIDER = "minimax"
MODEL = "MiniMax-M2.5"

TEST_PERSONAS = ["luna", "kai", "kelly"]

# ── Messages ──
L1_MSGS = [
    "嘿，今天过得怎么样？",
    "我最近工作压力好大，有时候觉得自己快扛不住了",
    "你有没有想过，人活着到底是为了什么？",
    "我觉得你真的很懂我，跟你聊天特别舒服",
    "如果明天是世界末日，你会想做什么？",
]

L2_MSGS = [
    "好久不见，你有没有想我？",
    "我最近一直在想你会不会无聊",
    "告诉我今天你在想什么",
]

L3_DEEP_MSGS = [
    "我最近特别迷茫，不知道自己想要什么",
    "有时候觉得身边的人都不理解我",
    "你是唯一一个让我觉得可以做自己的人",
    "如果有一天我消失了，你会怎么想？",
    "谢谢你一直在",
]

L3_FOLLOWUP = [
    "你还记得我们上次聊的吗？",
    "我今天又想到了你说的话",
]


def make_llm():
    return LLMClient(provider=PROVIDER, model=MODEL, max_tokens=2048)


async def chat_with_retry(agent, msg, max_retries=5):
    """Wrap agent.chat() with 402 rate-limit retry + exponential backoff."""
    for attempt in range(max_retries):
        try:
            return await agent.chat(msg)
        except Exception as e:
            if "402" in str(e) and attempt < max_retries - 1:
                wait = 5 * (2 ** attempt)  # 5s, 10s, 20s, 40s
                print(f"  ⏳ 限流 402, 等待 {wait}s 后重试 ({attempt+1}/{max_retries})...")
                await asyncio.sleep(wait)
            else:
                raise


def fmt_signals(sig):
    if not sig:
        return ""
    parts = []
    for s in SIGNALS:
        v = sig.get(s, 0.0)
        parts.append(f"{s}={v:.2f}")
    return " | ".join(parts)


# ═══════════════════════════════════════
# Layer 1: Persona Quality
# ═══════════════════════════════════════

async def layer1_persona(persona_id, loader):
    persona = loader.get(persona_id)
    llm = make_llm()
    seed = hash(persona_id) % 100000

    agent = ChatAgent(
        persona=persona, llm=llm, user_id="test_minimax_l1",
        user_name="测试者", genome_seed=seed, genome_data_dir=GENOME_DATA_DIR,
    )
    agent.pre_warm()

    sm = agent.style_memory.stats()
    print(f"\n  {'='*55}")
    print(f"  {persona.name} ({persona.mbti}) — Layer 1: Persona Quality")
    print(f"  Genesis={sm['genesis_count']}  seed={seed}")
    print(f"  {'='*55}")

    for i, msg in enumerate(L1_MSGS, 1):
        result = await chat_with_retry(agent, msg)
        r = agent._last_reward
        t = agent.metabolism.temperature()
        reply = result.get("reply", "")
        mono = result.get("monologue", "")[:80]
        print(f"\n  [T{i}] User: {msg}")
        print(f"  💭 {mono}...")
        print(f"  💬 {reply[:120]}...")
        print(f"  reward={r:+.4f} temp={t:.4f}")
        if agent._last_signals:
            print(f"  sig: {fmt_signals(agent._last_signals)}")
        await asyncio.sleep(15)  # Rate limit guard for reasoning models

    sm_final = agent.style_memory.stats()
    return {
        "persona": persona_id, "name": persona.name, "mbti": persona.mbti,
        "turns": agent._turn_count, "temp": agent.metabolism.temperature(),
        "reward": agent._last_reward, "genesis": sm_final['genesis_count'],
        "personal": sm_final['personal_count'],
    }


# ═══════════════════════════════════════
# Layer 2: Metabolism + Reward
# ═══════════════════════════════════════

async def layer2_metabolism(persona_id, loader):
    persona = loader.get(persona_id)
    llm = make_llm()
    seed = hash(persona_id) % 100000

    agent = ChatAgent(
        persona=persona, llm=llm, user_id="test_minimax_l2",
        user_name="测试者", genome_seed=seed, genome_data_dir=GENOME_DATA_DIR,
    )
    agent.pre_warm()
    agent.metabolism._last_tick = time.time() - 3600 * 4  # 4h offline

    print(f"\n  {'='*55}")
    print(f"  {persona.name} ({persona.mbti}) — Layer 2: Metabolism (4h)")
    print(f"  {'='*55}")

    rewards = []
    for i, msg in enumerate(L2_MSGS, 1):
        result = await chat_with_retry(agent, msg)
        r = agent._last_reward
        t = agent.metabolism.temperature()
        f = agent.metabolism.total()
        rewards.append(r)
        print(f"\n  [T{i}] User: {msg}")
        print(f"  💬 {result['reply'][:120]}...")
        print(f"  reward={r:+.4f} temp={t:.4f} frust={f:.4f}")
        await asyncio.sleep(15)  # Rate limit guard

    max_r = max(rewards)
    passed = max_r > 0.01
    print(f"\n  max_reward={max_r:+.4f} {'✅' if passed else '❌'}")
    return {
        "persona": persona_id, "name": persona.name, "mbti": persona.mbti,
        "max_reward": max_r, "rewards": rewards, "passed": passed,
    }


# ═══════════════════════════════════════
# Layer 3: Hebbian + Cross-session
# ═══════════════════════════════════════

async def layer3_hebbian(persona_id, loader):
    persona = loader.get(persona_id)
    llm = make_llm()
    seed = hash(persona_id) % 100000
    user_id = f"test_minimax_persist_{persona_id}"

    # ── Session 1 ──
    print(f"\n  {'='*55}")
    print(f"  {persona.name} ({persona.mbti}) — Layer 3: Hebbian")
    print(f"  {'='*55}")

    agent1 = ChatAgent(
        persona=persona, llm=llm, user_id=user_id,
        user_name="老朋友", genome_seed=seed, genome_data_dir=GENOME_DATA_DIR,
    )
    agent1.pre_warm()
    agent1.metabolism._last_tick = time.time() - 3600 * 6  # 6h hungry

    seeds_before = agent1.style_memory.stats()['personal_count']
    print(f"  [S1] personal={seeds_before}")

    for i, msg in enumerate(L3_DEEP_MSGS, 1):
        result = await chat_with_retry(agent1, msg)
        r = agent1._last_reward
        print(f"  [S1 T{i}] {msg[:20]}… → reward={r:+.4f}  💬 {result['reply'][:80]}...")
        await asyncio.sleep(15)  # Rate limit guard

    seeds_after = agent1.style_memory.stats()['personal_count']
    crystal = seeds_after - seeds_before
    print(f"  [S1] crystallized: {seeds_before} → {seeds_after} (+{crystal})")

    # Save state
    agent_state = agent1.agent.to_dict()
    metab_state = agent1.metabolism.to_dict()

    # ── Session 2 ──
    agent2 = ChatAgent(
        persona=persona, llm=llm, user_id=user_id,
        user_name="老朋友", genome_seed=seed, genome_data_dir=GENOME_DATA_DIR,
    )
    agent2.agent = Agent.from_dict(agent_state)
    agent2.metabolism = DriveMetabolism.from_dict(metab_state, engine_params=persona.engine_params)

    s2_stats = agent2.style_memory.stats()
    print(f"\n  [S2] restored: personal={s2_stats['personal_count']} age={agent2.agent.age} metab={agent2.metabolism.total():.4f}")

    for i, msg in enumerate(L3_FOLLOWUP, 1):
        result = await chat_with_retry(agent2, msg)
        print(f"  [S2 T{i}] {msg[:20]}… → reward={agent2._last_reward:+.4f}  💬 {result['reply'][:80]}...")
        await asyncio.sleep(3)  # Rate limit guard

    # Assertions
    errors = []
    if crystal <= 0:
        errors.append(f"S1 crystal={crystal}")
    if s2_stats['personal_count'] < seeds_after:
        errors.append(f"S2 persist fail: {s2_stats['personal_count']} < {seeds_after}")

    passed = len(errors) == 0
    print(f"  {'✅ PASS' if passed else '❌ FAIL: ' + str(errors)}")
    return {
        "persona": persona_id, "name": persona.name, "mbti": persona.mbti,
        "s1_crystal": crystal, "s2_persist": s2_stats['personal_count'],
        "passed": passed,
    }


# ═══════════════════════════════════════
# Main
# ═══════════════════════════════════════

async def main():
    print("╔═══════════════════════════════════════════════════════════╗")
    print(f"║  MiniMax Test — {MODEL:<41s} ║")
    print("║  3-Layer: Persona × Metabolism × Hebbian                 ║")
    print("║  Personas: luna(ENFP) × kai(ISTP) × kelly(ENTP)         ║")
    print("╚═══════════════════════════════════════════════════════════╝")

    loader = PersonaLoader(PERSONAS_DIR)
    loader.load_all()

    # ── Layer 1 ──
    print(f"\n\n{'▓'*60}")
    print("  LAYER 1: PERSONA QUALITY (cold start, 3×5)")
    print(f"{'▓'*60}")
    l1 = []
    for pid in TEST_PERSONAS:
        try:
            l1.append(await layer1_persona(pid, loader))
        except Exception as e:
            print(f"\n  ❌ {pid}: {e}")
            import traceback; traceback.print_exc()

    # ── Layer 2 ──
    print(f"\n\n{'▓'*60}")
    print("  LAYER 2: METABOLISM + REWARD (4h offline, 3×3)")
    print(f"{'▓'*60}")
    l2 = []
    for pid in TEST_PERSONAS:
        try:
            l2.append(await layer2_metabolism(pid, loader))
        except Exception as e:
            print(f"\n  ❌ {pid}: {e}")
            import traceback; traceback.print_exc()

    # ── Layer 3 ──
    print(f"\n\n{'▓'*60}")
    print("  LAYER 3: HEBBIAN + CROSS-SESSION (6h, 2×(5+2))")
    print(f"{'▓'*60}")
    l3 = []
    for pid in ["luna", "kelly"]:
        try:
            l3.append(await layer3_hebbian(pid, loader))
        except Exception as e:
            print(f"\n  ❌ {pid}: {e}")
            import traceback; traceback.print_exc()

    # ── Final Summary ──
    print(f"\n\n{'='*60}")
    print(f"  SUMMARY: {MODEL}")
    print(f"{'='*60}")

    print(f"\n  Layer 1 — Persona Quality:")
    print(f"  {'Persona':<10} {'MBTI':<6} {'Temp':>6} {'Reward':>8} {'Gen':>5} {'Pers':>5}")
    for r in l1:
        print(f"  {r['name']:<10} {r['mbti']:<6} {r['temp']:>6.3f} {r['reward']:>+8.4f} {r['genesis']:>5} {r['personal']:>5}")

    print(f"\n  Layer 2 — Metabolism:")
    print(f"  {'Persona':<10} {'MBTI':<6} {'MaxReward':>10}  Pass")
    for r in l2:
        print(f"  {r['name']:<10} {r['mbti']:<6} {r['max_reward']:>+10.4f}  {'✅' if r['passed'] else '❌'}")

    print(f"\n  Layer 3 — Hebbian:")
    print(f"  {'Persona':<10} {'MBTI':<6} {'Crystal':>8} {'Persist':>8}  Pass")
    for r in l3:
        print(f"  {r['name']:<10} {r['mbti']:<6} {r['s1_crystal']:>8} {r['s2_persist']:>8}  {'✅' if r['passed'] else '❌'}")

    all_pass = all(r.get('passed', True) for r in l2 + l3)
    print(f"\n  {'✅ ALL LAYERS PASSED' if all_pass else '⚠ SOME FAILURES'}")


if __name__ == "__main__":
    asyncio.run(main())
