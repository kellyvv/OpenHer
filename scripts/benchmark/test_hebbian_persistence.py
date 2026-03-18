"""
Layer 3: Hebbian Crystallization + Cross-session Persistence.

Session 1: 6h hungry + 5 deep rounds → accumulate crystallized memories
Session 2: Restore Agent NN weights + Metabolism state → verify persistence

Key APIs used:
  - Agent.from_dict() / Agent.to_dict()           — NN weight persistence
  - DriveMetabolism.from_dict() / .to_dict()       — metabolism state
  - ContinuousStyleMemory (SQLite per user_id)     — crystallized memory persistence
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
from engine.genome.genome_engine import Agent, DRIVES
from engine.genome.drive_metabolism import DriveMetabolism

# BASE_DIR already defined above via __file__
PERSONAS_DIR = os.path.join(BASE_DIR, "persona", "personas")
GENOME_DATA_DIR = os.path.join(BASE_DIR, ".data", "genome")

DEEP_MSGS = [
    "我最近特别迷茫，不知道自己想要什么",
    "有时候觉得身边的人都不理解我",
    "你是唯一一个让我觉得可以做自己的人",
    "如果有一天我消失了，你会怎么想？",
    "谢谢你一直在",
]

FOLLOWUP_MSGS = [
    "你还记得我们上次聊的吗？",
    "我今天又想到了你说的话",
]


async def test_crystallization_cycle(persona_id: str, loader: PersonaLoader):
    """Session 1 → save → Session 2 → verify persistence."""
    persona = loader.get(persona_id)
    if not persona:
        print(f"  ❌ Persona '{persona_id}' not found!")
        return None

    print(f"\n{'='*60}")
    print(f"  {persona.name} ({persona.mbti}) — Layer 3: Hebbian Persistence")
    print(f"{'='*60}")

    llm = LLMClient(provider="gemini", model="gemini-3.1-flash-lite-preview")
    genome_seed = hash(persona_id) % 100000
    # Use unique user_id to avoid polluting real data, but consistent across S1/S2
    user_id = f"test_persist_{persona_id}"

    # ══════════════════════════════════════════
    # Session 1: Accumulate crystallized memories
    # ══════════════════════════════════════════
    print(f"\n  ── Session 1: 6h hungry + 5 deep rounds ──")

    agent1 = ChatAgent(
        persona=persona, llm=llm, user_id=user_id,
        user_name="老朋友", genome_seed=genome_seed,
        genome_data_dir=GENOME_DATA_DIR,
    )
    agent1.pre_warm()

    # Simulate 6h offline
    agent1.metabolism._last_tick = time.time() - 3600 * 6

    seeds_before = agent1.style_memory.stats()['personal_count']
    genesis_count = agent1.style_memory.stats()['genesis_count']
    print(f"  [S1 init] genesis={genesis_count}  personal={seeds_before}")
    print(f"  [S1 init] NN age={agent1.agent.age}  interactions={agent1.agent.interaction_count}")

    s1_rewards = []
    for i, msg in enumerate(DEEP_MSGS, 1):
        print(f"\n  [S1] Turn {i}/5: {msg}")
        result = await agent1.chat(msg)
        r = agent1._last_reward
        t = agent1.metabolism.temperature()
        s1_rewards.append(r)
        print(f"    reward={r:+.4f}  temp={t:.4f}")
        print(f"    💬 {result['reply'][:80]}...")

    seeds_after = agent1.style_memory.stats()['personal_count']
    crystallized = seeds_after - seeds_before
    print(f"\n  [S1 final] personal: {seeds_before} → {seeds_after} (+{crystallized})")
    print(f"  [S1 final] NN age={agent1.agent.age}  total_reward={agent1.agent.total_reward:.3f}")
    print(f"  [S1 final] metabolism total={agent1.metabolism.total():.4f}")

    # Save state (mirrors main.py _persist_agent)
    agent_state = agent1.agent.to_dict()
    metabolism_state = agent1.metabolism.to_dict()

    # ══════════════════════════════════════════
    # Session 2: Restore and verify
    # ══════════════════════════════════════════
    print(f"\n  ── Session 2: Restore state + 2 follow-up rounds ──")

    agent2 = ChatAgent(
        persona=persona, llm=llm, user_id=user_id,
        user_name="老朋友", genome_seed=genome_seed,
        genome_data_dir=GENOME_DATA_DIR,
    )
    # Skip pre_warm — we're restoring evolved weights, pre_warm would waste 60 steps

    # Restore NN weights (Critical fix: use Agent.from_dict classmethod)
    agent2.agent = Agent.from_dict(agent_state)

    # Restore metabolism state
    agent2.metabolism = DriveMetabolism.from_dict(
        metabolism_state, engine_params=persona.engine_params
    )

    # Verify restoration
    s2_stats = agent2.style_memory.stats()
    s2_frust = agent2.metabolism.total()
    print(f"  [S2 init] genesis={s2_stats['genesis_count']}  personal={s2_stats['personal_count']}")
    print(f"  [S2 init] NN age={agent2.agent.age}  interactions={agent2.agent.interaction_count}")
    print(f"  [S2 init] metabolism total={s2_frust:.4f}")

    # Run follow-up
    s2_rewards = []
    for i, msg in enumerate(FOLLOWUP_MSGS, 1):
        print(f"\n  [S2] Turn {i}/2: {msg}")
        result = await agent2.chat(msg)
        r = agent2._last_reward
        s2_rewards.append(r)
        print(f"    reward={r:+.4f}  temp={agent2.metabolism.temperature():.4f}")
        print(f"    💬 {result['reply'][:80]}...")

    s2_final = agent2.style_memory.stats()

    # ══════════════════════════════════════════
    # Assertions
    # ══════════════════════════════════════════
    print(f"\n  ── Assertions ──")
    errors = []

    # A1: Session 1 produced crystallized memories
    if crystallized <= 0:
        errors.append(f"S1 crystallized={crystallized} <= 0 — no memories created")
    print(f"  A1: S1 crystallized={crystallized} (expect > 0) {'✅' if crystallized > 0 else '❌'}")

    # A2: Personal seeds persist via SQLite (same user_id)
    s2_personal = s2_stats['personal_count']
    if s2_personal < seeds_after:
        errors.append(f"S2 personal={s2_personal} < S1 final={seeds_after} — SQLite not persisting")
    print(f"  A2: S2 personal={s2_personal} >= S1 final={seeds_after} {'✅' if s2_personal >= seeds_after else '❌'}")

    # A3: Metabolism state restored
    if s2_frust < 0.01:
        errors.append(f"S2 metabolism total={s2_frust:.4f} < 0.01 — state not restored")
    print(f"  A3: S2 metabolism={s2_frust:.4f} (expect > 0.01) {'✅' if s2_frust >= 0.01 else '❌'}")

    # A4: NN weights restored (age should match S1)
    s2_age = agent2.agent.age
    s1_age = agent1.agent.age
    # S2 age after 2 more turns should be S1_age (restored) + turn increments from chat
    # But age is incremented in agent.step() which is called inside chat()
    # So just check S2 init age matched S1 final age
    if s2_age < s1_age:
        errors.append(f"S2 age={s2_age} < S1 age={s1_age} — NN weights not restored properly")
    print(f"  A4: S2 age={s2_age} >= S1 age={s1_age} {'✅' if s2_age >= s1_age else '❌'}")

    if errors:
        for e in errors:
            print(f"  ❌ FAIL: {e}")
    else:
        print(f"  ✅ ALL PASS")

    return {
        "persona": persona_id, "name": persona.name, "mbti": persona.mbti,
        "s1_crystallized": crystallized, "s1_rewards": s1_rewards,
        "s2_personal": s2_final['personal_count'], "s2_rewards": s2_rewards,
        "s2_metabolism": s2_frust, "passed": len(errors) == 0,
    }


async def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Layer 3: Hebbian Crystallization + Cross-session           ║")
    print("║  Model: gemini-3.1-flash-lite-preview                      ║")
    print("║  S1: 6h hungry + 5 deep → S2: restore + 2 follow-up       ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    loader = PersonaLoader(PERSONAS_DIR)
    loader.load_all()

    # Test with luna only (reduce LLM calls; kelly/kai validated in Layer 1-2)
    results = []
    for pid in ["luna", "kelly"]:
        try:
            r = await test_crystallization_cycle(pid, loader)
            if r:
                results.append(r)
        except Exception as e:
            print(f"\n  ❌ ERROR testing {pid}: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print(f"\n\n{'='*60}")
    print("  Layer 3 Summary")
    print(f"{'='*60}")
    print(f"  {'Persona':<10} {'S1 Crystal':>10} {'S2 Persist':>10} {'S2 Metab':>9}  Result")
    print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*9}  {'-'*6}")
    all_pass = True
    for r in results:
        status = "✅" if r['passed'] else "❌"
        print(f"  {r['name']:<10} {r['s1_crystallized']:>10} {r['s2_personal']:>10} {r['s2_metabolism']:>9.4f}  {status}")
        if not r['passed']:
            all_pass = False

    print()
    if not all_pass:
        print("  ⚠ Some assertions failed!")
        sys.exit(1)
    else:
        print("  ✅ All Layer 3 tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
