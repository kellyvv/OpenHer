"""
TaskSkillEngine — Load and execute task-oriented skills (trigger=tool).

Task skills (weather, search, etc.) are user-driven and executed via sandbox.
They are isolated from persona-intrinsic modality skills (photo, voice).

Execution: LLM generates a shell command → sandbox runs it → returns stdout/stderr.
"""

from __future__ import annotations

import re
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


class TaskSkillEngine:
    """Task-oriented skill engine for tool-triggered skills."""

    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, Skill] = {}

    # -- Loading ---------------------------------------------------------------

    def load_all(self) -> dict[str, Skill]:
        """Load L1 metadata for trigger=tool skills only."""
        self._skills.clear()
        if not self.skills_dir.exists():
            return {}

        for entry in sorted(self.skills_dir.iterdir()):
            if entry.is_dir():
                skill_file = entry / SKILL_FILENAME
                if skill_file.exists():
                    try:
                        skill = load_skill(entry)
                        if skill.trigger == "tool":
                            self._skills[skill.skill_id] = skill
                    except Exception as e:
                        print(f"[task-skill] Failed to load {entry.name}: {e}")
        return self._skills

    # -- L2 activation ---------------------------------------------------------

    def activate(self, skill_id: str) -> None:
        """Load L2 body (SKILL.md content) for a skill. Idempotent."""
        skill = self._skills.get(skill_id)
        if not skill or skill.is_activated:
            return
        post = frontmatter.load(str(Path(skill.base_dir) / SKILL_FILENAME))
        skill.body = post.content.strip()

    # -- Queries ---------------------------------------------------------------

    def get(self, skill_id: str) -> Optional[Skill]:
        if not self._skills:
            self.load_all()
        return self._skills.get(skill_id)

    @property
    def tool_skills(self) -> list[Skill]:
        """List of trigger:tool skills."""
        return [s for s in self._skills.values() if s.trigger == "tool"]

    def get_cron_skills(self) -> list[Skill]:
        """Get all skills with cron triggers (loaded alongside tool skills)."""
        # Cron skills are loaded in a separate pass if needed
        if not self._skills:
            self.load_all()
        return [s for s in self._skills.values() if s.trigger == "cron" and s.cron_schedule]

    def build_skill_declarations(self) -> list[dict]:
        """Convert tool_skills to OpenAI function calling format."""
        if not self._skills:
            self.load_all()
        return [{
            "type": "function",
            "function": {
                "name": skill.skill_id,
                "description": skill.description,
                "parameters": {"type": "object", "properties": {}},
            }
        } for skill in self.tool_skills]

    # -- Execution -------------------------------------------------------------

    async def execute(self, skill_id: str, user_intent: str, llm) -> SkillExecutionResult:
        """Execute a task skill: body → LLM generates command → sandbox runs.

        Args:
            skill_id: ID of the skill to execute.
            user_intent: Original user message.
            llm: LLMClient instance for command generation.
        """
        from providers.llm.base import ChatMessage

        skill_id = skill_id.lower()
        skill = self._skills.get(skill_id)
        if not skill:
            return SkillExecutionResult(
                skill_id=skill_id, success=False,
                status=ExecutionStatus.FAILED,
                output={"error": f"Unknown skill: {skill_id}"},
            )
        if not skill.is_activated:
            self.activate(skill_id)

        if not skill.body:
            return SkillExecutionResult(
                skill_id=skill_id, success=False,
                status=ExecutionStatus.FAILED,
                output={"error": "Skill body is empty", "stdout": "", "stderr": "", "returncode": -1},
            )

        # LLM generates shell command from body + user intent
        system_msg = ChatMessage("system",
            f"根据以下技能文档，为用户请求生成一条可执行的 shell 命令。\n"
            f"只输出命令本身，不要解释，不要 markdown 格式。\n\n"
            f"## 技能文档\n{skill.body}"
        )
        user_msg = ChatMessage("user", user_intent)
        resp = await llm.chat([system_msg, user_msg], temperature=0.1)

        # Clean markdown code block wrapping
        content = resp.content.strip()
        content = re.sub(r'^```\w*\n?', '', content)
        content = re.sub(r'\n?```$', '', content)
        command = content.strip()

        if not command:
            return SkillExecutionResult(
                skill_id=skill_id, success=False,
                status=ExecutionStatus.FAILED,
                output={"error": "LLM generated empty command", "stdout": "", "stderr": "", "returncode": -1},
            )

        from agent.skills.sandbox_executor import execute_shell
        result = await execute_shell(command)

        return SkillExecutionResult(
            skill_id=skill_id,
            success=result["success"],
            status=ExecutionStatus.COMPLETED if result["success"] else ExecutionStatus.FAILED,
            output={**result, "command": command},
        )
