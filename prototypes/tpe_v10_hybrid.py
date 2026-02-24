#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  🧬 TPE v10 — Hybrid Engine 🧬                                     ║
║                                                                      ║
║  v8 涌现骨架 + v9 智能代谢 + 简化 prompt injection                 ║
║                                                                      ║
║  保留（v8 涌现核心）:                                               ║
║    ✅ 随机神经网络（seed → 不同人格）                                ║
║    ✅ Hebbian 学习（人格随经历进化）                                 ║
║    ✅ 相变（突然性格转变）                                           ║
║    ✅ 热力学噪声（情绪状态影响行为可预测性）                        ║
║    ✅ 时间代谢 + 引力记忆 + 霍金辐射                                ║
║                                                                      ║
║  替换（v8 硬编码部分）:                                             ║
║    🔄 固定代谢系数 → LLM 判断 frustration 变化                     ║
║    🔄 40条五档描述 → 直接注入信号数值 + 极简两端锚点               ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import re
import ssl
import math
import time
import random
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_archive"))

from genome_v4 import (
    Agent, SCENARIOS, SIGNALS, SIGNAL_LABELS,
    DRIVES, DRIVE_LABELS, C, simulate_conversation, CONTEXT_FEATURES
)
from style_memory import ContinuousStyleMemory

# ── API 配置 ──
MODEL_CONFIGS = {
    "qwen3-max": {
        "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "key_env": "DASHSCOPE_API_KEY",
        "temperature": 0.92,
    },
    "MiniMax-M2.5-highspeed": {
        "endpoint": "https://api.minimaxi.com/v1/text/chatcompletion_v2",
        "key_env": "MINIMAX_API_KEY",
        "model_id": "MiniMax-M2.5-highspeed",
        "temperature": 0.7,
    },
}

API_KEYS = {}
for env_path in [
    os.path.join(os.path.dirname(__file__), "..", "server", ".env"),
    os.path.join(os.path.dirname(__file__), "..", ".env"),
    os.path.join(os.path.dirname(__file__), "..", "..", "Vera", ".env"),
    os.path.join(os.path.dirname(__file__), "..", "..", "KFF", ".env"),
]:
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    if k in ("DASHSCOPE_API_KEY", "MINIMAX_API_KEY") and k not in API_KEYS:
                        API_KEYS[k] = v

# Also check env vars
for key in ("DASHSCOPE_API_KEY", "MINIMAX_API_KEY"):
    if key not in API_KEYS and os.environ.get(key):
        API_KEYS[key] = os.environ[key]

DASHSCOPE_KEY = API_KEYS.get("DASHSCOPE_API_KEY", "")


# ══════════════════════════════════════════════
# LLM 调用
# ══════════════════════════════════════════════

def call_llm(system_prompt, user_msg, model="qwen3-max", temperature=None):
    config = MODEL_CONFIGS.get(model, MODEL_CONFIGS["qwen3-max"])
    api_key = API_KEYS.get(config["key_env"], DASHSCOPE_KEY)
    endpoint = config["endpoint"]
    model_id = config.get("model_id", model)

    if temperature is None:
        temperature = config.get("temperature", 0.92)

    payload = json.dumps({
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": temperature,
        "max_tokens": 600,
    }).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
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
# 物理常数（时间代谢用，LLM 做不了）
# ══════════════════════════════════════════════

FRUSTRATION_DECAY_LAMBDA = 0.08
CONNECTION_HUNGER_K = 0.15
NOVELTY_HUNGER_K = 0.05


# ══════════════════════════════════════════════
# 时间代谢（保留，纯数学）+ LLM 刺激代谢（替代固定系数）
# ══════════════════════════════════════════════

class HybridMetabolism:
    """
    时间代谢（数学方程）+ LLM 刺激代谢（替代固定系数）。

    与 v8 的区别：
    - time_metabolism() 完全相同
    - process_stimulus() 删除，改为 apply_llm_delta()
    """

    def __init__(self, clock=None):
        self.frustration = {d: 0.0 for d in DRIVES}
        self.decay_rate = 0.1
        self._last_tick = clock or time.time()

    def time_metabolism(self, now):
        """纯物理时间方程：消气 + 饥饿。（与 v8 完全一致）"""
        delta_hours = max(0.0, (now - self._last_tick) / 3600.0)
        self._last_tick = now
        if delta_hours < 0.001:
            return delta_hours

        decay_factor = math.exp(-FRUSTRATION_DECAY_LAMBDA * delta_hours)
        for d in DRIVES:
            self.frustration[d] *= decay_factor

        self.frustration['connection'] += CONNECTION_HUNGER_K * delta_hours
        self.frustration['novelty'] += NOVELTY_HUNGER_K * delta_hours

        for d in DRIVES:
            self.frustration[d] = max(0.0, min(5.0, self.frustration[d]))
        return delta_hours

    def apply_llm_delta(self, delta_dict):
        """应用 LLM 判断的 frustration 变化量（替代 v8 的固定代数规则）。"""
        old_total = self.total()
        for d in DRIVES:
            if d in delta_dict:
                self.frustration[d] += delta_dict[d]
            self.frustration[d] *= (1.0 - self.decay_rate)  # 每轮衰减（保留自 v8）
            self.frustration[d] = max(0.0, min(5.0, self.frustration[d]))
        return old_total - self.total()

    def sync_to_agent(self, agent):
        """将 frustration 同步到 Agent 的 drive_state（与 v8 一致）。"""
        for d in DRIVES:
            agent.drive_state[d] = min(1.0, agent.drive_baseline.get(d, 0.5)
                                       + self.frustration[d] * 0.15)
        agent._frustration = self.total()

    def total(self):
        return sum(self.frustration.values())

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
# LLM 感知（替代 v8 的 Critic + 固定代谢系数）
# ══════════════════════════════════════════════

CRITIC_PROMPT_V10 = """你是一个角色扮演 Agent 的情感感知器。分析用户输入，输出两组数据：

1. 对话上下文感知（8 维，0.0~1.0）：
  - user_emotion: 用户情绪（-1=负面, 0=中性, 1=正面）
  - topic_intimacy: 话题私密度（0=公事, 1=私密）
  - conversation_depth: 对话深度（0=刚开始, 1=聊很久了）
  - user_engagement: 用户投入度（0=敷衍, 1=投入）
  - conflict_level: 冲突程度（0=和谐, 1=冲突）
  - novelty_level: 信息新鲜度（0=重复/日常, 1=全新信息）
  - user_vulnerability: 用户敞开程度（0=防御, 1=敞开心扉）
  - time_of_day: 时间氛围（0=白天日常, 1=深夜私密）

2. Agent 5 个驱力的挫败变化量（正=更挫败，负=被缓解）

Agent 当前挫败值（0=满足, 5=极度渴望）：
{frustration_json}

用户说了："{user_input}"

严格输出纯 JSON：
{
  "context": {"user_emotion": 0.3, "topic_intimacy": 0.8, "conversation_depth": 0.5, "user_engagement": 0.7, "conflict_level": 0.1, "novelty_level": 0.3, "user_vulnerability": 0.6, "time_of_day": 0.5},
  "frustration_delta": {"connection": -0.3, "novelty": 0.0, "expression": 0.1, "safety": -0.2, "play": 0.0}
}"""


def critic_and_metabolize(user_input, frustration_dict, model="qwen3-max"):
    """
    LLM 直接输出 8D context + frustration delta。
    —— 替代: critic_sense() + build_context_from_critic() + process_stimulus()
    —— 消除了最后一块硬编码: 3D→8D 映射公式
    """
    prompt = CRITIC_PROMPT_V10.replace(
        "{frustration_json}", json.dumps(frustration_dict, ensure_ascii=False)
    ).replace("{user_input}", user_input)

    raw = call_llm(prompt, user_input, model=model, temperature=0.2)

    try:
        cleaned = re.sub(r'```json\s*', '', raw)
        cleaned = re.sub(r'```\s*', '', cleaned)
        data = json.loads(cleaned)

        # 8D context
        raw_ctx = data.get('context', {})
        context = {}
        for feat in CONTEXT_FEATURES:
            v = float(raw_ctx.get(feat, 0.5))
            if feat == 'user_emotion':
                context[feat] = max(-1.0, min(1.0, v))
            else:
                context[feat] = max(0.0, min(1.0, v))

        # frustration delta
        frustration_delta = {}
        raw_delta = data.get('frustration_delta', {})
        for d in DRIVES:
            v = float(raw_delta.get(d, 0.0))
            frustration_delta[d] = max(-3.0, min(3.0, v))

        return context, frustration_delta

    except (json.JSONDecodeError, ValueError, TypeError):
        return (
            {f: 0.5 for f in CONTEXT_FEATURES},
            {d: 0.0 for d in DRIVES},
        )


# (Context 映射公式已删除 — Critic LLM 直接输出 8D context)


# ══════════════════════════════════════════════
# 热力学噪声（保留自 v8）
# ══════════════════════════════════════════════

def apply_thermodynamic_noise(base_signals, total_frustration):
    temperature = total_frustration * 0.05
    noisy = {}
    for key, val in base_signals.items():
        noise = random.gauss(0.0, temperature)
        noisy[key] = max(0.0, min(1.0, val + noise))
    return noisy


# ══════════════════════════════════════════════
# Prompt Injection（v8 五档描述 × 全量 8 信号注入）
# ══════════════════════════════════════════════

SIGNAL_DESCRIPTIONS = {
    'directness': [
        (0.0, 0.2, '说话绕弯子，用暗示和隐喻，从不直说想法'),
        (0.2, 0.4, '说话比较委婉，倾向于用"可能""也许"这种词'),
        (0.4, 0.6, '说话正常，不特别直也不特别绕'),
        (0.6, 0.8, '说话直接，想到什么说什么，不太修饰'),
        (0.8, 1.0, '说话非常直接甚至冲，不在乎对方能不能接受'),
    ],
    'vulnerability': [
        (0.0, 0.2, '完全封闭自己，绝不暴露任何真实感受，用冷漠或玩笑挡住一切'),
        (0.2, 0.4, '很少表达真实感受，被追问也只是轻描淡写'),
        (0.4, 0.6, '偶尔会流露一点真心话，但不会太深入'),
        (0.6, 0.8, '愿意说出自己的感受和脆弱的一面'),
        (0.8, 1.0, '非常坦诚地暴露内心，包括恐惧、不安、依赖感'),
    ],
    'playfulness': [
        (0.0, 0.2, '非常严肃，不开玩笑，语气平淡甚至有点冷'),
        (0.2, 0.4, '偶尔带一点幽默但整体偏正经'),
        (0.4, 0.6, '正常聊天，有时轻松有时认真'),
        (0.6, 0.8, '喜欢开玩笑、逗人，语气轻快活泼'),
        (0.8, 1.0, '各种撒娇卖萌、搞怪、调皮，对话充满笑点'),
    ],
    'initiative': [
        (0.0, 0.2, '完全被动，只回答问题，从不主动说话或换话题'),
        (0.2, 0.4, '基本跟着对方走，偶尔追问一句'),
        (0.4, 0.6, '有来有回，不特别主动也不特别被动'),
        (0.6, 0.8, '经常主动提问、换话题、推动对话往前走'),
        (0.8, 1.0, '强势主导对话，自己抛话题、追问、引导方向'),
    ],
    'depth': [
        (0.0, 0.2, '只聊表面的事，天气、吃饭、日常琐事'),
        (0.2, 0.4, '聊天偏浅，不怎么深入感受层面'),
        (0.4, 0.6, '有时浅聊有时深聊，看情况'),
        (0.6, 0.8, '倾向于深入话题，探讨感受、价值观、关系'),
        (0.8, 1.0, '每句话都想往深了聊，挖掘本质，不满足于表面回应'),
    ],
    'warmth': [
        (0.0, 0.2, '冷淡疏离，语气冷冰冰的，不关心对方感受，甚至有点刻薄'),
        (0.2, 0.4, '比较冷淡，不太主动表达关心，回应简短'),
        (0.4, 0.6, '不冷不热，正常回应但不特别热情'),
        (0.6, 0.8, '温暖关心，语气柔和，会主动关心对方状态'),
        (0.8, 1.0, '非常热情体贴，嘘寒问暖，充满关怀和包容'),
    ],
    'defiance': [
        (0.0, 0.2, '非常顺从，对方说什么都同意，从不反驳'),
        (0.2, 0.4, '比较随和，即使不同意也不太会说出来'),
        (0.4, 0.6, '有自己的想法但不会太坚持'),
        (0.6, 0.8, '嘴硬，喜欢反驳，不轻易认错或服软'),
        (0.8, 1.0, '非常倔强，死不认错，越被质疑越硬杠，宁折不弯'),
    ],
    'curiosity': [
        (0.0, 0.2, '对对方的事完全不感兴趣，不追问任何细节'),
        (0.2, 0.4, '偶尔问一句但不怎么深入'),
        (0.4, 0.6, '正常程度的好奇，会追问一两句'),
        (0.6, 0.8, '对对方很好奇，喜欢追问细节和原因'),
        (0.8, 1.0, '刨根问底，什么都想知道，追着问不放'),
    ],
}


def signals_to_prompt(signals, agent):
    """全量注入 8 个信号的五档描述（不裁剪 top-3）。
    覆盖: 5^8 = 390,625 种组合。LLM 自行理解描述的组合含义。
    """
    lines = ["【你当前的状态】"]
    for sig_name in SIGNALS:
        val = signals[sig_name]
        for low, high, desc in SIGNAL_DESCRIPTIONS[sig_name]:
            if val < high or high == 1.0:
                lines.append(f"- {desc}")
                break

    dominant = agent.get_dominant_drive()
    lines.append(f"\n【内在需求】你现在最需要的是{DRIVE_LABELS[dominant]}")

    # 内在矛盾提示（来自 Agent 的 personality_fingerprint）
    fp = agent.personality_fingerprint(30)
    if fp.get('contradictions'):
        top_c = fp['contradictions'][0]
        lines.append(f"【矛盾】你一方面想{SIGNAL_LABELS[top_c[0]].split(' ')[1]}，一方面又想{SIGNAL_LABELS[top_c[1]].split(' ')[1]}，这让你纠结")

    return '\n'.join(lines)


# ══════════════════════════════════════════════
# Actor Prompt + 回复解析
# ══════════════════════════════════════════════

ACTOR_PROMPT = """[System Internal State: Subconscious Memory Retrieved]
当前的底层神经化学递质坐标，唤醒了海马体中以下高度相似的潜意识与行为切片：

{few_shot}

{signal_injection}

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
# v10 生命循环
# ══════════════════════════════════════════════

def chat_turn_v10(agent, memory, metabolism, user_input, last_action, turn_id, sim_time, model="qwen3-max"):
    """
    v10 Hybrid 生命循环:
    1. ⏳ 时间代谢（保留, 纯数学）
    2. 👁️ LLM 感知+代谢（替代 Critic + 固定系数）
    3. 🩸 同步到 Agent（保留）
    4. 🧬 结晶门控（保留）
    5. 🧠 神经网络信号计算（保留! v8 核心涌现）
    6. 🌡️ 热力学噪声（保留）
    7. 🔭 引力检索（保留）
    8. 📝 Actor Prompt（简化: 数值+锚点, 不是40条描述）
    9. 🎭 Actor LLM
    10. 🧠 Hebbian 学习（保留! v8 核心进化）
    """

    # ── Step 1: ⏳ 时间代谢 ──
    memory.set_clock(sim_time)
    delta_h = metabolism.time_metabolism(sim_time)

    # ── Step 2: 👁️ LLM 感知+代谢（直接输出 8D context + delta）──
    frust_dict = {d: round(metabolism.frustration[d], 2) for d in DRIVES}
    context, frustration_delta = critic_and_metabolize(user_input, frust_dict, model=model)
    reward = metabolism.apply_llm_delta(frustration_delta)

    # ── Step 3: 🩸 同步到 Agent ──
    metabolism.sync_to_agent(agent)

    # ── Step 4: 🧬 结晶门控 ──
    crystallized = False
    if last_action and reward > 0.3:
        memory.crystallize(
            last_action['signals'],
            last_action['monologue'],
            last_action['reply'],
            last_action['user_input'],
        )
        crystallized = True

    # ── Step 5: 🧠 神经网络信号计算（context 现在直接来自 LLM）──
    base_signals = agent.compute_signals(context)

    # ── Step 6: 🌡️ 热力学噪声 ──
    total_frust = metabolism.total()
    noisy_signals = apply_thermodynamic_noise(base_signals, total_frust)

    # ── Step 7: 🔭 引力检索 ──
    few_shot = memory.build_few_shot_prompt(noisy_signals, top_k=3)

    # ── Step 8: 📝 Actor Prompt（简化版）──
    signal_injection = signals_to_prompt(noisy_signals, agent)
    prompt = ACTOR_PROMPT.format(few_shot=few_shot, signal_injection=signal_injection)

    # ── Step 9: 🎭 Actor ──
    raw = call_llm(prompt, user_input, model=model)
    monologue, reply = extract_reply(raw)

    # ── Step 10: 🧠 Hebbian 学习 ──
    agent.step(context, reward=max(-1.0, min(1.0, reward)))

    # ── 显示 ──
    temp = total_frust * 0.05
    time_label = ""
    if delta_h > 0.01:
        if delta_h >= 24:
            time_label = f' ⏳{delta_h/24:.1f}天'
        else:
            time_label = f' ⏳{delta_h:.1f}h'

    # top-3 信号
    top_3 = sorted(SIGNALS, key=lambda s: abs(noisy_signals[s] - 0.5), reverse=True)[:3]
    sig_str = '  '.join(f'{s}={noisy_signals[s]:.2f}' for s in top_3)

    # context top 变化
    ctx_notable = sorted(CONTEXT_FEATURES, key=lambda f: abs(context.get(f, 0.5) - 0.5), reverse=True)[:3]
    ctx_str = ' '.join(f'{f[:6]}={context.get(f, 0.5):.2f}' for f in ctx_notable)

    print(f'  {C.BOLD}T{turn_id:02d}{C.RESET}{time_label}  T°={temp:.2f}')
    print(f'    {metabolism.status_bar()}')
    print(f'    👁️ {C.DIM}{ctx_str}{C.RESET}  '
          f'Δ={{{",".join(f"{d}:{frustration_delta[d]:+.1f}" for d in DRIVES)}}}  '
          f'reward={reward:+.2f}')
    print(f'    🧠 {C.CYAN}{sig_str}{C.RESET}')
    print(f'    👤 "{user_input}"')
    if monologue:
        print(f'    {C.MAGENTA}💭 {monologue[:85]}{C.RESET}')
    print(f'    {C.WHITE}💬 {reply}{C.RESET}')
    if crystallized:
        print(f'    {C.GREEN}🧬 结晶！(reward={reward:.2f}){C.RESET}')
    print()

    return {
        'signals': noisy_signals,
        'monologue': monologue,
        'reply': reply,
        'user_input': user_input,
        'reward': reward,
        'critic': context,
        'frustration': {d: round(metabolism.frustration[d], 2) for d in DRIVES},
        'frustration_delta': frustration_delta,
    }


# ══════════════════════════════════════════════
# 独立运行测试
# ══════════════════════════════════════════════

TEST_DIALOGUE = [
    (2,      "你根本不在乎我"),
    (3,      "你凭什么这么冷漠"),
    (5,      "算了 我受够了"),
    (10,     "好吧 对不起"),
    (5,      "嗯嗯 你说得对"),
    (10,     "今天有个老同学突然找我了"),
    (15,     "晚安"),
    (259200, "在吗"),           # 3天后
    (5,      "我这三天真的好想你"),
    (10,     "想抱抱"),
]


def run_v10(model="qwen3-max", seed=42):
    print(f"""
{C.BOLD}══════════════════════════════════════════════════════════════
  TPE v10 — Hybrid Engine
  ✅ 神经网络涌现  ✅ Hebbian进化  ✅ 相变
  ✅ 时间方程  ✅ 引力记忆
  🔄 LLM代谢（替代固定系数）  🔄 数值+锚点（替代40条描述）
=============================================================={C.RESET}
""")

    model_short = model.split("-")[0] if "-" in model else model
    api_key = API_KEYS.get(MODEL_CONFIGS.get(model, {}).get("key_env", ""), DASHSCOPE_KEY)
    if not api_key:
        print(f'{C.RED}❌ 未找到 {MODEL_CONFIGS.get(model, {}).get("key_env", "API_KEY")}{C.RESET}')
        return

    db_dir = os.path.join(os.path.dirname(__file__), "memory_db")
    base_time = time.time()
    sim_time = base_time

    # 初始化 Agent
    agent = Agent(seed=seed)
    simulate_conversation(agent, ['分享喜悦', '吵架冲突', '深夜心事'], steps_per_scenario=20)

    mem_id = f"v10_seed{seed}_{int(base_time)}"
    memory = ContinuousStyleMemory(mem_id, db_dir, now=sim_time)
    metabolism = HybridMetabolism(clock=sim_time)

    print(f'  🤖 模型: {model}  🧬 seed={seed}')
    print(f'  Agent seed={seed} 培养完成  pool={memory.stats()["total"]}')
    print(f'  初始温度: T°=0.00  {metabolism.status_bar()}')
    print()

    last_action = None
    results = []
    for i, (delay_sec, msg) in enumerate(TEST_DIALOGUE):
        sim_time += delay_sec

        if delay_sec >= 3600:
            hours = delay_sec / 3600.0
            print(f'{C.BOLD}{"─" * 50}{C.RESET}')
            if hours >= 24:
                print(f'{C.BOLD}  ⏳ {hours/24:.0f}天断联跳跃{C.RESET}')
            else:
                print(f'{C.BOLD}  ⏳ {hours:.0f}小时跳跃{C.RESET}')
            print(f'{C.BOLD}{"─" * 50}{C.RESET}')

        last_action = chat_turn_v10(agent, memory, metabolism, msg, last_action, i, sim_time, model=model)
        results.append(last_action)
        time.sleep(0.3)

    # 最终报告
    s = memory.stats()
    print(f'\n{C.BOLD}══ 最终统计 ══{C.RESET}')
    print(f'  记忆池={s["total"]}  个人记忆={s["personal_count"]}')
    print(f'  最终驱力: {metabolism.status_bar()}')
    print(f'  最终温度: T°={metabolism.total() * 0.05:.2f}')

    return results


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='qwen3-max',
                        choices=list(MODEL_CONFIGS.keys()),
                        help='LLM model to use')
    parser.add_argument('--seed', type=int, default=42, help='Agent seed')
    args = parser.parse_args()
    run_v10(model=args.model, seed=args.seed)
