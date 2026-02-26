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
_PAREN_RE = re.compile(r'[（(][^（(）)]{1,40}[）)]')


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

    Filters to 【最终回复】section, strips action descriptions,
    and sends clean chat_chunk events. After streaming, routes by modality.

    Args:
        raw_stream:        AsyncIterator of raw LLM chunks from chat_agent
        ws_send:           Coroutine to send a dict to the WebSocket
        on_reply_complete: Optional callback(reply_text, modality) after full reply parsed
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
                # Keep tail to handle markers split across chunks
                if len(buf) > len(_REPLY_START) * 2:
                    buf = buf[-len(_REPLY_START):]
                continue

        if in_reply:
            end_idx = buf.find(_REPLY_END)
            if end_idx != -1:
                to_send = _clean_reply(buf[:end_idx].lstrip("\n"))
                if to_send:
                    await ws_send({"type": "chat_chunk", "content": to_send})
                done_reply = True
                buf = ""
            else:
                safe_len = max(0, len(buf) - len(_REPLY_END))
                to_send = _clean_reply(buf[:safe_len])
                if to_send:
                    await ws_send({"type": "chat_chunk", "content": to_send})
                buf = buf[safe_len:]

    # Flush remaining if no end marker
    if in_reply and buf and not done_reply:
        to_send = _clean_reply(buf)
        if to_send:
            await ws_send({"type": "chat_chunk", "content": to_send})

    # ── Modality routing (post-stream) ──
    if on_reply_complete:
        raw_text = "".join(full_raw)
        parsed = parse_raw_output(raw_text)
        modality = _extract_primary_modality(parsed["modality"])

        # Future modality routing hooks go here:
        # if modality == "语音":
        #     await _route_voice(parsed["reply"], ws_send, tts_engine)
        # elif modality == "表情":
        #     await _route_sticker(parsed["reply"], ws_send)
        # elif modality == "照片":
        #     await _route_photo(ws_send)
        # elif modality == "静默":
        #     pass  # No reply

        await on_reply_complete(parsed["reply"], modality)
