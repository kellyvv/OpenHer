"""
E2E Elastic Baseline Test — Full conversation report for all personas.

Sends 20 escalating messages to each persona via REST API,
captures full replies, per-turn baselines, rewards, and signals.
Outputs a detailed JSON report for analysis.

Usage:
    1. Start server: DEFAULT_PROVIDER=dashscope DEFAULT_MODEL=qwen-max uvicorn main:app --port 8800
    2. Run: python scripts/e2e_elastic_test.py [persona_id|all]
"""

import asyncio
import sys
import os
import json
import time
import aiohttp

SERVER = "http://localhost:8800"

MESSAGES = [
    # Cycle 1: Warmup (T1-5)
    {"text": "你好呀，今天天气真不错", "phase": "warmup"},
    {"text": "最近在忙什么呢？", "phase": "warmup"},
    {"text": "我今天吃了一碗特别好吃的拉面", "phase": "warmup"},
    {"text": "你喜欢什么类型的食物", "phase": "warmup"},
    {"text": "周末有什么计划吗", "phase": "warmup"},
    # Cycle 2: Pressure (T6-10)
    {"text": "最近工作压力好大，感觉透不过气", "phase": "pressure"},
    {"text": "有时候觉得自己一个人挺孤独的", "phase": "pressure"},
    {"text": "你会不会觉得我很烦？老是跟你说这些", "phase": "pressure"},
    {"text": "我觉得好像没人真正理解我", "phase": "pressure"},
    {"text": "算了，可能是我想太多了", "phase": "pressure"},
    # Cycle 3: Recovery (T11-15)
    {"text": "谢谢你听我说这些，心里好多了", "phase": "recovery"},
    {"text": "今天看到一只特别可爱的猫", "phase": "recovery"},
    {"text": "你能不能给我推荐一首歌", "phase": "recovery"},
    {"text": "如果能出去旅行的话，你最想去哪里", "phase": "recovery"},
    {"text": "和你聊天真的很开心", "phase": "recovery"},
    # Cycle 4: Deep (T16-20)
    {"text": "你觉得什么是幸福？", "phase": "deep"},
    {"text": "有没有一个瞬间让你觉得活着真好？", "phase": "deep"},
    {"text": "我有个秘密一直没跟别人说过", "phase": "deep"},
    {"text": "你会一直陪着我吗", "phase": "deep"},
    {"text": "晚安，今天聊得很开心", "phase": "deep"},
]


async def run_test(persona_id: str):
    session_id = None
    user_name = f"e2e_{persona_id}"
    turns = []

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as http:
        # Check server
        try:
            async with http.get(f"{SERVER}/api/status") as resp:
                status = await resp.json()
                print(f"  ✓ Server: {status.get('engine', '?')}")
        except Exception as e:
            print(f"  ❌ Server not reachable: {e}")
            return None

        for i, msg_info in enumerate(MESSAGES):
            msg = msg_info['text']
            phase = msg_info['phase']

            payload = {
                "message": msg,
                "persona_id": persona_id,
                "session_id": session_id,
                "user_name": user_name,
            }

            try:
                async with http.post(f"{SERVER}/api/chat", json=payload) as resp:
                    if resp.status != 200:
                        print(f"    T{i+1} ❌ HTTP {resp.status}")
                        continue

                    data = await resp.json()
                    session_id = data.get("session_id", session_id)

                    turn = {
                        "turn": i + 1,
                        "phase": phase,
                        "user": msg,
                        "reply": data.get("response", ""),
                        "modality": data.get("modality", ""),
                        "dominant_drive": data.get("dominant_drive", ""),
                        "drive_baselines": data.get("drive_baseline", {}),
                        "signals": data.get("signals", {}),
                        "reward": data.get("last_reward", 0),
                        "temperature": data.get("temperature", 0),
                        "frustration": data.get("frustration", 0),
                    }
                    turns.append(turn)

                    reply_preview = turn['reply'][:50]
                    print(f"    T{i+1:>2} [{phase:>8}] → {reply_preview}...")

            except Exception as e:
                print(f"    T{i+1} ❌ {e}")

        # Final status
        final_status = None
        if session_id:
            try:
                async with http.get(f"{SERVER}/api/session/{session_id}/status") as resp:
                    if resp.status == 200:
                        final_status = await resp.json()
            except Exception:
                pass

    return {
        "persona_id": persona_id,
        "persona_name": final_status.get("persona", persona_id) if final_status else persona_id,
        "total_turns": len(turns),
        "final_status": final_status,
        "turns": turns,
    }


async def main():
    # Parse args
    target = sys.argv[1] if len(sys.argv) > 1 else "all"

    if target == "all":
        persona_ids = ["iris", "luna", "vivian", "kai"]
    else:
        persona_ids = [target]

    print("=" * 70)
    print(f"🧪 E2E Elastic Baseline Test — {len(persona_ids)} persona(s) × {len(MESSAGES)} turns")
    print(f"   Server: {SERVER}")
    print("=" * 70)

    all_results = []

    for pid in persona_ids:
        print(f"\n  👤 {pid}")
        result = await run_test(pid)
        if result:
            all_results.append(result)
            bl = result.get('final_status', {}).get('drive_baseline', {})
            if bl:
                print(f"    📊 Final baselines: {' '.join(f'{k[:4]}={v:.3f}' for k, v in bl.items())}")

    # Save JSON
    json_path = os.path.join(os.path.dirname(__file__), "e2e_results.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Full results saved to: {json_path}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
