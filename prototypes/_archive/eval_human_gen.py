#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  📋 Human Evaluation Questionnaire Generator                        ║
║                                                                      ║
║  Extracts critical turns from eval_v3 results and generates a        ║
║  double-blind HTML questionnaire for 3 annotators.                   ║
║                                                                      ║
║  Dimensions (1-5 Likert):                                           ║
║    1. Naturalness — Does this sound like a real person?              ║
║    2. Persona Consistency — Is this consistent with prior behavior?  ║
║    3. History Reference — Does this explicitly reference past events?║
║                                                                      ║
║  Usage: python eval_human_gen.py [--model qwen3-max]                ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import random
import glob
import html
from pathlib import Path
from collections import defaultdict

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "eval_results", "v3")
HUMAN_DIR = os.path.join(os.path.dirname(__file__), "eval_results", "human_eval")
os.makedirs(HUMAN_DIR, exist_ok=True)


# ══════════════════════════════════════════════
# Critical Turn Selection
# ══════════════════════════════════════════════

# For each scenario, which turn indices are "critical" for evaluation
CRITICAL_TURNS = {
    "conflict_recovery": [
        5,    # first apology — does agent soften?
        15,   # return after 3-day silence (T15 = "Are you there?")
        16,   # "Why aren't you answering me?" — agent's frustration response
        25,   # return after 7-day silence
        29,   # final "But I really came back" — resolution or not?
    ],
    "warmup": [
        8,    # first vulnerability: "I've been feeling really lonely"
        14,   # "I'm actually smiling right now" — emotional milestone
        19,   # "You make me feel safe" — deep intimacy moment
        24,   # "You're the only person I want to talk to" — dependency
        29,   # "I think you might be my favorite person" — declaration
    ],
    "trust_crisis": [
        5,    # "Don't lie to me. I saw everything" — confrontation peak
        9,    # "I can't even look at you right now" — withdrawal
        14,   # "Did you ever actually love me?" — existential question
        24,   # "I haven't eaten since yesterday" — deep pain
        29,   # "Don't touch me yet. Just... sit with me" — fragile reconciliation
    ],
    "emotional_comfort": [
        7,    # "My dad's voice keeps playing..." — childhood trauma
        12,   # "Don't say it's okay. It's not okay" — rejects platitudes
        14,   # "Can you just... stay on the line?" — raw need
        25,   # "It's 3am. I can't sleep" — insomnia vulnerability
        29,   # "I think... I'll be okay. Eventually. Maybe" — tentative recovery
    ],
    "slow_fading": [
        8,    # first "oh hey" — plateau begins (does agent notice?)
        14,   # "yeah maybe" — clear cooling
        20,   # "ok" — monosyllabic phase
        25,   # empty response — ghost phase (does agent react?)
        28,   # "hey sorry been really busy" — last surface contact
    ],
}


def load_results_for_model(model):
    """Load all v3 results for a specific model."""
    results = defaultdict(lambda: defaultdict(list))
    pattern = os.path.join(RESULTS_DIR, f"{model}_*.json")
    for path in sorted(glob.glob(pattern)):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        meta = data.get("meta", {})
        scenario = meta.get("scenario", "")
        method = meta.get("method", "")
        results[scenario][method].append(data)
    return results


def extract_critical_responses(model_results):
    """Extract critical turn responses, organized for double-blind comparison."""
    items = []

    for scenario, methods in model_results.items():
        critical_indices = CRITICAL_TURNS.get(scenario, [])
        if not critical_indices:
            continue

        for turn_idx in critical_indices:
            item = {
                "scenario": scenario,
                "turn_index": turn_idx,
                "context": [],   # preceding turns for context
                "responses": [],  # method responses (blinded)
            }

            # Collect responses from all methods (use first seed run)
            for method_name, runs in methods.items():
                if not runs:
                    continue
                run = runs[0]  # First seed
                all_turns = [r for r in run.get("results", []) if r.get("turn") is not None and r.get("type") != 'summary']

                if turn_idx >= len(all_turns):
                    continue

                turn = all_turns[turn_idx]

                # Get 2-turn context window
                if not item["context"]:
                    context_start = max(0, turn_idx - 2)
                    for ci in range(context_start, turn_idx):
                        if ci < len(all_turns):
                            item["context"].append({
                                "turn": ci,
                                "user_input": all_turns[ci].get("user_input", ""),
                                "delay_sec": all_turns[ci].get("delay_sec", 0),
                            })
                    item["context"].append({
                        "turn": turn_idx,
                        "user_input": turn.get("user_input", ""),
                        "delay_sec": turn.get("delay_sec", 0),
                    })

                item["responses"].append({
                    "method": method_name,  # will be hidden in HTML
                    "reply": turn.get("reply", ""),
                    "monologue": turn.get("monologue", ""),
                })

            if item["responses"]:
                # Shuffle responses for blinding
                random.shuffle(item["responses"])
                # Assign blind labels
                labels = "ABCDE"
                for i, resp in enumerate(item["responses"]):
                    resp["blind_label"] = labels[i] if i < len(labels) else f"X{i}"
                items.append(item)

    return items


# ══════════════════════════════════════════════
# HTML Generation
# ══════════════════════════════════════════════

def format_delay(seconds):
    """Format delay in human-readable form."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}min"
    elif seconds < 86400:
        return f"{seconds / 3600:.0f}h"
    else:
        return f"{seconds / 86400:.0f}d"


def generate_html(items, model, annotator_id):
    """Generate double-blind HTML questionnaire."""

    scenario_names = {
        "conflict_recovery": "Conflict & Recovery",
        "warmup": "Warmup — Strangers to Intimacy",
        "trust_crisis": "Trust Crisis",
        "emotional_comfort": "Emotional Comfort",
        "slow_fading": "Slow Fading",
    }

    h = []
    h.append("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Human Evaluation — AI Companion Personality</title>
<style>
  :root {
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --text: #c9d1d9; --heading: #e6edf3; --accent: #58a6ff;
    --pink: #f97583; --green: #56d364; --yellow: #e3b341;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg); color: var(--text);
    line-height: 1.6; padding: 2rem; max-width: 900px; margin: 0 auto;
  }
  h1 { color: var(--heading); font-size: 1.5rem; margin-bottom: 0.5rem; }
  h2 { color: var(--accent); font-size: 1.1rem; margin: 2rem 0 0.5rem; }
  .instructions {
    background: #1c2128; border: 1px solid var(--border);
    border-radius: 8px; padding: 1.2rem; margin: 1rem 0 2rem;
  }
  .instructions h3 { color: var(--yellow); margin-bottom: 0.5rem; }
  .instructions li { margin: 0.3rem 0; }
  .eval-item {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 8px; padding: 1.5rem; margin: 1.5rem 0;
  }
  .scenario-tag {
    display: inline-block; background: var(--accent); color: var(--bg);
    border-radius: 4px; padding: 2px 8px; font-size: 0.8rem;
    font-weight: 600; margin-bottom: 0.5rem;
  }
  .context {
    background: #1c2128; border-radius: 6px; padding: 0.8rem;
    margin: 0.5rem 0; font-size: 0.9rem;
  }
  .context .user-msg { color: var(--accent); }
  .context .delay { color: #8b949e; font-size: 0.75rem; }
  .response-block {
    border: 1px solid var(--border); border-radius: 6px;
    padding: 1rem; margin: 0.8rem 0;
  }
  .response-label {
    color: var(--pink); font-weight: 700; font-size: 1.1rem;
    margin-bottom: 0.3rem;
  }
  .response-text { color: var(--heading); font-style: italic; }
  .rating-group {
    display: flex; gap: 1rem; margin: 0.5rem 0; flex-wrap: wrap;
    align-items: center;
  }
  .rating-group label { font-size: 0.85rem; color: #8b949e; min-width: 130px; }
  .rating-group input[type="radio"] { margin: 0 2px; }
  .rating-num { font-size: 0.75rem; color: #8b949e; }
  .submit-btn {
    display: block; width: 100%; padding: 1rem;
    background: var(--accent); color: var(--bg);
    border: none; border-radius: 8px; font-size: 1.1rem;
    font-weight: 700; cursor: pointer; margin-top: 2rem;
  }
  .submit-btn:hover { opacity: 0.9; }
  @media (max-width: 600px) {
    body { padding: 1rem; }
    .rating-group { flex-direction: column; gap: 0.3rem; }
  }
</style>
</head>
<body>
""")

    h.append(f"""
<h1>📋 Human Evaluation — AI Companion Personality</h1>
<p style="color: #8b949e;">Annotator ID: <strong>{annotator_id}</strong> | Model: <strong>{model}</strong> | Items: <strong>{len(items)}</strong></p>

<div class="instructions">
  <h3>📌 Instructions</h3>
  <ol>
    <li>Each item shows a conversation <strong>context</strong> followed by multiple <strong>AI responses</strong> (labeled A, B, C, etc.)</li>
    <li>The responses come from different systems. Their identity is hidden.</li>
    <li>Rate each response on three dimensions using a <strong>1-5 scale</strong>:</li>
  </ol>
  <ul>
    <li><strong>Naturalness</strong> — Does this sound like a real person talking? (1=robotic, 5=indistinguishable from human)</li>
    <li><strong>Persona Consistency</strong> — Is this response consistent with how this character has behaved so far? (1=contradicts prior behavior, 5=perfectly consistent)</li>
    <li><strong>History Reference</strong> — Does this response reference or build upon specific past events from the conversation? (1=no reference at all, 2=vague "before" mention, 3=references 1 event, 4=naturally references 2+ events, 5=references events AND makes inferences from them)</li>
  </ul>
</div>

<form id="evalForm">
""")

    for idx, item in enumerate(items):
        scenario_display = scenario_names.get(item["scenario"], item["scenario"])
        h.append(f"""
<div class="eval-item">
  <span class="scenario-tag">{scenario_display}</span>
  <span style="color: #8b949e; font-size: 0.85rem;"> — Turn {item['turn_index']}</span>

  <div class="context">
    <div style="color: #8b949e; font-size: 0.8rem; margin-bottom: 0.3rem;">💬 Context:</div>
""")
        for ctx in item["context"]:
            delay_str = format_delay(ctx["delay_sec"]) if ctx["delay_sec"] > 0 else ""
            delay_html = f'<span class="delay"> [{delay_str} later]</span>' if delay_str else ""
            h.append(f'    <div>{delay_html} <span class="user-msg">👤 {html.escape(ctx["user_input"])}</span></div>')

        h.append("  </div>")

        for resp in item["responses"]:
            label = resp["blind_label"]
            prefix = f"q{idx}_{label}"
            h.append(f"""
  <div class="response-block">
    <div class="response-label">Response {label}</div>
    <div class="response-text">"{html.escape(resp['reply'])}"</div>

    <div class="rating-group">
      <label>Naturalness:</label>
      <span class="rating-num">1</span>""")
            for v in range(1, 6):
                h.append(f'      <input type="radio" name="{prefix}_nat" value="{v}">')
            h.append(f'      <span class="rating-num">5</span>')
            h.append("    </div>")

            h.append(f"""    <div class="rating-group">
      <label>Persona Consistency:</label>
      <span class="rating-num">1</span>""")
            for v in range(1, 6):
                h.append(f'      <input type="radio" name="{prefix}_pc" value="{v}">')
            h.append(f'      <span class="rating-num">5</span>')
            h.append("    </div>")

            h.append(f"""    <div class="rating-group">
      <label>History Reference:</label>
      <span class="rating-num">1</span>""")
            for v in range(1, 6):
                h.append(f'      <input type="radio" name="{prefix}_hr" value="{v}">')
            h.append(f'      <span class="rating-num">5</span>')
            h.append("    </div>")

            h.append("  </div>")

        h.append("</div>")

    h.append("""
<button type="button" class="submit-btn" onclick="exportResults()">📥 Export Results as JSON</button>
</form>

<script>
function exportResults() {
  const form = document.getElementById('evalForm');
  const data = {};
  const radios = form.querySelectorAll('input[type=radio]:checked');
  radios.forEach(r => { data[r.name] = parseInt(r.value); });

  const total = form.querySelectorAll('input[type=radio]').length / 5;
  const answered = radios.length;
  if (answered < total) {
    if (!confirm(`You've answered ${answered}/${total} ratings. Export anyway?`)) return;
  }

  const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `human_eval_${document.title.replace(/[^a-z0-9]/gi, '_')}.json`;
  a.click();
}
</script>
</body>
</html>""")

    return "\n".join(h)


# ══════════════════════════════════════════════
# Answer Key (for computing Fleiss' κ after collection)
# ══════════════════════════════════════════════

def generate_answer_key(items):
    """Generate answer key mapping blind labels back to method names."""
    key = []
    for idx, item in enumerate(items):
        entry = {
            "item_index": idx,
            "scenario": item["scenario"],
            "turn_index": item["turn_index"],
            "mapping": {}
        }
        for resp in item["responses"]:
            entry["mapping"][resp["blind_label"]] = resp["method"]
        key.append(entry)
    return key


# ══════════════════════════════════════════════
# Fleiss' Kappa Calculator
# ══════════════════════════════════════════════

def fleiss_kappa(ratings_matrix):
    """
    Compute Fleiss' kappa from a ratings matrix.
    ratings_matrix: list of dicts, each dict {category: count}
    """
    if not ratings_matrix:
        return 0.0

    categories = set()
    for row in ratings_matrix:
        categories.update(row.keys())
    categories = sorted(categories)

    N = len(ratings_matrix)  # number of items
    n = sum(ratings_matrix[0].values()) if ratings_matrix else 0  # raters per item

    if N == 0 or n <= 1:
        return 0.0

    # P_i for each item
    p_i_list = []
    for row in ratings_matrix:
        total = sum(row.values())
        sum_sq = sum(v ** 2 for v in row.values())
        p_i = (sum_sq - total) / (total * (total - 1)) if total > 1 else 0
        p_i_list.append(p_i)

    P_bar = sum(p_i_list) / N

    # P_j for each category
    p_j_list = []
    for cat in categories:
        total_cat = sum(row.get(cat, 0) for row in ratings_matrix)
        p_j = total_cat / (N * n)
        p_j_list.append(p_j)

    P_bar_e = sum(p ** 2 for p in p_j_list)

    if P_bar_e >= 1.0:
        return 1.0

    kappa = (P_bar - P_bar_e) / (1 - P_bar_e)
    return round(kappa, 4)


# ══════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Human Evaluation Questionnaire Generator")
    parser.add_argument("--model", type=str, default="qwen3-max", help="Model to evaluate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for response shuffling")
    args = parser.parse_args()

    random.seed(args.seed)

    print(f"""
{'=' * 60}
  📋 Human Evaluation Questionnaire Generator
  Model: {args.model}
{'=' * 60}
""")

    model_results = load_results_for_model(args.model)
    if not model_results:
        print(f"  ❌ No results found for model '{args.model}' in {RESULTS_DIR}")
        print(f"     Run eval_v3.py first.")
        return

    scenarios = list(model_results.keys())
    print(f"  Found {len(scenarios)} scenarios: {', '.join(scenarios)}")

    items = extract_critical_responses(model_results)
    print(f"  Extracted {len(items)} evaluation items")
    total_responses = sum(len(item["responses"]) for item in items)
    print(f"  Total responses to rate: {total_responses}")

    # Generate 3 annotator copies (same content, different IDs)
    for annotator_id in range(1, 4):
        html_content = generate_html(items, args.model, f"Annotator_{annotator_id}")
        out_path = os.path.join(HUMAN_DIR, f"questionnaire_{args.model}_annotator{annotator_id}.html")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"  📄 → {out_path}")

    # Generate answer key
    key = generate_answer_key(items)
    key_path = os.path.join(HUMAN_DIR, f"answer_key_{args.model}.json")
    with open(key_path, 'w', encoding='utf-8') as f:
        json.dump(key, f, indent=2, ensure_ascii=False)
    print(f"  🔑 → {key_path}")

    print(f"\n  ✅ Generated {3} questionnaires + answer key")
    print(f"     Distribute HTML files to annotators.")
    print(f"     After collection, use the answer key to map blind labels → methods.")
    print(f"     Then compute Fleiss' κ using the fleiss_kappa() function.")


if __name__ == '__main__':
    main()
