"""
ModalityRetryMixin — Modality failure handling for ChatAgent.

When a modality skill (TTS, image gen) fails after 2 silent tool retries:
  1. Inject failure context into Actor re-run
  2. Re-run Express through normal engine pipeline
  3. Engine naturally decides response (may choose text, retry modality, etc.)
  4. Result goes through normal _flush_buffer delivery

No standalone LLM calls — everything goes through the engine.
"""

from __future__ import annotations


class ModalityRetryMixin:
    """Modality skill failure handling — re-run Express via engine pipeline."""

    async def _modality_failure_with_retry(
        self, failed_modality: str, original_reply: str, express_content: str
    ) -> str:
        """Handle modality skill failure by re-running Express through the engine.

        Called after a modality skill has exhausted its 2 internal tool retries.
        Injects failure context and re-runs the Actor pass through the normal
        pipeline (extract_reply -> JSON context -> skill -> _flush_buffer).

        Returns the new reply text (from re-run Express), or original_reply if
        the re-run also fails.
        """
        from agent.parser import extract_reply
        from providers.llm.base import ChatMessage as _CM

        self._pending_retry = None  # reset

        # ── Inject failure context into Express re-run ──
        failure_hint = (
            f"\n\n（系统提示：角色刚才尝试发送{failed_modality}，但发送失败了。"
            f"请重新选择表达方式回复用户。原始回复内容：「{original_reply[:300]}」）"
        )

        express_prompt = getattr(self, '_last_express_prompt', None)
        if not express_prompt:
            print(f"  [retry] ⚠ No cached Express prompt, falling back to text")
            return original_reply

        try:
            express_messages = [
                _CM(role="system", content=express_prompt + failure_hint),
                _CM(role="user", content=getattr(self, '_last_user_message', "")),
            ]
            retry_response = await self.llm.chat(express_messages, temperature=0.9, max_tokens=500)
            retry_text = retry_response.content.strip()
            print(f"  [retry] 📝 Re-run Express: {retry_text[:100]}...")

            # Parse through normal pipeline
            _, retry_reply, retry_modality = extract_reply(retry_text)

            # Run modality skill if LLM chose one (through normal JSON context path)
            if self.modality_skill_engine and retry_modality not in ("文字", "静默", ""):
                import json as _json
                import re
                _SECTION_RE = re.compile(
                    r'(?:【(?P<zh>内心独白|最终回复|表达方式)】'
                    r'|\[(?P<en>Inner Monologue|Final Reply|Expression Mode)\])'
                )
                _matches = list(_SECTION_RE.finditer(retry_text))
                _raw_mod = retry_text[_matches[-1].end():].strip() if _matches else ""

                structured_context = _json.dumps({
                    "reply": retry_reply,
                    "modality": retry_modality,
                    "raw_modality": _raw_mod,
                }, ensure_ascii=False)

                skill_results = await self.modality_skill_engine.plan_and_execute(
                    raw_modality=_raw_mod,
                    raw_output=structured_context,
                    persona=self.persona,
                    llm=self.llm,
                )
                for skill_result in skill_results:
                    if skill_result.success:
                        self._skill_outputs.update(skill_result.output)
                        print(f"  [retry] ✅ Re-run skill succeeded: {retry_modality}")
                        return retry_reply

                # Re-run skill also failed — fall through to text
                print(f"  [retry] ⚠ Re-run skill also failed, delivering as text")

            return retry_reply or original_reply

        except Exception as e:
            print(f"  [retry] ✗ Re-run Express failed: {e}")
            return original_reply
