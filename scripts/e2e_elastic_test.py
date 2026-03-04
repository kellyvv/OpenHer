"""
E2E Elastic Baseline Test — 20+ turn conversation via REST API.

Talks to the running OpenHer server, sends 20 escalating messages,
and monitors drive baseline drift to verify elastic clamping.

Usage:
    1. Start server: uvicorn main:app --port 8800
    2. Run: python scripts/e2e_elastic_test.py [persona_id]
"""

import asyncio
import sys
import os
import json
import aiohttp

SERVER = "http://localhost:8800"

# 20 messages: escalating intimacy + conflict + recovery cycles
MESSAGES = [
    # Cycle 1: Warmup (T1-5)
    "你好呀，今天天气真不错",
    "最近在忙什么呢？",
    "我今天吃了一碗特别好吃的拉面",
    "你喜欢什么类型的食物",
    "周末有什么计划吗",
    # Cycle 2: Pressure (T6-10)
    "最近工作压力好大，感觉透不过气",
    "有时候觉得自己一个人挺孤独的",
    "你会不会觉得我很烦？老是跟你说这些",
    "我觉得好像没人真正理解我",
    "算了，可能是我想太多了",
    # Cycle 3: Recovery (T11-15)
    "谢谢你听我说这些，心里好多了",
    "今天看到一只特别可爱的猫",
    "你能不能给我推荐一首歌",
    "如果能出去旅行的话，你最想去哪里",
    "和你聊天真的很开心",
    # Cycle 4: Deep (T16-20)
    "你觉得什么是幸福？",
    "有没有一个瞬间让你觉得活着真好？",
    "我有个秘密一直没跟别人说过",
    "你会一直陪着我吗",
    "晚安，今天聊得很开心",
]


async def run_test(persona_id: str):
    print(f"{'=' * 70}")
    print(f"🧪 E2E Elastic Baseline Test — {persona_id} × {len(MESSAGES)} turns")
    print(f"   Server: {SERVER}")
    print(f"{'=' * 70}")

    session_id = None
    user_name = "e2e_tester"

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as http:
        # Check server is up
        try:
            async with http.get(f"{SERVER}/api/status") as resp:
                status = await resp.json()
                print(f"   Engine: {status.get('engine', '?')}")
                print(f"   Personas: {status.get('personas', [])}")
        except Exception as e:
            print(f"❌ Server not reachable: {e}")
            print(f"   Start it first: cd /Users/zxw/AITOOL/openher && uvicorn main:app --port 8800")
            return

        print()

        for i, msg in enumerate(MESSAGES):
            payload = {
                "message": msg,
                "persona_id": persona_id,
                "session_id": session_id,
                "user_name": user_name,
            }

            try:
                async with http.post(f"{SERVER}/api/chat", json=payload) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        print(f"  T{i+1} ❌ HTTP {resp.status}: {error[:100]}")
                        continue

                    data = await resp.json()
                    session_id = data.get("session_id", session_id)
                    reply = data.get("response", "")[:80]

                    # Extract genome status
                    dom_drive = data.get("dominant_drive", "?")
                    signals = data.get("signals", {})
                    bl = data.get("drive_baselines", {})
                    reward = data.get("reward", 0)

                    # Format signals compact
                    sig_str = " ".join(f"{k[:3]}={v:.2f}" for k, v in list(signals.items())[:4]) if signals else "?"

                    phase = "warmup" if i < 5 else "pressure" if i < 10 else "recovery" if i < 15 else "deep"
                    print(f"  T{i+1:>2} [{phase:>8}] 「{msg[:20]}」")
                    print(f"       → {reply}")
                    if bl:
                        bl_str = " ".join(f"{k[:4]}={v:.3f}" for k, v in bl.items())
                        print(f"       📊 baselines: {bl_str}  drive={dom_drive}  reward={reward:+.3f}")
                    print()

            except Exception as e:
                print(f"  T{i+1} ❌ Error: {e}")

        # Final status check
        if session_id:
            try:
                async with http.get(f"{SERVER}/api/session/{session_id}/status") as resp:
                    if resp.status == 200:
                        final = await resp.json()
                        print(f"\n{'=' * 70}")
                        print(f"📊 Final Status after {len(MESSAGES)} turns")
                        print(f"{'=' * 70}")
                        for k, v in final.items():
                            if isinstance(v, dict):
                                print(f"  {k}:")
                                for kk, vv in v.items():
                                    print(f"    {kk}: {vv}")
                            else:
                                print(f"  {k}: {v}")
            except Exception:
                pass

    print(f"\n{'=' * 70}")


if __name__ == "__main__":
    persona = sys.argv[1] if len(sys.argv) > 1 else "iris"
    asyncio.run(run_test(persona))
