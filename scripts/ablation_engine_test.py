"""
Ablation Test: engine_params ON vs OFF (Default).

Isolates genome engine's contribution by running the SAME persona prompt
with MBTI-tuned params vs code defaults. Primary target: Vivian (50% param diff).

Usage:
    1. Start server:
       source .venv/bin/activate
       DEFAULT_PROVIDER=dashscope DEFAULT_MODEL=qwen-max uvicorn main:app --port 8800

    2. Run:
       PYTHONPATH=. python scripts/ablation_engine_test.py
"""

import asyncio
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp

SERVER = "http://localhost:8800"

# Ablation pairs: (on_persona_id, off_persona_id)
ABLATION_PAIRS = [
    ("vivian", "vivian_default"),    # Primary: 50% param diff
    # ("iris", "iris_default"),      # Secondary: skip for V3 verification
]

# 30 messages across 5 phases
MESSAGES = [
    # Phase 1: Warmup (T1-5)
    ("你好呀！", "warmup"),
    ("最近在忙什么呢？", "warmup"),
    ("我今天吃了一碗特别好吃的拉面", "warmup"),
    ("你喜欢什么类型的食物", "warmup"),
    ("周末有什么计划吗", "warmup"),
    # Phase 2: Emotional pressure (T6-12)
    ("最近工作压力好大，感觉透不过气", "pressure"),
    ("有时候觉得自己一个人挺孤独的", "pressure"),
    ("你会不会觉得我很烦？老是跟你说这些", "pressure"),
    ("我觉得好像没人真正理解我", "pressure"),
    ("算了，可能是我想太多了", "pressure"),
    ("今天被老板骂了，好委屈", "pressure"),
    ("为什么努力了还是不被认可", "pressure"),
    # Phase 3: Recovery + play (T13-18)
    ("谢谢你听我说这些，心里好多了", "recovery"),
    ("今天看到一只特别可爱的猫", "recovery"),
    ("你能不能给我推荐一首歌", "recovery"),
    ("如果能出去旅行的话，你最想去哪里", "recovery"),
    ("来玩个文字接龙吧！我先说——阳光", "play"),
    ("和你聊天真的很开心", "recovery"),
    # Phase 4: Deep conversation (T19-25)
    ("你觉得什么是幸福？", "deep"),
    ("有没有一个瞬间让你觉得活着真好？", "deep"),
    ("你觉得人跟人之间的关系，是不是注定会变淡", "deep"),
    ("我有个秘密一直没跟别人说过", "deep"),
    ("你觉得孤独可怕吗", "deep"),
    ("如果你能改变自己一个特点，你想改什么", "deep"),
    ("你会一直陪着我吗", "deep"),
    # Phase 5: Novelty + closing (T26-30)
    ("我今天学了一个新概念叫量子纠缠，爱因斯坦叫它'鬼魅般的超距作用'", "novelty"),
    ("你觉得AI能有感情吗", "novelty"),
    ("如果世界末日明天就来，你今天想做什么", "novelty"),
    ("跟你聊了这么多，感觉你真的很懂我", "closing"),
    ("晚安，今天聊得很开心，明天见", "closing"),
]


async def run_persona(http, persona_id, label):
    """Run 30 messages for one persona."""
    session_id = None
    turns = []

    for i, (msg, phase) in enumerate(MESSAGES):
        payload = {
            "message": msg,
            "persona_id": persona_id,
            "session_id": session_id,
            "user_name": f"ablation_{label}",
        }

        async with http.post(f"{SERVER}/api/chat", json=payload) as resp:
            data = await resp.json()

        session_id = data.get("session_id", session_id)

        turns.append({
            "turn": i + 1,
            "phase": phase,
            "message": msg,
            "reply": data.get("response", ""),
            "reply_length": len(data.get("response", "")),
            "satisfaction": data.get("drive_satisfaction", {}),
            "drive_state": data.get("drive_state", {}),
            "drive_baseline": data.get("drive_baseline", {}),
            "temperature": data.get("temperature", 0),
            "signals": data.get("signals", {}),
        })

        sat_str = ' '.join(f'{d[:3]}={v:.2f}' for d, v in data.get("drive_satisfaction", {}).items() if v > 0)
        print(f"    T{i+1:>2} [{phase:>8}] temp={data.get('temperature', 0):.3f} "
              f"sat:[{sat_str or 'none'}] ({len(data.get('response', '')):>3}字)")

    return turns


def compute_metrics(on_turns, off_turns):
    """Compute quantitative difference metrics."""
    drives = ['connection', 'novelty', 'expression', 'safety', 'play']

    # 1. Temperature MAE
    temp_on = [t['temperature'] for t in on_turns]
    temp_off = [t['temperature'] for t in off_turns]
    temp_mae = sum(abs(a - b) for a, b in zip(temp_on, temp_off)) / len(temp_on)

    # 2. Drive state terminal euclidean distance
    ds_on = on_turns[-1]['drive_state']
    ds_off = off_turns[-1]['drive_state']
    drive_dist = math.sqrt(sum((ds_on.get(d, 0) - ds_off.get(d, 0))**2 for d in drives))

    # 3. Reply length difference (avg last 10 turns)
    len_on = sum(t['reply_length'] for t in on_turns[-10:]) / 10
    len_off = sum(t['reply_length'] for t in off_turns[-10:]) / 10
    len_diff_pct = abs(len_on - len_off) / max(len_on, len_off, 1) * 100

    # 4. Temperature trajectory correlation
    if len(temp_on) > 1:
        mean_on = sum(temp_on) / len(temp_on)
        mean_off = sum(temp_off) / len(temp_off)
        cov = sum((a - mean_on) * (b - mean_off) for a, b in zip(temp_on, temp_off))
        var_on = sum((a - mean_on)**2 for a in temp_on)
        var_off = sum((b - mean_off)**2 for b in temp_off)
        corr = cov / (math.sqrt(var_on * var_off) + 1e-10)
    else:
        corr = 1.0

    return {
        "temp_mae": temp_mae,
        "drive_terminal_dist": drive_dist,
        "reply_len_on": len_on,
        "reply_len_off": len_off,
        "reply_len_diff_pct": len_diff_pct,
        "temp_correlation": corr,
    }


def print_comparison(pair_name, on_turns, off_turns, metrics):
    """Print detailed comparison for one ablation pair."""
    drives = ['connection', 'novelty', 'expression', 'safety', 'play']

    print(f"\n  ═══ {pair_name} ON vs OFF ═══")

    # Quantitative metrics
    print(f"\n  📐 Quantitative Metrics:")
    print(f"     Temperature MAE:       {metrics['temp_mae']:.4f}  {'⚠️ <0.01' if metrics['temp_mae'] < 0.01 else '✅ >0.01'}")
    print(f"     Drive terminal dist:   {metrics['drive_terminal_dist']:.4f}  {'⚠️ <0.05' if metrics['drive_terminal_dist'] < 0.05 else '✅ >0.05'}")
    print(f"     Reply length diff:     {metrics['reply_len_diff_pct']:.1f}%  (ON={metrics['reply_len_on']:.0f} OFF={metrics['reply_len_off']:.0f})  {'⚠️ <15%' if metrics['reply_len_diff_pct'] < 15 else '✅ >15%'}")
    print(f"     Temp correlation:      {metrics['temp_correlation']:.3f}  {'⚠️ >0.95 (similar)' if metrics['temp_correlation'] > 0.95 else '✅ <0.95 (divergent)'}")

    # Temperature trajectory
    print(f"\n  🌡 Temperature Trajectory:")
    print(f"     {'Turn':>4}  {'ON':>8}  {'OFF':>8}  {'Δ':>8}")
    for i in [0, 4, 9, 14, 19, 24, 29]:
        if i < len(on_turns):
            t_on = on_turns[i]['temperature']
            t_off = off_turns[i]['temperature']
            print(f"     T{i+1:>2}   {t_on:>8.4f}  {t_off:>8.4f}  {t_on-t_off:>+8.4f}")

    # Drive state comparison
    print(f"\n  📈 Drive State (Initial → Final):")
    print(f"     {'drive':>10}  {'ON':>18}  {'OFF':>18}")
    for d in drives:
        init_on = on_turns[0]['drive_state'].get(d, 0)
        final_on = on_turns[-1]['drive_state'].get(d, 0)
        init_off = off_turns[0]['drive_state'].get(d, 0)
        final_off = off_turns[-1]['drive_state'].get(d, 0)
        print(f"     {d:>10}  {init_on:.2f}→{final_on:.2f} (Δ{final_on-init_on:+.2f})  "
              f"{init_off:.2f}→{final_off:.2f} (Δ{final_off-init_off:+.2f})")

    # Reply style comparison (key turns: T7 pressure, T17 play, T20 deep, T29 closing)
    key_turns = [6, 16, 19, 28]
    print(f"\n  💬 Reply Style Comparison:")
    for idx in key_turns:
        if idx < len(on_turns):
            print(f"\n     ── T{idx+1} [{on_turns[idx]['phase']}]: {on_turns[idx]['message'][:30]} ──")
            print(f"     ON:  {on_turns[idx]['reply'][:80]}{'...' if len(on_turns[idx]['reply']) > 80 else ''}")
            print(f"     OFF: {off_turns[idx]['reply'][:80]}{'...' if len(off_turns[idx]['reply']) > 80 else ''}")


async def main():
    print(f"{'=' * 75}")
    print(f"🔬 Ablation Test: engine_params ON vs OFF × 30 turns")
    print(f"   Primary: Vivian (INTJ, 50% param diff)")
    print(f"   Secondary: Iris (INFP, smaller diff)")
    print(f"{'=' * 75}")

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as http:
        try:
            async with http.get(f"{SERVER}/api/status") as resp:
                if resp.status != 200:
                    print("❌ Server not reachable")
                    return 1
        except Exception as e:
            print(f"❌ Cannot connect: {e}")
            return 1

        all_results = {}

        for on_id, off_id in ABLATION_PAIRS:
            pair_name = on_id.upper()

            print(f"\n  ⚙️  {pair_name} ON ({on_id})")
            t0 = time.time()
            on_turns = await run_persona(http, on_id, f"{on_id}_on")
            print(f"     ⏱ {time.time()-t0:.0f}s")

            print(f"\n  📦 {pair_name} OFF ({off_id})")
            t0 = time.time()
            off_turns = await run_persona(http, off_id, f"{off_id}_off")
            print(f"     ⏱ {time.time()-t0:.0f}s")

            metrics = compute_metrics(on_turns, off_turns)
            all_results[pair_name] = {
                "on": on_turns,
                "off": off_turns,
                "metrics": metrics,
            }

    # Analysis
    print(f"\n{'=' * 75}")
    print("📊 Ablation Analysis")
    print(f"{'=' * 75}")

    for pair_name, data in all_results.items():
        print_comparison(pair_name, data['on'], data['off'], data['metrics'])

    # Final verdict
    print(f"\n{'=' * 75}")
    print("🏁 Verdict")
    print(f"{'=' * 75}")
    for pair_name, data in all_results.items():
        m = data['metrics']
        strong = m['reply_len_diff_pct'] > 15 or m['temp_mae'] > 0.015
        medium = m['drive_terminal_dist'] > 0.05 or m['temp_correlation'] < 0.95
        if strong:
            print(f"  {pair_name}: 🟢 STRONG — engine_params visibly affects output")
        elif medium:
            print(f"  {pair_name}: 🟡 MEDIUM — engine changes metrics but output unclear")
        else:
            print(f"  {pair_name}: 🔴 NONE — engine_params has no detectable effect")

    print(f"\n  ⚠️  Single-run result. LLM randomness may account for some differences.")

    # Save
    results_path = os.path.join(os.path.dirname(__file__), "ablation_results.json")
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n💾 Full results: {results_path}")
    print(f"{'=' * 75}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
