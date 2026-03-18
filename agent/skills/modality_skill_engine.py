"""
ModalitySkillEngine — Load and execute persona-intrinsic modality skills.

Architecture: Claude Skill pattern (prompt-driven, not function calling).

  SKILL.md body → injected as LLM instructions
  LLM outputs structured JSON → engine parses
  Engine calls tools via ToolRegistry

Works with ANY LLM provider — no function calling support required.

Lifecycle:
  L1  build_prompt()  → inject descriptions into Express prompt
  L2  activate()      → load SKILL.md body on first use
  L3  execute()       → prompt LLM → parse JSON → call tools
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Optional, List

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


class ModalitySkillEngine:
    """Persona-intrinsic skill engine for modality-triggered skills."""

    def __init__(self, skills_dir: str, tool_registry: "Optional[ToolRegistry]" = None):
        self.skills_dir = Path(skills_dir)
        self.tool_registry = tool_registry
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
        return {s.modality: s.skill_id for s in self._skills.values()}

    def get_by_modality(self, modality: str) -> Optional[Skill]:
        skill_id = self.modality_skills.get(modality)
        return self._skills.get(skill_id) if skill_id else None

    def build_prompt(self) -> str:
        skills = list(self._skills.values())
        if not skills:
            return ""
        parts = ["# 技能指南"]
        for skill in skills:
            if skill.description:
                parts.append(f"\n## {skill.name}\n{skill.description}")
        return "\n".join(parts)

    # -- Plan & Execute (L3 — VERA-inspired) -----------------------------------

    async def plan_and_execute(
        self,
        raw_modality: str,
        raw_output: str,
        persona,
        llm,
        chat_history: list = None,
    ) -> List[SkillExecutionResult]:
        """LLM-driven multi-skill planning and execution.

        Inspired by VERA's activate_skill pattern:
          1. LLM sees all available skill summaries + raw_modality
          2. LLM returns an ordered execution plan (JSON array)
          3. Engine executes each skill in order, merging results

        Returns list of SkillExecutionResult (one per executed skill).
        """
        from providers.llm.base import ChatMessage

        if not self._skills:
            return []

        # Build skill catalog for the planning prompt
        skill_catalog = []
        for skill in self._skills.values():
            entry = {
                "modality": skill.modality,
                "name": skill.name,
                "description": skill.description,
                "tools": skill.tools,
            }
            skill_catalog.append(entry)

        catalog_json = json.dumps(skill_catalog, ensure_ascii=False, indent=2)

        system_prompt = (
            "你是一个 SKILL 调度器。根据 Express 输出的【表达方式】，决定需要执行哪些技能、按什么顺序执行。\n\n"
            f"## 可用技能\n```json\n{catalog_json}\n```\n\n"
            "## 规则\n"
            "1. 只选择【表达方式】中明确提到的技能\n"
            "2. 如果【表达方式】中同时包含语音和多条拆分，只选择 modality=语音，忽略多条拆分\n"
            "3. 内容生成类技能（照片、语音）排在前面，投递方式类技能（多条拆分）排在后面\n"
            "4. 如果没有匹配任何技能，返回空数组 []\n"
            "5. 每个技能条目必须包含 modality 和 params\n\n"
            "## 输出格式\n"
            "返回 JSON 数组，按执行顺序排列：\n"
            '```json\n[{"modality": "照片", "params": {...}}, {"modality": "多条拆分", "params": {...}}]\n```\n\n'
            "对于每个技能，params 的格式参考该技能的 SKILL.md 文档（会在激活时提供）。\n"
            "现在只需要返回 modality 列表，params 设为空对象 {} 即可。"
        )

        user_prompt = f"【表达方式】原文：{raw_modality}"

        messages = [
            ChatMessage("system", system_prompt),
            ChatMessage("user", user_prompt),
        ]

        try:
            response = await llm.chat(messages, temperature=0.1)
            plan = self._extract_json(response.content)
        except Exception as e:
            print(f"  [skill-plan] ❌ Planning failed: {e}")
            plan = None

        # Fallback: if planning fails, try simple keyword matching
        if not plan or not isinstance(plan, list):
            plan = []
            for skill in self._skills.values():
                if skill.modality and skill.modality in raw_modality:
                    plan.append({"modality": skill.modality, "params": {}})
            if plan:
                print(f"  [skill-plan] ⚠ LLM plan failed, fallback to keyword matching: {[p['modality'] for p in plan]}")

        if not plan:
            return []

        # Apply excludes rules declared in SKILL.md frontmatter
        plan_modalities = {p.get("modality") for p in plan}
        for skill in self._skills.values():
            if skill.excludes and skill.modality in plan_modalities:
                plan = [p for p in plan if p.get("modality") not in skill.excludes]

        print(f"  [skill-plan] 📋 Plan: {[p.get('modality') for p in plan]}")

        # Execute each skill in plan order
        results: List[SkillExecutionResult] = []
        for step in plan:
            modality = step.get("modality", "")
            skill = self.get_by_modality(modality)
            if not skill:
                print(f"  [skill-plan] ⚠ Unknown modality '{modality}', skipping")
                continue

            print(f"  [skill] 🎯 modality='{modality}' (from plan)")
            result = await self.execute(modality, raw_output, persona, llm, chat_history=chat_history)
            if result:
                result.output["_modality"] = modality  # inject plan's modality
                results.append(result)

        return results

    # -- Single-Skill Execution (L3) -------------------------------------------

    async def execute(
        self,
        modality: str,
        raw_output: str,
        persona,
        llm,
        chat_history: list = None,
    ) -> Optional[SkillExecutionResult]:
        """Execute a modality skill — prompt-driven, no function calling.

        Flow:
          1. Inject SKILL.md body as LLM instruction
          2. LLM outputs structured JSON
          3. Engine parses JSON
          4. Engine executes tools via ToolRegistry

        Fast path: split_messages skips LLM (pure text processing).
        """
        skill = self.get_by_modality(modality)
        if not skill:
            return None

        if not skill.is_activated:
            self.activate(skill.skill_id)

        # Route: prompt-driven tool-use vs legacy handler
        if skill.tools and self.tool_registry:
            return await self._execute_via_prompt(skill, raw_output, persona, llm, chat_history=chat_history)
        elif skill.handler_fn:
            return await self._execute_via_handler(skill, raw_output, persona, llm)
        else:
            print(f"  [modality-skill] ⚠ {skill.name}: no tools or handler_fn")
            return None

    # -- Prompt-driven execution (Claude Skill pattern) ----------------------

    @staticmethod
    def _build_chat_summary(chat_history, persona_name: str, max_turns: int = 6, max_chars: int = 600) -> str:
        """Build a concise chat summary for skill context injection."""
        if not chat_history:
            return "（无历史对话）"
        recent = chat_history[-max_turns:]
        lines = []
        for m in recent:
            role = "用户" if m.role == "user" else persona_name
            lines.append(f"{role}: {m.content[:100]}")
        return "\n".join(lines)[:max_chars]

    async def _execute_via_prompt(
        self,
        skill: Skill,
        raw_output: str,
        persona,
        llm,
        chat_history: list = None,
    ) -> SkillExecutionResult:
        """Execute skill via prompt-driven structured output.

        1. Build prompt from SKILL.md body + context
        2. LLM outputs JSON (following SKILL.md format instructions)
        3. Engine parses JSON
        4. Engine executes tools based on parsed parameters
        """
        from providers.llm.base import ChatMessage

        try:
            # Build prompt — SKILL.md body IS the instruction
            # Conditionally inject chat history (only if skill declares needs_chat_history)
            chat_block = ""
            if skill.needs_chat_history and chat_history:
                chat_summary = self._build_chat_summary(chat_history, persona.name)
                chat_block = f"## 最近对话\n{chat_summary}\n\n"

            system_prompt = (
                f"{skill.body}\n\n"
                f"---\n"
                f"## 当前上下文\n\n"
                f"角色名：{persona.name}\n"
                f"角色ID：{persona.persona_id}\n\n"
                f"{chat_block}"
                f"角色回复（JSON）：\n{raw_output}\n\n"
                f"---\n"
                f"请根据上述技能文档和角色回复上下文，直接输出 JSON。只输出 JSON，不要其他内容。"
            )

            # Pre-inject voice_preset for voice skills
            if "synthesize_voice" in skill.tools:
                voice_preset = self._resolve_voice_preset(persona)
                system_prompt += f"\n\n（系统预设 voice_preset: {voice_preset}）"

            messages = [
                ChatMessage("system", system_prompt),
                ChatMessage("user", "请输出 JSON。"),
            ]

            # Call LLM — NO tools parameter, pure text output
            response = await llm.chat(messages, temperature=0.3)

            # Parse JSON from LLM response
            params = self._extract_json(response.content)
            if not params:
                print(f"  [modality-skill] ⚠ Failed to parse JSON from LLM output")
                print(f"  [modality-skill]   raw: {response.content[:200]}")
                return SkillExecutionResult(
                    skill_id=skill.skill_id,
                    success=False,
                    status=ExecutionStatus.FAILED,
                    output={"error": "Failed to parse JSON from LLM", "raw": response.content[:500]},
                )

            print(f"  [modality-skill] 📋 LLM params: {json.dumps(params, ensure_ascii=False)[:200]}")

            # Execute tools based on skill type and parsed params
            return await self._dispatch_tools(skill, params, persona)

        except Exception as e:
            print(f"  [modality-skill] ❌ Prompt-driven execution failed: {e}")
            return SkillExecutionResult(
                skill_id=skill.skill_id,
                success=False,
                status=ExecutionStatus.FAILED,
                output={"error": str(e)},
            )

    async def _dispatch_tools(
        self,
        skill: Skill,
        params: dict,
        persona,
    ) -> SkillExecutionResult:
        """Dispatch tool calls based on parsed params.

        The engine knows the tool orchestration logic for each skill —
        this is deterministic, not LLM-decided.
        """
        output = {}

        # ── Photo skill: get_reference_image → generate_photo ──
        if "generate_photo" in skill.tools:
            # Step 1: Collect reference images (supports list, fallback to single)
            ref_types = params.get("reference_types") or []
            if not ref_types:
                single = params.get("reference_type")
                if single and single != "null":
                    ref_types = [single]

            reference_images = []
            if ref_types and self.tool_registry.has("get_reference_image"):
                for rt in ref_types:
                    ref_result = await self.tool_registry.execute("get_reference_image", {
                        "persona_id": persona.persona_id,
                        "reference_type": rt,
                    })
                    output.update(ref_result)
                    if ref_result.get("available"):
                        reference_images.append(ref_result["image_path"])
                    else:
                        print(f"  [modality-skill] ⚠ {rt} not available, skipping")

            # Step 2: Generate photo (with 2x silent retry)
            gen_params = {
                "prompt": params.get("prompt", ""),
                "persona_id": persona.persona_id,
                "aspect_ratio": params.get("aspect_ratio", "9:16"),
            }
            if reference_images:
                gen_params["reference_images"] = reference_images

            gen_result = await self._retry_tool("generate_photo", gen_params)
            output.update(gen_result)

        # ── Voice skill: synthesize_voice ──
        elif "synthesize_voice" in skill.tools:
            voice_preset = self._resolve_voice_preset(persona)
            voice_result = await self._retry_tool("synthesize_voice", {
                "text": params.get("text", ""),
                "voice_preset": voice_preset,
                "emotion_instruction": params.get("emotion_instruction", ""),
            })
            output.update(voice_result)

        # ── Split skill: split_messages ──
        elif "split_messages" in skill.tools:
            split_params = {"text": params.get("text", "")}
            if params.get("delays_ms"):
                split_params["delays_ms"] = params["delays_ms"]
            split_result = await self.tool_registry.execute("split_messages", split_params)
            output.update(split_result)

        # Determine success — check tool's own flag first, then known output keys
        success = output.pop("success", False)
        if not success:
            success = bool(output.get("image_path") or output.get("audio_path") or output.get("segments"))

        status_str = "✅" if success else "❌"
        print(f"  [modality-skill] {status_str} {skill.name} {'completed' if success else 'failed'}")

        return SkillExecutionResult(
            skill_id=skill.skill_id,
            success=success,
            status=ExecutionStatus.COMPLETED if success else ExecutionStatus.FAILED,
            output=output,
        )

    # -- Helpers ---------------------------------------------------------------

    async def _retry_tool(self, tool_name: str, params: dict, max_retries: int = 2) -> dict:
        """Execute a tool with silent retries for transient errors.

        Retries the same call up to max_retries times.
        Only the final failure propagates up to the engine.
        """
        import asyncio
        last_result = {}
        for attempt in range(1, max_retries + 2):  # 1 initial + max_retries
            result = await self.tool_registry.execute(tool_name, params)
            success = result.get("success", False)
            if not success:
                success = bool(result.get("image_path") or result.get("audio_path"))
            if success:
                return result
            last_result = result
            if attempt <= max_retries:
                print(f"  [tool] 🔄 {tool_name} retry {attempt}/{max_retries}")
                await asyncio.sleep(1)  # brief pause before retry
        return last_result


    def _extract_json(self, text: str):
        """Extract JSON (object or array) from LLM text output."""
        text = text.strip()

        # Try direct parse (object or array)
        if text.startswith(("{", "[")):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Strip markdown ```json ... ``` fence and try direct parse
        stripped = re.sub(r"^```(?:json)?\s*\n?", "", text)
        stripped = re.sub(r"\n?\s*```\s*$", "", stripped).strip()
        if stripped != text and stripped.startswith(("{", "[")):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                # Try sanitizing Chinese curly quotes inside JSON string values
                sanitized = stripped.replace('\u201c', '\\"').replace('\u201d', '\\"')
                try:
                    return json.loads(sanitized)
                except json.JSONDecodeError:
                    pass

        # Try extracting from ```json ... ``` block (object or array)
        m = re.search(r"```(?:json)?\s*\n?([{\[].*?[}\]])\s*\n?```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding [...] block (for plan arrays)
        m = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        # Try finding {...} block
        m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _resolve_voice_preset(self, persona) -> str:
        """Pre-resolve voice_preset from api.yaml voice_map."""
        try:
            from providers.config import _load as _load_config
            _tts_cfg = _load_config().get("tts", {})
            _voice_map = _tts_cfg.get("voice_map", {})
            _default_voice = _tts_cfg.get("providers", {}).get(
                _tts_cfg.get("provider", ""), {}
            ).get("default_voice", "Cherry")
            return _voice_map.get(persona.persona_id, _default_voice)
        except Exception:
            return "Cherry"

    # -- Legacy path (fallback) -----------------------------------------------

    async def _execute_via_handler(
        self,
        skill: Skill,
        raw_output: str,
        persona,
        llm,
    ) -> Optional[SkillExecutionResult]:
        """Legacy handler_fn path. Kept during migration."""
        from providers.llm.base import ChatMessage

        if not skill.handler_fn:
            return None

        try:
            system_msg = ChatMessage("system",
                f"根据以下技能文档和角色回复上下文，生成该技能的结构化输出。\n"
                f"只输出结构化内容，不要多余解释。\n\n{skill.body}"
            )
            user_msg = ChatMessage("user",
                f"角色回复：{raw_output}\n角色名：{persona.name}"
            )
            prompt_resp = await llm.chat([system_msg, user_msg], temperature=0.3)

            module_path, fn_name = skill.handler_fn.rsplit('.', 1)
            mod = importlib.import_module(module_path)
            handler = getattr(mod, fn_name)
            voice_preset = self._resolve_voice_preset(persona)

            result = await handler(
                persona_id=persona.persona_id,
                raw_output=prompt_resp.content,
                persona_name=persona.name,
                voice_preset=voice_preset,
                base_instructions=getattr(persona.voice, 'description', '') or '',
            )

            success = result.get("success", False)
            return SkillExecutionResult(
                skill_id=skill.skill_id,
                success=success,
                status=ExecutionStatus.COMPLETED if success else ExecutionStatus.FAILED,
                output=result,
            )
        except Exception as e:
            print(f"  [modality-skill] ❌ handler error: {e}")
            return SkillExecutionResult(
                skill_id=skill.skill_id,
                success=False,
                status=ExecutionStatus.FAILED,
                output={"error": str(e)},
            )
