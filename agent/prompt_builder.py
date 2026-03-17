"""
PromptBuilderMixin — Feel/Express prompt construction for ChatAgent.

Extracted from chat_agent.py to reduce file size.
Used as a mixin: ChatAgent(PromptBuilderMixin, ...).
"""

from __future__ import annotations

from engine.genome.genome_engine import SIGNALS
from engine.prompt_registry import render_prompt, load_signal_config


class PromptBuilderMixin:
    """Prompt construction methods for the persona engine's two-pass architecture."""

    def _build_feel_prompt(self, few_shot: str, signals: dict) -> str:
        """
        Build Pass 1 (Feel) prompt — generates monologue only.

        Builds identity anchor + signal injection, renders actor_feel template
        (no reply output format — monologue only).
        """
        import datetime as _dt

        # ── Identity anchor (only factual identity, no behavioral labels) ──
        persona = self.persona
        is_en = persona.lang == 'en'
        if is_en:
            identity = f"[Character]\n{persona.name}"
            if persona.age:
                identity += f", {persona.age} years old"
            if persona.gender:
                identity += f", {persona.gender}"
            identity += "."
        else:
            identity = f"【角色】\n{persona.name}"
            if persona.age:
                identity += f"，{persona.age}岁"
            if persona.gender:
                identity += f"，{persona.gender}"
            identity += "。"

        # Signal injection
        signal_injection = self.agent.to_prompt_injection_from_signals(
            signals,
            signal_overrides=self.persona.signal_overrides,
            frustration=self.metabolism.frustration,
            lang=self.persona.lang,
        )

        # Trend injection
        if self._prev_signals:
            trend_lines = []
            for sig in SIGNALS:
                delta = signals[sig] - self._prev_signals.get(sig, 0.5)
                if abs(delta) > self.trend_delta:
                    direction = ("trending up" if delta > 0 else "trending down") if is_en else ("上升" if delta > 0 else "下降")
                    from engine.genome.genome_engine import SIGNAL_LABELS as _FB_LABELS
                    sig_config = load_signal_config()
                    sig_info = sig_config.get('signals', {}).get(sig, {})
                    label = sig_info.get('emoji_label', _FB_LABELS.get(sig, sig))
                    trend_word = "noticeably" if is_en else "明显"
                    trend_lines.append(
                        f"- {label}{trend_word} {direction} "
                        f"({self._prev_signals[sig]:.2f} → {signals[sig]:.2f})"
                    )
            if trend_lines:
                trend_header = "【Trend】" if is_en else "【变化趋势】"
                signal_injection += f"\n{trend_header}\n" + "\n".join(trend_lines[:3])

        now = _dt.datetime.now()
        if is_en:
            signal_injection += f"\n\n【Time】{now.strftime('%Y-%m-%d')} {now.strftime('%H:%M')}"
        else:
            signal_injection += f"\n\n【当前时间】{now.strftime('%Y年%m月%d日')} {now.strftime('%H:%M')}"

        combined_injection = identity + "\n\n" + signal_injection

        # Inject skills prompt — legacy path (skills_prompt param), will be removed
        if self.skills_prompt:
            combined_injection += "\n\n" + self.skills_prompt

        template_name = "actor_feel_en" if is_en else "actor_feel"
        return render_prompt(
            template_name,
            few_shot=few_shot,
            signal_injection=combined_injection,
        )

    def _build_express_prompt(self, monologue: str, few_shot: str = "",
                               signals: dict = None,
                               modality_skill_engine=None) -> str:
        """
        Build Pass 2 (Express) prompt — monologue → reply + modality.

        Identity + signals + monologue + optional reply few-shot.
        Signals give Express the same behavioral calibration as Feel,
        enabling emergent length/modality decisions from persona state.
        """
        persona = self.persona
        is_en = persona.lang == 'en'
        if is_en:
            identity = persona.name
            if persona.age:
                identity += f", {persona.age} years old"
            if persona.gender:
                identity += f", {persona.gender}"
            identity += "."
        else:
            identity = persona.name
            if persona.age:
                identity += f"，{persona.age}岁"
            if persona.gender:
                identity += f"，{persona.gender}"
            identity += "。"

        # Signal injection — same source as Feel pass
        signal_text = ""
        if signals:
            signal_text = self.agent.to_prompt_injection_from_signals(
                signals,
                signal_overrides=self.persona.signal_overrides,
                frustration=self.metabolism.frustration,
                lang=self.persona.lang,
            )

        template_name = "actor_express_en" if is_en else "actor_express"
        rendered = render_prompt(
            template_name,
            identity=identity,
            monologue=monologue,
            signal_injection=signal_text,
        )

        # Prepend reply few-shot when available (LLM sees speech examples first)
        if few_shot:
            header = "[Character speech reference]" if is_en else "[角色说话参考]"
            rendered = f"{header}\n{few_shot}\n\n{rendered}"

        # Inject modality skill descriptions — LLM knows what capabilities exist
        if modality_skill_engine:
            skill_prompt = modality_skill_engine.build_prompt()
            if skill_prompt:
                rendered += "\n\n" + skill_prompt

        return rendered

    def _build_single_prompt(self, few_shot: str, signals: dict,
                              modality_skill_engine=None) -> str:
        """
        Build single-pass prompt — generates monologue + reply + modality in one call.

        Combines Feel and Express into one template with full context.
        """
        import datetime as _dt

        persona = self.persona
        is_en = persona.lang == 'en'

        # Identity anchor
        if is_en:
            identity = f"[Character]\n{persona.name}"
            if persona.age:
                identity += f", {persona.age} years old"
            if persona.gender:
                identity += f", {persona.gender}"
            identity += "."
        else:
            identity = f"【角色】\n{persona.name}"
            if persona.age:
                identity += f"，{persona.age}岁"
            if persona.gender:
                identity += f"，{persona.gender}"
            identity += "。"

        # Signal injection
        signal_injection = self.agent.to_prompt_injection_from_signals(
            signals,
            signal_overrides=self.persona.signal_overrides,
            frustration=self.metabolism.frustration,
            lang=self.persona.lang,
        )

        # Trend injection
        if self._prev_signals:
            trend_lines = []
            for sig in SIGNALS:
                delta = signals[sig] - self._prev_signals.get(sig, 0.5)
                if abs(delta) > self.trend_delta:
                    direction = ("trending up" if delta > 0 else "trending down") if is_en else ("上升" if delta > 0 else "下降")
                    from engine.genome.genome_engine import SIGNAL_LABELS as _FB_LABELS
                    sig_config = load_signal_config()
                    sig_info = sig_config.get('signals', {}).get(sig, {})
                    label = sig_info.get('emoji_label', _FB_LABELS.get(sig, sig))
                    trend_word = "noticeably" if is_en else "明显"
                    trend_lines.append(
                        f"- {label}{trend_word} {direction} "
                        f"({self._prev_signals[sig]:.2f} → {signals[sig]:.2f})"
                    )
            if trend_lines:
                trend_header = "【Trend】" if is_en else "【变化趋势】"
                signal_injection += f"\n{trend_header}\n" + "\n".join(trend_lines[:3])

        now = _dt.datetime.now()
        if is_en:
            signal_injection += f"\n\n【Time】{now.strftime('%Y-%m-%d')} {now.strftime('%H:%M')}"
        else:
            signal_injection += f"\n\n【当前时间】{now.strftime('%Y年%m月%d日')} {now.strftime('%H:%M')}"

        combined_injection = identity + "\n\n" + signal_injection

        template_name = "actor_single"
        rendered = render_prompt(
            template_name,
            few_shot=few_shot,
            signal_injection=combined_injection,
        )

        # Inject modality skill descriptions
        if modality_skill_engine:
            skill_prompt = modality_skill_engine.build_prompt()
            if skill_prompt:
                rendered += "\n\n" + skill_prompt

        return rendered

    @staticmethod
    def _detect_turn_lang(text: str) -> str:
        """Detect language from user input: 'zh' if CJK chars present, else 'en'."""
        return 'zh' if any('\u4e00' <= c <= '\u9fff' for c in text[:30]) else 'en'

    @staticmethod
    def _extract_monologue(raw: str) -> str:
        """
        Extract monologue from Pass 1 output.

        Pass 1 template ends with 【内心独白】, so model continues directly.
        Output likely does NOT contain the marker — use full text.
        If marker is present (Chinese or English fallback), extract content after it.
        """
        for marker in ("【内心独白】", "[Inner Monologue]"):
            idx = raw.find(marker)
            if idx != -1:
                return raw[idx + len(marker):].strip()
        return raw.strip()

    def _should_crystallize(self, reward: float, context: dict) -> bool:
        """
        Step 4 gate: decide if the PREVIOUS turn's action is worth crystallizing.

        Composite score replaces the fixed `reward > 0.3` threshold.
        Uses current-turn Critic context as user-reaction feedback (RL pattern).

        Hard floor: never crystallize when reward < -0.5 (clearly bad turn).
        Hard ceiling: always crystallize when reward > 0.8 (clearly great turn).
        """
        if reward < -0.5:
            return False
        if reward > 0.8:
            return True

        novelty = context.get('novelty_level', 0.0)
        engagement = context.get('user_engagement', 0.0)
        conflict = context.get('conflict_level', 0.0)

        # Composite: reward matters most, novelty×engagement captures "interesting",
        # low conflict captures "safe to remember"
        crystal_score = (
            0.4 * reward
            + 0.3 * (novelty * engagement)
            + 0.3 * (1.0 - conflict)
        )

        should = crystal_score > self.crystal_threshold
        if should:
            print(f"  [crystal] score={crystal_score:.3f} "
                  f"(reward={reward:.2f}, novelty={novelty:.2f}×eng={engagement:.2f}, "
                  f"conflict={conflict:.2f}) → crystallize")
        return should

    def _memory_injection_budget(self, context: dict) -> tuple[int, int]:
        """
        Step 8.5: compute dynamic character budgets for profile and episode injection.

        Deep/intimate conversations get more memory context (up to 800/600).
        Shallow/casual chats get minimal context (200/150).
        Linear interpolation based on max(conversation_depth, topic_intimacy).

        Returns: (profile_budget, episode_budget) in characters.
        """
        depth = context.get('conversation_depth', 0.0)
        intimacy = context.get('topic_intimacy', 0.0)
        # Use the higher of depth/intimacy as the driver
        t = max(depth, intimacy)
        # Linear interpolation: t=0 → min, t=1 → max
        profile_budget = int(200 + 600 * t)   # 200..800
        episode_budget = int(150 + 450 * t)   # 150..600
        return profile_budget, episode_budget

    def _blend_injection(
        self, relevant: str, static: str, budget: int,
    ) -> str:
        """
        Blend relevant (query-based) and static (session-init) memory text.

        Strategy: 80% relevant + 20% static floor ensures long-term profile
        stability even when search results are highly focused.
        When static is empty, relevant gets full budget (no waste).
        Falls back to pure static when no relevant results available.
        """
        if not relevant and not static:
            return ""
        if not relevant:
            # Mark this turn as fallback (only once per turn)
            if not self._turn_used_fallback:
                self._turn_used_fallback = True
                self._search_fallback += 1
            return static[:budget]
        # Has relevant: mark turn as relevant-injected
        if not static:
            # No static → give relevant full budget (no 20% waste)
            return relevant[:budget]
        # Both present → 80/20 split
        rel_budget = int(budget * 0.8)
        sta_budget = budget - rel_budget
        blended = relevant[:rel_budget]
        blended += "；" + static[:sta_budget]
        return blended
