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
import uuid
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
from engine.prompt_registry import render_prompt, load_signal_config


# ── Actor Prompt Template (fallback if config/prompts/actor.md missing) ──

_FALLBACK_ACTOR = """[System Internal State: Subconscious Memory Retrieved]
当前的底层神经化学递质坐标，唤醒了海马体中以下高度相似的潜意识与行为切片：

$few_shot

$signal_injection

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
MODALITY_MAP = {
    "静默": "静默", "silence": "静默",
    "文字": "文字", "text": "文字",
    "语音": "语音", "voice": "语音",
    "表情": "表情", "emoji": "表情",
    "多条拆分": "多条拆分", "split": "多条拆分",
    "照片": "照片", "photo": "照片",
}

def _parse_modality(raw: str) -> str:
    """Extract primary modality from Actor output. Supports Chinese and English tokens."""
    cleaned = raw.strip().lstrip("\uff1a: \n").lower()
    for token, canonical in MODALITY_MAP.items():
        if cleaned.startswith(token):
            return canonical
    return "文字"


# -- Section header regex: Chinese 【】 and English [] formats --
_SECTION_RE = re.compile(
    r'(?:【(?P<zh>内心独白|最终回复|表达方式)】'
    r'|\[(?P<en>Inner Monologue|Final Reply|Expression Mode)\])'
)
_TAG_MAP = {
    '内心独白': 'monologue', 'Inner Monologue': 'monologue',
    '最终回复': 'reply',     'Final Reply': 'reply',
    '表达方式': 'modality',  'Expression Mode': 'modality',
}


def extract_reply(raw: str) -> tuple[str, str, str]:
    """Extract monologue, reply, and modality from Actor output.

    Supports both Chinese (【最终回复】) and English ([Final Reply]) section headers.
    Returns canonical Chinese modality key for internal consistency.
    """
    sections: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(raw))
    for i, m in enumerate(matches):
        tag = m.group('zh') or m.group('en')
        key = _TAG_MAP[tag]
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        sections[key] = raw[start:end].strip()

    monologue = sections.get('monologue', '')
    reply = sections.get('reply', '')
    modality_raw = sections.get('modality', '')

    # Parse modality with bilingual map
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
        self._last_image_path: Optional[str] = None
        self._last_audio_path: Optional[str] = None
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
        print(f"✓ ChatAgent(Genome v10+EverMemOS) 初始化: {persona.name} ↔ {user_name or user_id} "
              f"(seed={genome_seed}, memories={self.style_memory.total_memories}, evermemos={evermemos_status})")


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
            fallback=_FALLBACK_ACTOR,
            few_shot=few_shot,
            signal_injection=combined_injection,
        )

    def _build_express_prompt(self, monologue: str, few_shot: str = "") -> str:
        """
        Build Pass 2 (Express) prompt — monologue → reply + modality.

        Identity + monologue + optional reply few-shot from genesis seeds.
        When few_shot is provided, it's prepended so LLM sees how the
        character speaks before seeing the current monologue.
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

        template_name = "actor_express_en" if is_en else "actor_express"
        rendered = render_prompt(
            template_name,
            fallback=(
                "【角色】\n$identity\n\n"
                "【角色此刻的内心】\n$monologue\n\n"
                "[表达指令]\n你是这个角色的唯一作者。\n"
                "角色内心正在经历以上感受。写出角色说出口的话和表达方式。\n\n"
                "按以下格式输出：\n"
                "【最终回复】\n角色实际说出口的话——从内心感受自然流出\n"
                "【表达方式】\n角色选择用什么方式发这条消息。"
                "可选：文字 / 语音 / 表情 / 多条拆分 / 照片 / 静默。可组合。理由一句话。\n"
                '（当角色认为现在不应该说话时，选"静默"。）'
            ),
            identity=identity,
            monologue=monologue,
        )

        # Prepend reply few-shot when available (LLM sees speech examples first)
        if few_shot:
            header = "[Character speech reference]" if is_en else "[角色说话参考]"
            rendered = f"{header}\n{few_shot}\n\n{rendered}"

        # Inject modality skill L1 descriptions (语音/照片 etc)
        if self.modality_skill_engine:
            skill_prompt = self.modality_skill_engine.build_prompt()
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

    async def chat(self, user_message: str, on_feel_done=None) -> dict:
        """
        Process a user message through the full Genome v10 lifecycle.
        Returns only the reply (monologue is stored internally).
        on_feel_done: optional async callback invoked after Feel pass completes.
        """
        async with self._turn_lock:
            return await self._chat_inner(user_message, on_feel_done=on_feel_done)

    async def _chat_inner(self, user_message: str, on_feel_done=None) -> dict:
        """Inner chat implementation (called under lock)."""
        # ── Step -1: Task skill routing (before persona engine) ──
        if self.task_skill_engine:
            skill_defs = self.task_skill_engine.build_skill_declarations()
            if skill_defs:
                routing_resp = None
                try:
                    routing_resp = await self.llm.chat(
                        [ChatMessage(role="user", content=user_message)],
                        tools=skill_defs,
                        tool_choice="auto",
                    )
                except Exception as e:
                    print(f"  [skill] ⚠ Tool routing failed ({e}), fallback to persona engine")
                if routing_resp and routing_resp.tool_calls:
                    tool_name = routing_resp.tool_calls[0]["name"]
                    print(f"  [skill] 🔧 Tool call: {tool_name}")
                    try:
                        result = await self.task_skill_engine.execute(tool_name, user_message, self.llm)
                    except Exception as e:
                        print(f"  [skill] ❌ execute() failed ({e}), falling through to persona engine")
                        result = None
                    if result is not None:
                        stdout = result.output.get("stdout", "").strip()
                        if stdout:
                            user_message = (
                                f"{user_message}\n\n"
                                f"[以下是真实查询数据，回复中必须自然融入关键数值，不要省略]\n"
                                f"{stdout[:800]}"
                            )
                            print(f"  [skill] ✅ 数据已注入 ({len(stdout)} chars), 继续引擎处理")
                    # fall through to persona engine (with or without injected data)

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
            if self.persona.lang == 'en':
                if profile_text:
                    feel_prompt += f"\n\n[{name}'s preferences] {profile_text}"
                if episode_text:
                    feel_prompt += f"\n\n[Past interactions with {name}] {episode_text}"
                if self._foresight_text:
                    feel_prompt += f"\n\n[Worth noting] {self._foresight_text}"
                if self._relevant_profile:
                    feel_prompt += f"\n\n[{name}'s profile] {self._relevant_profile}"
            else:
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

        # ── Step 9a: Pass 1 — Feel (generate monologue only) ──
        # NOTE: No history injection in Feel pass. Conversation context is already
        # encoded in Critic context (conflict, emotion, etc.) and signal values.
        # Raw history would trigger LLM alignment pressure in conflict scenarios.
        feel_messages = [ChatMessage(role="system", content=feel_prompt)]
        feel_messages.append(ChatMessage(role="user", content=user_message))

        feel_response = await self.llm.chat(feel_messages)
        monologue = self._extract_monologue(feel_response.content)

        # Notify caller that Feel is done (typing can start)
        if on_feel_done:
            await on_feel_done()

        # ── Step 9b: Pass 2 — Express (monologue → reply + modality) ──
        turn_lang = self._detect_turn_lang(user_message)
        express_few_shot = self.style_memory.build_few_shot_prompt(
            context, top_k=2, monologue_only=False, lang=turn_lang,
        )
        express_prompt = self._build_express_prompt(monologue, few_shot=express_few_shot)
        express_messages = [ChatMessage(role="system", content=express_prompt)]
        express_messages.extend(self.history[-4:])  # Light context
        express_messages.append(ChatMessage(role="user", content=user_message))

        express_response = await self.llm.chat(express_messages)
        _, reply, modality = extract_reply(express_response.content)

        # ── Step 9c: Modality — let LLM output be the authority ──
        # Skill engine claims modality directly from LLM raw text (primary).
        # _parse_modality result is fallback for base modalities only.
        image_path = None
        self._last_audio_path = None  # reset each turn
        skill_result = None
        _raw_mod = ""
        _matches = list(_SECTION_RE.finditer(express_response.content))
        if _matches:
            _raw_mod = express_response.content[_matches[-1].end():].strip()
            print(f"  [express] raw_modality='{_raw_mod[:80]}'")

        if self.modality_skill_engine and _raw_mod:
            for skill_mod in self.modality_skill_engine.modality_skills:
                if skill_mod in _raw_mod:
                    modality = skill_mod
                    print(f"  [skill] 🎯 modality='{modality}' (claimed from LLM output)")
                    skill_result = await self.modality_skill_engine.execute(
                        modality, express_response.content, self.persona, self.llm
                    )
                    if skill_result and skill_result.success:
                        image_path = skill_result.output.get("image_path")
                        self._last_image_path = image_path
                        self._last_audio_path = skill_result.output.get("audio_path")
                    break

        # ── Step 10: Hebbian learning ──
        clamped_reward = max(-1.0, min(1.0, reward))
        self.agent.step(context, reward=clamped_reward, drive_satisfaction=drive_satisfaction)
        self._last_drive_satisfaction = drive_satisfaction
        # ── Update state ──
        self.history.append(ChatMessage(role="user", content=user_message))
        self.history.append(ChatMessage(role="assistant", content=reply))

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
            for key in ('image_path', 'audio_path'):
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
            # ── Step -1: Task skill routing (before persona engine) ──
            if self.task_skill_engine:
                skill_defs = self.task_skill_engine.build_skill_declarations()
                if skill_defs:
                    routing_resp = None
                    try:
                        routing_resp = await self.llm.chat(
                            [ChatMessage(role="user", content=user_message)],
                            tools=skill_defs,
                            tool_choice="auto",
                        )
                    except Exception as e:
                        print(f"  [skill] ⚠ Tool routing failed ({e}), fallback to persona engine")
                    if routing_resp and routing_resp.tool_calls:
                        tool_name = routing_resp.tool_calls[0]["name"]
                        print(f"  [skill] 🔧 Tool call (stream): {tool_name}")
                        try:
                            result = await self.task_skill_engine.execute(tool_name, user_message, self.llm)
                        except Exception as e:
                            print(f"  [skill] ❌ execute() failed ({e}), falling through to persona engine")
                            result = None
                        if result is not None:
                            stdout = result.output.get("stdout", "").strip()
                            if stdout:
                                user_message = (
                                    f"{user_message}\n\n"
                                    f"[以下是真实查询数据，回复中必须自然融入关键数值，不要省略]\n"
                                    f"{stdout[:800]}"
                                )
                                print(f"  [skill] ✅ 数据已注入 ({len(stdout)} chars), 继续引擎处理")
                        # fall through to persona engine (with or without injected data)

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
            express_prompt = self._build_express_prompt(monologue, few_shot=express_few_shot)
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
            self._last_audio_path = None  # reset each turn
            skill_result = None
            _raw_mod = ""
            _raw_modality_match = list(_SECTION_RE.finditer(raw_text))
            if _raw_modality_match:
                _raw_mod = raw_text[_raw_modality_match[-1].end():].strip()
                print(f"  [express] raw_modality='{_raw_mod[:80]}'")

            if self.modality_skill_engine and _raw_mod:
                for skill_mod in self.modality_skill_engine.modality_skills:
                    if skill_mod in _raw_mod:
                        modality = skill_mod
                        print(f"  [skill] 🎯 modality='{modality}' (claimed from LLM output)")
                        skill_result = await self.modality_skill_engine.execute(
                            modality, raw_text, self.persona, self.llm
                        )
                        if skill_result and skill_result.success:
                            image_path = skill_result.output.get("image_path")
                            self._last_image_path = image_path
                            self._last_audio_path = skill_result.output.get("audio_path")
                        break

            # Step 10: Hebbian learning
            clamped_reward = max(-1.0, min(1.0, reward))
            self.agent.step(context, reward=clamped_reward, drive_satisfaction=drive_satisfaction)
            self._last_drive_satisfaction = drive_satisfaction
            # Update history
            self.history.append(ChatMessage(role="user", content=user_message))
            self.history.append(ChatMessage(role="assistant", content=reply))

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
                group_id=self._group_id,
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
        async def _do_store():
            try:
                await self.evermemos.store_turn(
                    user_id=self.evermemos_uid,
                    persona_id=self.persona.persona_id,
                    persona_name=self.persona.name,
                    user_name=self.user_name or "用户",
                    group_id=self._group_id,
                    user_message=user_message,
                    agent_reply=reply,
                )
                print(f"  [evermemos] ✅ stored turn (uid={self.evermemos_uid}, pid={self.persona.persona_id})")
            except Exception as e:
                print(f"  [evermemos] ❌ store failed: {type(e).__name__}: {e}")
        try:
            asyncio.create_task(_do_store())
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
                    group_id=self._group_id,
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
            "image_path": self._last_image_path,
            "audio_path": self._last_audio_path,
        }

    # ────────────────────────────────────────────
    # Proactive Tick: Drive-driven autonomous messaging
    # ────────────────────────────────────────────

    # Config defaults (can be overridden by memory_config.yaml)
    try:
        import yaml as _yaml
        from pathlib import Path as _Path
        _cfg_path = _Path(__file__).parent.parent / "providers" / "memory" / "memory_config.yaml"
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
        express_prompt = self._build_express_prompt(monologue, few_shot=express_few_shot)
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
