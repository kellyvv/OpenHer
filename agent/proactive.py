"""
ProactiveMixin — Drive-driven autonomous messaging for ChatAgent.

Implements the proactive tick: when a drive exceeds its baseline threshold,
the persona can initiate conversation without user input.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from providers.llm.client import ChatMessage
from engine.genome.genome_engine import DRIVES, DRIVE_LABELS
from engine.genome.critic import critic_sense
from agent.parser import extract_reply


# Config defaults (from memory_config.yaml if available)
try:
    import yaml as _yaml
    from pathlib import Path as _Path
    _cfg_path = _Path(__file__).parent.parent / "providers" / "memory" / "evermemos" / "memory_config.yaml"
    _cfg_data = _yaml.safe_load(_cfg_path.read_text()).get("evermemos", {}) if _cfg_path.exists() else {}
except Exception:
    _cfg_data = {}
_DEFAULT_IMPULSE_THRESHOLD = _cfg_data.get("impulse_threshold", 0.8)


class ProactiveMixin:
    """Drive-driven autonomous messaging (proactive tick)."""

    _IMPULSE_THRESHOLD = _DEFAULT_IMPULSE_THRESHOLD

    def _has_impulse(self) -> Optional[tuple]:
        """
        Drive self-check: is any drive significantly above its baseline?

        Returns (drive_id, description) if impulse detected, else None.
        Baseline is emergent (Step 3.5 evolves it each turn via Critic).
        Score = (normalized_frustration - baseline) / baseline.
        Score >= threshold means current desire is significantly above "normal".
        """
        strongest = None
        max_score = 0.0
        for d in DRIVES:
            norm_frust = self.metabolism.frustration[d] / 5.0  # 0~1
            baseline = self.agent.drive_baseline[d]             # 0~1
            # Relative deviation from baseline
            score = norm_frust * (1.0 + baseline)
            if score > max_score:
                max_score = score
                strongest = d

        if max_score >= self._IMPULSE_THRESHOLD and strongest:
            desc = f"内心的{DRIVE_LABELS[strongest]}冲动正在变强。"
            return (strongest, desc)
        return None

    async def proactive_tick(self) -> Optional[dict]:
        """
        Drive-driven autonomous tick. No user input required.

        Flow:
          1. Advance metabolism (Drive energy evolves with time)
          2. Check impulse (Drive deviation from baseline)
          3. If impulse → memory flashback + build stimulus
          4. Critic/Actor pipeline (same as chat, frozen learning)
          5. Actor decides: speak or stay silent

        Returns:
            {'reply': str, 'modality': str, 'monologue': str,
             'proactive': True, 'drive_id': str, 'tick_id': str}
            or None (no impulse / decided to stay silent)
        """
        async with self._turn_lock:
            return await self._proactive_tick_inner()

    async def _proactive_tick_inner(self) -> Optional[dict]:
        """Inner proactive tick (called under lock)."""
        start = time.time()
        tick_id = str(uuid.uuid4())

        # ── Step 1: Advance metabolism ──
        self.metabolism.time_metabolism(start)

        # ── Step 2: Drive self-check ──
        impulse = self._has_impulse()
        if not impulse:
            return None  # No impulse → zero cost (no LLM calls)

        drive_id, impulse_desc = impulse
        print(f"  [proactive] 💭 impulse detected: {impulse_desc}")

        # ── Step 3: Memory flashback ──
        # Search EverMemOS using impulse content — simulates "a memory pops up"
        flashback_parts = []
        if self.evermemos and self.evermemos.available:
            try:
                facts, episodes, profile = await self.evermemos.search_relevant_memories(
                    query=impulse_desc,
                    user_id=self.evermemos_uid,
                    group_id=self._group_id,
                )
                if episodes:
                    flashback_parts.append(f"[记忆闪回] {episodes}")
                if facts:
                    flashback_parts.append(f"[闪回细节] {facts}")
            except Exception as e:
                print(f"  [proactive] flashback search failed: {e}")

        # ── Step 4: Build stimulus (data formatting, not decision logic) ──
        name = self.user_name or "你"
        hours = (start - self._last_active) / 3600 if self._last_active > 0 else 0

        parts = [f"[内在状态] 已{hours:.0f}小时未与{name}互动。{impulse_desc}"]
        parts.extend(flashback_parts)
        if self._foresight_text:
            parts.append(f"[预感] {self._foresight_text}")

        stimulus = "\n".join(parts)

        # ── Step 5: Load session context (if not already cached) ──
        relationship_prior = await self._evermemos_gather()

        # ── Step 6: Critic perception (same pipeline, stimulus instead of user_message) ──
        frust_dict = {d: round(self.metabolism.frustration[d], 2) for d in DRIVES}
        _p = self.persona
        _mbti = getattr(_p, 'mbti', '') or '未知'
        _tags = '、'.join(getattr(_p, 'tags', [])[:3])
        _persona_hint = f"{_p.name} ({_mbti}) — {_tags}" if _tags else f"{_p.name} ({_mbti})"
        context, frustration_delta, rel_delta, drive_satisfaction = await critic_sense(
            stimulus, self.llm, frust_dict,
            user_profile=self._user_profile,
            episode_summary=self._episode_summary,
            persona_hint=_persona_hint,
        )

        # ── R1: FROZEN — Do NOT update relationship EMA (no user feedback) ──
        # Read-only: use prior values without writing to EMA
        relationship_4d = {
            'relationship_depth': self._relationship_ema.get('relationship_depth', 0.0),
            'trust_level': self._relationship_ema.get('trust_level', 0.0),
            'emotional_valence': self._relationship_ema.get('emotional_valence', 0.0),
            'pending_foresight': self._relationship_ema.get('pending_foresight', 0.0),
        }
        context.update(relationship_4d)

        # ── Step 7: Metabolism → reward (frustration release) ──
        reward = self.metabolism.apply_llm_delta(frustration_delta)
        self.metabolism.sync_to_agent(self.agent)

        # ── R1: FROZEN — Do NOT evolve drive baselines (Step 3.5) ──
        # ── R1: FROZEN — Do NOT do Hebbian learning (Step 10) ──

        # ── Step 8: Compute signals + noise ──
        base_signals = self.agent.compute_signals(context)
        total_frust = self.metabolism.total()
        noisy_signals = self.metabolism.apply_thermodynamic_noise(base_signals)

        # ── Step 9: Build Feel prompt (Pass 1) ──
        self.style_memory.set_clock(start)
        few_shot = self.style_memory.build_few_shot_prompt(context, top_k=3, monologue_only=True, lang=self.persona.lang)
        feel_prompt = self._build_feel_prompt(few_shot, noisy_signals)

        # ── Step 9.5: Memory injection into Feel prompt (foresight is key driver here) ──
        if self._session_ctx and self._session_ctx.has_history:
            if self.persona.lang == 'en':
                if self._user_profile:
                    feel_prompt += f"\n\n[{name}'s preferences] {self._user_profile[:300]}"
                if self._episode_summary:
                    feel_prompt += f"\n\n[Past interactions with {name}] {self._episode_summary[:300]}"
                if self._foresight_text:
                    feel_prompt += f"\n\n[Worth noting] {self._foresight_text}"
            else:
                if self._user_profile:
                    feel_prompt += f"\n\n[关于{name}的偏好] {self._user_profile[:300]}"
                if self._episode_summary:
                    feel_prompt += f"\n\n[与{name}过去发生的事] {self._episode_summary[:300]}"
                if self._foresight_text:
                    feel_prompt += f"\n\n[近期值得关心] {self._foresight_text}"

        # ── Step 10a: Pass 1 — Feel (generates monologue only, no reply instruction) ──
        feel_messages = [
            ChatMessage(role="system", content=feel_prompt),
            ChatMessage(role="user", content=stimulus),
        ]
        feel_response = await self.llm.chat(feel_messages)
        monologue = self._extract_monologue(feel_response.content)

        # ── Step 10b: Pass 2 — Express (monologue → reply + modality) ──
        turn_lang = self._detect_turn_lang(stimulus)
        express_few_shot = self.style_memory.build_few_shot_prompt(
            context, top_k=2, monologue_only=False, lang=turn_lang,
        )
        express_prompt = self._build_express_prompt(monologue, few_shot=express_few_shot, signals=noisy_signals)
        express_messages = [
            ChatMessage(role="system", content=express_prompt),
            ChatMessage(role="user", content=stimulus),
        ]
        express_response = await self.llm.chat(express_messages)
        _, reply, modality = extract_reply(express_response.content)

        elapsed = start and (time.time() - start) or 0
        if elapsed > 300:
            print(f"  [proactive] ⚠️ tick took {elapsed:.0f}s, approaching TTL")

        # ── Actor decided to stay silent ──
        if modality == "静默" or not reply.strip():
            print(f"  [proactive] 🤫 decided to stay silent: {monologue[:60]}")
            return None

        # ── Actor decided to speak ──
        print(f"  [proactive] 💬 sending: {reply[:40]}...")

        # Update last_active (proactive message counts as activity)
        self._last_active = time.time()

        return {
            'reply': reply,
            'modality': modality,
            'monologue': monologue,
            'proactive': True,
            'drive_id': drive_id,
            'tick_id': tick_id,
        }
