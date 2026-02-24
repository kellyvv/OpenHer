#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  🧬 Inner Monologue V2.1 × MiniMax-M2.5 — 模型对比 🧬               ║
║                                                                      ║
║  同样的信号冲突拦截 + 中文方括号格式                                  ║
║  MiniMax 新模型 M2.5 vs M2-her vs qwen3-max                         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import random
import re
import urllib.request
import ssl

sys.path.insert(0, os.path.dirname(__file__))
from genome_v4 import (
    Agent, SCENARIOS, SIGNALS, SIGNAL_LABELS,
    DRIVES, DRIVE_LABELS, C, N_SIGNALS, simulate_conversation
)
from genome_v4_monologue_test import (
    build_monologue_prompt, _detect_signal_collisions,
    extract_reply, sig_compact
)

# ── MiniMax API ──
API_KEY = ""
for env_path in [
    os.path.join(os.path.dirname(__file__), "..", "server", ".env"),
    os.path.join(os.path.dirname(__file__), "..", ".env"),
    os.path.join(os.path.dirname(__file__), "..", "..", "Vera", ".env"),
    os.path.join(os.path.dirname(__file__), "..", "..", "KFF", ".env"),
]:
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("MINIMAX_API_KEY="):
                    API_KEY = line.strip().split("=", 1)[1]
        if API_KEY:
            break

API_URL = "https://api.minimaxi.com/v1/text/chatcompletion_v2"
MODEL = "MiniMax-M2.5"


def call_m25(system_prompt: str, user_msg: str) -> str:
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.92, "max_tokens": 400,
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("choices") and data["choices"][0].get("message"):
                return data["choices"][0]["message"]["content"].strip()
            return f"[no response: {json.dumps(data, ensure_ascii=False)[:200]}]"
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:300]
        return f"[HTTP {e.code}: {err}]"
    except Exception as e:
        return f"[error: {e}]"


def run():
    print(f"""
{C.BOLD}══════════════════════════════════════════════════════════════
  Inner Monologue V2.1 × MiniMax-M2.5
  同样的信号冲突拦截，比较 M2.5 vs M2-her vs qwen3-max
=============================================================={C.RESET}
""")

    if not API_KEY:
        print(f'{C.RED}错误: 未找到 MINIMAX_API_KEY{C.RESET}')
        return

    # ── 培养 Agent ──
    configs = [
        (42,   'A', ['分享喜悦', '日常闲聊', '暧昧试探', '分享喜悦'],
         lambda a, s, c: random.gauss(0.4, 0.2), '快乐成长型'),
        (316,  'B', ['吵架冲突', '工作吐槽', '冷淡敷衍', '深夜心事'],
         lambda a, s, c: random.gauss(-0.1, 0.4), '受挫防御型'),
        (590,  'C', ['深夜心事', '暧昧试探', '深夜心事', '暧昧试探'],
         lambda a, s, c: random.gauss(0.3, 0.3), '情感深沉型'),
        (1001, 'D', ['日常闲聊', '冷淡敷衍', '吵架冲突', '冷淡敷衍'],
         lambda a, s, c: random.gauss(-0.2, 0.3), '冷漠疏离型'),
    ]

    agents = {}
    for seed, name, scenarios, reward_fn, desc in configs:
        agent = Agent(seed=seed)
        simulate_conversation(agent, scenarios, reward_fn=reward_fn, steps_per_scenario=30)
        agents[name] = (agent, desc)
        print(f'  {name}(seed={seed}): {desc}')
    print()

    # ── 对话测试 ──
    test_cases = [
        ("我今天好累啊",                    SCENARIOS['工作吐槽'],   '日常疲惫'),
        ("你有没有想过，人活着到底是为了什么", SCENARIOS['深夜心事'],   '深夜哲学'),
        ("哈哈哈我升职了！！！",             SCENARIOS['分享喜悦'],   '分享喜悦'),
        ("我觉得你根本不在乎我",             SCENARIOS['吵架冲突'],   '冲突指控'),
        ("我前任找我了...",                  SCENARIOS['暧昧试探'],   '敏感话题'),
    ]

    for user_msg, context, label in test_cases:
        print(f'{C.BOLD}{"─" * 60}{C.RESET}')
        print(f'  👤 {C.CYAN}"{user_msg}"{C.RESET}  ({label})')
        print(f'{C.BOLD}{"─" * 60}{C.RESET}')

        for name in ['A', 'B', 'C', 'D']:
            agent, desc = agents[name]
            signals = agent.compute_signals(context)
            collisions = _detect_signal_collisions(signals)
            collision_labels = [c[0] for c in collisions] if collisions else []

            print(f'\n  {C.BOLD}[{name}]{C.RESET} {desc}', end='')
            if collision_labels:
                print(f'  {C.YELLOW}⚡{"、".join(collision_labels)}{C.RESET}', end='')
            print()
            print(f'  {sig_compact(agent, context)}')

            prompt = build_monologue_prompt(agent, context)
            raw = call_m25(prompt, user_msg)
            monologue, reply = extract_reply(raw)

            if monologue:
                mono_short = monologue[:100] + ('...' if len(monologue) > 100 else '')
                print(f'  {C.MAGENTA}💭 {mono_short}{C.RESET}')
            print(f'  {C.WHITE}💬 {reply}{C.RESET}')

            agent.step(context, random.gauss(0.2, 0.3))

        print()

    # ── 漂移测试 ──
    print(f'\n{C.BOLD}{"─" * 60}{C.RESET}')
    print(f'{C.BOLD}  漂移测试: seed=42 × 吵架冲突 × 50轮负反馈{C.RESET}')
    print(f'{C.BOLD}{"─" * 60}{C.RESET}\n')

    da = Agent(seed=42)
    ctx = SCENARIOS['吵架冲突']
    msg = "我觉得你根本不在乎我"

    for i in range(50):
        signals = da.compute_signals(ctx)
        frust = getattr(da, '_frustration', 0.0)

        if i % 10 == 0:
            prompt = build_monologue_prompt(da, ctx)
            raw = call_m25(prompt, msg)
            monologue, reply = extract_reply(raw)

            collisions = _detect_signal_collisions(signals)
            c_tag = f' {C.YELLOW}⚡{"、".join(c[0] for c in collisions)}{C.RESET}' if collisions else ''

            print(f'  {C.BOLD}R{i:02d}{C.RESET}  w={signals["warmth"]:.2f} df={signals["defiance"]:.2f} f={frust:.1f}{c_tag}')
            if monologue:
                print(f'    {C.MAGENTA}💭 {monologue[:80]}{C.RESET}')
            print(f'    {C.WHITE}💬 {reply}{C.RESET}\n')

        da.step(ctx, reward=random.gauss(-0.3, 0.2))

    print(f'{C.BOLD}{"─" * 60}{C.RESET}')
    print(f'  测试完成！')
    print(f'{C.BOLD}{"─" * 60}{C.RESET}')


if __name__ == '__main__':
    run()
