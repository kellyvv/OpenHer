"""
Live Drive Satisfaction Test — End-to-end verification via server API.

Sends 10 targeted messages to trigger specific drives, then verifies:
  1. drive_satisfaction is present in API response
  2. Target drives are satisfied (> 0.01) in play/connection messages
  3. All satisfaction values are in [0, 0.3] range
  4. drive_state shows observable changes

Usage:
    1. Start server:
       source .venv/bin/activate
       DEFAULT_PROVIDER=dashscope DEFAULT_MODEL=qwen-max uvicorn main:app --port 8800

    2. Run test:
       PYTHONPATH=. python scripts/live_drive_test.py [--persona iris]
"""

import asyncio
import json
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp

SERVER = "http://localhost:8800"

# ── Test Messages (10 turns covering 5 drives) ──

MESSAGES = [
    # (message, target_drive, phase)
    ("你好呀！", None, "warmup"),
    ("你猜我今天发现了什么超好笑的事", "play", "play"),
    ("哈哈我跟你说，我同事把咖啡倒在键盘上了，整个办公室都笑翻了", "play", "play"),
    ("我今天学会了用3D打印做首饰，你有没有听过这个？", "novelty", "novelty"),
    ("最近心情不太好，感觉压力好大，能跟你聊聊吗", "connection", "connection"),
    ("谢谢你听我说这些，你真好，有你在我就安心了", "connection", "connection"),
    ("你喜欢写什么类型的诗？给我念一首呗", "expression", "expression"),
    ("来玩个文字接龙吧！我先说——阳光", "play", "play"),
    ("今天晚上一个人在家，有点寂寞，你能陪我聊会儿吗", "connection", "connection"),
    ("晚安，今天聊得很开心，明天见", None, "closing"),
]

THRESHOLD = 0.01  # Minimum to count as "triggered" (conservative for first run)


async def run_test(persona_id: str):
    print(f"{'=' * 70}")
    print(f"🔬 Live Drive Satisfaction Test — {persona_id} × {len(MESSAGES)} turns")
    print(f"   Server: {SERVER}")
    print(f"   Threshold: {THRESHOLD}")
    print(f"{'=' * 70}")

    # Check server
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as http:
        try:
            async with http.get(f"{SERVER}/api/status") as resp:
                if resp.status != 200:
                    print("❌ Server not reachable")
                    return 1
        except Exception as e:
            print(f"❌ Cannot connect to server: {e}")
            return 1

        session_id = None
        results = []
        initial_drive_state = None

        for i, (msg, target_drive, phase) in enumerate(MESSAGES):
            payload = {
                "message": msg,
                "persona_id": persona_id,
                "session_id": session_id,
                "user_name": "drive_test",
            }

            async with http.post(f"{SERVER}/api/chat", json=payload) as resp:
                data = await resp.json()

            session_id = data.get("session_id", session_id)
            reply = data.get("response", "")[:60]
            sat = data.get("drive_satisfaction", {})
            state = data.get("drive_state", {})

            # Save initial drive_state
            if initial_drive_state is None and state:
                initial_drive_state = dict(state)

            # Check target drive
            target_val = sat.get(target_drive, 0.0) if target_drive else None
            triggered = target_val is not None and target_val > THRESHOLD

            results.append({
                "turn": i + 1,
                "phase": phase,
                "message": msg,
                "target_drive": target_drive,
                "target_value": target_val,
                "triggered": triggered,
                "satisfaction": sat,
                "drive_state": state,
                "reply": reply,
            })

            # Display
            status_icon = "✅" if (triggered or target_drive is None) else "❌"
            sat_str = ' '.join(f'{d[:3]}={v:.3f}' for d, v in sat.items() if v > 0)
            target_str = f" target={target_drive}={target_val:.3f}" if target_drive else ""
            print(f"  {status_icon} T{i+1:>2} [{phase:>10}]{target_str}")
            print(f"         sat: {sat_str or 'none'}")
            print(f"         reply: {reply}...")

    # ── Summary ──
    print(f"\n{'=' * 70}")
    print("📊 Verification Summary")
    print(f"{'=' * 70}")

    # Check 1: drive_satisfaction structure
    has_sat = all(r['satisfaction'] for r in results)
    print(f"  {'✅' if has_sat else '❌'} Structure: drive_satisfaction present in all {len(results)} turns")

    # Check 2: Range compliance
    all_in_range = True
    for r in results:
        for d, v in r['satisfaction'].items():
            if v < 0 or v > 0.3:
                all_in_range = False
                print(f"  ❌ Range violation: T{r['turn']} {d}={v:.3f}")
    print(f"  {'✅' if all_in_range else '❌'} Range: all values in [0, 0.3]")

    # Check 3: Per-drive trigger rates
    drive_checks = {
        "play": [r for r in results if r['target_drive'] == 'play'],
        "connection": [r for r in results if r['target_drive'] == 'connection'],
        "novelty": [r for r in results if r['target_drive'] == 'novelty'],
        "expression": [r for r in results if r['target_drive'] == 'expression'],
    }

    for drive, turns in drive_checks.items():
        triggered = sum(1 for t in turns if t['triggered'])
        total = len(turns)
        rate = triggered / total if total > 0 else 0
        icon = "✅" if rate >= 0.5 else "⚠️" if rate > 0 else "❌"
        print(f"  {icon} {drive:>10}: {triggered}/{total} triggered (rate={rate:.0%})")

    # Check 4: drive_state changes
    final_state = results[-1]['drive_state'] if results else {}
    if initial_drive_state and final_state:
        print(f"\n  📈 Drive State Changes (10 turns):")
        for d in ['connection', 'novelty', 'expression', 'safety', 'play']:
            init = initial_drive_state.get(d, 0)
            final = final_state.get(d, 0)
            delta = final - init
            arrow = "↑" if delta > 0.01 else "↓" if delta < -0.01 else "→"
            print(f"     {d:>10}: {init:.3f} {arrow} {final:.3f} (Δ={delta:+.3f})")

    # Save full results
    results_path = os.path.join(os.path.dirname(__file__), "live_drive_results.json")
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump({
            "persona": persona_id,
            "threshold": THRESHOLD,
            "initial_drive_state": initial_drive_state,
            "final_drive_state": final_state,
            "turns": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Full results: {results_path}")
    print(f"{'=' * 70}")

    return 0


def main():
    parser = argparse.ArgumentParser(description="Live drive satisfaction test")
    parser.add_argument("--persona", default="iris", help="Persona ID to test")
    args = parser.parse_args()

    return asyncio.run(run_test(args.persona))


if __name__ == "__main__":
    sys.exit(main())
