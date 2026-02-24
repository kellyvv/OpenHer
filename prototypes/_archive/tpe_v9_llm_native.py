#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  🧬 TPE v9 — LLM-Native Persona Engine 🧬                         ║
║                                                                      ║
║  v8 (Genome) → v9 (LLM-Native) 变更：                              ║
║    ❌ 删除: 728参数神经网络                                          ║
║    ❌ 删除: 40条五档硬编码行为描述                                    ║
║    ❌ 删除: 固定代谢系数 (2.0/1.5/3.0...)                           ║
║    ✅ 保留: 时间代谢方程 (e^-λΔt + 线性饥饿)                       ║
║    ✅ 保留: 引力记忆 + 霍金辐射 (KNN数学操作)                      ║
║    🔄 新增: LLM 原生感知+代谢+行为指令生成 (一次调用)              ║
║                                                                      ║
║  核心思路：让 LLM 自己判断情绪变化和行为倾向，                     ║
║  而不是通过手编系数和神经网络间接计算。                              ║
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
from style_memory import ContinuousStyleMemory, SIGNAL_KEYS

# ── API 配置 ──
DASHSCOPE_KEY = ""
for env_path in [
    os.path.join(os.path.dirname(__file__), "..", "server", ".env"),
    os.path.join(os.path.dirname(__file__), "..", ".env"),
]:
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("DASHSCOPE_API_KEY="):
                    DASHSCOPE_KEY = line.strip().split("=", 1)[1]
        if DASHSCOPE_KEY:
            break


# ── 终端颜色 ──
class C:
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    DIM = '\033[2m'
    RESET = '\033[0m'


# ══════════════════════════════════════════════
# 驱力常量（与 v8 一致）
# ══════════════════════════════════════════════

DRIVES = ['connection', 'novelty', 'expression', 'safety', 'play']
DRIVE_LABELS = {
    'connection': '🤝联结', 'novelty': '✨新鲜', 'expression': '🗣️表达',
    'safety': '🛡️安全', 'play': '🎮玩闹',
}

# 物理常数（不可替代的数学方程参数）
FRUSTRATION_DECAY_LAMBDA = 0.08
CONNECTION_HUNGER_K = 0.15
NOVELTY_HUNGER_K = 0.05


# ══════════════════════════════════════════════
# LLM 调用（与 v8 相同）
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
        "max_tokens": 600,
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
# 时间代谢（保留，纯数学，LLM 做不了）
# ══════════════════════════════════════════════

class TimeMetabolism:
    """时间代谢：只负责时间方程，不负责刺激响应。"""

    def __init__(self, clock=None):
        self.frustration = {d: 0.0 for d in DRIVES}
        self._last_tick = clock or time.time()

    def time_metabolism(self, now):
        """纯物理时间方程：消气 + 饥饿。"""
        delta_hours = max(0.0, (now - self._last_tick) / 3600.0)
        self._last_tick = now

        if delta_hours < 0.001:
            return delta_hours

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

    def apply_delta(self, delta_dict):
        """应用 LLM 输出的 frustration 变化量。"""
        old_total = self.total()
        for d in DRIVES:
            if d in delta_dict:
                self.frustration[d] += delta_dict[d]
                self.frustration[d] = max(0.0, min(5.0, self.frustration[d]))
        return old_total - self.total()  # 正值 = frustration 减少 = good

    def total(self):
        return sum(self.frustration.values())

    def status_dict(self):
        return {d: round(self.frustration[d], 2) for d in DRIVES}

    def status_bar(self):
        parts = []
        for d in DRIVES:
            v = self.frustration[d]
            icon = DRIVE_LABELS.get(d, '?')
            if v > 2.0:   parts.append(f'{C.RED}{icon}{v:.1f}{C.RESET}')
            elif v > 0.5: parts.append(f'{C.YELLOW}{icon}{v:.1f}{C.RESET}')
            else:          parts.append(f'{C.GREEN}{icon}{v:.1f}{C.RESET}')
        return ' '.join(parts)


# ══════════════════════════════════════════════
# LLM-Native 感知 + 代谢 + 行为指令（替代 Critic + 固定系数 + 神经网络 + 40条描述）
# ══════════════════════════════════════════════

PERCEIVE_PROMPT = """你是一个角色扮演 Agent 的内在心理引擎。你的任务是分析用户的输入对 Agent 的情绪影响，并决定 Agent 应该怎样行动。

Agent 当前的内在驱力挫败值（0=满足，5=极度渴望）：
{frustration_json}

用户说了："{user_input}"

请完成以下任务，严格输出纯 JSON（无 Markdown，无解释）：

1. "frustration_delta": 分析这句话对 Agent 5 个驱力的影响，输出每个驱力的变化量（正=增加挫败，负=缓解）。
   - connection: 这个人是在拉近还是推远关系？
   - novelty: 这个人说的有新信息还是废话？
   - expression: 这个人在压制还是给空间让 Agent 表达？
   - safety: 这个人在攻击/施压还是在安抚？
   - play: 这个人的话有趣还是无聊？

2. "mood_vector": 根据 Agent 当前状态和这句话的刺激，输出 Agent 此刻 8 个行为倾向值（0.0~1.0）：
   - directness: 0=委婉暗示 → 1=直说
   - vulnerability: 0=防御封闭 → 1=袒露脆弱
   - playfulness: 0=严肃 → 1=撒娇玩闹
   - initiative: 0=被动 → 1=主动引导
   - depth: 0=表面 → 1=深度
   - warmth: 0=冷淡 → 1=热情
   - defiance: 0=顺从 → 1=反抗嘴硬
   - curiosity: 0=无所谓 → 1=追问到底

3. "behavioral_tendency": 用 1-2 句自然语言描述 Agent 此刻应该怎么回应。描述具体的语气、态度、情绪，不要笼统。

输出格式示例：
{
  "frustration_delta": {"connection": -0.5, "novelty": 0.1, "expression": 0.0, "safety": 0.3, "play": 0.0},
  "mood_vector": {"directness": 0.8, "vulnerability": 0.2, "playfulness": 0.1, "initiative": 0.3, "depth": 0.5, "warmth": 0.3, "defiance": 0.7, "curiosity": 0.2},
  "behavioral_tendency": "心里受伤了但嘴上不承认，语气变得冷硬，想反驳但又怕真的激怒对方"
}"""


def perceive_and_metabolize(user_input, frustration_dict, model="qwen3-max"):
    """
    LLM 原生感知 + 代谢：一次调用替代 Critic + 固定代数规则 + 神经网络 + 40条描述。

    Returns:
        frustration_delta: dict, 各驱力变化量
        mood_vector: dict, 8D 行为倾向
        behavioral_tendency: str, 自然语言行为指令
    """
    prompt = PERCEIVE_PROMPT.replace(
        "{frustration_json}", json.dumps(frustration_dict, ensure_ascii=False, indent=2)
    ).replace(
        "{user_input}", user_input
    )

    raw = call_llm(prompt, user_input, model=model, temperature=0.3)

    try:
        cleaned = re.sub(r'```json\s*', '', raw)
        cleaned = re.sub(r'```\s*', '', cleaned)
        data = json.loads(cleaned)

        frustration_delta = {}
        raw_delta = data.get('frustration_delta', {})
        for d in DRIVES:
            v = float(raw_delta.get(d, 0.0))
            frustration_delta[d] = max(-3.0, min(3.0, v))

        mood_vector = {}
        raw_mood = data.get('mood_vector', {})
        for k in SIGNAL_KEYS:
            v = float(raw_mood.get(k, 0.5))
            mood_vector[k] = max(0.0, min(1.0, v))

        behavioral_tendency = data.get('behavioral_tendency', '正常回应')

        return frustration_delta, mood_vector, behavioral_tendency

    except (json.JSONDecodeError, ValueError, TypeError, KeyError) as e:
        print(f"    {C.RED}⚠️ perceive parse error: {e}{C.RESET}")
        return (
            {d: 0.0 for d in DRIVES},
            {k: 0.5 for k in SIGNAL_KEYS},
            "正常回应",
        )


# ══════════════════════════════════════════════
# 热力学噪声（保留，用 frustration 驱动）
# ══════════════════════════════════════════════

def apply_thermodynamic_noise(mood_vector, total_frustration):
    temperature = total_frustration * 0.05
    noisy = {}
    for key, val in mood_vector.items():
        noise = random.gauss(0.0, temperature)
        noisy[key] = max(0.0, min(1.0, val + noise))
    return noisy


# ══════════════════════════════════════════════
# Actor Prompt（v9 简化版 — 不需要信号翻译，直接用 LLM 生成的行为描述）
# ══════════════════════════════════════════════

ACTOR_PROMPT_V9 = """[System Internal State: Subconscious Memory Retrieved]
当前的底层神经化学递质坐标，唤醒了海马体中以下高度相似的潜意识与行为切片：

{few_shot}

[当前行为倾向]
{behavioral_tendency}

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
# v9 生命循环
# ══════════════════════════════════════════════

def chat_turn_v9(memory, metabolism, user_input, last_action, turn_id, sim_time):
    """
    v9 LLM-Native 生命循环（6 步）:
    1. ⏳ 时间代谢（保留）
    2. 🧠 LLM 感知+代谢+行为指令（替代 Critic + 固定系数 + 神经网络 + 40条描述）
    3. 🧬 结晶门控（保留）
    4. 🔭 引力检索（保留）
    5. 🎭 Actor LLM
    6. 📝 记录
    """

    # ── Step 1: ⏳ 时间代谢 ──
    memory.set_clock(sim_time)
    delta_h = metabolism.time_metabolism(sim_time)

    # ── Step 2: 🧠 LLM 感知+代谢+行为指令 ──
    frustration_delta, mood_vector, behavioral_tendency = perceive_and_metabolize(
        user_input, metabolism.status_dict()
    )
    reward = metabolism.apply_delta(frustration_delta)

    # ── Step 3: 🧬 结晶门控 ──
    crystallized = False
    if last_action and reward > 0.3:
        n = memory.crystallize(
            last_action['mood_vector'],
            last_action['monologue'],
            last_action['reply'],
            last_action['user_input'],
        )
        crystallized = True

    # ── Step 3.5: 热噪声 ──
    total_frust = metabolism.total()
    noisy_mood = apply_thermodynamic_noise(mood_vector, total_frust)

    # ── Step 4: 🔭 引力检索 ──
    few_shot = memory.build_few_shot_prompt(noisy_mood, top_k=3)

    # ── Step 5: 🎭 Actor ──
    prompt = ACTOR_PROMPT_V9.format(
        few_shot=few_shot,
        behavioral_tendency=behavioral_tendency,
    )
    raw = call_llm(prompt, user_input, model="qwen3-max")
    monologue, reply = extract_reply(raw)

    # ── 显示 ──
    temp = total_frust * 0.05
    time_label = ""
    if delta_h > 0.01:
        if delta_h >= 24:
            time_label = f' ⏳{delta_h/24:.1f}天'
        else:
            time_label = f' ⏳{delta_h:.1f}h'

    print(f'  {C.BOLD}T{turn_id:02d}{C.RESET}{time_label}  T°={temp:.2f}')
    print(f'    {metabolism.status_bar()}')
    print(f'    🧠 Δ={{{",".join(f"{d}:{frustration_delta[d]:+.1f}" for d in DRIVES)}}}  '
          f'reward={reward:+.2f}')
    print(f'    📋 {C.CYAN}{behavioral_tendency}{C.RESET}')
    print(f'    👤 "{user_input}"')
    if monologue:
        print(f'    {C.MAGENTA}💭 {monologue[:85]}{C.RESET}')
    print(f'    {C.WHITE}💬 {reply}{C.RESET}')
    if crystallized:
        print(f'    {C.GREEN}🧬 结晶！(reward={reward:.2f}){C.RESET}')
    print()

    return {
        'mood_vector': noisy_mood,
        'monologue': monologue,
        'reply': reply,
        'user_input': user_input,
        'behavioral_tendency': behavioral_tendency,
        'reward': reward,
        'frustration': metabolism.status_dict(),
        'frustration_delta': frustration_delta,
    }


# ══════════════════════════════════════════════
# 独立运行测试
# ══════════════════════════════════════════════

def run_v9_standalone():
    print(f"""
{C.BOLD}══════════════════════════════════════════════════════════════
  TPE v9 — LLM-Native Persona Engine (独立测试)
  ❌ 无神经网络  ❌ 无硬编码描述  ❌ 无固定代谢系数
  ✅ 时间方程  ✅ 引力记忆  ✅ LLM 原生理解
=============================================================={C.RESET}
""")

    if not DASHSCOPE_KEY:
        print(f'{C.RED}❌ 未找到 DASHSCOPE_API_KEY{C.RESET}')
        return

    db_dir = os.path.join(os.path.dirname(__file__), "memory_db")
    base_time = time.time()
    sim_time = base_time

    memory = ContinuousStyleMemory("v9_test", db_dir, now=sim_time)
    metabolism = TimeMetabolism(clock=sim_time)

    print(f'  初始: pool={memory.stats()["total"]}  T°=0.00')
    print()

    # 测试对话（10轮，覆盖多种场景）
    dialogue = [
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

    last_action = None
    for i, (delay_sec, msg) in enumerate(dialogue):
        sim_time += delay_sec
        if delay_sec >= 3600:
            hours = delay_sec / 3600.0
            print(f'{C.BOLD}{"─" * 50}{C.RESET}')
            if hours >= 24:
                print(f'{C.BOLD}  ⏳ {hours/24:.0f}天断联跳跃{C.RESET}')
            else:
                print(f'{C.BOLD}  ⏳ {hours:.0f}小时跳跃{C.RESET}')
            print(f'{C.BOLD}{"─" * 50}{C.RESET}')

        last_action = chat_turn_v9(memory, metabolism, msg, last_action, i, sim_time)
        time.sleep(0.3)

    # 最终报告
    s = memory.stats()
    print(f'\n{C.BOLD}══ 最终统计 ══{C.RESET}')
    print(f'  记忆池={s["total"]}  个人记忆={s["personal_count"]}')
    print(f'  最终驱力: {metabolism.status_bar()}')
    print(f'  最终温度: T°={metabolism.total() * 0.05:.2f}')

    return metabolism, memory


if __name__ == '__main__':
    run_v9_standalone()
