"""
TaskSkillEngine — VERA-inspired ReAct loop for task-oriented skills.

Architecture: Prompt-driven ReAct (no function calling dependency).

  L1  build_catalog() → inject skill metadata into ReAct prompt
  L2  activate()      → JIT inject SKILL.md body on LLM request
  L3  react_loop()    → ReAct cycle: Thought → Action → Observation

Execution paths:
  executor=sandbox  → LLM generates shell command → execute_shell()
  executor=handler  → LLM generates params → ToolRegistry.execute()

Supports parallel (multiple actions per round) and serial (multi-round) chaining.
"""

from __future__ import annotations

import asyncio
import json
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

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from agent.skills.tool_registry import ToolRegistry


class TaskSkillEngine:
    """Task-oriented skill engine with ReAct loop."""

    def __init__(self, skills_dir: str, tool_registry: "Optional[ToolRegistry]" = None):
        self.skills_dir = Path(skills_dir)
        self.tool_registry = tool_registry
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
        """Get all skills with cron triggers."""
        if not self._skills:
            self.load_all()
        return [s for s in self._skills.values() if s.trigger == "cron" and s.cron_schedule]

    # -- L1 Catalog (Progressive Disclosure) -----------------------------------

    def build_catalog(self) -> str:
        """Build L1 skill catalog text for ReAct prompt injection.

        Returns a concise description of available skills (metadata only).
        """
        if not self._skills:
            self.load_all()
        if not self.tool_skills:
            return ""

        lines = ["可用工具技能："]
        for skill in self.tool_skills:
            lines.append(f"- {skill.skill_id}: {skill.description}")
        return "\n".join(lines)

    # -- ReAct Loop ------------------------------------------------------------

    async def react_loop(
        self,
        user_message: str,
        llm,
        max_rounds: int = 3,
    ) -> Optional[str]:
        """Run a pre-engine ReAct loop for task skill detection + execution.

        Pure prompt-driven — no function calling dependency.

        Flow:
          Round 1: LLM sees skill catalog (L1) + user message
                   → outputs nothing (no skill needed) or {"activate": "skill_id"}
          Round 2+: Engine JIT injects SKILL.md body (L2)
                   → LLM outputs {"actions": [...]} or {"done": true}
                   → Engine executes actions (sandbox or ToolRegistry)
                   → Observations fed back for next round

        Returns:
            Merged observation text to inject into user_message, or None.
        """
        from providers.llm.base import ChatMessage

        if not self._skills:
            self.load_all()
        if not self.tool_skills:
            return None

        catalog = self.build_catalog()
        if not catalog:
            return None

        # Build ReAct system prompt
        system_prompt = (
            "你是一个工具调度器。判断用户消息是否需要调用工具。\n\n"
            f"## {catalog}\n\n"
            "## 协议\n"
            "- 如果用户消息**直接、明确**地请求了某个技能的能力，输出 JSON：\n"
            '  {"activate": "skill_id"}\n\n'
            "- 如果已有技能文档，需要执行动作：\n"
            '  {"actions": [{"tool": "execute_shell", "params": {"command": "..."}}]}\n\n'
            "- **其他所有情况**，什么都不要输出，返回空。\n\n"
            "## 严格规则\n"
            "- 99% 的消息都不需要工具，默认返回空\n"
            "- 聊天、闲聊、提问、情感表达、讨论话题 → 返回空\n"
            "- 不要联想、不要推测用户可能需要什么工具\n"
            "- 用户没有明说要用工具，就不要激活\n"
        )

        messages = [ChatMessage("system", system_prompt)]
        messages.append(ChatMessage("user", user_message))

        all_observations: list[str] = []
        active_skill: Optional[Skill] = None

        for round_idx in range(max_rounds):
            try:
                response = await llm.chat(messages, temperature=0.1, max_tokens=500)
                raw = response.content.strip()
            except Exception as e:
                print(f"  [react] ❌ Round {round_idx + 1} LLM error: {e}")
                break

            # Empty output = LLM decided no skill needed → silent return
            if not raw:
                break

            parsed = self._extract_json(raw)

            if not parsed:
                # LLM output non-JSON (e.g. "不需要") = no skill needed
                break

            # done = no skill needed (backward compat)
            if parsed.get("done"):
                break

            # activate_skill — JIT inject SKILL.md body (L2)
            if "activate" in parsed:
                skill_id = parsed["activate"].lower()
                skill = self._skills.get(skill_id)
                if not skill:
                    print(f"  [react] ⚠ Unknown skill: {skill_id}")
                    break

                print(f"  [react] 🎯 Activate: {skill_id} (round {round_idx + 1})")
                self.activate(skill_id)
                active_skill = skill

                # JIT inject SKILL.md body into context
                skill_injection = (
                    f"技能 [{skill.name}] 已激活。以下是技能文档：\n\n"
                    f"{skill.body}\n\n"
                    f"请根据技能文档和用户请求，生成具体的执行动作。"
                )
                messages.append(ChatMessage("assistant", response.content))
                messages.append(ChatMessage("user", skill_injection))
                continue

            # actions — execute via sandbox or ToolRegistry
            actions = parsed.get("actions", [])
            if not actions:
                break

            thought = parsed.get("thought", "")
            print(f"  [react] 🔧 Actions (round {round_idx + 1}): "
                  f"{len(actions)} action(s), thought: {thought[:60]}")

            # Parallel execution via asyncio.gather
            tasks = [self._execute_action(a, active_skill) for a in actions]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect observations
            round_observations = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    obs = f"[错误] {result}"
                elif isinstance(result, str):
                    obs = result
                else:
                    obs = str(result)
                round_observations.append(obs)
                all_observations.append(obs)

            # Feed observations back for next round
            obs_text = "\n".join(f"[Observation {i+1}] {o}" for i, o in enumerate(round_observations))
            messages.append(ChatMessage("assistant", response.content))
            messages.append(ChatMessage("user",
                f"执行结果：\n{obs_text}\n\n"
                f"根据结果，是否需要更多操作？如果完成，返回 {{\"done\": true}}。"
            ))

        if not all_observations:
            return None

        # P4 fix: per-observation limit + truncation marker
        MAX_PER_OBS = 300
        trimmed = []
        for obs in all_observations:
            if len(obs) > MAX_PER_OBS:
                trimmed.append(obs[:MAX_PER_OBS] + "…（已截断）")
            else:
                trimmed.append(obs)
        merged = "\n".join(trimmed)
        print(f"  [react] 📋 Total observations: {len(all_observations)}, {len(merged)} chars")
        return merged

    # -- Action Execution ------------------------------------------------------

    async def _execute_action(
        self,
        action: dict,
        active_skill: Optional[Skill],
    ) -> str:
        """Execute a single action from the ReAct output.

        Routes to sandbox (execute_shell) or ToolRegistry based on action type.
        """
        tool_name = action.get("tool", "execute_shell")
        params = action.get("params", {})

        # Sandbox path
        if tool_name == "execute_shell":
            command = params.get("command", "")
            if not command:
                return "[错误] 空命令"

            # Clean markdown wrapping
            command = re.sub(r'^```\w*\n?', '', command)
            command = re.sub(r'\n?```$', '', command)
            command = command.strip()

            from agent.skills.sandbox_executor import execute_shell
            result = await execute_shell(command)

            stdout = result.get("stdout", "").strip()
            stderr = result.get("stderr", "").strip()
            if result["success"]:
                return stdout or "[执行成功，无输出]"
            else:
                return f"[执行失败] {stderr or stdout or '未知错误'}"

        # ToolRegistry path
        if self.tool_registry and self.tool_registry.has(tool_name):
            try:
                result = await self.tool_registry.execute(tool_name, params)
                return json.dumps(result, ensure_ascii=False)[:500]
            except Exception as e:
                return f"[工具错误] {tool_name}: {e}"

        return f"[未知工具] {tool_name}"

    async def _execute_with_skill(
        self,
        skill: Skill,
        user_message: str,
        llm,
    ) -> Optional[str]:
        """Fallback: execute a skill directly (keyword match path).

        Used when JSON parsing fails but keyword matching finds a skill.
        """
        from providers.llm.base import ChatMessage

        if not skill.body:
            return None

        system_msg = ChatMessage("system",
            f"根据以下技能文档，为用户请求生成一条可执行的 shell 命令。\n"
            f"只输出命令本身，不要解释，不要 markdown 格式。\n\n"
            f"## 技能文档\n{skill.body}"
        )
        user_msg = ChatMessage("user", user_message)
        resp = await llm.chat([system_msg, user_msg], temperature=0.1)

        content = resp.content.strip()
        content = re.sub(r'^```\w*\n?', '', content)
        content = re.sub(r'\n?```$', '', content)
        command = content.strip()

        if not command:
            return None

        from agent.skills.sandbox_executor import execute_shell
        result = await execute_shell(command)

        stdout = result.get("stdout", "").strip()
        if result["success"] and stdout:
            return stdout
        return None

    # -- Keyword Fallback ------------------------------------------------------

    def _keyword_match(self, user_message: str) -> Optional[Skill]:
        """Simple keyword matching fallback when LLM JSON fails."""
        msg_lower = user_message.lower()
        for skill in self.tool_skills:
            # Check skill name and description keywords
            triggers = [skill.skill_id, skill.name]
            desc_words = skill.description.split()
            triggers.extend(w for w in desc_words if len(w) >= 5)
            for trigger in triggers:
                if trigger.lower() in msg_lower:
                    return skill
        return None

    # -- JSON Extraction -------------------------------------------------------

    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON object from LLM text output."""
        text = text.strip()

        # Direct parse
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Strip markdown ```json ... ``` fence
        stripped = re.sub(r"^```(?:json)?\s*\n?", "", text)
        stripped = re.sub(r"\n?\s*```\s*$", "", stripped).strip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass

        # P1 fix: bracket-counting extraction (replaces greedy regex)
        obj_str = self._find_first_json_object(text)
        if obj_str:
            try:
                return json.loads(obj_str)
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _find_first_json_object(text: str) -> Optional[str]:
        """Find the first balanced {...} block using bracket counting."""
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == "\\" and in_string:
                escape = True
                continue
            if c == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return None

    # -- Legacy compat (kept for tests referencing execute()) ------------------

    async def execute(self, skill_id: str, user_intent: str, llm) -> SkillExecutionResult:
        """Execute a task skill directly. Legacy path, prefer react_loop().

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
