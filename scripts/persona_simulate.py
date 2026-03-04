"""
Persona Emergence Simulation — quantitative validation of personality evolution.

Runs 4 different persona seeds through simulated conversations, measuring:
- coupling_rate: how often signals cross bucket boundaries (horizontal diversity)
- reward trajectory diversity: whether different personas get different avg rewards
- signal drift: whether top-3 signals change over 16 turns (vertical emergence)

Target metrics (post-optimization):
- coupling_rate >= 0.40
- 4 personas have distinct avg rewards
- top-3 signals change at least 2x in 16 turns
"""

import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.genome.genome_engine import Agent, SIGNALS, SCENARIOS, SIGNAL_LABELS, DRIVES
from core.genome.drive_metabolism import DriveMetabolism, apply_thermodynamic_noise
from core.genome.style_memory import ContinuousStyleMemory


PERSONA_SEEDS = [42, 137, 256, 999]
PERSONA_NAMES = ['Iris', 'Luna', 'Vivian', 'Kai']
N_TURNS = 16
SCENARIO_SEQ = ['分享喜悦', '吵架冲突', '深夜心事']


def top3_signals(signals: dict) -> tuple:
    """Return names of top-3 signals by value."""
    sorted_sigs = sorted(signals.items(), key=lambda x: x[1], reverse=True)
    return tuple(s[0] for s in sorted_sigs[:3])


def bucket(val: float) -> int:
    """3-bucket: 0=low, 1=mid, 2=high."""
    if val < 0.33:
        return 0
    elif val < 0.66:
        return 1
    return 2


def simulate_persona(seed: int, name: str):
    """Simulate one persona through N_TURNS, return metrics."""
    agent = Agent(seed=seed)

    # Pre-warm (like real server does)
    from core.genome.genome_engine import simulate_conversation
    simulate_conversation(agent, SCENARIO_SEQ, steps_per_scenario=20)
    for d in DRIVES:
        agent.drive_state[d] = agent.drive_baseline[d]
    agent._frustration = 0.0

    metabolism = DriveMetabolism()

    rewards = []
    bucket_changes = 0
    total_comparisons = 0
    prev_top3 = None
    top3_changes = 0

    # Simulate mixed conversation
    contexts = [
        SCENARIOS['深夜心事'],
        SCENARIOS['日常闲聊'],
        SCENARIOS['吵架冲突'],
        SCENARIOS['分享喜悦'],
    ]

    for turn in range(N_TURNS):
        ctx = contexts[turn % len(contexts)].copy()
        ctx['conversation_depth'] = min(1.0, 0.1 + turn * 0.06)

        # Compute signals
        base_signals = agent.compute_signals(ctx)
        total_frust = metabolism.total()
        noisy_signals = apply_thermodynamic_noise(base_signals, total_frust)

        # Simulate reward (varies by persona behavior)
        reward = random.gauss(0.1, 0.4) + (noisy_signals.get('warmth', 0.5) - 0.5) * 0.3
        reward = max(-1.0, min(1.0, reward))

        # Apply metabolism
        delta_dict = {}
        for d in DRIVES:
            delta_dict[d] = random.gauss(0, 0.2)
        actual_reward = metabolism.apply_llm_delta(delta_dict)
        metabolism.sync_to_agent(agent)

        # Learn
        agent.learn(noisy_signals, reward, ctx)

        rewards.append(reward)

        # Track bucket changes (coupling)
        if turn > 0:
            for sig in SIGNALS:
                prev_bucket = bucket(prev_signals[sig])
                curr_bucket = bucket(noisy_signals[sig])
                if prev_bucket != curr_bucket:
                    bucket_changes += 1
                total_comparisons += 1

        # Track top-3 signal changes (drift)
        curr_top3 = top3_signals(noisy_signals)
        if prev_top3 is not None and curr_top3 != prev_top3:
            top3_changes += 1
        prev_top3 = curr_top3
        prev_signals = dict(noisy_signals)

    coupling_rate = bucket_changes / max(1, total_comparisons)
    avg_reward = sum(rewards) / len(rewards)

    return {
        'name': name,
        'seed': seed,
        'coupling_rate': coupling_rate,
        'avg_reward': avg_reward,
        'top3_changes': top3_changes,
        'final_signals': {s: round(noisy_signals[s], 3) for s in SIGNALS},
        'final_drives': {d: round(agent.drive_state[d], 3) for d in DRIVES},
        'drive_baseline': {d: round(agent.drive_baseline[d], 3) for d in DRIVES},
        'frustration': round(agent._frustration, 3),
        'weight_sample': round(agent.W2[0][0], 6),
    }


def main():
    print("=" * 70)
    print("🧬 Persona Emergence Simulation")
    print("=" * 70)

    results = []
    for seed, name in zip(PERSONA_SEEDS, PERSONA_NAMES):
        r = simulate_persona(seed, name)
        results.append(r)

    # ── Print per-persona results ──
    for r in results:
        print(f"\n--- {r['name']} (seed={r['seed']}) ---")
        print(f"  coupling_rate:  {r['coupling_rate']:.3f}")
        print(f"  avg_reward:     {r['avg_reward']:.3f}")
        print(f"  top3_changes:   {r['top3_changes']} / {N_TURNS - 1}")
        print(f"  frustration:    {r['frustration']}")
        print(f"  W2[0][0]:       {r['weight_sample']}")
        top3 = top3_signals(r['final_signals'])
        print(f"  final top-3:    {', '.join(SIGNAL_LABELS[s] for s in top3)}")
        print(f"  drive baseline: {r['drive_baseline']}")

    # ── Aggregate metrics ──
    print("\n" + "=" * 70)
    print("📊 Aggregate Metrics")
    print("=" * 70)

    avg_coupling = sum(r['coupling_rate'] for r in results) / len(results)
    avg_rewards = [r['avg_reward'] for r in results]
    reward_spread = max(avg_rewards) - min(avg_rewards)
    avg_top3_changes = sum(r['top3_changes'] for r in results) / len(results)

    print(f"  avg coupling_rate:  {avg_coupling:.3f}  (target: >= 0.40)")
    print(f"  reward spread:      {reward_spread:.3f}  (target: > 0)")
    print(f"  avg top3 changes:   {avg_top3_changes:.1f}  (target: >= 2)")

    # ── Pass/Fail ──
    print("\n" + "=" * 70)
    checks = [
        ("coupling_rate >= 0.40", avg_coupling >= 0.40),
        ("reward diversity (spread > 0)", reward_spread > 0.01),
        ("signal drift (avg changes >= 2)", avg_top3_changes >= 2.0),
    ]
    all_pass = True
    for label, passed in checks:
        icon = "✅" if passed else "❌"
        print(f"  {icon} {label}")
        if not passed:
            all_pass = False

    if all_pass:
        print("\n🎉 ALL EMERGENCE CHECKS PASSED!")
    else:
        print("\n⚠️  Some checks failed — review parameters")
    print("=" * 70)


if __name__ == "__main__":
    main()
