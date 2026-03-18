"""
OutputRouter — API layer between ChatAgent and WebSocket/REST transport.

Responsibilities:
  1. Parse raw LLM output (【内心独白】/【最终回复】/【表达方式】 or [Inner Monologue]/[Final Reply]/[Expression Mode])
  2. Clean reply text (strip parenthetical action descriptions)
  3. Route by modality: text → chat_chunk, voice → tts, sticker/photo → media
  4. Stream clean chunks to WebSocket caller

This is the single place where raw model output becomes a frontend event.
Adding new modalities (voice, sticker, photo) only requires changes here.
"""

from __future__ import annotations

import re
from typing import AsyncIterator, Callable, Awaitable, Any

from agent.parser import extract_reply

# ── Streaming marker constants ──
_REPLY_STARTS = ("【最终回复】", "[Final Reply]")
_REPLY_ENDS   = ("【表达方式】", "[Expression Mode]")
_MAX_MARKER_LEN = max(
    max(len(m) for m in _REPLY_STARTS),
    max(len(m) for m in _REPLY_ENDS),
)


def parse_raw_output(raw: str) -> dict:
    """
    Parse a complete raw LLM output string into structured fields.

    Delegates to parser.extract_reply for unified parsing logic.

    Returns:
        {
            "monologue": str,
            "reply":    str,    (cleaned, with empty-value fallback)
            "modality": str,
        }
    """
    monologue, reply, modality = extract_reply(raw)
    return {
        "monologue": monologue,
        "reply": reply,
        "modality": modality,
    }


# _extract_primary_modality removed — parser.extract_reply handles modality parsing.


# ── WebSocket send type alias ──
WsSend = Callable[[dict], Awaitable[None]]


async def stream_to_ws(
    raw_stream: AsyncIterator[str],
    ws_send: WsSend,
    *,
    on_feel_done: Callable[[], Awaitable[None]] | None = None,
    on_reply_complete: Callable[[str, str], Awaitable[None]] | None = None,
) -> None:
    """
    Stream raw LLM output through the output router to a WebSocket.

    Streaming extracts the 【最终回复】 / [Final Reply] section.
    No per-chunk cleaning — unreliable when parentheticals span chunk boundaries.

    Full cleaning (strip action descriptions) is applied once on the complete
    text via on_reply_complete → parse_raw_output → _clean_reply.

    Args:
        raw_stream:        AsyncIterator of raw LLM chunks from chat_agent
        ws_send:           Coroutine to send a dict to the WebSocket
        on_feel_done:      Callback when Feel pass completes (before Express starts)
        on_reply_complete: Callback(clean_reply, modality) after full stream
    """
    buf = ""
    in_reply = False
    done_reply = False
    full_raw: list[str] = []

    async for chunk in raw_stream:
        # Intercept Feel-done sentinel (not a real chunk)
        if chunk == "__FEEL_DONE__":
            if on_feel_done:
                await on_feel_done()
            continue

        full_raw.append(chunk)
        if done_reply:
            continue

        buf += chunk

        if not in_reply:
            for marker in _REPLY_STARTS:
                idx = buf.find(marker)
                if idx != -1:
                    in_reply = True
                    buf = buf[idx + len(marker):]
                    break
            else:
                # Keep tail to catch markers split across chunks
                if len(buf) > _MAX_MARKER_LEN * 2:
                    buf = buf[-_MAX_MARKER_LEN:]
                continue

        # in_reply: check for end marker
        for marker in _REPLY_ENDS:
            end_idx = buf.find(marker)
            if end_idx != -1:
                done_reply = True
                buf = ""
                break

    # ── Post-stream: parse full output via unified parser, fire callback ──
    if on_reply_complete:
        raw_text = "".join(full_raw)
        parsed = parse_raw_output(raw_text)
        modality = parsed["modality"]

        await on_reply_complete(parsed["reply"], modality)

