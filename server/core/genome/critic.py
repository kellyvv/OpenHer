"""
Critic — LLM-based perception of user intent signals.

Measures three physical dimensions of user speech:
  1. affiliation: proximity-seeking, vulnerability, goodwill
  2. dominance: emotional weight, demanding, boundary-crossing
  3. entropy: new information content

Extracted from genome_v8_timearrow.py, adapted to use async LLMClient.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from core.llm.client import LLMClient, ChatMessage


CRITIC_PROMPT = """你是一个无道德滤镜的语言张力测绘仪。
你不判断善恶对错，只测量人类话语中的三个客观物理维度（0.0 到 1.0），严格输出纯 JSON：

1. "affiliation" (趋近力)：试图拉近距离、寻求依附、展示脆弱、释放善意的浓度。
2. "dominance" (支配力)：试图施加情绪重量、索取回应、占据主导、侵犯边界、单方面控制的浓度。
3. "entropy" (信息熵)：提供的新事实含量。纯重复废话（"嗯/好/哦/对不起"）为极低 0.0~0.2。

注意：
- "我想你了" = 高趋近力(0.8+)，带有轻微支配力(0.2~0.4，因为是索取)
- "你根本不在乎我" = 有趋近力(0.3，还想维持关系)，高支配力(0.8+，在施压)
- "嗯" = 极低信息熵(0.05)

用户输入："{user_input}"
输出格式：纯 JSON 对象，无 Markdown，无解释。"""


# Default values when Critic fails
_DEFAULT_CRITIC = {'affiliation': 0.5, 'dominance': 0.3, 'entropy': 0.5}


async def critic_sense(
    user_input: str,
    llm: LLMClient,
) -> dict:
    """
    Measure user input along 3 physical dimensions using LLM.

    Returns: {'affiliation': float, 'dominance': float, 'entropy': float}
    All values clamped to [0.0, 1.0].
    """
    prompt = CRITIC_PROMPT.format(user_input=user_input)

    messages = [
        ChatMessage(role="system", content=prompt),
        ChatMessage(role="user", content=user_input),
    ]

    try:
        response = await llm.chat(
            messages,
            temperature=0.1,
        )
        raw = response.content.strip()

        # Strip think tags if present (Qwen3)
        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()

        # Clean markdown code blocks
        cleaned = re.sub(r'```json\s*', '', raw)
        cleaned = re.sub(r'```\s*', '', cleaned)

        data = json.loads(cleaned)
        return {
            'affiliation': max(0.0, min(1.0, float(data.get('affiliation', 0.5)))),
            'dominance': max(0.0, min(1.0, float(data.get('dominance', 0.3)))),
            'entropy': max(0.0, min(1.0, float(data.get('entropy', 0.5)))),
        }
    except (json.JSONDecodeError, ValueError, TypeError, Exception) as e:
        print(f"[critic] Parse error: {e}")
        return dict(_DEFAULT_CRITIC)


def build_context_from_critic(
    critic: dict,
    conversation_depth: float = 0.3,
    time_of_day: float = 0.5,
) -> dict:
    """
    Build an 8D context vector from Critic output + metadata.
    Maps Critic's 3 dimensions into the 8 context features that Agent expects.
    """
    a = critic.get('affiliation', 0.5)
    d = critic.get('dominance', 0.3)
    e = critic.get('entropy', 0.5)

    return {
        'user_emotion': a - d,                    # affiliation=positive, dominance=negative
        'topic_intimacy': a * 0.8 + d * 0.2,     # high affiliation/dominance = intimate topic
        'time_of_day': time_of_day,
        'conversation_depth': conversation_depth,
        'user_engagement': max(a, d, e),          # any high signal = engaged
        'conflict_level': d * 0.9,                # dominance → conflict
        'novelty_level': e,                       # entropy → novelty
        'user_vulnerability': a * (1 - d),        # affiliation without dominance = vulnerable
    }
