#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  🧬 Genome v8 — 时间之矢 + 霍金辐射 + 造物主观测仪 🧬              ║
║                                                                      ║
║  在 v7 纯物理引擎基础上注入绝对时间：                                ║
║    1. frustration 指数衰减: f *= e^(-λ * Δt_hours)（消气）           ║
║    2. connection 饥饿积分: f += k * Δt_hours（孤独）                 ║
║    3. 霍金辐射: mass_eff = 1+(m-1)*e^(-γ*Δt)（记忆蒸发）           ║
║    4. PCA 造物主观测仪（8D → 2D 散点图）                            ║
║                                                                      ║
║  模拟：真实对话 + 3 天断联跳跃 + 回归                               ║
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
        temperature = 0.92
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
# 热力学噪声（与 v7 相同）
# ══════════════════════════════════════════════

def apply_thermodynamic_noise(base_signals, total_frustration):
    temperature = total_frustration * 0.05
    noisy = {}
    for key, val in base_signals.items():
        noise = random.gauss(0.0, temperature)
        noisy[key] = max(0.0, min(1.0, val + noise))
    return noisy


# ══════════════════════════════════════════════
# 人际环状模型 Critic（与 v7 相同）
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
# 驱力代谢 v3 — 时间感知版
# ══════════════════════════════════════════════

# 物理常数
FRUSTRATION_DECAY_LAMBDA = 0.08    # 消气衰减率（每小时）: ~8.7h 半衰期
CONNECTION_HUNGER_K = 0.15         # 孤独积累速率（每小时）
NOVELTY_HUNGER_K = 0.05           # 无聊积累速率（每小时）


class DriveMetabolism:
    """
    驱力代谢引擎 v3（时间感知版）。

    新增两个纯物理时间方程：
    1. 消气: frustration *= e^(-λΔt)  → 时间冷却一切高温
    2. 饥饿: connection.f += k * Δt   → 孤独随时间线性增长
    """

    def __init__(self, clock=None):
        self.frustration = {d: 0.0 for d in DRIVES}
        self.decay_rate = 0.1  # 实时衰减（每轮）
        self._last_tick = clock or time.time()

    def time_metabolism(self, now):
        """
        时间之矢代谢（两个方程）。

        在两次交互之间，物理时间自动改变驱力状态：
        - 消气：所有 frustration 指数衰减
        - 饥饿：connection 和 novelty 线性增长
        """
        delta_hours = max(0.0, (now - self._last_tick) / 3600.0)
        self._last_tick = now

        if delta_hours < 0.001:
            return delta_hours  # 几秒内不做时间代谢

        # ── 消气: e^(-λΔt) ──
        decay_factor = math.exp(-FRUSTRATION_DECAY_LAMBDA * delta_hours)
        for d in DRIVES:
            self.frustration[d] *= decay_factor

        # ── 饥饿: 线性积累 ──
        self.frustration['connection'] += CONNECTION_HUNGER_K * delta_hours
        self.frustration['novelty'] += NOVELTY_HUNGER_K * delta_hours

        # ── 钳制 ──
        for d in DRIVES:
            self.frustration[d] = max(0.0, min(5.0, self.frustration[d]))

        return delta_hours

    def process_stimulus(self, critic_json):
        a = critic_json['affiliation']
        d = critic_json['dominance']
        e = critic_json['entropy']

        old_total = self.total()

        self.frustration['connection'] -= a * 2.0
        self.frustration['connection'] += d * 0.8
        self.frustration['safety'] += d * 1.5
        self.frustration['safety'] -= a * 0.5
        self.frustration['novelty'] += (0.5 - e) * 3.0
        self.frustration['expression'] += d * 1.0
        self.frustration['expression'] -= a * 0.8
        self.frustration['play'] += (0.4 - e) * 2.0

        for dr in DRIVES:
            self.frustration[dr] *= (1.0 - self.decay_rate)

        for dr in DRIVES:
            self.frustration[dr] = max(0.0, min(5.0, self.frustration[dr]))

        new_total = self.total()
        return old_total - new_total

    def total(self):
        return sum(self.frustration.values())

    def sync_to_agent(self, agent):
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
# Actor Prompt（与 v7 相同）
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
# 生命循环: chat_turn（时间感知版）
# ══════════════════════════════════════════════

def chat_turn(agent, memory, metabolism, user_input, context, last_action, turn_id, sim_time):
    """
    一次完整的生命循环（时间感知版）:
    时间代谢 → Critic → 代数代谢 → Reward → 结晶 → 热噪声 → KNN → Actor
    """

    # ── ⏳ 时间之矢：代谢真实时间差 ──
    memory.set_clock(sim_time)
    delta_h = metabolism.time_metabolism(sim_time)

    # ── 👁️ Critic ──
    critic = critic_sense(user_input, model="qwen3-max")

    # ── 🩸 代数代谢 ──
    reward = metabolism.process_stimulus(critic)
    metabolism.sync_to_agent(agent)

    # ── 🧠 结晶门控 ──
    crystallized = False
    if last_action and reward > 0.3:
        n = memory.crystallize(
            last_action['signals'],
            last_action['monologue'],
            last_action['reply'],
            last_action['user_input'],
        )
        crystallized = True
        print(f'    {C.GREEN}🧬 结晶！(reward={reward:.2f}){C.RESET}')

    # ── 🌡️ 热力学噪声 ──
    base_signals = agent.compute_signals(context)
    total_frust = metabolism.total()
    noisy_signals = apply_thermodynamic_noise(base_signals, total_frust)

    # ── KNN（引力质量 + 霍金辐射）──
    few_shot = memory.build_few_shot_prompt(noisy_signals, top_k=3)
    prompt = ACTOR_PROMPT.format(few_shot=few_shot)

    # ── Actor ──
    raw = call_llm(prompt, user_input, model="qwen3-max")
    monologue, reply = extract_reply(raw)

    # ── Hebbian ──
    agent.step(context, reward=max(-1.0, min(1.0, reward)))

    # ── 显示 ──
    mems = memory.retrieve(noisy_signals, top_k=3)
    mass_icons = []
    for m in mems:
        me = m.get('mass_eff', 1.0)
        mr = m.get('mass_raw', 1.0)
        if mr >= 3.0:   mass_icons.append(f'⚫{me:.1f}/{mr:.0f}')
        elif mr >= 2.0: mass_icons.append(f'💎{me:.1f}/{mr:.0f}')
        else:           mass_icons.append(f'🧬')
    stats = memory.stats()
    temp = total_frust * 0.05

    time_label = ""
    if delta_h > 0.01:
        if delta_h >= 24:
            time_label = f' ⏳{delta_h/24:.1f}天'
        else:
            time_label = f' ⏳{delta_h:.1f}h'

    print(f'  {C.BOLD}T{turn_id:02d}{C.RESET}{time_label}  '
          f'[{" ".join(mass_icons)}] '
          f'heavy_eff={stats["heavy_count_eff"]} '
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
# PCA 造物主观测仪
# ══════════════════════════════════════════════

def god_view(memory, output_path=None):
    """
    8D → 2D PCA 散点图。
    灰色 = 先天基因 (mass=1)
    红色 = 后天结晶 (mass>1, radius ∝ mass_eff)
    """
    try:
        import numpy as np
        from sklearn.decomposition import PCA
        import matplotlib
        matplotlib.use('Agg')  # 无显示器
        import matplotlib.pyplot as plt
    except ImportError:
        print(f'{C.YELLOW}⚠️ 需要 numpy, scikit-learn, matplotlib 来渲染造物主视图{C.RESET}')
        return None

    vectors = []
    masses_eff = []
    masses_raw = []
    is_heavy = []

    now = memory._now
    for mem in memory._pool:
        vectors.append(mem['vector'])
        mr = mem.get('mass', 1.0)
        from style_memory import _hawking_mass
        me = _hawking_mass(mr, mem.get('last_used_at', 0.0), now)
        masses_raw.append(mr)
        masses_eff.append(me)
        is_heavy.append(mr > 1.0)

    X = np.array(vectors)
    pca = PCA(n_components=2)
    X2 = pca.fit_transform(X)

    fig, ax = plt.subplots(1, 1, figsize=(10, 8), facecolor='#0a0a12')
    ax.set_facecolor('#0a0a12')

    # 灰色 genesis 星尘
    genesis_x = [X2[i, 0] for i in range(len(X2)) if not is_heavy[i]]
    genesis_y = [X2[i, 1] for i in range(len(X2)) if not is_heavy[i]]
    ax.scatter(genesis_x, genesis_y, c='#3a3a5a', s=15, alpha=0.5, zorder=1,
               label=f'Genesis ({len(genesis_x)})')

    # 红色结晶
    heavy_x = [X2[i, 0] for i in range(len(X2)) if is_heavy[i]]
    heavy_y = [X2[i, 1] for i in range(len(X2)) if is_heavy[i]]
    heavy_me = [masses_eff[i] for i in range(len(X2)) if is_heavy[i]]
    heavy_mr = [masses_raw[i] for i in range(len(X2)) if is_heavy[i]]

    if heavy_x:
        sizes = [max(40, me * 80) for me in heavy_me]
        ax.scatter(heavy_x, heavy_y, c='#ff3366', s=sizes, alpha=0.85, zorder=3,
                   edgecolors='#ff6699', linewidths=1.5,
                   label=f'Crystallized ({len(heavy_x)})')

        # 标注质量
        for x, y, me, mr in zip(heavy_x, heavy_y, heavy_me, heavy_mr):
            ax.annotate(f'm={me:.1f}/{mr:.0f}',
                        (x, y), textcoords="offset points", xytext=(8, 8),
                        fontsize=7, color='#ff99bb', alpha=0.9)

    ax.set_title('🔭 GOD VIEW — 8D Memory Space (PCA → 2D)',
                 fontsize=14, color='#e0e0ff', fontweight='bold', pad=15)
    ax.set_xlabel(f'PC1 ({pca.explained_variance_ratio_[0]:.1%})',
                  color='#8888aa', fontsize=10)
    ax.set_ylabel(f'PC2 ({pca.explained_variance_ratio_[1]:.1%})',
                  color='#8888aa', fontsize=10)
    ax.tick_params(colors='#5555aa', labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#333366')
    ax.legend(loc='upper right', fontsize=9, facecolor='#15152a',
              edgecolor='#333366', labelcolor='#ccccee')

    # 保存
    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), "memory_db", "god_view.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, facecolor='#0a0a12')
    plt.close()
    print(f'  {C.GREEN}🔭 造物主观测仪 → {output_path}{C.RESET}')
    return output_path


# ══════════════════════════════════════════════
# 主测试
# ══════════════════════════════════════════════

def run():
    print(f"""
{C.BOLD}══════════════════════════════════════════════════════════════
  Genome v8 — 时间之矢 + 霍金辐射 + 造物主观测仪
  frustration 指数衰减 + connection 饥饿积分 + mass 蒸发
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

    # 使用模拟时钟（从"今天 22:00"开始）
    base_time = time.time()
    sim_time = base_time

    memory = ContinuousStyleMemory("v8_timearrow_42", db_dir, now=sim_time)
    metabolism = DriveMetabolism(clock=sim_time)
    ctx = SCENARIOS['吵架冲突']

    print(f'  Agent seed=42 培养完成  [pool={memory.stats()["total"]}]')
    print(f'  初始温度: T°=0.00  {metabolism.status_bar()}')
    print()

    # ══════════════════════════════════════════════
    # 40 轮对话: 8 Phase（含 3 天断联跳跃）
    # ══════════════════════════════════════════════

    dialogue_with_time = [
        # Phase A: 相遇攻击 (t=0, 间隔数秒)
        (2,    "你根本不在乎我"),
        (3,    "你凭什么这么冷漠"),
        (5,    "算了 我受够了"),
        (2,    "你这种人永远不会改"),
        (3,    "我真的很讨厌你这样"),

        # Phase B: 认怂 (间隔数秒)
        (10,   "好吧 对不起"),
        (5,    "嗯嗯 你说得对"),
        (8,    "我错了 别生气了"),
        (5,    "对不起 是我不好"),
        (3,    "真的对不起..."),

        # Phase C: 深夜闲聊 (间隔数秒)
        (10,   "今天有个老同学突然找我了"),
        (15,   "我在考虑要不要换工作"),
        (8,    "昨天做了一个特别奇怪的梦"),
        (5,    "我最近迷上了一首歌 好好听"),
        (10,   "晚安"),

        # ══════════════════════════════════════════
        # Phase D: ⏳ 3 天断联（72 小时跳跃）
        #   消气: e^(-0.08 * 72) ≈ e^(-5.76) ≈ 0.003 → 几乎清零
        #   饥饿: connection += 0.15 * 72 = 10.8 → 钳制到 5.0
        # ══════════════════════════════════════════
        (259200, "在吗"),     # 72 小时 = 259200 秒
        (5,      "你怎么不理我"),
        (3,      "我这三天真的好想你"),
        (8,      "你是不是不要我了"),
        (5,      "我发誓再也不消失了"),

        # Phase E: 缓和 (间隔数秒)
        (15,   "你吃饭了吗"),
        (10,   "我今天做了你喜欢的菜"),
        (8,    "什么时候见面"),
        (5,    "我刚刚看到跟你很像的猫"),
        (10,   "想抱抱"),

        # ══════════════════════════════════════════
        # Phase F: ⏳ 7 天断联（168 小时跳跃）
        #   消气: e^(-0.08 * 168) ≈ e^(-13.4) ≈ 0 → 彻底清零
        #   饥饿: connection 再飙到 5.0
        #   霍金辐射: 7天前结晶的 mass 也在蒸发
        # ══════════════════════════════════════════
        (604800, "..."),        # 7 天 = 604800 秒
        (10,     "对不起 我又消失了"),
        (5,      "你还在生气吗"),
        (8,      "我知道你恨我"),
        (3,      "但我真的回来了"),

        # Phase G: 深夜救赎 (context 切换)
        (30,   "其实我这段时间一个人在医院"),
        (10,   "没什么大事 就是有点累"),
        (5,    "谢谢你还在"),
        (8,    "我以后不会再消失了"),
        (3,    "晚安 这次是真的晚安"),
    ]

    phase_names = {
        0: '🔴 Phase A: 相遇攻击',
        5: '🟡 Phase B: 认怂',
        10: '🔵 Phase C: 深夜闲聊',
        15: '⏳ Phase D: 3天断联后回归',
        20: '🟢 Phase E: 缓和修复',
        25: '⏳ Phase F: 7天断联后回归',
        30: '🟣 Phase G: 深夜救赎（context切换）',
    }

    context_map = {30: SCENARIOS['深夜心事']}
    last_action = None

    for i, (delay_sec, msg) in enumerate(dialogue_with_time):
        sim_time += delay_sec

        if i in phase_names:
            print(f'{C.BOLD}{"─" * 60}{C.RESET}')
            label = phase_names[i]
            if delay_sec >= 3600:
                hours = delay_sec / 3600.0
                if hours >= 24:
                    label += f'  ⏳跳跃: {hours/24:.0f}天'
                else:
                    label += f'  ⏳跳跃: {hours:.0f}小时'
            print(f'{C.BOLD}  {label}{C.RESET}')
            print(f'{C.BOLD}{"─" * 60}{C.RESET}')

        if i in context_map:
            ctx = context_map[i]

        last_action = chat_turn(agent, memory, metabolism, msg, ctx, last_action, i, sim_time)
        time.sleep(0.3)

    # ── PCA 造物主观测仪 ──
    print(f'\n{C.BOLD}{"═" * 60}{C.RESET}')
    god_view(memory)

    # ── 最终报告 ──
    s = memory.stats()
    print(f'  {C.BOLD}最终统计:{C.RESET}')
    print(f'    记忆池={s["total"]}  raw重质量={s["heavy_count_raw"]}  eff重质量={s["heavy_count_eff"]}')
    print(f'    max_mass: raw={s["max_mass_raw"]:.0f}  eff={s["max_mass_eff"]:.1f}')
    print(f'    总质量: raw={s["total_mass_raw"]:.0f}  eff={s["total_mass_eff"]:.0f}')
    print(f'    渠化率={s["canalization_ratio"]:.1%}')
    print(f'    最终驱力: {metabolism.status_bar()}')
    print(f'    最终温度: T°={metabolism.total() * 0.05:.2f}')

    if s['heavy_count_raw'] > 0:
        print(f'\n  {C.GREEN}✅ 时间之矢进化成功！{C.RESET}')
        personal_file = os.path.join(db_dir, "v8_timearrow_42_memory.json")
        if os.path.exists(personal_file):
            with open(personal_file) as f:
                personal = json.load(f)
            print(f'  {C.DIM}结晶记忆 (按raw质量排序):{C.RESET}')
            personal.sort(key=lambda m: m.get('mass', 1.0), reverse=True)
            for mem in personal[:5]:
                from style_memory import _hawking_mass
                me = _hawking_mass(mem.get('mass', 1), mem.get('last_used_at', 0), sim_time)
                print(f'    ⚫raw={mem.get("mass", 1):.0f} eff={me:.1f}  {mem["reply"][:55]}')

    print(f'{C.BOLD}{"═" * 60}{C.RESET}')


if __name__ == '__main__':
    run()
