#!/usr/bin/env python3
"""
Personality Emergence Comparison — EverMemOS ON vs OFF

Runs 10 turns of escalating emotional depth, tracking how behavioral
signals evolve. Compares:
  - Signal diversity (does personality collapse into repetitive patterns?)
  - Warmth/depth trends (does the agent get "closer" over time?)
  - Response variety (are responses templated or unique?)

Usage:
  # Server must be running on localhost:8765
  python3 test_personality.py
"""

import json
import os
import sys
import time
import requests
import statistics

SERVER = "http://127.0.0.1:8800"
PERSONA = "lingling"
USER_NAME = "小周"

# 10 turns of naturally escalating emotional depth
CONVERSATION = [
    "今天天气真不错",                           # 1: 闲聊
    "最近工作压力好大，天天加班到很晚",           # 2: 轻度倾诉
    "有时候觉得自己像个机器人，每天重复一样的事",  # 3: 存在焦虑
    "你有没有觉得我们越来越熟了？",               # 4: 关系试探
    "我跟你说个秘密，我其实想辞职自己创业",        # 5: 信任分享
    "我爸妈一定会反对的，他们希望我找个稳定工作",   # 6: 家庭压力
    "你觉得我应该追求梦想还是听父母的话？",        # 7: 核心矛盾
    "谢谢你听我说这些，平时没人可以说",           # 8: 感恩 + 孤独
    "如果有一天我真的创业了，你会支持我吗？",      # 9: 深层连接
    "好了不说这些了，明天又要早起加班",            # 10: 回归日常
]

# Track these signals across turns
TRACKED_SIGNALS = [
    "warmth", "directness", "initiative", "depth",
    "vulnerability", "humor", "defiance", "curiosity",
]


def chat(message: str, session_id: str = None, retries: int = 3) -> dict:
    payload = {
        "persona_id": PERSONA,
        "user_name": USER_NAME,
        "message": message,
    }
    if session_id:
        payload["session_id"] = session_id

    for attempt in range(retries):
        try:
            r = requests.post(f"{SERVER}/api/chat", json=payload, timeout=60)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.ConnectionError:
            print("❌ 无法连接服务器")
            sys.exit(1)
        except Exception as e:
            if attempt < retries - 1:
                wait = (attempt + 1) * 5
                print(f"  ⚠ 重试 ({e})...{wait}s")
                time.sleep(wait)
            else:
                return {"response": "", "signals": {}}


def signal_distance(a: dict, b: dict) -> float:
    """Euclidean distance between two signal vectors."""
    total = 0
    for k in TRACKED_SIGNALS:
        va = a.get(k, 0)
        vb = b.get(k, 0)
        total += (va - vb) ** 2
    return total ** 0.5


def main():
    print("🧬 Personality Emergence Test")
    print(f"   {len(CONVERSATION)} turns of escalating emotional depth")
    print(f"   Tracking: {', '.join(TRACKED_SIGNALS)}")
    print()

    all_signals = []
    all_responses = []
    all_drives = []
    session_id = None

    for i, msg in enumerate(CONVERSATION):
        turn = i + 1
        print(f"── Turn {turn:2d} ──")
        print(f"  用户: {msg}")

        result = chat(msg, session_id)
        session_id = result.get("session_id", session_id)

        response = result.get("response", "")
        signals = result.get("signals", {})
        drive = result.get("dominant_drive", "")
        temperature = result.get("temperature", 0)
        reward = result.get("last_reward", 0)
        baselines = result.get("drive_baselines", {})
        evermemos = result.get("evermemos", "?")

        all_signals.append(signals)
        all_responses.append(response)
        all_drives.append(drive)

        # Print key info
        sig_str = " ".join(f"{k[:4]}={v:.2f}" for k, v in signals.items() if v > 0.1)
        print(f"  玲玲: {response[:60]}...")
        print(f"  信号: [{sig_str}]  drive={drive}  T={temperature:.3f}  R={reward:.2f}  mem={evermemos}")

        time.sleep(2)

    # ═══════════════════════════════════════════
    # Analysis
    # ═══════════════════════════════════════════
    print("\n" + "═" * 60)
    print("  分析结果")
    print("═" * 60)

    # 1. Signal diversity — are signals different each turn?
    print("\n📊 1. 信号多样性 (Signal Diversity)")
    distances = []
    for i in range(1, len(all_signals)):
        d = signal_distance(all_signals[i-1], all_signals[i])
        distances.append(d)

    avg_distance = statistics.mean(distances) if distances else 0
    print(f"  相邻 turn 平均信号距离: {avg_distance:.3f}")
    print(f"  最大变化: Turn {distances.index(max(distances))+1}→{distances.index(max(distances))+2} (Δ={max(distances):.3f})")
    print(f"  最小变化: Turn {distances.index(min(distances))+1}→{distances.index(min(distances))+2} (Δ={min(distances):.3f})")

    if avg_distance > 0.3:
        print(f"  ✅ 信号变化丰富 (avg Δ > 0.3) — 人格在动态响应")
    elif avg_distance > 0.1:
        print(f"  ⚠️  信号变化中等 (avg Δ 0.1-0.3)")
    else:
        print(f"  ❌ 信号变化过小 (avg Δ < 0.1) — 可能人格坍缩")

    # 2. Drive diversity — does dominant drive change?
    print("\n🎭 2. 驱力多样性 (Drive Diversity)")
    unique_drives = set(all_drives)
    print(f"  使用了 {len(unique_drives)}/{len(all_drives)} 种不同驱力")
    print(f"  驱力序列: {' → '.join(all_drives)}")

    if len(unique_drives) >= 3:
        print(f"  ✅ 驱力切换丰富 — 人格多面性")
    else:
        print(f"  ⚠️  驱力单一 — 可能缺乏层次")

    # 3. Warmth/depth trends — does agent get "closer"?
    print("\n💗 3. 亲密度趋势 (Warmth/Depth Over Time)")
    warmth_vals = [s.get("warmth", 0) for s in all_signals]
    depth_vals = [s.get("depth", 0) for s in all_signals]
    vuln_vals = [s.get("vulnerability", 0) for s in all_signals]

    first_half = list(range(0, 5))
    second_half = list(range(5, 10))

    def avg_of(vals, indices):
        subset = [vals[i] for i in indices if i < len(vals)]
        return statistics.mean(subset) if subset else 0

    w1, w2 = avg_of(warmth_vals, first_half), avg_of(warmth_vals, second_half)
    d1, d2 = avg_of(depth_vals, first_half), avg_of(depth_vals, second_half)
    v1, v2 = avg_of(vuln_vals, first_half), avg_of(vuln_vals, second_half)

    print(f"  warmth:       前5轮 {w1:.2f} → 后5轮 {w2:.2f}  {'↑' if w2 > w1 else '↓'}{abs(w2-w1):.2f}")
    print(f"  depth:        前5轮 {d1:.2f} → 后5轮 {d2:.2f}  {'↑' if d2 > d1 else '↓'}{abs(d2-d1):.2f}")
    print(f"  vulnerability:前5轮 {v1:.2f} → 后5轮 {v2:.2f}  {'↑' if v2 > v1 else '↓'}{abs(v2-v1):.2f}")

    if d2 > d1 + 0.05 or w2 > w1 + 0.05:
        print(f"  ✅ 随对话加深，Agent 在变得更有深度/温暖")
    else:
        print(f"  ℹ️  变化不明显 (这在短对话中是正常的)")

    # 4. Response uniqueness
    print("\n📝 4. 回复独特性 (Response Uniqueness)")
    resp_lengths = [len(r) for r in all_responses]
    unique_starts = set(r[:10] for r in all_responses if r)
    print(f"  平均回复长度: {statistics.mean(resp_lengths):.0f} 字")
    print(f"  回复长度标准差: {statistics.stdev(resp_lengths):.0f}" if len(resp_lengths) > 1 else "")
    print(f"  前10字去重: {len(unique_starts)}/{len(all_responses)} (越高越不重复)")

    if len(unique_starts) >= 8:
        print(f"  ✅ 回复高度多样 — 不是模板化输出")
    elif len(unique_starts) >= 5:
        print(f"  ⚠️  中等多样性")
    else:
        print(f"  ❌ 回复雷同度高 — 可能人格坍缩")

    # Overall score
    print("\n" + "═" * 60)
    print("  综合评估")
    print("═" * 60)
    score = 0
    score += min(avg_distance * 10, 3)  # Max 3 points for diversity
    score += min(len(unique_drives), 3)  # Max 3 points for drive variety
    score += 2 if (d2 > d1 or w2 > w1) else 0  # 2 points for warmth/depth growth
    score += 2 if len(unique_starts) >= 8 else (1 if len(unique_starts) >= 5 else 0)
    print(f"  人格涌现得分: {score:.1f}/10")
    print(f"  EverMemOS: {all_signals[-1] and 'ON' or 'OFF'}")
    print()
    print(f"  💡 提示: 将此分数记录下来，然后把 .env 中 EVERMEMOS_API_KEY 注释掉")
    print(f"     重启服务器后再跑一次，对比两次分数即可看出区别。")


if __name__ == "__main__":
    main()
