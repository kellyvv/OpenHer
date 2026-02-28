"""
OutputRouter — API layer between ChatAgent and WebSocket/REST transport.

Responsibilities:
  1. Parse raw LLM output (【内心独白】/【最终回复】/【表达方式】)
  2. Clean reply text (strip parenthetical action descriptions)
  3. Route by modality: text → chat_chunk, voice → tts, sticker/photo → media
  4. Stream clean chunks to WebSocket caller

This is the single place where raw model output becomes a frontend event.
Adding new modalities (voice, sticker, photo) only requires changes here.
"""

from __future__ import annotations

import re
from typing import AsyncIterator, Callable, Awaitable, Any

# ── Parser constants ──
_REPLY_START = "【最终回复】"
_REPLY_END   = "【表达方式】"
_MODALITY_START = "【表达方式】"

# Strip parenthetical action descriptions: （偷偷松了口气） or (sighs quietly)
# No length cap — long inner monologue parens (e.g. 45+ chars) must also be stripped.
_PAREN_RE = re.compile(r'[（(][^（(）)]+[）)]')


def parse_raw_output(raw: str) -> dict:
    """
    Parse a complete raw LLM output string into structured fields.

    Returns:
        {
            "monologue": str,   # 内心独白
            "reply":    str,    # 最终回复 (cleaned)
            "modality": str,    # 表达方式 raw text
        }
    """
    monologue = ""
    reply = ""
    modality = ""

    parts = re.split(r'【(内心独白|最终回复|表达方式)】', raw)
    for i, part in enumerate(parts):
        if part == "内心独白" and i + 1 < len(parts):
            monologue = parts[i + 1].strip()
        elif part == "最终回复" and i + 1 < len(parts):
            reply = parts[i + 1].strip()
        elif part == "表达方式" and i + 1 < len(parts):
            modality = parts[i + 1].strip()

    reply = _clean_reply(reply)
    return {"monologue": monologue, "reply": reply, "modality": modality}


def _clean_reply(text: str) -> str:
    """Remove parenthetical action descriptions from reply text."""
    return _PAREN_RE.sub("", text).strip()


def _extract_primary_modality(modality_text: str) -> str:
    """
    Determine primary modality from 【表达方式】text.

    Priority order matches MODALITY_ENUM in chat_agent.py:
      静默 > 语音 > 表情 > 多条拆分 > 照片 > 文字 (default)
    """
    for modality in ("静默", "语音", "表情", "多条拆分", "照片"):
        if modality in modality_text:
            return modality
    return "文字"


# ── WebSocket send type alias ──
WsSend = Callable[[dict], Awaitable[None]]


async def stream_to_ws(
    raw_stream: AsyncIterator[str],
    ws_send: WsSend,
    *,
    on_reply_complete: Callable[[str, str], Awaitable[None]] | None = None,
) -> None:
    """
    Stream raw LLM output through the output router to a WebSocket.

    Streaming only extracts the 【最终回复】section (no per-chunk cleaning —
    unreliable when parentheticals span chunk boundaries).

    Full cleaning (strip action descriptions) is applied once on the complete
    text via on_reply_complete → parse_raw_output → _clean_reply.

    Args:
        raw_stream:        AsyncIterator of raw LLM chunks from chat_agent
        ws_send:           Coroutine to send a dict to the WebSocket
        on_reply_complete: Callback(clean_reply, modality) after full stream
    """
    buf = ""
    in_reply = False
    done_reply = False
    full_raw: list[str] = []

    async for chunk in raw_stream:
        full_raw.append(chunk)
        if done_reply:
            continue

        buf += chunk

        if not in_reply:
            idx = buf.find(_REPLY_START)
            if idx != -1:
                in_reply = True
                buf = buf[idx + len(_REPLY_START):]
            else:
                if len(buf) > len(_REPLY_START) * 2:
                    buf = buf[-len(_REPLY_START):]
                continue

        # in_reply: don't yield to frontend during streaming
        # Just extract to know when 【表达方式】arrives
        end_idx = buf.find(_REPLY_END)
        if end_idx != -1:
            done_reply = True
            buf = ""

    # ── Post-stream: parse full output, clean once, fire callback ──
    if on_reply_complete:
        raw_text = "".join(full_raw)
        parsed = parse_raw_output(raw_text)   # _clean_reply applied here on full text
        modality = _extract_primary_modality(parsed["modality"])

        # Future modality routing hooks:
        # if modality == "语音": await _route_voice(...)
        # elif modality == "表情": await _route_sticker(...)
        # elif modality == "照片": await _route_photo(...)
        # elif modality == "静默": return  # no reply

        await on_reply_complete(parsed["reply"], modality)

