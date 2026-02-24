#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  📊 Evaluation Pipeline v3 — Statistical Analysis                   ║
║                                                                      ║
║  Aggregates results from eval_v3.py runs and computes:               ║
║    - Per-metric mean ± std across seeds                              ║
║    - Cross-scenario aggregation table                                ║
║    - Wilcoxon signed-rank tests (V8 vs each baseline)                ║
║    - Cohen's d + rank-biserial r effect sizes                        ║
║    - Publication-ready figures                                       ║
║                                                                      ║
║  Usage: python eval_v3_stats.py                                      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import math
import glob
from collections import defaultdict
from pathlib import Path

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "eval_results", "v3")

# ══════════════════════════════════════════════
# Load Results
# ══════════════════════════════════════════════

def load_all_results():
    """Load all v3 result JSONs into a structured dict."""
    results = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    # results[model][scenario][method] = [run1, run2, run3]

    pattern = os.path.join(RESULTS_DIR, "*.json")
    for path in sorted(glob.glob(pattern)):
        if os.path.basename(path).startswith("_"):
            continue  # skip checkpoint
        if "stats_" in os.path.basename(path):
            continue  # skip our own output

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        meta = data.get("meta", {})
        model = meta.get("model", "unknown")
        scenario = meta.get("scenario", "unknown")
        method = meta.get("method", "unknown")

        results[model][scenario][method].append(data)

    return results


# ══════════════════════════════════════════════
# Statistical Tests
# ══════════════════════════════════════════════

def mean_std(values):
    """Compute mean and std."""
    if not values:
        return 0.0, 0.0
    m = sum(values) / len(values)
    if len(values) < 2:
        return m, 0.0
    var = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return m, math.sqrt(var)


def wilcoxon_signed_rank(x, y):
    """
    Manual Wilcoxon signed-rank test (no scipy dependency).
    Returns (statistic, p_value_approx).
    For n >= 10, uses normal approximation; for smaller n, returns approximate p.
    """
    diffs = [a - b for a, b in zip(x, y)]
    diffs = [(i, d) for i, d in enumerate(diffs) if abs(d) > 1e-10]

    if len(diffs) < 3:
        return 0, 1.0

    # Rank by absolute value
    diffs.sort(key=lambda t: abs(t[1]))
    ranks = {}
    for rank_idx, (orig_idx, d) in enumerate(diffs, 1):
        ranks[orig_idx] = rank_idx

    # Sum of positive ranks and negative ranks
    w_plus = sum(ranks[i] for i, d in diffs if d > 0)
    w_minus = sum(ranks[i] for i, d in diffs if d < 0)
    w = min(w_plus, w_minus)

    n = len(diffs)
    # Normal approximation for p-value
    mean_w = n * (n + 1) / 4.0
    std_w = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    if std_w == 0:
        return w, 1.0
    z = (w - mean_w) / std_w
    # Two-tailed p-value approximation using error function
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))
    return w, p


def cohens_d_paired(x, y):
    """Cohen's d for paired samples."""
    diffs = [a - b for a, b in zip(x, y)]
    if len(diffs) < 2:
        return 0.0
    m = sum(diffs) / len(diffs)
    var = sum((d - m) ** 2 for d in diffs) / (len(diffs) - 1)
    sd = math.sqrt(var) if var > 0 else 1e-10
    return m / sd


def rank_biserial_r(x, y):
    """Rank-biserial correlation (effect size for Wilcoxon)."""
    diffs = [a - b for a, b in zip(x, y)]
    diffs_nonzero = [d for d in diffs if abs(d) > 1e-10]
    n = len(diffs_nonzero)
    if n == 0:
        return 0.0

    # Sort by absolute value, assign ranks
    indexed = sorted(enumerate(diffs_nonzero), key=lambda t: abs(t[1]))
    ranks = [0] * n
    for rank_idx, (orig_idx, _) in enumerate(indexed, 1):
        ranks[orig_idx] = rank_idx

    r_plus = sum(ranks[i] for i in range(n) if diffs_nonzero[i] > 0)
    r_minus = sum(ranks[i] for i in range(n) if diffs_nonzero[i] < 0)

    total_rank = n * (n + 1) / 2.0
    if total_rank == 0:
        return 0.0
    return (r_plus - r_minus) / total_rank


def interpret_d(d):
    """Interpret Cohen's d magnitude."""
    d = abs(d)
    if d < 0.2:
        return "negligible"
    elif d < 0.5:
        return "small"
    elif d < 0.8:
        return "medium"
    else:
        return "large"


def compute_effect_sizes(v8_scores, baseline_scores):
    """Full statistical comparison: Wilcoxon + Cohen's d + rank-biserial r."""
    if len(v8_scores) != len(baseline_scores) or len(v8_scores) < 3:
        return {"p": 1.0, "cohens_d": 0.0, "rank_biserial_r": 0.0, "interpretation": "insufficient data"}

    w, p = wilcoxon_signed_rank(v8_scores, baseline_scores)
    d = cohens_d_paired(v8_scores, baseline_scores)
    r = rank_biserial_r(v8_scores, baseline_scores)

    return {
        "w_statistic": w,
        "p": round(p, 4),
        "cohens_d": round(d, 3),
        "rank_biserial_r": round(r, 3),
        "interpretation": interpret_d(d),
    }


# ══════════════════════════════════════════════
# Aggregation & Report
# ══════════════════════════════════════════════

KEY_METRICS = ['distinct_2', 'cross_rep_3', 'semantic_entropy', 'emotional_variance',
               'rlhf_collapse_index', 'pcs', 'avg_reply_length']


def aggregate_across_seeds(runs):
    """Aggregate metrics across multiple seed runs (mean ± std)."""
    if not runs:
        return {}
    metric_values = defaultdict(list)
    for run in runs:
        for k, v in run.get("metrics", {}).items():
            if isinstance(v, (int, float)):
                metric_values[k].append(v)
    return {k: mean_std(v) for k, v in metric_values.items()}


def generate_report(all_results):
    """Generate full statistical report."""
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("  📊 Evaluation Pipeline v3 — Statistical Report")
    report_lines.append("=" * 80)

    all_stats = {}

    for model in sorted(all_results.keys()):
        report_lines.append(f"\n{'═' * 80}")
        report_lines.append(f"  🤖 Model: {model}")
        report_lines.append(f"{'═' * 80}")

        model_data = all_results[model]

        # ── Cross-scenario table ──
        report_lines.append(f"\n  ┌{'─' * 76}┐")
        report_lines.append(f"  │ {'Metric':<20} {'Prompt':>10} {'Reflexion':>10} {'V8 Full':>10} {'NoTherm':>10} {'NoHawk':>10} │")
        report_lines.append(f"  ├{'─' * 76}┤")

        # Aggregate across ALL scenarios for overall comparison
        method_overall = defaultdict(lambda: defaultdict(list))
        for scenario in model_data:
            for method in model_data[scenario]:
                runs = model_data[scenario][method]
                for run in runs:
                    for k, v in run.get("metrics", {}).items():
                        if isinstance(v, (int, float)):
                            method_overall[method][k].append(v)

        methods_order = ['baseline_prompt', 'baseline_reflexion', 'v8_full', 'v8_no_thermal', 'v8_no_hawking']

        for metric in KEY_METRICS:
            row = f"  │ {metric:<20}"
            for method in methods_order:
                vals = method_overall.get(method, {}).get(metric, [])
                if vals:
                    m, s = mean_std(vals)
                    row += f" {m:>7.3f}±{s:.2f}"
                else:
                    row += f" {'—':>10}"
            row += " │"
            report_lines.append(row)
        report_lines.append(f"  └{'─' * 76}┘")

        # ── Per-scenario breakdown ──
        for scenario in sorted(model_data.keys()):
            report_lines.append(f"\n  📋 Scenario: {scenario}")
            for method in methods_order:
                runs = model_data[scenario].get(method, [])
                agg = aggregate_across_seeds(runs)
                if agg:
                    parts = [f"{k}={m:.3f}±{s:.2f}" for k, (m, s) in agg.items() if k in KEY_METRICS]
                    report_lines.append(f"    {method:<22} {', '.join(parts[:4])}")

        # ── Effect sizes: V8 vs baselines ──
        report_lines.append(f"\n  📐 Effect Sizes (V8 Full vs Baselines)")
        report_lines.append(f"  {'─' * 70}")

        for baseline in ['baseline_prompt', 'baseline_reflexion']:
            report_lines.append(f"\n    V8 Full vs {baseline}:")
            for metric in KEY_METRICS:
                v8_vals = method_overall.get('v8_full', {}).get(metric, [])
                bl_vals = method_overall.get(baseline, {}).get(metric, [])
                if v8_vals and bl_vals:
                    # Align by matching scenario+seed pairs
                    min_len = min(len(v8_vals), len(bl_vals))
                    es = compute_effect_sizes(v8_vals[:min_len], bl_vals[:min_len])
                    report_lines.append(
                        f"      {metric:<22} p={es['p']:<8.4f} d={es['cohens_d']:>+6.3f} ({es['interpretation']:<10}) "
                        f"r={es['rank_biserial_r']:>+6.3f}"
                    )

        # Store for JSON output
        all_stats[model] = {
            "overall": {method: {k: {"mean": m, "std": s}
                                  for k, (m, s) in
                                  {mk: mean_std(mv)
                                   for mk, mv in method_overall.get(method, {}).items()
                                   if mk in KEY_METRICS}.items()}
                        for method in methods_order},
            "effect_sizes": {},
        }

        for baseline in ['baseline_prompt', 'baseline_reflexion']:
            es_dict = {}
            for metric in KEY_METRICS:
                v8_vals = method_overall.get('v8_full', {}).get(metric, [])
                bl_vals = method_overall.get(baseline, {}).get(metric, [])
                if v8_vals and bl_vals:
                    min_len = min(len(v8_vals), len(bl_vals))
                    es_dict[metric] = compute_effect_sizes(v8_vals[:min_len], bl_vals[:min_len])
            all_stats[model]["effect_sizes"][f"v8_vs_{baseline}"] = es_dict

    return "\n".join(report_lines), all_stats


# ══════════════════════════════════════════════
# Visualization
# ══════════════════════════════════════════════

def plot_results(all_results):
    """Generate publication-ready comparison figures."""
    try:
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("  ⚠️  matplotlib/numpy not available, skipping plots")
        return

    plt.rcParams['axes.unicode_minus'] = False

    colors = {
        'baseline_prompt': '#888888',
        'baseline_reflexion': '#ff9900',
        'v8_full': '#ff3366',
        'v8_no_thermal': '#66aaff',
        'v8_no_hawking': '#99ff66',
    }
    method_labels = {
        'baseline_prompt': 'Prompt-only',
        'baseline_reflexion': 'Reflexion',
        'v8_full': 'V8 Full',
        'v8_no_thermal': 'No Thermal',
        'v8_no_hawking': 'No Hawking',
    }
    methods_order = list(method_labels.keys())

    for model in all_results:
        model_data = all_results[model]

        # Aggregate all scenario data
        method_metrics = defaultdict(lambda: defaultdict(list))
        for scenario in model_data:
            for method in model_data[scenario]:
                for run in model_data[scenario][method]:
                    for k, v in run.get("metrics", {}).items():
                        if isinstance(v, (int, float)):
                            method_metrics[method][k].append(v)

        # ── Bar chart: key metrics ──
        fig, axes = plt.subplots(1, 3, figsize=(15, 5), facecolor='#0a0a12')
        chart_metrics = ['distinct_2', 'semantic_entropy', 'emotional_variance']
        chart_titles = ['Distinct-2 ↑', 'Semantic Entropy ↑', 'Emotional Variance ↑']

        for ax, metric, title in zip(axes, chart_metrics, chart_titles):
            ax.set_facecolor('#0a0a12')
            ax.tick_params(colors='#8888aa', labelsize=8)
            for spine in ax.spines.values():
                spine.set_color('#333366')

            x = range(len(methods_order))
            means = []
            stds = []
            for method in methods_order:
                vals = method_metrics.get(method, {}).get(metric, [])
                m, s = mean_std(vals) if vals else (0, 0)
                means.append(m)
                stds.append(s)

            bars = ax.bar(x, means, yerr=stds, capsize=4,
                         color=[colors.get(m, '#fff') for m in methods_order],
                         alpha=0.85, edgecolor='#333366')
            ax.set_title(title, color='#e0e0ff', fontsize=11)
            ax.set_xticks(x)
            ax.set_xticklabels([method_labels[m] for m in methods_order],
                              rotation=25, ha='right', fontsize=8, color='#ccccee')

        fig.suptitle(f'📊 {model} — Key Metrics Comparison',
                    fontsize=14, color='#e0e0ff', fontweight='bold')
        plt.tight_layout(rect=[0, 0, 1, 0.93])
        out_path = os.path.join(RESULTS_DIR, f"stats_{model}_metrics.png")
        plt.savefig(out_path, dpi=150, facecolor='#0a0a12')
        plt.close()
        print(f'  📊 → {out_path}')

        # ── Heatmap: scenarios × methods ──
        scenarios = sorted(model_data.keys())
        if scenarios and len(methods_order) > 0:
            fig, ax = plt.subplots(figsize=(10, 6), facecolor='#0a0a12')
            ax.set_facecolor('#0a0a12')

            metric = 'distinct_2'
            data_matrix = []
            for scenario in scenarios:
                row = []
                for method in methods_order:
                    runs = model_data[scenario].get(method, [])
                    vals = [r.get("metrics", {}).get(metric, 0) for r in runs]
                    m, _ = mean_std(vals) if vals else (0, 0)
                    row.append(m)
                data_matrix.append(row)

            im = ax.imshow(data_matrix, cmap='RdYlGn', aspect='auto')
            ax.set_xticks(range(len(methods_order)))
            ax.set_xticklabels([method_labels[m] for m in methods_order],
                              rotation=25, ha='right', fontsize=9, color='#ccccee')
            ax.set_yticks(range(len(scenarios)))
            ax.set_yticklabels([s.replace('_', ' ').title() for s in scenarios],
                              fontsize=9, color='#ccccee')
            ax.set_title(f'{model} — Distinct-2 Heatmap (Scenarios × Methods)',
                        color='#e0e0ff', fontsize=12)
            plt.colorbar(im, ax=ax, shrink=0.8)

            # Annotate cells
            for i in range(len(scenarios)):
                for j in range(len(methods_order)):
                    ax.text(j, i, f'{data_matrix[i][j]:.3f}',
                           ha='center', va='center', fontsize=8,
                           color='black' if data_matrix[i][j] > 0.5 else 'white')

            plt.tight_layout()
            out_path = os.path.join(RESULTS_DIR, f"stats_{model}_heatmap.png")
            plt.savefig(out_path, dpi=150, facecolor='#0a0a12')
            plt.close()
            print(f'  📊 → {out_path}')


# ══════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════

def main():
    print(f"""
{'=' * 60}
  📊 Evaluation Pipeline v3 — Statistical Analysis
{'=' * 60}
""")

    all_results = load_all_results()
    if not all_results:
        print("  ❌ No result files found in", RESULTS_DIR)
        print("     Run eval_v3.py first to generate results.")
        return

    models = list(all_results.keys())
    total_files = sum(
        len(runs) for m in all_results.values()
        for s in m.values() for runs in s.values()
    )
    print(f"  Found {total_files} result files across {len(models)} models")

    # Generate report
    report_text, all_stats = generate_report(all_results)
    print(report_text)

    # Save text report
    report_path = os.path.join(RESULTS_DIR, "stats_report.txt")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(f'\n  📝 Report → {report_path}')

    # Save JSON stats
    stats_path = os.path.join(RESULTS_DIR, "stats_summary.json")
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(all_stats, f, indent=2, ensure_ascii=False)
    print(f'  💾 Stats → {stats_path}')

    # Generate plots
    plot_results(all_results)

    print(f'\n  ✅ Statistical analysis complete!')


if __name__ == '__main__':
    main()
