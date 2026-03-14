"""
Voice message handler — parse LLM structured output and call DashScope TTS.

Called by ModalitySkillEngine.execute() via dynamic dispatch.
"""

from __future__ import annotations

import os
import re
import time
from typing import Optional


def parse_voice_output(raw_output: str) -> dict:
    """Parse LLM structured output into emotion_instruction + text.
    
    Expected format:
        语音｜情绪指令：[情绪控制指令]
        内容：[合成文字]
    """
    result = {
        "emotion_instruction": "",
        "text": "",
    }

    # Match emotion instruction
    instr_match = re.search(
        r'(?:情绪指令|情绪控制|指令)[：:]\s*(.+?)(?:\n|$)',
        raw_output,
        re.DOTALL,
    )
    if instr_match:
        result["emotion_instruction"] = instr_match.group(1).strip()

    # Match content
    content_match = re.search(
        r'(?:内容|文本|台词)[：:]\s*(.+?)(?:\n|$)',
        raw_output,
        re.DOTALL,
    )
    if content_match:
        result["text"] = content_match.group(1).strip()

    # Fallback: if no structured format, use entire output as text
    if not result["text"] and raw_output.strip():
        # Try to extract anything after the last colon
        lines = [l.strip() for l in raw_output.strip().split("\n") if l.strip()]
        if lines:
            result["text"] = lines[-1]

    return result


async def generate_voice(
    persona_id: str,
    raw_output: str,
    persona_name: str = "",
    voice_preset: str = "",
    base_instructions: str = "",
    **kwargs,
) -> dict:
    """Generate a voice message from LLM structured output.

    Called by ModalitySkillEngine.execute() — unified handler interface.

    Args:
        persona_id: Persona ID for cache path organization.
        raw_output: LLM structured output to parse (emotion_instruction + text).
        persona_name: Display name (unused but part of interface).
        voice_preset: TTS voice ID (e.g. "Maia", "Bella").
        base_instructions: Persona base TTS instructions to merge with emotion.
    
    Returns:
        dict with keys: success, audio_path, error
    """
    # 1. Parse structured output
    parsed = parse_voice_output(raw_output)
    text = parsed["text"]
    emotion_instruction = parsed["emotion_instruction"]

    if not text:
        return {"success": False, "audio_path": None, "error": "No text found in output"}

    # 2. Merge base_instructions + emotion_instruction
    instructions_parts = []
    if base_instructions:
        instructions_parts.append(base_instructions)
    if emotion_instruction:
        instructions_parts.append(emotion_instruction)
    merged_instructions = "\n".join(instructions_parts) if instructions_parts else None

    # 3. Resolve voice name
    voice_name = voice_preset or "Cherry"  # default fallback

    print(f"  [voice] 🎤 voice={voice_name}, text={text[:40]}...")
    if merged_instructions:
        print(f"  [voice] 💭 instructions={merged_instructions[:60]}...")

    # 4. Call DashScope TTS
    try:
        from providers.speech.tts.dashscope import DashScopeTTSProvider

        # Generate cache path
        cache_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            ".cache", "voice", persona_id,
        )
        os.makedirs(cache_dir, exist_ok=True)

        provider = DashScopeTTSProvider(cache_dir=cache_dir)

        result = await provider.synthesize(
            text=text,
            voice_name=voice_name,
            emotion_instruction=merged_instructions,
        )

        if result.success and result.audio_path:
            print(f"  [voice] ✅ Audio generated: {result.audio_path}")
            return {
                "success": True,
                "audio_path": result.audio_path,
                "error": None,
            }
        else:
            error_msg = getattr(result, 'error', 'Unknown error')
            print(f"  [voice] ❌ TTS failed: {error_msg}")
            return {"success": False, "audio_path": None, "error": str(error_msg)}

    except Exception as e:
        print(f"  [voice] ❌ Exception: {e}")
        return {"success": False, "audio_path": None, "error": str(e)}
