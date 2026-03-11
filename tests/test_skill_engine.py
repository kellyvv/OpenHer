"""Tests for the unified SkillEngine (v9 architecture).

Covers L1 loading, L2 activation, modality_skills mapping,
get_by_modality, tool_skills, build_skills_prompt, and ExecutionStatus.
"""

import os
import tempfile
import textwrap
from pathlib import Path

import pytest

from agent.skills.skill_engine import (
    ExecutionStatus,
    Skill,
    SkillEngine,
    SkillExecutionResult,
)


@pytest.fixture
def skills_dir(tmp_path):
    """Create a temporary skills directory with a test SKILL.md."""
    skill_dir = tmp_path / "selfie_gen"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(textwrap.dedent("""\
        ---
        name: 角色照片生成
        description: 以自拍照片表达自我
        trigger: modality
        modality: 照片
        executor: handler
        handler_fn: skills.selfie_gen.handler.generate_selfie
        resources:
          - idimage/
        ---

        # 角色照片生成

        详细的照片生成指南...
    """))
    return tmp_path


@pytest.fixture
def openclaw_skills_dir(tmp_path):
    """Create an OpenClaw-style skill (no trigger/executor, has scripts/)."""
    skill_dir = tmp_path / "weather"
    skill_dir.mkdir()
    (skill_dir / "scripts").mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(textwrap.dedent("""\
        ---
        name: 天气查询
        description: 查询天气信息
        ---

        查询指定城市的天气。
    """))
    return tmp_path


class TestL1Loading:
    """L1 metadata loading — body should be None."""

    def test_load_all_returns_l1_only(self, skills_dir):
        engine = SkillEngine(str(skills_dir))
        skills = engine.load_all()

        assert "selfie_gen" in skills
        skill = skills["selfie_gen"]
        assert skill.name == "角色照片生成"
        assert skill.description == "以自拍照片表达自我"
        assert skill.trigger == "modality"
        assert skill.modality == "照片"
        assert skill.executor == "handler"
        assert skill.handler_fn == "skills.selfie_gen.handler.generate_selfie"
        assert skill.resources == ["idimage/"]
        assert skill.base_dir == str(skills_dir / "selfie_gen")
        assert skill.body is None  # L1: body not loaded
        assert not skill.is_activated


class TestL2Activation:
    """L2 activation — body should be loaded from SKILL.md content."""

    def test_activate_loads_body(self, skills_dir):
        engine = SkillEngine(str(skills_dir))
        engine.load_all()

        engine.activate("selfie_gen")
        skill = engine.get("selfie_gen")
        assert skill.is_activated
        assert "角色照片生成" in skill.body
        assert "详细的照片生成指南" in skill.body

    def test_activate_idempotent(self, skills_dir):
        """Repeated activate() should not re-read file."""
        engine = SkillEngine(str(skills_dir))
        engine.load_all()

        engine.activate("selfie_gen")
        body_first = engine.get("selfie_gen").body

        # Mutate body to detect re-read
        engine.get("selfie_gen").body = "MODIFIED"
        engine.activate("selfie_gen")
        assert engine.get("selfie_gen").body == "MODIFIED"  # Not re-read


class TestModalitySkills:
    """modality_skills property and get_by_modality."""

    def test_modality_skills_mapping(self, skills_dir):
        engine = SkillEngine(str(skills_dir))
        engine.load_all()

        mapping = engine.modality_skills
        assert mapping == {"照片": "selfie_gen"}

    def test_get_by_modality(self, skills_dir):
        engine = SkillEngine(str(skills_dir))
        engine.load_all()

        skill = engine.get_by_modality("照片")
        assert skill is not None
        assert skill.skill_id == "selfie_gen"

        # Non-existent modality
        assert engine.get_by_modality("语音") is None


class TestToolSkills:
    """tool_skills property — Stage 1 should be empty for modality skills."""

    def test_tool_skills_empty(self, skills_dir):
        engine = SkillEngine(str(skills_dir))
        engine.load_all()
        assert engine.tool_skills == []

    def test_openclaw_defaults_to_tool(self, openclaw_skills_dir):
        """OpenClaw skill with scripts/ dir → trigger:tool, executor:sandbox."""
        engine = SkillEngine(str(openclaw_skills_dir))
        engine.load_all()

        skill = engine.get("weather")
        assert skill.trigger == "tool"
        assert skill.executor == "sandbox"
        assert skill in engine.tool_skills


class TestBuildSkillsPrompt:
    """build_skills_prompt uses description (not body)."""

    def test_build_skills_prompt_l1_uses_desc(self, skills_dir):
        engine = SkillEngine(str(skills_dir))
        engine.load_all()

        prompt = engine.build_skills_prompt()
        assert "技能指南" in prompt
        assert "角色照片生成" in prompt
        assert "以自拍照片表达自我" in prompt
        # Body content should NOT appear (body=None, uses description)
        assert "详细的照片生成指南" not in prompt


class TestExecutionStatus:
    """ExecutionStatus enum and SkillExecutionResult."""

    def test_execution_status_enum(self):
        assert ExecutionStatus.COMPLETED.value == "completed"
        assert ExecutionStatus.FAILED.value == "failed"
        assert ExecutionStatus.NEEDS_INFO.value == "needs_info"
        assert ExecutionStatus.IN_PROGRESS.value == "in_progress"

    def test_skill_execution_result(self):
        result = SkillExecutionResult(
            skill_id="selfie_gen",
            success=True,
            status=ExecutionStatus.COMPLETED,
            output={"image_path": "/tmp/photo.png"},
        )
        assert result.output.get("image_path") == "/tmp/photo.png"
        assert result.next_skills == []  # Stage 2 placeholder default

    def test_skill_execution_result_failed(self):
        result = SkillExecutionResult(
            skill_id="selfie_gen",
            success=False,
            status=ExecutionStatus.FAILED,
            output={"error": "API error"},
        )
        assert not result.success
        assert result.status == ExecutionStatus.FAILED


# ---------------------------------------------------------------------------
# Stage 2: Task skill declarations & execution
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock
from providers.llm.base import ChatResponse


@pytest.fixture
def tool_skill_dir(tmp_path):
    """Create a trigger:tool skill with body (for declarations + execute tests)."""
    skill_dir = tmp_path / "weather"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: weather
        description: Get current weather and forecasts (no API key required).
        trigger: tool
        executor: sandbox
        ---

        Quick command: curl -s "wttr.in/{city}?format=3"
    """))
    return tmp_path


class TestBuildSkillDeclarations:
    """build_skill_declarations() — OpenAI function calling format."""

    def test_returns_openai_format(self, tool_skill_dir):
        engine = SkillEngine(str(tool_skill_dir))
        engine.load_all()
        defs = engine.build_skill_declarations()
        assert len(defs) == 1
        assert defs[0]["type"] == "function"
        assert defs[0]["function"]["name"] == "weather"
        assert defs[0]["function"]["description"]  # non-empty
        assert defs[0]["function"]["parameters"] == {"type": "object", "properties": {}}

    def test_auto_load_if_not_loaded(self, tool_skill_dir):
        engine = SkillEngine(str(tool_skill_dir))
        # Not calling load_all() — should auto-load
        defs = engine.build_skill_declarations()
        assert len(defs) == 1

    def test_empty_when_no_tool_skills(self, skills_dir):
        """modality-only skills return empty declarations."""
        engine = SkillEngine(str(skills_dir))
        engine.load_all()
        assert engine.build_skill_declarations() == []


class TestExecute:
    """execute() — OpenClaw SKILL model execution."""

    async def test_execute_success(self, tool_skill_dir):
        """LLM generates valid command → sandbox executes → success."""
        class MockLLM:
            async def chat(self, msgs, **kw):
                return ChatResponse(content="echo hello_weather")
        engine = SkillEngine(str(tool_skill_dir))
        engine.load_all()
        result = await engine.execute("weather", "北京天气", MockLLM())
        assert result.success
        assert result.output["stdout"] == "hello_weather"
        assert result.output["command"] == "echo hello_weather"
        assert result.status == ExecutionStatus.COMPLETED

    async def test_execute_empty_command(self, tool_skill_dir):
        """LLM returns empty content → FAILED, sandbox never called."""
        class MockLLM:
            async def chat(self, msgs, **kw):
                return ChatResponse(content="")
        engine = SkillEngine(str(tool_skill_dir))
        engine.load_all()
        result = await engine.execute("weather", "北京天气", MockLLM())
        assert not result.success
        assert "empty command" in result.output["error"]

    async def test_execute_unknown_skill(self, tool_skill_dir):
        """Unknown skill_id → FAILED immediately."""
        engine = SkillEngine(str(tool_skill_dir))
        engine.load_all()
        result = await engine.execute("nonexistent", "whatever", AsyncMock())
        assert not result.success
        assert "Unknown skill" in result.output["error"]


class TestExecuteShell:
    """execute_shell() — sandbox command execution."""

    async def test_basic_command(self):
        from agent.skills.sandbox_executor import execute_shell
        result = await execute_shell("echo hello")
        assert result["success"]
        assert result["stdout"] == "hello"
        assert result["returncode"] == 0

    async def test_timeout_kill(self):
        from agent.skills.sandbox_executor import execute_shell
        result = await execute_shell("sleep 10", timeout=1)
        assert not result["success"]
        assert "timed out" in result["stderr"]
        assert result["returncode"] == -1


class TestTaskLogStore:
    """TaskLogStore — isolated persistence for task executions."""

    def test_log_and_retrieve(self, tmp_path):
        from agent.skills.task_log_store import TaskLogStore
        store = TaskLogStore(str(tmp_path / "task.db"))
        store.log_execution(
            persona_id="luna",
            skill_id="weather",
            user_input="北京天气",
            command='curl -s "wttr.in/Beijing?format=3"',
            stdout="Beijing: ☀️ +22°C",
            stderr="",
            success=True,
            reply="北京今天22度晴天哦～",
        )
        rows = store.get_recent("luna", limit=5)
        assert len(rows) == 1
        assert rows[0]["skill_id"] == "weather"
        assert rows[0]["stdout"] == "Beijing: ☀️ +22°C"
        assert rows[0]["success"] == 1
        store.close()
