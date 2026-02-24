"""
WebSocket integration test — Tests end-to-end chat via WebSocket protocol.
"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_websocket():
    import websockets

    print("=" * 60)
    print("WebSocket 端到端测试")
    print("=" * 60)

    uri = "ws://localhost:8800/ws/chat"

    async with websockets.connect(uri) as ws:
        # ── Test 1: Chat with xiaoyun ──
        print("\n📤 发送聊天消息 → 小云")
        await ws.send(json.dumps({
            "type": "chat",
            "content": "嘿，在干嘛呢？",
            "persona_id": "xiaoyun",
            "user_name": "测试用户",
        }))

        # Collect response
        full_response = ""
        chat_started = False
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            msg = json.loads(raw)

            if msg["type"] == "chat_start":
                print(f"  ✅ chat_start, session: {msg['session_id']}")
                chat_started = True
            elif msg["type"] == "chat_chunk":
                full_response += msg["content"]
            elif msg["type"] == "chat_end":
                print(f"  💬 小云: {full_response}")
                print(f"  📊 情绪: {msg['emotion']}, 亲密度: {msg['intimacy']}")
                break
            elif msg["type"] == "error":
                print(f"  ❌ Error: {msg['content']}")
                break

        assert chat_started, "Should have received chat_start"
        assert full_response, "Should have received response content"

        # ── Test 2: Switch to lingling ──
        print("\n📤 切换角色 → 玲玲")
        await ws.send(json.dumps({
            "type": "switch_persona",
            "persona_id": "lingling",
            "user_name": "测试用户",
        }))

        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        msg = json.loads(raw)
        assert msg["type"] == "persona_switched"
        print(f"  ✅ 切换成功: {msg['persona']}, session: {msg['session_id']}")

        # ── Test 3: Chat with lingling ──
        print("\n📤 和玲玲聊天")
        await ws.send(json.dumps({
            "type": "chat",
            "content": "你好啊玲玲",
        }))

        full_response = ""
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            msg = json.loads(raw)
            if msg["type"] == "chat_start":
                pass
            elif msg["type"] == "chat_chunk":
                full_response += msg["content"]
            elif msg["type"] == "chat_end":
                print(f"  💬 玲玲: {full_response}")
                print(f"  📊 情绪: {msg['emotion']}, 亲密度: {msg['intimacy']}")
                break

        assert full_response, "Lingling should respond"

        # ── Test 4: Status check ──
        print("\n📤 查询状态")
        await ws.send(json.dumps({"type": "status"}))
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        msg = json.loads(raw)
        print(f"  ✅ 状态: {msg}")

    print(f"\n{'=' * 60}")
    print("🎉 WebSocket 测试全部通过!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(test_websocket())
