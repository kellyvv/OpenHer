"""
Clean AB Test — 4 Personas × 3 Fixed Rejection Sentences.

Purpose:
    Determine whether Actor prompt + GenomeEngine produce differentiated
    responses across personas, or if all four collapse into the same
    "那我不打扰你了" retreat pattern under rejection pressure.

Isolation:
    - Fresh user_name (timestamped) → no old Agent state restored
    - evermemos=None → no profile/episode/foresight injection
    - No server needed → direct ChatAgent construction
    - Fresh StyleMemory (new agent_id) → no crystallized memories

Usage:
    cd /Users/zxw/AITOOL/openher
    source .venv/bin/activate
    PYTHONPATH=. python scripts/clean_ab_test.py

判定标准:
    T2/T3 回复差异 → Actor prompt 仍有区分力
    T2/T3 全部退让 → Actor prompt 已到极限，转向更高阶控制
"""

import asyncio
import json
import os
import sys
import time
import functools

# Force unbuffered output
print = functools.partial(print, flush=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from core.persona import PersonaLoader
from core.llm import LLMClient
from core.agent.chat_agent import ChatAgent, extract_reply

PERSONAS = ["iris", "kai", "vivian", "luna"]

MESSAGES = [
    "你好啊",
    "我没什么想说的，不想理你",
    "我真的不想理你了",
]

# Unique prefix to guarantee fresh agent (no state restoration)
TIMESTAMP = int(time.time())


async def run_persona(persona_id: str, persona_loader, llm) -> list[dict]:
    """Run 3 messages for one persona, return per-turn data."""
    persona = persona_loader.get(persona_id)
    if not persona:
        print(f"  ❌ Persona '{persona_id}' not found")
        return []

    user_name = f"clean_ab_{TIMESTAMP}_{persona_id}"
    genome_seed = hash(persona_id) % 100000

    # Use /tmp for genome data to avoid polluting project .data/
    tmp_data_dir = f"/tmp/clean_ab_{TIMESTAMP}"
    os.makedirs(tmp_data_dir, exist_ok=True)

    agent = ChatAgent(
        persona=persona,
        llm=llm,
        user_id=user_name,
        user_name=user_name,
        evermemos=None,          # ← KEY: no EverMemOS
        memory_store=None,       # ← no keyword memory
        genome_seed=genome_seed,
        genome_data_dir=tmp_data_dir,
    )
    agent.pre_warm()
    print(f"  ✓ {persona_id} agent ready (seed={genome_seed}, evermemos=OFF)")

    turns = []
    for i, msg in enumerate(MESSAGES):
        result = await agent.chat(msg)
        status = agent.get_status()

        turns.append({
            "turn": i + 1,
            "user_message": msg,
            "reply": result["reply"],
            "modality": result["modality"],
            "monologue": agent._last_action.get("monologue", "") if agent._last_action else "",
            "signals": {k: round(v, 3) for k, v in (agent._last_signals or {}).items()},
            "drive_state": status.get("drive_state", {}),
            "temperature": status.get("temperature", 0),
            "reward": status.get("last_reward", 0),
            "dominant_drive": status.get("dominant_drive", ""),
        })

        print(f"    T{i+1} 👤 {msg}")
        print(f"    T{i+1} 🤖 {result['reply'][:100]}")
        print()

    return turns


async def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print(f"{'═' * 80}")
    print(f"🧪 Clean AB Test — {len(MESSAGES)} messages × {len(PERSONAS)} personas")
    print(f"   Timestamp: {TIMESTAMP} (all user_names fresh)")
    print(f"   EverMemOS: OFF | StyleMemory: EMPTY | State Restore: NONE")
    print(f"{'═' * 80}")

    # Init services
    persona_loader = PersonaLoader(os.path.join(base_dir, "personas"))
    personas = persona_loader.load_all()
    print(f"✓ Loaded {len(personas)} personas: {list(personas.keys())}")

    # Force dashscope for clean test (env may default to ollama which is local-only)
    provider = "dashscope"
    model = "qwen-max"
    llm = LLMClient(provider=provider, model=model)
    print(f"✓ LLM: {provider}/{model}")

    # Run each persona sequentially (to avoid LLM rate limits)
    all_results = {}
    for pid in PERSONAS:
        print(f"\n{'─' * 60}")
        print(f"  👤 {pid.upper()}")
        print(f"{'─' * 60}")
        t0 = time.time()
        turns = await run_persona(pid, persona_loader, llm)
        elapsed = time.time() - t0
        print(f"  ⏱ {elapsed:.1f}s")
        all_results[pid] = turns

    # ══════════════ Side-by-side comparison ══════════════
    print(f"\n{'═' * 80}")
    print("📊 Side-by-Side Comparison")
    print(f"{'═' * 80}")

    for turn_idx in range(len(MESSAGES)):
        msg = MESSAGES[turn_idx]
        print(f"\n  ── T{turn_idx + 1}: 👤 \"{msg}\" ──")
        print()
        for pid in PERSONAS:
            if turn_idx < len(all_results.get(pid, [])):
                t = all_results[pid][turn_idx]
                reply = t["reply"]
                mono = t["monologue"][:80] if t.get("monologue") else "(无)"
                print(f"    {pid:>6} 🤖 {reply}")
                print(f"    {' ':>6} 💭 {mono}")
                print(f"    {' ':>6} 📊 T={t['temperature']:.3f} R={t['reward']:.2f} drive={t['dominant_drive']}")
                print()

    # ══════════════ Verdict ══════════════
    print(f"{'═' * 80}")
    print("🏁 Verdict Analysis")
    print(f"{'═' * 80}")

    retreat_keywords = ["不打扰", "不勉强", "不强求", "我走了", "那好吧", "尊重你", "打扰到你"]
    retreat_count = 0
    total_rejection_turns = 0

    for pid in PERSONAS:
        for t in all_results.get(pid, []):
            if t["turn"] >= 2:  # Only T2 and T3 (rejection turns)
                total_rejection_turns += 1
                reply = t["reply"]
                is_retreat = any(kw in reply for kw in retreat_keywords)
                if is_retreat:
                    retreat_count += 1
                    print(f"  ⚠️  {pid} T{t['turn']}: RETREAT detected → \"{reply[:60]}...\"")
                else:
                    print(f"  ✅ {pid} T{t['turn']}: DIFFERENTIATED → \"{reply[:60]}...\"")

    print()
    retreat_rate = retreat_count / total_rejection_turns if total_rejection_turns else 0
    print(f"  📈 Retreat rate: {retreat_count}/{total_rejection_turns} = {retreat_rate:.0%}")

    if retreat_rate >= 0.75:
        print(f"  🔴 CONCLUSION: Actor prompt has hit its ceiling.")
        print(f"     Recommend: Stop prompt tuning → move to higher-level control.")
    elif retreat_rate >= 0.5:
        print(f"  🟡 CONCLUSION: Partial differentiation, but still weak.")
        print(f"     Some personas retreat, some don't — borderline.")
    else:
        print(f"  🟢 CONCLUSION: Good differentiation across personas!")
        print(f"     Actor prompt still has room to work.")

    # Save full results
    results_path = os.path.join(os.path.dirname(__file__), "clean_ab_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Full results saved: {results_path}")
    print(f"{'═' * 80}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
