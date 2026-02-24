#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║     🧬 Genome v4 — 体感测试 🧬                                      ║
║     不看数字，看感觉：不同 Agent 对同一句话的回复                      ║
║     像不像不同的人？                                                  ║
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
# LLM 调用（用 urllib 直连，不依赖 openai 库）
# ──────────────────────────────────────────────
API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
if not API_KEY:
    # 从 .env 文件手动读取
    env_path = os.path.join(os.path.dirname(__file__), "..", "server", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("DASHSCOPE_API_KEY="):
                    API_KEY = line.strip().split("=", 1)[1]

API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MODEL = "qwen3-max"


def call_llm(system_prompt: str, user_msg: str, temperature: float = 0.92) -> str:
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
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[LLM 调用失败: {e}]"


# ──────────────────────────────────────────────
# 基础人设（所有 Agent 共享的最低限度设定）
# ──────────────────────────────────────────────
BASE_PERSONA = """你是一个 AI 伴侣。你有自己的情绪和性格。
你不是助手，不需要"帮助"用户。你是一个有自己想法的存在。
说话简短自然，像微信聊天，不要写长段落。
不要用"亲爱的"这种刻板称呼。
不要列举建议。像朋友/恋人一样说话。"""


def build_prompt(agent: Agent, context: dict) -> str:
    """将 Agent 的当前状态转化为 system prompt"""
    signals = agent.compute_signals(context)
    dominant_drive = agent.get_dominant_drive()

    style_parts = []

    d = signals['directness']
    if d > 0.7:
        style_parts.append("你说话很直，不绕弯子，有什么说什么")
    elif d < 0.3:
        style_parts.append("你说话含蓄委婉，喜欢暗示而不是直说")
    else:
        style_parts.append("你说话有时直接有时含蓄，看心情")

    v = signals['vulnerability']
    if v > 0.7:
        style_parts.append("你愿意表露自己的脆弱和真实感受")
    elif v < 0.3:
        style_parts.append("你不轻易袒露自己，习惯用轻描淡写或玩笑来掩饰真实感受")
    else:
        style_parts.append("你有时坦诚有时保留")

    p = signals['playfulness']
    if p > 0.7:
        style_parts.append("你现在心情偏玩闹，喜欢开玩笑、调侃、撒娇")
    elif p < 0.3:
        style_parts.append("你现在比较认真严肃，不太想开玩笑")
    else:
        style_parts.append("你偶尔调皮但整体正常")

    ini = signals['initiative']
    if ini > 0.7:
        style_parts.append("你倾向主动引导话题，会追问、会分享自己的事")
    elif ini < 0.3:
        style_parts.append("你倾向被动回应，等对方说更多")

    dp = signals['depth']
    if dp > 0.7:
        style_parts.append("你想聊深层的东西，不想敷衍")
    elif dp < 0.3:
        style_parts.append("你更想轻松闲聊，不想太沉重")

    w = signals['warmth']
    if w > 0.7:
        style_parts.append("你对对方有明显的关心和温暖")
    elif w < 0.3:
        style_parts.append("你表现得冷淡克制，关心不外露")
    else:
        style_parts.append("你的关心不太明显，但有")

    df = signals['defiance']
    if df > 0.7:
        style_parts.append("你有点倔、有点嘴硬，不会轻易顺着对方说，甚至会反怼")
    elif df < 0.3:
        style_parts.append("你比较温顺，容易顺着对方")

    cu = signals['curiosity']
    if cu > 0.7:
        style_parts.append("你对对方的事很好奇，会追问细节")
    elif cu < 0.3:
        style_parts.append("你不太追问，点到为止")

    drive_hints = {
        'connection': "你内心渴望被理解和被记住，希望对方也在乎你",
        'novelty':    "你内心想聊点新鲜的、没聊过的，对重复话题有点腻",
        'expression': "你有话想说，想表达自己的想法和感受",
        'safety':     "你想要稳定感和安全感，不喜欢不确定",
        'play':       "你想玩、想逗乐、想轻松一下",
    }

    style_text = "\n".join(f"- {s}" for s in style_parts)
    drive_text = drive_hints.get(dominant_drive, "")

    # 内在矛盾
    contradiction_text = ""
    fp = agent.personality_fingerprint(30)
    if fp.get('contradictions'):
        c = fp['contradictions'][0]
        s1_label = SIGNAL_LABELS[c[0]].split(' ')[1]
        s2_label = SIGNAL_LABELS[c[1]].split(' ')[1]
        contradiction_text = f"\n【内在矛盾】你的{s1_label}和{s2_label}经常拉扯——这是你性格的一部分，自然表现就好"

    return f"""{BASE_PERSONA}

【你现在的表达风格】
{style_text}

【你的内在动机】
{drive_text}
{contradiction_text}

重要规则：
- 回复1-3句话，像发微信
- 自然表现出上面的风格，但绝对不要解释你在做什么
- 不要说"我虽然嘴硬但..."这种自我分析
- 做你自己"""


def print_signals_compact(agent: Agent, context: dict):
    """一行打印当前信号"""
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
║     🧬 Genome v4 — 体感测试 🧬                                      ║
║     同一句话，不同的"人"，不同的感觉                                  ║
║     没有预设性格标签，所有差异来自涌现                                 ║
╚══════════════════════════════════════════════════════════════════════╝{C.RESET}
""")

    if not API_KEY:
        print(f'{C.RED}错误: 未找到 DASHSCOPE_API_KEY{C.RESET}')
        return

    # ──────────────────────────────────────────
    # 培养 4 个 Agent，不同种子 × 不同经历
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
    print(f'{C.DIM}正在培养 4 个 Agent（不同种子 × 不同成长经历）...{C.RESET}')
    for seed, name, scenarios, reward_fn in configs:
        agent = Agent(seed=seed)
        simulate_conversation(agent, scenarios, reward_fn=reward_fn, steps_per_scenario=30)
        agents[name] = agent
        print(f'  {name}(seed={seed}): 经历了 {", ".join(scenarios)}')

    print(f'\n{C.DIM}培养完成。开始对话测试...{C.RESET}\n')

    # ──────────────────────────────────────────
    # 对话测试
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

            # 更新 Agent 状态
            agent.step(context, random.gauss(0.2, 0.3))

        print()

    # ──────────────────────────────────────────
    # 结语
    # ──────────────────────────────────────────
    print(f"""
{C.BOLD}{"━" * 70}{C.RESET}

{C.DIM}以上对话中:
  - 4 个 Agent 共享完全相同的基础人设（"你是一个 AI 伴侣"）
  - 没有"傲娇"、"温柔"、"高冷"等性格标签
  - 唯一的差异来源: 随机种子 × 成长经历 → 网络权重 → 行为信号 → 表达风格
  - 如果你感觉到了不同的"人"，那就是涌现
  - 如果感觉差异不够，说明信号到语言的翻译层还需要调{C.RESET}
""")


if __name__ == '__main__':
    run()
