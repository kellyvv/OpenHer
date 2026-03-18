"""
ChatAgent — Genome v10 Hybrid lifecycle-powered conversational agent.

Per-turn lifecycle (with EverMemOS async memory):
  0.  EverMemOS session context (first turn only: async load profile)
  1.  Time metabolism (DriveMetabolism)
  2.  Critic perception (LLM → 8D context + frustration delta + relationship delta)
  2.5 Semi-emergent relationship update:
       posterior = clip(prior + LLM_delta)
       alpha = clip(0.15 + 0.5*depth, 0.15, 0.65)
       ema_state = alpha*posterior + (1-alpha)*prev
  3.  LLM metabolism (apply frustration delta → reward)
  3.5 Critic-driven Drive baseline evolution (BASELINE_LR=0.01, every turn)
       frustration_delta > 0 → drive not satisfied → baseline rises
       frustration_delta < 0 → drive satisfied → baseline eases
       No math formula. Purely LLM-judged, same structure as Hebbian learning.
  4.  Crystallization gate (composite score: reward + novelty×engagement + conflict penalty)
  5.  Compute signals (Agent neural network, 12D context)
  6.  Thermodynamic noise injection
  7.  KNN retrieval (ContinuousStyleMemory)
  8.  Build Actor prompt (persona + signals + few-shot)
  8.5 Profile/Episode memory injection (user facts + narrative)
  9.  LLM Actor (generate response with monologue + reply)
  10. Hebbian learning (Agent.step)
  11. EverMemOS store_turn → asyncio.create_task (non-blocking)
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from typing import AsyncIterator, Optional

from providers.llm.client import LLMClient, ChatMessage, ChatResponse
from persona.loader import Persona
from engine.genome.genome_engine import Agent, DRIVES, SIGNALS, DRIVE_LABELS
from engine.genome.drive_metabolism import DriveMetabolism, apply_thermodynamic_noise
from engine.genome.critic import critic_sense
from engine.genome.style_memory import ContinuousStyleMemory
from memory.memory_store import MemoryStore

# Parser utilities (extracted to agent/parser.py)
from agent.parser import extract_reply, _parse_modality, _SECTION_RE, _TAG_MAP

# Mixin modules (extracted from this file)
from agent.prompt_builder import PromptBuilderMixin
from agent.evermemos_mixin import EverMemosMixin
from agent.modality_retry import ModalityRetryMixin
from agent.proactive import ProactiveMixin




class ChatAgent(PromptBuilderMixin, EverMemosMixin, ModalityRetryMixin, ProactiveMixin):
    """
    Genome v8 lifecycle-powered persona chat agent.

    Each instance represents one user ↔ persona conversation session,
    backed by a living personality engine (Agent + DriveMetabolism +
    ContinuousStyleMemory).
    """

    def __init__(
        self,
        persona: Persona,
        llm: LLMClient,
        user_id: str = "default_user",
        user_name: Optional[str] = None,
        task_skill_engine=None,
        modality_skill_engine=None,
        skills_prompt: Optional[str] = None,
        skill_engine=None,
        memory_store: Optional[MemoryStore] = None,
        genome_seed: int = 42,
        genome_data_dir: Optional[str] = None,
        max_history: int = 40,
        evermemos=None,
        task_log_store=None,
    ):
        self.persona = persona
        self.llm = llm
        self.user_id = user_id
        self.user_name = user_name
        # Dual skill engines (isolated)
        self.task_skill_engine = task_skill_engine or skill_engine  # backward compat
        self.modality_skill_engine = modality_skill_engine
        self.skills_prompt = skills_prompt or ""
        self.task_log_store = task_log_store

        self.memory_store = memory_store
        self.max_history = max_history

        # ── Genome v8 Engine (with per-persona params) ──
        engine_params = persona.engine_params
        self.agent = Agent(seed=genome_seed, engine_params=engine_params)
        self.metabolism = DriveMetabolism(engine_params=engine_params)

        # Per-persona tunable parameters (with defaults)
        self.baseline_lr = engine_params.get('baseline_lr', 0.01)
        self.elasticity = engine_params.get('elasticity', 0.05)
        self.crystal_threshold = engine_params.get('crystal_threshold', 0.50)
        self.trend_delta = engine_params.get('trend_delta', 0.15)

        # Apply persona-specific genome seed (initial conditions only)
        if persona.drive_baseline:
            for d, v in persona.drive_baseline.items():
                if d in self.agent.drive_baseline:
                    self.agent.drive_baseline[d] = float(v)
                    self.agent.drive_state[d] = float(v)

        # Snapshot initial baseline for elastic pullback (persona gravity)
        self._initial_baseline = dict(self.agent.drive_baseline)

        self.style_memory = ContinuousStyleMemory(
            agent_id=f"{persona.persona_id}_{user_id}",
            db_dir=genome_data_dir,
            persona_id=persona.persona_id,
            hawking_gamma=engine_params.get('hawking_gamma'),
        )

        # ── Conversation state ──
        self.history: list[ChatMessage] = []
        self._turn_count: int = 0
        self._last_action: Optional[dict] = None
        self._last_critic: Optional[dict] = None
        self._last_signals: Optional[dict] = None
        self._prev_signals: Optional[dict] = None  # Previous turn signals for trend injection
        self._last_reward: float = 0.0
        self._last_modality: str = ""
        self._skill_outputs: dict = {}  # all modality skill results, reset per turn
        self._last_drive_satisfaction: dict = {}
        # ── Concurrency lock (R2: serialize chat/stream/proactive_tick) ──
        self._turn_lock = asyncio.Lock()

        # ── Proactive tick state ──
        self._last_active: float = time.time()
        self._state_version: int = 0
        self._interaction_cadence: float = 0.0  # EMA of interaction interval (seconds)

        # ── EverMemOS Async Memory ──
        self.evermemos = evermemos
        self.evermemos_uid = f"{user_id}__{persona.persona_id}"  # sender for user messages in store
        self._group_id = f"{persona.persona_id}__{user_id}"  # group_id scopes per user-persona pair
        self._user_profile: str = ""
        self._episode_summary: str = ""   # Narrative history for Critic + Actor
        self._session_ctx = None   # SessionContext loaded on first turn

        # ── Phase 1 Emergence: Relationship EMA state ──
        self._relationship_ema: dict = {}  # Populated on first turn from prior

        # ── Phase 3: Query-based relevance retrieval ──
        self._relevant_facts: str = ""      # Populated by async search from previous turn
        self._relevant_episodes: str = ""   # Populated by async search from previous turn
        self._relevant_profile: str = ""    # P1: Profile attrs from search
        self._foresight_text: str = ""      # P1: Foresight content from session context
        self._search_task: Optional[asyncio.Task] = None  # Tracks background search
        self._search_turn_id: int = 0       # Turn that fired the search (concurrency guard)
        self._search_hit: int = 0           # Observability: successful search collections
        self._search_timeout: int = 0       # Observability: timeout fallbacks
        self._search_fallback: int = 0      # Observability: turns that used static (per-turn)
        self._search_relevant_used: int = 0 # Observability: turns that injected relevant
        self._turn_used_fallback: bool = False  # Per-turn flag, reset each turn

        evermemos_status = "ON" if (evermemos and evermemos.available) else "OFF"
        m = self.metabolism
        print(f"✓ ChatAgent(Genome v10+EverMemOS) 初始化: {persona.name} ↔ {user_name or user_id} "
              f"(seed={genome_seed}, memories={self.style_memory.total_memories}, evermemos={evermemos_status})")
        print(f"  [metabolism] conn_k={m.connection_hunger_k}, nov_k={m.novelty_hunger_k}, "
              f"decay={m.decay_lambda}, temp_coeff={m.temp_coeff}, temp_floor={m.temp_floor}")


    def pre_warm(self, scenarios: list | None = None, steps_per_scenario: int = 20) -> None:
        """
        Pre-warm the Agent's neural network via simulated scenario steps.

        Call this ONCE on brand-new agents (before any real conversation).
        Restored agents already have shaped weights — calling this again
        would corrupt their evolved personality; always guard with age check:

            if agent.agent.age == 0:
                agent.pre_warm()

        Args:
            scenarios:           Scenario sequence; defaults to V10 standard 3-phase.
            steps_per_scenario:  Steps per scenario (default 20 → 60 total).
        """
        from engine.genome.genome_engine import simulate_conversation, DRIVES
        if scenarios is None:
            scenarios = ['分享喜悦', '吵架冲突', '深夜心事']
        simulate_conversation(self.agent, scenarios, steps_per_scenario=steps_per_scenario)

        # Reset drive_state to baseline after pre_warm.
        # Pre_warm shaped the NN weights (W1/W2) — that's its real job.
        # The saturated drive_state (all → ~1.0) is a side effect of 60 steps
        # of positive-biased rewards and must not leak into real conversation.
        for d in DRIVES:
            self.agent.drive_state[d] = self.agent.drive_baseline[d]
        self.agent._frustration = 0.0



    # ── Prompt building, memory blending, crystallization ──
    # See agent/prompt_builder.py (PromptBuilderMixin)

    async def chat(self, user_message: str, on_feel_done=None) -> dict:
        """
        Process a user message through the full Genome v10 lifecycle.
        Returns only the reply (monologue is stored internally).
        on_feel_done: optional async callback invoked after Feel pass completes.
        """
        async with self._turn_lock:
            return await self._chat_inner(user_message, on_feel_done=on_feel_done)

    async def _run_task_skills(self, user_message: str) -> str:
        """Step -1: Run task skill ReAct loop before persona engine.

        Returns user_message (unchanged or enriched with observations).
        """
        if not self.task_skill_engine:
            return user_message
        try:
            observations = await self.task_skill_engine.react_loop(user_message, self.llm)
            if observations:
                user_message = (
                    f"{user_message}\n\n"
                    f"[以下是真实查询数据，回复中必须自然融入关键数值，不要省略]\n"
                    f"{observations}"
                )
                print(f"  [skill] ✅ 数据已注入 ({len(observations)} chars), 继续引擎处理")
        except Exception as e:
            print(f"  [skill] ⚠ ReAct loop failed ({e}), fallback to persona engine")
        return user_message

    async def _chat_inner(self, user_message: str, on_feel_done=None) -> dict:
        """Inner chat implementation (called under lock)."""
        # ── Step -1: Task skill ReAct loop (before persona engine) ──
        user_message = await self._run_task_skills(user_message)

        # ── Step 0: persona engine (zero changes below this line) ──
        self._turn_count += 1
        self._turn_used_fallback = False  # Reset per-turn fallback flag
        now = time.time()

        # Update interaction cadence (EMA)
        if self._last_active > 0:
            delta = now - self._last_active
            if self._interaction_cadence > 0:
                self._interaction_cadence = 0.3 * delta + 0.7 * self._interaction_cadence
            else:
                self._interaction_cadence = delta
        self._last_active = now

        # ── Step 0: EverMemOS session context (first turn only) ──
        relationship_prior = await self._evermemos_gather()

        # ── Step 1: Time metabolism ──
        delta_h = self.metabolism.time_metabolism(now)

        # ── Step 2: Critic perception (8D context + 5D delta + 3D relationship) ──
        frust_dict = {d: round(self.metabolism.frustration[d], 2) for d in DRIVES}
        # Build persona hint for persona-aware Critic
        _p = self.persona
        _mbti = getattr(_p, 'mbti', '') or '未知'
        _persona_hint = f"{_p.name} ({_mbti})"
        context, frustration_delta, rel_delta, drive_satisfaction = await critic_sense(
            user_message, self.llm, frust_dict,
            user_profile=self._user_profile,
            episode_summary=self._episode_summary,
            persona_hint=_persona_hint,
        )

        # ── Step 2.5: Semi-emergent relationship update (prior + delta + clip + EMA) ──
        relationship_4d = self._apply_relationship_ema(
            relationship_prior, rel_delta, context.get('conversation_depth', 0.0)
        )
        context.update(relationship_4d)  # Merge 8D + 4D → 12D
        self._last_critic = context  # Store full 12D context (after merge)

        # ── Step 3: LLM metabolism → reward ──
        reward = self.metabolism.apply_llm_delta(frustration_delta)
        self.metabolism.sync_to_agent(self.agent)
        self._last_reward = reward

        # ── Step 3.5: Critic-driven Drive baseline evolution ──
        # Elastic baseline: spring force pulls baseline back toward persona origin.
        # Prevents unbounded drift while preserving local emergence.
        # frustration_delta > 0 = drive not satisfied this turn → baseline rises (hungers more)
        # frustration_delta < 0 = drive satisfied this turn → baseline eases
        for d in DRIVES:
            shift = frustration_delta.get(d, 0.0) * self.baseline_lr
            drift = self.agent.drive_baseline[d] - self._initial_baseline.get(d, 0.5)
            pull_back = -drift * self.elasticity
            self.agent.drive_baseline[d] = max(0.1, min(0.95,
                self.agent.drive_baseline[d] + shift + pull_back
            ))

        # ── Step 4: Crystallization gate (last action) ──
        if self._last_action and self._should_crystallize(reward, context):
            self.style_memory.set_clock(now)
            self.style_memory.crystallize(
                self._last_action['context'],
                self._last_action['monologue'],
                self._last_action['reply'],
                self._last_action['user_input'],
            )

        # ── Step 5: Compute signals (context from Critic directly) ──
        base_signals = self.agent.compute_signals(context)

        # ── Step 6: Thermodynamic noise ──
        total_frust = self.metabolism.total()
        noisy_signals = self.metabolism.apply_thermodynamic_noise(base_signals)
        self._prev_signals = self._last_signals  # Track for trend injection
        self._last_signals = noisy_signals

        # ── Step 7: KNN retrieval (full examples for single-pass) ──
        self.style_memory.set_clock(now)
        few_shot = self.style_memory.build_few_shot_prompt(
            context, top_k=3, monologue_only=False, lang=self.persona.lang,
        )

        # ── Step 8: Build single-pass prompt (actor_single template) ──
        single_prompt = self._build_single_prompt(
            few_shot, noisy_signals,
            modality_skill_engine=self.modality_skill_engine,
        )

        # ── Step 8.5: Memory injection into prompt ──
        if self._session_ctx and self._session_ctx.has_history:
            await self._collect_search_results()
            profile_budget, episode_budget = self._memory_injection_budget(context)
            profile_text = self._blend_injection(
                self._relevant_facts, self._user_profile, profile_budget
            )
            episode_text = self._blend_injection(
                self._relevant_episodes, self._episode_summary, episode_budget
            )
            name = self.user_name or "你"
            if self.persona.lang == 'en':
                if profile_text:
                    single_prompt += f"\n\n[{name}'s preferences] {profile_text}"
                if episode_text:
                    single_prompt += f"\n\n[Past interactions with {name}] {episode_text}"
                if self._foresight_text:
                    single_prompt += f"\n\n[Worth noting] {self._foresight_text}"
                if self._relevant_profile:
                    single_prompt += f"\n\n[{name}'s profile] {self._relevant_profile}"
            else:
                if profile_text:
                    single_prompt += f"\n\n[关于{name}的偏好] {profile_text}"
                if episode_text:
                    single_prompt += f"\n\n[与{name}过去发生的事] {episode_text}"
                if self._foresight_text:
                    single_prompt += f"\n\n[近期值得关心] {self._foresight_text}"
                if self._relevant_profile:
                    single_prompt += f"\n\n[{name}的画像] {self._relevant_profile}"
            if self._relevant_facts or self._relevant_episodes or self._relevant_profile:
                self._search_relevant_used += 1

        # ── Step 9: Single-pass LLM call ──

        single_messages = [ChatMessage(role="system", content=single_prompt)]
        single_messages.extend(self.history[-self.max_history:])  # Full history
        single_messages.append(ChatMessage(role="user", content=user_message))

        # Notify caller that prompt is built (typing indicator can start)
        if on_feel_done:
            await on_feel_done()

        single_response = await self.llm.chat(single_messages)
        monologue, reply, modality = extract_reply(single_response.content)

        # ── Step 9b: Modality skill execution ──
        self._skill_outputs = {}     # reset each turn
        self._pending_retry = None    # reset each turn
        skill_result = None           # default when no skill runs

        # Extract raw modality text (full LLM output after 【表达方式】)
        _raw_mod = ""
        _matches = list(_SECTION_RE.finditer(single_response.content))
        if _matches:
            _raw_mod = single_response.content[_matches[-1].end():].strip()
            print(f"  [express] raw_modality='{_raw_mod[:80]}'")

        # Scan raw_modality for registered SKILL keywords — LLM plans execution
        if self.modality_skill_engine and _raw_mod:
            skill_results = await self.modality_skill_engine.plan_and_execute(
                raw_modality=_raw_mod,
                raw_output=single_response.content,
                persona=self.persona,
                llm=self.llm,
                chat_history=self.history,
            )
            for skill_result in skill_results:
                if not skill_result.success:
                    continue
                self._skill_outputs.update(skill_result.output)

            # Modality from LLM plan, not parser
            if self._skill_outputs.get("_modality"):
                modality = self._skill_outputs["_modality"]

            if not skill_results:
                # No skills matched — plain text
                pass
            elif all(not r.success for r in skill_results):
                # All skills failed — fallback
                print(f"  [skill] ⚠ All skills failed, triggering LLM fallback")
                fallback_reply = await self._modality_failure_with_retry(
                    modality, reply, single_response.content
                )
                if fallback_reply:
                    reply = fallback_reply
                modality = "文字"
                self._fallback_history_added = True

        # ── Step 10: Hebbian learning ──
        clamped_reward = max(-1.0, min(1.0, reward))
        self.agent.step(context, reward=clamped_reward, drive_satisfaction=drive_satisfaction)
        self._last_drive_satisfaction = drive_satisfaction
        # ── Update state ──
        self.history.append(ChatMessage(role="user", content=user_message))
        if not getattr(self, '_fallback_history_added', False):
            self.history.append(ChatMessage(role="assistant", content=reply))
        self._fallback_history_added = False

        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        self._last_action = {
            'context': context,
            'monologue': monologue,
            'reply': reply,
            'modality': modality,
            'user_input': user_message,
        }
        self._last_modality = modality

        # Store facts in keyword memory (if available)
        if self.memory_store:
            self.memory_store.add(
                user_id=self.user_id,
                persona_id=self.persona.persona_id,
                content=user_message,
                category="user_message",
                importance=context.get('entropy', 0.5),
            )

        sat_str = ' '.join(f'{d[:3]}={v:.2f}' for d, v in drive_satisfaction.items() if v > 0)
        print(f"  [genome] reward={reward:.2f} temp={self.metabolism.temperature():.3f} modality={modality[:30]}")
        print(f"  [feel] monologue={monologue[:60]}")
        print(f"  [drive_sat] {sat_str or 'none'}")

        # ── Step 11: EverMemOS store_turn (non-blocking background task) ──
        self._evermemos_store_bg(user_message, reply)

        # ── Step 12: Fire async search for NEXT turn's injection ──
        self._evermemos_search_bg(user_message)

        result = {'reply': reply, 'modality': modality}
        if skill_result and skill_result.success:
            for key in ('image_path', 'audio_path', 'segments', 'delays_ms'):
                if skill_result.output.get(key):
                    result[key] = skill_result.output[key]
        return result

    # _express_wrap removed — SKILL results now injected into user_message
    # and processed through the full persona engine (Feel → Express).

    def _log_task(self, skill_id: str, user_input: str, output: dict, reply: str) -> None:
        """Log task execution to task.db (isolated from persona memory)."""
        if not self.task_log_store:
            return
        try:
            self.task_log_store.log_execution(
                persona_id=self.persona.persona_id,
                skill_id=skill_id,
                user_input=user_input,
                command=output.get("command", ""),
                stdout=output.get("stdout", ""),
                stderr=output.get("stderr", ""),
                success=output.get("success", False),
                reply=reply,
            )
        except Exception as e:
            print(f"  [task_log] save error: {e}")

    async def chat_stream(self, user_message: str) -> AsyncIterator[str]:
        """
        Stream a response through the Genome v10 lifecycle.
        Steps 1-8 run first (Critic, metabolism, KNN), then Actor streams.
        """
        await self._turn_lock.acquire()
        try:
            # ── Step -1: Task skill ReAct loop (before persona engine) ──
            user_message = await self._run_task_skills(user_message)

            # ── Step 0: persona engine (zero changes below this line) ──
            self._turn_count += 1
            self._turn_used_fallback = False
            now = time.time()

            # Update interaction cadence (EMA)
            if self._last_active > 0:
                delta = now - self._last_active
                if self._interaction_cadence > 0:
                    self._interaction_cadence = 0.3 * delta + 0.7 * self._interaction_cadence
                else:
                    self._interaction_cadence = delta
            self._last_active = now

            # ── Step 0: EverMemOS session context (first turn only) ──
            relationship_prior = await self._evermemos_gather()

            # ── Step 1: Metabolism ──
            delta_h = self.metabolism.time_metabolism(now)
            # ── Step 2: Critic perception (8D context + 5D delta + 3D relationship) ──
            frust_dict = {d: round(self.metabolism.frustration[d], 2) for d in DRIVES}
            _p = self.persona
            _mbti = getattr(_p, 'mbti', '') or '未知'
            _tags = '、'.join(getattr(_p, 'tags', [])[:3])
            _persona_hint = f"{_p.name} ({_mbti}) — {_tags}" if _tags else f"{_p.name} ({_mbti})"
            context, frustration_delta, rel_delta, drive_satisfaction = await critic_sense(
                user_message, self.llm, frust_dict,
                user_profile=self._user_profile,
                episode_summary=self._episode_summary,
                persona_hint=_persona_hint,
            )

            # ── Step 2.5: Semi-emergent relationship update ──
            relationship_4d = self._apply_relationship_ema(
                relationship_prior, rel_delta, context.get('conversation_depth', 0.0)
            )
            context.update(relationship_4d)
            self._last_critic = context

            reward = self.metabolism.apply_llm_delta(frustration_delta)
            self.metabolism.sync_to_agent(self.agent)
            self._last_reward = reward

            # ── Step 3.5: Critic-driven Drive baseline evolution ──
            # Elastic baseline: spring force pulls baseline back toward persona origin.
            # Prevents unbounded drift while preserving local emergence.
            for d in DRIVES:
                shift = frustration_delta.get(d, 0.0) * self.baseline_lr
                drift = self.agent.drive_baseline[d] - self._initial_baseline.get(d, 0.5)
                pull_back = -drift * self.elasticity
                self.agent.drive_baseline[d] = max(0.1, min(0.95,
                    self.agent.drive_baseline[d] + shift + pull_back
                ))

            # ── Step 4: Crystallization ──
            if self._last_action and self._should_crystallize(reward, context):
                self.style_memory.set_clock(now)
                self.style_memory.crystallize(
                    self._last_action['context'],
                    self._last_action['monologue'],
                    self._last_action['reply'],
                    self._last_action['user_input'],
                )

            # ── Steps 5-6: Signals + noise ──
            base_signals = self.agent.compute_signals(context)
            total_frust = self.metabolism.total()
            noisy_signals = self.metabolism.apply_thermodynamic_noise(base_signals)
            self._prev_signals = self._last_signals  # Track for trend injection
            self._last_signals = noisy_signals

            # ── Step 7: KNN retrieval (monologue-only for Pass 1) ──
            self.style_memory.set_clock(now)
            few_shot = self.style_memory.build_few_shot_prompt(
                context, top_k=3, monologue_only=True, lang=self.persona.lang,
            )

            # ── Step 8: Build Feel prompt (Pass 1) ──
            feel_prompt = self._build_feel_prompt(few_shot, noisy_signals)

            # ── Step 8.5: Memory injection into Feel prompt ──
            if self._session_ctx and self._session_ctx.has_history:
                await self._collect_search_results()
                profile_budget, episode_budget = self._memory_injection_budget(context)
                profile_text = self._blend_injection(
                    self._relevant_facts, self._user_profile, profile_budget
                )
                episode_text = self._blend_injection(
                    self._relevant_episodes, self._episode_summary, episode_budget
                )
                name = self.user_name or "你"
                if profile_text:
                    feel_prompt += f"\n\n[关于{name}的偏好] {profile_text}"
                if episode_text:
                    feel_prompt += f"\n\n[与{name}过去发生的事] {episode_text}"
                if self._foresight_text:
                    feel_prompt += f"\n\n[近期值得关心] {self._foresight_text}"
                if self._relevant_profile:
                    feel_prompt += f"\n\n[{name}的画像] {self._relevant_profile}"
                if self._relevant_facts or self._relevant_episodes or self._relevant_profile:
                    self._search_relevant_used += 1

            # ── Step 9a: Pass 1 — Feel (non-stream, not pushed to frontend) ──
            # NOTE: No history — context is in signals + Critic, not raw turns.
            feel_messages = [ChatMessage(role="system", content=feel_prompt)]
            feel_messages.append(ChatMessage(role="user", content=user_message))

            feel_response = await self.llm.chat(feel_messages)
            monologue = self._extract_monologue(feel_response.content)

            # Signal to stream consumer that Feel is done → "typing" can start
            yield "__FEEL_DONE__"

            # ── Step 9b: Pass 2 — Express (streamed to frontend) ──
            turn_lang = self._detect_turn_lang(user_message)
            express_few_shot = self.style_memory.build_few_shot_prompt(
                context, top_k=2, monologue_only=False, lang=turn_lang,
            )
            express_prompt = self._build_express_prompt(monologue, few_shot=express_few_shot, signals=noisy_signals, modality_skill_engine=self.modality_skill_engine)
            self._last_express_prompt = express_prompt      # cache for retry
            self._last_user_message = user_message          # cache for retry
            express_messages = [ChatMessage(role="system", content=express_prompt)]
            express_messages.extend(self.history[-4:])
            express_messages.append(ChatMessage(role="user", content=user_message))

            full_response = []
            async for chunk in self.llm.chat_stream(express_messages):
                full_response.append(chunk)
                yield chunk

            # ── Post-stream processing ──
            raw_text = "".join(full_response)
            _, reply, modality = extract_reply(raw_text)

            # ── Modality — let LLM output be the authority ──
            self._skill_outputs = {}       # reset each turn
            self._pending_retry = None     # reset each turn
            skill_result = None
            _raw_mod = ""
            _raw_modality_match = list(_SECTION_RE.finditer(raw_text))
            if _raw_modality_match:
                _raw_mod = raw_text[_raw_modality_match[-1].end():].strip()
                print(f"  [express] raw_modality='{_raw_mod[:80]}'")

            # Scan raw_modality for registered SKILL keywords — LLM plans execution
            if self.modality_skill_engine and _raw_mod:
                # Build structured JSON context for SKILL — clean boundary,
                # prevents SKILL LLM from seeing leaked content in raw Express text
                import json as _json
                structured_context = _json.dumps({
                    "reply": reply,
                    "modality": modality,
                }, ensure_ascii=False)
                print(f"  [skill-context] 📦 {structured_context[:200]}")

                skill_results = await self.modality_skill_engine.plan_and_execute(
                    raw_modality=_raw_mod,
                    raw_output=structured_context,
                    persona=self.persona,
                    llm=self.llm,
                    chat_history=self.history,
                )
                for skill_result in skill_results:
                    if not skill_result.success:
                        continue
                    self._skill_outputs.update(skill_result.output)

                # Modality from LLM plan, not parser
                if self._skill_outputs.get("_modality"):
                    modality = self._skill_outputs["_modality"]

                if skill_results and all(not r.success for r in skill_results):
                    print(f"  [skill] ⚠ All skills failed, triggering LLM fallback")
                    fallback_reply = await self._modality_failure_with_retry(
                        modality, reply, raw_text
                    )
                    if fallback_reply:
                        reply = fallback_reply
                    modality = "文字"
                    self._fallback_history_added = True

            # Step 10: Hebbian learning
            clamped_reward = max(-1.0, min(1.0, reward))
            self.agent.step(context, reward=clamped_reward, drive_satisfaction=drive_satisfaction)
            self._last_drive_satisfaction = drive_satisfaction
            # Update history
            self.history.append(ChatMessage(role="user", content=user_message))
            if not getattr(self, '_fallback_history_added', False):
                self.history.append(ChatMessage(role="assistant", content=reply))
            self._fallback_history_added = False

            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]

            self._last_action = {
                'context': context,
                'monologue': monologue,
                'reply': reply,
                'modality': modality,
                'user_input': user_message,
            }
            self._last_modality = modality

            sat_str = ' '.join(f'{d[:3]}={v:.2f}' for d, v in drive_satisfaction.items() if v > 0)
            print(f"  [genome] reward={reward:.2f} temp={self.metabolism.temperature():.3f} modality={modality[:30]}")
            print(f"  [feel] monologue={monologue[:60]}")
            print(f"  [drive_sat] {sat_str or 'none'}")

            # ── Step 11: EverMemOS store_turn ──
            self._evermemos_store_bg(user_message, reply)

            # ── Step 12: Fire async search for NEXT turn ──
            self._evermemos_search_bg(user_message)
        finally:
            self._turn_lock.release()


    # ── EverMemOS integration ──
    # See agent/evermemos_mixin.py (EverMemosMixin)

    # ── Modality failure with retry ──
    # See agent/modality_retry.py (ModalityRetryMixin)



    def get_status(self) -> dict:
        """Get comprehensive agent status including genome state."""
        mem_stats = self.style_memory.stats()
        metabolism_status = self.metabolism.status_summary()

        # Get top 3 signals for display
        signals_summary = {}
        if self._last_signals:
            sorted_sigs = sorted(
                self._last_signals.items(),
                key=lambda x: abs(x[1] - 0.5),
                reverse=True,
            )[:3]
            signals_summary = {k: round(v, 2) for k, v in sorted_sigs}

        dominant_drive = self.agent.get_dominant_drive()

        # Phase 3 metrics (all per-turn denominators)
        total_searches = self._search_hit + self._search_timeout
        search_hit_rate = self._search_hit / total_searches if total_searches else 0.0
        search_timeout_rate = self._search_timeout / total_searches if total_searches else 0.0
        turns = max(self._turn_count, 1)
        fallback_rate = self._search_fallback / turns
        relevant_injection_ratio = self._search_relevant_used / turns

        return {
            "persona": self.persona.name,
            "dominant_drive": DRIVE_LABELS.get(dominant_drive, dominant_drive),
            "drive_baseline": {d: round(self.agent.drive_baseline[d], 3) for d in DRIVES},
            "drive_state": {d: round(self.agent.drive_state[d], 3) for d in DRIVES},
            "drive_satisfaction": {d: round(v, 3) for d, v in self._last_drive_satisfaction.items()} if self._last_drive_satisfaction else {},
            "signals": signals_summary,
            "temperature": metabolism_status['temperature'],
            "frustration": metabolism_status['total'],
            "history_length": len(self.history),
            "turn_count": self._turn_count,
            "memory_count": mem_stats.get('total', 0),
            "personal_memories": mem_stats.get('personal_count', 0),
            "age": self.agent.age,
            "last_reward": round(self._last_reward, 2),
            "modality": self._last_modality,
            # Relationship EMAs (Phase 1 Emergence)
            "relationship": {
                "depth": round(self._relationship_ema.get('relationship_depth', 0.0), 3),
                "trust": round(self._relationship_ema.get('trust_level', 0.0), 3),
                "valence": round(self._relationship_ema.get('emotional_valence', 0.0), 3),
            },
            "evermemos": "ON" if (self.evermemos and self.evermemos.available) else "OFF",
            "search_hit": self._search_hit,
            "search_timeout": self._search_timeout,
            "search_fallback": self._search_fallback,
            "search_hit_rate": round(search_hit_rate, 3),
            "search_timeout_rate": round(search_timeout_rate, 3),
            "fallback_rate": round(fallback_rate, 3),
            "relevant_injection_ratio": round(relevant_injection_ratio, 3),
            **self._skill_outputs,  # all skill outputs auto-forwarded
        }

    def get_debug_status(self) -> dict:
        """Get full engine state for developer visualization (Plan B: activations only).

        Returns comprehensive debug data for the neural network visualization
        panel. Only called when client sends debug: true.
        """
        # 25D input vector
        input_vec = self.agent._last_input or [0.0] * 25

        # 24D hidden layer activations
        hidden_vec = self.agent._last_hidden or [0.0] * 24

        # 8D behavioral signals (after noise)
        sig = {}
        if self._last_signals:
            sig = {s: round(v, 4) for s, v in self._last_signals.items()}

        # 12D context vector (from Critic, after relationship merge)
        ctx = {}
        if self._last_critic:
            ctx = {k: round(v, 4) if isinstance(v, float) else v
                   for k, v in self._last_critic.items()}

        drive_st = {d: round(self.agent.drive_state[d], 4) for d in DRIVES}
        sig_str = ' '.join(f'{k[:3]}={v:.2f}' for k, v in sig.items())
        drv_str = ' '.join(f'{k[:3]}={v:.2f}' for k, v in drive_st.items())
        mono_preview = (self._last_action.get("monologue", "") if self._last_action else "")[:40]
        print(f"  [debug-viz] signals: {sig_str}")
        print(f"  [debug-viz] drives:  {drv_str}")
        print(f"  [debug-viz] mono:    {mono_preview}")

        return {
            "context_vector": ctx,
            "signals": sig,
            "hidden_activations": [round(h, 4) for h in hidden_vec],
            "input_vector": [round(v, 4) for v in input_vec],
            "drive_state": drive_st,
            "drive_baseline": {d: round(self.agent.drive_baseline[d], 4) for d in DRIVES},
            "frustration": round(self.metabolism.total(), 4),
            "temperature": round(self.metabolism.temperature(), 4),
            "monologue": self._last_action.get("monologue", "") if self._last_action else "",
            "style_recall": self.style_memory.last_recall_info(),
            "relationship": {
                k: round(v, 4) if isinstance(v, (int, float)) else v
                for k, v in self._relationship_ema.items()
            },
            "reward": round(self._last_reward, 4),
            "age": self.agent.age,
            "turn_count": self._turn_count,
            "phase_transition": getattr(self.agent, '_last_phase_transition', False),
        }

    # ── Proactive Tick ──
    # See agent/proactive.py (ProactiveMixin)

