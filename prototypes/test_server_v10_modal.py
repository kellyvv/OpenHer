"""End-to-end test: server v10 engine + modality output"""
import json, re, ssl, os, urllib.request, sys, time

API_KEYS = {}
for env_path in [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server", ".env"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"),
]:
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    if k == "DASHSCOPE_API_KEY":
                        API_KEYS[k] = v
DASHSCOPE_KEY = API_KEYS.get("DASHSCOPE_API_KEY", "")


def call_llm_raw(system, user, model="qwen3-max"):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.92,
    }).encode()
    req = urllib.request.Request(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DASHSCOPE_KEY}",
        },
    )
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        data = json.loads(resp.read())
    raw = data["choices"][0]["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


# ── Use server's modules ──
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))
from core.genome.genome_engine import Agent, DRIVES, SIGNALS, CONTEXT_FEATURES
from core.genome.drive_metabolism import DriveMetabolism, apply_thermodynamic_noise
from core.agent.chat_agent import ACTOR_PROMPT, extract_reply


def critic_sense_sync(user_input, frustration_dict):
    prompt = (
        "你是情感感知器。分析用户输入，输出JSON：\n"
        "1. context（8维，0~1）: user_emotion(-1~1), topic_intimacy, conversation_depth, "
        "user_engagement, conflict_level, novelty_level, user_vulnerability, time_of_day\n"
        "2. frustration_delta: 5驱力变化量（正=更挫败，负=缓解）\n"
        f"Agent挫败值：{json.dumps({d: round(v, 2) for d, v in frustration_dict.items()})}\n"
        f'用户说："{user_input}"\n'
        '输出纯JSON：{"context":{...},"frustration_delta":{...}}'
    )
    raw = call_llm_raw(prompt, "")
    cleaned = re.sub(r"```json\s*", "", raw)
    cleaned = re.sub(r"```\s*", "", cleaned)
    try:
        data = json.loads(cleaned)
        ctx = {}
        for k, v in data.get("context", {}).items():
            lo = -1.0 if k == "user_emotion" else 0.0
            ctx[k] = max(lo, min(1.0, float(v)))
        delta = {
            d: max(-3.0, min(3.0, float(data.get("frustration_delta", {}).get(d, 0.0))))
            for d in DRIVES
        }
        return ctx, delta
    except Exception:
        return {f: 0.5 for f in CONTEXT_FEATURES}, {d: 0.0 for d in DRIVES}


TEST_DIALOGUE = [
    (2,      "你根本不在乎我"),
    (3,      "你凭什么这么冷漠"),
    (5,      "算了 我受够了"),
    (60,     "好吧 对不起"),
    (10,     "嗯嗯 你说得对"),
    (30,     "今天有个老同学突然找我了"),
    (120,    "晚安"),
    (259200, "在吗"),
    (5,      "我这三天真的好想你"),
    (10,     "想抱抱"),
]


def main():
    seed = 42
    agent = Agent(seed=seed)
    metabolism = DriveMetabolism()

    print("=" * 60)
    print("  SERVER v10 端到端测试（含【表达方式】）")
    print("=" * 60)

    sim_time = time.time()
    for i, (delay, msg) in enumerate(TEST_DIALOGUE):
        sim_time += delay
        if delay >= 3600:
            metabolism.time_metabolism(sim_time)
            print(f"\n{'─' * 50}")
            print(f"  ⏳ {delay / 86400:.1f}天断联")
            print(f"{'─' * 50}")

        # Critic
        frust_dict = {d: metabolism.frustration[d] for d in DRIVES}
        context, frustration_delta = critic_sense_sync(msg, frust_dict)
        reward = metabolism.apply_llm_delta(frustration_delta)
        metabolism.sync_to_agent(agent)

        # Signals
        base_signals = agent.compute_signals(context)
        total_frust = metabolism.total()
        noisy_signals = apply_thermodynamic_noise(base_signals, total_frust)

        # Actor
        signal_injection = agent.to_prompt_injection(context)
        system_prompt = ACTOR_PROMPT.format(
            few_shot="(无历史切片)", signal_injection=signal_injection
        )
        raw = call_llm_raw(system_prompt, msg)
        monologue, reply, modality = extract_reply(raw)

        # Learn
        agent.learn(noisy_signals, max(-1, min(1, reward)), context)

        # Print
        top3 = sorted(
            noisy_signals.items(), key=lambda x: abs(x[1] - 0.5), reverse=True
        )[:3]
        top3_str = "  ".join(f"{s}={v:.2f}" for s, v in top3)
        tag = f" ⏳{delay / 86400:.1f}天" if delay >= 3600 else ""
        if reward > 0.3:
            tag += " 🧬"

        print(f"\n  T{i:02d}{tag}  T°={total_frust * 0.05:.2f}  reward={reward:+.2f}")
        print(f"    🧠 {top3_str}")
        print(f"    👤 \"{msg}\"")
        print(f"    💬 {reply[:100]}")
        print(f"    📱 {modality}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
