"""
主动消息真实测试 — 直接调用 ChatAgent + proactive_tick()

不走 HTTP API，直接实例化引擎组件，跑真实 LLM 调用：
  1. 创建 ChatAgent (Luna)
  2. 用冲突性对话积累 safety frustration
  3. 人为模拟沉默 N 小时（调整 _last_active）
  4. 调用 proactive_tick()，观察真实输出

Usage:
  python scripts/test_proactive_real.py
"""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, "/Users/zxw/AITOOL/openher-docker")

from dotenv import load_dotenv
load_dotenv("/Users/zxw/AITOOL/openher-docker/.env")

from engine.genome.genome_engine import DRIVES, DRIVE_LABELS
from providers.llm.client import LLMClient
from providers.api_config import get_llm_config
from persona import PersonaLoader
from agent.chat_agent import ChatAgent


def header(t):
    print(f"\n{'='*65}\n  {t}\n{'='*65}")


def dump_drive_state(agent, label=""):
    """打印 drive 状态快照。"""
    m = agent.metabolism
    print(f"\n  [{label}] Drive 状态快照:")
    print(f"  {'Drive':15s} {'Frustration':>12} {'Norm(f/5)':>10} {'Baseline':>10} {'ImpScore':>10}")
    print(f"  {'-'*15} {'-'*12} {'-'*10} {'-'*10} {'-'*10}")
    for d in DRIVES:
        f = m.frustration[d]
        n = f / 5.0
        b = agent.agent.drive_baseline[d]
        s = n * (1.0 + b)
        flag = " 🔥" if s >= 0.8 else ""
        print(f"  {d:15s} {f:>12.4f} {n:>10.4f} {b:>10.4f} {s:>+10.3f}{flag}")
    print(f"  Total frustration: {m.total():.4f}")
    print(f"  Temperature: {m.temperature():.4f}")


async def main():
    header("主动消息真实 E2E 测试")

    # ── 初始化引擎（和服务器一样的方式加载 LLM 配置）──
    loader = PersonaLoader("/Users/zxw/AITOOL/openher-docker/persona/personas")
    luna = loader.get("luna")

    llm_cfg = get_llm_config()
    llm = LLMClient(
        provider=llm_cfg["provider"],
        model=llm_cfg["model"],
        temperature=llm_cfg.get("temperature", 0.92),
        max_tokens=llm_cfg.get("max_tokens", 1024),
    )
    print(f"  LLM: {llm_cfg['provider']}/{llm_cfg['model']}")
    print(f"  Persona: {luna.name} ({luna.mbti})")

    agent = ChatAgent(
        persona=luna,
        llm=llm,
        user_id="proactive_real_test",
        user_name="小明",
        genome_seed=hash("luna") % 100000,
    )
    # Pre-warm
    if agent.agent.age == 0:
        agent.pre_warm()
        print("  ✓ Pre-warm done")

    # ── Phase 1: 冲突性对话，积累 frustration ──
    header("Phase 1: 冲突性对话 (积累 safety frustration)")

    conflict_msgs = [
        "你是不是根本不在乎我？每次找你，你都心不在焉的",
        "算了，我不想和你说了，你根本不理解我",
        "你就是这样，永远只顾自己，从来不管别人的感受",
    ]

    for i, msg in enumerate(conflict_msgs):
        print(f"\n  Turn {i+1}: {msg}")
        result = await agent.chat(msg)
        print(f"  Reply: {result['reply'][:80]}...")
        print(f"  Modality: {result['modality']}")

        dump_drive_state(agent, f"Turn {i+1} 后")

    # ── Phase 2: 查看 impulse 状态 ──
    header("Phase 2: 对话结束后 impulse 检查")

    impulse = agent._has_impulse()
    if impulse:
        drive_id, desc = impulse
        print(f"  ✅ IMPULSE 已触发！ drive={drive_id}, desc={desc}")
    else:
        print(f"  ⚠ 对话后 impulse 未自然触发")
        # 直接检查各 drive 的 score
        m = agent.metabolism
        print(f"  各 drive 的 impulse score:")
        for d in DRIVES:
            n = m.frustration[d] / 5.0
            b = agent.agent.drive_baseline[d]
            s = n * (1.0 + b)
            print(f"    {d}: score={s:.3f}  (需要 >= 0.8)")

        # 如果自然没触发，人为拉高 connection frustration 到触发值
        print(f"\n  手动拉高 connection frustration 到 2.5 以模拟想念...")
        m.frustration['connection'] = 2.5
        dump_drive_state(agent, "手动调整后")

        impulse = agent._has_impulse()
        if impulse:
            drive_id, desc = impulse
            print(f"\n  ✅ IMPULSE 触发！ drive={drive_id}, desc={desc}")
        else:
            print(f"\n  ❌ 仍未触发，手动设置 connection 到 3.0")
            m.frustration['connection'] = 3.0
            impulse = agent._has_impulse()
            if impulse:
                drive_id, desc = impulse
                print(f"  ✅ IMPULSE 触发！ drive={drive_id}, desc={desc}")

    # ── Phase 3: 模拟沉默 + 调用 proactive_tick ──
    header("Phase 3: 模拟沉默后调用 proactive_tick()")

    # 模拟 2 小时前的对话（让 stimulus 里显示时间）
    agent._last_active = time.time() - 2 * 3600
    print(f"  模拟: 2 小时前最后一次互动")

    dump_drive_state(agent, "proactive_tick 前")

    print(f"\n  正在调用 proactive_tick() (真实 LLM 调用)...")
    tick_result = await agent.proactive_tick()

    # ── Phase 4: 输出完整数据 ──
    header("Phase 4: proactive_tick() 输出数据")

    if tick_result:
        print(f"  ✅ proactive_tick 返回了消息！\n")
        print(f"  完整数据:")
        print(f"  {json.dumps(tick_result, indent=2, ensure_ascii=False)}")
        print(f"\n  拆解:")
        print(f"    reply:      {tick_result['reply']}")
        print(f"    modality:   {tick_result['modality']}")
        print(f"    monologue:  {tick_result['monologue']}")
        print(f"    proactive:  {tick_result['proactive']}")
        print(f"    drive_id:   {tick_result['drive_id']}")
        print(f"    tick_id:    {tick_result['tick_id']}")

        dump_drive_state(agent, "proactive_tick 后")

        # WebSocket 推送数据结构
        print(f"\n  WebSocket 推送 payload:")
        ws_payload = {
            "type": "proactive",
            "content": tick_result['reply'],
            "modality": tick_result['modality'],
            "drive": tick_result['drive_id'],
            "persona": luna.name,
        }
        print(f"  {json.dumps(ws_payload, indent=2, ensure_ascii=False)}")
    else:
        print(f"  ⚠ proactive_tick 返回 None")
        print(f"  可能原因：")
        print(f"    1. _has_impulse() 未触发 (frustration 不够高)")
        print(f"    2. Actor 选择了 '静默' (modality='静默')")
        dump_drive_state(agent, "tick 返回 None 后")

    header("测试完成")


if __name__ == "__main__":
    asyncio.run(main())
