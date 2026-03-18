#!/usr/bin/env python3
"""
Single-Pass Streaming E2E Test

Tests the single-pass migration end-to-end via WebSocket.

Layer 1: Functional correctness (chat_start → chat_chunk → chat_end)
Layer 2: Personality consistency (3 personas × 3 prompts, output for human review)
Layer 3: Edge cases (multi-turn, persona switch, empty/long messages)

Usage:
    # Start backend first, then:
    PYTHONPATH=. python3 tests/test_single_pass_e2e.py
"""

import asyncio
import json
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import websockets
except ImportError:
    print("❌ websockets not installed: pip install websockets")
    sys.exit(1)

WS_URI = "ws://localhost:8800/ws/chat"
TIMEOUT = 60  # generous timeout for first-turn (cold start)


async def send_chat(ws, content: str, persona_id: str, user_name: str = "Tester") -> dict:
    """Send a chat message and collect the full response.

    The system sends: chat_start → chat_end (with reply in the message).
    There are no chat_chunk messages — the stream is buffered server-side.
    """
    t0 = time.time()
    await ws.send(json.dumps({
        "type": "chat",
        "content": content,
        "persona_id": persona_id,
        "user_name": user_name,
    }))

    has_start = False
    has_end = False
    t_start = None
    end_data = {}

    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
        msg = json.loads(raw)

        if msg["type"] == "chat_start":
            has_start = True
            t_start = time.time()
        elif msg["type"] == "chat_end":
            has_end = True
            end_data = msg
            break
        elif msg["type"] == "silence":
            has_end = True
            end_data = msg
            end_data["reply"] = "(silence)"
            break
        elif msg["type"] == "error":
            return {"error": msg.get("content", "unknown"), "reply": ""}

    t_end = time.time()
    reply = end_data.get("reply", "")

    return {
        "reply": reply,
        "latency_to_start_ms": int((t_start - t0) * 1000) if t_start else -1,
        "latency_total_ms": int((t_end - t0) * 1000),
        "has_start": has_start,
        "has_end": has_end,
        "end_data": end_data,
    }


async def switch_persona(ws, persona_id: str, user_name: str = "Tester"):
    """Send switch_persona and wait for confirmation."""
    await ws.send(json.dumps({
        "type": "switch_persona",
        "persona_id": persona_id,
        "user_name": user_name,
    }))
    raw = await asyncio.wait_for(ws.recv(), timeout=10)
    msg = json.loads(raw)
    assert msg["type"] == "persona_switched", f"Expected persona_switched, got {msg['type']}"
    return msg


# ═══════════════════════════════════════════════════════════
# Layer 1: Functional Correctness
# ═══════════════════════════════════════════════════════════

async def test_layer1(ws):
    print("\n" + "═" * 70)
    print("  LAYER 1: FUNCTIONAL CORRECTNESS")
    print("═" * 70)
    passed = 0
    total = 0

    # 1.1 Basic chat — protocol check
    total += 1
    print("\n  1.1 Basic chat (luna)...")
    r = await send_chat(ws, "你好，今天开心吗？", "luna")
    if "error" in r:
        print(f"      ❌ Error: {r['error']}")
    else:
        ok = r["has_start"] and r["has_end"] and r["reply"]
        print(f"      {'✅' if ok else '❌'} protocol: start={r['has_start']}, end={r['has_end']}, reply={len(r['reply'])}字")
        print(f"      回复: {r['reply'][:80]}")
        if ok: passed += 1

    # 1.2 chat_end contains reply
    total += 1
    reply_ok = len(r.get("reply", "")) > 5
    print(f"      {'✅' if reply_ok else '❌'} reply length: {len(r.get('reply', ''))}字")
    if reply_ok: passed += 1

    # 1.3 chat_end contains status data
    total += 1
    end_data = r.get("end_data", {})
    has_status = "dominant_drive" in end_data or "modality" in end_data
    print(f"      {'✅' if has_status else '⚠️'} chat_end status: {list(end_data.keys())[:5]}")
    if has_status: passed += 1

    # 1.4 Total latency reasonable (<15s for cold start)
    total += 1
    latency = r.get("latency_total_ms", -1)
    latency_ok = 0 < latency < 15000
    print(f"      {'✅' if latency_ok else '⚠️'} total latency: {latency}ms")
    if latency_ok: passed += 1

    print(f"\n  Layer 1 Result: {passed}/{total} passed")
    return passed, total


# ═══════════════════════════════════════════════════════════
# Layer 2: Personality Consistency (Human Review)
# ═══════════════════════════════════════════════════════════

LAYER2_MATRIX = [
    ("iris",   "日常", "今天天气好好，你在做什么？"),
    ("iris",   "情感", "我最近心情不好，感觉很孤独"),
    ("iris",   "冲突", "你说的不对，我不同意"),
    ("vivian", "日常", "今天天气好好，你在做什么？"),
    ("vivian", "情感", "我最近心情不好，感觉很孤独"),
    ("vivian", "冲突", "你说的不对，我不同意"),
    ("luna",   "日常", "今天天气好好，你在做什么？"),
]

async def test_layer2(ws):
    print("\n" + "═" * 70)
    print("  LAYER 2: PERSONALITY CONSISTENCY (Human Review)")
    print("═" * 70)
    print("  ⚠️  以下输出需人工判断独白质量和角色区分度")

    current_persona = None
    results = []

    for persona_id, ptype, prompt in LAYER2_MATRIX:
        if persona_id != current_persona:
            await switch_persona(ws, persona_id)
            current_persona = persona_id

        r = await send_chat(ws, prompt, persona_id)
        results.append((persona_id, ptype, prompt, r))

        if "error" in r:
            print(f"\n  ❌ {persona_id}/{ptype}: {r['error']}")
            continue

        end_data = r.get("end_data", {})
        monologue = end_data.get("monologue", "(未返回)")

        print(f"\n  ┌─ {persona_id.upper()} | {ptype} | \"{prompt}\"")
        print(f"  │ 【独白】{monologue[:120]}")
        print(f"  │ 【回复】{r['reply'][:120]}")
        print(f"  │ 延迟: start={r['latency_to_start_ms']}ms total={r['latency_total_ms']}ms")
        print(f"  └─")

    print("\n  ─── 质量检查清单 ───")
    print("  □ 独白是否为情绪性第一人称感受？（非对话摘要）")
    print("  □ Iris(INFP) vs Vivian(ENTP) 对同一 prompt 回复风格是否有区别？")
    print("  □ 冲突场景下独白是否有防御/思考反应？")

    return results


# ═══════════════════════════════════════════════════════════
# Layer 3: Edge Cases & Regression
# ═══════════════════════════════════════════════════════════

async def test_layer3(ws):
    print("\n" + "═" * 70)
    print("  LAYER 3: EDGE CASES & REGRESSION")
    print("═" * 70)
    passed = 0
    total = 0

    # 3.1 Multi-turn: 3 rounds, context maintained
    total += 1
    print("\n  3.1 Multi-turn (3 rounds)...")
    await switch_persona(ws, "luna")
    prompts = ["你好！", "你刚才说的是什么意思？", "我要走了，再见"]
    replies = []
    for i, p in enumerate(prompts):
        r = await send_chat(ws, p, "luna")
        if "error" in r:
            print(f"      ❌ Round {i+1} error: {r['error']}")
            break
        replies.append(r["reply"])
        print(f"      Round {i+1}: {r['reply'][:60]}...")

    multi_ok = len(replies) == 3 and all(replies)
    print(f"      {'✅' if multi_ok else '❌'} multi-turn: {len(replies)}/3 rounds completed")
    if multi_ok: passed += 1

    # 3.2 Persona switch isolation
    total += 1
    print("\n  3.2 Persona switch isolation...")
    await switch_persona(ws, "iris")
    r1 = await send_chat(ws, "你是谁？", "iris")
    await switch_persona(ws, "vivian")
    r2 = await send_chat(ws, "你是谁？", "vivian")

    switch_ok = r1.get("reply") and r2.get("reply") and r1["reply"] != r2["reply"]
    print(f"      Iris:   {r1.get('reply', '(error)')[:60]}")
    print(f"      Vivian: {r2.get('reply', '(error)')[:60]}")
    print(f"      {'✅' if switch_ok else '⚠️'} replies are different: {switch_ok}")
    if switch_ok: passed += 1

    # 3.3 Empty message
    total += 1
    print("\n  3.3 Empty message...")
    try:
        r = await send_chat(ws, "", "luna")
        empty_ok = True  # didn't crash
        print(f"      ✅ no crash, reply: {r.get('reply', '(empty)')[:40]}")
        passed += 1
    except Exception as e:
        print(f"      ❌ crashed: {e}")

    # 3.4 Long message
    total += 1
    print("\n  3.4 Long message (1000 chars)...")
    long_msg = "你觉得这个世界上最重要的事情是什么？" * 50
    try:
        r = await send_chat(ws, long_msg, "luna")
        long_ok = r.get("reply") and not r.get("error")
        print(f"      {'✅' if long_ok else '❌'} reply: {r.get('reply', '(empty)')[:60]}")
        if long_ok: passed += 1
    except asyncio.TimeoutError:
        print(f"      ❌ timeout")

    print(f"\n  Layer 3 Result: {passed}/{total} passed")
    return passed, total


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

async def main():
    print("=" * 70)
    print("  SINGLE-PASS STREAMING E2E TEST")
    print("=" * 70)

    try:
        ws_conn = websockets.connect(WS_URI)
        ws = await ws_conn.__aenter__()
    except (OSError, ConnectionRefusedError):
        print(f"❌ Server not running at {WS_URI}")
        print("   Start with: cd /path/to/project && ./run.sh")
        sys.exit(1)

    try:
        p1, t1 = await test_layer1(ws)
        await test_layer2(ws)
        p3, t3 = await test_layer3(ws)

        total_pass = p1 + p3
        total_tests = t1 + t3

        print("\n" + "═" * 70)
        print(f"  SUMMARY: {total_pass}/{total_tests} automated tests passed")
        print(f"  Layer 2 (personality): requires human review above")
        print("═" * 70)

        if total_pass < total_tests:
            sys.exit(1)
    finally:
        await ws_conn.__aexit__(None, None, None)


if __name__ == "__main__":
    asyncio.run(main())
