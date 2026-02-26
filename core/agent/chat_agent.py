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
  3.5 Critic-driven Drive baseline evolution (BASELINE_LR=0.003, every turn)
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
import uuid
import re
import time
from typing import AsyncIterator, Optional

from core.llm.client import LLMClient, ChatMessage, ChatResponse
from core.persona.persona_loader import Persona
from core.genome.genome_engine import Agent, DRIVES, SIGNALS, DRIVE_LABELS
from core.genome.drive_metabolism import DriveMetabolism, apply_thermodynamic_noise
from core.genome.critic import critic_sense
from core.genome.style_memory import ContinuousStyleMemory
from core.memory.memory_store import MemoryStore


# ── Actor Prompt Template ──

ACTOR_PROMPT = """[System Internal State: Subconscious Memory Retrieved]
当前的底层神经化学递质坐标，唤醒了海马体中以下高度相似的潜意识与行为切片：

{few_shot}

{signal_injection}

[Runtime Instruction]
你在此时此刻是这个人格的主体，不是AI助手。
以上述切片呈现的整体人格质感（情绪密度、用词、攻击性、温度、主动性、脆弱感、玩笑感、深度、热度等一切可感知的维度）为参照底色，以第一人称本能地对用户的最新刺激做出回应。



严格按以下格式输出：
【内心独白】
第一人称真实的生理冲动与心理防线
【最终回复】
直接对用户说出口的话
【表达方式】
你决定用什么方式发这条消息。可选：文字 / 语音 / 表情 / 多条拆分 / 照片 / 静默。可组合。说明理由（一句话）。
（当你认为现在不应该说话时，选“静默”。）"""

# -- Modality Parsing --
MODALITY_ENUM = ("静默", "文字", "语音", "表情", "多条拆分", "照片")

def _parse_modality(raw: str) -> str:
    """Extract primary modality from Actor output. Ordered enum, first-token match."""
    cleaned = raw.strip().lstrip("\uff1a: \n")
    candidate = cleaned[:4]
    for m in MODALITY_ENUM:
        if candidate.startswith(m):
            return m
    return "文字"


def extract_reply(raw: str) -> tuple[str, str, str]:
    """Extract monologue, reply, and modality from Actor output."""
    monologue = ""
    reply = ""
    modality_raw = ""

    # Parse structured sections
    parts = re.split(r'【(内心独白|最终回复|表达方式)】', raw)
    for j in range(len(parts)):
        if parts[j] == '内心独白' and j+1 < len(parts):
            monologue = parts[j+1].strip()
        elif parts[j] == '最终回复' and j+1 < len(parts):
            reply = parts[j+1].strip()
        elif parts[j] == '表达方式' and j+1 < len(parts):
            modality_raw = parts[j+1].strip()

    # Parse modality with strict enum (R11/R22)
    modality = _parse_modality(modality_raw) if modality_raw else "文字"

    # Silence short-circuit: Actor chose not to speak
    if modality == "静默":
        return monologue, "", "静默"

    if not reply:
        # Fallback: strip action descriptions
        reply = re.sub(r'[(（(][^)）)]*[)）)]', '', raw).strip()
        reply = re.sub(r'\*[^*]+\*', '', reply).strip()
        if not reply:
            reply = "..."

    return monologue, reply, modality_raw or modality


class ChatAgent:
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
        skills_prompt: Optional[str] = None,
        memory_store: Optional[MemoryStore] = None,
        genome_seed: int = 42,
        genome_data_dir: Optional[str] = None,
        max_history: int = 40,
        evermemos=None,
    ):
        self.persona = persona
        self.llm = llm
        self.user_id = user_id
        self.user_name = user_name
        self.skills_prompt = skills_prompt
        self.memory_store = memory_store
        self.max_history = max_history

        # ── Genome v8 Engine ──
        self.agent = Agent(seed=genome_seed)
        self.metabolism = DriveMetabolism()

        # Apply persona-specific genome seed (initial conditions only)
        if persona.drive_baseline:
            for d, v in persona.drive_baseline.items():
                if d in self.agent.drive_baseline:
                    self.agent.drive_baseline[d] = float(v)
                    self.agent.drive_state[d] = float(v)

        self.style_memory = ContinuousStyleMemory(
            agent_id=f"{persona.persona_id}_{user_id}",
            db_dir=genome_data_dir,
        )

        # ── Conversation state ──
        self.history: list[ChatMessage] = []
        self._turn_count: int = 0
        self._last_action: Optional[dict] = None
        self._last_critic: Optional[dict] = None
        self._last_signals: Optional[dict] = None
        self._last_reward: float = 0.0
        self._last_modality: str = ""

        # ── Concurrency lock (R2: serialize chat/stream/proactive_tick) ──
        self._turn_lock = asyncio.Lock()

        # ── Proactive tick state ──
        self._last_active: float = time.time()
        self._state_version: int = 0
        self._interaction_cadence: float = 0.0  # EMA of interaction interval (seconds)

        # ── EverMemOS Async Memory ──
        self.evermemos = evermemos
        self.evermemos_uid = f"{user_id}__{persona.persona_id}"
        self._group_id = f"{persona.persona_id}__{user_id}"  # group_id for EverMemOS
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
        print(f"✓ ChatAgent(Genome v10+EverMemOS) 初始化: {persona.name} ↔ {user_name or user_id} "
              f"(seed={genome_seed}, memories={self.style_memory.total_memories}, evermemos={evermemos_status})")

    def _build_actor_prompt(self, few_shot: str, signals: dict) -> str:
        """Build the Actor system prompt — matches prototype tpe_v10_hybrid.py.
        Signal injection drives behavior; persona is minimal (name only).
        """
        # Use pre-computed signals (same as KNN retrieval) — no re-computation
        signal_injection = self.agent.to_prompt_injection_from_signals(signals)

        return ACTOR_PROMPT.format(
            few_shot=few_shot,
            signal_injection=signal_injection,
        )

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

        should = crystal_score > 0.35
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

    async def chat(self, user_message: str) -> str:
        """
        Process a user message through the full Genome v10 lifecycle.
        Returns only the reply (monologue is stored internally).
        """
        async with self._turn_lock:
            return await self._chat_inner(user_message)

    async def _chat_inner(self, user_message: str) -> str:
        """Inner chat implementation (called under lock)."""
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
        context, frustration_delta, rel_delta = await critic_sense(
            user_message, self.llm, frust_dict,
            user_profile=self._user_profile,
            episode_summary=self._episode_summary,
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
        # frustration_delta > 0 = drive not satisfied this turn → baseline rises (hungers more)
        # frustration_delta < 0 = drive satisfied this turn → baseline eases
        # BASELINE_LR is a numerical stability param (like Hebbian lr), not a semantic rule.
        BASELINE_LR = 0.003
        for d in DRIVES:
            shift = frustration_delta.get(d, 0.0) * BASELINE_LR
            self.agent.drive_baseline[d] = max(0.1, min(0.95,
                self.agent.drive_baseline[d] + shift
            ))

        # ── Step 4: Crystallization gate (last action) ──
        if self._last_action and self._should_crystallize(reward, context):
            self.style_memory.set_clock(now)
            self.style_memory.crystallize(
                self._last_action['signals'],
                self._last_action['monologue'],
                self._last_action['reply'],
                self._last_action['user_input'],
            )

        # ── Step 5: Compute signals (context from Critic directly) ──
        base_signals = self.agent.compute_signals(context)

        # ── Step 6: Thermodynamic noise ──
        total_frust = self.metabolism.total()
        noisy_signals = apply_thermodynamic_noise(base_signals, total_frust)
        self._last_signals = noisy_signals

        # ── Step 7: KNN retrieval ──
        self.style_memory.set_clock(now)
        few_shot = self.style_memory.build_few_shot_prompt(noisy_signals, top_k=3)

        # ── Step 8: Build Actor prompt ──
        system_prompt = self._build_actor_prompt(few_shot, noisy_signals)

        # ── Step 8.5: Memory injection (profile + episode + foresight) ──
        if self._session_ctx and self._session_ctx.has_history:
            # Collect search results right before injection (not at turn start)
            await self._collect_search_results()
            profile_budget, episode_budget = self._memory_injection_budget(context)
            # Phase 3: blend relevant (80%) + static (20%) for stability
            profile_text = self._blend_injection(
                self._relevant_facts, self._user_profile, profile_budget
            )
            episode_text = self._blend_injection(
                self._relevant_episodes, self._episode_summary, episode_budget
            )
            name = self.user_name or self.user_id
            if profile_text:
                system_prompt += f"\n\n[关于{name}的偏好] {profile_text}"
            if episode_text:
                system_prompt += f"\n\n[与{name}过去发生的事] {episode_text}"
            # P1: Inject foresight prediction text
            if self._foresight_text:
                system_prompt += f"\n\n[近期值得关心] {self._foresight_text}"
            # P1: Inject profile from search
            if self._relevant_profile:
                system_prompt += f"\n\n[{name}的画像] {self._relevant_profile}"
            # Track if this turn used relevant content
            if self._relevant_facts or self._relevant_episodes or self._relevant_profile:
                self._search_relevant_used += 1

        # ── Step 9: LLM Actor ──
        messages = [ChatMessage(role="system", content=system_prompt)]
        messages.extend(self.history)
        messages.append(ChatMessage(role="user", content=user_message))

        response = await self.llm.chat(messages)
        monologue, reply, modality = extract_reply(response.content)

        # ── Step 10: Hebbian learning ──
        clamped_reward = max(-1.0, min(1.0, reward))
        self.agent.step(context, reward=clamped_reward)

        # ── Update state ──
        self.history.append(ChatMessage(role="user", content=user_message))
        self.history.append(ChatMessage(role="assistant", content=reply))

        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        self._last_action = {
            'signals': noisy_signals,
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

        print(f"  [genome] reward={reward:.2f} temp={total_frust*0.05:.3f} modality={modality[:30]}")

        # ── Step 11: EverMemOS store_turn (non-blocking background task) ──
        self._evermemos_store_bg(user_message, reply)

        # ── Step 12: Fire async search for NEXT turn's injection ──
        self._evermemos_search_bg(user_message)

        return {'reply': reply, 'modality': modality}

    async def chat_stream(self, user_message: str) -> AsyncIterator[str]:
        """
        Stream a response through the Genome v10 lifecycle.
        Steps 1-8 run first (Critic, metabolism, KNN), then Actor streams.
        """
        await self._turn_lock.acquire()
        try:
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
            context, frustration_delta, rel_delta = await critic_sense(
                user_message, self.llm, frust_dict,
                user_profile=self._user_profile,
                episode_summary=self._episode_summary,
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
            BASELINE_LR = 0.003
            for d in DRIVES:
                shift = frustration_delta.get(d, 0.0) * BASELINE_LR
                self.agent.drive_baseline[d] = max(0.1, min(0.95,
                    self.agent.drive_baseline[d] + shift
                ))

            # ── Step 4: Crystallization ──
            if self._last_action and self._should_crystallize(reward, context):
                self.style_memory.set_clock(now)
                self.style_memory.crystallize(
                    self._last_action['signals'],
                    self._last_action['monologue'],
                    self._last_action['reply'],
                    self._last_action['user_input'],
                )

            # ── Steps 5-6: Signals + noise ──
            base_signals = self.agent.compute_signals(context)
            total_frust = self.metabolism.total()
            noisy_signals = apply_thermodynamic_noise(base_signals, total_frust)
            self._last_signals = noisy_signals

            # ── Step 7-8: KNN + Actor prompt ──
            self.style_memory.set_clock(now)
            few_shot = self.style_memory.build_few_shot_prompt(noisy_signals, top_k=3)
            system_prompt = self._build_actor_prompt(few_shot, noisy_signals)

            # ── Step 8.5: Memory injection ──
            if self._session_ctx and self._session_ctx.has_history:
                await self._collect_search_results()
                profile_budget, episode_budget = self._memory_injection_budget(context)
                profile_text = self._blend_injection(
                    self._relevant_facts, self._user_profile, profile_budget
                )
                episode_text = self._blend_injection(
                    self._relevant_episodes, self._episode_summary, episode_budget
                )
                name = self.user_name or self.user_id
                if profile_text:
                    system_prompt += f"\n\n[关于{name}的偏好] {profile_text}"
                if episode_text:
                    system_prompt += f"\n\n[与{name}过去发生的事] {episode_text}"
                if self._foresight_text:
                    system_prompt += f"\n\n[近期值得关心] {self._foresight_text}"
                if self._relevant_profile:
                    system_prompt += f"\n\n[{name}的画像] {self._relevant_profile}"
                if self._relevant_facts or self._relevant_episodes or self._relevant_profile:
                    self._search_relevant_used += 1

            # ── Step 9: Stream Actor ──
            messages = [ChatMessage(role="system", content=system_prompt)]
            messages.extend(self.history)
            messages.append(ChatMessage(role="user", content=user_message))

            full_response = []
            async for chunk in self.llm.chat_stream(messages):
                full_response.append(chunk)
                yield chunk

            # ── Post-stream processing ──
            raw_text = "".join(full_response)
            monologue, reply, modality = extract_reply(raw_text)

            # Step 10: Hebbian learning
            clamped_reward = max(-1.0, min(1.0, reward))
            self.agent.step(context, reward=clamped_reward)

            # Update history
            self.history.append(ChatMessage(role="user", content=user_message))
            self.history.append(ChatMessage(role="assistant", content=reply))

            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]

            self._last_action = {
                'signals': noisy_signals,
                'monologue': monologue,
                'reply': reply,
                'modality': modality,
                'user_input': user_message,
            }
            self._last_modality = modality

            print(f"  [genome] reward={reward:.2f} temp={total_frust*0.05:.3f} modality={modality[:30]}")

            # ── Step 11: EverMemOS store_turn ──
            self._evermemos_store_bg(user_message, reply)

            # ── Step 12: Fire async search for NEXT turn ──
            self._evermemos_search_bg(user_message)
        finally:
            self._turn_lock.release()

    async def _evermemos_gather(self) -> dict:
        """
        Step 0: Load EverMemOS session context (first turn only).
        Subsequent turns reuse cached _session_ctx.
        Returns relationship_4d dict for GenomeEngine context.
        """
        empty_4d = {
            'relationship_depth': 0.0,
            'emotional_valence': 0.0,
            'trust_level': 0.0,
            'pending_foresight': 0.0,
        }

        if not (self.evermemos and self.evermemos.available):
            return empty_4d

        # Load once per session
        if self._turn_count == 1:
            self._session_ctx = await self.evermemos.load_session_context(
                user_id=self.evermemos_uid,
                persona_id=self.persona.persona_id,
            )
            if self._session_ctx.user_profile:
                self._user_profile = self._session_ctx.user_profile
            if self._session_ctx.episode_summary:
                self._episode_summary = self._session_ctx.episode_summary
            # P1: Cache foresight text for Actor injection
            if self._session_ctx.foresight_text:
                self._foresight_text = self._session_ctx.foresight_text

        if not self._session_ctx:
            return empty_4d

        return self.evermemos.relationship_vector(self._session_ctx)

    def _apply_relationship_ema(
        self,
        prior: dict,
        rel_delta: dict,
        conversation_depth: float,
    ) -> dict:
        """
        Step 2.5: Semi-emergent relationship update.

        Pattern: posterior = clip(prior + LLM_delta) → EMA smooth
          alpha = clip(0.15 + 0.5 * depth, 0.15, 0.65)
          state_t = alpha * posterior + (1 - alpha) * state_{t-1}

        First turn initializes EMA state from prior, then applies delta normally.
        """
        # Map Critic output keys → context feature keys
        delta_map = {
            'relationship_depth': rel_delta.get('relationship_delta', 0.0),
            'emotional_valence': rel_delta.get('emotional_valence', 0.0),
            'trust_level': rel_delta.get('trust_delta', 0.0),
            'pending_foresight': 0.0,  # No delta for foresight (data-driven only)
        }

        # Initialize EMA on first turn
        if not self._relationship_ema:
            self._relationship_ema = dict(prior)

        # Compute posterior = clip(prior + delta)
        posterior = {}
        for k in prior:
            lo = -1.0 if k == 'emotional_valence' else 0.0
            posterior[k] = max(lo, min(1.0, prior[k] + delta_map.get(k, 0.0)))

        # Depth-modulated alpha: shallow → trust prior, deep → trust LLM
        alpha = max(0.15, min(0.65, 0.15 + 0.5 * conversation_depth))

        # EMA smooth
        ema = {}
        for k in prior:
            prev = self._relationship_ema.get(k, prior[k])
            ema[k] = round(alpha * posterior[k] + (1 - alpha) * prev, 4)
        self._relationship_ema = ema

        # Observability log
        print(
            f"  [emergence] α={alpha:.2f} | "
            f"depth: prior={prior['relationship_depth']:.2f} "
            f"δ={delta_map['relationship_depth']:+.2f} → ema={ema['relationship_depth']:.3f} | "
            f"trust: prior={prior['trust_level']:.2f} "
            f"δ={delta_map['trust_level']:+.2f} → ema={ema['trust_level']:.3f} | "
            f"valence: δ={delta_map['emotional_valence']:+.2f} → ema={ema['emotional_valence']:.3f} | "
            f"foresight={ema['pending_foresight']:.2f}"
        )

        return ema

    def _evermemos_store_bg(self, user_message: str, reply: str) -> None:
        """Step 11: Fire-and-forget EverMemOS storage (asyncio.create_task)."""
        if not (self.evermemos and self.evermemos.available):
            return
        try:
            asyncio.create_task(
                self.evermemos.store_turn(
                    user_id=self.evermemos_uid,
                    persona_id=self.persona.persona_id,
                    persona_name=self.persona.name,
                    user_name=self.user_name or self.user_id,
                    group_id=self._group_id,
                    user_message=user_message,
                    agent_reply=reply,
                )
            )
        except Exception as e:
            print(f"  [evermemos] create_task error: {e}")

    def _evermemos_search_bg(self, user_message: str) -> None:
        """
        Step 12: Fire async RRF search for the current user_message.
        Results are collected at Step 8.5 of the NEXT turn.
        Cancels any pending search before starting a new one.
        """
        if not (self.evermemos and self.evermemos.available):
            return
        if not self._session_ctx or not self._session_ctx.has_history:
            return

        # Cancel any orphaned previous search task
        if self._search_task and not self._search_task.done():
            self._search_task.cancel()
            self._search_task = None

        try:
            self._search_turn_id = self._turn_count  # Tag with origin turn
            self._search_task = asyncio.create_task(
                self.evermemos.search_relevant_memories(
                    query=user_message,
                    user_id=self.evermemos_uid,
                )
            )
        except Exception as e:
            print(f"  [evermemos] search create_task error: {e}")
            self._search_task = None

    async def _collect_search_results(self) -> None:
        """
        Collect previous turn's async search results (called at Step 8.5).
        Validates turn_id to prevent concurrent mismatch.
        Waits up to 0.5s; on timeout/error falls back to empty (static used).
        """
        if self._search_task is None:
            return

        # Concurrency guard: reject stale results from wrong turn
        expected_turn = self._turn_count - 1
        if self._search_turn_id != expected_turn:
            self._search_task.cancel()
            self._search_task = None
            self._relevant_facts = ""
            self._relevant_episodes = ""
            self._relevant_profile = ""   # P1a fix: was missing, caused stale profile injection
            return


        try:
            facts, episodes, profile = await asyncio.wait_for(
                self._search_task, timeout=0.5
            )
            self._relevant_facts = facts
            self._relevant_episodes = episodes
            self._relevant_profile = profile   # P1
            self._search_hit += 1
        except asyncio.TimeoutError:
            self._search_timeout += 1
            total = self._search_hit + self._search_timeout
            pct = self._search_timeout / total * 100 if total else 0
            print(f"  [evermemos] 🔍 search timeout (>500ms), "
                  f"static fallback ({self._search_timeout}/{total} = {pct:.0f}%)")
            self._relevant_facts = ""
            self._relevant_episodes = ""
            self._relevant_profile = ""
        except Exception as e:
            print(f"  [evermemos] 🔍 search collect error: {e}")
            self._relevant_facts = ""
            self._relevant_episodes = ""
            self._relevant_profile = ""
        finally:
            self._search_task = None

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
            "evermemos": "ON" if (self.evermemos and self.evermemos.available) else "OFF",
            "search_hit": self._search_hit,
            "search_timeout": self._search_timeout,
            "search_fallback": self._search_fallback,
            "search_hit_rate": round(search_hit_rate, 3),
            "search_timeout_rate": round(search_timeout_rate, 3),
            "fallback_rate": round(fallback_rate, 3),
            "relevant_injection_ratio": round(relevant_injection_ratio, 3),
        }

    # ────────────────────────────────────────────
    # Proactive Tick: Drive-driven autonomous messaging
    # ────────────────────────────────────────────

    # Config defaults (can be overridden by memory_config.yaml)
    try:
        import yaml as _yaml
        from pathlib import Path as _Path
        _cfg_path = _Path(__file__).parent.parent.parent / "config" / "memory_config.yaml"
        _cfg_data = _yaml.safe_load(_cfg_path.read_text()).get("evermemos", {}) if _cfg_path.exists() else {}
    except Exception:
        _cfg_data = {}
    _IMPULSE_THRESHOLD = _cfg_data.get("impulse_threshold", 0.8)

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
            score = (norm_frust - baseline) / max(baseline, 0.05)
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
                )
                if episodes:
                    flashback_parts.append(f"[记忆闪回] {episodes}")
                if facts:
                    flashback_parts.append(f"[闪回细节] {facts}")
            except Exception as e:
                print(f"  [proactive] flashback search failed: {e}")

        # ── Step 4: Build stimulus (data formatting, not decision logic) ──
        name = self.user_name or self.user_id
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
        context, frustration_delta, rel_delta = await critic_sense(
            stimulus, self.llm, frust_dict,
            user_profile=self._user_profile,
            episode_summary=self._episode_summary,
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
        noisy_signals = apply_thermodynamic_noise(base_signals, total_frust)

        # ── Step 9: Build Actor prompt ──
        self.style_memory.set_clock(start)
        few_shot = self.style_memory.build_few_shot_prompt(noisy_signals, top_k=3)
        system_prompt = self._build_actor_prompt(few_shot, noisy_signals)

        # ── Step 9.5: Memory injection (foresight is key driver here) ──
        if self._session_ctx and self._session_ctx.has_history:
            if self._user_profile:
                system_prompt += f"\n\n[关于{name}的偏好] {self._user_profile[:300]}"
            if self._episode_summary:
                system_prompt += f"\n\n[与{name}过去发生的事] {self._episode_summary[:300]}"
            if self._foresight_text:
                system_prompt += f"\n\n[近期值得关心] {self._foresight_text}"

        # ── Step 10: LLM Actor (no history, no fake user_message) ──
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=stimulus),
        ]
        response = await self.llm.chat(messages)
        monologue, reply, modality = extract_reply(response.content)

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
