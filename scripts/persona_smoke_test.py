"""
Persona Smoke Test — Fast automated validation for new/modified personas.

No LLM required. Uses simulated conversations (genome engine only) to verify
that a persona's drive configuration produces healthy behavior under stress.

Usage:
    python scripts/persona_smoke_test.py                  # Test all personas
    python scripts/persona_smoke_test.py personas/vivian  # Test one persona

Checks:
    1. W2 Frobenius drift in healthy range (not zero, not exploding)
    2. Baseline stays within elastic bounds (max ±0.15 from initial)
    3. Signal outputs have reasonable spread (not collapsed)
    4. Weights stay within clip bounds (no explosion)
    5. Coupling rate > 0 (persona is actually learning)
    6. Drive differentiation (drives don't all converge)
"""

import sys
import os
import math
import random
import yaml
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.genome.genome_engine import (
    Agent, SIGNALS, DRIVES, SCENARIOS, simulate_conversation,
    N_SIGNALS, HIDDEN_SIZE, INPUT_SIZE
)
from engine.genome.drive_metabolism import DriveMetabolism, apply_thermodynamic_noise


# ═══════════════════════ Thresholds ═══════════════════════

@dataclass
class HealthBounds:
    """Universal health bounds — persona-agnostic."""
    w2_drift_min: float = 0.002     # Too low = not learning at all
    w2_drift_max: float = 0.800     # Too high = weight explosion (60-turn sim normal range: 0.10-0.58)
    baseline_max_drift: float = 0.15 # With ELASTICITY=0.05, theoretical max ~0.10
    signal_spread_min: float = 0.03  # Minimum std across 8 signals (continuous regime: ~0.05-0.10)
    signal_mean_min: float = 0.15    # Not all signals crushed to 0
    signal_mean_max: float = 0.85    # Not all signals saturated to 1
    w2_max_abs: float = 2.0          # Clip is 1.5, allow small headroom
    w1_max_abs: float = 3.0          # Allow slightly above clip (clip is 2.0, transient overshoot OK)
    coupling_rate_min: float = 0.05  # At least 5% of turns show coupled learning
    drive_spread_min: float = 0.03   # Drives shouldn't all converge to same value

BOUNDS = HealthBounds()

# Stress test scenarios - deliberately adversarial sequence
STRESS_SEQUENCES = [
    ['日常闲聊', '深夜心事', '吵架冲突'],   # Escalation
    ['吵架冲突', '吵架冲突', '分享喜悦'],   # Sustained conflict → recovery
    ['分享喜悦', '深夜心事', '日常闲聊'],   # Emotional rollercoaster
]


# ═══════════════════════ Helpers ═══════════════════════

def frobenius_norm(W, rows, cols):
    return math.sqrt(sum(W[i][j] ** 2 for i in range(rows) for j in range(cols)))


def frobenius_drift(w_now, w_init, rows, cols):
    return math.sqrt(sum(
        (w_now[i][j] - w_init[i][j]) ** 2
        for i in range(rows) for j in range(cols)
    ))


def load_persona(persona_dir):
    """Load persona from PERSONA.md YAML frontmatter."""
    md_path = os.path.join(persona_dir, "PERSONA.md")
    if not os.path.exists(md_path):
        raise FileNotFoundError(f"No PERSONA.md found in {persona_dir}")

    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract YAML frontmatter between --- markers
    parts = content.split('---')
    if len(parts) < 3:
        raise ValueError(f"No YAML frontmatter in {md_path}")

    data = yaml.safe_load(parts[1])
    name = data.get('name', os.path.basename(persona_dir))
    seed = hash(name) % 10000
    baseline = data.get('genome_seed', {}).get('drive_baseline', {})

    return {
        'name': name,
        'seed': seed,
        'baseline': baseline,
        'mbti': data.get('mbti', ''),
        'tags': data.get('tags', []),
    }


# ═══════════════════════ Core Test ═══════════════════════

def run_smoke_test(persona, sequence_idx=0):
    """Run one stress test sequence, return health metrics."""
    random.seed(persona['seed'] + sequence_idx * 1000)

    agent = Agent(seed=persona['seed'])
    for d, v in persona['baseline'].items():
        if d in agent.drive_baseline:
            agent.drive_baseline[d] = float(v)
            agent.drive_state[d] = float(v)

    initial_baseline = dict(agent.drive_baseline)

    # Snapshot W2/W1 initial state
    w2_init = [[agent.W2[i][j] for j in range(HIDDEN_SIZE)] for i in range(N_SIGNALS)]
    w1_init = [[agent.W1[i][j] for j in range(INPUT_SIZE)] for i in range(HIDDEN_SIZE)]

    # Simulate with elastic baseline (matching chat_agent.py behavior)
    BASELINE_LR = 0.01
    ELASTICITY = 0.05
    metabolism = DriveMetabolism()

    sequence = STRESS_SEQUENCES[sequence_idx % len(STRESS_SEQUENCES)]
    coupling_events = 0
    total_steps = 0
    all_signals = []

    for scenario_name in sequence:
        ctx = SCENARIOS[scenario_name].copy()
        for step in range(20):
            ctx['conversation_depth'] = min(1.0, ctx['conversation_depth'] + 0.02)

            # Simulate reward from metabolism
            reward = random.gauss(0.0, 0.4)

            # Step engine
            signals = agent.compute_signals(ctx)
            # Synthetic satisfaction: positive reward → uniform micro-satisfaction
            sat = {d: max(0.0, reward * 0.05) for d in DRIVES} if reward > 0 else None
            agent.step(ctx, reward, drive_satisfaction=sat)

            # Track coupling (signal shift > 0.03 correlated with reward direction)
            if all_signals:
                prev = all_signals[-1]
                max_shift = max(abs(signals[s] - prev[s]) for s in SIGNALS)
                if max_shift > 0.03 and abs(reward) > 0.15:
                    coupling_events += 1

            all_signals.append(dict(signals))
            total_steps += 1

            # Elastic baseline evolution (simulate Critic-driven shift)
            for d in DRIVES:
                shift = random.gauss(0, 0.3) * BASELINE_LR
                drift = agent.drive_baseline[d] - initial_baseline.get(d, 0.5)
                pull_back = -drift * ELASTICITY
                agent.drive_baseline[d] = max(0.1, min(0.95,
                    agent.drive_baseline[d] + shift + pull_back
                ))

    # ── Compute metrics ──
    w2_drift = frobenius_drift(agent.W2, w2_init, N_SIGNALS, HIDDEN_SIZE)

    max_bl_drift = max(abs(agent.drive_baseline[d] - initial_baseline.get(d, 0.5))
                       for d in DRIVES)

    # Signal statistics (last 20 steps)
    recent = all_signals[-20:]
    signal_means = {s: sum(r[s] for r in recent) / len(recent) for s in SIGNALS}
    overall_mean = sum(signal_means.values()) / len(signal_means)
    signal_std = (sum((signal_means[s] - overall_mean) ** 2
                      for s in SIGNALS) / len(SIGNALS)) ** 0.5

    # Weight bounds
    w2_max = max(abs(agent.W2[i][j]) for i in range(N_SIGNALS) for j in range(HIDDEN_SIZE))
    w1_max = max(abs(agent.W1[i][j]) for i in range(HIDDEN_SIZE) for j in range(INPUT_SIZE))

    coupling_rate = coupling_events / total_steps if total_steps > 0 else 0

    # Drive spread
    drive_vals = [agent.drive_baseline[d] for d in DRIVES]
    drive_mean = sum(drive_vals) / len(drive_vals)
    drive_spread = (sum((v - drive_mean) ** 2 for v in drive_vals) / len(drive_vals)) ** 0.5

    return {
        'w2_drift': w2_drift,
        'max_bl_drift': max_bl_drift,
        'signal_mean': overall_mean,
        'signal_spread': signal_std,
        'w2_max': w2_max,
        'w1_max': w1_max,
        'coupling_rate': coupling_rate,
        'drive_spread': drive_spread,
    }


def check_health(metrics, bounds=BOUNDS):
    """Check metrics against health bounds. Returns (pass, failures)."""
    failures = []

    if metrics['w2_drift'] < bounds.w2_drift_min:
        failures.append(f"W2 drift too LOW ({metrics['w2_drift']:.4f} < {bounds.w2_drift_min}): not learning")
    if metrics['w2_drift'] > bounds.w2_drift_max:
        failures.append(f"W2 drift too HIGH ({metrics['w2_drift']:.4f} > {bounds.w2_drift_max}): possible explosion")

    if metrics['max_bl_drift'] > bounds.baseline_max_drift:
        failures.append(f"Baseline drift ({metrics['max_bl_drift']:.3f}) exceeds elastic bound ({bounds.baseline_max_drift})")

    if metrics['signal_spread'] < bounds.signal_spread_min:
        failures.append(f"Signal spread ({metrics['signal_spread']:.4f}) too low: signals collapsed")
    if metrics['signal_mean'] < bounds.signal_mean_min:
        failures.append(f"Signal mean ({metrics['signal_mean']:.4f}) too low: crushed to zero")
    if metrics['signal_mean'] > bounds.signal_mean_max:
        failures.append(f"Signal mean ({metrics['signal_mean']:.4f}) too high: saturated")

    if metrics['w2_max'] > bounds.w2_max_abs:
        failures.append(f"W2 max weight ({metrics['w2_max']:.2f}) exceeds clip threshold ({bounds.w2_max_abs})")
    if metrics['w1_max'] > bounds.w1_max_abs:
        failures.append(f"W1 max weight ({metrics['w1_max']:.2f}) exceeds clip threshold ({bounds.w1_max_abs})")

    if metrics['coupling_rate'] < bounds.coupling_rate_min:
        failures.append(f"Coupling rate ({metrics['coupling_rate']:.2%}) too low: no emergent behavior")

    if metrics['drive_spread'] < bounds.drive_spread_min:
        failures.append(f"Drive spread ({metrics['drive_spread']:.4f}) too low: drives converged to same value")

    return len(failures) == 0, failures


# ═══════════════════════ Main ═══════════════════════

def main():
    personas_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "persona", "personas")

    # Parse args
    if len(sys.argv) > 1:
        # Test specific persona(s)
        targets = sys.argv[1:]
    else:
        # Test all personas
        targets = [os.path.join(personas_dir, d)
                   for d in sorted(os.listdir(personas_dir))
                   if os.path.isdir(os.path.join(personas_dir, d))]

    print("=" * 75)
    print("🧪 Persona Smoke Test")
    print(f"   {len(targets)} persona(s) × {len(STRESS_SEQUENCES)} stress sequences = "
          f"{len(targets) * len(STRESS_SEQUENCES)} tests")
    print("=" * 75)

    all_pass = True
    results_summary = []

    for target in targets:
        # Resolve path
        if not os.path.isabs(target):
            if os.path.isdir(os.path.join(personas_dir, target)):
                target = os.path.join(personas_dir, target)

        try:
            persona = load_persona(target)
        except Exception as e:
            print(f"\n  ⚠️  Cannot load {target}: {e}")
            all_pass = False
            continue

        print(f"\n  👤 {persona['name']} ({persona['mbti']}) "
              f"{'|'.join(persona['tags'])}")
        print(f"     drives: {' '.join(f'{d}={v:.2f}' for d, v in persona['baseline'].items())}")

        persona_pass = True
        all_metrics = []

        for seq_i in range(len(STRESS_SEQUENCES)):
            metrics = run_smoke_test(persona, seq_i)
            all_metrics.append(metrics)
            passed, failures = check_health(metrics)

            seq_label = '→'.join(STRESS_SEQUENCES[seq_i])
            status = "✅" if passed else "❌"
            print(f"     {status} Seq{seq_i+1} [{seq_label}]")
            print(f"        w2Δ={metrics['w2_drift']:.4f}  "
                  f"blΔ={metrics['max_bl_drift']:.3f}  "
                  f"sig={metrics['signal_mean']:.2f}±{metrics['signal_spread']:.3f}  "
                  f"coupling={metrics['coupling_rate']:.0%}  "
                  f"drives_σ={metrics['drive_spread']:.3f}")

            if not passed:
                for f in failures:
                    print(f"        ⚠️  {f}")
                persona_pass = False

        # Aggregate across sequences
        avg_w2 = sum(m['w2_drift'] for m in all_metrics) / len(all_metrics)
        avg_coupling = sum(m['coupling_rate'] for m in all_metrics) / len(all_metrics)
        overall = "PASS ✅" if persona_pass else "FAIL ❌"
        print(f"     ── {persona['name']}: {overall}  (avg w2Δ={avg_w2:.4f}, coupling={avg_coupling:.0%})")

        results_summary.append({
            'name': persona['name'],
            'passed': persona_pass,
            'avg_w2': avg_w2,
            'avg_coupling': avg_coupling,
        })

        if not persona_pass:
            all_pass = False

    # Final summary
    print(f"\n{'=' * 75}")
    passed_count = sum(1 for r in results_summary if r['passed'])
    total_count = len(results_summary)

    if all_pass:
        print(f"🎉 ALL {total_count} PERSONAS PASSED")
    else:
        print(f"⚠️  {passed_count}/{total_count} passed, {total_count - passed_count} failed")
        for r in results_summary:
            if not r['passed']:
                print(f"   ❌ {r['name']}")

    print("=" * 75)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
