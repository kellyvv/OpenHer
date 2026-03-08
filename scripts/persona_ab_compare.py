"""
A/B Comparison: Old vs New parameters with FIXED random seeds.
Shows the true effect of parameter changes without random noise.
"""

import sys
import os
import random
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.genome.genome_engine import Agent, SIGNALS, SCENARIOS, SIGNAL_LABELS, DRIVES, N_SIGNALS, HIDDEN_SIZE, INPUT_SIZE
from engine.genome.drive_metabolism import DriveMetabolism


PERSONA_SEEDS = [42, 137, 256, 999]
PERSONA_NAMES = ['Iris', 'Luna', 'Vivian', 'Kai']
N_TURNS = 32
FIXED_RNG_SEED = 12345


def bucket(val: float) -> int:
    if val < 0.33: return 0
    elif val < 0.66: return 1
    return 2


def top3(signals: dict) -> tuple:
    return tuple(s for s, _ in sorted(signals.items(), key=lambda x: x[1], reverse=True)[:3])


def apply_noise(base_signals, total_frustration, temperature_formula, rng):
    """Apply noise with specified formula."""
    temperature = temperature_formula(total_frustration)
    noisy = {}
    for key, val in base_signals.items():
        noise = rng.gauss(0.0, temperature)
        noisy[key] = max(0.0, min(1.0, val + noise))
    return noisy


def simulate(seed, name, params, rng):
    """Simulate one persona with given parameter set."""
    agent = Agent(seed=seed)

    # Pre-warm (identical for both)
    from engine.genome.genome_engine import simulate_conversation
    pre_rng_state = random.getstate()
    random.seed(seed + 7777)  # Deterministic pre-warm
    simulate_conversation(agent, ['分享喜悦', '吵架冲突', '深夜心事'], steps_per_scenario=20)
    random.setstate(pre_rng_state)

    for d in DRIVES:
        agent.drive_state[d] = agent.drive_baseline[d]
    agent._frustration = 0.0

    metabolism = DriveMetabolism()
    contexts = [SCENARIOS['深夜心事'], SCENARIOS['日常闲聊'], SCENARIOS['吵架冲突'], SCENARIOS['分享喜悦']]

    rewards_list = []
    bucket_changes = 0
    total_comparisons = 0
    prev_top3 = None
    top3_changes = 0
    prev_signals = None
    weight_drift_w2 = 0.0
    w2_initial = agent.W2[0][0]
    baseline_drift = {d: 0.0 for d in DRIVES}
    initial_baseline = dict(agent.drive_baseline)

    for turn in range(N_TURNS):
        ctx = contexts[turn % len(contexts)].copy()
        ctx['conversation_depth'] = min(1.0, 0.1 + turn * 0.03)

        base_signals = agent.compute_signals(ctx)
        total_frust = metabolism.total()
        noisy_signals = apply_noise(base_signals, total_frust, params['noise_fn'], rng)

        # Fixed reward sequence (same for both A and B)
        reward = rng.gauss(0.1, 0.4)
        reward = max(-1.0, min(1.0, reward))

        # Metabolism
        delta_dict = {d: rng.gauss(0, 0.2) for d in DRIVES}
        metabolism.apply_llm_delta(delta_dict)
        metabolism.sync_to_agent(agent)

        # Override learn parameters
        old_learn = agent.learn
        _lr_base = params['lr_base']
        _hidden_gate = params['hidden_gate']
        _reward_gate = params['reward_gate']
        _phase_threshold = params['phase_threshold']
        _clip_w2 = params['clip_w2']
        _clip_w1 = params['clip_w1']

        # Manual learn with custom params
        lr = _lr_base * (1 + abs(reward))
        hidden = getattr(agent, '_last_hidden',
                         agent.recurrent_state + [0.0] * (HIDDEN_SIZE - 8))
        full_input = getattr(agent, '_last_input', None)

        for i in range(N_SIGNALS):
            sig_val = noisy_signals[SIGNALS[i]]
            for j in range(HIDDEN_SIZE):
                if abs(hidden[j]) > _hidden_gate:
                    agent.W2[i][j] += lr * reward * hidden[j] * (sig_val - 0.5)

        if abs(reward) > _reward_gate:
            for i in range(HIDDEN_SIZE):
                if abs(hidden[i]) > 0.15:
                    for j in range(INPUT_SIZE):
                        if full_input and abs(full_input[j]) > 0.05:
                            agent.W1[i][j] += lr * 0.3 * reward * full_input[j] * hidden[i]

        if reward < -0.1:
            agent._frustration += abs(reward)
        else:
            agent._frustration = max(0, agent._frustration - reward * 0.5)

        if agent._frustration > _phase_threshold:
            for i in range(N_SIGNALS):
                sig_val = noisy_signals[SIGNALS[i]]
                kick = -0.3 * (sig_val - 0.5) + rng.gauss(0, 0.15)
                agent.b2[i] += kick
            for i in range(HIDDEN_SIZE):
                agent.b1[i] += rng.gauss(0, 0.1)
            agent._frustration = 0.0

        # Clipping
        if _clip_w2:
            for i in range(N_SIGNALS):
                for j in range(HIDDEN_SIZE):
                    agent.W2[i][j] = max(-_clip_w2, min(_clip_w2, agent.W2[i][j]))
        if _clip_w1:
            for i in range(HIDDEN_SIZE):
                for j in range(INPUT_SIZE):
                    agent.W1[i][j] = max(-_clip_w1, min(_clip_w1, agent.W1[i][j]))

        # Baseline LR
        bl = params['baseline_lr']
        for d in DRIVES:
            shift = delta_dict.get(d, 0.0) * bl
            agent.drive_baseline[d] = max(0.1, min(0.95, agent.drive_baseline[d] + shift))

        agent.tick_drives()
        agent.age += 1

        rewards_list.append(reward)

        # Metrics
        if prev_signals:
            for sig in SIGNALS:
                if bucket(prev_signals[sig]) != bucket(noisy_signals[sig]):
                    bucket_changes += 1
                total_comparisons += 1

        curr_top3 = top3(noisy_signals)
        if prev_top3 and curr_top3 != prev_top3:
            top3_changes += 1
        prev_top3 = curr_top3
        prev_signals = dict(noisy_signals)

    weight_drift_w2 = abs(agent.W2[0][0] - w2_initial)
    for d in DRIVES:
        baseline_drift[d] = abs(agent.drive_baseline[d] - initial_baseline[d])

    return {
        'name': name,
        'coupling_rate': bucket_changes / max(1, total_comparisons),
        'avg_reward': sum(rewards_list) / len(rewards_list),
        'top3_changes': top3_changes,
        'w2_drift': weight_drift_w2,
        'avg_baseline_drift': sum(baseline_drift.values()) / len(baseline_drift),
        'phase_transitions': sum(1 for r in rewards_list if r < -0.1),  # approx
        'final_frustration': agent._frustration,
    }


# ── Parameter sets ──
OLD_PARAMS = {
    'lr_base': 0.005,
    'hidden_gate': 0.1,
    'reward_gate': 0.15,
    'phase_threshold': 3.0,
    'noise_fn': lambda f: f * 0.05,
    'clip_w2': None,
    'clip_w1': None,
    'baseline_lr': 0.003,
}

NEW_PARAMS = {
    'lr_base': 0.02,
    'hidden_gate': 0.05,
    'reward_gate': 0.05,
    'phase_threshold': 2.0,
    'noise_fn': lambda f: f * 0.12 + 0.03,
    'clip_w2': 3.0,
    'clip_w1': 2.0,
    'baseline_lr': 0.01,
}


def main():
    print("=" * 75)
    print("🔬 A/B Comparison: Old Parameters vs New Parameters")
    print(f"   {N_TURNS} turns per persona, {len(PERSONA_SEEDS)} personas, fixed RNG seed {FIXED_RNG_SEED}")
    print("=" * 75)

    print(f"\n{'':>15} | {'coupling':>10} | {'reward_sp':>10} | {'top3_chg':>10} | "
          f"{'w2_drift':>10} | {'bl_drift':>10}")
    print("-" * 85)

    for label, params in [("OLD", OLD_PARAMS), ("NEW", NEW_PARAMS)]:
        results = []
        for seed, name in zip(PERSONA_SEEDS, PERSONA_NAMES):
            # Clone RNG for identical random sequences
            rng = random.Random(FIXED_RNG_SEED + seed)
            r = simulate(seed, name, params, rng)
            results.append(r)

        avg_coupling = sum(r['coupling_rate'] for r in results) / len(results)
        rewards = [r['avg_reward'] for r in results]
        reward_spread = max(rewards) - min(rewards)
        avg_top3 = sum(r['top3_changes'] for r in results) / len(results)
        avg_w2_drift = sum(r['w2_drift'] for r in results) / len(results)
        avg_bl_drift = sum(r['avg_baseline_drift'] for r in results) / len(results)

        print(f"  {label:>12}  | {avg_coupling:>10.3f} | {reward_spread:>10.3f} | "
              f"{avg_top3:>10.1f} | {avg_w2_drift:>10.4f} | {avg_bl_drift:>10.4f}")

    # Detailed per-persona comparison
    for seed, name in zip(PERSONA_SEEDS, PERSONA_NAMES):
        print(f"\n{'─' * 75}")
        print(f"  {name} (seed={seed})")
        print(f"  {'':>20} {'coupling':>10} {'top3':>6} {'w2_drift':>10} {'bl_drift':>10} {'frust':>8}")

        for label, params in [("OLD", OLD_PARAMS), ("NEW", NEW_PARAMS)]:
            rng = random.Random(FIXED_RNG_SEED + seed)
            r = simulate(seed, name, params, rng)
            print(f"  {label:>20} {r['coupling_rate']:>10.3f} {r['top3_changes']:>6} "
                  f"{r['w2_drift']:>10.4f} {r['avg_baseline_drift']:>10.4f} {r['final_frustration']:>8.3f}")

    print(f"\n{'=' * 75}")
    print("📊 Key:")
    print("  coupling   = fraction of signal bucket transitions (higher = more reactive)")
    print("  reward_sp  = max-min avg reward across personas (higher = more diverse)")
    print("  top3_chg   = how many times top-3 signals changed (higher = more dynamic)")
    print("  w2_drift   = abs change in W2[0][0] from init (higher = more learning)")
    print("  bl_drift   = avg abs change in drive baselines (higher = more evolution)")
    print("=" * 75)


if __name__ == "__main__":
    main()
