"""
ModalitySkillEngine — Load and execute persona-intrinsic modality skills.

Modality skills (照片, 语音, etc.) are persona expressions triggered by
the Express pass. They are isolated from task skills (weather, search, etc.).

Lifecycle:
  L1  build_prompt()  → inject descriptions into Express prompt
  L2  activate()      → load SKILL.md body on first use
  L3  execute()       → LLM generates params → dynamic handler dispatch
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Optional

import frontmatter

from agent.skills.skill_types import (
    SKILL_FILENAME,
    ExecutionStatus,
    Skill,
    SkillExecutionResult,
    load_skill,
)


class ModalitySkillEngine:
    """Persona-intrinsic skill engine for modality-triggered skills."""

    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, Skill] = {}

    # -- Loading (L1) -------------------------------------------------------

    def load_all(self) -> dict[str, Skill]:
        """Load L1 metadata for trigger=modality skills only."""
        self._skills.clear()
        if not self.skills_dir.exists():
            return {}

        for entry in sorted(self.skills_dir.iterdir()):
            if entry.is_dir():
                skill_file = entry / SKILL_FILENAME
                if skill_file.exists():
                    try:
                        skill = load_skill(entry)
                        if skill.trigger == "modality" and skill.modality:
                            self._skills[skill.skill_id] = skill
                    except Exception as e:
                        print(f"[modality-skill] Failed to load {entry.name}: {e}")
        return self._skills

    # -- L2 activation -------------------------------------------------------

    def activate(self, skill_id: str) -> None:
        """Load L2 body (SKILL.md content) for a skill. Idempotent."""
        skill = self._skills.get(skill_id)
        if not skill or skill.is_activated:
            return
        post = frontmatter.load(str(Path(skill.base_dir) / SKILL_FILENAME))
        skill.body = post.content.strip()

    # -- Queries --------------------------------------------------------------

    @property
    def modality_skills(self) -> dict[str, str]:
        """Map modality name → skill_id.
        Used for quick lookup: `if modality in engine.modality_skills`
        """
        return {
            s.modality: s.skill_id
            for s in self._skills.values()
        }

    def get_by_modality(self, modality: str) -> Optional[Skill]:
        """Find the skill bound to a given modality."""
        skill_id = self.modality_skills.get(modality)
        return self._skills.get(skill_id) if skill_id else None

    def build_prompt(self) -> str:
        """Build L1 prompt section from modality skills for Express injection."""
        skills = list(self._skills.values())
        if not skills:
            return ""
        parts = ["# 技能指南"]
        for skill in skills:
            if skill.description:
                parts.append(f"\n## {skill.name}\n{skill.description}")
        return "\n".join(parts)

    # -- Execution (L3) -------------------------------------------------------

    async def execute(
        self,
        modality: str,
        raw_output: str,
        persona,
        llm,
    ) -> Optional[SkillExecutionResult]:
        """Execute a modality skill: L2 activate → LLM params → handler dispatch.

        Args:
            modality:   The modality keyword (e.g. "照片", "语音").
            raw_output: Full Express pass raw LLM output.
            persona:    The Persona object (for voice config etc).
            llm:        LLMClient instance for L2 parameter generation.
        """
        skill = self.get_by_modality(modality)
        if not skill or not skill.handler_fn:
            return None

        if not skill.is_activated:
            self.activate(skill.skill_id)

        try:
            # L2: LLM reads skill body → generates structured parameters
            from providers.llm.base import ChatMessage

            system_msg = ChatMessage("system",
                f"根据以下技能文档和角色回复上下文，生成该技能的结构化输出。\n"
                f"只输出结构化内容，不要多余解释。\n\n{skill.body}"
            )
            user_msg = ChatMessage("user",
                f"角色回复：{raw_output}\n角色名：{persona.name}"
            )
            prompt_resp = await llm.chat([system_msg, user_msg], temperature=0.3)
            structured_output = prompt_resp.content

            print(f"  [modality-skill] 🎯 {skill.name}: structured output ready")

            # L3: Dynamic handler dispatch via handler_fn
            module_path, fn_name = skill.handler_fn.rsplit('.', 1)
            mod = importlib.import_module(module_path)
            handler = getattr(mod, fn_name)

            result = await handler(
                persona_id=persona.persona_id,
                raw_output=structured_output,
                persona_name=persona.name,
                voice_preset=getattr(persona.voice, 'voice_preset', '') or '',
                base_instructions=getattr(persona.voice, 'base_instructions', '') or '',
            )

            success = result.get("success", False)
            if success:
                print(f"  [modality-skill] ✅ {skill.name} completed")
            else:
                print(f"  [modality-skill] ❌ {skill.name} failed: {result.get('error')}")

            return SkillExecutionResult(
                skill_id=skill.skill_id,
                success=success,
                status=ExecutionStatus.COMPLETED if success else ExecutionStatus.FAILED,
                output=result,
            )

        except Exception as e:
            print(f"  [modality-skill] ❌ Exception in {skill.name}: {e}")
            return SkillExecutionResult(
                skill_id=skill.skill_id,
                success=False,
                status=ExecutionStatus.FAILED,
                output={"error": str(e)},
            )
