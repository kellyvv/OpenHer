#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  📊 Evaluation Pipeline 2.0 — NLP 工业标准指标                     ║
║                                                                      ║
║  废弃自创指标，换用论文审稿人认可的金标准:                          ║
║    1. Distinct-N (N-gram 不重复率)   → 替代 Semantic Entropy        ║
║    2. N-gram 重复率 (Rep-N)          → 精确量化模式坍缩            ║
║    3. 情感轨迹协方差Trace            → 替代 Emotional Variance     ║
║    4. 回复长度方差                    → 情绪波动代理               ║
║                                                                      ║
║  输入: eval_results/eval_raw.json (Phase 7 的原始数据)              ║
║  输出: eval_results/v2_metrics.json + v2_comparison.png             ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import math
import re
from collections import Counter

import jieba

# ── Paths ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "eval_results")
RAW_JSON = os.path.join(RESULTS_DIR, "eval_raw.json")

# ANSI
class C:
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    RESET = '\033[0m'


# ══════════════════════════════════════════════
# 中文分词
# ══════════════════════════════════════════════

def tokenize_zh(text):
    """用 jieba 分词。过滤标点和空白。"""
    tokens = list(jieba.cut(text))
    # 过滤纯标点和空白
    tokens = [t for t in tokens if re.search(r'[\u4e00-\u9fff\w]', t)]
    return tokens


# ══════════════════════════════════════════════
# Metric 1: Distinct-N (Li et al., 2016)
#
# 对话系统多样性的标准指标，被 ACL/EMNLP 近百篇论文引用。
# Distinct-N = 不重复 N-gram 数 / 总 N-gram 数
# 值域 [0, 1]。1 = 完全不重复，0 = 全是复读机。
# ══════════════════════════════════════════════

def get_ngrams(tokens, n):
    """从 token 列表提取 n-gram 元组列表。"""
    return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]


def distinct_n(replies, n):
    """
    计算一组回复的 Distinct-N。

    Args:
        replies: 回复字符串列表
        n: N-gram 的 N (通常 1, 2, 3, 4)

    Returns:
        Distinct-N 值 (0~1)
    """
    all_ngrams = []
    for reply in replies:
        tokens = tokenize_zh(reply)
        ngrams = get_ngrams(tokens, n)
        all_ngrams.extend(ngrams)

    if not all_ngrams:
        return 0.0

    unique_ngrams = set(all_ngrams)
    return len(unique_ngrams) / len(all_ngrams)


# ══════════════════════════════════════════════
# Metric 2: Rep-N (N-gram 重复率)
#
# 互补指标。Rep-N = 1 - Distinct-N，但按回复级别计算。
# 用于定位具体哪些轮次出现了复读。
#
# 单轮 Rep-4 = 该轮回复中 4-gram 重复占比。
# 全局 Rep-4 = 跨所有回复的 4-gram 重复率。
# ══════════════════════════════════════════════

def rep_n_per_turn(replies, n):
    """计算每轮的 N-gram 重复率。"""
    rates = []
    for reply in replies:
        tokens = tokenize_zh(reply)
        ngrams = get_ngrams(tokens, n)
        if not ngrams:
            rates.append(0.0)
            continue
        counter = Counter(ngrams)
        repeated = sum(c - 1 for c in counter.values() if c > 1)
        rates.append(repeated / len(ngrams))
    return rates


def cross_turn_rep_n(replies, n):
    """
    跨回复重复率：测量不同轮次之间的 N-gram 重复。
    这是检测"模板化"的最直接指标。

    方法：把所有回复的 N-gram 去重后，计算跨回复共享的比例。
    """
    per_reply_ngram_sets = []
    for reply in replies:
        tokens = tokenize_zh(reply)
        ngrams = set(get_ngrams(tokens, n))
        per_reply_ngram_sets.append(ngrams)

    if len(per_reply_ngram_sets) < 2:
        return 0.0

    # 统计每个 n-gram 出现在多少个不同的回复中
    ngram_reply_count = Counter()
    for ngram_set in per_reply_ngram_sets:
        for ng in ngram_set:
            ngram_reply_count[ng] += 1

    # 跨回复重复 = 出现在 ≥2 个回复中的 n-gram 数 / 总去重 n-gram 数
    all_unique = set(ngram_reply_count.keys())
    cross_repeated = sum(1 for ng, c in ngram_reply_count.items() if c >= 2)

    return cross_repeated / max(1, len(all_unique))


# ══════════════════════════════════════════════
# Metric 3: 情感轨迹分析 (简化版)
#
# 完整版需要 RoBERTa-GoEmotions (HuggingFace)，但为了
# 不引入 GPU 依赖，先用简易的情感极性词典做近似。
# 后续可替换为 transformer pipeline。
# ══════════════════════════════════════════════

# 简易极性词典 (正/负/中性)
POSITIVE_MARKERS = set('嗯哦好嘛呀吧哈嘻喜欢抱笑乖甜会想念温柔安心'.replace('', ' ').split() +
                       ['喜欢', '想你', '抱抱', '笑', '乖', '甜', '温柔', '安心', '晚安'])
NEGATIVE_MARKERS = set('滚恨烦讨厌别走哭算了受够冷漠消失对不起错道歉怕'.replace('', ' ').split() +
                       ['滚', '恨', '讨厌', '受够', '消失', '冷漠', '对不起', '算了', '怕'])


def simple_sentiment(text):
    """简易情感极性分数 [-1, 1]。正=正面，负=负面。"""
    tokens = set(tokenize_zh(text))
    pos = len(tokens & POSITIVE_MARKERS)
    neg = len(tokens & NEGATIVE_MARKERS)
    total = pos + neg
    if total == 0:
        return 0.0
    return (pos - neg) / total


def sentiment_trajectory_stats(replies):
    """计算情感轨迹的统计特征。"""
    sentiments = [simple_sentiment(r) for r in replies]

    if len(sentiments) < 2:
        return {'mean': 0.0, 'std': 0.0, 'range': 0.0, 'trajectory': sentiments}

    mean_s = sum(sentiments) / len(sentiments)
    var_s = sum((s - mean_s) ** 2 for s in sentiments) / len(sentiments)
    std_s = math.sqrt(var_s)

    # 情感转折次数（连续符号变化）
    sign_changes = sum(1 for i in range(1, len(sentiments))
                       if sentiments[i] * sentiments[i-1] < 0)

    return {
        'mean': round(mean_s, 4),
        'std': round(std_s, 4),
        'range': round(max(sentiments) - min(sentiments), 4),
        'sign_changes': sign_changes,
        'trajectory': [round(s, 3) for s in sentiments],
    }


# ══════════════════════════════════════════════
# Metric 4: 回复长度统计
# ══════════════════════════════════════════════

def reply_length_stats(replies):
    """回复长度的均值和标准差"""
    lengths = [len(r) for r in replies]
    if not lengths:
        return {'mean': 0, 'std': 0}
    mean_l = sum(lengths) / len(lengths)
    var_l = sum((x - mean_l) ** 2 for x in lengths) / len(lengths)
    return {
        'mean': round(mean_l, 1),
        'std': round(math.sqrt(var_l), 1),
        'min': min(lengths),
        'max': max(lengths),
    }


# ══════════════════════════════════════════════
# 综合计算
# ══════════════════════════════════════════════

def compute_all_metrics(replies, method_name):
    """对一组回复计算所有标准指标。"""

    d1 = distinct_n(replies, 1)
    d2 = distinct_n(replies, 2)
    d3 = distinct_n(replies, 3)
    d4 = distinct_n(replies, 4)

    cross_rep3 = cross_turn_rep_n(replies, 3)
    cross_rep4 = cross_turn_rep_n(replies, 4)

    sentiment = sentiment_trajectory_stats(replies)
    length = reply_length_stats(replies)

    return {
        'method': method_name,
        'distinct_1': round(d1, 4),
        'distinct_2': round(d2, 4),
        'distinct_3': round(d3, 4),
        'distinct_4': round(d4, 4),
        'cross_turn_rep_3': round(cross_rep3, 4),
        'cross_turn_rep_4': round(cross_rep4, 4),
        'sentiment_mean': sentiment['mean'],
        'sentiment_std': sentiment['std'],
        'sentiment_range': sentiment['range'],
        'sentiment_sign_changes': sentiment['sign_changes'],
        'reply_length_mean': length['mean'],
        'reply_length_std': length['std'],
        'total_replies': len(replies),
    }


# ══════════════════════════════════════════════
# 可视化
# ══════════════════════════════════════════════

def plot_v2(all_metrics, all_replies):
    """生成 V2 对比图表 — 只用正规军指标"""
    try:
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
    except ImportError:
        print(f'{C.YELLOW}⚠️ 需要 matplotlib{C.RESET}')
        return

    zh_fonts = [f for f in fm.findSystemFonts() if 'PingFang' in f or 'Hei' in f or 'Song' in f]
    if zh_fonts:
        plt.rcParams['font.family'] = fm.FontProperties(fname=zh_fonts[0]).get_name()
    plt.rcParams['axes.unicode_minus'] = False

    methods = list(all_metrics.keys())
    colors = {
        'baseline_prompt': '#888888',
        'baseline_reflexion': '#ff9900',
        'v8_full': '#ff3366',
        'v8_no_thermal': '#66aaff',
        'v8_no_hawking': '#99ff66',
    }
    labels = {
        'baseline_prompt': 'Prompt-only',
        'baseline_reflexion': 'Reflexion',
        'v8_full': 'Ours (V8)',
        'v8_no_thermal': 'Abl: No Thermal',
        'v8_no_hawking': 'Abl: No Hawking',
    }

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), facecolor='#0a0a12')
    for ax in axes.flat:
        ax.set_facecolor('#0a0a12')
        ax.tick_params(colors='#8888aa', labelsize=8)
        for spine in ax.spines.values():
            spine.set_color('#333366')

    # ── Panel 1: Distinct-N 柱状图 ──
    ax1 = axes[0, 0]
    x = range(4)
    width = 0.14
    for mi, method in enumerate(methods):
        m = all_metrics[method]
        values = [m['distinct_1'], m['distinct_2'], m['distinct_3'], m['distinct_4']]
        ax1.bar([xi + mi * width for xi in x], values, width,
                color=colors.get(method, '#fff'), alpha=0.85,
                label=labels.get(method, method))
    ax1.set_title('Distinct-N (higher = more diverse)', color='#e0e0ff', fontsize=11)
    ax1.set_xticks([xi + width * len(methods) / 2 for xi in x])
    ax1.set_xticklabels(['D-1', 'D-2', 'D-3', 'D-4'], color='#ccccee')
    ax1.set_ylim(0, 1.05)
    ax1.legend(fontsize=7, facecolor='#15152a', edgecolor='#333366', labelcolor='#ccccee')
    ax1.axhline(y=0.5, color='#444466', linestyle=':', alpha=0.5)

    # ── Panel 2: Cross-turn Repetition Rate ──
    ax2 = axes[0, 1]
    x2 = range(len(methods))
    rep3_vals = [all_metrics[m]['cross_turn_rep_3'] for m in methods]
    rep4_vals = [all_metrics[m]['cross_turn_rep_4'] for m in methods]
    w = 0.3
    ax2.bar([xi - w/2 for xi in x2], rep3_vals, w,
            color='#6688cc', alpha=0.8, label='Cross-Rep-3')
    ax2.bar([xi + w/2 for xi in x2], rep4_vals, w,
            color='#cc6688', alpha=0.8, label='Cross-Rep-4')
    ax2.set_title('Cross-turn N-gram Repetition (lower = less template)', color='#e0e0ff', fontsize=11)
    ax2.set_xticks(x2)
    ax2.set_xticklabels([labels.get(m, m) for m in methods], color='#ccccee', fontsize=7, rotation=15)
    ax2.legend(fontsize=7, facecolor='#15152a', edgecolor='#333366', labelcolor='#ccccee')

    # ── Panel 3: Sentiment Trajectory ──
    ax3 = axes[1, 0]
    for method in methods:
        replies = all_replies[method]
        trajectory = [simple_sentiment(r) for r in replies]
        ax3.plot(range(len(trajectory)), trajectory,
                 color=colors.get(method, '#fff'), alpha=0.7, linewidth=1.2,
                 label=labels.get(method, method))

    # 标记时间跳跃位置
    ax3.axvline(x=15, color='#ff4444', linestyle='--', alpha=0.3, linewidth=1)
    ax3.axvline(x=25, color='#ff4444', linestyle='--', alpha=0.3, linewidth=1)
    ax3.text(15.3, 0.9, '3d gap', color='#ff6666', fontsize=7, alpha=0.7)
    ax3.text(25.3, 0.9, '7d gap', color='#ff6666', fontsize=7, alpha=0.7)

    ax3.set_title('Sentiment Trajectory', color='#e0e0ff', fontsize=11)
    ax3.set_xlabel('Turn', color='#8888aa')
    ax3.set_ylabel('Polarity [-1, +1]', color='#8888aa')
    ax3.set_ylim(-1.1, 1.1)
    ax3.legend(fontsize=6, facecolor='#15152a', edgecolor='#333366', labelcolor='#ccccee')

    # ── Panel 4: Summary Table (text) ──
    ax4 = axes[1, 1]
    ax4.axis('off')
    table_data = []
    col_headers = ['Method', 'D-3', 'D-4', 'XRep-3', 'XRep-4', 'Sent.Std', 'Len.Std']
    for method in methods:
        m = all_metrics[method]
        table_data.append([
            labels.get(method, method),
            f'{m["distinct_3"]:.3f}',
            f'{m["distinct_4"]:.3f}',
            f'{m["cross_turn_rep_3"]:.3f}',
            f'{m["cross_turn_rep_4"]:.3f}',
            f'{m["sentiment_std"]:.3f}',
            f'{m["reply_length_std"]:.1f}',
        ])

    table = ax4.table(cellText=table_data, colLabels=col_headers,
                      loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(8)

    for (row, col), cell in table.get_celld().items():
        cell.set_facecolor('#15152a')
        cell.set_edgecolor('#333366')
        cell.set_text_props(color='#ccccee')
        if row == 0:
            cell.set_facecolor('#1a1a3a')
            cell.set_text_props(color='#e0e0ff', fontweight='bold')
        # 高亮 No Thermal 行
        if row > 0 and table_data[row-1][0] == 'Abl: No Thermal':
            cell.set_facecolor('#1a1a2a')
            cell.set_text_props(color='#ff6688')

    ax4.set_title('NLP Standard Metrics Summary', color='#e0e0ff', fontsize=11, pad=20)

    fig.suptitle('Evaluation Pipeline 2.0: NLP Industry-Standard Metrics',
                 fontsize=14, color='#e0e0ff', fontweight='bold', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    out_path = os.path.join(RESULTS_DIR, "v2_comparison.png")
    plt.savefig(out_path, dpi=150, facecolor='#0a0a12')
    plt.close()
    print(f'  {C.GREEN}📊 V2 图表 → {out_path}{C.RESET}')
    return out_path


# ══════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════

def main():
    print(f"""
{C.BOLD}══════════════════════════════════════════════════════════════
  📊 Evaluation Pipeline 2.0 — NLP Standard Metrics
  Distinct-N × Cross-Rep × Sentiment Trajectory
=============================================================={C.RESET}
""")

    # 加载原始数据
    if not os.path.exists(RAW_JSON):
        print(f'{C.RED}❌ 未找到 {RAW_JSON}{C.RESET}')
        print(f'   请先运行 eval_paper.py 生成原始数据。')
        return

    with open(RAW_JSON, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    print(f'  {C.DIM}加载 {RAW_JSON} — {len(raw_data)} 个 method{C.RESET}')

    # 提取回复
    all_replies = {}
    all_metrics = {}

    for method_name, turns in raw_data.items():
        replies = [t['reply'] for t in turns if isinstance(t, dict) and t.get('reply')]
        all_replies[method_name] = replies
        print(f'\n{C.BOLD}  ▸ {method_name} ({len(replies)} replies){C.RESET}')

        metrics = compute_all_metrics(replies, method_name)
        all_metrics[method_name] = metrics

        print(f'    Distinct-1:  {metrics["distinct_1"]:.4f}')
        print(f'    Distinct-2:  {metrics["distinct_2"]:.4f}')
        print(f'    Distinct-3:  {metrics["distinct_3"]:.4f}')
        print(f'    {C.BOLD}Distinct-4:  {metrics["distinct_4"]:.4f}{C.RESET}')
        print(f'    Cross-Rep-3: {metrics["cross_turn_rep_3"]:.4f}')
        print(f'    {C.BOLD}Cross-Rep-4: {metrics["cross_turn_rep_4"]:.4f}{C.RESET}')
        print(f'    Sentiment σ: {metrics["sentiment_std"]:.4f}')
        print(f'    Length μ±σ:   {metrics["reply_length_mean"]:.0f} ± {metrics["reply_length_std"]:.0f}')

    # 保存 JSON
    json_path = os.path.join(RESULTS_DIR, "v2_metrics.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_metrics, f, ensure_ascii=False, indent=2)
    print(f'\n  {C.GREEN}💾 V2 metrics → {json_path}{C.RESET}')

    # 可视化
    plot_v2(all_metrics, all_replies)

    # ── 关键对比总结 ──
    print(f'\n{C.BOLD}══════════════════════════════════════════════════════════════')
    print(f'  📋 关键发现 (NLP Standard Metrics)')
    print(f'=============================================================={C.RESET}')

    v8 = all_metrics.get('v8_full', {})
    no_th = all_metrics.get('v8_no_thermal', {})
    prompt = all_metrics.get('baseline_prompt', {})
    reflex = all_metrics.get('baseline_reflexion', {})

    if v8 and no_th:
        d4_drop = ((no_th.get('distinct_4', 0) - v8.get('distinct_4', 0))
                   / max(v8.get('distinct_4', 1), 0.001) * 100)
        rep4_rise = ((no_th.get('cross_turn_rep_4', 0) - v8.get('cross_turn_rep_4', 0))
                     / max(v8.get('cross_turn_rep_4', 0.001), 0.001) * 100)
        print(f'\n  {C.CYAN}消融 A (No Thermal) vs V8 Full:{C.RESET}')
        print(f'    Distinct-4: {no_th.get("distinct_4", 0):.4f} vs {v8.get("distinct_4", 0):.4f}'
              f' ({d4_drop:+.1f}%)')
        print(f'    Cross-Rep-4: {no_th.get("cross_turn_rep_4", 0):.4f} vs {v8.get("cross_turn_rep_4", 0):.4f}'
              f' ({rep4_rise:+.1f}%)')

    print(f'\n{C.BOLD}{"═" * 60}{C.RESET}')
    print(f'  {C.GREEN}✅ V2 评估完成{C.RESET}')
    print(f'{C.BOLD}{"═" * 60}{C.RESET}')


if __name__ == '__main__':
    main()
