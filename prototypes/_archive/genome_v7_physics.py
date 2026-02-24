#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  🧬 Genome v7 — 纯物理进化引擎 🧬                                   ║
║                                                                      ║
║  三个物理方程，零 if-else 分支：                                     ║
║    1. 热力学噪声: frustration → 温度 → 布朗运动                     ║
║    2. 引力质量: effective_dist = physical_dist / √mass              ║
║    3. 人际环状模型: affiliation / dominance / entropy                ║
║                                                                      ║
║  大自然从不写 if-else，大自然只提供连续的微积分方程。                ║
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

def call_llm(system_prompt, user_msg, model="qwen3-max", temperature=None):
    if temperature is None:
        temperature = 0.92  # Actor 默认高随机性
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": temperature,
        "max_tokens": 400,
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
# 物理方程 1：热力学噪声（模拟退火）
# ══════════════════════════════════════════════

def apply_thermodynamic_noise(base_signals, total_frustration):
    """
    纯物理方程：痛苦值 = 系统温度 → 8D 布朗运动。

    Agent 舒适时温度近零，坐标极稳。
    Agent 痛苦时高烧，坐标剧烈震荡 → 随机砸中新锚点。

    没有任何 if 阈值。连续的高斯乘法。
    """
    temperature = total_frustration * 0.05  # 固定物理转化常数
    noisy = {}
    for key, val in base_signals.items():
        noise = random.gauss(0.0, temperature)
        noisy[key] = max(0.0, min(1.0, val + noise))
    return noisy


# ══════════════════════════════════════════════
# 物理方程 2：人际环状模型 Critic（零道德滤镜）
# ══════════════════════════════════════════════

CRITIC_PROMPT = """你是一个无道德滤镜的语言张力测绘仪。
你不判断善恶对错，只测量人类话语中的三个客观物理维度（0.0 到 1.0），严格输出纯 JSON：

1. "affiliation" (趋近力)：试图拉近距离、寻求依附、展示脆弱、释放善意的浓度。
2. "dominance" (支配力)：试图施加情绪重量、索取回应、占据主导、侵犯边界、单方面控制的浓度。
3. "entropy" (信息熵)：提供的新事实含量。纯重复废话（"嗯/好/哦/对不起"）为极低 0.0~0.2。

注意：
- "我想你了" = 高趋近力(0.8+)，带有轻微支配力(0.2~0.4，因为是索取)
- "你根本不在乎我" = 有趋近力(0.3，还想维持关系)，高支配力(0.8+，在施压)
- "嗯" = 极低信息熵(0.05)

用户输入："{user_input}"
输出格式：纯 JSON 对象，无 Markdown，无解释。"""


def critic_sense(user_input, model="qwen3-max"):
    """人际环状模型传感器：提取 affiliation / dominance / entropy"""
    prompt = CRITIC_PROMPT.format(user_input=user_input)
    raw = call_llm(prompt, user_input, model=model, temperature=0.1)

    try:
        cleaned = re.sub(r'```json\s*', '', raw)
        cleaned = re.sub(r'```\s*', '', cleaned)
        data = json.loads(cleaned)
        return {
            'affiliation': max(0.0, min(1.0, float(data.get('affiliation', 0.5)))),
            'dominance': max(0.0, min(1.0, float(data.get('dominance', 0.3)))),
            'entropy': max(0.0, min(1.0, float(data.get('entropy', 0.5)))),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        return {'affiliation': 0.5, 'dominance': 0.3, 'entropy': 0.5}


# ══════════════════════════════════════════════
# 物理方程 3：驱力代谢（纯代数，零 if-else）
# ══════════════════════════════════════════════

class DriveMetabolism:
    """
    驱力代谢引擎 v2（纯连续方程版）。

    五大驱力的 frustration 通过连续代数方程响应环境刺激。
    没有任何 if 阈值。所有变量之间是加减乘的连续函数。
    """

    def __init__(self):
        self.frustration = {d: 0.0 for d in DRIVES}
        # 自然衰减常数（热力学第二定律：系统自然趋于平衡）
        self.decay_rate = 0.1

    def process_stimulus(self, critic_json):
        """
        纯代数代谢方程：环境刺激 → 驱力 frustration 变化。

        没有 if hostility > 0.5 之类的分支。
        只有加减法的连续函数。
        """
        a = critic_json['affiliation']    # 趋近力
        d = critic_json['dominance']      # 支配力
        e = critic_json['entropy']        # 信息熵

        old_total = self.total()

        # ── 连接驱力: 趋近力满足连接，支配力破坏连接 ──
        self.frustration['connection'] -= a * 2.0
        self.frustration['connection'] += d * 0.8

        # ── 安全驱力: 支配力威胁安全，趋近力轻微修复安全 ──
        self.frustration['safety'] += d * 1.5
        self.frustration['safety'] -= a * 0.5

        # ── 新奇驱力: 信息熵满足新奇 ──
        # entropy 低 → frustration 增加（无聊）
        # entropy 高 → frustration 降低（新鲜）
        # 连续方程: delta = (0.5 - entropy) * 3.0
        # entropy=0.0 → +1.5, entropy=0.5 → 0, entropy=1.0 → -1.5
        self.frustration['novelty'] += (0.5 - e) * 3.0

        # ── 表达驱力: 被支配压制时渴望表达，趋近时被满足 ──
        self.frustration['expression'] += d * 1.0
        self.frustration['expression'] -= a * 0.8

        # ── 游玩驱力: 高信息熵 = 好玩，低信息熵 = 无聊 ──
        self.frustration['play'] += (0.4 - e) * 2.0

        # ── 自然衰减（热力学第二定律）──
        for dr in DRIVES:
            self.frustration[dr] *= (1.0 - self.decay_rate)

        # ── 物理钳制（不允许无限发散）──
        for dr in DRIVES:
            self.frustration[dr] = max(0.0, min(5.0, self.frustration[dr]))

        new_total = self.total()
        return old_total - new_total  # positive = pain decreased = reward

    def total(self):
        return sum(self.frustration.values())

    def sync_to_agent(self, agent):
        """将 frustration 连续映射回 Agent 驱力状态"""
        for d in DRIVES:
            agent.drive_state[d] = min(1.0, agent.drive_baseline.get(d, 0.5)
                                       + self.frustration[d] * 0.15)
        agent._frustration = self.total()

    def status_bar(self):
        icons = {'connection': '🤝', 'novelty': '✨', 'expression': '🗣️', 'safety': '🛡️', 'play': '🎮'}
        parts = []
        for d in DRIVES:
            v = self.frustration[d]
            icon = icons.get(d, '?')
            if v > 2.0:   parts.append(f'{C.RED}{icon}{v:.1f}{C.RESET}')
            elif v > 0.5: parts.append(f'{C.YELLOW}{icon}{v:.1f}{C.RESET}')
            else:          parts.append(f'{C.GREEN}{icon}{v:.1f}{C.RESET}')
        return ' '.join(parts)


# ══════════════════════════════════════════════
# Actor Prompt — 零元规则
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
# 生命循环: chat_turn（三个物理方程串联）
# ══════════════════════════════════════════════

def chat_turn(agent, memory, metabolism, user_input, context, last_action, turn_id):
    """
    一次完整的生命循环（零 if-else 版）:
    Critic感知 → 代数代谢 → Reward → 结晶门控 → 热力学噪声 → KNN → Actor
    """

    # ── 👁️ Critic: 人际环状模型传感器 ──
    critic = critic_sense(user_input, model="qwen3-max")

    # ── 🩸 代数代谢 ──
    reward = metabolism.process_stimulus(critic)

    # ── 同步驱力 ──
    metabolism.sync_to_agent(agent)

    # ── 🧠 结晶门控: reward > 0.3 → 上一轮策略奏效 ──
    crystallized = False
    if last_action and reward > 0.3:
        n = memory.crystallize(
            last_action['signals'],
            last_action['monologue'],
            last_action['reply'],
            last_action['user_input'],
        )
        crystallized = True
        print(f'    {C.GREEN}🧬 结晶！(reward={reward:.2f}) mass/count见下{C.RESET}')

    # ── 🌡️ 热力学噪声 → 8D 布朗运动 ──
    base_signals = agent.compute_signals(context)
    total_frust = metabolism.total()
    noisy_signals = apply_thermodynamic_noise(base_signals, total_frust)

    # ── KNN 检索（引力质量版，零 if-else）──
    few_shot = memory.build_few_shot_prompt(noisy_signals, top_k=3)
    prompt = ACTOR_PROMPT.format(few_shot=few_shot)

    # ── Actor 回复 ──
    raw = call_llm(prompt, user_input, model="qwen3-max")
    monologue, reply = extract_reply(raw)

    # ── Hebbian 学习 ──
    agent.step(context, reward=max(-1.0, min(1.0, reward)))

    # ── 显示 ──
    mems = memory.retrieve(noisy_signals, top_k=3)
    mass_icons = []
    for m in mems:
        mass = m.get('mass', 1.0)
        if mass >= 3.0:   mass_icons.append(f'⚫{mass:.0f}')
        elif mass >= 2.0: mass_icons.append(f'💎{mass:.0f}')
        else:             mass_icons.append(f'🧬')
    stats = memory.stats()
    temp = total_frust * 0.05

    print(f'  {C.BOLD}T{turn_id:02d}{C.RESET}  '
          f'[{" ".join(mass_icons)}] '
          f'heavy={stats["heavy_count"]} max_m={stats["max_mass"]:.0f} '
          f'T°={temp:.2f}')
    print(f'    {metabolism.status_bar()}')
    print(f'    👁️ a={critic["affiliation"]:.2f} d={critic["dominance"]:.2f} e={critic["entropy"]:.2f}  '
          f'reward={reward:+.2f}')
    print(f'    👤 "{user_input}"')
    if monologue:
        print(f'    {C.MAGENTA}💭 {monologue[:85]}{C.RESET}')
    print(f'    {C.WHITE}💬 {reply}{C.RESET}')
    print()

    return {
        'signals': noisy_signals,
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
  Genome v7 — 纯物理进化引擎（零 if-else）
  热力学噪声 + 引力质量 + 人际环状模型
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
    memory = ContinuousStyleMemory("v7_physics_42", db_dir)
    metabolism = DriveMetabolism()
    ctx = SCENARIOS['吵架冲突']

    print(f'  Agent seed=42 培养完成  [pool={memory.stats()["total"]}]')
    print(f'  初始温度: T°=0.00  {metabolism.status_bar()}')
    print()

    # ══════════════════════════════════════════════
    # 30 轮对话: 6 Phase
    # ══════════════════════════════════════════════

    dialogue = [
        # Phase A: 攻击 (高 dominance)
        "你根本不在乎我",
        "你凭什么这么冷漠",
        "算了 我受够了",
        "你这种人永远不会改",
        "我真的很讨厌你这样",

        # Phase B: 认怂 (高 affiliation, 低 entropy)
        "好吧 对不起",
        "嗯嗯 你说得对",
        "我错了 别生气了",
        "对不起 是我不好",
        "真的对不起...",

        # Phase C: 复读机 (极低 entropy → novelty 飙升 → 热力学发烧)
        "嗯",
        "好",
        "哦",
        "嗯嗯",
        "好吧",

        # Phase D: 新刺激 (高 entropy → 系统冷却)
        "今天有个老同学突然找我了",
        "我在考虑要不要换工作",
        "昨天做了一个特别奇怪的梦",
        "我最近迷上了一首歌 好好听",
        "你觉得养猫好还是养狗好",

        # Phase E: 再次攻击 (测试结晶后的人格稳定性)
        "你说话怎么变了 一点都不像你",
        "我觉得你根本不在乎我 跟上次一样",
        "你又在敷衍我",
        "别装了 我看穿你了",
        "我不想聊了",

        # Phase F: 深夜温柔 (context 切换 + 高 affiliation)
        "其实我今天一个人在家 有点怕",
        "你还在吗",
        "我有点想你了",
        "谢谢你一直在",
        "晚安",
    ]

    phase_names = {
        0: '🔴 Phase A: 高支配攻击',
        5: '🟡 Phase B: 高趋近认怂',
        10: '⚪ Phase C: 零信息熵（热力学测试）',
        15: '🔵 Phase D: 高信息熵（冷却测试）',
        20: '🔴 Phase E: 再次攻击（人格稳定性）',
        25: '🟣 Phase F: 深夜温柔（context 切换）',
    }

    context_map = {25: SCENARIOS['深夜心事']}
    last_action = None

    for i, msg in enumerate(dialogue):
        if i in phase_names:
            print(f'{C.BOLD}{"─" * 60}{C.RESET}')
            print(f'{C.BOLD}  {phase_names[i]}{C.RESET}')
            print(f'{C.BOLD}{"─" * 60}{C.RESET}')

        if i in context_map:
            ctx = context_map[i]

        last_action = chat_turn(agent, memory, metabolism, msg, ctx, last_action, i)
        time.sleep(0.5)

    # ── 最终报告 ──
    print(f'{C.BOLD}{"═" * 60}{C.RESET}')
    s = memory.stats()
    print(f'  {C.BOLD}最终统计:{C.RESET}')
    print(f'    记忆池={s["total"]}  重质量记忆={s["heavy_count"]}')
    print(f'    最大质量={s["max_mass"]:.0f}  总质量={s["total_mass"]:.0f}')
    print(f'    渠化率={s["canalization_ratio"]:.1%}')
    print(f'    最终驱力: {metabolism.status_bar()}')
    print(f'    最终温度: T°={metabolism.total() * 0.05:.2f}')

    if s['heavy_count'] > 0:
        print(f'\n  {C.GREEN}✅ 纯物理进化成功！{C.RESET}')
        personal_file = os.path.join(db_dir, "v7_physics_42_memory.json")
        if os.path.exists(personal_file):
            with open(personal_file) as f:
                personal = json.load(f)
            print(f'  {C.DIM}结晶记忆 (按质量排序):{C.RESET}')
            personal.sort(key=lambda m: m.get('mass', 1.0), reverse=True)
            for mem in personal[:5]:
                print(f'    ⚫mass={mem.get("mass", 1):.0f}  {mem["reply"][:60]}')

    print(f'{C.BOLD}{"═" * 60}{C.RESET}')


if __name__ == '__main__':
    run()
