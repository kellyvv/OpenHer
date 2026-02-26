"""
Live test: actually calls the LLM with the full persona pipeline.
Tests: PersonaLoader → Genome Engine → LLM → Response
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
    print("OpenHer Live Chat Test")
    print("=" * 60)

    # 1. Load persona (use first available)
    personas_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "personas")
    loader = PersonaLoader(personas_dir)
    personas = loader.load_all()
    print(f"\n✅ Loaded {len(personas)} personas: {list(personas.keys())}")

    persona_id = list(personas.keys())[0]
    persona = loader.get(persona_id)
    print(f"✅ Selected persona: {persona.name} ({persona_id})")
    if persona.drive_baseline:
        print(f"   Drive baseline: {persona.drive_baseline}")

    # 2. Create LLM client
    llm = LLMClient(provider="dashscope", model="qwen-max")

    # 3. Create chat agent
    agent = ChatAgent(
        persona=persona,
        llm=llm,
        user_id="test_user",
        user_name="Tester",
    )

    # 4. Multi-turn conversation test
    test_messages = [
        "Hey, who are you?",
        "I've been working overtime all week, just got home...",
        "Thanks for caring~ What do you usually do for fun?",
    ]

    for i, msg in enumerate(test_messages, 1):
        print(f"\n{'─' * 50}")
        print(f"👤 User [{i}]: {msg}")

        print(f"💬 {persona.name}: ", end="", flush=True)
        for chunk in agent.chat_stream(msg):
            print(chunk, end="", flush=True)
        print()

        status = agent.get_status()
        print(f"   📊 Turn: {status['turn_count']} | Drive: {status['dominant_drive']}")

    print(f"\n{'=' * 60}")
    print("🎉 Live chat test complete!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
