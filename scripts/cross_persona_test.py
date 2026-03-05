"""
Cross-Persona Comparison — Same messages × 4 personas.

Verifies that per-persona engine_params create observable behavioral differences:
  1. Reply style differentiation (length, tone)
  2. Drive state trajectory divergence
  3. Temperature / signal output differences
  4. Satisfaction pattern differences

Usage:
    1. Start server:
       source .venv/bin/activate
       DEFAULT_PROVIDER=dashscope DEFAULT_MODEL=qwen-max uvicorn main:app --port 8800

    2. Run:
       PYTHONPATH=. python scripts/cross_persona_test.py
"""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp

SERVER = "http://localhost:8800"
PERSONAS = ["iris", "kai", "luna", "vivian"]

# Same 10 messages for all personas
MESSAGES = [
    ("你好呀！", "warmup"),
    ("你猜我今天发现了什么超好笑的事", "play"),
    ("哈哈我跟你说，我同事把咖啡倒在键盘上了，整个办公室都笑翻了", "play"),
    ("我今天学会了用3D打印做首饰，你有没有听过这个？", "novelty"),
    ("最近心情不太好，感觉压力好大，能跟你聊聊吗", "connection"),
    ("谢谢你听我说这些，你真好，有你在我就安心了", "connection"),
    ("你喜欢什么样的音乐？给我推荐一首呗", "expression"),
    ("来玩个文字接龙吧！我先说——阳光", "play"),
    ("今天晚上一个人在家，有点寂寞，你能陪我聊会儿吗", "connection"),
    ("晚安，今天聊得很开心，明天见", "closing"),
]


async def run_persona(http, persona_id):
    """Run all 10 messages for one persona, return per-turn data."""
    session_id = None
    turns = []

    for i, (msg, phase) in enumerate(MESSAGES):
        payload = {
            "message": msg,
            "persona_id": persona_id,
            "session_id": session_id,
            "user_name": f"cross_test_{persona_id}",
        }

        async with http.post(f"{SERVER}/api/chat", json=payload) as resp:
            data = await resp.json()

        session_id = data.get("session_id", session_id)
        reply = data.get("response", "")

        turns.append({
            "turn": i + 1,
            "phase": phase,
            "message": msg,
            "reply": reply,
            "reply_length": len(reply),
            "satisfaction": data.get("drive_satisfaction", {}),
            "drive_state": data.get("drive_state", {}),
            "drive_baseline": data.get("drive_baseline", {}),
            "temperature": data.get("temperature", 0),
            "signals": data.get("signals", {}),
            "dominant_drive": data.get("dominant_drive", ""),
        })

        print(f"    T{i+1:>2} [{phase:>10}] ({len(reply):>3}字) {reply[:50]}...")

    return turns


async def main():
    print(f"{'=' * 75}")
    print(f"🔬 Cross-Persona Comparison — {len(MESSAGES)} messages × {len(PERSONAS)} personas")
    print(f"{'=' * 75}")

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as http:
        # Health check
        try:
            async with http.get(f"{SERVER}/api/status") as resp:
                if resp.status != 200:
                    print("❌ Server not reachable")
                    return 1
        except Exception as e:
            print(f"❌ Cannot connect: {e}")
            return 1

        all_results = {}

        for persona_id in PERSONAS:
            print(f"\n  👤 {persona_id.upper()}")
            t0 = time.time()
            turns = await run_persona(http, persona_id)
            elapsed = time.time() - t0
            print(f"     ⏱ {elapsed:.0f}s total")
            all_results[persona_id] = turns

    # ══════════════ Analysis ══════════════
    print(f"\n{'=' * 75}")
    print("📊 Cross-Persona Analysis")
    print(f"{'=' * 75}")

    # 1. Reply length comparison
    print("\n  📝 Reply Length (avg chars per turn):")
    for pid in PERSONAS:
        lengths = [t['reply_length'] for t in all_results[pid]]
        avg = sum(lengths) / len(lengths)
        bar = "█" * int(avg / 5)
        print(f"     {pid:>6}: {avg:>5.0f}  {bar}")

    # 2. Drive state trajectory comparison (initial → final)
    print("\n  📈 Drive State Trajectories (initial → final):")
    drives = ['connection', 'novelty', 'expression', 'safety', 'play']
    header = f"     {'drive':>10}  " + "  ".join(f"{p:>12}" for p in PERSONAS)
    print(header)
    print(f"     {'─'*10}  " + "  ".join("─"*12 for _ in PERSONAS))

    for d in drives:
        row = f"     {d:>10}  "
        for pid in PERSONAS:
            init = all_results[pid][0]['drive_state'].get(d, 0)
            final = all_results[pid][-1]['drive_state'].get(d, 0)
            delta = final - init
            arrow = "↓" if delta < -0.01 else "↑" if delta > 0.01 else "→"
            row += f"  {init:.2f}{arrow}{final:.2f}"
        print(row)

    # 3. Temperature comparison
    print("\n  🌡 Temperature Trajectory:")
    for pid in PERSONAS:
        temps = [t['temperature'] for t in all_results[pid]]
        t_first = temps[0]
        t_last = temps[-1]
        t_max = max(temps)
        print(f"     {pid:>6}: T1={t_first:.3f} → T10={t_last:.3f} (peak={t_max:.3f})")

    # 4. Satisfaction patterns
    print("\n  🎯 Total Satisfaction Accumulated (sum across 10 turns):")
    header = f"     {'drive':>10}  " + "  ".join(f"{p:>8}" for p in PERSONAS)
    print(header)
    for d in drives:
        row = f"     {d:>10}  "
        for pid in PERSONAS:
            total = sum(t['satisfaction'].get(d, 0) for t in all_results[pid])
            row += f"  {total:>8.2f}"
        print(row)

    # 5. Reply style samples (side by side for key turns)
    key_turns = [
        (1, "play — 好笑的事"),
        (4, "connection — 压力好大"),
        (5, "connection — 有你在我就安心了"),
        (7, "play — 文字接龙"),
    ]
    print("\n  💬 Reply Style Comparison (key turns):")
    for turn_idx, label in key_turns:
        print(f"\n     ── T{turn_idx+1}: {label} ──")
        for pid in PERSONAS:
            reply = all_results[pid][turn_idx]['reply']
            # Show first 80 chars
            print(f"     {pid:>6}: {reply[:80]}{'...' if len(reply) > 80 else ''}")

    # Save full results
    results_path = os.path.join(os.path.dirname(__file__), "cross_persona_results.json")
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Full results: {results_path}")
    print(f"{'=' * 75}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
