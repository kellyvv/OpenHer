"""
Voice tools — atomic tools for voice message generation.

Migrated from skills/modality/voice_msg/handler.py.
Registered into ToolRegistry at startup.

Note: voice_preset is pre-resolved by the engine and injected into
the LLM system prompt. The tool receives it as a parameter.
"""

from __future__ import annotations

import os
from pathlib import Path

from agent.skills.tool_registry import Tool, ToolRegistry


# ── Tool: synthesize_voice ──

async def _synthesize_voice(
    text: str,
    voice_preset: str = "",
    emotion_instruction: str = "",
) -> dict:
    """Synthesize a voice message using TTS provider.

    Args:
        text: The text content to speak.
        voice_preset: TTS voice ID (e.g. "Cherry", "Maia"). Pre-resolved by engine.
        emotion_instruction: Detailed emotion control instruction for TTS.

    Returns:
        {success: bool, audio_path: str | null, error: str | null}
    """
    if not text:
        return {"success": False, "audio_path": None, "error": "No text provided"}

    voice_name = voice_preset or "Cherry"  # default fallback

    print(f"  [tool] 🎤 synthesize_voice: voice={voice_name}, text={text[:40]}...")
    if emotion_instruction:
        print(f"  [tool] 💭 emotion={emotion_instruction[:60]}...")

    try:
        from providers.registry import get_tts

        cache_dir = str(
            Path(__file__).resolve().parents[3] / ".cache" / "voice"
        )
        os.makedirs(cache_dir, exist_ok=True)

        provider = get_tts(cache_dir=cache_dir)

        result = await provider.synthesize(
            text=text,
            voice_name=voice_name,
            emotion_instruction=emotion_instruction or None,
        )

        if result.success and result.audio_path:
            print(f"  [tool] ✅ Audio generated: {result.audio_path}")
            return {
                "success": True,
                "audio_path": result.audio_path,
                "error": None,
            }
        else:
            error_msg = getattr(result, "error", "Unknown error")
            print(f"  [tool] ❌ TTS failed: {error_msg}")
            return {"success": False, "audio_path": None, "error": str(error_msg)}

    except Exception as e:
        print(f"  [tool] ❌ synthesize_voice error: {e}")
        return {"success": False, "audio_path": None, "error": str(e)}


# ── Registration ──

def register_voice_tools(registry: ToolRegistry) -> None:
    """Register voice tools into the global registry."""

    registry.register(Tool(
        name="synthesize_voice",
        description="生成语音消息。根据文本内容和情绪指令合成语音。",
        parameters={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "角色要说的话（实际台词内容）",
                },
                "voice_preset": {
                    "type": "string",
                    "description": "TTS 音色 ID（由系统预设，通常不需要指定）",
                },
                "emotion_instruction": {
                    "type": "string",
                    "description": "详细的情绪控制指令，描述语速、语调、音色、呼吸感等",
                },
            },
            "required": ["text", "emotion_instruction"],
        },
        handler=_synthesize_voice,
    ))
