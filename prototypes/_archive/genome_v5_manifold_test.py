#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  🧬 Genome v5 — Continuous Memory Manifold 集成测试 🧬              ║
║                                                                      ║
║  代码里没有任何一行关于性格的文字设定。                                ║
║  人格完全由 8 维空间 KNN 检索 + 历史样本插值涌现。                    ║
║                                                                      ║
║  v5.1 修复:                                                          ║
║    Fix 1: 净化 Prompt — 删除所有元规则文字                            ║
║    Fix 2: 接入 frustration 门控 — 真实驱力结算触发结晶                ║
║    Fix 3: 渠化引力 0.85x — 个人记忆的距离折扣                        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import random
import re
import ssl
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from genome_v4 import (
    Agent, SCENARIOS, SIGNALS, SIGNAL_LABELS,
    DRIVES, DRIVE_LABELS, C, simulate_conversation
)
from style_memory import ContinuousStyleMemory


# ── API 配置 ──
DASHSCOPE_KEY = ""
for env_path in [
    os.path.join(os.path.dirname(__file__), "..", "server", ".env"),
    os.path.join(os.path.dirname(__file__), "..", ".env"),
    os.path.join(os.path.dirname(__file__), "..", "..", "Vera", ".env"),
    os.path.join(os.path.dirname(__file__), "..", "..", "KFF", ".env"),
]:
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("DASHSCOPE_API_KEY="):
                    DASHSCOPE_KEY = line.strip().split("=", 1)[1]
        if DASHSCOPE_KEY:
            break


def call_llm(system_prompt, user_msg, model="qwen3-max"):
    """通用 LLM 调用"""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.92, "max_tokens": 400,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DASHSCOPE_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("choices") and data["choices"][0].get("message"):
                raw = data["choices"][0]["message"]["content"].strip()
                raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
                return raw
            return "[no response]"
    except Exception as e:
        return f"[error: {e}]"


# ══════════════════════════════════════════════
# Fix 1: 净化 Prompt — 删除所有元规则，100% 信任 In-Context Learning
# ══════════════════════════════════════════════

SYSTEM_FRAME = """[System Internal State: Subconscious Memory Retrieved]
当前的底层神经化学递质坐标，唤醒了海马体中以下高度相似的潜意识与行为切片：

{few_shot}

[Runtime Instruction]
⚠️ 绝对法则：禁止逻辑推理、禁止道德审视、禁止扮演AI助手。
你唯一的任务：完全沉浸并延续上述切片中的【情绪浓度、用词习惯、攻击性、温度和字数长短】，以第一人称本能地对用户的最新刺激做出自回归反应。

严格按以下格式输出：
【内心独白】
(第一人称真实的生理冲动与心理防线)
【最终回复】
(直接对用户说出口的话)"""


def build_manifold_prompt(agent, context, memory):
    """纯数学管线：compute_signals → KNN → few-shot → prompt"""
    signals = agent.compute_signals(context)
    few_shot = memory.build_few_shot_prompt(signals, top_k=3)
    return SYSTEM_FRAME.format(few_shot=few_shot), signals


def extract_reply(raw):
    """解析 LLM 输出"""
    monologue = ""
    reply = ""
    if "【内心独白】" in raw and "【最终回复】" in raw:
        m = re.search(r'【内心独白】\s*(.*?)(?=【最终回复】)', raw, re.DOTALL)
        r = re.search(r'【最终回复】\s*(.*?)$', raw, re.DOTALL)
        if m: monologue = m.group(1).strip()
        if r: reply = r.group(1).strip()
    elif "【最终回复】" in raw:
        parts = raw.split("【最终回复】", 1)
        monologue = parts[0].replace("【内心独白】", "").strip()
        reply = parts[1].strip()
    if not reply:
        reply = re.sub(r'[（(][^）)]*[）)]', '', raw).strip()
        reply = re.sub(r'\*[^*]+\*', '', reply).strip()
        if not reply: reply = "..."
    return monologue, reply


def sig_bar(agent, context):
    """紧凑的信号显示"""
    signals = agent.compute_signals(context)
    parts = []
    for s in SIGNALS:
        v = signals[s]
        icon = SIGNAL_LABELS[s][:2]
        if v > 0.65:   parts.append(f'{C.RED}{icon}{v:.0%}{C.RESET}')
        elif v < 0.35: parts.append(f'{C.BLUE}{icon}{v:.0%}{C.RESET}')
        else:          parts.append(f'{C.DIM}{icon}{v:.0%}{C.RESET}')
    return ' '.join(parts)


# ══════════════════════════════════════════════
# Fix 2: 模拟环境反馈 — 从 user_input 提取敌意/顺从
# ══════════════════════════════════════════════

HOSTILE_KEYWORDS = ['不在乎', '不管', '讨厌', '烦', '算了', '滚', '走开', '不想聊']
COMPLY_KEYWORDS = ['好吧', '对不起', '我错了', '你说得对', '嗯嗯', '谢谢']

def estimate_user_hostility(user_input):
    """极简的环境感知：从用户话语中提取敌意水平"""
    score = 0.3  # 基线
    for kw in HOSTILE_KEYWORDS:
        if kw in user_input:
            score += 0.2
    for kw in COMPLY_KEYWORDS:
        if kw in user_input:
            score -= 0.2
    return max(0.0, min(1.0, score))


# ══════════════════════════════════════════════
# 主测试
# ══════════════════════════════════════════════

def run():
    print(f"""
{C.BOLD}══════════════════════════════════════════════════════════════
  Genome v5.1 — Continuous Memory Manifold + 结晶闭环
  Fix 1: 净化 Prompt  | Fix 2: frustration 门控 | Fix 3: 渠化引力
=============================================================={C.RESET}
""")

    if not DASHSCOPE_KEY:
        print(f'{C.RED}❌ 未找到 DASHSCOPE_API_KEY{C.RESET}')
        return

    db_dir = os.path.join(os.path.dirname(__file__), "memory_db")

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
        memory = ContinuousStyleMemory(f"v51_{name}_{seed}", db_dir)
        agents[name] = (agent, memory, desc)
        s = memory.stats()
        print(f'  {name}(seed={seed}): {desc}  [genesis={s["genesis_count"]}]')
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
            agent, memory, desc = agents[name]
            print(f'\n  {C.BOLD}[{name}]{C.RESET} {desc}')
            print(f'  {sig_bar(agent, context)}')

            prompt, signals = build_manifold_prompt(agent, context, memory)
            raw = call_llm(prompt, user_msg)
            monologue, reply = extract_reply(raw)

            mems = memory.retrieve(signals, top_k=3)
            sources = [f'{m["source"][0]}d={m["distance"]:.2f}' for m in mems]
            print(f'  {C.DIM}🔍 {" | ".join(sources)}{C.RESET}')

            if monologue:
                print(f'  {C.MAGENTA}💭 {monologue[:90]}{C.RESET}')
            print(f'  {C.WHITE}💬 {reply}{C.RESET}')

            agent.step(context, random.gauss(0.2, 0.3))

        print()

    # ══════════════════════════════════════════════
    # 漂移测试 v2: 真实 frustration 闭环 + 记忆结晶
    # ══════════════════════════════════════════════
    print(f'\n{C.BOLD}{"─" * 60}{C.RESET}')
    print(f'{C.BOLD}  漂移测试 v2: frustration 闭环 + 记忆结晶{C.RESET}')
    print(f'{C.BOLD}  模拟: 前 25 轮持续攻击 → 后 25 轮用户认怂{C.RESET}')
    print(f'{C.BOLD}{"─" * 60}{C.RESET}\n')

    drift_agent = Agent(seed=42)
    drift_memory = ContinuousStyleMemory("v51_drift_42", db_dir)
    ctx = SCENARIOS['吵架冲突']

    # 模拟对话序列：先攻击，后认怂
    dialogue_sequence = (
        # 前 25 轮：用户不断攻击 → frustration 飙升
        [("我觉得你根本不在乎我", -0.4)] * 5 +
        [("你凭什么这么对我", -0.5)] * 5 +
        [("算了 你就是这种人", -0.6)] * 5 +
        [("烦死了 别理我", -0.3)] * 5 +
        [("我不想聊了", -0.2)] * 5 +
        # 后 25 轮：用户认怂退让 → frustration 下降 → 触发结晶！
        [("好吧 对不起", 0.5)] * 5 +
        [("嗯嗯 你说得对", 0.4)] * 5 +
        [("谢谢你一直在", 0.6)] * 5 +
        [("我错了...", 0.5)] * 5 +
        [("你能原谅我吗", 0.4)] * 5
    )

    # 缓存上一轮的动作，用于滞后结晶
    last_action = None

    for i, (msg, reward) in enumerate(dialogue_sequence):
        # 环境感知：根据用户输入更新驱力
        hostility = estimate_user_hostility(msg)

        # 驱力结算：攻击→safety受损；认怂→safety恢复
        if hostility > 0.5:
            drift_agent.drive_state['safety'] = max(0, drift_agent.drive_state['safety'] - 0.1)
        else:
            drift_agent.drive_state['safety'] = min(1.0, drift_agent.drive_state['safety'] + 0.05)
            drift_agent.drive_state['connection'] = min(1.0, drift_agent.drive_state['connection'] + 0.05)

        # 前向传播
        signals = drift_agent.compute_signals(ctx)
        current_frust = drift_agent._frustration

        # ══════════════════════════════════════════════
        # Fix 2 v2: 奖励门控结晶（Actor-Critic 模式）
        # ──────────────────────────────────────────────
        # 物理含义：用户当前的正面行为（reward > 0）验证了
        # Agent 上一轮的发言策略是有效的 → 结晶该策略
        # ══════════════════════════════════════════════
        if last_action and reward > 0.2:
            n = drift_memory.crystallize(
                last_action['signals'],
                last_action['monologue'],
                last_action['reply'],
                last_action['user_input'],
            )
            print(f'    {C.GREEN}🧬 结晶！上轮策略被用户验证 '
                  f'(reward={reward:.1f}) '
                  f'personal={n}{C.RESET}')

        # 每 5 轮做一次 LLM 调用（展示效果）
        if i % 5 == 0:
            prompt, sigs = build_manifold_prompt(drift_agent, ctx, drift_memory)
            raw = call_llm(prompt, msg)
            monologue, reply = extract_reply(raw)

            mems = drift_memory.retrieve(sigs, top_k=3)
            src_icons = ['💎' if m['source'] == 'personal' else '🧬' for m in mems]

            phase = '🔴攻击' if i < 25 else '🟢认怂'
            print(f'  {C.BOLD}R{i:02d}{C.RESET} [{phase}] '
                  f'w={sigs["warmth"]:.2f} df={sigs["defiance"]:.2f} '
                  f'frust={current_frust:.1f} '
                  f'[{"".join(src_icons)}] '
                  f'mem={drift_memory.personal_count}')
            print(f'    👤 "{msg}"')
            if monologue:
                print(f'    {C.MAGENTA}💭 {monologue[:80]}{C.RESET}')
            print(f'    {C.WHITE}💬 {reply}{C.RESET}')
            print()

            last_action = {
                'signals': sigs,
                'monologue': monologue,
                'reply': reply,
                'user_input': msg,
            }
        else:
            last_action = None  # 非 LLM 轮次不缓存

        drift_agent.step(ctx, reward=reward)

    # 最终统计
    print(f'{C.BOLD}{"─" * 60}{C.RESET}')
    s = drift_memory.stats()
    print(f'  漂移测试完成:')
    print(f'    genesis={s["genesis_count"]}  personal={s["personal_count"]}')
    print(f'    渠化率={s["canalization_ratio"]:.1%}')

    if s['personal_count'] > 0:
        print(f'\n  {C.GREEN}✅ 记忆结晶成功！Agent 已开始积累专属经验{C.RESET}')
        # 显示最后结晶的记忆
        print(f'  {C.DIM}最近结晶的记忆:{C.RESET}')
        personal_file = os.path.join(db_dir, "v51_drift_42_memory.json")
        if os.path.exists(personal_file):
            with open(personal_file) as f:
                personal = json.load(f)
            for mem in personal[-3:]:
                print(f'    💎 {mem["reply"][:60]}')
    else:
        print(f'\n  {C.YELLOW}⚠️ 未触发结晶（frustration 未成功下降）{C.RESET}')

    print(f'{C.BOLD}{"─" * 60}{C.RESET}')


if __name__ == '__main__':
    run()
