"""
ChatAgent — Genome v10 Hybrid lifecycle-powered conversational agent.

The 10-step lifecycle per turn:
  1. Time metabolism (DriveMetabolism)
  2. Critic perception (LLM → 8D context + frustration delta)
  3. LLM metabolism (apply frustration delta → reward)
  4. Crystallization gate (reward > 0.3 → crystallize last action)
  5. Compute signals (Agent neural network, context from Critic)
  6. Thermodynamic noise injection
  7. KNN retrieval (ContinuousStyleMemory)
  8. Build Actor prompt (persona + signals + few-shot)
  9. LLM Actor (generate response with monologue + reply)
  10. Hebbian learning (Agent.step)
"""

from __future__ import annotations

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
from core.memory.evermemos_client import EverMemOSClient
from core.genome.genome_engine import N_CRITIC_CONTEXT


# ── Actor Prompt Template ──

ACTOR_PROMPT = """[System Internal State: Subconscious Memory Retrieved]
当前的底层神经化学递质坐标，唤醒了海马体中以下高度相似的潜意识与行为切片：

{few_shot}

{long_term_memory}

{signal_injection}

[Runtime Instruction]
⚠️ 绝对法则：禁止逻辑推理、禁止道德审视、禁止扮演AI助手。
你唯一的任务：完全沉浸并延续上述切片中的【情绪浓度、用词习惯、攻击性、温度和字数长短】，以第一人称本能地对用户的最新刺激做出自回归反应。
如果「你记得的事情」中有相关信息，自然地融入回复中（不要生硬地复述）。

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
        evermemos: Optional[EverMemOSClient] = None,
        genome_seed: int = 42,
        genome_data_dir: Optional[str] = None,
        max_history: int = 40,
    ):
        self.persona = persona
        self.llm = llm
        self.user_id = user_id
        self.user_name = user_name
        self.skills_prompt = skills_prompt
        self.memory_store = memory_store
        self.evermemos = evermemos
        self.max_history = max_history

        # Stable user ID for EverMemOS (user_name preferred over random session_id)
        self.evermemos_uid = user_name or user_id

        # ── Genome v10 Engine ──
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
        self._user_profile: str = ""  # Cached EverMemOS profile

        evermemos_status = 'ON' if (evermemos and evermemos.available) else 'OFF'
        print(f"✓ ChatAgent(Genome v10+EverMemOS) 初始化: {persona.name} ↔ {user_name or user_id} "
              f"(seed={genome_seed}, memories={self.style_memory.total_memories}, evermemos={evermemos_status})")

    def _build_actor_prompt(self, few_shot: str, signals: dict,
                            long_term_memory: str = "") -> str:
        """Build the Actor system prompt with dual memory.
        - few_shot: ContinuousStyleMemory behavioral anchors (how to talk)
        - long_term_memory: EverMemOS semantic memory (what you know)
        - signal_injection: 8D signal descriptions (current state)
        """
        # Build signal injection (use full 12D context)
        context = self._last_critic or {}
        signal_injection = self.agent.to_prompt_injection(context)

        # Format long-term memory section
        if long_term_memory:
            ltm_section = f"[Long-term Memory: 你记得的事情]\n{long_term_memory}"
        else:
            ltm_section = "[Long-term Memory: 你记得的事情]\n（还没有关于这个用户的长期记忆）"

        return ACTOR_PROMPT.format(
            few_shot=few_shot,
            long_term_memory=ltm_section,
            signal_injection=signal_injection,
        )

    def _evermemos_gather(self, user_message: str) -> tuple:
        """
        Step 0: EverMemOS context gathering.
        Returns: (user_profile, semantic_memory, relationship_4d)
        """
        user_profile = ""
        semantic_memory = ""
        relationship_4d = {
            'relationship_depth': 0.0,
            'emotional_valence': 0.0,
            'trust_level': 0.0,
            'pending_foresight': 0.0,
        }

        if not (self.evermemos and self.evermemos.available):
            return user_profile, semantic_memory, relationship_4d

        try:
            # 0a. Build semantic memory context
            semantic_memory = self.evermemos.build_memory_context(
                user_id=self.evermemos_uid,
                persona_id=self.persona.persona_id,
                current_query=user_message,
            ) or ""

            # 0b. Get user profile text (for Critic)
            profile_results = self.evermemos.get_profile(self.evermemos_uid)
            if profile_results:
                user_profile = "\n".join(r.content for r in profile_results[:3])
                self._user_profile = user_profile

            # 0c. Encode relationship → 4D vector
            relationship_4d = self.evermemos.encode_relationship(
                user_id=self.evermemos_uid,
                current_query=user_message,
            )

            rel_str = " ".join(f"{k}={v:.2f}" for k, v in relationship_4d.items())
            print(f"  [evermemos] {rel_str} | mem={len(semantic_memory)}ch")

        except Exception as e:
            print(f"  [evermemos] gather error: {e}")

        return user_profile, semantic_memory, relationship_4d

    def _evermemos_store(self, user_message: str, reply: str,
                        signals: dict = None) -> None:
        """
        Step 11: Store conversation to EverMemOS with signal metadata.
        """
        if not (self.evermemos and self.evermemos.available):
            return

        try:
            self.evermemos.store_conversation(
                user_id=self.evermemos_uid,
                persona_id=self.persona.persona_id,
                user_name=self.user_name or "用户",
                persona_name=self.persona.name,
                user_message=user_message,
                agent_response=reply,
            )
        except Exception as e:
            print(f"  [evermemos] store error: {e}")

    async def chat(self, user_message: str) -> str:
        """
        Process a user message through the full Genome v10 + EverMemOS lifecycle.
        Returns only the reply (monologue is stored internally).
        """
        self._turn_count += 1
        now = time.time()

        # ── Step 0: EverMemOS context gathering ──
        user_profile, semantic_memory, relationship_4d = self._evermemos_gather(user_message)

        # ── Step 0.5: Foresight → drive injection ──
        if relationship_4d.get('pending_foresight', 0) > 0.5:
            self.metabolism.frustration['connection'] += 0.3
            self.metabolism.frustration['expression'] += 0.2
            print("  [foresight] 🔮 pending foresight → drive injection")

        # ── Step 1: Time metabolism ──
        delta_h = self.metabolism.time_metabolism(now)

        # ── Step 2: Critic perception (8D context + delta) ──
        frust_dict = {d: round(self.metabolism.frustration[d], 2) for d in DRIVES}
        context, frustration_delta = await critic_sense(
            user_message, self.llm, frust_dict,
            user_profile=user_profile,
        )
        self._last_critic = context

        # Merge Critic's 8D with EverMemOS's 4D → 12D context
        context.update(relationship_4d)

        # ── Step 3: LLM metabolism → reward ──
        reward = self.metabolism.apply_llm_delta(frustration_delta)
        self.metabolism.sync_to_agent(self.agent)
        self._last_reward = reward

        # ── Step 4: Crystallization gate (last action) ──
        if self._last_action and reward > 0.3:
            self.style_memory.set_clock(now)
            self.style_memory.crystallize(
                self._last_action['signals'],
                self._last_action['monologue'],
                self._last_action['reply'],
                self._last_action['user_input'],
            )

        # ── Step 5: Compute signals (12D context → neural network) ──
        base_signals = self.agent.compute_signals(context)

        # ── Step 6: Thermodynamic noise ──
        total_frust = self.metabolism.total()
        noisy_signals = apply_thermodynamic_noise(base_signals, total_frust)
        self._last_signals = noisy_signals

        # ── Step 7: KNN retrieval ──
        self.style_memory.set_clock(now)
        few_shot = self.style_memory.build_few_shot_prompt(noisy_signals, top_k=3)

        # ── Step 8: Build Actor prompt (dual memory) ──
        system_prompt = self._build_actor_prompt(few_shot, noisy_signals,
                                                 long_term_memory=semantic_memory)

        # ── Step 9: LLM Actor ──
        messages = [ChatMessage(role="system", content=system_prompt)]
        messages.extend(self.history)
        messages.append(ChatMessage(role="user", content=user_message))

        response = await self.llm.chat(messages)
        monologue, reply, modality = extract_reply(response.content)

        # ── Step 10: Hebbian learning ──
        clamped_reward = max(-1.0, min(1.0, reward))
        self.agent.step(context, reward=clamped_reward)

        # ── Step 11: EverMemOS persistence ──
        self._evermemos_store(user_message, reply, signals=noisy_signals)

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

        return {'reply': reply, 'modality': modality}

    async def chat_stream(self, user_message: str) -> AsyncIterator[str]:
        """
        Stream a response through the Genome v10 + EverMemOS lifecycle.
        Steps 0-8 run first (EverMemOS, Critic, metabolism, KNN), then Actor streams.
        """
        self._turn_count += 1
        now = time.time()

        # ── Step 0: EverMemOS context gathering ──
        user_profile, semantic_memory, relationship_4d = self._evermemos_gather(user_message)

        # ── Step 0.5: Foresight → drive injection ──
        if relationship_4d.get('pending_foresight', 0) > 0.5:
            self.metabolism.frustration['connection'] += 0.3
            self.metabolism.frustration['expression'] += 0.2
            print("  [foresight] 🔮 pending foresight → drive injection")

        # ── Steps 1-3: Metabolism + Critic (12D) ──
        delta_h = self.metabolism.time_metabolism(now)
        frust_dict = {d: round(self.metabolism.frustration[d], 2) for d in DRIVES}
        context, frustration_delta = await critic_sense(
            user_message, self.llm, frust_dict,
            user_profile=user_profile,
        )
        self._last_critic = context
        context.update(relationship_4d)  # Merge 8D + 4D → 12D
        reward = self.metabolism.apply_llm_delta(frustration_delta)
        self.metabolism.sync_to_agent(self.agent)
        self._last_reward = reward

        # ── Step 4: Crystallization ──
        if self._last_action and reward > 0.3:
            self.style_memory.set_clock(now)
            self.style_memory.crystallize(
                self._last_action['signals'],
                self._last_action['monologue'],
                self._last_action['reply'],
                self._last_action['user_input'],
            )

        # ── Steps 5-6: Signals + noise (12D context → neural network) ──
        base_signals = self.agent.compute_signals(context)
        total_frust = self.metabolism.total()
        noisy_signals = apply_thermodynamic_noise(base_signals, total_frust)
        self._last_signals = noisy_signals

        # ── Step 7-8: KNN + Actor prompt (dual memory) ──
        self.style_memory.set_clock(now)
        few_shot = self.style_memory.build_few_shot_prompt(noisy_signals, top_k=3)
        system_prompt = self._build_actor_prompt(few_shot, noisy_signals,
                                                 long_term_memory=semantic_memory)

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

        # Step 11: EverMemOS persistence
        self._evermemos_store(user_message, reply, signals=noisy_signals)

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

        return {
            "persona": self.persona.name,
            "dominant_drive": DRIVE_LABELS.get(dominant_drive, dominant_drive),
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
        }
