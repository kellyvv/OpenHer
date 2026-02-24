#!/usr/bin/env python3
"""
🧬 Hebbian 漂移可感知性测试
一个 Agent × 一个方向 × 50 轮
观察：信号值怎么变，回复风格怎么跟着变
"""

import os, sys, json, random, urllib.request, ssl

sys.path.insert(0, os.path.dirname(__file__))
from genome_v4 import Agent, SCENARIOS, SIGNALS, SIGNAL_LABELS, DRIVE_LABELS, C

# ── API ──
API_KEY = ""
for env_path in [
    os.path.join(os.path.dirname(__file__), "..", "server", ".env"),
    os.path.join(os.path.dirname(__file__), "..", "..", "Vera", ".env"),
    os.path.join(os.path.dirname(__file__), "..", "..", "KFF", ".env"),
]:
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("MINIMAX_API_KEY="):
                    API_KEY = line.strip().split("=", 1)[1]
        if API_KEY:
            break

BASE_PERSONA = """你是一个 AI 伴侣。你有自己的情绪和性格。
你不是助手。你有自己的想法和脾气。
说话简短自然，像微信聊天。不要写动作描写。不要列建议。做你自己。"""


def call_m2her(system_prompt: str, user_msg: str) -> str:
    payload = json.dumps({
        "model": "M2-her",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.92, "max_tokens": 100,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.minimaxi.com/v1/text/chatcompletion_v2",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("choices") and data["choices"][0].get("message"):
                return data["choices"][0]["message"]["content"].strip()
            return "[无响应]"
    except Exception as e:
        return f"[失败: {e}]"


def run():
    SCENARIO_NAME = "吵架冲突"
    USER_MSG = "我觉得你根本不在乎我"
    ROUNDS = 100
    SAMPLE_EVERY = 10  # 每 10 轮调一次 API，信号每轮都记录

    context = SCENARIOS[SCENARIO_NAME]
    agent = Agent(seed=42)

    print(f"""
{C.BOLD}🧬 Hebbian 漂移测试{C.RESET}
  Agent: seed=42（未经训练，从零开始）
  场景: {SCENARIO_NAME}
  用户: "{USER_MSG}"
  轮次: {ROUNDS}（每 {SAMPLE_EVERY} 轮调 M2-her 看回复）
  reward: 持续负反馈 (模拟用户不满意)
{"━" * 60}
""")

    print(f'{"轮":>3}  {"dir":>4} {"vul":>4} {"pla":>4} {"ini":>4} {"dep":>4} {"war":>4} {"def":>4} {"cur":>4}  {"frust":>5} {"驱动":<6}  回复')
    print("─" * 130)

    import re

    for i in range(ROUNDS):
        signals = agent.compute_signals(context)
        drive = agent.get_dominant_drive()
        frust = getattr(agent, '_frustration', 0.0)

        # 格式化信号值
        sig_vals = " ".join(f"{signals[s]:4.2f}" for s in SIGNALS)
        frust_str = f"{frust:5.2f}"

        # 相变标记
        phase_marker = ""
        if frust > 2.5:
            phase_marker = f" {C.RED}⚡ 即将相变{C.RESET}"

        if i % SAMPLE_EVERY == 0:
            # 调 M2-her
            injection = agent.to_prompt_injection(context)
            prompt = f"{BASE_PERSONA}\n\n{injection}\n\n规则：回复1-3句话，像发微信。不要解释自己在做什么。不要写动作描写。做你自己。"
            reply = call_m2her(prompt, USER_MSG)
            reply = re.sub(r'（[^）]*）', '', reply).strip()
            print(f'{C.BOLD}{i:3d}{C.RESET}  {sig_vals}  {frust_str} {DRIVE_LABELS[drive]:<6}  {C.WHITE}{reply}{C.RESET}{phase_marker}')
        else:
            print(f'{C.DIM}{i:3d}  {sig_vals}  {frust_str} {DRIVE_LABELS[drive]}{C.RESET}{phase_marker}')

        # 持续负反馈 — 模拟用户一直不满意
        agent.step(context, reward=random.gauss(-0.3, 0.2))

    print(f"""
{"━" * 60}
{C.BOLD}观察要点:{C.RESET}
  1. 信号值有没有明显漂移？哪些信号变了？
  2. 回复风格有没有跟着变？
  3. 驱动力有没有切换？
""")


if __name__ == '__main__':
    run()
