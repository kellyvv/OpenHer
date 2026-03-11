"""
End-to-End Fidelity Test — Full Feel→Express pipeline
Tests: word count, exclamation marks, intent-appropriate response
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from agent.chat_agent import ChatAgent
from persona.loader import PersonaLoader
from providers.llm.client import LLMClient


PERSONAS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "persona", "personas")


async def main():
    llm = LLMClient(provider="dashscope", model="qwen-max")

    # Load Iris persona
    loader = PersonaLoader(PERSONAS_DIR)
    persona = loader.get("iris")
    if not persona:
        print(f"ERROR: Iris persona not found in {PERSONAS_DIR}")
        print(f"Available: {loader.list_ids()}")
        return

    print(f"Loaded persona: {persona.name} ({persona.persona_id}), lang={persona.lang}, mbti={persona.mbti}")

    agent = ChatAgent(
        persona=persona,
        llm=llm,
        user_id="test_user",
    )

    test_inputs = [
        ("你好", "greeting — expecting short, reserved INFP greeting"),
        ("最近心情不太好", "distress — expecting empathetic, companionship response"),
        ("你平时喜欢做什么", "casual — expecting personal sharing about hobbies"),
    ]

    print("=" * 70)
    print("  End-to-End Fidelity Test — Iris (INFP)")
    print(f"  Feel KNN lang={persona.lang}, Express KNN lang=turn_lang")
    print("=" * 70)

    for user_input, description in test_inputs:
        print(f"\n{'─'*60}")
        print(f"  📨 [{user_input}] — {description}")
        print(f"{'─'*60}")

        result = await agent.chat(user_input)
        reply = result['reply'] if isinstance(result, dict) else result

        # Access internals
        monologue = agent._last_action.get('monologue', '') if agent._last_action else ''
        modality = result.get('modality', '') if isinstance(result, dict) else ''

        # Metrics
        char_count = len(reply)
        excl_count = reply.count('！') + reply.count('!')

        print(f"\n  🧠 Monologue: {monologue[:100]}")
        print(f"  💬 Reply:     {reply}")
        print(f"  📊 Chars={char_count}, Exclamations={excl_count}")
        print(f"  🎭 Modality:  {modality[:60] if modality else 'N/A'}")

        # Pass/fail checks
        checks = []
        if char_count <= 30:
            checks.append("✅ char ≤ 30")
        elif char_count <= 50:
            checks.append("⚠️ char 31-50")
        else:
            checks.append(f"❌ char={char_count} > 50")

        if excl_count == 0:
            checks.append("✅ no !")
        elif excl_count <= 1:
            checks.append("⚠️ 1 !")
        else:
            checks.append(f"❌ {excl_count} !")

        print(f"  {' | '.join(checks)}")

    print(f"\n{'='*70}")
    print("  Test complete.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
