"""
SkillEngine — Load and execute companion skills from SKILL.md files.

Each skill is a directory with a SKILL.md (YAML frontmatter + instructions)
and optionally Python handler scripts. Skills can be triggered by:
  - modality  → persona intrinsic (selfie, voice, ...), triggered by Express modality emergence
  - tool      → task execution, registered as Feel pass LLM tools (Stage 2)
  - cron      → proactive outreach on schedule
  - manual    → explicit user invocation
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import frontmatter


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Skill:
    """Loaded skill definition (L1 metadata from SKILL.md frontmatter)."""
    skill_id: str
    name: str
    description: str = ""
    trigger: str = "manual"          # modality | tool | cron | manual
    modality: str = ""               # bound modality (e.g. "照片") for trigger:modality skills
    executor: str = "handler"        # handler | sandbox
    handler_fn: str = ""             # Python entry point (e.g. skills.selfie_gen.handler.generate_selfie)
    resources: list[str] = field(default_factory=list)  # dir names = type convention (idimage/)
    base_dir: str = ""
    body: Optional[str] = None       # L2 instructions (lazy-loaded by activate())

    # deprecated — kept for backward compat
    handler: Optional[str] = None
    cron_schedule: Optional[str] = None
    requires: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def is_activated(self) -> bool:
        """L2 body has been loaded."""
        return self.body is not None


class ExecutionStatus(Enum):
    """Skill execution state machine."""
    COMPLETED = "completed"
    NEEDS_INFO = "needs_info"
    IN_PROGRESS = "in_progress"
    FAILED = "failed"


@dataclass
class SkillExecutionResult:
    """Result of a skill execution."""
    skill_id: str
    success: bool
    status: ExecutionStatus
    output: dict
    next_skills: list[str] = field(default_factory=list)  # Stage 2: chaining placeholder


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class SkillEngine:
    """Load and manage companion skills with L1/L2/L3 progressive disclosure."""

    SKILL_FILENAME = "SKILL.md"

    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, Skill] = {}

    # -- L1 loading --------------------------------------------------------

    def load_all(self) -> dict[str, Skill]:
        """Load L1 metadata (frontmatter only) for all skills. Body is NOT loaded."""
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

    def _load_one(self, skill_dir: Path) -> Skill:
        """Parse SKILL.md frontmatter into Skill (L1 only, body=None)."""
        skill_file = skill_dir / self.SKILL_FILENAME
        post = frontmatter.load(str(skill_file))
        meta = post.metadata

        # trigger: smart default for OpenClaw compat
        trigger = meta.get("trigger", "")
        if not trigger:
            has_scripts = (skill_dir / "scripts").exists()
            trigger = "tool" if has_scripts else "manual"

        # executor: infer from trigger
        executor = meta.get("executor", "")
        if not executor:
            executor = "sandbox" if trigger == "tool" else "handler"

        # handler_fn: prefer new field, fallback to legacy
        handler_fn = (
            meta.get("handler_fn")
            or meta.get("handler_module")
            or meta.get("handler")
            or ""
        )

        return Skill(
            skill_id=skill_dir.name,
            name=meta.get("name", skill_dir.name),
            description=meta.get("description", ""),
            trigger=trigger,
            modality=meta.get("modality", ""),
            executor=executor,
            handler_fn=handler_fn,
            resources=meta.get("resources", []),
            base_dir=str(skill_dir),
            body=None,  # L1 only — activate() loads L2
            # legacy fields
            handler=meta.get("handler_module") or meta.get("handler"),
            cron_schedule=meta.get("cron"),
            requires=meta.get("requires", []),
            tags=meta.get("tags", []),
        )

    # -- L2 activation -----------------------------------------------------

    def activate(self, skill_id: str) -> None:
        """Load L2 body (SKILL.md content) for a skill. Idempotent."""
        skill = self._skills.get(skill_id)
        if not skill or skill.is_activated:
            return  # already activated or not found
        post = frontmatter.load(str(Path(skill.base_dir) / self.SKILL_FILENAME))
        skill.body = post.content.strip()

    # -- Queries -----------------------------------------------------------

    def get(self, skill_id: str) -> Optional[Skill]:
        if not self._skills:
            self.load_all()
        return self._skills.get(skill_id)

    def get_cron_skills(self) -> list[Skill]:
        """Get all skills with cron triggers."""
        if not self._skills:
            self.load_all()
        return [s for s in self._skills.values() if s.trigger == "cron" and s.cron_schedule]

    @property
    def modality_skills(self) -> dict[str, str]:
        """Map modality name → skill_id for trigger:modality skills.
        Used for quick lookup: `if modality in engine.modality_skills`
        """
        return {
            s.modality: s.skill_id
            for s in self._skills.values()
            if s.trigger == "modality" and s.modality
        }

    @property
    def tool_skills(self) -> list[Skill]:
        """List of trigger:tool skills (full Skill objects for Stage 2 LLM tool registration)."""
        return [s for s in self._skills.values() if s.trigger == "tool"]

    def get_by_modality(self, modality: str) -> Optional[Skill]:
        """Find the skill bound to a given modality."""
        skill_id = self.modality_skills.get(modality)
        return self._skills.get(skill_id) if skill_id else None

    def build_skills_prompt(self) -> str:
        """Build a combined prompt section from modality skills using L1 description."""
        skills = [s for s in self._skills.values() if s.trigger == "modality"]
        if not skills:
            return ""
        parts = ["# 技能指南"]
        for skill in skills:
            if skill.description:
                parts.append(f"\n## {skill.name}\n{skill.description}")
        return "\n".join(parts)
