"""
KNN Seed Diagnosis v2 — Uses real Critic output (same as calibration)
Verifies: after calibrate_genesis_v2, does top-k actually differ by user intent?
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from engine.genome.style_memory import ContinuousStyleMemory, CONTEXT_KEYS
from engine.genome.critic import critic_sense
from engine.genome.genome_engine import DRIVES
from providers.llm.client import LLMClient


async def diagnose_persona(persona_id: str, llm: LLMClient):
    sm = ContinuousStyleMemory(agent_id=persona_id, persona_id=persona_id)
    pool_total = len(sm._pool)
    zh_count = sum(1 for m in sm._pool if m.get('lang') == 'zh')
    en_count = sum(1 for m in sm._pool if m.get('lang') == 'en')

    print(f"\n{'='*70}")
    print(f"  {persona_id} — Pool: {pool_total} seeds ({zh_count} ZH, {en_count} EN)")
    print(f"  Unique vectors: {len(set(str(m['vector']) for m in sm._pool))}")
    print(f"{'='*70}")

    frustration = {d: 0.0 for d in DRIVES}
    test_inputs = ["你好", "你平时喜欢做什么", "最近心情不太好"]

    for msg in test_inputs:
        # Get real Critic context (same as runtime)
        ctx, _, _, _ = await critic_sense(
            stimulus=msg, llm=llm, frustration=frustration,
            user_profile="", episode_summary="",
        )

        # Detect turn language
        turn_lang = 'zh' if any('\u4e00' <= c <= '\u9fff' for c in msg[:10]) else 'en'

        print(f"\n  📨 [{msg}] (turn_lang={turn_lang})")
        print(f"     critic: {', '.join(f'{k}={ctx.get(k,0):.1f}' for k in CONTEXT_KEYS)}")

        # Retrieve with lang_preference
        results = sm.retrieve(ctx, top_k=3, lang_preference=turn_lang)

        for i, r in enumerate(results):
            lang_tag = "🟢ZH" if r.get('lang') == 'zh' else "🔵EN"
            print(f"    [{i+1}] {lang_tag} dist={r['distance']:.3f} \"{r.get('user_input', '')[:30]}\"")
            print(f"        mono: {r['monologue'][:60]}")
            print(f"        reply: {r['reply'][:40]}")

    # Cross-language test
    print(f"\n  --- Cross-language test ---")
    en_msg = "I've been feeling really down"
    ctx_en, _, _, _ = await critic_sense(
        stimulus=en_msg, llm=llm, frustration=frustration,
        user_profile="", episode_summary="",
    )
    print(f"\n  📨 [{en_msg}] (turn_lang=en)")
    results_en = sm.retrieve(ctx_en, top_k=3, lang_preference='en')
    for i, r in enumerate(results_en):
        lang_tag = "🟢ZH" if r.get('lang') == 'zh' else "🔵EN"
        print(f"    [{i+1}] {lang_tag} dist={r['distance']:.3f} \"{r.get('user_input', '')[:40]}\"")
        print(f"        reply: {r['reply'][:40]}")


async def main():
    llm = LLMClient(provider="dashscope", model="qwen-max")
    for pid in ['iris', 'kai']:
        await diagnose_persona(pid, llm)


if __name__ == '__main__':
    asyncio.run(main())
