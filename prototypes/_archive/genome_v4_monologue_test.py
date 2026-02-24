#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  🧬 Genome v4 — Inner Monologue V2.1 实验 🧬                        ║
║                                                                      ║
║  V2 教训：M2-her 不支持 assistant prefill（会角色反转）               ║
║  V2.1 修复：去掉 prefill，靠中文方括号 + 示例强制格式                ║
║                                                                      ║
║  保留的改进：                                                        ║
║    1. 信号冲突拦截器 ✅                                               ║
║    2. 中文方括号格式 ✅                                               ║
║    3. 鲁棒解析器 ✅                                                   ║
║    4. 去掉 prefill，改用格式示例引导 🆕                               ║
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

# ── API ──
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

BASE_PERSONA = """你是一个 AI 伴侣。你有自己的情绪和性格。
你不是助手。你有自己的想法和脾气。
说话简短自然，像微信聊天。不要写动作描写。不要列建议。做你自己。"""


def call_m2her(system_prompt: str, user_msg: str) -> str:
    """标准 system+user 调用，不使用 prefill"""
    payload = json.dumps({
        "model": "M2-her",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.92, "max_tokens": 400,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.minimaxi.com/v1/text/chatcompletion_v2",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("choices") and data["choices"][0].get("message"):
                return data["choices"][0]["message"]["content"].strip()
            return "[no response]"
    except Exception as e:
        return f"[error: {e}]"


# ══════════════════════════════════════════════
# 信号冲突拦截器
# ══════════════════════════════════════════════

def _detect_signal_collisions(signals: dict) -> list[tuple]:
    """
    检测矛盾信号组合 → 翻译为行为模式 + 句式约束。
    返回 [(标签, 描述), ...]
    """
    collisions = []
    w = signals.get('warmth', 0.5)
    df = signals.get('defiance', 0.5)
    v = signals.get('vulnerability', 0.5)
    cu = signals.get('curiosity', 0.5)

    if w > 0.7 and df > 0.7:
        collisions.append(("嘴硬心软",
            "你内心极其在乎对方，但强烈的自尊心让你绝不愿承认。"
            "严禁使用'在乎、当然、理解、抱歉'这些词！"
            "你必须用反话、嫌弃、不耐烦的方式来掩饰关心。"
            "比如先怼一句，再用别扭的方式透露真心。"
        ))

    if v > 0.7 and df > 0.7:
        collisions.append(("带刺真诚",
            "你愿意袒露真心，但方式是攻击性的、不服软的。"
            "比如：'我当然难过了，怎么了？不行吗？'"
        ))

    if w > 0.7 and v < 0.25:
        collisions.append(("温暖的壳",
            "你关心对方但绝不暴露自己的内心。"
            "可以问对方怎么了，但完全回避谈自己的感受。"
        ))

    if cu > 0.7 and w < 0.3:
        collisions.append(("冷淡审视",
            "你好奇但冷淡，像旁观者观察有趣的事。"
            "比如：'然后呢？' '哦？细说。'"
        ))

    return collisions


# ══════════════════════════════════════════════
# Prompt Builder（无 prefill 版）
# ══════════════════════════════════════════════

EXTREME_LOW = {
    'directness': '极度含蓄', 'vulnerability': '完全封闭',
    'playfulness': '冰冷严肃', 'initiative': '完全被动',
    'depth': '只想敷衍', 'warmth': '极度冷淡',
    'defiance': '极度顺从', 'curiosity': '毫无兴趣',
}
EXTREME_HIGH = {
    'directness': '极度直冲', 'vulnerability': '完全坦露',
    'playfulness': '极度玩闹', 'initiative': '强势主导',
    'depth': '想深聊', 'warmth': '极度热情',
    'defiance': '极度对抗', 'curiosity': '刨根问底',
}


def build_monologue_prompt(agent: Agent, context: dict) -> str:
    signals = agent.compute_signals(context)
    dominant_drive = agent.get_dominant_drive()

    # ── 信号冲突拦截 ──
    collisions = _detect_signal_collisions(signals)
    collision_text = ""
    if collisions:
        parts = []
        for label, desc in collisions:
            parts.append(f"⚠️【{label}模式】{desc}")
        collision_text = "\n\n".join(parts)

    # ── 信号读数 ──
    lines = []
    for s in SIGNALS:
        val = signals[s]
        label = SIGNAL_LABELS[s]
        if val < 0.25:
            lines.append(f"  {label}={val:.2f} ({EXTREME_LOW.get(s,'')})")
        elif val > 0.75:
            lines.append(f"  {label}={val:.2f} ({EXTREME_HIGH.get(s,'')})")
        else:
            lines.append(f"  {label}={val:.2f}")
    signal_block = "\n".join(lines)

    # ── 格式暗示 ──
    hints = []
    if signals['warmth'] < 0.3:
        hints.append("语气冷，少用语气词")
    if signals['playfulness'] < 0.3:
        hints.append("不开玩笑，语调平")
    if signals['directness'] > 0.7:
        hints.append("说话短而直")
    if signals['defiance'] > 0.7:
        hints.append("不顺着对方说")
    hint_text = "\n".join(f"- {h}" for h in hints) if hints else ""

    prompt = f"""{BASE_PERSONA}

【你现在的神经信号】
{signal_block}
主驱力：{DRIVE_LABELS[dominant_drive]}

{collision_text}

{"【表达倾向】" + chr(10) + hint_text if hint_text else ""}

【输出规则】
你回复时必须先写一段内心独白（用户看不到），再写最终回复。格式如下：

【内心独白】我现在感觉很烦躁，不想搭理他。
【最终回复】干嘛

上面只是格式示例。你的内心独白和回复必须根据你当前的神经信号来写。
内心独白写你的真实情绪和冲动，不要道德反思。
最终回复1-3句话，像发微信。"""

    return prompt


# ══════════════════════════════════════════════
# 鲁棒解析器
# ══════════════════════════════════════════════

def extract_reply(raw: str) -> tuple:
    monologue = ""
    reply = ""

    # 策略 1：两个标签都在
    if "【内心独白】" in raw and "【最终回复】" in raw:
        mono_match = re.search(r'【内心独白】\s*(.*?)(?=【最终回复】)', raw, re.DOTALL)
        reply_match = re.search(r'【最终回复】\s*(.*?)$', raw, re.DOTALL)
        if mono_match:
            monologue = mono_match.group(1).strip()
        if reply_match:
            reply = reply_match.group(1).strip()

    # 策略 2：只有【最终回复】
    elif "【最终回复】" in raw:
        parts = raw.split("【最终回复】", 1)
        monologue = parts[0].strip()
        reply = parts[1].strip()

    # 策略 3：只有【内心独白】
    elif "【内心独白】" in raw:
        content = raw.split("【内心独白】", 1)[1].strip()
        # 尝试按换行分割
        lines = [l.strip() for l in content.split('\n') if l.strip()]
        if len(lines) >= 2:
            monologue = lines[0]
            reply = '\n'.join(lines[1:])
        else:
            reply = content

    # 策略 4 (兜底)
    if not reply:
        clean = raw.strip()
        # 去掉动作描写
        clean = re.sub(r'（[^）]*）', '', clean).strip()
        clean = re.sub(r'\*[^*]+\*', '', clean).strip()
        reply = clean if clean else "..."

    # 清理
    reply = re.sub(r'（[^）]*）', '', reply).strip()
    reply = re.sub(r'\*[^*]+\*', '', reply).strip()
    if not reply:
        reply = "..."

    return monologue, reply


def sig_compact(agent: Agent, context: dict) -> str:
    signals = agent.compute_signals(context)
    parts = []
    for s in SIGNALS:
        v = signals[s]
        short = SIGNAL_LABELS[s][:2]
        if v > 0.65:
            parts.append(f'{C.RED}{short}{v:.0%}{C.RESET}')
        elif v < 0.35:
            parts.append(f'{C.BLUE}{short}{v:.0%}{C.RESET}')
        else:
            parts.append(f'{C.DIM}{short}{v:.0%}{C.RESET}')
    return ' '.join(parts) + f' | {DRIVE_LABELS[agent.get_dominant_drive()]}'


# ══════════════════════════════════════════════
# 主测试
# ══════════════════════════════════════════════

def run():
    print(f"""
{C.BOLD}══════════════════════════════════════════════════════════════
  Inner Monologue V2.1 — 去掉 prefill + 格式示例引导
  改进: 信号冲突拦截 / 中文方括号 / 格式示例 / 鲁棒解析
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

            # ── 信号 & 冲突检测 ──
            collisions = _detect_signal_collisions(signals)
            collision_labels = [c[0] for c in collisions] if collisions else []

            print(f'\n  {C.BOLD}[{name}]{C.RESET} {desc}', end='')
            if collision_labels:
                print(f'  {C.YELLOW}⚡{"、".join(collision_labels)}{C.RESET}', end='')
            print()
            print(f'  {sig_compact(agent, context)}')

            # ── 调用 LLM ──
            prompt = build_monologue_prompt(agent, context)
            raw = call_m2her(prompt, user_msg)
            monologue, reply = extract_reply(raw)

            if monologue:
                mono_short = monologue[:90] + ('...' if len(monologue) > 90 else '')
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
            raw = call_m2her(prompt, msg)
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
