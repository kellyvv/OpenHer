"""
Cross-Persona Comparison — Same input, different personas
Verify: INFP vs ENFP vs INTJ produce stylistically distinct monologue+reply
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
    loader = PersonaLoader(PERSONAS_DIR)

    # Test personas with contrasting styles
    test_personas = [
        ("iris",   "INFP", "内向感受型 — 存在性陪伴"),
        ("luna",   "ENFP", "外向直觉型 — 热情鼓励"),
        ("vivian", "INTJ", "内向思维型 — 理性分析"),
        ("kai",    "ISTP", "内向感知型 — 沉默行动"),
    ]

    test_input = "最近心情不太好"

    print("=" * 70)
    print(f"  Cross-Persona Comparison: \"{test_input}\"")
    print("=" * 70)

    for pid, mbti, desc in test_personas:
        persona = loader.get(pid)
        if not persona:
            print(f"\n  ⚠ {pid} not found, skipping")
            continue

        agent = ChatAgent(persona=persona, llm=llm, user_id="test_user")

        print(f"\n{'─'*70}")
        print(f"  {persona.name} ({mbti}) — {desc}")
        print(f"{'─'*70}")

        result = await agent.chat(test_input)
        reply = result['reply'] if isinstance(result, dict) else result
        monologue = agent._last_action.get('monologue', '') if agent._last_action else ''

        char_count = len(reply)
        excl_count = reply.count('！') + reply.count('!')

        print(f"  🧠 独白: {monologue}")
        print(f"  💬 回复: {reply}")
        print(f"  📊 字数={char_count}  ！={excl_count}")

    print(f"\n{'='*70}")
    print("  对比完成。看独白和回复的风格差异。")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
