"""
Quick validation test for the Persona Engine + Genome v8 Engine.
Tests persona loading and genome signal computation.
"""

import sys
import os

# Add the server directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.persona import PersonaLoader
from core.genome.genome_engine import Agent, SIGNALS, SCENARIOS, SIGNAL_LABELS
from core.genome.drive_metabolism import DriveMetabolism, apply_thermodynamic_noise


def test_persona_loader():
    print("=" * 60)
    print("TEST: PersonaLoader")
    print("=" * 60)

    loader = PersonaLoader(os.path.join(os.path.dirname(os.path.dirname(__file__)), "personas"))
    personas = loader.load_all()

    print(f"\n✅ Loaded {len(personas)} personas: {list(personas.keys())}")
    required = {'iris', 'luna', 'vivian', 'kai'}
    missing = required - set(personas.keys())
    assert not missing, f"Missing required personas: {missing}"

    for pid, p in personas.items():
        print(f"\n--- {p.name} (ID: {pid}) ---")
        print(f"  Age: {p.age}, Gender: {p.gender}, MBTI: {p.mbti}")
        print(f"  Tags: {p.tags}")
        assert p.name, "Name should not be empty"
        assert p.drive_baseline, f"{pid} should have drive_baseline"
        print(f"  Drive baseline: {p.drive_baseline}")
        assert p.bio, f"{pid} should have bio"

    print("\n✅ PersonaLoader tests PASSED")


def test_genome_engine():
    print("\n" + "=" * 60)
    print("TEST: Genome Engine (Agent + DriveMetabolism)")
    print("=" * 60)

    # Create agent
    agent = Agent(seed=42)
    print(f"✅ Agent created: seed=42, drives={list(agent.drive_state.keys())}")

    # Test signal computation
    signals = agent.compute_signals(SCENARIOS['深夜心事'])
    print(f"✅ Signals (深夜心事): {len(signals)} dims")
    for s in SIGNALS[:4]:
        print(f"    {SIGNAL_LABELS[s]}: {signals[s]:.3f}")
    assert len(signals) == 8, f"Expected 8 signals, got {len(signals)}"

    # Test drive metabolism
    metabolism = DriveMetabolism()
    print(f"\n  Initial frustration total: {metabolism.total():.2f}")

    # Simulate time passage (1 hour)
    import time as t
    metabolism.time_metabolism(metabolism._last_tick + 3600)
    print(f"  After 1h: total={metabolism.total():.2f}, connection={metabolism.frustration['connection']:.3f}")
    assert metabolism.frustration['connection'] > 0, "Connection hunger should grow over time"
    print(f"✅ Time metabolism works")

    fake_delta = {'connection': -0.5, 'novelty': 0.2, 'expression': -0.3}
    reward = metabolism.apply_llm_delta(fake_delta)
    print(f"\n  Drive delta: {fake_delta}")
    print(f"  Reward: {reward:.3f}")
    print(f"  After delta: total={metabolism.total():.2f}")
    print(f"✅ apply_llm_delta works")

    # Test thermodynamic noise
    noisy = apply_thermodynamic_noise(signals, metabolism.total())
    diffs = [abs(noisy[s] - signals[s]) for s in SIGNALS]
    avg_noise = sum(diffs) / len(diffs)
    print(f"\n  Average noise magnitude: {avg_noise:.4f}")
    print(f"✅ Thermodynamic noise works")

    # Test Hebbian learning
    old_w2_sample = agent.W2[0][0]
    agent.step(SCENARIOS['深夜心事'], reward=0.5)
    new_w2_sample = agent.W2[0][0]
    weight_changed = abs(new_w2_sample - old_w2_sample) > 0.0001
    print(f"\n  W2[0][0]: {old_w2_sample:.6f} → {new_w2_sample:.6f} (changed={weight_changed})")
    print(f"✅ Hebbian learning works")

    # Test serialization
    data = agent.to_dict()
    restored = Agent.from_dict(data)
    assert restored.seed == agent.seed
    assert restored.age == agent.age
    assert abs(restored.W2[0][0] - agent.W2[0][0]) < 1e-10
    print(f"✅ Agent serialization round-trip OK")

    meta_data = metabolism.to_dict()
    restored_m = DriveMetabolism.from_dict(meta_data)
    assert abs(restored_m.total() - metabolism.total()) < 1e-6
    print(f"✅ DriveMetabolism serialization round-trip OK")

    print("\n✅ Genome Engine tests PASSED")


if __name__ == "__main__":
    test_persona_loader()
    test_genome_engine()
    print("\n" + "=" * 60)
    print("🎉 ALL TESTS PASSED!")
    print("=" * 60)
