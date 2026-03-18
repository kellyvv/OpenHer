#!/usr/bin/env python3
"""
Engine-level recall accuracy test.

Verifies ContinuousStyleMemory.retrieve() from DB returns seeds with
expected vector proximity for each scenario context. Tests that:
1. Top-1 seed has distance < threshold (seed exists near query point)
2. Seeds retrieved for different scenarios are actually different
3. DB-loaded pool matches original JSON (when available)

Usage:
    PYTHONPATH=. python3 tests/test_recall_accuracy.py
"""

import json
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.genome.style_memory import ContinuousStyleMemory, CONTEXT_KEYS, _l2_distance, _context_to_vec


# ── Scenario contexts (matching calibrate_genesis.py) ──

SCENARIO_CONTEXTS = {
    "greeting": {
        "conflict_level": 0.0, "user_emotion": 0.5, "user_engagement": 0.2,
        "user_vulnerability": 0.0, "topic_intimacy": 0.0, "conversation_depth": 0.0,
        "novelty_level": 0.0, "time_of_day": 0.5,
    },
    "casual": {
        "conflict_level": 0.0, "user_emotion": 0.3, "user_engagement": 0.5,
        "user_vulnerability": 0.1, "topic_intimacy": 0.2, "conversation_depth": 0.3,
        "novelty_level": 0.5, "time_of_day": 0.5,
    },
    "playful": {
        "conflict_level": 0.0, "user_emotion": 0.7, "user_engagement": 0.8,
        "user_vulnerability": 0.2, "topic_intimacy": 0.3, "conversation_depth": 0.4,
        "novelty_level": 0.3, "time_of_day": 0.5,
    },
    "intimate": {
        "conflict_level": 0.0, "user_emotion": 0.6, "user_engagement": 0.7,
        "user_vulnerability": 0.6, "topic_intimacy": 0.8, "conversation_depth": 0.6,
        "novelty_level": 0.2, "time_of_day": 0.7,
    },
    "distress": {
        "conflict_level": 0.1, "user_emotion": -0.5, "user_engagement": 0.4,
        "user_vulnerability": 0.7, "topic_intimacy": 0.5, "conversation_depth": 0.4,
        "novelty_level": 0.2, "time_of_day": 0.8,
    },
    "rejection": {
        "conflict_level": 0.5, "user_emotion": -0.3, "user_engagement": 0.3,
        "user_vulnerability": 0.1, "topic_intimacy": 0.2, "conversation_depth": 0.3,
        "novelty_level": 0.1, "time_of_day": 0.5,
    },
    "confrontation": {
        "conflict_level": 0.9, "user_emotion": -0.8, "user_engagement": 0.7,
        "user_vulnerability": 0.1, "topic_intimacy": 0.3, "conversation_depth": 0.5,
        "novelty_level": 0.1, "time_of_day": 0.5,
    },
}

# Distance threshold: a properly calibrated seed should be within this
# distance of its scenario's context vector
DISTANCE_THRESHOLD = 0.5


def test_recall_for_persona(persona_id: str, lang: str = "zh"):
    """Test recall accuracy for one persona."""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".data")
    db_path = os.path.join(data_dir, "openher.db")

    sm = ContinuousStyleMemory(
        agent_id=f"{persona_id}_recall_test",
        persona_id=persona_id,
        db_dir=data_dir,
        now=1000.0,
    )

    stats = sm.stats()
    if stats['genesis_count'] == 0:
        print(f"  ⚠️  {persona_id}: no genesis seeds, skipping")
        return None

    print(f"\n{'═' * 70}")
    print(f"  {persona_id.upper()} — {stats['genesis_count']} genesis seeds (lang={lang})")
    print(f"{'═' * 70}")

    # Test 1: Each scenario has seeds within distance threshold
    pass_count = 0
    total = 0
    retrieved_inputs = {}

    for scenario, context in SCENARIO_CONTEXTS.items():
        results = sm.retrieve(context, top_k=3, lang_preference=lang)
        total += 1

        if not results:
            print(f"  {scenario:<14} ❌ no results")
            continue

        top = results[0]
        dist = top['distance']
        ok = dist < DISTANCE_THRESHOLD
        if ok:
            pass_count += 1

        status = "✅" if ok else "❌"
        retrieved_inputs[scenario] = top['user_input']

        print(f"  {scenario:<14} {status} dist={dist:.4f}  \"{top['user_input'][:40]}\"")
        for j, r in enumerate(results[1:], 2):
            print(f"  {'':14}    #{j} dist={r['distance']:.4f}  \"{r['user_input'][:35]}\"")

    # Test 2: Different scenarios retrieve different seeds (no cross-contamination)
    unique_top1 = len(set(retrieved_inputs.values()))
    diversity_ok = unique_top1 >= 5  # At least 5 out of 7 scenarios get unique seeds

    print(f"\n  Proximity:  {pass_count}/{total} scenarios have top-1 dist < {DISTANCE_THRESHOLD}")
    print(f"  Diversity:  {unique_top1}/7 unique top-1 seeds {'✅' if diversity_ok else '⚠️'}")

    accuracy = pass_count / total if total > 0 else 0
    return accuracy, diversity_ok


def test_json_db_consistency():
    """Verify JSON original data matches DB data (if JSON still exists)."""
    import glob
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".data")
    genome_dir = os.path.join(data_dir, "genome")
    db_path = os.path.join(data_dir, "openher.db")

    json_files = sorted(glob.glob(os.path.join(genome_dir, "genesis_*.json")))
    if not json_files:
        print("\n  ⚠️  No JSON files (already deleted). Skipping JSON↔DB comparison.")
        return True

    print(f"\n{'═' * 70}")
    print(f"  JSON ↔ DB CONSISTENCY")
    print(f"{'═' * 70}")

    conn = sqlite3.connect(db_path)
    all_ok = True

    for jf in json_files:
        pid = os.path.basename(jf).replace("genesis_", "").replace(".json", "")
        with open(jf, 'r') as f:
            json_seeds = json.load(f)

        row = conn.execute("SELECT seeds FROM genesis_seed WHERE persona_id=?", (pid,)).fetchone()
        if not row:
            print(f"  ❌ {pid}: missing in DB")
            all_ok = False
            continue

        db_seeds = json.loads(row[0])

        # Count check
        if len(json_seeds) != len(db_seeds):
            print(f"  ❌ {pid}: count mismatch {len(json_seeds)} vs {len(db_seeds)}")
            all_ok = False
            continue

        # Vector check
        vec_ok = all(
            js.get('vector') == ds.get('vector')
            for js, ds in zip(json_seeds, db_seeds)
        )
        if not vec_ok:
            print(f"  ❌ {pid}: vector mismatch")
            all_ok = False
        else:
            print(f"  ✅ {pid}: {len(db_seeds)} seeds, vectors identical")

    conn.close()
    return all_ok


def main():
    personas = ["kelly", "iris", "ember", "kai", "vivian"]

    # Engine-level recall
    results = {}
    for pid in personas:
        r = test_recall_for_persona(pid, lang="zh")
        if r is not None:
            results[pid] = r

    # JSON vs DB consistency
    consistency_ok = test_json_db_consistency()

    # Summary
    print(f"\n{'═' * 70}")
    print(f"  RECALL ACCURACY SUMMARY")
    print(f"{'═' * 70}")

    all_pass = True
    for pid, (acc, div) in results.items():
        status = "✅" if acc >= 0.7 else "⚠️" if acc >= 0.5 else "❌"
        div_str = "div=✅" if div else "div=⚠️"
        print(f"  {status} {pid:<12} proximity={acc:.0%}  {div_str}")
        if acc < 0.5:
            all_pass = False

    avg_acc = sum(a for a, _ in results.values()) / len(results) if results else 0
    print(f"\n  Average proximity: {avg_acc:.0%}")
    print(f"  JSON↔DB consistency: {'✅' if consistency_ok else '❌'}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
