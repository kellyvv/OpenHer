"""
Split message tools — atomic tool for multi-message splitting.

Registered into ToolRegistry at startup.
Pure text processing, no external service calls.
"""

from __future__ import annotations

from agent.skills.tool_registry import Tool, ToolRegistry


# ── Tool: split_messages ──

async def _split_messages(
    text: str,
    delays_ms: list[int] | None = None,
    delay_ms_per_char: int = 80,
) -> dict:
    """Split a reply into multiple message segments.

    Args:
        text: Reply text with \\n\\n separators between segments.
        delays_ms: Optional LLM-provided delays (ms) per segment.
        delay_ms_per_char: Fallback: milliseconds per character for typing delay.

    Returns:
        {success: bool, segments: list[str], delays_ms: list[int]}
    """
    if not text:
        return {"success": False, "segments": [], "delays_ms": []}

    # Split by double newline, filter empty
    raw_segments = text.split("\n\n")
    segments = [s.strip() for s in raw_segments if s.strip()]

    if len(segments) <= 1:
        return {"success": False, "segments": segments, "delays_ms": [0]}

    # Use LLM-provided delays if available and length matches
    if delays_ms and len(delays_ms) == len(segments):
        final_delays = [max(0, min(d, 6000)) for d in delays_ms]
    else:
        # Fallback: formula-based delays
        final_delays = [0]
        for seg in segments[1:]:
            delay = len(seg) * delay_ms_per_char
            delay = max(800, min(delay, 3000))
            final_delays.append(delay)

    print(f"  [tool] ✂️ split_messages: {len(segments)} segments, delays={final_delays}")

    return {
        "success": True,
        "segments": segments,
        "delays_ms": final_delays,
    }


# ── Registration ──

def register_split_tools(registry: ToolRegistry) -> None:
    """Register split message tools into the global registry."""

    registry.register(Tool(
        name="split_messages",
        description="将回复拆分为多条消息，模拟真人打字节奏。",
        parameters={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "含 \\n\\n 分隔的角色回复原文",
                },
                "delays_ms": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "每段消息发送前的等待毫秒数",
                },
            },
            "required": ["text"],
        },
        handler=_split_messages,
    ))
