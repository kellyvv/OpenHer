from agent.skills.task_skill_engine import TaskSkillEngine
from agent.skills.modality_skill_engine import ModalitySkillEngine

# Backward compat alias
SkillEngine = TaskSkillEngine

__all__ = ["TaskSkillEngine", "ModalitySkillEngine", "SkillEngine"]
