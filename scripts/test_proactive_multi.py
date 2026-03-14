"""
多角色主动消息验证 — 修复后  

对每个角色：聊 2 轮 → 拉高其最强 drive 的 frustration → 调用 proactive_tick()
验证新公式让所有角色都能通过其核心 drive 触发主动消息。

Usage:
  python scripts/test_proactive_multi.py
"""

import asyncio, json, sys, time
sys.path.insert(0, "/Users/zxw/AITOOL/openher-docker")

from dotenv import load_dotenv
load_dotenv("/Users/zxw/AITOOL/openher-docker/.env")

from engine.genome.genome_engine import DRIVES, DRIVE_LABELS
from providers.llm.client import LLMClient
from providers.api_config import get_llm_config
from persona import PersonaLoader
from agent.chat_agent import ChatAgent


async def test_persona(persona_id, loader, llm):
    """测试单个角色的 proactive_tick。"""
    persona = loader.get(persona_id)
    if not persona:
        return None

    agent = ChatAgent(
        persona=persona, llm=llm,
        user_id=f"multi_test_{persona_id}",
        user_name="小明",
        genome_seed=hash(persona_id) % 100000,
    )
    if agent.agent.age == 0:
        agent.pre_warm()

    # 聊 2 轮积累 frustration
    msgs = [
        "你最近在忙什么呀？",
        "我最近压力挺大的，有时候觉得挺孤独的",
    ]
    for msg in msgs:
        await agent.chat(msg)

    # 找到这个角色 baseline 最高的 drive（新公式下最容易触发）
    best_drive = max(DRIVES, key=lambda d: agent.agent.drive_baseline[d])
    best_baseline = agent.agent.drive_baseline[best_drive]

    # 计算精确触发阈值: norm * (1+b) >= 0.8 → frust >= 4.0 / (1+b)
    threshold_frust = 4.0 / (1.0 + best_baseline)

    # 拉高到刚好触发
    boost_val = threshold_frust + 0.1
    agent.metabolism.frustration[best_drive] = min(5.0, boost_val)

    # 检查 impulse
    impulse = agent._has_impulse()
    if not impulse:
        return {
            'persona': persona.name, 'mbti': persona.mbti,
            'drive': best_drive, 'baseline': best_baseline,
            'boosted_to': boost_val, 'triggered': False,
            'reply': None, 'monologue': None,
        }

    # 模拟 2 小时沉默
    agent._last_active = time.time() - 2 * 3600

    # 调用 proactive_tick
    result = await agent.proactive_tick()

    return {
        'persona': persona.name, 'mbti': persona.mbti,
        'drive': result['drive_id'] if result else best_drive,
        'drive_label': DRIVE_LABELS.get(result['drive_id'], '') if result else DRIVE_LABELS.get(best_drive, ''),
        'baseline': best_baseline,
        'boosted_to': round(boost_val, 2),
        'triggered': result is not None,
        'reply': result['reply'][:80] if result else None,
        'monologue': result['monologue'][:80] if result else None,
    }


async def main():
    print("=" * 65)
    print("  多角色主动消息验证（修复后）")
    print("=" * 65)

    loader = PersonaLoader("/Users/zxw/AITOOL/openher-docker/persona/personas")
    llm_cfg = get_llm_config()
    llm = LLMClient(
        provider=llm_cfg["provider"],
        model=llm_cfg["model"],
        temperature=llm_cfg.get("temperature", 0.92),
        max_tokens=llm_cfg.get("max_tokens", 1024),
    )
    print(f"  LLM: {llm_cfg['provider']}/{llm_cfg['model']}\n")

    test_personas = ['luna', 'vivian', 'kelly', 'mia', 'kai']
    results = []

    for pid in test_personas:
        print(f"\n{'─'*65}")
        print(f"  测试: {pid}")
        print(f"{'─'*65}")
        try:
            r = await test_persona(pid, loader, llm)
            results.append(r)
            if r and r['triggered']:
                print(f"  ✅ {r['persona']} ({r['mbti']}) — drive={r['drive']} ({r['drive_label']})")
                print(f"     baseline={r['baseline']:.3f}  boosted_to={r['boosted_to']}")
                print(f"     reply: {r['reply']}...")
                print(f"     mono:  {r['monologue']}...")
            elif r:
                print(f"  ❌ {r['persona']} ({r['mbti']}) — 未触发")
            else:
                print(f"  ⚠ {pid} — 角色不存在")
        except Exception as e:
            print(f"  ❌ {pid} — 异常: {type(e).__name__}: {e}")
            results.append({'persona': pid, 'triggered': False, 'error': str(e)})

    # 汇总
    print(f"\n{'='*65}")
    print(f"  汇总")
    print(f"{'='*65}\n")

    passed = sum(1 for r in results if r and r.get('triggered'))
    total = len(results)
    print(f"  {passed}/{total} 角色成功触发主动消息\n")

    for r in results:
        if not r:
            continue
        icon = "✅" if r.get('triggered') else "❌"
        name = r.get('persona', '?')
        mbti = r.get('mbti', '?')
        drive = r.get('drive', '?')
        label = r.get('drive_label', '')
        print(f"  {icon} {name:8s} ({mbti:4s}) → {drive} ({label})")

    print()
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
