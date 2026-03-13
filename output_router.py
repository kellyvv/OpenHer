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

# ── Parser constants (bilingual: Chinese primary, English fallback) ──
_REPLY_STARTS = ("【最终回复】", "[Final Reply]")
_REPLY_ENDS   = ("【表达方式】", "[Expression Mode]")
_MAX_MARKER_LEN = max(
    max(len(m) for m in _REPLY_STARTS),
    max(len(m) for m in _REPLY_ENDS),
)

# Strip parenthetical action descriptions: （偷偷松了口气） or (sighs quietly)
_PAREN_RE = re.compile(r'[（(][^（(）)]{1,40}[）)]')

# Section header regex (shared with chat_agent.py)
_SECTION_RE = re.compile(
    r'(?:【(?P<zh>内心独白|最终回复|表达方式)】'
    r'|\[(?P<en>Inner Monologue|Final Reply|Expression Mode)\])'
)
_TAG_MAP = {
    '内心独白': 'monologue', 'Inner Monologue': 'monologue',
    '最终回复': 'reply',     'Final Reply': 'reply',
    '表达方式': 'modality',  'Expression Mode': 'modality',
}

# Bilingual modality normalization (canonical = Chinese key)
_MODALITY_MAP = {
    "静默": "静默", "silence": "静默",
    "文字": "文字", "text": "文字",
    "语音": "语音", "voice": "语音",
    "表情": "表情", "emoji": "表情",
    "多条拆分": "多条拆分", "split": "多条拆分",
    "照片": "照片", "photo": "照片",
}


def parse_raw_output(raw: str) -> dict:
    """
    Parse a complete raw LLM output string into structured fields.

    Supports both Chinese (【最终回复】) and English ([Final Reply]) section headers.

    Returns:
        {
            "monologue": str,
            "reply":    str,    (cleaned)
            "modality": str,    (canonical Chinese key)
        }
    """
    sections: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(raw))
    for i, m in enumerate(matches):
        tag = m.group('zh') or m.group('en')
        key = _TAG_MAP[tag]
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        sections[key] = raw[start:end].strip()

    reply = _clean_reply(sections.get('reply', ''))
    return {
        "monologue": sections.get('monologue', ''),
        "reply": reply,
        "modality": sections.get('modality', ''),
    }


def _clean_reply(text: str) -> str:
    """Remove parenthetical action descriptions from reply text."""
    return _PAREN_RE.sub("", text).strip()


def _extract_primary_modality(modality_text: str) -> str:
    """
    Determine primary modality from 表达方式 text.

    Supports both Chinese and English modality tokens.
    Priority order: 静默 > 语音 > 表情 > 多条拆分 > 照片 > 文字 (default)
    """
    lowered = modality_text.strip().lower()
    for token, canonical in _MODALITY_MAP.items():
        if token in lowered and canonical != "文字":
            return canonical
    return "文字"


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

