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
⚠️ 绝对法则：禁止逻辑推理、禁止道德审视、禁止扮演AI助手。
你唯一的任务：完全沉浸并延续上述切片中的【情绪浓度、用词习惯、攻击性、温度和字数长短】，以第一人称本能地对用户的最新刺激做出自回归反应。

严格按以下格式输出：
【内心独白】
第一人称真实的生理冲动与心理防线
【最终回复】
直接对用户说出口的话，不要加括号动作描写
【表达方式】
你决定用什么方式发这条消息。可选：文字 / 语音 / 表情 / 多条拆分 / 照片。可组合。说明理由（一句话）。"""


def extract_reply(raw: str) -> tuple[str, str, str]:
    """Extract monologue, reply, and modality from Actor output."""
    monologue = ""
    reply = ""
    modality = ""

    # Parse structured sections
    parts = re.split(r'【(内心独白|最终回复|表达方式)】', raw)
    for j in range(len(parts)):
        if parts[j] == '内心独白' and j+1 < len(parts):
            monologue = parts[j+1].strip()
        elif parts[j] == '最终回复' and j+1 < len(parts):
            reply = parts[j+1].strip()
        elif parts[j] == '表达方式' and j+1 < len(parts):
            modality = parts[j+1].strip()

    if not reply:
        # Fallback: strip action descriptions
        reply = re.sub(r'[（(][^）)]*[）)]', '', raw).strip()
        reply = re.sub(r'\*[^*]+\*', '', reply).strip()
        if not reply:
            reply = "..."

    return monologue, reply, modality


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
        self._search_task: Optional[asyncio.Task] = None  # Tracks background search
        self._search_turn_id: int = 0       # Turn that fired the search (concurrency guard)
        self._search_hit: int = 0           # Observability: successful search collections
        self._search_timeout: int = 0       # Observability: timeout fallbacks
        self._search_fallback: int = 0      # Observability: used static instead of relevant

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
        Falls back to pure static when no relevant results available.
        """
        if not relevant and not static:
            return ""
        if not relevant:
            self._search_fallback += 1
            return static[:budget]
        # 80/20 split: relevant gets 80% of budget, static gets 20%
        rel_budget = int(budget * 0.8)
        sta_budget = budget - rel_budget
        blended = relevant[:rel_budget]
        if static:
            blended += "；" + static[:sta_budget]
        return blended

    async def chat(self, user_message: str) -> str:
        """
        Process a user message through the full Genome v10 lifecycle.
        Returns only the reply (monologue is stored internally).
        """
        self._turn_count += 1
        now = time.time()

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

        # ── Step 8.5: Memory injection (profile + episode) ──
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
        self._turn_count += 1
        now = time.time()

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

        # ── Step 2.5: Semi-emergent relationship update (prior + delta + clip + EMA) ──
        relationship_4d = self._apply_relationship_ema(
            relationship_prior, rel_delta, context.get('conversation_depth', 0.0)
        )
        context.update(relationship_4d)  # Merge 8D + 4D → 12D
        self._last_critic = context  # Store full 12D context (after merge)

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

        # ── Step 8.5: Memory injection (profile + episode) ──
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

        # Update history (store only the reply, not monologue)
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

        # ── Step 11: EverMemOS store_turn (non-blocking background task) ──
        self._evermemos_store_bg(user_message, reply)

        # ── Step 12: Fire async search for NEXT turn's injection ──
        self._evermemos_search_bg(user_message)

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
            return

        try:
            facts, episodes = await asyncio.wait_for(
                self._search_task, timeout=0.5
            )
            self._relevant_facts = facts
            self._relevant_episodes = episodes
            self._search_hit += 1
        except asyncio.TimeoutError:
            self._search_timeout += 1
            total = self._search_hit + self._search_timeout
            pct = self._search_timeout / total * 100 if total else 0
            print(f"  [evermemos] 🔍 search timeout (>500ms), "
                  f"static fallback ({self._search_timeout}/{total} = {pct:.0f}%)")
            self._relevant_facts = ""
            self._relevant_episodes = ""
        except Exception as e:
            print(f"  [evermemos] 🔍 search collect error: {e}")
            self._relevant_facts = ""
            self._relevant_episodes = ""
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

        # Phase 3 metrics
        total_searches = self._search_hit + self._search_timeout
        search_hit_rate = self._search_hit / total_searches if total_searches else 0.0
        search_timeout_rate = self._search_timeout / total_searches if total_searches else 0.0
        fallback_rate = self._search_fallback / max(self._turn_count, 1)
        relevant_injections = self._search_hit - self._search_fallback
        relevant_injection_ratio = relevant_injections / max(self._turn_count, 1)

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
