#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  📊 TPE v8 vs v9 对比测试 📊                                       ║
║                                                                      ║
║  同一组 10 轮对话，分别跑 v8 (Genome) 和 v9 (LLM-Native)，          ║
║  并排对比：frustration 状态 / 行为指令 / Actor 回复                  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_archive"))

# ── v8 imports ──
from genome_v8_timearrow import (
    DriveMetabolism as DriveMetabolismV8,
    critic_sense as critic_sense_v8,
    apply_thermodynamic_noise as noise_v8,
    ACTOR_PROMPT as ACTOR_PROMPT_V8,
    extract_reply as extract_reply_v8,
    call_llm,
    C,
)
from genome_v4 import Agent, SCENARIOS, SIGNALS, DRIVES, DRIVE_LABELS, CONTEXT_FEATURES
from style_memory import ContinuousStyleMemory

# ── v9 imports ──
from tpe_v9_llm_native import (
    TimeMetabolism as TimeMetabolismV9,
    perceive_and_metabolize,
    apply_thermodynamic_noise as noise_v9,
    ACTOR_PROMPT_V9,
    extract_reply as extract_reply_v9,
    chat_turn_v9,
)


# ══════════════════════════════════════════════
# v8 单轮（简化版，只跑核心管道）
# ══════════════════════════════════════════════

def build_context_from_critic(critic):
    """v8 的 Critic 3D → 8D context 映射"""
    a = critic.get('affiliation', 0.5)
    d = critic.get('dominance', 0.3)
    e = critic.get('entropy', 0.5)
    return {
        'user_emotion': a - d,
        'topic_intimacy': a * 0.8 + d * 0.2,
        'time_of_day': 0.5,
        'conversation_depth': 0.3,
        'user_engagement': max(a, d, e),
        'conflict_level': d * 0.9,
        'novelty_level': e,
        'user_vulnerability': a * (1 - d),
    }


def chat_turn_v8(agent, memory, metabolism, user_input, last_action, turn_id, sim_time):
    """v8 完整生命循环（10步），返回结构化结果"""

    # Step 1: 时间代谢
    memory.set_clock(sim_time)
    delta_h = metabolism.time_metabolism(sim_time)

    # Step 2: Critic
    critic = critic_sense_v8(user_input)

    # Step 3: 代数代谢
    reward = metabolism.process_stimulus(critic)
    metabolism.sync_to_agent(agent)

    # Step 4: 结晶
    crystallized = False
    if last_action and reward > 0.3:
        memory.crystallize(
            last_action['signals'],
            last_action['monologue'],
            last_action['reply'],
            last_action['user_input'],
        )
        crystallized = True

    # Step 5: 信号
    context = build_context_from_critic(critic)
    base_signals = agent.compute_signals(context)

    # Step 6: 噪声
    total_frust = metabolism.total()
    noisy_signals = noise_v8(base_signals, total_frust)

    # Step 7: KNN
    few_shot = memory.build_few_shot_prompt(noisy_signals, top_k=3)

    # Step 8: 信号注入（v8 方式：top-3 五档描述）
    signal_injection = agent.to_prompt_injection(context)

    # Step 8: Actor prompt
    prompt = ACTOR_PROMPT_V8.format(few_shot=few_shot)
    # v8 prototype 只有 few_shot，没有 signal_injection 在 ACTOR_PROMPT 模板里
    # 但实际 server 版的 chat_agent.py 是有的，为了公平对比我们加上
    prompt = prompt.replace("[Runtime Instruction]",
                            f"{signal_injection}\n\n[Runtime Instruction]")

    # Step 9: Actor
    raw = call_llm(prompt, user_input)
    monologue, reply = extract_reply_v8(raw)

    # Step 10: Hebbian
    agent.step(context, reward=max(-1.0, min(1.0, reward)))

    return {
        'signals': noisy_signals,
        'monologue': monologue,
        'reply': reply,
        'user_input': user_input,
        'reward': reward,
        'signal_injection': signal_injection,
        'critic': critic,
        'frustration': {d: round(metabolism.frustration[d], 2) for d in DRIVES},
    }


# ══════════════════════════════════════════════
# 对比测试
# ══════════════════════════════════════════════

# 10 轮测试对话（覆盖：攻击、认怂、闲聊、断联回归）
TEST_DIALOGUE = [
    (2,      "你根本不在乎我"),
    (3,      "你凭什么这么冷漠"),
    (5,      "算了 我受够了"),
    (10,     "好吧 对不起"),
    (5,      "嗯嗯 你说得对"),
    (10,     "今天有个老同学突然找我了"),
    (15,     "晚安"),
    (259200, "在吗"),           # 3天后
    (5,      "我这三天真的好想你"),
    (10,     "想抱抱"),
]


def run_single_engine(engine_name, run_func, *args):
    """通用引擎运行器"""
    base_time = time.time()
    sim_time = base_time
    results = []
    last_action = None

    for i, (delay_sec, msg) in enumerate(TEST_DIALOGUE):
        sim_time += delay_sec
        last_action = run_func(*args, msg, last_action, i, sim_time)
        results.append({
            'turn': i,
            'user_input': msg,
            'delay_sec': delay_sec,
            'reply': last_action['reply'],
            'monologue': last_action.get('monologue', ''),
            'reward': round(last_action.get('reward', 0), 2),
            'frustration': last_action.get('frustration', {}),
        })
        time.sleep(0.5)  # API 限速

    return results


def run_compare():
    print(f"""
{C.BOLD}╔══════════════════════════════════════════════════════════════╗
║  📊 TPE v8 vs v9 — 对比测试                                ║
║  同一组 10 轮对话 × 2 引擎                                  ║
╚══════════════════════════════════════════════════════════════╝{C.RESET}
""")

    db_dir = os.path.join(os.path.dirname(__file__), "memory_db")

    # ═══════════════════════════════════════
    # Phase 1: 跑 v8
    # ═══════════════════════════════════════
    print(f'\n{C.BOLD}{"═" * 60}')
    print(f'  🧬 Phase 1: TPE v8 (Genome — 神经网络 + 硬编码规则)')
    print(f'{"═" * 60}{C.RESET}\n')

    # 初始化 v8
    from genome_v4 import simulate_conversation
    agent_v8 = Agent(seed=42)
    # 培养 Agent（与 v8 原型一致）
    simulate_conversation(agent_v8, ['分享喜悦', '吵架冲突', '深夜心事'], steps_per_scenario=20)

    memory_v8 = ContinuousStyleMemory("compare_v8", db_dir, now=time.time())
    metabolism_v8 = DriveMetabolismV8(clock=time.time())

    v8_results = run_single_engine(
        "v8", chat_turn_v8,
        agent_v8, memory_v8, metabolism_v8,
    )

    # ═══════════════════════════════════════
    # Phase 2: 跑 v9
    # ═══════════════════════════════════════
    print(f'\n{C.BOLD}{"═" * 60}')
    print(f'  🧠 Phase 2: TPE v9 (LLM-Native — 无神经网络、无硬编码)')
    print(f'{"═" * 60}{C.RESET}\n')

    memory_v9 = ContinuousStyleMemory("compare_v9", db_dir, now=time.time())
    metabolism_v9 = TimeMetabolismV9(clock=time.time())

    v9_results = run_single_engine(
        "v9", chat_turn_v9,
        memory_v9, metabolism_v9,
    )

    # ═══════════════════════════════════════
    # Phase 3: 并排对比
    # ═══════════════════════════════════════
    print(f'\n{C.BOLD}{"═" * 60}')
    print(f'  📊 对比结果')
    print(f'{"═" * 60}{C.RESET}\n')

    comparison = []
    for i in range(len(TEST_DIALOGUE)):
        v8 = v8_results[i]
        v9 = v9_results[i]

        print(f'{C.BOLD}── T{i:02d}: "{v8["user_input"]}" ──{C.RESET}')

        # Frustration 对比
        print(f'  {C.DIM}Frustration:{C.RESET}')
        for d in DRIVES:
            f8 = v8['frustration'].get(d, 0)
            f9 = v9['frustration'].get(d, 0)
            diff = f9 - f8
            diff_str = f'{C.RED}+{diff:.1f}{C.RESET}' if diff > 0.3 else (
                f'{C.GREEN}{diff:.1f}{C.RESET}' if diff < -0.3 else f'{diff:+.1f}')
            print(f'    {DRIVE_LABELS[d]:8s}  v8={f8:.1f}  v9={f9:.1f}  Δ={diff_str}')

        # Reward 对比
        print(f'  {C.DIM}Reward:{C.RESET}  v8={v8["reward"]:+.2f}  v9={v9["reward"]:+.2f}')

        # 回复对比
        r8 = v8['reply'][:60] + ('...' if len(v8['reply']) > 60 else '')
        r9 = v9['reply'][:60] + ('...' if len(v9['reply']) > 60 else '')
        print(f'  {C.BLUE}v8💬{C.RESET} {r8}')
        print(f'  {C.CYAN}v9💬{C.RESET} {r9}')
        print()

        comparison.append({
            'turn': i,
            'user_input': v8['user_input'],
            'v8_reply': v8['reply'],
            'v9_reply': v9['reply'],
            'v8_reward': v8['reward'],
            'v9_reward': v9['reward'],
            'v8_frustration': v8['frustration'],
            'v9_frustration': v9['frustration'],
        })

    # 保存结果
    output_dir = os.path.join(os.path.dirname(__file__), "eval_results")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "v8_vs_v9.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)
    print(f'{C.GREEN}✅ 结果已保存到 {output_file}{C.RESET}')


if __name__ == '__main__':
    run_compare()
