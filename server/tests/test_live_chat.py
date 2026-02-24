"""
Live test: actually calls the LLM with the full persona pipeline.
Tests: PersonaLoader → EmotionState → Intimacy → PromptBuilder → LLM → Response
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from core.persona import PersonaLoader
from core.llm import LLMClient
from core.agent.chat_agent import ChatAgent


def main():
    print("=" * 60)
    print("OpenHer 模型接入实测")
    print("=" * 60)

    # 1. Load persona
    personas_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "personas")
    loader = PersonaLoader(personas_dir)
    personas = loader.load_all()
    print(f"\n✅ 加载了 {len(personas)} 个角色: {list(personas.keys())}")

    xiaoyun = loader.get("xiaoyun")
    print(f"✅ 选择角色: {xiaoyun.name}")

    # 2. Create LLM client
    llm = LLMClient(provider="dashscope", model="qwen-max")

    # 3. Create chat agent
    agent = ChatAgent(
        persona=xiaoyun,
        llm=llm,
        user_id="test_user",
        user_name="小哥哥",
    )

    # 4. Multi-turn conversation test
    test_messages = [
        "你好呀，你是谁？",
        "今天上班好累啊，加班到现在才回来",
        "谢谢你关心～你平时都会做什么呀？",
    ]

    for i, msg in enumerate(test_messages, 1):
        print(f"\n{'─' * 50}")
        print(f"👤 用户 [{i}]: {msg}")

        # Streaming response
        print(f"💬 {xiaoyun.name}: ", end="", flush=True)
        for chunk in agent.chat_stream(msg):
            print(chunk, end="", flush=True)
        print()

        # Show agent status
        status = agent.get_status()
        print(f"   📊 情绪: {status['emotion']} | 亲密度: {status['intimacy_level']} (XP: {status['intimacy_xp']})")

    print(f"\n{'=' * 60}")
    print("🎉 模型接入测试完成!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
