"""
Critic — LLM-based perception of user intent signals (v10 Hybrid).

v10 change: Directly outputs 8D context + 5D frustration delta.
Eliminates the 3D→8D hand-written mapping formula.

Extracted from genome_v8_timearrow.py, upgraded to v10 architecture.
"""

from __future__ import annotations

import json
import re
from typing import Optional, Tuple

from core.llm.client import LLMClient, ChatMessage
from core.genome.genome_engine import DRIVES, CONTEXT_FEATURES


CRITIC_PROMPT = """你是一个角色扮演 Agent 的情感感知器。分析用户输入，输出两组数据：

1. 对话上下文感知（8 维，0.0~1.0）：
  - user_emotion: 用户情绪（-1=负面, 0=中性, 1=正面）
  - topic_intimacy: 话题私密度（0=公事, 1=私密）
  - conversation_depth: 对话深度（0=刚开始, 1=聊很久了）
  - user_engagement: 用户投入度（0=敷衍, 1=投入）
  - conflict_level: 冲突程度（0=和谐, 1=冲突）
  - novelty_level: 信息新鲜度（0=重复/日常, 1=全新信息）
  - user_vulnerability: 用户敞开程度（0=防御, 1=敞开心扉）
  - time_of_day: 时间氛围（0=白天日常, 1=深夜私密）

2. Agent 5 个驱力的挫败变化量（正=更挫败，负=被缓解）

Agent 当前挫败值（0=满足, 5=极度渴望）：
{frustration_json}

{user_profile_section}{episode_section}用户说了："{user_input}"

严格输出纯 JSON：
{
  "context": {"user_emotion": 0.3, "topic_intimacy": 0.8, "conversation_depth": 0.5, "user_engagement": 0.7, "conflict_level": 0.1, "novelty_level": 0.3, "user_vulnerability": 0.6, "time_of_day": 0.5},
  "frustration_delta": {"connection": -0.3, "novelty": 0.0, "expression": 0.1, "safety": -0.2, "play": 0.0}
}"""


# Default values when Critic fails
_DEFAULT_CONTEXT = {f: 0.5 for f in CONTEXT_FEATURES}
_DEFAULT_DELTA = {d: 0.0 for d in DRIVES}


async def critic_sense(
    user_input: str,
    llm: LLMClient,
    frustration: dict = None,
    user_profile: str = "",
    episode_summary: str = "",
) -> Tuple[dict, dict]:
    """
    Measure user input → 8D context + 5D frustration delta.

    Args:
        user_profile: EverMemOS user profile for relationship-aware perception.
        episode_summary: Narrative episode history so Critic knows past conversations.

    Returns: (context_8d, frustration_delta)
    """
    frust_json = json.dumps(
        frustration or _DEFAULT_DELTA,
        ensure_ascii=False,
    )

    # Build profile section
    profile_section = ""
    if user_profile:
        profile_section = f"关于这个用户的历史画像（请据此更准确地感知情绪和意图）：\n{user_profile}\n\n"

    # Build episode section (narrative history → Critic can gauge conversation_depth)
    episode_section = ""
    if episode_summary:
        episode_section = f"与此用户的历史对话叙事（据此判断 conversation_depth 和 topic_intimacy）：\n{episode_summary}\n\n"

    prompt = CRITIC_PROMPT.replace(
        "{frustration_json}", frust_json
    ).replace(
        "{user_input}", user_input
    ).replace(
        "{user_profile_section}", profile_section
    ).replace(
        "{episode_section}", episode_section
    )

    messages = [
        ChatMessage(role="system", content=prompt),
        ChatMessage(role="user", content=user_input),
    ]

    try:
        response = await llm.chat(
            messages,
            temperature=0.2,
        )
        raw = response.content.strip()

        # Strip think tags if present (Qwen3)
        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()

        # Clean markdown code blocks
        cleaned = re.sub(r'```json\s*', '', raw)
        cleaned = re.sub(r'```\s*', '', cleaned)

        data = json.loads(cleaned)

        # Parse 8D context
        raw_ctx = data.get('context', {})
        context = {}
        for feat in CONTEXT_FEATURES:
            v = float(raw_ctx.get(feat, 0.5))
            if feat == 'user_emotion':
                context[feat] = max(-1.0, min(1.0, v))
            else:
                context[feat] = max(0.0, min(1.0, v))

        # Parse frustration delta
        frustration_delta = {}
        raw_delta = data.get('frustration_delta', {})
        for d in DRIVES:
            v = float(raw_delta.get(d, 0.0))
            frustration_delta[d] = max(-3.0, min(3.0, v))

        return context, frustration_delta

    except (json.JSONDecodeError, ValueError, TypeError, Exception) as e:
        print(f"[critic] Parse error: {e}")
        return dict(_DEFAULT_CONTEXT), dict(_DEFAULT_DELTA)
