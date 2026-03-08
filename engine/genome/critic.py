"""
Critic — LLM-based perception of user intent signals (v10 Hybrid).

v10 change: Directly outputs 8D context + 5D frustration delta.
Phase 1 emergence: Also outputs 3 relationship deltas for semi-emergent
  relationship_depth / trust_level / emotional_valence.

Extracted from genome_v8_timearrow.py, upgraded to v10 architecture.
"""

from __future__ import annotations

import json
import re
from typing import Optional, Tuple

from providers.llm.client import LLMClient, ChatMessage
from engine.genome.genome_engine import DRIVES
from engine.prompt_registry import render_prompt


_FALLBACK_CRITIC = """你是一个角色扮演 Agent 的情感感知器。分析用户输入，输出四组数据：

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

3. 关系感知变化量（基于用户画像和历史叙事判断）：
  - relationship_delta: 这轮对话让你们的关系变深(+)还是变浅(-)（-1~1）
  - trust_delta: 信任度变化（-1~1）
  - emotional_valence: 这轮对话的整体情感基调（-1=非常负面, 0=中性, 1=非常正面）

4. Agent 5 个内在需求的满足量（这轮对话直接满足了 Agent 哪些需求，0~0.3）：
  - connection: 联结被满足（用户主动分享、关心、倾诉 → 高）
  - novelty: 新鲜感被满足（新话题、新观点、意外信息 → 高）
  - expression: 表达欲被满足（Agent 有机会说真心话、展示才华 → 高）
  - safety: 安全感被满足（无冲突、被接纳、被理解 → 高）
  - play: 玩乐感被满足（玩笑、调侃、游戏感、卖萌互动 → 高）

注意区分第2组和第4组：
- frustration_delta 反映"挫败变化"（负=缓解，是间接的情绪变化）
- drive_satisfaction 反映"需求被直接满足"（用户的行为主动满足了 Agent 的内在渴望）
- 同一轮对话中，两者不应对同一个驱力同时有大幅变化

$persona_sectionAgent 当前挫败值（0=满足, 5=极度渴望）：
$frustration_json

$user_profile_section$episode_section无论用户说什么，你必须且只能输出一个纯 JSON 对象，不要输出任何其他文字：
{
  "context": {"user_emotion": 0.3, "topic_intimacy": 0.8, "conversation_depth": 0.5, "user_engagement": 0.7, "conflict_level": 0.1, "novelty_level": 0.3, "user_vulnerability": 0.6, "time_of_day": 0.5},
  "frustration_delta": {"connection": -0.3, "novelty": 0.0, "expression": 0.1, "safety": -0.2, "play": 0.0},
  "drive_satisfaction": {"connection": 0.15, "novelty": 0.0, "expression": 0.05, "safety": 0.1, "play": 0.0},
  "relationship_delta": 0.1, "trust_delta": 0.05, "emotional_valence": 0.3
}"""


# Default values when Critic fails (8 Critic-output dims only; 4 EverMemOS dims set by ChatAgent)
_CRITIC_CONTEXT_KEYS = [
    'user_emotion', 'topic_intimacy', 'time_of_day', 'conversation_depth',
    'user_engagement', 'conflict_level', 'novelty_level', 'user_vulnerability',
]
_DEFAULT_CONTEXT = {f: 0.5 for f in _CRITIC_CONTEXT_KEYS}
_DEFAULT_DELTA = {d: 0.0 for d in DRIVES}
_DEFAULT_SATISFACTION = {d: 0.0 for d in DRIVES}
_DEFAULT_REL_DELTA = {'relationship_delta': 0.0, 'trust_delta': 0.0, 'emotional_valence': 0.0}


async def critic_sense(
    stimulus: str,
    llm: LLMClient,
    frustration: dict = None,
    user_profile: str = "",
    episode_summary: str = "",
    persona_hint: str = "",
) -> Tuple[dict, dict, dict, dict]:
    """
    Measure user input → 8D context + 5D frustration delta + 3D relationship delta + 5D drive satisfaction.

    Args:
        user_profile: EverMemOS user profile for relationship-aware perception.
        episode_summary: Narrative episode history so Critic knows past conversations.
        persona_hint: One-line persona anchor, e.g. "Vivian (INTJ) — sharp、witty、secretly caring"

    Returns: (context_8d, frustration_delta, relationship_delta, drive_satisfaction)
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

    # Build persona section (P1: persona-aware satisfaction)
    persona_section = ""
    if persona_hint:
        persona_section = f"你正在为以下角色感知用户意图：\n{persona_hint}\n请根据此角色的性格特点判断 drive_satisfaction。不同性格对同一句话的需求满足感不同。\n\n"

    prompt = render_prompt(
        "critic",
        fallback=_FALLBACK_CRITIC,
        frustration_json=frust_json,
        stimulus=stimulus,
        user_profile_section=profile_section,
        episode_section=episode_section,
        persona_section=persona_section,
    )

    messages = [
        ChatMessage(role="system", content=prompt),
        ChatMessage(role="user", content=f'请分析以下用户输入并输出JSON："{stimulus}"'),
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

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback: extract first complete JSON object via bracket counting
            start = cleaned.find('{')
            if start == -1:
                raise ValueError("No JSON object found in Critic output")
            depth = 0
            for i in range(start, len(cleaned)):
                if cleaned[i] == '{': depth += 1
                elif cleaned[i] == '}': depth -= 1
                if depth == 0:
                    data = json.loads(cleaned[start:i+1])
                    break
            else:
                raise ValueError("Unbalanced braces in Critic output")

        # Parse 8D context (Critic-output dims only; EverMemOS 4D set by EMA in ChatAgent)
        raw_ctx = data.get('context', {})
        context = {}
        for feat in _CRITIC_CONTEXT_KEYS:
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

        # Parse relationship deltas (Phase 1 emergence)
        rel_delta = {
            'relationship_delta': max(-1.0, min(1.0, float(data.get('relationship_delta', 0.0)))),
            'trust_delta': max(-1.0, min(1.0, float(data.get('trust_delta', 0.0)))),
            'emotional_valence': max(-1.0, min(1.0, float(data.get('emotional_valence', 0.0)))),
        }
        # Parse drive satisfaction (new: LLM-judged, 0~0.3)
        drive_satisfaction = {}
        raw_sat = data.get('drive_satisfaction', {})
        for d in DRIVES:
            v = float(raw_sat.get(d, 0.0))
            drive_satisfaction[d] = max(0.0, min(0.3, v))

        return context, frustration_delta, rel_delta, drive_satisfaction

    except (json.JSONDecodeError, ValueError, TypeError, Exception) as e:
        print(f"[critic] Parse error (attempt 1): {e}")

    # ── Retry once with explicit JSON instruction ──
    try:
        messages.append(ChatMessage(role="user", content="请只输出JSON，不要说其他话。"))
        response = await llm.chat(messages, temperature=0.2)
        raw = response.content.strip()
        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
        cleaned = re.sub(r'```json\s*', '', raw)
        cleaned = re.sub(r'```\s*', '', cleaned)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find('{')
            if start == -1:
                raise ValueError("No JSON in retry output")
            depth = 0
            for i in range(start, len(cleaned)):
                if cleaned[i] == '{': depth += 1
                elif cleaned[i] == '}': depth -= 1
                if depth == 0:
                    data = json.loads(cleaned[start:i+1])
                    break
            else:
                raise ValueError("Unbalanced braces in retry")

        raw_ctx = data.get('context', {})
        context = {}
        for feat in _CRITIC_CONTEXT_KEYS:
            v = float(raw_ctx.get(feat, 0.5))
            context[feat] = max(-1.0, min(1.0, v)) if feat == 'user_emotion' else max(0.0, min(1.0, v))

        frustration_delta = {d: max(-3.0, min(3.0, float(data.get('frustration_delta', {}).get(d, 0.0)))) for d in DRIVES}
        rel_delta = {
            'relationship_delta': max(-1.0, min(1.0, float(data.get('relationship_delta', 0.0)))),
            'trust_delta': max(-1.0, min(1.0, float(data.get('trust_delta', 0.0)))),
            'emotional_valence': max(-1.0, min(1.0, float(data.get('emotional_valence', 0.0)))),
        }
        drive_satisfaction = {d: max(0.0, min(0.3, float(data.get('drive_satisfaction', {}).get(d, 0.0)))) for d in DRIVES}

        print(f"[critic] Retry succeeded")
        return context, frustration_delta, rel_delta, drive_satisfaction

    except (json.JSONDecodeError, ValueError, TypeError, Exception) as e:
        print(f"[critic] Parse error after retry: {e}")
        return dict(_DEFAULT_CONTEXT), dict(_DEFAULT_DELTA), dict(_DEFAULT_REL_DELTA), dict(_DEFAULT_SATISFACTION)
