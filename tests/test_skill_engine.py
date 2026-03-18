"""Tests for the dual SkillEngine architecture (v7 — ReAct).

TaskSkillEngine: trigger=tool skills, VERA-inspired ReAct loop.
ModalitySkillEngine: trigger=modality skills only.
Shared types: skill_types.py (Skill, ExecutionStatus, SkillExecutionResult).
"""

import os
import tempfile
import textwrap
from pathlib import Path

import pytest

from agent.skills.skill_types import (
    ExecutionStatus,
    Skill,
    SkillExecutionResult,
    load_skill,
)
from agent.skills.task_skill_engine import TaskSkillEngine
from agent.skills.modality_skill_engine import ModalitySkillEngine
# Backward compat alias
from agent.skills import SkillEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def modality_skills_dir(tmp_path):
    """Create a temporary skills directory with a modality SKILL.md."""
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
def tool_skill_dir(tmp_path):
    """Create a trigger:tool skill with body."""
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


@pytest.fixture
def mixed_skills_dir(tmp_path):
    """Create a directory with both modality and tool skills."""
    # Modality skill
    selfie_dir = tmp_path / "selfie_gen"
    selfie_dir.mkdir()
    (selfie_dir / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: 角色照片生成
        description: 以自拍照片表达自我
        trigger: modality
        modality: 照片
        handler_fn: skills.selfie_gen.handler.generate_selfie
        ---
        照片指南
    """))
    # Tool skill
    weather_dir = tmp_path / "weather"
    weather_dir.mkdir()
    (weather_dir / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: weather
        description: Get weather info.
        trigger: tool
        executor: sandbox
        ---
        curl "wttr.in/{city}"
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


# ---------------------------------------------------------------------------
# Shared types (skill_types.py)
# ---------------------------------------------------------------------------

class TestSharedTypes:
    """Skill, ExecutionStatus, SkillExecutionResult from skill_types.py."""

    def test_load_skill_modality(self, modality_skills_dir):
        skill = load_skill(modality_skills_dir / "selfie_gen")
        assert skill.skill_id == "selfie_gen"
        assert skill.name == "角色照片生成"
        assert skill.trigger == "modality"
        assert skill.modality == "照片"
        assert skill.handler_fn == "skills.selfie_gen.handler.generate_selfie"
        assert skill.body is None  # L1 only
        assert not skill.is_activated

    def test_load_skill_tool(self, tool_skill_dir):
        skill = load_skill(tool_skill_dir / "weather")
        assert skill.trigger == "tool"
        assert skill.executor == "sandbox"

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
        assert result.next_skills == []

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
# ModalitySkillEngine
# ---------------------------------------------------------------------------

class TestModalitySkillEngine:
    """ModalitySkillEngine — only loads trigger=modality skills."""

    def test_load_only_modality_skills(self, mixed_skills_dir):
        engine = ModalitySkillEngine(str(mixed_skills_dir))
        skills = engine.load_all()
        assert "selfie_gen" in skills
        assert "weather" not in skills  # tool skill filtered out

    def test_modality_skills_mapping(self, modality_skills_dir):
        engine = ModalitySkillEngine(str(modality_skills_dir))
        engine.load_all()
        assert engine.modality_skills == {"照片": "selfie_gen"}

    def test_get_by_modality(self, modality_skills_dir):
        engine = ModalitySkillEngine(str(modality_skills_dir))
        engine.load_all()
        skill = engine.get_by_modality("照片")
        assert skill is not None
        assert skill.skill_id == "selfie_gen"
        assert engine.get_by_modality("语音") is None

    def test_activate_loads_body(self, modality_skills_dir):
        engine = ModalitySkillEngine(str(modality_skills_dir))
        engine.load_all()
        engine.activate("selfie_gen")
        skill = engine.get_by_modality("照片")
        assert skill.is_activated
        assert "角色照片生成" in skill.body

    def test_build_prompt(self, modality_skills_dir):
        engine = ModalitySkillEngine(str(modality_skills_dir))
        engine.load_all()
        prompt = engine.build_prompt()
        assert "技能指南" in prompt
        assert "角色照片生成" in prompt
        assert "以自拍照片表达自我" in prompt
        # Body content should NOT appear (L1 uses description only)
        assert "详细的照片生成指南" not in prompt

    def test_empty_dir(self, tmp_path):
        engine = ModalitySkillEngine(str(tmp_path))
        skills = engine.load_all()
        assert skills == {}
        assert engine.modality_skills == {}
        assert engine.build_prompt() == ""


# ---------------------------------------------------------------------------
# TaskSkillEngine — Loading & Catalog
# ---------------------------------------------------------------------------

class TestTaskSkillEngine:
    """TaskSkillEngine — only loads trigger=tool skills."""

    def test_load_only_tool_skills(self, mixed_skills_dir):
        engine = TaskSkillEngine(str(mixed_skills_dir))
        skills = engine.load_all()
        assert "weather" in skills
        assert "selfie_gen" not in skills  # modality skill filtered out

    def test_tool_skills_property(self, tool_skill_dir):
        engine = TaskSkillEngine(str(tool_skill_dir))
        engine.load_all()
        assert len(engine.tool_skills) == 1
        assert engine.tool_skills[0].skill_id == "weather"

    def test_build_catalog(self, tool_skill_dir):
        """build_catalog() generates L1 description text."""
        engine = TaskSkillEngine(str(tool_skill_dir))
        engine.load_all()
        catalog = engine.build_catalog()
        assert "weather" in catalog
        assert "weather" in catalog.lower() or "forecasts" in catalog.lower()

    def test_build_catalog_empty(self, modality_skills_dir):
        """No tool skills → empty catalog."""
        engine = TaskSkillEngine(str(modality_skills_dir))
        engine.load_all()
        assert engine.build_catalog() == ""

    def test_openclaw_defaults_to_tool(self, openclaw_skills_dir):
        engine = TaskSkillEngine(str(openclaw_skills_dir))
        engine.load_all()
        skill = engine.get("weather")
        assert skill.trigger == "tool"
        assert skill.executor == "sandbox"
        assert skill in engine.tool_skills

    def test_backward_compat_alias(self):
        """SkillEngine import should still work as TaskSkillEngine alias."""
        assert SkillEngine is TaskSkillEngine


# ---------------------------------------------------------------------------
# TaskSkillEngine — JSON Extraction
# ---------------------------------------------------------------------------

class TestJSONExtraction:
    """TaskSkillEngine._extract_json — parses various LLM output formats."""

    def setup_method(self):
        self.engine = TaskSkillEngine("/nonexistent")

    def test_direct_json(self):
        result = self.engine._extract_json('{"done": true, "thought": "test"}')
        assert result == {"done": True, "thought": "test"}

    def test_markdown_fenced_json(self):
        text = '```json\n{"activate": "weather", "thought": "reason"}\n```'
        result = self.engine._extract_json(text)
        assert result["activate"] == "weather"

    def test_json_with_surrounding_text(self):
        text = 'Here is the result: {"done": true} and more text'
        result = self.engine._extract_json(text)
        assert result["done"] is True

    def test_nested_json(self):
        text = '{"actions": [{"tool": "execute_shell", "params": {"command": "echo hi"}}]}'
        result = self.engine._extract_json(text)
        assert len(result["actions"]) == 1

    def test_invalid_json(self):
        result = self.engine._extract_json("no json here")
        assert result is None


# ---------------------------------------------------------------------------
# TaskSkillEngine — Keyword Matching Fallback
# ---------------------------------------------------------------------------

class TestKeywordMatch:
    """TaskSkillEngine._keyword_match — fallback when JSON fails."""

    def test_match_by_skill_id(self, tool_skill_dir):
        engine = TaskSkillEngine(str(tool_skill_dir))
        engine.load_all()
        skill = engine._keyword_match("今天的weather怎么样")
        assert skill is not None
        assert skill.skill_id == "weather"

    def test_match_by_description(self, tool_skill_dir):
        engine = TaskSkillEngine(str(tool_skill_dir))
        engine.load_all()
        skill = engine._keyword_match("I want to check the forecasts")
        assert skill is not None
        assert skill.skill_id == "weather"

    def test_no_match(self, tool_skill_dir):
        engine = TaskSkillEngine(str(tool_skill_dir))
        engine.load_all()
        skill = engine._keyword_match("你吃饭了吗")
        assert skill is None


# ---------------------------------------------------------------------------
# Isolation test
# ---------------------------------------------------------------------------

class TestIsolation:
    """Both engines load from same dir but get distinct skills."""

    def test_engines_are_isolated(self, mixed_skills_dir):
        task_engine = TaskSkillEngine(str(mixed_skills_dir))
        modality_engine = ModalitySkillEngine(str(mixed_skills_dir))

        task_skills = task_engine.load_all()
        modality_skills = modality_engine.load_all()

        # No overlap
        assert set(task_skills.keys()) & set(modality_skills.keys()) == set()
        assert "weather" in task_skills
        assert "selfie_gen" in modality_skills


# ---------------------------------------------------------------------------
# Task skill execution (legacy execute() path)
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock
from providers.llm.base import ChatResponse


class TestExecute:
    """TaskSkillEngine.execute() — command generation + sandbox."""

    async def test_execute_success(self, tool_skill_dir):
        class MockLLM:
            async def chat(self, msgs, **kw):
                return ChatResponse(content="echo hello_weather")
        engine = TaskSkillEngine(str(tool_skill_dir))
        engine.load_all()
        result = await engine.execute("weather", "北京天气", MockLLM())
        assert result.success
        assert result.output["stdout"] == "hello_weather"
        assert result.output["command"] == "echo hello_weather"
        assert result.status == ExecutionStatus.COMPLETED

    async def test_execute_empty_command(self, tool_skill_dir):
        class MockLLM:
            async def chat(self, msgs, **kw):
                return ChatResponse(content="")
        engine = TaskSkillEngine(str(tool_skill_dir))
        engine.load_all()
        result = await engine.execute("weather", "北京天气", MockLLM())
        assert not result.success
        assert "empty command" in result.output["error"]

    async def test_execute_unknown_skill(self, tool_skill_dir):
        engine = TaskSkillEngine(str(tool_skill_dir))
        engine.load_all()
        result = await engine.execute("nonexistent", "whatever", AsyncMock())
        assert not result.success
        assert "Unknown skill" in result.output["error"]


# ---------------------------------------------------------------------------
# ReAct loop
# ---------------------------------------------------------------------------

class TestReactLoop:
    """TaskSkillEngine.react_loop() — prompt-driven ReAct."""

    async def test_react_no_skill_needed(self, tool_skill_dir):
        """Normal chat → LLM returns done:true → None."""
        class MockLLM:
            async def chat(self, msgs, **kw):
                return ChatResponse(content='{"done": true, "thought": "普通聊天"}')
        engine = TaskSkillEngine(str(tool_skill_dir))
        engine.load_all()
        result = await engine.react_loop("你好呀", MockLLM())
        assert result is None

    async def test_react_activate_and_execute(self, tool_skill_dir):
        """Weather skill → activate → execute → observations."""
        call_count = 0
        class MockLLM:
            async def chat(self, msgs, **kw):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # Round 1: activate
                    return ChatResponse(content='{"activate": "weather", "thought": "用户问天气"}')
                elif call_count == 2:
                    # Round 2: execute (after JIT injection)
                    return ChatResponse(content='{"actions": [{"tool": "execute_shell", "params": {"command": "echo Beijing: 22C"}}], "thought": "生成命令"}')
                else:
                    # Round 3: done
                    return ChatResponse(content='{"done": true, "thought": "完成"}')

        engine = TaskSkillEngine(str(tool_skill_dir))
        engine.load_all()
        result = await engine.react_loop("北京天气怎么样", MockLLM())
        assert result is not None
        assert "Beijing: 22C" in result

    async def test_react_max_rounds(self, tool_skill_dir):
        """Max rounds prevents infinite loops."""
        class MockLLM:
            async def chat(self, msgs, **kw):
                # Always try to activate (never done)
                return ChatResponse(content='{"activate": "weather", "thought": "试试"}')

        engine = TaskSkillEngine(str(tool_skill_dir))
        engine.load_all()
        result = await engine.react_loop("北京天气", MockLLM(), max_rounds=2)
        # Should terminate due to max_rounds, no observations collected
        assert result is None

    async def test_react_empty_skills(self, modality_skills_dir):
        """No tool skills → immediate None."""
        engine = TaskSkillEngine(str(modality_skills_dir))
        engine.load_all()
        result = await engine.react_loop("北京天气", AsyncMock())
        assert result is None


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
