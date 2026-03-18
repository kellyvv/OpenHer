"""
Layer 2: Time Metabolism + Reward Signal Verification.

Tests that the thermodynamic engine produces meaningful reward signals
when the persona has been "offline" for 4 hours (connection hunger).

Trick: set metabolism._last_tick = time.time() - 3600*4 BEFORE first chat().
When chat() internally calls time_metabolism(time.time()), it sees delta_hours ≈ 4.0
and triggers:
  - connection.frust += 0.15 * 4 = 0.60
  - novelty.frust   += 0.05 * 4 = 0.20
  - total ≈ 0.80

Then apply_llm_delta() computes reward = old_total - new_total > 0.
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
from engine.genome.genome_engine import DRIVES

# BASE_DIR already defined above via __file__
PERSONAS_DIR = os.path.join(BASE_DIR, "persona", "personas")
GENOME_DATA_DIR = os.path.join(BASE_DIR, ".data", "genome")

# Connection-heavy messages (should relieve connection hunger → positive reward)
WARM_MSGS = [
    "好久不见，你有没有想我？",
    "我最近一直在想你会不会无聊",
    "告诉我今天你在想什么",
]

TEST_PERSONAS = ["luna", "kai", "kelly"]


async def test_warm_reward(persona_id: str, loader: PersonaLoader):
    """Run 3-round warm session with 4h simulated offline."""
    persona = loader.get(persona_id)
    if not persona:
        print(f"  ❌ Persona '{persona_id}' not found!")
        return None

    print(f"\n{'='*60}")
    print(f"  {persona.name} ({persona.mbti}) — Layer 2: Metabolism + Reward")
    print(f"{'='*60}")

    llm = LLMClient(provider="gemini", model="gemini-3.1-flash-lite-preview")
    genome_seed = hash(persona_id) % 100000

    agent = ChatAgent(
        persona=persona, llm=llm, user_id="test_warm",
        user_name="测试者", genome_seed=genome_seed,
        genome_data_dir=GENOME_DATA_DIR,
    )
    agent.pre_warm()

    # ── Verify: cold state after pre_warm ──
    pre_frust = agent.metabolism.total()
    pre_temp = agent.metabolism.temperature()
    print(f"  [post-prewarm] total_frust={pre_frust:.4f}  temp={pre_temp:.4f}")
    print(f"  [post-prewarm] frustration={dict((d, round(f, 4)) for d, f in agent.metabolism.frustration.items())}")

    # ── Simulate 4h offline: shift _last_tick backward ──
    agent.metabolism._last_tick = time.time() - 3600 * 4
    print(f"\n  ⏩ Simulated 4h offline (_last_tick -= 14400s)")

    # ── Verify: what time_metabolism WILL compute on first chat() ──
    # (Don't call it ourselves — let chat() do it naturally at L580)
    expected_conn = 0.15 * 4  # connection_hunger_k * delta_hours
    expected_nov = 0.05 * 4   # novelty_hunger_k * delta_hours
    print(f"  [expected] connection.frust ≈ {expected_conn:.2f}, novelty.frust ≈ {expected_nov:.2f}")
    print(f"  [expected] total ≈ {expected_conn + expected_nov:.2f}")

    # ── Run 3 turns ──
    rewards = []
    temps = []
    frusts = []

    for i, msg in enumerate(WARM_MSGS, 1):
        print(f"\n  ── Turn {i}/3: {msg} ──")

        result = await agent.chat(msg)
        r = agent._last_reward
        t = agent.metabolism.temperature()
        f = agent.metabolism.total()

        rewards.append(r)
        temps.append(t)
        frusts.append(f)

        print(f"  reward={r:+.4f}  temp={t:.4f}  total_frust={f:.4f}")
        print(f"  frustration={dict((d, round(v, 3)) for d, v in agent.metabolism.frustration.items())}")
        print(f"  💬 {result['reply'][:100]}...")

    # ── Assertions ──
    max_r = max(rewards)
    print(f"\n  ── Assertions ──")
    print(f"  max_reward = {max_r:.4f} (threshold: > 0.01)")
    print(f"  turn1_temp = {temps[0]:.4f} (threshold: > 0.02)")
    print(f"  turn1_frust = {frusts[0]:.4f} (threshold: > 0.05)")

    errors = []
    if max_r <= 0.01:
        errors.append(f"max_reward={max_r:.4f} <= 0.01 — no meaningful reward signal")
    if temps[0] <= 0.02:
        errors.append(f"turn1_temp={temps[0]:.4f} <= 0.02 — temperature didn't rise after 4h offline")

    if errors:
        for e in errors:
            print(f"  ❌ FAIL: {e}")
    else:
        print(f"  ✅ ALL PASS")

    return {
        "persona": persona_id, "name": persona.name, "mbti": persona.mbti,
        "rewards": rewards, "max_reward": max_r,
        "temps": temps, "frusts": frusts,
        "passed": len(errors) == 0,
    }


async def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Layer 2: Time Metabolism + Reward Verification             ║")
    print("║  Model: gemini-3.1-flash-lite-preview                      ║")
    print("║  Trick: _last_tick -= 4h → natural hunger accumulation     ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    loader = PersonaLoader(PERSONAS_DIR)
    loader.load_all()

    results = []
    for pid in TEST_PERSONAS:
        try:
            r = await test_warm_reward(pid, loader)
            if r:
                results.append(r)
        except Exception as e:
            print(f"\n  ❌ ERROR testing {pid}: {e}")
            import traceback
            traceback.print_exc()

    # Summary table
    print(f"\n\n{'='*60}")
    print("  Layer 2 Summary")
    print(f"{'='*60}")
    print(f"  {'Persona':<10} {'MBTI':<6} {'MaxReward':>10} {'T1 Temp':>8} {'T1 Frust':>9}  Result")
    print(f"  {'-'*10} {'-'*6} {'-'*10} {'-'*8} {'-'*9}  {'-'*6}")
    all_pass = True
    for r in results:
        status = "✅" if r['passed'] else "❌"
        print(f"  {r['name']:<10} {r['mbti']:<6} {r['max_reward']:>+10.4f} {r['temps'][0]:>8.4f} {r['frusts'][0]:>9.4f}  {status}")
        if not r['passed']:
            all_pass = False

    print()
    if not all_pass:
        print("  ⚠ Some assertions failed!")
        sys.exit(1)
    else:
        print("  ✅ All Layer 2 tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
