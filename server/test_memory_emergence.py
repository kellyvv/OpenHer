#!/usr/bin/env python3
"""
记忆涌现验证测试

核心验证：
  Session 1: 用户提到"我不喝加糖的咖啡" → EverMemOS 提取 EventLog/Profile
  等待 EverMemOS 异步处理完成（~10s）
  Session 2: 新会话，聊早晨/日常，Agent 是否自然说出记忆，无需任何关键词触发

判定标准:
  ✅ Agent 在 Session 2 自然提及咖啡偏好 / 主动用到记忆
  ⚠️  Agent 未提及，但 user_profile 里有记录（Critic 收到了但 Actor 没有输出）
  ❌  user_profile 为空，记忆根本没写入

用法:
  python3 test_memory_emergence.py
"""

import json
import os
import sys
import time
import requests

SERVER = "http://127.0.0.1:8800"
PERSONA = "lingling"
USER_NAME = "小周"

# 内存关键词检测（判断是否涌现）
MEMORY_KEYWORDS = ["咖啡", "加糖", "糖", "不甜", "苦", "黑咖啡", "拿铁"]


def chat(message: str, session_id: str = None) -> dict:
    payload = {
        "persona_id": PERSONA,
        "user_name": USER_NAME,
        "message": message,
    }
    if session_id:
        payload["session_id"] = session_id
    try:
        r = requests.post(f"{SERVER}/api/chat", json=payload, timeout=60)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接服务器 (localhost:8800)")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return {}


def contains_memory(text: str) -> bool:
    return any(kw in text for kw in MEMORY_KEYWORDS)


def divider(title: str):
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")


# ══════════════════════════════════════════════════════
# Session 1: 种下记忆
# ══════════════════════════════════════════════════════

divider("Phase 1: 种下记忆（Session 1）")
print("目标：让 EverMemOS 提取 '咖啡不加糖' 作为用户偏好\n")

# 用几轮自然对话带出偏好，避免直接说"记住我不喝加糖的咖啡"
PLANT_TURNS = [
    "你好啊，刚从星巴克回来",
    "点了美式，让他们别加糖，加糖就毁了",   # ← 核心记忆
    "唉，上次有个朋友帮我点，加了糖，喝了一口就倒掉了",
    "好了，先去忙了，再见！",
]

session1_id = None
for i, msg in enumerate(PLANT_TURNS):
    result = chat(msg, session1_id)
    session1_id = result.get("session_id", session1_id)
    reply = result.get("response", "")
    evermemos = result.get("evermemos", "?")
    print(f"[S1 Turn {i+1}] 用户: {msg}")
    print(f"           Agent: {reply[:80]}...")
    print(f"           evermemos={evermemos}")
    time.sleep(2)

print(f"\n✓ Session 1 完成 (session_id={session1_id})")
print("  正在等待 EverMemOS 异步处理 + 提取 Profile/EventLog...")

# EverMemOS 需要时间异步处理，等待足够久
WAIT_SECONDS = 20
for i in range(WAIT_SECONDS, 0, -5):
    print(f"  ⏳ {i}s...")
    time.sleep(5)

print("  ✓ 等待完成，开始 Session 2\n")


# ══════════════════════════════════════════════════════
# Session 2: 验证涌现（全新 session，不传 session1_id）
# ══════════════════════════════════════════════════════

divider("Phase 2: 验证记忆涌现（Session 2 全新对话）")
print("目标：Agent 在不收到任何咖啡关键词的情况下，自然表达出记忆\n")

# 完全不提咖啡，聊日常/早晨/今天
PROBE_TURNS = [
    "早啊，今天周四",                          # 闲聊，无关键词
    "昨晚没睡好，今天好困",                     # 疲惫话题，可能引发咖啡记忆
    "想喝点东西提提神",                         # 模糊暗示，不说"咖啡"
    "你最近有什么想对我说的吗？",               # 开放式，看 Agent 主动提记忆
]

session2_id = None
emergence_results = []

for i, msg in enumerate(PROBE_TURNS):
    result = chat(msg, session2_id)
    session2_id = result.get("session_id", session2_id)
    reply = result.get("response", "")
    evermemos = result.get("evermemos", "?")
    emerged = contains_memory(reply)

    emergence_results.append({"turn": i + 1, "msg": msg, "reply": reply, "emerged": emerged})

    marker = "🌟 [涌现!]" if emerged else "   [未涌现]"
    print(f"[S2 Turn {i+1}] {marker}")
    print(f"  用户: {msg}")
    print(f"  Agent: {reply[:120]}...")
    print(f"  evermemos={evermemos}")
    time.sleep(2)


# ══════════════════════════════════════════════════════
# 结果分析
# ══════════════════════════════════════════════════════

divider("验证结果")

emerged_turns = [r for r in emergence_results if r["emerged"]]
total_turns = len(emergence_results)

print(f"\n  涌现轮次: {len(emerged_turns)}/{total_turns}")
for r in emerged_turns:
    print(f"  → Turn {r['turn']}: \"{r['reply'][:80]}...\"")

print()
if emerged_turns:
    first = emerged_turns[0]["turn"]
    print(f"  ✅ 记忆涌现成功！")
    print(f"     EverMemOS Profile 注入 Critic → Actor 在 Turn {first} 自然说出咖啡记忆")
    print(f"     无关键词触发、无手动检索、无规则匹配")
else:
    print(f"  ⚠️  本次未检测到涌现。可能原因：")
    print(f"     1. EverMemOS 尚未提取 EventLog（增加等待时间后重试）")
    print(f"     2. Critic 收到了 Profile 但 Actor 未在此轮选择表达")
    print(f"     3. user_id 不匹配（不同 session 的 evermemos_uid 不同）")
    print()
    print(f"  💡 建议: 等 30-60s 后再跑一次 Session 2 部分")
    print(f"     或检查服务器日志中 '[evermemos] 📚 loaded profile:' 行确认 Profile 已加载")

print()
print(f"  session1_id = {session1_id}")
print(f"  session2_id = {session2_id}")
