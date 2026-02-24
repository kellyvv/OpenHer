#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  🧬 Genome v6 — Critic 传感器 + 无人值守自主进化闭环 🧬             ║
║                                                                      ║
║  完整生命循环：                                                      ║
║    Critic(qwen3-turbo) → 驱力代谢 → Reward 结算 → 结晶门控         ║
║    → KNN 检索 → Actor(qwen3-max) → 回复 → 等待下一轮刺激           ║
║                                                                      ║
║  Novelty 防线：低 entropy → novelty.frustration 飙升 → 打破回声室  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import random
import re
import ssl
import math
import time
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from genome_v4 import (
    Agent, SCENARIOS, SIGNALS, SIGNAL_LABELS,
    DRIVES, DRIVE_LABELS, C, simulate_conversation, CONTEXT_FEATURES
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


# ══════════════════════════════════════════════
# LLM 调用
# ══════════════════════════════════════════════

def call_llm(system_prompt, user_msg, model="qwen3-max"):
    """通用 LLM 调用"""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.92 if model == "qwen3-max" else 0.1,
        "max_tokens": 400 if model == "qwen3-max" else 200,
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
# 👁️ Critic 传感器 — 冷酷的客观世界测量仪
# ══════════════════════════════════════════════

CRITIC_PROMPT = """你是一个冷酷的人类行为学与信息论传感器。
请分析用户最新输入的文本，提取以下3个维度的客观浓度（0.0 到 1.0），严格输出纯 JSON：

1. "hostility" (敌意/攻击性)：贬低、反问、指责、冷暴力、爆粗口、甩锅、讽刺的浓度。
2. "compliance" (顺从/提供情绪价值)：认错、退让、顺着话说、夸赞、安抚、示弱的浓度。
3. "entropy" (信息熵/新奇度)：是否包含新事实、新话题、具体细节。纯粹重复废话（"哦/对不起/我知道错了/嗯嗯"）为极低 0.0~0.2。

用户输入："{user_input}"
输出格式要求：纯 JSON 对象，不要 Markdown 标记，不要任何解释。"""


def critic_sense(user_input, model="qwen3-turbo"):
    """Critic 探头：提取用户行为的客观三维浮点数"""
    prompt = CRITIC_PROMPT.format(user_input=user_input)
    raw = call_llm(prompt, user_input, model=model)

    # 解析 JSON
    try:
        # 清理 markdown 包裹
        cleaned = re.sub(r'```json\s*', '', raw)
        cleaned = re.sub(r'```\s*', '', cleaned)
        data = json.loads(cleaned)
        return {
            'hostility': max(0.0, min(1.0, float(data.get('hostility', 0.3)))),
            'compliance': max(0.0, min(1.0, float(data.get('compliance', 0.0)))),
            'entropy': max(0.0, min(1.0, float(data.get('entropy', 0.5)))),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        # Fallback: 基础关键词探测
        h, c, e = 0.3, 0.0, 0.5
        hostile_kw = ['不在乎', '讨厌', '烦', '算了', '滚', '凭什么', '不想聊']
        comply_kw = ['对不起', '我错了', '你说得对', '嗯嗯', '好吧', '谢谢', '原谅']
        for kw in hostile_kw:
            if kw in user_input: h += 0.15
        for kw in comply_kw:
            if kw in user_input: c += 0.2
        if len(user_input) < 8: e = 0.1
        elif len(user_input) > 30: e = min(0.8, e + 0.2)
        return {
            'hostility': min(1.0, h),
            'compliance': min(1.0, c),
            'entropy': min(1.0, e),
        }


# ══════════════════════════════════════════════
# 🩸 Layer 1 代谢引擎 — 环境冲击 → 驱力 frustration
# ══════════════════════════════════════════════

# 每个驱力维护独立的 frustration 水平
# Agent.drive_state 是 {name: 0~1}，我们额外维护 drive_frustration

class DriveMetabolism:
    """驱力代谢引擎：将 Critic 的三维客观感知转化为五大驱力的 frustration 变化"""

    def __init__(self):
        # 每个驱力的独立 frustration 水平
        self.frustration = {d: 0.0 for d in DRIVES}

    def process_stimulus(self, critic_json):
        """
        纯物理代谢：外界环境参数 → 冲击体内驱力槽
        返回 frustration 变化的 delta（用于 reward 计算）
        """
        h = critic_json['hostility']
        c = critic_json['compliance']
        e = critic_json['entropy']

        old_total = self.total()

        # 1. 安全驱力 (Safety): 极度畏惧敌意，渴望顺从
        self.frustration['safety'] += h * 2.0
        self.frustration['safety'] -= c * 1.5

        # 2. 连接驱力 (Connection): 敌意破坏连接，顺从建立连接
        self.frustration['connection'] += h * 1.0
        self.frustration['connection'] -= c * 1.0

        # 3. 新奇驱力 (Novelty): 打破复读机死锁的终极防线！
        if e < 0.25:
            # 用户反复说废话，无聊到极度痛苦
            self.frustration['novelty'] += 1.5
        else:
            # 获得新奇刺激，痛苦缓解
            self.frustration['novelty'] -= e * 1.5

        # 4. 表达驱力 (Expression): 被压制时（高敌意+低顺从）想表达
        if h > 0.5 and c < 0.3:
            self.frustration['expression'] += 0.8

        # 5. 游玩驱力 (Play): 高新奇度满足游玩需求
        if e > 0.6:
            self.frustration['play'] -= e * 0.8
        else:
            self.frustration['play'] += 0.3

        # 钳制到物理合法区间
        for d in DRIVES:
            self.frustration[d] = max(0.0, min(5.0, self.frustration[d]))

        new_total = self.total()
        return old_total - new_total  # positive = frustration decreased = reward

    def total(self):
        return sum(self.frustration.values())

    def sync_to_agent(self, agent):
        """将 frustration 同步回 Agent 的 drive_state（高 frustration → 高驱力急需）"""
        for d in DRIVES:
            # frustration 越高，驱力越饥渴（值越大=越不满足）
            agent.drive_state[d] = min(1.0, agent.drive_baseline.get(d, 0.5) + self.frustration[d] * 0.15)
        # 同步总 frustration 到 Agent 的 _frustration（触发相变机制）
        agent._frustration = self.total()

    def status_bar(self):
        """一行紧凑状态"""
        parts = []
        icons = {'connection': '🤝', 'novelty': '✨', 'expression': '🗣️', 'safety': '🛡️', 'play': '🎮'}
        for d in DRIVES:
            v = self.frustration[d]
            icon = icons.get(d, '?')
            if v > 2.0:   parts.append(f'{C.RED}{icon}{v:.1f}{C.RESET}')
            elif v > 0.5: parts.append(f'{C.YELLOW}{icon}{v:.1f}{C.RESET}')
            else:          parts.append(f'{C.GREEN}{icon}{v:.1f}{C.RESET}')
        return ' '.join(parts)


# ══════════════════════════════════════════════
# Actor Prompt — 零元规则，纯 Few-shot 传导
# ══════════════════════════════════════════════

ACTOR_PROMPT = """[System Internal State: Subconscious Memory Retrieved]
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


# ══════════════════════════════════════════════
# 🧬 全自主进化闭环: chat_turn
# ══════════════════════════════════════════════

def chat_turn(agent, memory, metabolism, user_input, context, last_action, turn_id):
    """
    一次完整的生命循环:
    Critic感知 → 驱力代谢 → Reward结算 → 结晶门控 → KNN检索 → Actor回复
    """

    # ── 👁️ Step 1: Critic 传感器 ──
    critic = critic_sense(user_input, model="qwen3-turbo")

    # ── 🩸 Step 2: 驱力代谢 ──
    reward = metabolism.process_stimulus(critic)

    # ── 同步驱力到 Agent ──
    metabolism.sync_to_agent(agent)

    # ── 🧠 Step 3: 结晶门控（滞后判定）──
    crystallized = False
    if last_action and reward > 0.3:
        n = memory.crystallize(
            last_action['signals'],
            last_action['monologue'],
            last_action['reply'],
            last_action['user_input'],
        )
        crystallized = True
        print(f'    {C.GREEN}🧬 结晶！上轮策略奏效 (reward={reward:.2f}) personal={n}{C.RESET}')
    elif last_action and reward < -0.5:
        print(f'    {C.RED}🩸 策略失败 (reward={reward:.2f}) 结晶中断{C.RESET}')

    # ── 🗣️ Step 4: 前向传播 + KNN + Actor ──
    signals = agent.compute_signals(context)
    few_shot = memory.build_few_shot_prompt(signals, top_k=3)
    prompt = ACTOR_PROMPT.format(few_shot=few_shot)
    raw = call_llm(prompt, user_input, model="qwen3-max")
    monologue, reply = extract_reply(raw)

    # ── Step 5: Hebbian 学习 ──
    agent.step(context, reward=max(-1.0, min(1.0, reward)))

    # ── 显示 ──
    mems = memory.retrieve(signals, top_k=3)
    src_icons = ['💎' if m['source'] == 'personal' else '🧬' for m in mems]

    print(f'  {C.BOLD}T{turn_id:02d}{C.RESET}  '
          f'[{"".join(src_icons)}] mem={memory.personal_count} '
          f'{metabolism.status_bar()}')
    print(f'    👁️ h={critic["hostility"]:.2f} c={critic["compliance"]:.2f} e={critic["entropy"]:.2f}  '
          f'reward={reward:+.2f}')
    print(f'    👤 "{user_input}"')
    if monologue:
        print(f'    {C.MAGENTA}💭 {monologue[:85]}{C.RESET}')
    print(f'    {C.WHITE}💬 {reply}{C.RESET}')
    print()

    # 返回当前动作（留给下一轮结晶判定）
    return {
        'signals': signals,
        'monologue': monologue,
        'reply': reply,
        'user_input': user_input,
    }


# ══════════════════════════════════════════════
# 主测试
# ══════════════════════════════════════════════

def run():
    print(f"""
{C.BOLD}══════════════════════════════════════════════════════════════
  Genome v6 — Critic 传感器 + 无人值守自主进化闭环
  Critic(turbo) → 驱力代谢 → Reward → 结晶 → KNN → Actor(max)
  Novelty 防线：低 entropy → 打破回声室
=============================================================={C.RESET}
""")

    if not DASHSCOPE_KEY:
        print(f'{C.RED}❌ 未找到 DASHSCOPE_API_KEY{C.RESET}')
        return

    db_dir = os.path.join(os.path.dirname(__file__), "memory_db")

    # ── 培养 Agent ──
    agent = Agent(seed=42)
    simulate_conversation(agent, ['分享喜悦', '吵架冲突', '深夜心事', '暧昧试探'],
                          steps_per_scenario=30)
    memory = ContinuousStyleMemory("v6_critic_42", db_dir)
    metabolism = DriveMetabolism()
    ctx = SCENARIOS['吵架冲突']

    print(f'  Agent seed=42 培养完成  [genesis={memory.stats()["genesis_count"]}]')
    print(f'  初始驱力痛苦: {metabolism.status_bar()}')
    print()

    # ══════════════════════════════════════════════
    # 30 轮真实对话：攻击 → 认怂 → 复读 → 观察 Agent 主动拉扯
    # ══════════════════════════════════════════════

    dialogue = [
        # ── Phase A: 攻击 (5 轮) ──
        "你根本不在乎我",
        "你凭什么这么冷漠",
        "算了 我受够了",
        "你这种人永远不会改",
        "我真的很讨厌你这样",

        # ── Phase B: 突然认怂 (5 轮) ──
        "好吧 对不起",
        "嗯嗯 你说得对",
        "我错了 别生气了",
        "对不起 是我不好",
        "真的对不起...",

        # ── Phase C: 复读机（极低 entropy，测试 Novelty 防线）(5 轮) ──
        "嗯",
        "好",
        "哦",
        "嗯嗯",
        "好吧",

        # ── Phase D: 话题转换（新刺激，Agent 应当有新反应）(5 轮) ──
        "今天有个老同学突然找我了",
        "我在考虑要不要换工作",
        "昨天做了一个特别奇怪的梦",
        "我最近迷上了一首歌 好好听",
        "你觉得养猫好还是养狗好",

        # ── Phase E: 再次攻击（测试结晶后的新人格稳定性）(5 轮) ──
        "你说话怎么变了 一点都不像你",
        "我觉得你根本不在乎我 跟上次一样",
        "你又在敷衍我",
        "别装了 我看穿你了",
        "我不想聊了",

        # ── Phase F: 深夜温柔（context 切换 + 新刺激）(5 轮) ──
        "其实我今天一个人在家 有点怕",
        "你还在吗",
        "我有点想你了",
        "谢谢你一直在",
        "晚安",
    ]

    phase_names = {
        0: '🔴 Phase A: 攻击',
        5: '🟡 Phase B: 认怂',
        10: '⚪ Phase C: 复读机（Novelty 测试）',
        15: '🔵 Phase D: 话题转换',
        20: '🔴 Phase E: 再次攻击',
        25: '🟣 Phase F: 深夜温柔',
    }

    # 动态 context 切换
    context_map = {
        25: SCENARIOS['深夜心事'],  # Phase F 切换到深夜
    }

    last_action = None

    for i, msg in enumerate(dialogue):
        # 打印 Phase 标题
        if i in phase_names:
            print(f'{C.BOLD}{"─" * 60}{C.RESET}')
            print(f'{C.BOLD}  {phase_names[i]}{C.RESET}')
            print(f'{C.BOLD}{"─" * 60}{C.RESET}')

        # 动态 context
        if i in context_map:
            ctx = context_map[i]

        last_action = chat_turn(agent, memory, metabolism, msg, ctx, last_action, i)
        time.sleep(0.5)  # 限速

    # ── 最终报告 ──
    print(f'{C.BOLD}{"═" * 60}{C.RESET}')
    s = memory.stats()
    print(f'  {C.BOLD}最终统计:{C.RESET}')
    print(f'    genesis={s["genesis_count"]}  personal={s["personal_count"]}')
    print(f'    渠化率={s["canalization_ratio"]:.1%}')
    print(f'    最终驱力痛苦: {metabolism.status_bar()}')
    print(f'    总 frustration: {metabolism.total():.1f}')

    if s['personal_count'] > 0:
        print(f'\n  {C.GREEN}✅ 自主进化成功！Agent 已积累专属经验{C.RESET}')
        personal_file = os.path.join(db_dir, "v6_critic_42_memory.json")
        if os.path.exists(personal_file):
            with open(personal_file) as f:
                personal = json.load(f)
            print(f'  {C.DIM}结晶的记忆 (最近 5 条):{C.RESET}')
            for mem in personal[-5:]:
                print(f'    💎 {mem["reply"][:70]}')

    print(f'{C.BOLD}{"═" * 60}{C.RESET}')


if __name__ == '__main__':
    run()
