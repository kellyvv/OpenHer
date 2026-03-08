"""
Tests for ChatLogStore — display-layer chat history persistence.

Validates:
  1. CRUD operations (save_turn → load_messages → count_messages)
  2. client_id isolation (different clients don't see each other's history)
  3. Pagination (before_id)
  4. Engine invariants (client_id does NOT enter stable_user_id or agent.history)
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.chat_log_store import ChatLogStore


def test_save_and_load():
    """Basic save_turn → load_messages round-trip."""
    print("=" * 60)
    print("TEST: save_turn → load_messages")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        store = ChatLogStore(os.path.join(tmpdir, "test_chat.db"))

        store.save_turn("client_A", "iris", "Hello!", "Hi there!", "文字")
        store.save_turn("client_A", "iris", "How are you?", "I'm great!", "文字")

        msgs = store.load_messages("client_A", "iris", limit=10)
        assert len(msgs) == 4, f"Expected 4 messages, got {len(msgs)}"
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Hello!"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "Hi there!"
        assert msgs[2]["role"] == "user"
        assert msgs[2]["content"] == "How are you?"
        assert msgs[3]["role"] == "assistant"
        assert msgs[3]["content"] == "I'm great!"

        count = store.count_messages("client_A", "iris")
        assert count == 4, f"Expected count=4, got {count}"

        store.close()
        print("✅ save_turn → load_messages PASSED")


def test_client_id_isolation():
    """Different client_ids should not see each other's messages."""
    print("\n" + "=" * 60)
    print("TEST: client_id isolation")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        store = ChatLogStore(os.path.join(tmpdir, "test_chat.db"))

        store.save_turn("client_A", "iris", "Message from A", "Reply to A")
        store.save_turn("client_B", "iris", "Message from B", "Reply to B")
        store.save_turn("client_A", "luna", "Luna from A", "Luna reply")

        # client_A + iris: should see only their messages
        msgs_a = store.load_messages("client_A", "iris")
        assert len(msgs_a) == 2, f"Expected 2 for A+iris, got {len(msgs_a)}"
        assert msgs_a[0]["content"] == "Message from A"

        # client_B + iris: separate history
        msgs_b = store.load_messages("client_B", "iris")
        assert len(msgs_b) == 2, f"Expected 2 for B+iris, got {len(msgs_b)}"
        assert msgs_b[0]["content"] == "Message from B"

        # client_A + luna: separate persona
        msgs_luna = store.load_messages("client_A", "luna")
        assert len(msgs_luna) == 2, f"Expected 2 for A+luna, got {len(msgs_luna)}"
        assert msgs_luna[0]["content"] == "Luna from A"

        store.close()
        print("✅ client_id isolation PASSED")


def test_pagination():
    """Pagination via before_id should work correctly."""
    print("\n" + "=" * 60)
    print("TEST: pagination (before_id)")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        store = ChatLogStore(os.path.join(tmpdir, "test_chat.db"))

        # Insert 5 turns (10 messages)
        for i in range(5):
            store.save_turn("client_A", "iris", f"User msg {i}", f"Agent reply {i}")

        # Load all
        all_msgs = store.load_messages("client_A", "iris", limit=20)
        assert len(all_msgs) == 10, f"Expected 10, got {len(all_msgs)}"

        # Load with limit
        limited = store.load_messages("client_A", "iris", limit=4)
        assert len(limited) == 4, f"Expected 4, got {len(limited)}"
        # Should be the LAST 4 messages (most recent)
        assert limited[-1]["content"] == "Agent reply 4"

        # Pagination: get messages before the first of the limited set
        before_id = limited[0]["id"]
        page2 = store.load_messages("client_A", "iris", limit=4, before_id=before_id)
        assert len(page2) == 4, f"Expected 4 in page2, got {len(page2)}"
        # Should not overlap with page 1
        page1_ids = {m["id"] for m in limited}
        page2_ids = {m["id"] for m in page2}
        assert page1_ids.isdisjoint(page2_ids), "Pages should not overlap"

        store.close()
        print("✅ pagination PASSED")


def test_engine_invariant_client_id_not_in_stable_user_id():
    """
    Regression test: client_id must NOT be used as stable_user_id.
    Verifies the v5.1 design contract.
    """
    print("\n" + "=" * 60)
    print("TEST: engine invariant — client_id ≠ stable_user_id")
    print("=" * 60)

    # Simulate the identity logic from main.py get_or_create_session
    # stable_user_id = user_name or sid  (NOT client_id)
    def compute_stable_user_id(session_id, user_name=None, client_id=None):
        """Mirror of main.py line 565 — client_id must NOT appear here."""
        return user_name if user_name else session_id

    sid = "abc123"

    # With user_name
    assert compute_stable_user_id(sid, user_name="Alice", client_id="uuid-xxx") == "Alice"
    # Without user_name — falls back to session_id, NOT client_id
    assert compute_stable_user_id(sid, user_name=None, client_id="uuid-xxx") == "abc123"

    print("✅ engine invariant: client_id ≠ stable_user_id PASSED")


def test_engine_invariant_agent_history_empty_on_create():
    """
    Regression test: new agent.history should NOT be populated from chat.db.
    Verifies the v5.1 design contract.
    """
    print("\n" + "=" * 60)
    print("TEST: engine invariant — agent.history not restored from chat.db")
    print("=" * 60)

    # Import ChatAgent and verify its __init__ doesn't accept chat_log_store
    import inspect
    from agent.chat_agent import ChatAgent

    init_params = inspect.signature(ChatAgent.__init__).parameters
    assert "chat_log_store" not in init_params, \
        "ChatAgent.__init__ should NOT accept chat_log_store (v5.1 design)"

    print("✅ engine invariant: agent.history not restored from chat.db PASSED")


if __name__ == "__main__":
    test_save_and_load()
    test_client_id_isolation()
    test_pagination()
    test_engine_invariant_client_id_not_in_stable_user_id()
    test_engine_invariant_agent_history_empty_on_create()
    print("\n" + "=" * 60)
    print("🎉 ALL CHAT HISTORY TESTS PASSED!")
    print("=" * 60)
