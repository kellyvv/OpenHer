#!/usr/bin/env python3
"""
V10 对比测试：用 Kai 真实对话输入，测试不同 seed 下的人格多样性
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_archive"))

from tpe_v10_hybrid import (
    Agent, ContinuousStyleMemory, HybridMetabolism,
    critic_and_metabolize, apply_thermodynamic_noise,
    signals_to_prompt, ACTOR_PROMPT, extract_reply,
    call_llm, DRIVES
)
from genome_v4 import SIGNALS, simulate_conversation
import time

# Kai 的实际对话记录
KAI_DIALOGUE = [
    "你好啊",
    "为什么上来问我吃饭了吗",
    "什么口气，我能有什么意见，只是觉得奇怪",
    "而且是四个字，不是三个字",
    "跟你聊天很无趣",
    "你这人怎么这样",
    "算了吧，跟你聊不来",
]

def run_test(seed, label):
    print(f"\n{'='*60}")
    print(f"  seed={seed}  [{label}]")
    print(f"{'='*60}")

    db_dir = os.path.join(os.path.dirname(__file__), "memory_db")
    base_time = time.time()
    sim_time = base_time

    agent = Agent(seed=seed)
    # V10 关键：60轮预热（3个场景 × 20步）
    simulate_conversation(agent, ['分享喜悦', '吵架冲突', '深夜心事'], steps_per_scenario=20)

    mem_id = f"kai_test_seed{seed}_{int(base_time)}"
    memory = ContinuousStyleMemory(mem_id, db_dir, now=sim_time)
    metabolism = HybridMetabolism(clock=sim_time)

    last_action = None

    for i, user_input in enumerate(KAI_DIALOGUE):
        sim_time += 30  # 30秒间隔
        memory.set_clock(sim_time)

        frust_dict = {d: round(metabolism.frustration[d], 2) for d in DRIVES}
        context, frustration_delta = critic_and_metabolize(user_input, frust_dict)
        reward = metabolism.apply_llm_delta(frustration_delta)
        metabolism.sync_to_agent(agent)

        if last_action and reward > 0.3:
            memory.crystallize(
                last_action['signals'], last_action['monologue'],
                last_action['reply'], last_action['user_input'],
            )

        base_signals = agent.compute_signals(context)
        noisy = apply_thermodynamic_noise(base_signals, metabolism.total())

        few_shot = memory.build_few_shot_prompt(noisy, top_k=3)
        signal_injection = signals_to_prompt(noisy, agent)
        prompt = ACTOR_PROMPT.format(few_shot=few_shot, signal_injection=signal_injection)

        raw = call_llm(prompt, user_input)
        monologue, reply = extract_reply(raw)

        # 关键信号
        key_sigs = {s: round(noisy[s], 2) for s in ['directness','playfulness','defiance','warmth']}

        print(f"\nT{i+1:02d}  U: {user_input}")
        print(f"     signals: {key_sigs}  reward={reward:+.2f}")
        print(f"     💬 {reply}")

        last_action = {
            'signals': noisy, 'monologue': monologue,
            'reply': reply, 'user_input': user_input,
        }
        agent.step(context, reward=max(-1.0, min(1.0, reward)))
        time.sleep(0.5)


if __name__ == '__main__':
    # 测试 3 个 seed，对比多样性
    for seed, label in [(42, "default"), (100, "alt-A"), (888, "alt-B")]:
        run_test(seed, label)
