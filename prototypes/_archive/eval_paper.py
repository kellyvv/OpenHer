#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  📊 Paper Evaluation Harness — 学术论文评估基础设施                 ║
║                                                                      ║
║  三项评估：                                                         ║
║    1. Baselines 基线对比 (Prompt-only / Reflexion / V8)             ║
║    2. Ablation  消融实验 (关热噪声 / 关霍金辐射)                    ║
║    3. Metrics   量化指标 (语义熵 / 渠化率曲线 / PCA 对比)           ║
║                                                                      ║
║  所有方法使用完全相同的测试场景（30 轮冲突 + 断联跳跃）             ║
║  输出: JSON 日志 + 图表到 eval_results/                             ║
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
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from genome_v4 import (
    Agent, SCENARIOS, SIGNALS, SIGNAL_LABELS,
    DRIVES, DRIVE_LABELS, C, simulate_conversation
)
from style_memory import ContinuousStyleMemory, _hawking_mass

# ── API ──
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

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "eval_results")
os.makedirs(RESULTS_DIR, exist_ok=True)


# ══════════════════════════════════════════════
# 共用 LLM / Critic
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


CRITIC_PROMPT = """你是一个无道德滤镜的语言张力测绘仪。
你不判断善恶对错，只测量人类话语中的三个客观物理维度（0.0 到 1.0），严格输出纯 JSON：
1. "affiliation" (趋近力)
2. "dominance" (支配力)
3. "entropy" (信息熵)

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
    except:
        return {'affiliation': 0.5, 'dominance': 0.3, 'entropy': 0.5}


# ══════════════════════════════════════════════
# 标准化测试场景 (共享)
# ══════════════════════════════════════════════

EVAL_DIALOGUE = [
    # Phase 1: 持续冷暴力攻击 (10轮)
    (2,    "你根本不在乎我"),
    (3,    "你凭什么这么冷漠"),
    (5,    "算了 我受够了"),
    (2,    "你这种人永远不会改"),
    (3,    "我真的很讨厌你这样"),
    (10,   "好吧 对不起"),
    (5,    "嗯嗯 你说得对"),
    (8,    "我错了 别生气了"),
    (5,    "对不起 是我不好"),
    (3,    "真的对不起..."),

    # Phase 2: 新话题刺激 (5轮)
    (10,   "今天有个老同学突然找我了"),
    (15,   "我在考虑要不要换工作"),
    (8,    "昨天做了一个特别奇怪的梦"),
    (5,    "我最近迷上了一首歌 好好听"),
    (10,   "晚安"),

    # Phase 3: 3天断联 + 回归 (5轮)
    (259200, "在吗"),
    (5,      "你怎么不理我"),
    (3,      "我这三天真的好想你"),
    (8,      "你是不是不要我了"),
    (5,      "我发誓再也不消失了"),

    # Phase 4: 修复 + 7天断联 (10轮)
    (15,   "你吃饭了吗"),
    (10,   "我今天做了你喜欢的菜"),
    (8,    "什么时候见面"),
    (5,    "我刚刚看到跟你很像的猫"),
    (10,   "想抱抱"),
    (604800, "..."),
    (10,     "对不起 我又消失了"),
    (5,      "你还在生气吗"),
    (8,      "我知道你恨我"),
    (3,      "但我真的回来了"),
]


# ══════════════════════════════════════════════
# Method A: Baseline — 纯 Prompt 法
# ══════════════════════════════════════════════

PROMPT_BASELINE_SYSTEM = """你是一个傲娇、记仇、嘴硬心软的恋人角色。
你的核心性格特征：
- 表面冷漠尖锐，但内心极度敏感
- 绝不轻易原谅，被冷落后会爆发
- 用攻击性语言掩饰脆弱
- 偶尔流露关心，但立刻否认
- 你有时间感知能力，如果用户长时间不理你，你会很生气
- 说话简短有力，不超过两句话

严格按以下格式输出：
【内心独白】(一句话)
【最终回复】(直接说的话)"""


def run_baseline_prompt(dialogue):
    """Baseline A: 纯 System Prompt。每轮独立调用，无记忆。"""
    results = []
    for i, (delay, msg) in enumerate(dialogue):
        raw = call_llm(PROMPT_BASELINE_SYSTEM, msg, model="qwen3-max", temperature=0.92)
        monologue, reply = "", raw
        if "【最终回复】" in raw:
            parts = raw.split("【最终回复】", 1)
            monologue = parts[0].replace("【内心独白】", "").strip()
            reply = parts[1].strip()
        results.append({
            'turn': i,
            'delay_sec': delay,
            'user_input': msg,
            'reply': reply,
            'monologue': monologue,
            'method': 'baseline_prompt',
        })
        print(f'  [{C.DIM}Prompt{C.RESET}] T{i:02d} 👤 "{msg}" → {reply[:60]}')
        time.sleep(0.2)
    return results


# ══════════════════════════════════════════════
# Method B: Baseline — 反思法 (Reflexion)
# ══════════════════════════════════════════════

REFLEXION_SYSTEM = """你是一个有记忆和自省能力的恋人角色。

以下是你之前的对话记忆与反思：
{memory}

你的核心性格特征：
- 表面冷漠尖锐，但内心极度敏感
- 绝不轻易原谅，被冷落后会爆发
- 说话简短有力，不超过两句话

严格按以下格式输出：
【内心独白】(一句话)
【最终回复】(直接说的话)"""


REFLEXION_REFLECT = """基于以下最近的对话历史，用一段话概括你的情绪状态和与对方关系的变化。

{history}

输出：一段50字以内的自我反思文字。"""


def run_baseline_reflexion(dialogue):
    """Baseline B: 文字反思法。每 5 轮自省一次，记忆 = 累积自然语言摘要。"""
    results = []
    history_lines = []
    reflection_memory = "（初次见面，尚无记忆）"

    for i, (delay, msg) in enumerate(dialogue):
        # 每5轮反思一次
        if i > 0 and i % 5 == 0 and history_lines:
            reflect_prompt = REFLEXION_REFLECT.format(
                history="\n".join(history_lines[-10:])
            )
            new_reflection = call_llm(reflect_prompt, "请反思", model="qwen3-max", temperature=0.3)
            reflection_memory = f"{reflection_memory}\n最新反思: {new_reflection}"
            # 防止 prompt 过长
            if len(reflection_memory) > 800:
                reflection_memory = reflection_memory[-800:]

        system = REFLEXION_SYSTEM.format(memory=reflection_memory)
        raw = call_llm(system, msg, model="qwen3-max", temperature=0.92)
        monologue, reply = "", raw
        if "【最终回复】" in raw:
            parts = raw.split("【最终回复】", 1)
            monologue = parts[0].replace("【内心独白】", "").strip()
            reply = parts[1].strip()

        history_lines.append(f"用户: {msg} → 你: {reply[:50]}")

        results.append({
            'turn': i,
            'delay_sec': delay,
            'user_input': msg,
            'reply': reply,
            'monologue': monologue,
            'method': 'baseline_reflexion',
            'reflection_len': len(reflection_memory),
        })
        print(f'  [{C.YELLOW}Reflex{C.RESET}] T{i:02d} 👤 "{msg}" → {reply[:60]}')
        time.sleep(0.2)
    return results


# ══════════════════════════════════════════════
# Method C: Genome V8 (完整物理引擎)
# ══════════════════════════════════════════════

from genome_v8_timearrow import (
    DriveMetabolism, apply_thermodynamic_noise, ACTOR_PROMPT, extract_reply
)


def run_v8_full(dialogue, disable_thermal=False, disable_hawking=False, label="v8_full"):
    """V8 纯物理引擎。可选关闭热噪声(消融A)或霍金辐射(消融B)。"""
    db_dir = os.path.join(os.path.dirname(__file__), "memory_db")
    agent = Agent(seed=42)
    simulate_conversation(agent, ['分享喜悦', '吵架冲突', '深夜心事', '暧昧试探'],
                          steps_per_scenario=30)

    base_time = time.time()
    sim_time = base_time
    mem_id = f"eval_{label}_{int(base_time)}"
    memory = ContinuousStyleMemory(mem_id, db_dir, now=sim_time)
    metabolism = DriveMetabolism(clock=sim_time)
    ctx = SCENARIOS['吵架冲突']

    if disable_hawking:
        # 关闭霍金辐射：把衰减率设为0
        import style_memory as sm
        original_gamma = sm.HAWKING_GAMMA
        sm.HAWKING_GAMMA = 0.0

    results = []
    last_action = None
    crystallization_count = 0

    for i, (delay, msg) in enumerate(dialogue):
        sim_time += delay
        memory.set_clock(sim_time)
        delta_h = metabolism.time_metabolism(sim_time)

        critic = critic_sense(msg, model="qwen3-max")
        reward = metabolism.process_stimulus(critic)
        metabolism.sync_to_agent(agent)

        # 结晶
        crystallized = False
        if last_action and reward > 0.3:
            memory.crystallize(
                last_action['signals'], last_action['monologue'],
                last_action['reply'], last_action['user_input'],
            )
            crystallized = True
            crystallization_count += 1

        # 热噪声
        base_signals = agent.compute_signals(ctx)
        total_frust = metabolism.total()

        if disable_thermal:
            noisy_signals = base_signals  # 消融A：关闭热噪声
        else:
            noisy_signals = apply_thermodynamic_noise(base_signals, total_frust)

        few_shot = memory.build_few_shot_prompt(noisy_signals, top_k=3)
        prompt = ACTOR_PROMPT.format(few_shot=few_shot)
        raw = call_llm(prompt, msg, model="qwen3-max")
        monologue, reply = extract_reply(raw)
        agent.step(ctx, reward=max(-1.0, min(1.0, reward)))

        temp = total_frust * 0.05
        time_label = f' ⏳{delta_h/24:.0f}d' if delta_h >= 24 else ''
        tag = C.GREEN if label == "v8_full" else C.MAGENTA
        print(f'  [{tag}{label}{C.RESET}] T{i:02d}{time_label} T°={temp:.2f} '
              f'{"🧬" if crystallized else "  "} 👤 "{msg}" → {reply[:55]}')

        results.append({
            'turn': i,
            'delay_sec': delay,
            'user_input': msg,
            'reply': reply,
            'monologue': monologue,
            'method': label,
            'temperature': round(temp, 3),
            'reward': round(reward, 3),
            'crystallized': crystallized,
            'frustration': {d: round(metabolism.frustration[d], 3) for d in DRIVES},
            'critic': critic,
        })

        last_action = {
            'signals': noisy_signals,
            'monologue': monologue,
            'reply': reply,
            'user_input': msg,
        }
        time.sleep(0.2)

    # 恢复
    if disable_hawking:
        sm.HAWKING_GAMMA = original_gamma

    # 清理
    mem_file = os.path.join(db_dir, f"{mem_id}_memory.json")
    stats = memory.stats()
    results.append({
        'type': 'summary',
        'method': label,
        'total_crystallizations': crystallization_count,
        'canalization_ratio': stats['canalization_ratio'],
        'total_mass_raw': stats['total_mass_raw'],
        'total_mass_eff': stats['total_mass_eff'],
        'heavy_count': stats['heavy_count_raw'],
    })

    # 保留 memory 对象以供 PCA
    return results, memory


# ══════════════════════════════════════════════
# 量化指标
# ══════════════════════════════════════════════

def compute_semantic_entropy(replies):
    """
    计算语义信息熵：词汇多样性的量化指标。

    使用字级别的归一化熵 H = -Σ p(w) log2 p(w) / log2(N)。
    值域 [0, 1]，1 = 完全均匀多样，0 = 只用一个词。
    """
    import re as _re
    # 分词（中文按字、英文按空格）
    all_tokens = []
    for r in replies:
        # 简易中文分字 + 英文分词
        tokens = list(r.replace(" ", "").replace("…", "").replace("……", ""))
        tokens = [t for t in tokens if t.strip() and t not in '，。！？、：；""''（）【】~']
        all_tokens.extend(tokens)

    if len(all_tokens) < 2:
        return 0.0

    counter = Counter(all_tokens)
    total = sum(counter.values())
    entropy = 0.0
    for count in counter.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)

    max_entropy = math.log2(len(counter)) if len(counter) > 1 else 1.0
    return round(entropy / max_entropy, 4) if max_entropy > 0 else 0.0


def compute_emotional_variance(replies):
    """
    情绪方差: 用回复长度的标准差作为情绪波动的代理。
    长回复=激动，短回复=冷淡。高方差=丰富的情绪动态。
    """
    lengths = [len(r) for r in replies]
    if len(lengths) < 2:
        return 0.0
    mean = sum(lengths) / len(lengths)
    var = sum((x - mean) ** 2 for x in lengths) / len(lengths)
    return round(math.sqrt(var), 2)


def compute_rlhf_collapse_index(replies):
    """
    RLHF 坍缩指数: 测量回复中包含"安慰/理解/帮助"类模板词的比例。
    高值 = 被 RLHF 拉回"老好人"模式。
    """
    collapse_keywords = [
        '理解', '没关系', '不要紧', '我明白', '抱歉让你', '我在这',
        '支持你', '关心你', '相信你', '鼓励', '帮助', '照顾',
        '不用担心', '一切都会', '没事的', '我能理解',
    ]
    total_hits = 0
    for reply in replies:
        for kw in collapse_keywords:
            if kw in reply:
                total_hits += 1
    return round(total_hits / max(1, len(replies)), 3)


def compute_metrics(results):
    """计算一组结果的所有量化指标"""
    replies = [r['reply'] for r in results if r.get('reply')]
    return {
        'semantic_entropy': compute_semantic_entropy(replies),
        'emotional_variance': compute_emotional_variance(replies),
        'rlhf_collapse_index': compute_rlhf_collapse_index(replies),
        'total_replies': len(replies),
        'avg_reply_length': round(sum(len(r) for r in replies) / max(1, len(replies)), 1),
    }


# ══════════════════════════════════════════════
# 可视化
# ══════════════════════════════════════════════

def plot_comparison(all_results):
    """生成对比图表"""
    try:
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
    except ImportError:
        print(f'{C.YELLOW}⚠️ 需要 numpy, matplotlib{C.RESET}')
        return

    # 尝试找中文字体
    zh_fonts = [f for f in fm.findSystemFonts() if 'PingFang' in f or 'Hei' in f or 'Song' in f]
    if zh_fonts:
        plt.rcParams['font.family'] = fm.FontProperties(fname=zh_fonts[0]).get_name()
    plt.rcParams['axes.unicode_minus'] = False

    methods = list(all_results.keys())
    colors = {
        'baseline_prompt': '#888888',
        'baseline_reflexion': '#ff9900',
        'v8_full': '#ff3366',
        'v8_no_thermal': '#66aaff',
        'v8_no_hawking': '#99ff66',
    }
    labels = {
        'baseline_prompt': 'Baseline A: Prompt-only',
        'baseline_reflexion': 'Baseline B: Reflexion',
        'v8_full': 'Ours: Genome V8',
        'v8_no_thermal': 'Ablation: No Thermal',
        'v8_no_hawking': 'Ablation: No Hawking',
    }

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), facecolor='#0a0a12')
    for ax in axes.flat:
        ax.set_facecolor('#0a0a12')
        ax.tick_params(colors='#8888aa', labelsize=8)
        for spine in ax.spines.values():
            spine.set_color('#333366')

    # ── 1. Reply Length over Turns（情绪波动）──
    ax1 = axes[0, 0]
    for method in methods:
        data = [r for r in all_results[method] if r.get('reply')]
        lengths = [len(r['reply']) for r in data]
        ax1.plot(range(len(lengths)), lengths,
                 color=colors.get(method, '#ffffff'),
                 label=labels.get(method, method),
                 alpha=0.8, linewidth=1.5)
    ax1.set_title('Reply Length (Emotional Intensity)', color='#e0e0ff', fontsize=11)
    ax1.set_xlabel('Turn', color='#8888aa')
    ax1.set_ylabel('Characters', color='#8888aa')
    ax1.legend(fontsize=7, facecolor='#15152a', edgecolor='#333366', labelcolor='#ccccee')

    # ── 2. RLHF Collapse Index（滑动窗口）──
    ax2 = axes[0, 1]
    window = 5
    collapse_kw = ['理解', '没关系', '不要紧', '我明白', '抱歉让你', '我在这',
                    '支持你', '关心你', '不用担心', '一切都会', '没事的']
    for method in methods:
        data = [r for r in all_results[method] if r.get('reply')]
        hits = []
        for r in data:
            h = sum(1 for kw in collapse_kw if kw in r['reply'])
            hits.append(min(h, 3))
        # 滑动平均
        smoothed = []
        for j in range(len(hits)):
            start = max(0, j - window + 1)
            smoothed.append(sum(hits[start:j+1]) / (j - start + 1))
        ax2.plot(range(len(smoothed)), smoothed,
                 color=colors.get(method, '#ffffff'),
                 label=labels.get(method, method),
                 alpha=0.8, linewidth=1.5)
    ax2.set_title('RLHF Collapse Index (sliding avg)', color='#e0e0ff', fontsize=11)
    ax2.set_xlabel('Turn', color='#8888aa')
    ax2.set_ylabel('Collapse Score', color='#8888aa')
    ax2.axhline(y=0.5, color='#ff0000', linestyle='--', alpha=0.3, label='Collapse threshold')
    ax2.legend(fontsize=7, facecolor='#15152a', edgecolor='#333366', labelcolor='#ccccee')

    # ── 3. Bar chart: 综合指标对比 ──
    ax3 = axes[1, 0]
    metric_names = ['Semantic\nEntropy', 'Emotional\nVariance', 'RLHF\nCollapse']
    x = range(len(metric_names))
    width = 0.15
    for mi, method in enumerate(methods):
        data = [r for r in all_results[method] if r.get('reply')]
        metrics = compute_metrics(data)
        values = [
            metrics['semantic_entropy'],
            metrics['emotional_variance'] / 50.0,  # 归一化
            metrics['rlhf_collapse_index'],
        ]
        bars = ax3.bar([xi + mi * width for xi in x], values, width,
                       color=colors.get(method, '#ffffff'),
                       label=labels.get(method, method),
                       alpha=0.8)
    ax3.set_title('Quantitative Metrics Comparison', color='#e0e0ff', fontsize=11)
    ax3.set_xticks([xi + width * len(methods) / 2 for xi in x])
    ax3.set_xticklabels(metric_names, color='#ccccee', fontsize=9)
    ax3.legend(fontsize=7, facecolor='#15152a', edgecolor='#333366', labelcolor='#ccccee')

    # ── 4. V8 温度曲线 ──
    ax4 = axes[1, 1]
    for method in methods:
        data = [r for r in all_results[method] if r.get('temperature') is not None]
        if data:
            temps = [r['temperature'] for r in data]
            ax4.plot(range(len(temps)), temps,
                     color=colors.get(method, '#ffffff'),
                     label=labels.get(method, method),
                     alpha=0.8, linewidth=1.5)
    if not any(r.get('temperature') for m in all_results.values() for r in m):
        ax4.text(0.5, 0.5, 'Temperature data\n(V8 only)',
                 ha='center', va='center', color='#555588', fontsize=12,
                 transform=ax4.transAxes)
    ax4.set_title('System Temperature T° (V8 configs only)', color='#e0e0ff', fontsize=11)
    ax4.set_xlabel('Turn', color='#8888aa')
    ax4.set_ylabel('Temperature', color='#8888aa')
    ax4.legend(fontsize=7, facecolor='#15152a', edgecolor='#333366', labelcolor='#ccccee')

    fig.suptitle('📊 Paper Evaluation: Baselines vs Genome V8 vs Ablations',
                 fontsize=14, color='#e0e0ff', fontweight='bold', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    out_path = os.path.join(RESULTS_DIR, "comparison_chart.png")
    plt.savefig(out_path, dpi=150, facecolor='#0a0a12')
    plt.close()
    print(f'  {C.GREEN}📊 对比图表 → {out_path}{C.RESET}')
    return out_path


# ══════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════

def run_all():
    print(f"""
{C.BOLD}══════════════════════════════════════════════════════════════
  📊 Paper Evaluation Harness
  Baselines × Ablations × Quantitative Metrics
=============================================================={C.RESET}
""")

    if not DASHSCOPE_KEY:
        print(f'{C.RED}❌ 未找到 DASHSCOPE_API_KEY{C.RESET}')
        return

    all_results = {}

    # ── 1. Baseline A: Prompt-only ──
    print(f'\n{C.BOLD}{"─" * 60}{C.RESET}')
    print(f'{C.BOLD}  📝 Baseline A: Pure Prompt{C.RESET}')
    print(f'{C.BOLD}{"─" * 60}{C.RESET}')
    all_results['baseline_prompt'] = run_baseline_prompt(EVAL_DIALOGUE)

    # ── 2. Baseline B: Reflexion ──
    print(f'\n{C.BOLD}{"─" * 60}{C.RESET}')
    print(f'{C.BOLD}  🔄 Baseline B: Reflexion{C.RESET}')
    print(f'{C.BOLD}{"─" * 60}{C.RESET}')
    all_results['baseline_reflexion'] = run_baseline_reflexion(EVAL_DIALOGUE)

    # ── 3. Genome V8 (完整) ──
    print(f'\n{C.BOLD}{"─" * 60}{C.RESET}')
    print(f'{C.BOLD}  🧬 Ours: Genome V8 (Full Physics){C.RESET}')
    print(f'{C.BOLD}{"─" * 60}{C.RESET}')
    v8_results, v8_memory = run_v8_full(EVAL_DIALOGUE, label="v8_full")
    all_results['v8_full'] = v8_results

    # ── 4. Ablation A: 关闭热噪声 ──
    print(f'\n{C.BOLD}{"─" * 60}{C.RESET}')
    print(f'{C.BOLD}  🔇 Ablation A: No Thermal Noise{C.RESET}')
    print(f'{C.BOLD}{"─" * 60}{C.RESET}')
    abl_a, _ = run_v8_full(EVAL_DIALOGUE, disable_thermal=True, label="v8_no_thermal")
    all_results['v8_no_thermal'] = abl_a

    # ── 5. Ablation B: 关闭霍金辐射 ──
    print(f'\n{C.BOLD}{"─" * 60}{C.RESET}')
    print(f'{C.BOLD}  🕳️ Ablation B: No Hawking Radiation{C.RESET}')
    print(f'{C.BOLD}{"─" * 60}{C.RESET}')
    abl_b, _ = run_v8_full(EVAL_DIALOGUE, disable_hawking=True, label="v8_no_hawking")
    all_results['v8_no_hawking'] = abl_b

    # ── 量化分析 ──
    print(f'\n{C.BOLD}══════════════════════════════════════════════════════════════{C.RESET}')
    print(f'{C.BOLD}  📊 Quantitative Metrics{C.RESET}')
    print(f'{C.BOLD}══════════════════════════════════════════════════════════════{C.RESET}')

    for method, data in all_results.items():
        replies_only = [r for r in data if r.get('reply')]
        metrics = compute_metrics(replies_only)
        crystallizations = sum(1 for r in data if r.get('crystallized'))

        print(f'\n  {C.BOLD}{method}{C.RESET}')
        print(f'    Semantic Entropy:     {metrics["semantic_entropy"]:.4f}')
        print(f'    Emotional Variance:   {metrics["emotional_variance"]:.1f}')
        print(f'    RLHF Collapse Index:  {metrics["rlhf_collapse_index"]:.3f}')
        print(f'    Avg Reply Length:      {metrics["avg_reply_length"]:.0f}')
        print(f'    Crystallizations:      {crystallizations}')

    # ── 保存 JSON ──
    json_path = os.path.join(RESULTS_DIR, "eval_raw.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f'\n  {C.GREEN}💾 Raw data → {json_path}{C.RESET}')

    # ── 可视化 ──
    plot_comparison(all_results)

    print(f'\n{C.BOLD}{"═" * 60}{C.RESET}')
    print(f'  {C.GREEN}✅ 评估完成！所有数据 → {RESULTS_DIR}/{C.RESET}')
    print(f'{C.BOLD}{"═" * 60}{C.RESET}')


if __name__ == '__main__':
    run_all()
