"""
SkillEngine — Load and execute companion skills from SKILL.md files.

Each skill is a directory with a SKILL.md (YAML frontmatter + instructions)
and optionally Python handler scripts. Skills can be triggered by:
  - Cron schedule (proactive outreach)
  - LLM tool-call (agent-invoked)
  - User command (explicit invocation)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import frontmatter


@dataclass
class Skill:
    """Loaded skill definition."""
    skill_id: str
    name: str
    description: str = ""
    trigger: str = "manual"          # manual | cron | auto
    cron_schedule: Optional[str] = None  # e.g. "0 8 * * *" for 8am daily
    requires: list[str] = field(default_factory=list)  # tool dependencies
    tags: list[str] = field(default_factory=list)
    prompt_injection: str = ""       # Instructions to inject into system prompt
    handler: Optional[str] = None    # Python handler module path
    base_dir: str = ""


class SkillEngine:
    """Load and manage companion skills."""

    SKILL_FILENAME = "SKILL.md"

    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, Skill] = {}

    def load_all(self) -> dict[str, Skill]:
        """Load all skills from the skills directory."""
        self._skills.clear()
        if not self.skills_dir.exists():
            return {}

        for entry in sorted(self.skills_dir.iterdir()):
            if entry.is_dir():
                skill_file = entry / self.SKILL_FILENAME
                if skill_file.exists():
                    try:
                        skill = self._load_one(entry)
                        self._skills[skill.skill_id] = skill
                    except Exception as e:
                        print(f"[skill] Failed to load {entry.name}: {e}")
        return self._skills

    def get(self, skill_id: str) -> Optional[Skill]:
        if not self._skills:
            self.load_all()
        return self._skills.get(skill_id)

    def get_cron_skills(self) -> list[Skill]:
        """Get all skills with cron triggers."""
        if not self._skills:
            self.load_all()
        return [s for s in self._skills.values() if s.trigger == "cron" and s.cron_schedule]

    def get_auto_skills(self) -> list[Skill]:
        """Get skills that should be auto-injected into every prompt."""
        if not self._skills:
            self.load_all()
        return [s for s in self._skills.values() if s.trigger == "auto"]

    def build_skills_prompt(self) -> str:
        """Build a combined prompt section from all auto skills."""
        auto_skills = self.get_auto_skills()
        if not auto_skills:
            return ""
        parts = ["# 技能指南"]
        for skill in auto_skills:
            if skill.prompt_injection:
                parts.append(f"\n## {skill.name}\n{skill.prompt_injection}")
        return "\n".join(parts)

    def _load_one(self, skill_dir: Path) -> Skill:
        skill_file = skill_dir / self.SKILL_FILENAME
        post = frontmatter.load(str(skill_file))
        meta = post.metadata

        return Skill(
            skill_id=skill_dir.name,
            name=meta.get("name", skill_dir.name),
            description=meta.get("description", ""),
            trigger=meta.get("trigger", "manual"),
            cron_schedule=meta.get("cron"),
            requires=meta.get("requires", []),
            tags=meta.get("tags", []),
            prompt_injection=post.content.strip(),
            handler=meta.get("handler"),
            base_dir=str(skill_dir),
        )
