"""
Shared types for the Skill subsystem.

Both TaskSkillEngine and ModalitySkillEngine import from here
to avoid cross-dependency.
"""

from __future__ import annotations

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
    resources: list[str] = field(default_factory=list)
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
    next_skills: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public parsing function (used by both engines)
# ---------------------------------------------------------------------------

SKILL_FILENAME = "SKILL.md"


def load_skill(skill_dir: Path) -> Skill:
    """Parse SKILL.md frontmatter into Skill (L1 only, body=None).

    Extracted from the old SkillEngine._load_one() so both
    TaskSkillEngine and ModalitySkillEngine can share it.
    """
    skill_file = skill_dir / SKILL_FILENAME
    post = frontmatter.load(str(skill_file))
    meta = post.metadata

    # trigger: smart default
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
