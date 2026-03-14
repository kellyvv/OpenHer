"""
ModalityRetryMixin — Modality fallback + 3x serial retry for ChatAgent.

When a modality skill (TTS, image gen) fails:
  1. LLM generates in-character text explanation
  2. Serial retry via mini Express pass (up to 3 times)
  3. On success → _pending_retry for main.py to deliver as follow-up
  4. All retries fail → system notification "{name}似乎出了点问题"
"""

from __future__ import annotations

from providers.llm.base import ChatMessage as _CM


class ModalityRetryMixin:
    """Modality skill failure handling with persona-aware retry."""

    async def _modality_failure_with_retry(
        self, failed_modality: str, original_reply: str, express_content: str
    ) -> str:
        """Handle modality skill failure with in-character fallback + serial retry.

        Flow (like a real person):
          1. Generate an in-character text explanation ("手机信号不好…")
          2. Add that text to conversation history (LLM knows it said this)
          3. Retry the modality skill up to 3 times via mini Express pass
          4. If retry succeeds → store in _pending_retry for main.py to deliver
             (user sees: text explanation → few seconds → voice/photo arrives)
          5. If all retries fail → system notification
        """
        self._pending_retry = None  # reset

        # ── Step 1: LLM generates in-character fallback text ──
        _no_tech = "不要提及技术故障、系统错误、服务器、TTS等技术词汇。"
        hint = (
            f"你是{self.persona.name}。"
            f"你刚才想给用户发一条{failed_modality}消息，但没有发送成功。"
            f"你原本想说的内容是：「{original_reply[:200]}」\n"
            f"请以你自己的方式，用简短的文字告诉用户为什么这次没法发{failed_modality}。"
            f"保持你的人格特征和说话风格。{_no_tech}"
            "自然一些，像真人一样解释。直接说你想说的话，不要加标签。"
        )
        fallback_msgs = [
            _CM(role="system", content=hint),
            _CM(role="user", content=f"（{failed_modality}没发出去，跟我说一声吧）"),
        ]
        try:
            resp = await self.llm.chat(fallback_msgs, temperature=0.9, max_tokens=200)
            fallback = resp.content.strip()
            print(f"  [skill] ✓ modality fallback: {fallback[:80]}...")
        except Exception as e:
            print(f"  [skill] ✗ fallback LLM call failed: {e}")
            fallback = ""

        # ── Step 2: Add fallback to history (LLM will know about it next turn) ──
        if fallback:
            self.history.append(_CM(role="assistant", content=fallback))

        # ── Step 3: Retry loop (up to 3 attempts via mini Express pass) ──
        MAX_RETRIES = 3
        if self.modality_skill_engine and fallback:
            _no_tech2 = "不要提及技术故障、系统错误、服务器、TTS等技术词汇。"
            for attempt in range(1, MAX_RETRIES + 1):
                print(f"  [skill] 🔄 Retry {attempt}/{MAX_RETRIES}: mini Express pass for {failed_modality}...")
                retry_prompt = (
                    f"你是{self.persona.name}（{self.persona.mbti}）。\n"
                    f"你刚才想给用户发{failed_modality}，但没发出去。\n"
                    f"你已经发了一段文字解释：「{fallback[:200]}」\n"
                    f"现在你想再试一次发{failed_modality}。\n\n"
                    f"因为你知道上次没发成功，这次你的表达可以和上次不一样——"
                    f"也许更轻松、更自然、或者带着一点「这次终于发出去了」的感觉。\n"
                    f"保持你的人格特征。{_no_tech2}\n\n"
                    f"按以下格式输出：\n"
                    f"【最终回复】\n你这次说的话\n"
                    f"【表达方式】\n{failed_modality}\n"
                )
                retry_msgs = [
                    _CM(role="system", content=retry_prompt),
                    _CM(role="user", content=f"（第{attempt}次尝试，再发一次{failed_modality}吧）"),
                ]
                try:
                    retry_express = await self.llm.chat(retry_msgs, temperature=0.9, max_tokens=300)
                    retry_text = retry_express.content.strip()
                    print(f"  [skill] 📝 Retry express: {retry_text[:100]}...")

                    # Extract reply from 【最终回复】
                    retry_reply = retry_text
                    for marker in ("【最终回复】", "[Final Reply]"):
                        idx = retry_text.find(marker)
                        if idx != -1:
                            after = retry_text[idx + len(marker):].strip()
                            for end_marker in ("【表达方式】", "[Expression]"):
                                end_idx = after.find(end_marker)
                                if end_idx != -1:
                                    after = after[:end_idx].strip()
                            retry_reply = after
                            break

                    # Run modality skill with new express content
                    retry_result = await self.modality_skill_engine.execute(
                        failed_modality, retry_text, self.persona, self.llm
                    )
                    if retry_result and retry_result.success:
                        print(f"  [skill] ✅ Retry {attempt}/{MAX_RETRIES} succeeded!")
                        self._pending_retry = {
                            "modality": failed_modality,
                            "reply": retry_reply,
                            "image_path": retry_result.output.get("image_path"),
                            "audio_path": retry_result.output.get("audio_path"),
                        }
                        if retry_result.output.get("image_path"):
                            self._last_image_path = retry_result.output["image_path"]
                        if retry_result.output.get("audio_path"):
                            self._last_audio_path = retry_result.output["audio_path"]
                        break  # success, stop retrying
                    else:
                        print(f"  [skill] ✗ Retry {attempt}/{MAX_RETRIES} failed")
                except Exception as e:
                    print(f"  [skill] ✗ Retry {attempt}/{MAX_RETRIES} error: {e}")
            else:
                # All retries exhausted — system notification
                print(f"  [skill] 💀 All {MAX_RETRIES} retries failed, sending system notification")
                _name = self.persona.name
                _is_zh = getattr(self.persona, 'lang', 'zh') == 'zh'
                _sys_msg = f"{_name}似乎出了点问题" if _is_zh else f"{_name} seems to have an issue"
                self._pending_retry = {
                    "modality": "系统通知",
                    "reply": _sys_msg,
                    "image_path": None,
                    "audio_path": None,
                    "is_system": True,
                }

        return fallback
