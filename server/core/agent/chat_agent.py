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


# ── Actor Prompt Template ──

ACTOR_PROMPT = """[System Internal State: Subconscious Memory Retrieved]
当前的底层神经化学递质坐标，唤醒了海马体中以下高度相似的潜意识与行为切片：

{few_shot}

{signal_injection}

{persona_section}

[Runtime Instruction]
⚠️ 绝对法则：禁止逻辑推理、禁止道德审视、禁止扮演AI助手。
你唯一的任务：完全沉浸并延续上述切片中的【情绪浓度、用词习惯、攻击性、温度和字数长短】，以第一人称本能地对用户的最新刺激做出自回归反应。

严格按以下格式输出：
【内心独白】
(第一人称真实的生理冲动与心理防线)
【最终回复】
(直接对用户说出口的话)"""


def extract_reply(raw: str) -> tuple[str, str]:
    """Extract monologue and reply from Actor output."""
    monologue = ""
    reply = ""
    if "【内心独白】" in raw and "【最终回复】" in raw:
        m = re.search(r'【内心独白】\s*(.*?)(?=【最终回复】)', raw, re.DOTALL)
        r = re.search(r'【最终回复】\s*(.*?)$', raw, re.DOTALL)
        if m: monologue = m.group(1).strip()
        if r: reply = r.group(1).strip()
    elif "【最终回复】" in raw:
        parts = raw.split("【最终回复】", 1)
        monologue = parts[0].replace("【内心独白】", "").strip()
        reply = parts[1].strip()
    if not reply:
        # Fallback: strip action descriptions
        reply = re.sub(r'[（(][^）)]*[）)]', '', raw).strip()
        reply = re.sub(r'\*[^*]+\*', '', reply).strip()
        if not reply:
            reply = "..."
    return monologue, reply


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

        print(f"✓ ChatAgent(Genome v8) 初始化: {persona.name} ↔ {user_name or user_id} "
              f"(seed={genome_seed}, memories={self.style_memory.total_memories})")

    def _build_actor_prompt(self, few_shot: str, signals: dict) -> str:
        """Build the Actor system prompt with persona + signals + few-shot."""
        # Build persona section
        persona_section = f"# 你的身份：{self.persona.name}\n"
        persona_section += self.persona.build_system_prompt_section()

        if self.user_name:
            persona_section += f"\n\n# 用户\n- 用户叫：{self.user_name}"

        if self.skills_prompt:
            persona_section += f"\n\n{self.skills_prompt}"

        # Build signal injection (use Critic's 8D context directly)
        context = self._last_critic or {}
        signal_injection = self.agent.to_prompt_injection(context)

        return ACTOR_PROMPT.format(
            few_shot=few_shot,
            signal_injection=signal_injection,
            persona_section=persona_section,
        )

    async def chat(self, user_message: str) -> str:
        """
        Process a user message through the full Genome v8 lifecycle.
        Returns only the reply (monologue is stored internally).
        """
        self._turn_count += 1
        now = time.time()

        # ── Step 1: Time metabolism ──
        delta_h = self.metabolism.time_metabolism(now)

        # ── Step 2: Critic perception (8D context + delta) ──
        frust_dict = {d: round(self.metabolism.frustration[d], 2) for d in DRIVES}
        context, frustration_delta = await critic_sense(user_message, self.llm, frust_dict)
        self._last_critic = context

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

        # ── Step 9: LLM Actor ──
        messages = [ChatMessage(role="system", content=system_prompt)]
        messages.extend(self.history)
        messages.append(ChatMessage(role="user", content=user_message))

        response = await self.llm.chat(messages)
        monologue, reply = extract_reply(response.content)

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
            'user_input': user_message,
        }

        # Store facts in keyword memory (if available)
        if self.memory_store:
            self.memory_store.add(
                user_id=self.user_id,
                persona_id=self.persona.persona_id,
                content=user_message,
                category="user_message",
                importance=context.get('entropy', 0.5),
            )

        print(f"  [genome] context={context} reward={reward:.2f} temp={total_frust*0.05:.3f}")

        return reply

    async def chat_stream(self, user_message: str) -> AsyncIterator[str]:
        """
        Stream a response through the Genome v10 lifecycle.
        Steps 1-8 run first (Critic, metabolism, KNN), then Actor streams.
        """
        self._turn_count += 1
        now = time.time()

        # ── Steps 1-3: Metabolism + Critic (8D) ──
        delta_h = self.metabolism.time_metabolism(now)
        frust_dict = {d: round(self.metabolism.frustration[d], 2) for d in DRIVES}
        context, frustration_delta = await critic_sense(user_message, self.llm, frust_dict)
        self._last_critic = context
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

        # ── Steps 5-6: Signals + noise ──
        base_signals = self.agent.compute_signals(context)
        total_frust = self.metabolism.total()
        noisy_signals = apply_thermodynamic_noise(base_signals, total_frust)
        self._last_signals = noisy_signals

        # ── Step 7-8: KNN + Actor prompt ──
        self.style_memory.set_clock(now)
        few_shot = self.style_memory.build_few_shot_prompt(noisy_signals, top_k=3)
        system_prompt = self._build_actor_prompt(few_shot, noisy_signals)

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
        monologue, reply = extract_reply(raw_text)

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
            'user_input': user_message,
        }

        print(f"  [genome] critic={critic} reward={reward:.2f} temp={total_frust*0.05:.3f}")

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
        }
