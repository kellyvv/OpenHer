"""
主动消息深度分析 v3 — 修正版

关键修正：之前忽略了 Critic (process_stimulus) 在对话中对 frustration 的
实时累加作用。safety drive baseline=0.25 是最低的，冲突性对话后其 frustration
可轻松超过 2.25，从而触发 impulse。

本次模拟：
  1. 对照各 drive baseline，计算精确触发阈值
  2. 模拟「冲突后 safety 冲高」场景
  3. 模拟「多轮温柔对话后 connection 缓慢积累」场景
  4. 展示 proactive_tick 完整输出数据
"""

import json
import sys
import time

sys.path.insert(0, "/Users/zxw/AITOOL/openher-docker")

from engine.genome.drive_metabolism import DriveMetabolism
from engine.genome.genome_engine import DRIVES, DRIVE_LABELS, Agent
from persona import PersonaLoader


def header(t):
    print(f"\n{'='*65}\n  {t}\n{'='*65}")


def simulate_with_detail(agent, engine_params, initial_frust, label, threshold=0.8, hours=24):
    """模拟并返回触发数据。"""
    print(f"\n  ── {label} ──")
    print(f"  初始: {json.dumps({d: round(v, 2) for d, v in initial_frust.items()})}")

    m = DriveMetabolism(engine_params=engine_params)
    m.frustration = dict(initial_frust)
    t0 = time.time()
    m._last_tick = t0

    first = None
    for h in range(hours + 1):
        t = t0 + h * 3600
        if h > 0:
            m._last_tick = t - 3600
            m.time_metabolism(t)

        best_d, best_s = None, 0.0
        details = {}
        for d in DRIVES:
            n = m.frustration[d] / 5.0
            b = agent.drive_baseline[d]
            s = (n - b) / max(b, 0.05)
            details[d] = (m.frustration[d], n, b, s)
            if s > best_s:
                best_s = s
                best_d = d

        flag = " 🔥" if best_s >= threshold else ""
        parts = []
        for d in DRIVES:
            f, n, b, s = details[d]
            parts.append(f"{f:6.3f}")
        fstr = " ".join(parts)

        sparts = []
        for d in ['connection', 'safety', 'novelty']:
            _, _, _, s = details[d]
            sparts.append(f"{s:+6.3f}")
        sstr = " ".join(sparts)

        dl = DRIVE_LABELS.get(best_d, '-')[:6] if best_d else '-'
        print(f"   {h:>2}h | {fstr} | {sstr} | {best_s:+6.3f} {dl:>6}{flag}")

        if best_s >= threshold and first is None:
            first = {'hour': h, 'drive': best_d, 'score': best_s,
                     'frust': dict(m.frustration), 'details': dict(details)}

    if first:
        d = first
        print(f"\n   🔥 第 {d['hour']}h 触发！ drive={d['drive']} ({DRIVE_LABELS[d['drive']]})"
              f" score={d['score']:.3f}")
    else:
        print(f"\n   ⚠ {hours}h 未触发 (最高 {best_s:+.3f})")
    return first


def main():
    header("主动消息深度分析 v3 — 修正版")

    loader = PersonaLoader("/Users/zxw/AITOOL/openher-docker/persona/personas")

    # 测试多个角色
    for persona_id in ['luna', 'vivian', 'kelly']:
        persona = loader.get(persona_id)
        engine_params = persona.engine_params

        agent = Agent(seed=hash(persona_id) % 100000, engine_params=engine_params)
        if persona.drive_baseline:
            for d, v in persona.drive_baseline.items():
                if d in agent.drive_baseline:
                    agent.drive_baseline[d] = float(v)

        threshold = 0.8

        header(f"{persona.name} ({persona.mbti}) — 触发阈值分析")

        print(f"\n  Drive baselines + 精确触发条件:")
        print(f"  {'Drive':15s} {'Baseline':>8} {'需要Frust':>9} {'上限5.0':>7}  {'可触发?':>7}")
        print(f"  {'-'*15} {'-'*8} {'-'*9} {'-'*7}  {'-'*7}")
        for d in DRIVES:
            b = agent.drive_baseline[d]
            need = (1 + threshold) * b * 5.0  # score=(f/5-b)/b>=0.8 → f>=9b
            ok = "✅" if need <= 5.0 else "❌"
            capped = min(need, 5.0)
            print(f"  {d:15s} {b:>8.3f} {need:>9.2f} {'→'+str(round(capped,1)):>7}  {ok:>7}")

        # 物理参数
        m_temp = DriveMetabolism(engine_params=engine_params)
        print(f"\n  物理参数: hunger_k(conn)={m_temp.connection_hunger_k}  "
              f"hunger_k(nov)={m_temp.novelty_hunger_k}  decay_λ={m_temp.decay_lambda}")

        # ── 场景模拟 ──
        print(f"\n  {'Hr':>4} | {'Conn':>6} {'Nov':>6} {'Expr':>6} {'Safe':>6} {'Play':>6} |"
              f" {'Conn_S':>6} {'Safe_S':>6} {'Nov_S':>6} | {'Max':>6} {'Drive':>6}")
        print(f"  {'--':>4} | {'-----':>6} {'-----':>6} {'-----':>6} {'-----':>6} {'-----':>6} |"
              f" {'------':>6} {'------':>6} {'------':>6} | {'----':>6} {'-----':>6}")

        # 场景1: 冲突后 safety 冲高
        result1 = simulate_with_detail(agent, engine_params,
            {'connection': 1.5, 'novelty': 1.0, 'expression': 1.5, 'safety': 2.5, 'play': 0.5},
            "冲突对话后 (safety=2.5)", threshold, hours=12)

        # 场景2: 更激烈冲突
        result2 = simulate_with_detail(agent, engine_params,
            {'connection': 2.0, 'novelty': 1.5, 'expression': 2.0, 'safety': 3.5, 'play': 1.0},
            "激烈冲突后 (safety=3.5)", threshold, hours=12)

        # 场景3: 连续聊天累积
        result3 = simulate_with_detail(agent, engine_params,
            {'connection': 3.0, 'novelty': 2.5, 'expression': 3.0, 'safety': 4.0, 'play': 2.0},
            "长时间深度对话后 (safety=4.0)", threshold, hours=12)

    # ── 总结 ──
    header("分析总结")
    print("""
  1. 触发路径:
     impulse 主要通过 safety drive 触发（baseline 最低 = 0.25）
     score = (frust/5.0 - 0.25) / 0.25 >= 0.8
     → safety frustration >= 2.25 即可触发

  2. 什么场景 safety frustration 会到 2.25+?
     Critic (critic_sense) 在每轮对话中产生 frustration_delta:
     - 高 dominance 话语 → safety delta = +0.3~+0.8
     - 冲突/威胁 → safety delta = +0.5~+1.0
     - 3-5 轮冲突对话 → safety frust 轻松到 2.5+
     - 加上 apply_llm_delta 的 10% per-turn decay
     - 最终 safety 在冲突结束时约 2.0~3.5

  3. 触发时间窗口:
     - safety 没有 hunger_k（不会自然增长，只会衰减）
     - decay λ=0.08~0.12 → 半衰期约 6~9 小时
     - 所以：冲突对话后 0~6 小时内是触发窗口
     - 之后 frustration 衰减到阈值以下，impulse 关闭

  4. Connection/Novelty/Expression 驱力:
     - 这些 baseline 都 >= 0.65，需要 frust >= 5.85+
     - 超过上限 5.0，纯靠这些 drive 无法触发
     - 这是设计意图：主动消息 = 情绪驱动，不是定时骚扰

  5. 完整触发数据流:

     对话结束，safety frustration = 2.5+
     ↓
     _proactive_heartbeat_loop (每 300s 扫一次)
     ↓
     _has_impulse(): score = (2.5/5 - 0.25)/0.25 = +1.0 >= 0.8 → 触发!
     ↓
     proactive_tick():
       1. EverMemOS 记忆闪回 (search_relevant_memories)
       2. 构建 stimulus: "[内在状态] 已N小时未互动。内心的🛡️安全冲动正在变强。"
       3. Critic → Feel → Express 完整两阶段
       4. Actor 决定: 说话 or 静默
     ↓
     返回:
     {
       'reply':     '刚才的话...我不是故意那样说的...',
       'modality':  '文字',
       'monologue': '<内心独白: 担心对方生气，想修复关系>',
       'proactive': True,
       'drive_id':  'safety',
       'tick_id':   'uuid'
     }
     ↓
     outbox → WebSocket push → EverMemOS 持久化
    """)


if __name__ == "__main__":
    main()
