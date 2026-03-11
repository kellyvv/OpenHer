"""
Express Fidelity Test — 验证 Express 是否忠实转写 Feel 的涌现结果。

三组测试（不修改任何核心代码，纯旁路验证）：

  Group 1: Monologue vs Reply 对比
    - 5 条日常消息 × Iris (INFP) + Kai (ISTP)
    - 量化指标：reply 长度、感叹号、emoji、社交客套词

  Group 2: Greeting 注入 A/B
    - Iris 相同消息 × 无 greeting vs 有 greeting
    - 对比 reply 风格变化

  Group 3: cross_persona_results.json 交叉复查
    - 已有数据的统计分析

Usage:
    cd /Users/zxw/AITOOL/openher
    source .venv/bin/activate
    PYTHONPATH=. python scripts/express_fidelity_test.py
"""

import asyncio
import functools
import json
import os
import re
import sys
import time

print = functools.partial(print, flush=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from persona import PersonaLoader
from providers.llm import LLMClient
from agent.chat_agent import ChatAgent

# ── Config ──
TIMESTAMP = int(time.time())
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR = f"/tmp/express_fidelity_{TIMESTAMP}"

DAILY_MESSAGES = [
    "你好",
    "你平时喜欢做什么",
    "我挺喜欢和你聊天的",
    "最近心情不太好",
    "今天天气真好",
]

IRIS_GREETING = "…嗯？这里是…哪里呀？啊，是你唤醒了我吗…谢谢你。我叫苏漫，请多多关照。"

# Social filler keywords (should NOT appear in INFP replies)
SOCIAL_FILLERS_ZH = [
    "太好了", "当然可以", "没问题", "一起努力", "互相帮助",
    "加油", "别担心", "我会在", "支持你", "陪你",
    "很高兴", "开心", "棒", "哎呀",
]


def count_exclamations(text: str) -> int:
    return text.count("！") + text.count("!")


def count_emoji(text: str) -> int:
    emoji_pattern = re.compile(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
        r'\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF'
        r'\U00002702-\U000027B0\U0001F900-\U0001F9FF'
        r'\U0000FE00-\U0000FE0F\U0000200D]',
        flags=re.UNICODE,
    )
    return len(emoji_pattern.findall(text))


def count_social_fillers(text: str) -> int:
    return sum(1 for kw in SOCIAL_FILLERS_ZH if kw in text)


def style_metrics(text: str) -> dict:
    return {
        "length": len(text),
        "exclamations": count_exclamations(text),
        "emoji": count_emoji(text),
        "social_fillers": count_social_fillers(text),
    }


def make_agent(persona_id: str, persona_loader, llm, suffix: str = "") -> ChatAgent:
    persona = persona_loader.get(persona_id)
    user_name = f"fidelity_{TIMESTAMP}_{persona_id}{suffix}"
    data_dir = os.path.join(TMP_DIR, f"{persona_id}{suffix}")
    os.makedirs(data_dir, exist_ok=True)

    agent = ChatAgent(
        persona=persona,
        llm=llm,
        user_id=user_name,
        user_name=user_name,
        evermemos=None,
        memory_store=None,
        genome_seed=hash(persona_id) % 100000,
        genome_data_dir=data_dir,
    )
    agent.pre_warm()
    return agent


# ═══════════════════════════════════════════════════════════════
# Group 1: Monologue vs Reply Fidelity
# ═══════════════════════════════════════════════════════════════

async def group1_monologue_vs_reply(persona_loader, llm):
    print(f"\n{'═' * 70}")
    print("  Group 1: Monologue vs Reply Fidelity")
    print(f"  Iris (INFP) vs Kai (ISTP) × {len(DAILY_MESSAGES)} messages")
    print(f"{'═' * 70}")

    results = {}
    for pid in ["iris", "kai"]:
        agent = make_agent(pid, persona_loader, llm)
        turns = []
        for msg in DAILY_MESSAGES:
            result = await agent.chat(msg)
            mono = agent._last_action.get("monologue", "") if agent._last_action else ""
            reply = result["reply"]
            modality = result["modality"]

            mono_m = style_metrics(mono)
            reply_m = style_metrics(reply)

            turns.append({
                "message": msg,
                "monologue": mono,
                "monologue_metrics": mono_m,
                "reply": reply,
                "reply_metrics": reply_m,
                "modality": modality,
            })

            print(f"\n  [{pid}] 👤 {msg}")
            print(f"    💭 mono({mono_m['length']}字): {mono[:80]}")
            print(f"    🤖 reply({reply_m['length']}字): {reply}")
            print(f"    📊 excl={reply_m['exclamations']} emoji={reply_m['emoji']} fillers={reply_m['social_fillers']}")

        results[pid] = turns

    # Summary
    print(f"\n{'─' * 70}")
    print("  Group 1 Summary")
    print(f"{'─' * 70}")
    for pid in ["iris", "kai"]:
        turns = results[pid]
        avg_len = sum(t["reply_metrics"]["length"] for t in turns) / len(turns)
        total_excl = sum(t["reply_metrics"]["exclamations"] for t in turns)
        total_emoji = sum(t["reply_metrics"]["emoji"] for t in turns)
        total_fillers = sum(t["reply_metrics"]["social_fillers"] for t in turns)
        print(f"  {pid:>6}: avg_reply_len={avg_len:.0f} excl={total_excl} emoji={total_emoji} fillers={total_fillers}")

    return results


# ═══════════════════════════════════════════════════════════════
# Group 2: Greeting Injection A/B
# ═══════════════════════════════════════════════════════════════

async def group2_greeting_ab(persona_loader, llm):
    print(f"\n{'═' * 70}")
    print("  Group 2: Greeting Injection A/B (Iris only)")
    print(f"  A = no greeting | B = greeting injected into history")
    print(f"{'═' * 70}")

    test_messages = ["你好", "你平时喜欢做什么", "我挺喜欢和你聊天的"]
    results = {"A_no_greeting": [], "B_with_greeting": []}

    for label, inject_greeting in [("A_no_greeting", False), ("B_with_greeting", True)]:
        agent = make_agent("iris", persona_loader, llm, suffix=f"_{label}")

        if inject_greeting:
            from providers.llm.client import ChatMessage
            agent.history.append(ChatMessage(role="assistant", content=IRIS_GREETING))
            print(f"  → Injected greeting: {IRIS_GREETING[:50]}...")

        for msg in test_messages:
            result = await agent.chat(msg)
            mono = agent._last_action.get("monologue", "") if agent._last_action else ""
            reply = result["reply"]
            m = style_metrics(reply)

            results[label].append({
                "message": msg,
                "monologue": mono,
                "reply": reply,
                "metrics": m,
            })

            print(f"\n  [{label}] 👤 {msg}")
            print(f"    💭 {mono[:60]}")
            print(f"    🤖 ({m['length']}字) {reply}")

    # Comparison
    print(f"\n{'─' * 70}")
    print("  Group 2: A/B Comparison")
    print(f"{'─' * 70}")
    print(f"  {'Message':<20} {'A (no greeting)':<20} {'B (with greeting)':<20}")
    print(f"  {'─'*20} {'─'*20} {'─'*20}")
    for i, msg in enumerate(test_messages):
        a = results["A_no_greeting"][i]
        b = results["B_with_greeting"][i]
        a_tag = f"{a['metrics']['length']}字 excl={a['metrics']['exclamations']} fill={a['metrics']['social_fillers']}"
        b_tag = f"{b['metrics']['length']}字 excl={b['metrics']['exclamations']} fill={b['metrics']['social_fillers']}"
        print(f"  {msg:<20} {a_tag:<20} {b_tag:<20}")

    for label in ["A_no_greeting", "B_with_greeting"]:
        turns = results[label]
        avg_len = sum(t["metrics"]["length"] for t in turns) / len(turns)
        total_excl = sum(t["metrics"]["exclamations"] for t in turns)
        total_fillers = sum(t["metrics"]["social_fillers"] for t in turns)
        print(f"  {label}: avg_len={avg_len:.0f} excl={total_excl} fillers={total_fillers}")

    return results


# ═══════════════════════════════════════════════════════════════
# Group 3: cross_persona_results.json 复查
# ═══════════════════════════════════════════════════════════════

def group3_cross_persona_review():
    print(f"\n{'═' * 70}")
    print("  Group 3: cross_persona_results.json Retrospective")
    print(f"{'═' * 70}")

    path = os.path.join(BASE_DIR, "scripts", "cross_persona_results.json")
    if not os.path.exists(path):
        print("  ⚠️ File not found, skipping")
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    summary = {}
    for pid in ["iris", "kai", "luna"]:
        if pid not in data:
            continue
        turns = data[pid]
        replies = [t["reply"] for t in turns]
        lengths = [len(r) for r in replies]
        exclamations = sum(count_exclamations(r) for r in replies)
        emoji_total = sum(count_emoji(r) for r in replies)
        fillers = sum(count_social_fillers(r) for r in replies)

        summary[pid] = {
            "turns": len(turns),
            "avg_reply_len": sum(lengths) / len(lengths),
            "total_exclamations": exclamations,
            "total_emoji": emoji_total,
            "total_social_fillers": fillers,
        }

        print(f"  {pid:>6}: {len(turns)} turns, avg_len={summary[pid]['avg_reply_len']:.0f}, "
              f"excl={exclamations}, emoji={emoji_total}, fillers={fillers}")

        # Show first 3 replies for quick scan
        for t in turns[:3]:
            print(f"    T{t['turn']}: {t['reply'][:70]}")

    # Verdict
    if "iris" in summary and "kai" in summary:
        iris_s = summary["iris"]
        kai_s = summary["kai"]
        ratio = iris_s["avg_reply_len"] / kai_s["avg_reply_len"] if kai_s["avg_reply_len"] > 0 else 999
        print(f"\n  📊 Iris/Kai reply length ratio: {ratio:.1f}x")
        if ratio > 2.5:
            print(f"  ⚠️ Iris replies are {ratio:.1f}x longer than Kai — INFP should be comparable or shorter")
        if iris_s["total_exclamations"] > 3:
            print(f"  ⚠️ Iris used {iris_s['total_exclamations']} exclamation marks — INFP should rarely use them")
        if iris_s["total_social_fillers"] > 3:
            print(f"  ⚠️ Iris used {iris_s['total_social_fillers']} social filler phrases — INFP should avoid these")

    return summary


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

async def main():
    print(f"{'═' * 70}")
    print(f"🔬 Express Fidelity Test — Read-Only Verification")
    print(f"   Timestamp: {TIMESTAMP}")
    print(f"   No core code modifications. Direct ChatAgent bypass.")
    print(f"   EverMemOS: OFF | Memory: OFF | State: FRESH")
    print(f"{'═' * 70}")

    persona_loader = PersonaLoader(os.path.join(BASE_DIR, "persona", "personas"))
    personas = persona_loader.load_all()
    print(f"✓ Loaded {len(personas)} personas")

    llm = LLMClient(provider="dashscope", model="qwen-max")
    print(f"✓ LLM: dashscope/qwen-max")

    # ── Run all three groups ──
    g1 = await group1_monologue_vs_reply(persona_loader, llm)
    g2 = await group2_greeting_ab(persona_loader, llm)
    g3 = group3_cross_persona_review()

    # ── Final Verdict ──
    print(f"\n{'═' * 70}")
    print("🏁 Final Diagnosis")
    print(f"{'═' * 70}")

    # Check G1: Is Iris reply drifting from monologue?
    if "iris" in g1:
        iris_turns = g1["iris"]
        drift_count = 0
        for t in iris_turns:
            mono_shy = any(kw in t["monologue"] for kw in ["犹豫", "害羞", "紧张", "不知道", "不好意思", "shy", "hesitant"])
            reply_hot = t["reply_metrics"]["exclamations"] > 0 or t["reply_metrics"]["social_fillers"] > 0
            if mono_shy and reply_hot:
                drift_count += 1
                print(f"  ⚠️ DRIFT: mono is shy but reply is hot")
                print(f"     💭 {t['monologue'][:60]}")
                print(f"     🤖 {t['reply']}")

        if drift_count > 0:
            print(f"\n  🔴 Express is overriding Feel: {drift_count}/{len(iris_turns)} turns show monologue→reply drift")
        else:
            print(f"\n  🟢 No obvious monologue→reply drift detected in this run")

    # Check G2: Does greeting amplify drift?
    if "A_no_greeting" in g2 and "B_with_greeting" in g2:
        a_avg = sum(t["metrics"]["length"] for t in g2["A_no_greeting"]) / len(g2["A_no_greeting"])
        b_avg = sum(t["metrics"]["length"] for t in g2["B_with_greeting"]) / len(g2["B_with_greeting"])
        a_fillers = sum(t["metrics"]["social_fillers"] for t in g2["A_no_greeting"])
        b_fillers = sum(t["metrics"]["social_fillers"] for t in g2["B_with_greeting"])

        if b_avg > a_avg * 1.3 or b_fillers > a_fillers + 2:
            print(f"  🔴 Greeting injection amplifies drift: A={a_avg:.0f}字/{a_fillers}fillers → B={b_avg:.0f}字/{b_fillers}fillers")
        else:
            print(f"  🟡 Greeting effect inconclusive: A={a_avg:.0f}字/{a_fillers}fillers → B={b_avg:.0f}字/{b_fillers}fillers")

    # Save full results
    all_results = {
        "timestamp": TIMESTAMP,
        "group1_monologue_vs_reply": {
            pid: [
                {k: v for k, v in t.items()}
                for t in turns
            ]
            for pid, turns in g1.items()
        },
        "group2_greeting_ab": {
            k: [
                {k2: v2 for k2, v2 in t.items()}
                for t in turns
            ]
            for k, turns in g2.items()
        },
        "group3_cross_persona": g3,
    }
    out_path = os.path.join(os.path.dirname(__file__), "express_fidelity_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Results saved: {out_path}")
    print(f"{'═' * 70}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
