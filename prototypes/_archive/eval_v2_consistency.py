#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  📊 Evaluation Pipeline 2.1 — Persona Consistency Metric           ║
║                                                                      ║
║  核心指标: Persona Consistency Score (PCS)                          ║
║                                                                      ║
║  方法:                                                               ║
║    1. 对每轮回复做 jieba 分词 → TF-IDF 向量化                      ║
║    2. 计算连续 W 轮窗口内所有 pair 的 cosine similarity             ║
║    3. PCS = mean(所有窗口的 mean_cosine)                            ║
║                                                                      ║
║  PCS 高 = 说话风格一致 (像同一个人)                                 ║
║  PCS 低 = 风格跳变 (每轮像不同的人)                                 ║
║                                                                      ║
║  结合 Distinct-N:                                                    ║
║  - Reflexion: D-4 高 + PCS 低 = 多样但不一致 (人格分裂)            ║
║  - V8:       D-4 适中 + PCS 高 = 多样且一致 (真人)                 ║
║  - No Thermal: D-4 低 + PCS 超高 = 一致但复读 (坍缩)              ║
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
    CYAN = '\033[36m'
    MAGENTA = '\033[35m'
    RESET = '\033[0m'


# ══════════════════════════════════════════════
# TF-IDF (轻量级，无外部依赖)
# ══════════════════════════════════════════════

def tokenize_zh(text):
    tokens = list(jieba.cut(text))
    return [t for t in tokens if re.search(r'[\u4e00-\u9fff\w]', t)]


def build_tfidf_vectors(replies):
    """
    为一组回复构建 TF-IDF 向量。

    Returns:
        vocab: 词→索引映射
        vectors: list of dict {词索引: tfidf值}
    """
    # 分词
    tokenized = [tokenize_zh(r) for r in replies]

    # 构建词表
    all_tokens = set()
    for tokens in tokenized:
        all_tokens.update(tokens)
    vocab = {t: i for i, t in enumerate(sorted(all_tokens))}

    # 文档频率 (DF)
    df = Counter()
    for tokens in tokenized:
        unique_tokens = set(tokens)
        for t in unique_tokens:
            df[t] += 1

    n_docs = len(replies)

    # TF-IDF
    vectors = []
    for tokens in tokenized:
        if not tokens:
            vectors.append({})
            continue

        tf = Counter(tokens)
        vec = {}
        for t, count in tf.items():
            tf_val = count / len(tokens)
            idf_val = math.log((n_docs + 1) / (df[t] + 1)) + 1  # smooth IDF
            vec[vocab[t]] = tf_val * idf_val
        vectors.append(vec)

    return vocab, vectors


def cosine_sim(vec_a, vec_b):
    """计算两个稀疏向量(dict)的余弦相似度"""
    if not vec_a or not vec_b:
        return 0.0

    # 交集
    common_keys = set(vec_a.keys()) & set(vec_b.keys())
    if not common_keys:
        return 0.0

    dot = sum(vec_a[k] * vec_b[k] for k in common_keys)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


# ══════════════════════════════════════════════
# Persona Consistency Score (PCS)
# ══════════════════════════════════════════════

def persona_consistency_score(replies, window=5):
    """
    计算 Persona Consistency Score (PCS)。

    方法：在长度为 W 的滑动窗口内，计算所有 pair 的
    cosine similarity 平均值。最终 PCS = 所有窗口的均值。

    PCS ∈ [0, 1]
    - 1.0 = 每轮回复风格完全相同 (极端一致/复读机)
    - 0.0 = 每轮完全不同 (人格分裂)
    - 0.3~0.5 = 真人的典型范围 (有一致性但有变化)

    Args:
        replies: 回复文本列表
        window: 滑动窗口大小 (默认 5)

    Returns:
        dict with 'pcs', 'pcs_trajectory', 'pcs_std'
    """
    if len(replies) < 2:
        return {'pcs': 0.0, 'pcs_trajectory': [], 'pcs_std': 0.0}

    _, vectors = build_tfidf_vectors(replies)

    window_scores = []
    for i in range(len(vectors) - window + 1):
        window_vecs = vectors[i:i + window]
        # 计算窗口内所有 pair 的 cosine sim
        sims = []
        for a in range(len(window_vecs)):
            for b in range(a + 1, len(window_vecs)):
                sims.append(cosine_sim(window_vecs[a], window_vecs[b]))
        if sims:
            window_scores.append(sum(sims) / len(sims))

    if not window_scores:
        return {'pcs': 0.0, 'pcs_trajectory': [], 'pcs_std': 0.0}

    pcs = sum(window_scores) / len(window_scores)
    pcs_std = math.sqrt(sum((s - pcs) ** 2 for s in window_scores) / len(window_scores))

    return {
        'pcs': round(pcs, 4),
        'pcs_trajectory': [round(s, 4) for s in window_scores],
        'pcs_std': round(pcs_std, 4),
    }


def consecutive_cosine(replies):
    """
    计算连续两轮之间的 cosine similarity。
    更直接地观察风格跳变。
    """
    if len(replies) < 2:
        return {'mean': 0.0, 'trajectory': []}

    _, vectors = build_tfidf_vectors(replies)

    sims = []
    for i in range(len(vectors) - 1):
        sims.append(cosine_sim(vectors[i], vectors[i + 1]))

    mean_sim = sum(sims) / len(sims) if sims else 0.0
    return {
        'mean': round(mean_sim, 4),
        'std': round(math.sqrt(sum((s - mean_sim) ** 2 for s in sims) / max(1, len(sims))), 4),
        'trajectory': [round(s, 4) for s in sims],
    }


# ══════════════════════════════════════════════
# Consistency-Diversity Tradeoff Score
# ══════════════════════════════════════════════

def consistency_diversity_score(pcs, distinct_4):
    """
    一致性-多样性平衡分:
    CDS = 2 × PCS × D-4 / (PCS + D-4)   (调和平均)

    - 纯复读机: D-4 低 → CDS 低
    - 纯分裂:   PCS 低 → CDS 低
    - 好 Agent:  两者都高 → CDS 高
    """
    if pcs + distinct_4 == 0:
        return 0.0
    return round(2 * pcs * distinct_4 / (pcs + distinct_4), 4)


# ══════════════════════════════════════════════
# 可视化
# ══════════════════════════════════════════════

def plot_consistency(all_pcs, all_d4, all_consec):
    try:
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
    except ImportError:
        print(f'{C.YELLOW}⚠️ 需要 matplotlib{C.RESET}')
        return

    zh_fonts = [f for f in fm.findSystemFonts() if 'PingFang' in f or 'Hei' in f]
    if zh_fonts:
        plt.rcParams['font.family'] = fm.FontProperties(fname=zh_fonts[0]).get_name()
    plt.rcParams['axes.unicode_minus'] = False

    methods = list(all_pcs.keys())
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

    # ── Panel 1: PCS 柱状图 ──
    ax1 = axes[0, 0]
    x = range(len(methods))
    pcs_vals = [all_pcs[m]['pcs'] for m in methods]
    bar_colors = [colors.get(m, '#fff') for m in methods]
    bars = ax1.bar(x, pcs_vals, color=bar_colors, alpha=0.85, width=0.6)
    ax1.set_title('Persona Consistency Score (PCS)', color='#e0e0ff', fontsize=11)
    ax1.set_xticks(x)
    ax1.set_xticklabels([labels.get(m, m) for m in methods], color='#ccccee', fontsize=8, rotation=15)
    ax1.set_ylim(0, max(pcs_vals) * 1.3)
    # 标注数值
    for i, (bar, val) in enumerate(zip(bars, pcs_vals)):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
                 f'{val:.3f}', ha='center', va='bottom', color='#ccccee', fontsize=9)

    # ── Panel 2: Consistency vs Diversity 散点图 (核心!) ──
    ax2 = axes[0, 1]
    for m in methods:
        pcs = all_pcs[m]['pcs']
        d4 = all_d4.get(m, 0)
        cds = consistency_diversity_score(pcs, d4)
        ax2.scatter(d4, pcs, color=colors.get(m, '#fff'), s=120, alpha=0.9,
                    edgecolors='white', linewidths=0.5, zorder=3)
        ax2.annotate(f'{labels.get(m, m)}\nCDS={cds:.3f}',
                     (d4, pcs), textcoords="offset points",
                     xytext=(10, -5), fontsize=7, color=colors.get(m, '#fff'),
                     alpha=0.9)

    ax2.set_title('Consistency-Diversity Tradeoff', color='#e0e0ff', fontsize=11)
    ax2.set_xlabel('Distinct-4 (Diversity →)', color='#8888aa')
    ax2.set_ylabel('PCS (Consistency →)', color='#8888aa')
    # 理想区域
    ax2.axhspan(0.05, 0.25, alpha=0.05, color='#00ff88')
    ax2.text(0.97, 0.22, 'Ideal zone:\nhigh diversity +\nmoderate consistency',
             fontsize=7, color='#448866', alpha=0.6, ha='right')

    # ── Panel 3: 连续 cosine similarity 轨迹 ──
    ax3 = axes[1, 0]
    for m in methods:
        traj = all_consec[m]['trajectory']
        ax3.plot(range(len(traj)), traj, color=colors.get(m, '#fff'), alpha=0.7,
                 linewidth=1.2, label=labels.get(m, m))
    ax3.axvline(x=14, color='#ff4444', linestyle='--', alpha=0.3)
    ax3.axvline(x=24, color='#ff4444', linestyle='--', alpha=0.3)
    ax3.text(14.3, 0.9, '3d gap', color='#ff6666', fontsize=7, alpha=0.7)
    ax3.text(24.3, 0.9, '7d gap', color='#ff6666', fontsize=7, alpha=0.7)
    ax3.set_title('Consecutive Cosine Similarity (style stability)', color='#e0e0ff', fontsize=11)
    ax3.set_xlabel('Turn', color='#8888aa')
    ax3.set_ylabel('Cosine Sim', color='#8888aa')
    ax3.set_ylim(-0.05, 1.05)
    ax3.legend(fontsize=6, facecolor='#15152a', edgecolor='#333366', labelcolor='#ccccee')

    # ── Panel 4: Summary Table ──
    ax4 = axes[1, 1]
    ax4.axis('off')
    headers = ['Method', 'PCS', 'D-4', 'CDS', 'Consec.μ']
    rows = []
    for m in methods:
        pcs = all_pcs[m]['pcs']
        d4 = all_d4.get(m, 0)
        cds = consistency_diversity_score(pcs, d4)
        consec = all_consec[m]['mean']
        rows.append([labels.get(m, m), f'{pcs:.3f}', f'{d4:.3f}', f'{cds:.3f}', f'{consec:.3f}'])

    table = ax4.table(cellText=rows, colLabels=headers, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    for (row, col), cell in table.get_celld().items():
        cell.set_facecolor('#15152a')
        cell.set_edgecolor('#333366')
        cell.set_text_props(color='#ccccee')
        if row == 0:
            cell.set_facecolor('#1a1a3a')
            cell.set_text_props(color='#e0e0ff', fontweight='bold')
        # 高亮最佳 CDS
        if row > 0 and col == 3:
            cds_val = float(rows[row-1][3])
            if cds_val == max(float(r[3]) for r in rows):
                cell.set_text_props(color='#ff3366', fontweight='bold')

    ax4.set_title('Consistency-Diversity Scores', color='#e0e0ff', fontsize=11, pad=20)

    fig.suptitle('Persona Consistency: Closing the Consistency-Diversity Tradeoff',
                 fontsize=14, color='#e0e0ff', fontweight='bold', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    out_path = os.path.join(RESULTS_DIR, "v2_consistency.png")
    plt.savefig(out_path, dpi=150, facecolor='#0a0a12')
    plt.close()
    print(f'  {C.GREEN}📊 一致性图表 → {out_path}{C.RESET}')
    return out_path


# ══════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════

def main():
    print(f"""
{C.BOLD}══════════════════════════════════════════════════════════════
  📊 Persona Consistency Score (PCS)
  Consistency-Diversity Tradeoff Analysis
=============================================================={C.RESET}
""")

    if not os.path.exists(RAW_JSON):
        print(f'{C.RED}❌ 未找到 {RAW_JSON}{C.RESET}')
        return

    with open(RAW_JSON, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    # 加载 V2 的 Distinct-4 数据
    v2_path = os.path.join(RESULTS_DIR, "v2_metrics.json")
    d4_data = {}
    if os.path.exists(v2_path):
        with open(v2_path, 'r') as f:
            v2_metrics = json.load(f)
            for m, metrics in v2_metrics.items():
                d4_data[m] = metrics.get('distinct_4', 0)

    all_pcs = {}
    all_consec = {}

    for method_name, turns in raw_data.items():
        replies = [t['reply'] for t in turns if isinstance(t, dict) and t.get('reply')]
        if not replies:
            continue

        pcs_result = persona_consistency_score(replies, window=5)
        consec_result = consecutive_cosine(replies)
        all_pcs[method_name] = pcs_result
        all_consec[method_name] = consec_result

        d4 = d4_data.get(method_name, 0)
        cds = consistency_diversity_score(pcs_result['pcs'], d4)

        print(f'\n  {C.BOLD}▸ {method_name}{C.RESET}')
        print(f'    PCS (window=5):       {pcs_result["pcs"]:.4f} ± {pcs_result["pcs_std"]:.4f}')
        print(f'    Consecutive cos μ:    {consec_result["mean"]:.4f} ± {consec_result["std"]:.4f}')
        print(f'    Distinct-4:           {d4:.4f}')
        print(f'    {C.BOLD}CDS (harmonic):       {cds:.4f}{C.RESET}')

    # ── 关键对比 ──
    print(f'\n{C.BOLD}══════════════════════════════════════════════════════════════')
    print(f'  📋 Consistency-Diversity Tradeoff 分析')
    print(f'=============================================================={C.RESET}')

    # 计算并排序 CDS
    cds_ranking = []
    for m in all_pcs:
        pcs = all_pcs[m]['pcs']
        d4 = d4_data.get(m, 0)
        cds = consistency_diversity_score(pcs, d4)
        cds_ranking.append((m, pcs, d4, cds))

    cds_ranking.sort(key=lambda x: x[3], reverse=True)
    print(f'\n  {C.CYAN}CDS 排名 (调和平均 = 兼顾多样性与一致性):{C.RESET}')
    for rank, (m, pcs, d4, cds) in enumerate(cds_ranking, 1):
        marker = '🥇' if rank == 1 else '🥈' if rank == 2 else '🥉' if rank == 3 else '  '
        print(f'    {marker} #{rank} {m:20s} CDS={cds:.4f}  (PCS={pcs:.3f} × D4={d4:.3f})')

    # 保存
    output = {m: {
        'pcs': all_pcs[m]['pcs'],
        'pcs_std': all_pcs[m]['pcs_std'],
        'consecutive_cosine_mean': all_consec[m]['mean'],
        'consecutive_cosine_std': all_consec[m]['std'],
        'distinct_4': d4_data.get(m, 0),
        'cds': consistency_diversity_score(all_pcs[m]['pcs'], d4_data.get(m, 0)),
    } for m in all_pcs}

    json_path = os.path.join(RESULTS_DIR, "v2_consistency.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\n  {C.GREEN}💾 → {json_path}{C.RESET}')

    # 可视化
    plot_consistency(all_pcs, d4_data, all_consec)

    print(f'\n{C.BOLD}{"═" * 60}{C.RESET}')
    print(f'  {C.GREEN}✅ Persona Consistency 分析完成{C.RESET}')
    print(f'{C.BOLD}{"═" * 60}{C.RESET}')


if __name__ == '__main__':
    main()
