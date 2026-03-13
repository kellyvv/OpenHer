"""
Test Gemini LLM Provider — Complete Persona Engine Flow.

Mirrors main.py's exact initialization:
  1. load_dotenv
  2. PersonaLoader.load_all()
  3. LLMClient(provider="gemini", model="gemini-3.1-flash-lite-preview")
  4. ChatAgent with genome_data_dir=.data/genome (genesis seeds)
  5. genome_seed = hash(persona_id)
  6. pre_warm() for new agents
  7. Full lifecycle: Critic → Metabolism → Signals → KNN → Feel → Express

Personas: luna (ENFP), rex (ENTJ), vivian (INTJ)
"""

import asyncio
import sys
import os
import time

# Must load .env BEFORE importing providers
sys.path.insert(0, "/Users/zxw/AITOOL/openher")
from dotenv import load_dotenv
load_dotenv(os.path.join("/Users/zxw/AITOOL/openher", ".env"), override=True)

from providers.llm.client import LLMClient, ChatMessage
from persona.loader import PersonaLoader
from agent.chat_agent import ChatAgent
from engine.genome.genome_engine import DRIVES, SIGNALS


# ── Config (mirrors main.py startup) ──
BASE_DIR = "/Users/zxw/AITOOL/openher"
PERSONAS_DIR = os.path.join(BASE_DIR, "persona", "personas")
GENOME_DATA_DIR = os.path.join(BASE_DIR, ".data", "genome")

# ── 5 Rounds (escalating depth) ──
USER_MESSAGES = [
    "嘿，今天过得怎么样？",
    "我最近工作压力好大，有时候觉得自己快扛不住了",
    "你有没有想过，人活着到底是为了什么？",
    "我觉得你真的很懂我，跟你聊天特别舒服",
    "如果明天是世界末日，你会想做什么？",
]

TEST_PERSONAS = ["luna", "kai", "kelly"]


def fmt_drives(agent_obj):
    lines = []
    for d in DRIVES:
        s = agent_obj.drive_state[d]
        b = agent_obj.drive_baseline[d]
        lines.append(f"    {d:12s}  state={s:.3f}  baseline={b:.3f}")
    return "\n".join(lines)


def fmt_signals(sig):
    if not sig:
        return "    (none)"
    lines = []
    for s in SIGNALS:
        v = sig.get(s, 0.0)
        bar = "█" * int(v * 20)
        lines.append(f"    {s:12s}  {v:.3f}  {bar}")
    return "\n".join(lines)


async def test_persona(persona_id: str, loader: PersonaLoader):
    """Run 5-round conversation with one persona — full engine flow."""
    persona = loader.get(persona_id)
    if not persona:
        print(f"❌ Persona '{persona_id}' not found!")
        return None

    print(f"\n{'='*70}")
    print(f"  PERSONA: {persona.name} ({persona.mbti}) [{persona_id}]")
    print(f"  Lang: {persona.lang}  Gender: {persona.gender}")
    print(f"{'='*70}")

    # ── Mirrors main.py line 130-135: LLM Client ──
    llm = LLMClient(provider="gemini", model="gemini-3.1-flash-lite-preview")

    # ── Mirrors main.py line 577: deterministic seed per persona ──
    genome_seed = hash(persona_id) % 100000

    # ── Mirrors main.py line 583-595: ChatAgent with full config ──
    agent = ChatAgent(
        persona=persona,
        llm=llm,
        user_id="test_user",
        user_name="测试者",
        genome_seed=genome_seed,
        genome_data_dir=GENOME_DATA_DIR,
        # No state_store/evermemos/skill_engines — testing core engine only
    )

    # ── Mirrors main.py line 619-621: pre-warm new agent ──
    agent.pre_warm()
    print(f"  [pre-warm] ✓ 60 steps done (seed={genome_seed})")

    # Show genesis seed & initial state
    sm_stats = agent.style_memory.stats()
    print(f"  [genesis] loaded {sm_stats['genesis_count']} seeds, {sm_stats['personal_count']} personal")
    print(f"\n  ── Initial Drive State ──")
    print(fmt_drives(agent.agent))

    # ── Run 5 rounds ──
    for i, msg in enumerate(USER_MESSAGES, 1):
        print(f"\n  {'─'*60}")
        print(f"  Round {i}/5  |  User: {msg}")
        print(f"  {'─'*60}")

        result = await agent.chat(msg)

        reply = result.get("reply", "")
        modality = result.get("modality", "文字")

        print(f"\n  💬 Reply [{modality}]: {reply}")

        # Engine state
        print(f"\n  ── Engine State (Turn {i}) ──")
        print(f"  Reward: {agent._last_reward:.3f}  |  Temp: {agent.metabolism.temperature():.3f}")

        if agent._last_signals:
            print(f"  Signals:")
            print(fmt_signals(agent._last_signals))

        print(f"  Drives:")
        print(fmt_drives(agent.agent))

        if agent._last_critic:
            ctx = agent._last_critic
            key_metrics = ['conversation_depth', 'topic_intimacy', 'emotional_valence',
                           'trust_level', 'user_engagement', 'conflict_level']
            ctx_str = "  |  ".join(f"{k}={ctx.get(k,0):.2f}" for k in key_metrics)
            print(f"  Critic: {ctx_str}")

    # Style memory final stats
    sm_final = agent.style_memory.stats()
    print(f"\n  {'='*60}")
    print(f"  FINAL: {persona.name} ({persona.mbti})")
    print(f"  Turns: {agent._turn_count}  |  Temp: {agent.metabolism.temperature():.3f}  |  Reward: {agent._last_reward:.3f}")
    print(f"  Memories: genesis={sm_final['genesis_count']}  personal={sm_final['personal_count']}  total={sm_final['total']}")
    print(f"  Total Mass (eff): {sm_final['total_mass_eff']}")
    print(f"  {'='*60}")

    return {
        "persona": persona_id,
        "name": persona.name,
        "mbti": persona.mbti,
        "turns": agent._turn_count,
        "final_temp": agent.metabolism.temperature(),
        "final_reward": agent._last_reward,
        "genesis": sm_final['genesis_count'],
        "personal": sm_final['personal_count'],
        "total_mass": sm_final['total_mass_eff'],
    }


async def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Gemini LLM Test — Complete Persona Engine Flow            ║")
    print("║  Model: gemini-3.1-flash-lite-preview                      ║")
    print("║  Personas: luna(ENFP) × kai(ISTP) × kelly(ENTP)            ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    loader = PersonaLoader(PERSONAS_DIR)
    loader.load_all()
    print(f"\nLoaded {len(loader.list_ids())} personas: {loader.list_ids()}")

    results = []
    for pid in TEST_PERSONAS:
        try:
            r = await test_persona(pid, loader)
            if r:
                results.append(r)
        except Exception as e:
            print(f"\n❌ ERROR testing {pid}: {e}")
            import traceback
            traceback.print_exc()

    # Final comparison
    print(f"\n\n{'='*70}")
    print("  COMPARISON TABLE")
    print(f"{'='*70}")
    print(f"  {'Persona':<10} {'MBTI':<6} {'Temp':>8} {'Reward':>8} {'Genesis':>8} {'Personal':>8} {'Mass':>8}")
    print(f"  {'-'*10} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for r in results:
        print(f"  {r['name']:<10} {r['mbti']:<6} "
              f"{r['final_temp']:>8.3f} {r['final_reward']:>8.3f} "
              f"{r['genesis']:>8} {r['personal']:>8} {r['total_mass']:>8.1f}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
