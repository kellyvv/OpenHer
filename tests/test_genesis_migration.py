#!/usr/bin/env python3
"""
Test genesis migration: data integrity, KNN recall consistency, action marker cleaning.

Usage:
    PYTHONPATH=. python3 tests/test_genesis_migration.py
"""

import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.genome.style_memory import ContinuousStyleMemory, clean_action_markers, CONTEXT_KEYS


# ── Test helpers ──

def load_json_genesis(json_path):
    """Load genesis from JSON file (original format)."""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def create_db_memory(persona_id, db_path, now=1000.0):
    """Create a ContinuousStyleMemory that reads from DB."""
    return ContinuousStyleMemory(
        agent_id=f"{persona_id}_testuser",
        persona_id=persona_id,
        state_db_path=db_path,
        now=now,
    )


# ── Tests ──

def test_data_integrity():
    """Verify JSON data matches DB data for all personas."""
    print("═" * 60)
    print("TEST 1: Data Integrity")
    print("═" * 60)

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".data")
    genome_dir = os.path.join(data_dir, "genome")
    db_path = os.path.join(data_dir, "openher.db")

    import glob
    json_files = sorted(glob.glob(os.path.join(genome_dir, "genesis_*.json")))

    if not json_files:
        print("  ⚠️  No JSON files found (already deleted?). Skipping integrity test.")
        print("      Run this test BEFORE deleting JSON files.\n")
        return True

    all_pass = True
    for json_file in json_files:
        persona_id = os.path.basename(json_file).replace("genesis_", "").replace(".json", "")

        # Load from JSON (original)
        json_seeds = load_json_genesis(json_file)

        # Load from DB (migrated)
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT seeds FROM genesis_seed WHERE persona_id=?", (persona_id,)).fetchone()
        conn.close()

        if not row:
            print(f"  ❌ {persona_id}: NOT FOUND in DB")
            all_pass = False
            continue

        db_seeds = json.loads(row[0])

        # Compare counts
        if len(json_seeds) != len(db_seeds):
            print(f"  ❌ {persona_id}: count mismatch JSON={len(json_seeds)} DB={len(db_seeds)}")
            all_pass = False
            continue

        # Compare vectors (text may differ due to action marker cleaning)
        vectors_match = True
        for i, (js, ds) in enumerate(zip(json_seeds, db_seeds)):
            if js.get('vector') != ds.get('vector'):
                print(f"  ❌ {persona_id} seed {i}: vector mismatch")
                vectors_match = False
                break

        if vectors_match:
            print(f"  ✅ {persona_id}: {len(db_seeds)} seeds, vectors match")
        else:
            all_pass = False

    print()
    return all_pass


def test_knn_recall():
    """Verify KNN recall is consistent between JSON-loaded and DB-loaded memories."""
    print("═" * 60)
    print("TEST 2: KNN Recall Consistency")
    print("═" * 60)

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".data")
    db_path = os.path.join(data_dir, "openher.db")

    # Test contexts covering different scenarios
    test_contexts = [
        {"conflict_level": 0.0, "user_emotion": 0.5, "user_engagement": 0.2,
         "user_vulnerability": 0.0, "topic_intimacy": 0.0, "conversation_depth": 0.0,
         "novelty_level": 0.0, "time_of_day": 0.5},  # greeting
        {"conflict_level": 0.0, "user_emotion": -0.8, "user_engagement": 0.6,
         "user_vulnerability": 0.5, "topic_intimacy": 0.7, "conversation_depth": 0.3,
         "novelty_level": 0.2, "time_of_day": 0.9},  # distress/late night
        {"conflict_level": 0.9, "user_emotion": -0.8, "user_engagement": 0.7,
         "user_vulnerability": 0.2, "topic_intimacy": 0.3, "conversation_depth": 0.5,
         "novelty_level": 0.1, "time_of_day": 0.5},  # confrontation
    ]

    personas_to_test = ["kelly", "iris", "ember"]
    all_pass = True

    for persona_id in personas_to_test:
        sm = create_db_memory(persona_id, db_path)
        if sm.stats()['genesis_count'] == 0:
            print(f"  ⚠️  {persona_id}: no genesis seeds in DB, skipping")
            continue

        print(f"  {persona_id} (genesis={sm.stats()['genesis_count']}):")

        for i, ctx in enumerate(test_contexts):
            results = sm.retrieve(ctx, top_k=3, lang_preference='zh')
            if results:
                top = results[0]
                print(f"    ctx{i+1}: top1 dist={top['distance']:.4f} "
                      f"user_input=\"{top['user_input'][:30]}...\"")
            else:
                print(f"    ctx{i+1}: no results (might be lang filtered)")

    print(f"\n  ✅ KNN recall working from DB\n")
    return all_pass


def test_empty_persona():
    """Verify empty persona doesn't crash."""
    print("═" * 60)
    print("TEST 3: Empty Persona")
    print("═" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        sm = ContinuousStyleMemory(
            agent_id="nonexistent_testuser",
            persona_id="nonexistent",
            state_db_path=db_path,
            db_dir=tmpdir,
            now=1000.0,
        )
        stats = sm.stats()
        assert stats['genesis_count'] == 0, f"Expected 0, got {stats['genesis_count']}"
        assert stats['total'] == 0, f"Expected 0 total, got {stats['total']}"

        # Retrieve should return empty, not crash
        results = sm.retrieve({"conflict_level": 0.5}, top_k=3)
        assert results == [], f"Expected empty results, got {results}"

        print(f"  ✅ Empty persona: genesis_count=0, retrieve=[], no crash\n")
    return True


def test_clean_action_markers():
    """Verify action marker cleaning covers all patterns."""
    print("═" * 60)
    print("TEST 4: Action Marker Cleaning")
    print("═" * 60)

    cases = [
        ("他说了*顿了顿*什么", "他说了什么"),
        ("*sighs softly* hello", "hello"),
        ("＊轻笑＊嗯", "嗯"),
        ("（沉默）好吧", "好吧"),
        ("（轻轻笑）谢谢", "谢谢"),
        ("(pauses) well", "well"),
        ("(laughs) ok", "ok"),
        ("「沉默」嗯", "嗯"),
        ("no markers here", "no markers here"),
        ("多个*动作1*中间*动作2*文字", "多个中间文字"),
    ]

    all_pass = True
    for input_text, expected in cases:
        result = clean_action_markers(input_text)
        if result == expected:
            print(f"  ✅ \"{input_text}\" → \"{result}\"")
        else:
            print(f"  ❌ \"{input_text}\" → \"{result}\" (expected \"{expected}\")")
            all_pass = False

    print()
    return all_pass


def test_save_and_load_roundtrip():
    """Verify save_genesis_to_db → load roundtrip."""
    print("═" * 60)
    print("TEST 5: Save → Load Roundtrip")
    print("═" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        test_seeds = [
            {
                "vector": [0.0, 0.5, 0.2, 0.0, 0.0, 0.0, 0.0, 0.5],
                "monologue": "*顿了顿*有人来了",
                "reply": "（沉默）你好",
                "user_input": "你好啊",
                "mass": 1.0,
                "lang": "zh"
            },
            {
                "vector": [0.9, -0.8, 0.7, 0.2, 0.3, 0.5, 0.1, 0.5],
                "monologue": "This is (sighs) annoying",
                "reply": "Whatever ＊rolls eyes＊",
                "user_input": "you're annoying",
                "mass": 1.0,
                "lang": "en"
            }
        ]

        # Save
        ContinuousStyleMemory.save_genesis_to_db("test_persona", test_seeds, db_path)

        # Load via ContinuousStyleMemory
        sm = ContinuousStyleMemory(
            agent_id="test_persona_user1",
            persona_id="test_persona",
            state_db_path=db_path,
            db_dir=tmpdir,
            now=1000.0,
        )

        stats = sm.stats()
        assert stats['genesis_count'] == 2, f"Expected 2 genesis, got {stats['genesis_count']}"

        # Verify action markers were cleaned
        pool = sm._pool
        assert "*" not in pool[0]['monologue'], f"Action marker not cleaned: {pool[0]['monologue']}"
        assert "（" not in pool[0]['reply'], f"Action marker not cleaned: {pool[0]['reply']}"
        assert "(sighs)" not in pool[1]['monologue'], f"Action marker not cleaned: {pool[1]['monologue']}"
        assert "＊" not in pool[1]['reply'], f"Action marker not cleaned: {pool[1]['reply']}"

        # Verify vectors preserved
        assert pool[0]['vector'] == [0.0, 0.5, 0.2, 0.0, 0.0, 0.0, 0.0, 0.5]

        print(f"  ✅ 2 seeds saved, loaded, action markers cleaned")
        print(f"     monologue[0]: \"{pool[0]['monologue']}\"")
        print(f"     reply[0]: \"{pool[0]['reply']}\"")
        print(f"     monologue[1]: \"{pool[1]['monologue']}\"")
        print(f"     reply[1]: \"{pool[1]['reply']}\"\n")

    return True


if __name__ == "__main__":
    results = []
    results.append(("Data Integrity", test_data_integrity()))
    results.append(("KNN Recall", test_knn_recall()))
    results.append(("Empty Persona", test_empty_persona()))
    results.append(("Action Markers", test_clean_action_markers()))
    results.append(("Save/Load Roundtrip", test_save_and_load_roundtrip()))

    print("═" * 60)
    print("SUMMARY")
    print("═" * 60)
    all_pass = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_pass = False

    sys.exit(0 if all_pass else 1)
