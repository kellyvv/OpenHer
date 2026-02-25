#!/usr/bin/env python3
"""
MiniMax Robustness Check — Appendix C Data Generator

Computes key metrics for MiniMax-M2.5 excluding emotional_comfort scenario,
comparing Baseline-Prompt (BP) vs TPE-Full (v8_full).
"""

import os
import json
import math
import glob
from collections import defaultdict

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "eval_results", "v3")
EXCLUDE_SCENARIO = "emotional_comfort"

def mean_std(values):
    if not values:
        return 0.0, 0.0
    m = sum(values) / len(values)
    if len(values) < 2:
        return m, 0.0
    var = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return m, math.sqrt(var)

def cliffs_delta(x, y):
    """Cliff's delta effect size."""
    n = 0
    d = 0
    for xi in x:
        for yi in y:
            if xi > yi:
                d += 1
            elif xi < yi:
                d -= 1
            n += 1
    return d / n if n > 0 else 0.0

def main():
    # Load MiniMax results
    results = defaultdict(lambda: defaultdict(list))
    # results[scenario][method] = [runs]

    pattern = os.path.join(RESULTS_DIR, "MiniMax-M2.5_*.json")
    for path in sorted(glob.glob(pattern)):
        basename = os.path.basename(path)
        if basename.startswith("_") or "stats_" in basename:
            continue
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        meta = data.get("meta", {})
        scenario = meta.get("scenario", "unknown")
        method = meta.get("method", "unknown")
        results[scenario][method].append(data)

    print(f"MiniMax-M2.5 results loaded:")
    for scenario in sorted(results.keys()):
        methods = {m: len(r) for m, r in results[scenario].items()}
        excluded = " *** EXCLUDED ***" if scenario == EXCLUDE_SCENARIO else ""
        print(f"  {scenario}: {methods}{excluded}")

    # Filter out emotional_comfort
    filtered = {s: m for s, m in results.items() if s != EXCLUDE_SCENARIO}

    print(f"\nAfter excluding '{EXCLUDE_SCENARIO}':")
    print(f"  Remaining scenarios: {sorted(filtered.keys())}")

    # Aggregate metrics for BP and TPE-Full
    KEY_METRICS = ['pcs', 'emotional_variance', 'distinct_2', 'cross_rep_3', 'rlhf_collapse_index']
    DISPLAY_NAMES = {
        'pcs': 'PCS',
        'emotional_variance': 'EmotVar',
        'distinct_2': 'Distinct-2',
        'cross_rep_3': 'Cross-Rep-3',
        'rlhf_collapse_index': 'RLHF-CI',
    }
    HIGHER_BETTER = {'pcs', 'emotional_variance', 'distinct_2'}

    bp_metrics = defaultdict(list)
    v8_metrics = defaultdict(list)

    for scenario in filtered:
        for run in filtered[scenario].get('baseline_prompt', []):
            for k in KEY_METRICS:
                v = run.get("metrics", {}).get(k)
                if v is not None and isinstance(v, (int, float)):
                    bp_metrics[k].append(v)

        for run in filtered[scenario].get('v8_full', []):
            for k in KEY_METRICS:
                v = run.get("metrics", {}).get(k)
                if v is not None and isinstance(v, (int, float)):
                    v8_metrics[k].append(v)

    print(f"\n{'='*70}")
    print(f"  MiniMax-M2.5 — Excluding emotional_comfort")
    print(f"  BP runs: {len(bp_metrics.get('pcs', []))}, TPE-Full runs: {len(v8_metrics.get('pcs', []))}")
    print(f"{'='*70}")

    print(f"\n{'Metric':<15} {'BP':>12} {'TPE-Full':>12} {'Δ':>10} {'Cliff d':>10}")
    print(f"{'-'*60}")

    latex_rows = []

    for metric in KEY_METRICS:
        bp_vals = bp_metrics[metric]
        v8_vals = v8_metrics[metric]

        bp_m, bp_s = mean_std(bp_vals)
        v8_m, v8_s = mean_std(v8_vals)
        delta = v8_m - bp_m

        cd = cliffs_delta(v8_vals, bp_vals) if bp_vals and v8_vals else 0.0

        name = DISPLAY_NAMES[metric]
        direction = "↑" if metric in HIGHER_BETTER else "↓"

        print(f"{name:<15} {bp_m:>8.3f}±{bp_s:.3f} {v8_m:>8.3f}±{v8_s:.3f} {delta:>+8.3f} {cd:>+8.3f}")

        # Format for LaTeX
        delta_str = f"+{delta:.3f}" if delta >= 0 else f"$-${abs(delta):.3f}"
        latex_rows.append(f"{name} ${direction}$ & {bp_m:.3f} & {v8_m:.3f} & {delta_str} \\\\")

    print(f"\n{'='*70}")
    print(f"\nLaTeX table rows (copy-paste into appendix.tex):")
    print(f"{'='*70}")
    for row in latex_rows:
        print(row)

    # Also compute overall Cliff's delta
    print(f"\nOverall Cliff's delta magnitude: ", end="")
    all_cd = []
    for metric in KEY_METRICS:
        bp_vals = bp_metrics[metric]
        v8_vals = v8_metrics[metric]
        if bp_vals and v8_vals:
            cd = abs(cliffs_delta(v8_vals, bp_vals))
            all_cd.append(cd)
    if all_cd:
        avg_cd = sum(all_cd) / len(all_cd)
        print(f"avg |d| = {avg_cd:.3f}")

if __name__ == '__main__':
    main()
