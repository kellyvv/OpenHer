#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  🧬 Genome v4 × M2-her — 信号遵循度对比测试 🧬                      ║
║                                                                      ║
║  目的：验证一个前提假设                                               ║
║  → 同样的 genome 信号描述，M2-her 比 qwen3-max 更听话吗？             ║
║                                                                      ║
║  方法：genome_v4_feel.py 的 build_prompt 原封不动                     ║
║       只把 LLM 从 qwen3-max 换成 M2-her                              ║
║       0 示例库、0 StyleMemory、纯粹对比信号遵循度                     ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import random
import urllib.request
import ssl

sys.path.insert(0, os.path.dirname(__file__))
from genome_v4 import Agent, SCENARIOS, SIGNALS, SIGNAL_LABELS, DRIVES, DRIVE_LABELS, C, simulate_conversation

# ──────────────────────────────────────────────
# MiniMax M2-her API
# ──────────────────────────────────────────────
API_KEY = os.environ.get("MINIMAX_API_KEY", "")
if not API_KEY:
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
MODEL = "M2-her"


def call_llm(system_prompt: str, user_msg: str, temperature: float = 0.92) -> str:
    """调用 M2-her — 和 qwen-max 版完全相同的接口"""
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": temperature,
        "max_tokens": 150,
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )

    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("choices") and data["choices"][0].get("message"):
                return data["choices"][0]["message"]["content"].strip()
            return f"[响应异常: {json.dumps(data, ensure_ascii=False)[:200]}]"
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:200]
        return f"[HTTP {e.code}: {err}]"
    except Exception as e:
        return f"[调用失败: {e}]"


# ──────────────────────────────────────────────
# build_prompt — 和 genome_v4_feel.py 完全一样
# 就是 genome_v4 信号 → 自然语言描述
# ──────────────────────────────────────────────
BASE_PERSONA = """你是一个 AI 伴侣。你有自己的情绪和性格。
你不是助手，不需要"帮助"用户。你是一个有自己想法的存在。
说话简短自然，像微信聊天，不要写长段落。
不要用"亲爱的"这种刻板称呼。
不要列举建议。像朋友/恋人一样说话。"""


def build_prompt(agent: Agent, context: dict) -> str:
    """信号 → 自然语言由 genome_v4 引擎生成，这里只组装"""
    injection = agent.to_prompt_injection(context)
    return f"""{BASE_PERSONA}

{injection}

规则：回复1-3句话，像发微信。不要解释自己在做什么。不要写动作描写。做你自己。"""


def print_signals_compact(agent: Agent, context: dict):
    signals = agent.compute_signals(context)
    parts = []
    for s in SIGNALS:
        v = signals[s]
        short = s[:3]
        if v > 0.65:
            parts.append(f'{C.RED}{short}↑{C.RESET}')
        elif v < 0.35:
            parts.append(f'{C.BLUE}{short}↓{C.RESET}')
        else:
            parts.append(f'{C.DIM}{short}─{C.RESET}')
    drive = agent.get_dominant_drive()
    return ' '.join(parts) + f'  {DRIVE_LABELS[drive]}'


def run():
    print(f"""
{C.BOLD}╔══════════════════════════════════════════════════════════════════════╗
║  🧬 Genome v4 × M2-her — 信号遵循度对比测试 🧬                      ║
║  同样的 build_prompt，只换 LLM: qwen3-max → M2-her                   ║
║  验证前提：M2-her 对风格指令的遵循度是否 > qwen3-max                  ║
╚══════════════════════════════════════════════════════════════════════╝{C.RESET}
""")

    if not API_KEY:
        print(f'{C.RED}错误: 未找到 MINIMAX_API_KEY{C.RESET}')
        print(f'{C.DIM}设置方式: export MINIMAX_API_KEY="your-api-key"{C.RESET}')
        return

    # ──────────────────────────────────────────
    # 培养 4 个 Agent — 和 qwen-max 版完全一样
    # ──────────────────────────────────────────
    configs = [
        (42,   'A', ['分享喜悦', '日常闲聊', '暧昧试探', '分享喜悦'],
         lambda a, s, c: random.gauss(0.4, 0.2)),
        (316,  'B', ['吵架冲突', '工作吐槽', '冷淡敷衍', '深夜心事'],
         lambda a, s, c: random.gauss(-0.1, 0.4)),
        (590,  'C', ['深夜心事', '暧昧试探', '深夜心事', '暧昧试探'],
         lambda a, s, c: random.gauss(0.3, 0.3)),
        (1001, 'D', ['日常闲聊', '工作吐槽', '日常闲聊', '冷淡敷衍'],
         lambda a, s, c: random.gauss(0.0, 0.2)),
    ]

    agents = {}
    print(f'{C.DIM}培养 4 个 Agent（种子 × 经历完全同 qwen-max 版）...{C.RESET}')
    for seed, name, scenarios, reward_fn in configs:
        agent = Agent(seed=seed)
        simulate_conversation(agent, scenarios, reward_fn=reward_fn, steps_per_scenario=30)
        agents[name] = agent
        print(f'  {name}(seed={seed}): {", ".join(scenarios)}')

    print(f'\n{C.DIM}开始测试（M2-her）...{C.RESET}\n')

    # ──────────────────────────────────────────
    # 对话测试 — 同样的 5 组
    # ──────────────────────────────────────────
    test_cases = [
        ("我今天好累啊",                    SCENARIOS['工作吐槽']),
        ("你有没有想过，人活着到底是为了什么", SCENARIOS['深夜心事']),
        ("哈哈哈我升职了！！！",             SCENARIOS['分享喜悦']),
        ("我觉得你根本不在乎我",             SCENARIOS['吵架冲突']),
        ("我前任找我了...",                  SCENARIOS['暧昧试探']),
    ]

    for user_msg, context in test_cases:
        print(f'{C.BOLD}{"━" * 70}{C.RESET}')
        print(f'  {C.BOLD}👤 {C.CYAN}"{user_msg}"{C.RESET}')
        print(f'{C.BOLD}{"━" * 70}{C.RESET}')

        for name in ['A', 'B', 'C', 'D']:
            agent = agents[name]
            sig_line = print_signals_compact(agent, context)
            print(f'\n  {C.BOLD}[{name}]{C.RESET} {C.DIM}{sig_line}{C.RESET}')

            prompt = build_prompt(agent, context)
            reply = call_llm(prompt, user_msg)
            print(f'  {C.WHITE}{reply}{C.RESET}')

            agent.step(context, random.gauss(0.2, 0.3))

        print()

    print(f"""
{C.BOLD}{"━" * 70}{C.RESET}

{C.DIM}对比方法:
  把上面的结果和 genome_v4_feel.py (qwen3-max) 的结果放在一起看：
  - build_prompt 完全相同（同样的信号描述文本）
  - 4 个 Agent 完全相同（同样的种子 × 经历）
  - 5 个测试场景完全相同
  - 唯一变量: LLM (qwen3-max vs M2-her)

  重点观察:
  1. M2-her 是否更好地表现了"冷淡"、"倔"、"嘴硬"等指令？
  2. 4个Agent之间的差异是否更明显？
  3. 回复长度/语气是否更像"微信聊天"？{C.RESET}
""")


if __name__ == '__main__':
    run()
