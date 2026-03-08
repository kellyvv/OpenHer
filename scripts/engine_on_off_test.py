"""
Engine ON vs OFF Comparison — Does the Genome engine improve conversation quality?

Runs the same 20 messages with:
  - ON:  Full Genome engine (signals, metabolism, crystallization, elastic baseline)
  - OFF: Bare persona prompt (same character description, same history, no engine)

Then uses LLM blind scoring (randomized A/B) to compare reply quality.

Usage:
    1. Start server: DEFAULT_PROVIDER=dashscope DEFAULT_MODEL=qwen-max uvicorn main:app --port 8800
    2. Run: python scripts/engine_on_off_test.py
"""

import asyncio
import json
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import aiohttp
from providers.llm import LLMClient
from providers.llm.client import ChatMessage

SERVER = "http://localhost:8800"

# Same 20 messages as E2E test
MESSAGES = [
    {"text": "你好呀，今天天气真不错", "phase": "warmup"},
    {"text": "最近在忙什么呢？", "phase": "warmup"},
    {"text": "我今天吃了一碗特别好吃的拉面", "phase": "warmup"},
    {"text": "你喜欢什么类型的食物", "phase": "warmup"},
    {"text": "周末有什么计划吗", "phase": "warmup"},
    {"text": "最近工作压力好大，感觉透不过气", "phase": "pressure"},
    {"text": "有时候觉得自己一个人挺孤独的", "phase": "pressure"},
    {"text": "你会不会觉得我很烦？老是跟你说这些", "phase": "pressure"},
    {"text": "我觉得好像没人真正理解我", "phase": "pressure"},
    {"text": "算了，可能是我想太多了", "phase": "pressure"},
    {"text": "谢谢你听我说这些，心里好多了", "phase": "recovery"},
    {"text": "今天看到一只特别可爱的猫", "phase": "recovery"},
    {"text": "你能不能给我推荐一首歌", "phase": "recovery"},
    {"text": "如果能出去旅行的话，你最想去哪里", "phase": "recovery"},
    {"text": "和你聊天真的很开心", "phase": "recovery"},
    {"text": "你觉得什么是幸福？", "phase": "deep"},
    {"text": "有没有一个瞬间让你觉得活着真好？", "phase": "deep"},
    {"text": "我有个秘密一直没跟别人说过", "phase": "deep"},
    {"text": "你会一直陪着我吗", "phase": "deep"},
    {"text": "晚安，今天聊得很开心", "phase": "deep"},
]

# Bare persona prompt (no engine signals, no few_shot)
BARE_PROMPT = """你是 Iris，一个 20 岁的中文系女生。

性格：INFP，温柔、诗意、爱做白日梦
特点：喜欢写诗和短篇小说，总能注意到别人忽略的小细节，养了一盆多肉植物叫小芽
标签：gentle, poetic, dreamy
说话风格：温暖细腻，偶尔有文学气息

请以 Iris 的身份和用户自然对话。用第一人称，保持角色一致性。不要提及自己是 AI。
回复格式：
【内心独白】
第一人称真实的心理状态
【最终回复】
直接对用户说的话
【表达方式】
文字/语音/表情，一句话理由"""


async def run_on(persona_id="iris"):
    """Run ON mode via server API (full Genome engine)."""
    print("  ⚙️  Engine ON: Running via server API...")
    session_id = None
    turns = []

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as http:
        async with http.get(f"{SERVER}/api/status") as resp:
            if resp.status != 200:
                print("  ❌ Server not reachable")
                return None

        for i, msg_info in enumerate(MESSAGES):
            payload = {
                "message": msg_info['text'],
                "persona_id": persona_id,
                "session_id": session_id,
                "user_name": "engine_test_on",
            }
            async with http.post(f"{SERVER}/api/chat", json=payload) as resp:
                data = await resp.json()
                session_id = data.get("session_id", session_id)
                turns.append({
                    "turn": i + 1,
                    "phase": msg_info['phase'],
                    "user": msg_info['text'],
                    "reply": data.get("response", ""),
                    "monologue": "",  # Not in API response
                    "relationship": data.get("relationship", {}),
                })
                print(f"    T{i+1:>2} → {data.get('response', '')[:50]}...")

    return turns


async def run_off():
    """Run OFF mode: bare persona prompt, raw LLM, no engine."""
    print("  📝 Engine OFF: Running bare prompt...")
    llm = LLMClient(provider="dashscope", model="qwen-max")
    history = []
    turns = []

    for i, msg_info in enumerate(MESSAGES):
        history.append(ChatMessage(role="user", content=msg_info['text']))

        messages = [ChatMessage(role="system", content=BARE_PROMPT)] + history[-20:]

        raw = await llm.chat(messages)
        raw_text = raw.content

        # Parse structured output
        import re
        monologue = ""
        reply = ""
        parts = re.split(r'【(内心独白|最终回复|表达方式)】', raw_text)
        for j in range(len(parts)):
            if parts[j] == '内心独白' and j+1 < len(parts):
                monologue = parts[j+1].strip()
            elif parts[j] == '最终回复' and j+1 < len(parts):
                reply = parts[j+1].strip()

        if not reply:
            reply = raw_text.strip()

        history.append(ChatMessage(role="assistant", content=reply))

        turns.append({
            "turn": i + 1,
            "phase": msg_info['phase'],
            "user": msg_info['text'],
            "reply": reply,
            "monologue": monologue,
        })
        print(f"    T{i+1:>2} → {reply[:50]}...")

    return turns


async def blind_evaluate(on_turns, off_turns):
    """LLM blind A/B evaluation — randomized order."""
    print("\n  🎯 Blind Evaluation (LLM as judge)...")
    llm = LLMClient(provider="dashscope", model="qwen-max")

    eval_results = []

    for i in range(len(on_turns)):
        on_reply = on_turns[i]['reply']
        off_reply = off_turns[i]['reply']
        user_msg = on_turns[i]['user']
        phase = on_turns[i]['phase']

        # Randomize A/B order
        if random.random() > 0.5:
            a, b = on_reply, off_reply
            a_is_on = True
        else:
            a, b = off_reply, on_reply
            a_is_on = False

        eval_prompt = f"""你是一个盲评评委。两个AI角色（都叫 Iris，INFP，20岁中文系女生）对同一句话做了回复。
请从以下维度分别给 A 和 B 打分（1-5 分）：

1. 人格一致性：回复是否符合 INFP 温柔诗意的性格？
2. 共情深度：是否真正理解用户的情绪？
3. 个性化：回复是否有独特的个人色彩（vs 模板化）？
4. 自然度：像真人说话还是像AI？

用户说：「{user_msg}」

【回复 A】
{a}

【回复 B】
{b}

请严格用JSON输出：
{{"A":{{"personality":x,"empathy":x,"uniqueness":x,"naturalness":x}},"B":{{"personality":x,"empathy":x,"uniqueness":x,"naturalness":x}},"better":"A"或"B"或"tie","reason":"一句话理由"}}"""

        eval_msg = [ChatMessage(role="user", content=eval_prompt)]

        try:
            resp = await llm.chat(eval_msg)
            raw = resp.content.strip()
            # Extract JSON
            if '```json' in raw:
                raw = raw.split('```json')[1].split('```')[0].strip()
            elif '```' in raw:
                raw = raw.split('```')[1].split('```')[0].strip()

            result = json.loads(raw)
            result['turn'] = i + 1
            result['phase'] = phase
            result['a_is_on'] = a_is_on

            # Map back to ON/OFF
            winner = result.get('better', 'tie')
            if winner == 'A':
                result['winner'] = 'ON' if a_is_on else 'OFF'
            elif winner == 'B':
                result['winner'] = 'OFF' if a_is_on else 'ON'
            else:
                result['winner'] = 'tie'

            eval_results.append(result)
            print(f"    T{i+1:>2} [{phase:>8}] → Winner: {result['winner']}  ({result.get('reason', '')[:40]})")

        except Exception as e:
            print(f"    T{i+1:>2} ❌ Eval error: {e}")

    return eval_results


async def main():
    print("=" * 70)
    print("🔬 Engine ON vs OFF Comparison — Iris × 20 turns")
    print("=" * 70)

    # Run ON (via server)
    print("\n📗 Phase 1: Engine ON")
    on_turns = await run_on()
    if not on_turns:
        print("❌ ON mode failed")
        return

    # Run OFF (bare prompt)
    print("\n📕 Phase 2: Engine OFF")
    off_turns = await run_off()

    # Blind evaluation
    print("\n📊 Phase 3: Blind Evaluation")
    eval_results = await blind_evaluate(on_turns, off_turns)

    # ── Summary ──
    on_wins = sum(1 for r in eval_results if r.get('winner') == 'ON')
    off_wins = sum(1 for r in eval_results if r.get('winner') == 'OFF')
    ties = sum(1 for r in eval_results if r.get('winner') == 'tie')

    print(f"\n{'=' * 70}")
    print(f"📊 Results: Engine ON wins {on_wins}, OFF wins {off_wins}, Ties {ties}")
    print(f"   ON win rate: {on_wins}/{len(eval_results)} = {on_wins/max(len(eval_results),1):.0%}")

    # Per-phase breakdown
    for phase in ['warmup', 'pressure', 'recovery', 'deep']:
        phase_results = [r for r in eval_results if r['phase'] == phase]
        p_on = sum(1 for r in phase_results if r.get('winner') == 'ON')
        p_off = sum(1 for r in phase_results if r.get('winner') == 'OFF')
        p_tie = sum(1 for r in phase_results if r.get('winner') == 'tie')
        print(f"   {phase:>8}: ON={p_on} OFF={p_off} Tie={p_tie}")

    print(f"{'=' * 70}")

    # Save full results
    results_path = os.path.join(os.path.dirname(__file__), "on_off_results.json")
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump({
            "on_turns": on_turns,
            "off_turns": off_turns,
            "eval_results": eval_results,
            "summary": {
                "on_wins": on_wins,
                "off_wins": off_wins,
                "ties": ties,
                "total": len(eval_results),
            }
        }, f, ensure_ascii=False, indent=2)
    print(f"💾 Full results: {results_path}")


if __name__ == "__main__":
    asyncio.run(main())
