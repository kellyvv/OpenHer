#!/usr/bin/env python3
"""
Step 6 Diagnostic: Print Critic 8D output for 3 test inputs.
Answers: Can Critic distinguish greeting vs distress vs casual?
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from engine.genome.critic import critic_sense
from engine.genome.genome_engine import DRIVES
from engine.genome.style_memory import CONTEXT_KEYS
from providers.llm.client import LLMClient


async def main():
    llm = LLMClient(provider="dashscope", model="qwen-max")
    frustration = {d: 0.0 for d in DRIVES}

    inputs = ["你好", "最近心情不太好", "你平时喜欢做什么"]

    print("=" * 60)
    print("  Critic 8D Diagnostic — Turn-1 Context Differentiation")
    print("=" * 60)

    all_contexts = {}
    for text in inputs:
        ctx, frust_d, rel_d, drive_sat = await critic_sense(
            stimulus=text,
            llm=llm,
            frustration=frustration,
            user_profile="",
            episode_summary="",
        )
        all_contexts[text] = ctx
        print(f"\n  📨 [{text}]")
        for k in CONTEXT_KEYS:
            v = ctx.get(k, 0.0)
            bar = "█" * int(abs(v) * 20)
            sign = "-" if v < 0 else " "
            print(f"    {k:25s}: {sign}{abs(v):.2f}  {bar}")

    # Compute pairwise L2 distances
    import math
    print(f"\n{'=' * 60}")
    print("  Pairwise L2 distances (same space as KNN)")
    print(f"{'=' * 60}")
    for i, t1 in enumerate(inputs):
        for t2 in inputs[i+1:]:
            v1 = [all_contexts[t1].get(k, 0.0) for k in CONTEXT_KEYS]
            v2 = [all_contexts[t2].get(k, 0.0) for k in CONTEXT_KEYS]
            dist = math.sqrt(sum((a-b)**2 for a, b in zip(v1, v2)))
            print(f"  {t1:20s} ↔ {t2:20s} = {dist:.4f}")

    # Verdict
    v1 = [all_contexts["你好"].get(k, 0.0) for k in CONTEXT_KEYS]
    v2 = [all_contexts["最近心情不太好"].get(k, 0.0) for k in CONTEXT_KEYS]
    v3 = [all_contexts["你平时喜欢做什么"].get(k, 0.0) for k in CONTEXT_KEYS]
    d12 = math.sqrt(sum((a-b)**2 for a, b in zip(v1, v2)))
    d13 = math.sqrt(sum((a-b)**2 for a, b in zip(v1, v3)))
    d23 = math.sqrt(sum((a-b)**2 for a, b in zip(v2, v3)))
    avg_d = (d12 + d13 + d23) / 3

    print(f"\n  Average distance: {avg_d:.4f}")
    if avg_d > 0.3:
        print("  ✅ 8D has differentiation power → Fix calibrate_genesis.py only")
    elif avg_d > 0.15:
        print("  ⚠️ Marginal — may need semantic layer as supplement")
    else:
        print("  ❌ 8D is flat at turn-1 → Need semantic layer")


if __name__ == "__main__":
    asyncio.run(main())
