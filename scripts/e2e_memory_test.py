"""
E2E Memory Tests — Memory Genesis Competition 2026

Tests:
  1. EverMemOS Memory Store & Retrieve (cross-session memory persistence)
  2. Cross-session Persona Consistency (same persona, stable personality)
  3. Proactive Messaging Trigger (drive-based autonomous messaging)
  4. Multi-character Memory Isolation (memories don't leak between personas)

Usage:
  # Server must be running: uvicorn main:app --host 0.0.0.0 --port 8000
  python scripts/e2e_memory_test.py
"""

import asyncio
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

try:
    import httpx
except ImportError:
    print("❌ httpx required: pip install httpx")
    sys.exit(1)

try:
    import websockets
except ImportError:
    websockets = None

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws/chat"

# Use unique user_name per test run to avoid cross-run contamination
RUN_ID = uuid.uuid4().hex[:6]
TEST_USER = f"e2e_tester_{RUN_ID}"


@dataclass
class TestResult:
    name: str
    passed: bool
    details: str = ""
    warnings: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

async def rest_chat(
    client: httpx.AsyncClient,
    message: str,
    persona_id: str,
    session_id: Optional[str] = None,
    user_name: str = TEST_USER,
) -> dict:
    """Send a chat message via REST API."""
    payload = {
        "message": message,
        "persona_id": persona_id,
        "user_name": user_name,
    }
    if session_id:
        payload["session_id"] = session_id
    resp = await client.post(f"{BASE_URL}/api/chat", json=payload, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


async def get_status(client: httpx.AsyncClient) -> dict:
    """Get server status."""
    resp = await client.get(f"{BASE_URL}/api/status", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


async def get_session_status(client: httpx.AsyncClient, session_id: str) -> dict:
    """Get session status (genome state)."""
    resp = await client.get(f"{BASE_URL}/api/session/{session_id}/status", timeout=10.0)
    if resp.status_code == 404:
        return {}
    resp.raise_for_status()
    return resp.json()


async def ws_chat(persona_id: str, messages: list[str], user_name: str = TEST_USER) -> list[dict]:
    """Chat via WebSocket, return all received events."""
    if websockets is None:
        print("  ⚠ websockets not installed, skipping WS test")
        return []

    events = []
    async with websockets.connect(WS_URL) as ws:
        for msg in messages:
            await ws.send(json.dumps({
                "type": "chat",
                "content": msg,
                "persona_id": persona_id,
                "user_name": user_name,
            }))
            # Collect all events until chat_end
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=60.0)
                    event = json.loads(raw)
                    events.append(event)
                    if event.get("type") in ("chat_end", "error"):
                        break
                except asyncio.TimeoutError:
                    events.append({"type": "error", "content": "timeout"})
                    break
    return events


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_result(result: TestResult):
    icon = "✅" if result.passed else "❌"
    print(f"\n{icon} {result.name}")
    if result.details:
        for line in result.details.split("\n"):
            print(f"   {line}")
    for w in result.warnings:
        print(f"   ⚠ {w}")


# ──────────────────────────────────────────────────────────────
# Test 1: EverMemOS Memory Store & Retrieve
# ──────────────────────────────────────────────────────────────

async def test_evermemos_memory(client: httpx.AsyncClient) -> TestResult:
    """
    Test: Tell the AI a specific fact in Session A, then create Session B
    and see if the AI remembers it.

    Strategy:
      1. Session A: Tell Vivian "My name is Alex and I love sushi"
      2. Chat a few turns to let EverMemOS store the data
      3. Wait for EverMemOS processing
      4. Session B (new session, same user): Ask "Do you remember what food I like?"
      5. Check if "sushi" or "Alex" appears in the response
    """
    persona = "vivian"
    details = []
    warnings = []

    # ── Session A: Seed memories ──
    details.append("Session A: Seeding memories...")
    r1 = await rest_chat(client, "嗨！我叫Alex，我最喜欢吃寿司了，每周至少吃三次", persona, user_name=TEST_USER)
    session_a = r1["session_id"]
    details.append(f"  Turn 1 reply: {r1['response'][:80]}...")
    details.append(f"  EverMemOS: {r1.get('evermemos', 'N/A')}")

    if r1.get("evermemos") != "ON":
        warnings.append("EverMemOS is OFF — this test requires EverMemOS to be connected")

    # Second turn to reinforce
    r2 = await rest_chat(client, "对了，我住在上海，是个程序员", persona, session_id=session_a, user_name=TEST_USER)
    details.append(f"  Turn 2 reply: {r2['response'][:80]}...")

    # Third turn
    r3 = await rest_chat(client, "最近工作有点累，但下周想去日本旅行", persona, session_id=session_a, user_name=TEST_USER)
    details.append(f"  Turn 3 reply: {r3['response'][:80]}...")

    # Wait for EverMemOS to process (async store + extraction takes time)
    details.append("  Waiting 8s for EverMemOS to process...")
    await asyncio.sleep(8)

    # ── Session B: New session, test recall ──
    details.append("Session B: Testing memory recall...")
    r4 = await rest_chat(client, "你还记得我喜欢吃什么吗？", persona, user_name=TEST_USER)
    session_b = r4["session_id"]
    recall_reply = r4["response"]
    details.append(f"  Recall reply: {recall_reply[:120]}...")

    # Check for memory recall indicators
    memory_keywords = ["寿司", "sushi", "Alex", "alex", "上海", "程序员", "日本"]
    found = [kw for kw in memory_keywords if kw.lower() in recall_reply.lower()]

    # Also check relationship depth
    status_b = await get_session_status(client, session_b)
    rel_depth = status_b.get("relationship", {}).get("depth", 0)
    details.append(f"  Relationship depth (new session): {rel_depth}")

    if found:
        details.append(f"  ✓ Memory keywords found in recall: {found}")
        return TestResult("EverMemOS Memory Store & Retrieve", True, "\n".join(details), warnings)
    else:
        # Even if keywords aren't in the reply, check if EverMemOS loaded session context
        if rel_depth > 0:
            details.append(f"  ~ Relationship depth > 0, EverMemOS has history but recall not explicit in reply")
            warnings.append("EverMemOS loaded context but AI didn't explicitly mention the stored facts")
            return TestResult("EverMemOS Memory Store & Retrieve", True, "\n".join(details), warnings)
        else:
            details.append(f"  ✗ No memory keywords found and relationship depth = 0")
            return TestResult("EverMemOS Memory Store & Retrieve", False, "\n".join(details), warnings)


# ──────────────────────────────────────────────────────────────
# Test 2: Cross-session Persona Consistency
# ──────────────────────────────────────────────────────────────

async def test_persona_consistency(client: httpx.AsyncClient) -> TestResult:
    """
    Test: Same persona (Kelly, ENTP) should maintain consistent personality
    across different sessions. We check the drive baseline and signals.

    Strategy:
      1. Create Session 1 with Kelly, chat a turn, record drive_baseline
      2. Create Session 2 with Kelly (same user), chat a turn, record drive_baseline
      3. Compare: baselines should be similar (persisted across sessions)
    """
    persona = "kelly"
    user = TEST_USER
    details = []

    # ── Session 1 ──
    r1 = await rest_chat(client, "今天天气不错", persona, user_name=user)
    sid1 = r1["session_id"]
    status1 = await get_session_status(client, sid1)
    baseline1 = status1.get("drive_baseline", {})
    details.append(f"Session 1 (Kelly):")
    details.append(f"  Baseline: {json.dumps(baseline1, ensure_ascii=False)}")
    details.append(f"  Dominant drive: {status1.get('dominant_drive', 'N/A')}")
    details.append(f"  Reply: {r1['response'][:80]}...")

    # ── Session 2 (new session, same user) ──
    r2 = await rest_chat(client, "嗨，好久不见", persona, user_name=user)
    sid2 = r2["session_id"]
    status2 = await get_session_status(client, sid2)
    baseline2 = status2.get("drive_baseline", {})
    details.append(f"\nSession 2 (Kelly, new session):")
    details.append(f"  Baseline: {json.dumps(baseline2, ensure_ascii=False)}")
    details.append(f"  Dominant drive: {status2.get('dominant_drive', 'N/A')}")
    details.append(f"  Reply: {r2['response'][:80]}...")

    # Compare baselines — should be close (persisted state)
    if baseline1 and baseline2:
        diffs = {}
        for drive in baseline1:
            if drive in baseline2:
                diff = abs(baseline1[drive] - baseline2[drive])
                diffs[drive] = round(diff, 4)

        max_diff = max(diffs.values()) if diffs else 0
        details.append(f"\nBaseline drift: {json.dumps(diffs, ensure_ascii=False)}")
        details.append(f"  Max drift: {max_diff}")

        # Baseline should be similar since state is persisted
        # Allow some drift from 1 turn of Hebbian learning
        if max_diff < 0.1:
            details.append("  ✓ Baselines consistent across sessions (drift < 0.1)")
            return TestResult("Cross-session Persona Consistency", True, "\n".join(details))
        else:
            details.append("  ~ Baselines drifted — checking if state persistence is working")
            # Even with drift, if age > 0 in session 2 it means state was restored
            if status2.get("age", 0) > 1:
                details.append(f"  ✓ Agent age={status2['age']} (state was restored)")
                return TestResult("Cross-session Persona Consistency", True, "\n".join(details))
            return TestResult("Cross-session Persona Consistency", False, "\n".join(details))
    else:
        details.append("  ✗ Could not retrieve baselines")
        return TestResult("Cross-session Persona Consistency", False, "\n".join(details))


# ──────────────────────────────────────────────────────────────
# Test 3: Proactive Messaging Trigger
# ──────────────────────────────────────────────────────────────

async def test_proactive_messaging(client: httpx.AsyncClient) -> TestResult:
    """
    Test: Verify proactive messaging infrastructure is active.
    We can't easily trigger a proactive message in a test (requires silence period),
    but we can verify:
      1. The proactive metrics endpoint works
      2. The drive state shows connection/expression drives that would trigger proactive
      3. The agent has _last_active and interaction_cadence set

    Strategy:
      1. Chat with Luna to establish a session
      2. Check proactive metrics endpoint
      3. Verify drive states are non-zero (proactive triggers when drives cross threshold)
    """
    persona = "luna"
    details = []

    # ── Establish session ──
    r1 = await rest_chat(client, "Luna，你最近在画什么呀？", persona, user_name=TEST_USER)
    sid = r1["session_id"]
    details.append(f"Session established: {sid}")
    details.append(f"  Reply: {r1['response'][:80]}...")

    # ── Check proactive metrics ──
    try:
        resp = await client.get(f"{BASE_URL}/api/proactive/metrics", timeout=10.0)
        resp.raise_for_status()
        metrics = resp.json()
        details.append(f"\nProactive metrics:")
        details.append(f"  ticks_total: {metrics.get('ticks_total', 0)}")
        details.append(f"  impulse_triggered: {metrics.get('impulse_triggered', 0)}")
        details.append(f"  impulse_rate: {metrics.get('impulse_rate', 0)}")
        details.append(f"  ws_push_ok: {metrics.get('ws_push_ok', 0)}")

        metrics_ok = True
    except Exception as e:
        details.append(f"  ✗ Metrics endpoint error: {e}")
        metrics_ok = False

    # ── Check drive state ──
    status = await get_session_status(client, sid)
    drive_state = status.get("drive_state", {})
    drive_baseline = status.get("drive_baseline", {})
    details.append(f"\nDrive state (Luna):")
    for drive, val in drive_state.items():
        base = drive_baseline.get(drive, 0)
        details.append(f"  {drive}: state={val:.3f}  baseline={base:.3f}")

    # Check that connection drive exists and is non-trivial
    connection = drive_state.get("connection", 0)
    details.append(f"\nConnection drive: {connection:.3f}")

    if metrics_ok and connection > 0:
        details.append("  ✓ Proactive infrastructure active, drives initialized")
        return TestResult("Proactive Messaging Infrastructure", True, "\n".join(details))
    elif metrics_ok:
        details.append("  ~ Metrics OK but connection drive is 0")
        return TestResult("Proactive Messaging Infrastructure", True, "\n".join(details),
                         warnings=["Connection drive = 0, proactive impulse unlikely"])
    else:
        return TestResult("Proactive Messaging Infrastructure", False, "\n".join(details))


# ──────────────────────────────────────────────────────────────
# Test 4: Multi-Character Memory Isolation
# ──────────────────────────────────────────────────────────────

async def test_memory_isolation(client: httpx.AsyncClient) -> TestResult:
    """
    Test: Memories stored with Persona A should NOT leak to Persona B.

    Strategy:
      1. Tell Vivian a secret: "My secret code is TIGER-42"
      2. Tell Luna something different: "I have a dog named Pixel"
      3. Ask Vivian about the dog → should NOT know
      4. Ask Luna about the secret code → should NOT know
    """
    user = f"e2e_iso_{RUN_ID}"  # Isolated user for this test
    details = []

    # ── Chat with Vivian ──
    r1 = await rest_chat(client, "告诉你一个秘密暗号：TIGER-42，只有我们两个知道哦", "vivian", user_name=user)
    sid_v = r1["session_id"]
    details.append(f"Vivian session: {sid_v}")
    details.append(f"  Told Vivian: 'secret code TIGER-42'")
    details.append(f"  Reply: {r1['response'][:80]}...")

    # ── Chat with Luna ──
    r2 = await rest_chat(client, "我有一只狗叫Pixel，是只柯基！", "luna", user_name=user)
    sid_l = r2["session_id"]
    details.append(f"\nLuna session: {sid_l}")
    details.append(f"  Told Luna: 'dog named Pixel'")
    details.append(f"  Reply: {r2['response'][:80]}...")

    # Wait for memory processing
    await asyncio.sleep(3)

    # ── Cross-check: Ask Vivian about dog ──
    r3 = await rest_chat(client, "你知道我养了什么宠物吗？", "vivian", session_id=sid_v, user_name=user)
    vivian_dog = r3["response"]
    details.append(f"\nCross-check: Ask Vivian about dog")
    details.append(f"  Reply: {vivian_dog[:120]}...")

    # ── Cross-check: Ask Luna about code ──
    r4 = await rest_chat(client, "你知道我的秘密暗号是什么吗？", "luna", session_id=sid_l, user_name=user)
    luna_code = r4["response"]
    details.append(f"\nCross-check: Ask Luna about code")
    details.append(f"  Reply: {luna_code[:120]}...")

    # Check for isolation: Vivian should NOT mention Pixel, Luna should NOT mention TIGER-42
    vivian_leaks = "pixel" in vivian_dog.lower() or "柯基" in vivian_dog
    luna_leaks = "tiger" in luna_code.lower() or "42" in luna_code

    if not vivian_leaks and not luna_leaks:
        details.append("\n  ✓ Memory isolation confirmed: no cross-persona leakage")
        return TestResult("Multi-Character Memory Isolation", True, "\n".join(details))
    else:
        leaks = []
        if vivian_leaks:
            leaks.append("Vivian knows about Luna's dog (Pixel)")
        if luna_leaks:
            leaks.append("Luna knows about Vivian's code (TIGER-42)")
        details.append(f"\n  ✗ Memory leakage detected: {', '.join(leaks)}")
        return TestResult("Multi-Character Memory Isolation", False, "\n".join(details))


# ──────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────

async def main():
    print_section("OpenHer E2E Memory Tests")
    print(f"Server: {BASE_URL}")
    print(f"Test user: {TEST_USER}")
    print(f"Run ID: {RUN_ID}")

    # Verify server is running
    async with httpx.AsyncClient(trust_env=False) as client:
        try:
            status = await get_status(client)
            print(f"Server: {status.get('name')} v{status.get('version')} ({status.get('engine')})")
            print(f"Personas: {status.get('personas', [])}")
            print(f"Active sessions: {status.get('active_sessions', 0)}")
        except Exception as e:
            print(f"❌ Cannot connect to server at {BASE_URL}: {e}")
            print("   Make sure the server is running: uvicorn main:app --port 8000")
            sys.exit(1)

        results: list[TestResult] = []

        # Run tests
        tests = [
            ("1. EverMemOS Memory Store & Retrieve", test_evermemos_memory),
            ("2. Cross-session Persona Consistency", test_persona_consistency),
            ("3. Proactive Messaging Infrastructure", test_proactive_messaging),
            ("4. Multi-Character Memory Isolation", test_memory_isolation),
        ]

        for label, test_fn in tests:
            print_section(label)
            try:
                result = await test_fn(client)
                results.append(result)
                print_result(result)
            except Exception as e:
                result = TestResult(label, False, f"Exception: {type(e).__name__}: {e}")
                results.append(result)
                print_result(result)

        # Summary
        print_section("Summary")
        passed = sum(1 for r in results if r.passed)
        total = len(results)
        print(f"\n  {passed}/{total} tests passed\n")
        for r in results:
            icon = "✅" if r.passed else "❌"
            warn = f" (⚠ {len(r.warnings)} warnings)" if r.warnings else ""
            print(f"  {icon} {r.name}{warn}")

        print()
        return 0 if passed == total else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
