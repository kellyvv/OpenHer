#!/usr/bin/env python3
"""
Calibrate genesis vectors v2 — Per-seed Critic-sourced 8D vectors.

Replaces the old KEYWORD_MAP → SCENARIO_CONTEXTS bucket system.
Each seed gets its own unique 8D vector by running user_input through
the same Critic LLM used at runtime.

Also adds 'lang' field to each seed.

Usage:
    python scripts/calibrate_genesis_v2.py           # all personas
    python scripts/calibrate_genesis_v2.py iris kai   # specific
"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv()

from engine.genome.critic import critic_sense
from engine.genome.genome_engine import DRIVES
from engine.genome.style_memory import CONTEXT_KEYS
from providers.llm.client import LLMClient


def detect_lang(text: str) -> str:
    """Detect language from text: 'zh' if CJK chars present, else 'en'."""
    return 'zh' if any('\u4e00' <= c <= '\u9fff' for c in text[:30]) else 'en'


async def calibrate_persona(persona_id: str, data_dir: str, llm: LLMClient):
    """Calibrate genesis vectors for a single persona using Critic."""
    genesis_path = os.path.join(data_dir, f"genesis_{persona_id}.json")
    if not os.path.exists(genesis_path):
        print(f"  ⚠ No genesis file: {genesis_path}")
        return False

    with open(genesis_path, "r", encoding="utf-8") as f:
        genesis = json.load(f)

    frustration = {d: 0.0 for d in DRIVES}
    print(f"  Calibrating {len(genesis)} seeds via Critic LLM...")

    for i, seed in enumerate(genesis):
        user_input = seed.get("user_input", "")
        if not user_input:
            print(f"    [{i+1}] ⚠ No user_input, skipping")
            continue

        # Get 8D context from Critic (same as runtime)
        context, _, _, _ = await critic_sense(
            stimulus=user_input,
            llm=llm,
            frustration=frustration,
            user_profile="",
            episode_summary="",
        )

        new_vector = [round(context.get(k, 0.0), 4) for k in CONTEXT_KEYS]
        old_vector = seed.get("vector", [])

        # Detect language
        lang = detect_lang(seed.get("monologue", ""))
        seed["lang"] = lang
        seed["vector"] = new_vector

        # Show diff
        if len(old_vector) == len(new_vector):
            delta = sum(abs(a - b) for a, b in zip(old_vector, new_vector))
        else:
            delta = float("inf")

        lang_icon = "🟢" if lang == "zh" else "🔵"
        print(f"    [{i+1:2d}] {lang_icon}{lang} Δ={delta:.2f} \"{user_input[:30]}\"")
        print(f"         old: {[round(v, 2) for v in old_vector]}")
        print(f"         new: {new_vector}")

    # Write back
    with open(genesis_path, "w", encoding="utf-8") as f:
        json.dump(genesis, f, ensure_ascii=False, indent=4)
    print(f"  ✓ Written to {genesis_path}")

    # Stats
    unique_vecs = len(set(str(s["vector"]) for s in genesis))
    zh_count = sum(1 for s in genesis if s.get("lang") == "zh")
    en_count = sum(1 for s in genesis if s.get("lang") == "en")
    print(f"  📊 {len(genesis)} seeds, {unique_vecs} unique vectors, {zh_count} ZH / {en_count} EN")
    return True


async def main():
    llm = LLMClient(provider="dashscope", model="qwen-max")
    data_dir = os.path.join(ROOT, ".data", "genome")

    # Which personas to calibrate
    if len(sys.argv) > 1:
        target_ids = sys.argv[1:]
    else:
        target_ids = []
        for f in os.listdir(data_dir):
            if f.startswith("genesis_") and f.endswith(".json"):
                pid = f[len("genesis_"):-len(".json")]
                target_ids.append(pid)

    if not target_ids:
        print("No genesis files found.")
        return

    print(f"Calibrating {len(target_ids)} persona(s): {target_ids}")
    print(f"Using Critic LLM (same as runtime) for 8D vectors\n")

    for pid in sorted(target_ids):
        print(f"=== {pid} ===")
        await calibrate_persona(pid, data_dir, llm)
        print()

    print("Done. All genesis vectors now use Critic-sourced coordinates.")


if __name__ == "__main__":
    asyncio.run(main())
