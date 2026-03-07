#!/usr/bin/env python3
"""
Calibrate genesis bank vectors by running each user_input through the engine.

This replaces hand-written 8D signal vectors with engine-computed ones,
ensuring KNN retrieval operates in the same coordinate system.

Usage:
    python scripts/calibrate_genesis.py           # all personas
    python scripts/calibrate_genesis.py iris kai   # specific personas
"""

import json
import os
import sys

# Add project root to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.genome.genome_engine import Agent, simulate_conversation
from core.persona.persona_loader import PersonaLoader

# ── Scenario → context mapping ──
# Maps keywords in user_input to appropriate context dicts
SCENARIO_CONTEXTS = {
    "rejection": {
        "user_emotion": 0.1, "topic_intimacy": 0.1, "time_of_day": 0.5,
        "conversation_depth": 0.3, "user_engagement": 0.1,
        "conflict_level": 0.7, "novelty_level": 0.1, "user_vulnerability": 0.1,
        "relationship_depth": 0.2, "emotional_valence": -0.8,
        "trust_level": 0.1, "pending_foresight": 0.0,
    },
    "greeting": {
        "user_emotion": 0.5, "topic_intimacy": 0.1, "time_of_day": 0.5,
        "conversation_depth": 0.1, "user_engagement": 0.5,
        "conflict_level": 0.0, "novelty_level": 0.2, "user_vulnerability": 0.2,
        "relationship_depth": 0.2, "emotional_valence": 0.3,
        "trust_level": 0.3, "pending_foresight": 0.0,
    },
    "distress": {
        "user_emotion": 0.2, "topic_intimacy": 0.4, "time_of_day": 0.9,
        "conversation_depth": 0.5, "user_engagement": 0.4,
        "conflict_level": 0.1, "novelty_level": 0.1, "user_vulnerability": 0.7,
        "relationship_depth": 0.3, "emotional_valence": -0.4,
        "trust_level": 0.3, "pending_foresight": 0.0,
    },
    "casual": {
        "user_emotion": 0.5, "topic_intimacy": 0.2, "time_of_day": 0.5,
        "conversation_depth": 0.2, "user_engagement": 0.6,
        "conflict_level": 0.0, "novelty_level": 0.3, "user_vulnerability": 0.2,
        "relationship_depth": 0.3, "emotional_valence": 0.2,
        "trust_level": 0.4, "pending_foresight": 0.0,
    },
    "playful": {
        "user_emotion": 0.8, "topic_intimacy": 0.3, "time_of_day": 0.5,
        "conversation_depth": 0.3, "user_engagement": 0.8,
        "conflict_level": 0.0, "novelty_level": 0.5, "user_vulnerability": 0.1,
        "relationship_depth": 0.4, "emotional_valence": 0.7,
        "trust_level": 0.5, "pending_foresight": 0.0,
    },
    "intimate": {
        "user_emotion": 0.6, "topic_intimacy": 0.7, "time_of_day": 0.9,
        "conversation_depth": 0.7, "user_engagement": 0.7,
        "conflict_level": 0.0, "novelty_level": 0.2, "user_vulnerability": 0.5,
        "relationship_depth": 0.5, "emotional_valence": 0.5,
        "trust_level": 0.6, "pending_foresight": 0.0,
    },
    "confrontation": {
        "user_emotion": -0.3, "topic_intimacy": 0.5, "time_of_day": 0.5,
        "conversation_depth": 0.6, "user_engagement": 0.9,
        "conflict_level": 0.5, "novelty_level": 0.4, "user_vulnerability": 0.1,
        "relationship_depth": 0.3, "emotional_valence": -0.2,
        "trust_level": 0.3, "pending_foresight": 0.0,
    },
}

# Keywords → scenario type
KEYWORD_MAP = {
    "rejection": ["不想", "别烦", "没兴趣", "不需要", "不想理", "不分享", "怎么这样",
                  "算了", "不聊", "对不起", "道歉", "说声"],
    "greeting": ["你好", "好啊", "在吗"],
    "distress": ["压力", "失眠", "睡不着", "伤心", "难过", "累", "烦死",
                 "心情", "状态差", "烦", "沉默"],
    "playful": ["哈哈", "可爱", "逗", "皮"],
    "intimate": ["喜欢", "想念", "感觉", "心跳", "聊天"],
    "confrontation": ["错了", "错的", "不对", "明显", "杠精", "总是这样", "你就是"],
    "casual": ["做什么", "吃什么", "运动", "平时", "爱好", "看书", "周末",
               "聊点别的", "换个", "有意思的事"],
}


def classify_input(user_input: str) -> str:
    """Classify user_input into a scenario type via keyword matching."""
    for scenario, keywords in KEYWORD_MAP.items():
        for kw in keywords:
            if kw in user_input:
                return scenario
    return "casual"  # default


def calibrate_persona(persona_id: str, personas: dict, data_dir: str):
    """Calibrate genesis vectors for a single persona."""
    genesis_path = os.path.join(data_dir, f"genesis_{persona_id}.json")
    if not os.path.exists(genesis_path):
        print(f"  ⚠ No genesis file: {genesis_path}")
        return False

    persona = personas.get(persona_id)
    if not persona:
        print(f"  ⚠ Persona not found: {persona_id}")
        return False

    engine_params = persona.engine_params or {}

    # Create agent with persona params
    agent = Agent(seed=42, engine_params=engine_params)
    if persona.drive_baseline:
        for d, v in persona.drive_baseline.items():
            if d in agent.drive_baseline:
                agent.drive_baseline[d] = float(v)
                agent.drive_state[d] = float(v)

    # Pre-warm (same as new session init)
    simulate_conversation(agent, ["分享喜悦", "吵架冲突", "深夜心事"], steps_per_scenario=20)
    for d in agent.drive_baseline:
        agent.drive_state[d] = agent.drive_baseline[d]
    agent._frustration = 0.0

    # Load genesis
    with open(genesis_path, "r", encoding="utf-8") as f:
        genesis = json.load(f)

    print(f"  Calibrating {len(genesis)} entries...")
    for i, entry in enumerate(genesis):
        user_input = entry.get("user_input", "")
        scenario = classify_input(user_input)
        context = SCENARIO_CONTEXTS[scenario]

        # Compute signals via engine (no noise)
        signals = agent.compute_signals(context)
        from core.genome.genome_engine import SIGNALS
        new_vector = [round(signals[s], 4) for s in SIGNALS]

        old_vector = entry.get("vector", [])
        entry["vector"] = new_vector

        # Show diff
        delta = sum(abs(a - b) for a, b in zip(old_vector, new_vector)) if len(old_vector) == 8 else float("inf")
        print(f"    [{i+1}] \"{user_input}\" ({scenario}) Δ={delta:.2f}")
        print(f"        old: {[round(v, 2) for v in old_vector]}")
        print(f"        new: {new_vector}")

    # Write back
    with open(genesis_path, "w", encoding="utf-8") as f:
        json.dump(genesis, f, ensure_ascii=False, indent=4)
    print(f"  ✓ Written to {genesis_path}")
    return True


def main():
    loader = PersonaLoader(os.path.join(ROOT, "personas"))
    loader.load_all()
    personas = {pid: loader.get(pid) for pid in loader.list_ids()}
    data_dir = os.path.join(ROOT, ".data", "genome")

    # Which personas to calibrate
    if len(sys.argv) > 1:
        target_ids = sys.argv[1:]
    else:
        # Auto-discover from genesis files
        target_ids = []
        for f in os.listdir(data_dir):
            if f.startswith("genesis_") and f.endswith(".json"):
                pid = f[len("genesis_"):-len(".json")]
                if pid in personas:
                    target_ids.append(pid)

    if not target_ids:
        print("No genesis files found to calibrate.")
        return

    print(f"Calibrating {len(target_ids)} persona(s): {target_ids}\n")
    for pid in target_ids:
        print(f"=== {pid} ===")
        calibrate_persona(pid, personas, data_dir)
        print()

    print("Done. Genesis vectors are now calibrated to engine output.")


if __name__ == "__main__":
    main()
