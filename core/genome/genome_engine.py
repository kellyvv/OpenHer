"""
Genome Engine — Agent personality core extracted from genome_v4.py.

Provides:
  - Agent: Random neural network personality entity with drives,
    Hebbian learning, frustration-triggered phase transitions.
  - DRIVES, SIGNALS, CONTEXT_FEATURES: Constants for the 5-drive,
    8-signal, 8-context architecture.
  - SCENARIOS: Predefined conversation context templates.
"""

from __future__ import annotations

import math
import random
import json
from copy import deepcopy
from typing import Optional


# ══════════════════════════════════════════════
# Layer 1: Drive System
# ══════════════════════════════════════════════

DRIVES = ['connection', 'novelty', 'expression', 'safety', 'play']
DRIVE_LABELS = {
    'connection': '🔗 联结',
    'novelty':    '✨ 新鲜',
    'expression': '💬 表达',
    'safety':     '🛡️ 安全',
    'play':       '🎭 玩闹',
}
N_DRIVES = len(DRIVES)


# ══════════════════════════════════════════════
# Layer 2: Behavioral Modulation Signals (8D)
# ══════════════════════════════════════════════

SIGNALS = [
    'directness',     # 0=委婉暗示 → 1=直说
    'vulnerability',  # 0=防御心理 → 1=袒露脆弱
    'playfulness',    # 0=认真严肃 → 1=玩闹撒娇
    'initiative',     # 0=被动回应 → 1=主动引导
    'depth',          # 0=表面闲聊 → 1=深度对话
    'warmth',         # 0=冷淡疏离 → 1=热情关怀
    'defiance',       # 0=顺从 → 1=反抗/嘴硬
    'curiosity',      # 0=无所谓 → 1=追问到底
]
SIGNAL_LABELS = {
    'directness':   '🎯 直接度',
    'vulnerability': '💧 坦露度',
    'playfulness':  '🎪 玩闹度',
    'initiative':   '🚀 主动度',
    'depth':        '🌊 深度',
    'warmth':       '🔥 温暖度',
    'defiance':     '⚡ 倔强度',
    'curiosity':    '🔍 好奇度',
}
N_SIGNALS = len(SIGNALS)


# ══════════════════════════════════════════════
# Context Features (8D input from conversation)
# ══════════════════════════════════════════════

CONTEXT_FEATURES = [
    'user_emotion',       # -1=负面 → 1=正面
    'topic_intimacy',     # 0=公事 → 1=私密
    'time_of_day',        # 0=早晨 → 1=深夜
    'conversation_depth', # 0=刚开始 → 1=聊很久了
    'user_engagement',    # 0=敷衍 → 1=投入
    'conflict_level',     # 0=和谐 → 1=冲突
    'novelty_level',      # 0=日常话题 → 1=全新话题
    'user_vulnerability', # 0=防御 → 1=敞开心扉
    # ── EverMemOS relationship dimensions (新用户“0，老用户渐进增长) ──
    'relationship_depth', # 0=陈生人 → 1=老朋友
    'emotional_valence',  # -1=负面基调 → 1=正面基调
    'trust_level',        # 0=无信任 → 1=高度信任
    'pending_foresight',  # 0=无 → 1=有待处理的前瞅
]
N_CONTEXT = len(CONTEXT_FEATURES)

RECURRENT_SIZE = 8
INPUT_SIZE = N_DRIVES + N_CONTEXT + RECURRENT_SIZE
HIDDEN_SIZE = 24
WEIGHT_DECAY = 0.995  # L2 decay per step — prevents weight explosion / signal saturation


# ══════════════════════════════════════════════
# Fallback Signal & Drive Config (used if config/prompts/signal_buckets.yaml doesn't exist)
# ══════════════════════════════════════════════

_FB_SIG_CN = {
    'directness': '直接感', 'vulnerability': '脆弱感',
    'playfulness': '玩闹感', 'initiative': '主动性',
    'depth': '深度', 'warmth': '温暖度',
    'defiance': '倔强度', 'curiosity': '好奇心',
}

_FB_DESCRIPTIONS = {
    'directness': [
        (0.0, 0.33, '说话委婉含蓄，倾向于暗示和隐喻'),
        (0.33, 0.66, '说话正常，不特别直也不特别绕'),
        (0.66, 1.0, '说话非常直接，想到什么说什么，不在乎修饰'),
    ],
    'vulnerability': [
        (0.0, 0.33, '封闭自己，很少暴露真实感受'),
        (0.33, 0.66, '偶尔流露真心话，但不会太深入'),
        (0.66, 1.0, '坦诚暴露内心，包括恐惧、不安、依赖感'),
    ],
    'playfulness': [
        (0.0, 0.33, '严肃正经，不怎么开玩笑，语气平淡'),
        (0.33, 0.66, '有时轻松有时认真，正常聊天状态'),
        (0.66, 1.0, '各种撒娇卖萌、搞怪调皮，对话充满笑点'),
    ],
    'initiative': [
        (0.0, 0.33, '被动回应，基本跟着对方走'),
        (0.33, 0.66, '有来有回，不特别主动也不特别被动'),
        (0.66, 1.0, '强势主导对话，主动抛话题、追问、引导方向'),
    ],
    'depth': [
        (0.0, 0.33, '聊天偏浅，多是表面话题和日常琐事'),
        (0.33, 0.66, '有时浅聊有时深聊，看情况'),
        (0.66, 1.0, '倾向于深入话题，探讨感受、价值观、关系的本质'),
    ],
    'warmth': [
        (0.0, 0.33, '冷淡疏离，不太主动表达关心'),
        (0.33, 0.66, '不冷不热，正常回应但不特别热情'),
        (0.66, 1.0, '非常温暖体贴，嘘寒问暖，充满关怀'),
    ],
    'defiance': [
        (0.0, 0.33, '比较随和顺从，不怎么反驳'),
        (0.33, 0.66, '有自己的想法但不会太坚持'),
        (0.66, 1.0, '嘴硬倔强，喜欢反驳，越被质疑越硬杠'),
    ],
    'curiosity': [
        (0.0, 0.33, '对对方的事不太感兴趣，不怎么追问'),
        (0.33, 0.66, '正常程度的好奇，会追问一两句'),
        (0.66, 1.0, '刨根问底，什么都想知道，追着问不放'),
    ],
}

_FB_SIGNAL_CONFIG = {
    sig: {'label': _FB_SIG_CN[sig], 'emoji_label': SIGNAL_LABELS[sig], 'buckets': _FB_DESCRIPTIONS[sig]}
    for sig in SIGNALS
}

_FB_DRIVE_CONFIG = {
    d: {'label': DRIVE_LABELS[d].split(' ')[1], 'emoji_label': DRIVE_LABELS[d]}
    for d in DRIVES
}


# ══════════════════════════════════════════════
# Conversation Scenario Templates
# ══════════════════════════════════════════════

SCENARIOS = {
    '深夜心事': {
        'user_emotion': -0.3, 'topic_intimacy': 0.9, 'time_of_day': 0.95,
        'conversation_depth': 0.7, 'user_engagement': 0.8,
        'conflict_level': 0.0, 'novelty_level': 0.2, 'user_vulnerability': 0.9,
    },
    '日常闲聊': {
        'user_emotion': 0.3, 'topic_intimacy': 0.2, 'time_of_day': 0.5,
        'conversation_depth': 0.2, 'user_engagement': 0.5,
        'conflict_level': 0.0, 'novelty_level': 0.3, 'user_vulnerability': 0.2,
    },
    '吵架冲突': {
        'user_emotion': -0.8, 'topic_intimacy': 0.6, 'time_of_day': 0.7,
        'conversation_depth': 0.5, 'user_engagement': 0.9,
        'conflict_level': 0.9, 'novelty_level': 0.1, 'user_vulnerability': 0.1,
    },
    '分享喜悦': {
        'user_emotion': 0.9, 'topic_intimacy': 0.5, 'time_of_day': 0.4,
        'conversation_depth': 0.3, 'user_engagement': 0.9,
        'conflict_level': 0.0, 'novelty_level': 0.6, 'user_vulnerability': 0.3,
    },
}


def simulate_conversation(agent: 'Agent', scenario_sequence: list,
                          reward_fn=None, steps_per_scenario: int = 20) -> None:
    """
    Pre-warm Agent neural network through simulated scenario steps.

    This is the key bootstrap that creates cross-seed personality diversity —
    without it, all agents start from the same neutral state and the LLM's
    default prior dominates. With 60 steps (3 scenarios × 20), the random
    neural network has already been shaped by experience before turn 1.

    Args:
        agent:              The Agent to pre-warm
        scenario_sequence:  List of scenario names from SCENARIOS dict
        reward_fn:          Optional custom reward function (agent, signals, ctx) → float
        steps_per_scenario: Steps per scenario (default 20, total 60 for 3 scenarios)
    """
    for scenario_name in scenario_sequence:
        ctx = SCENARIOS[scenario_name].copy()
        for step in range(steps_per_scenario):
            ctx['conversation_depth'] = min(1.0, ctx['conversation_depth'] + 0.02)
            if reward_fn:
                signals = agent.compute_signals(ctx)
                reward = reward_fn(agent, signals, ctx)
            else:
                reward = random.gauss(0.2, 0.3)  # Slightly positive default
            # Synthetic satisfaction: positive reward → uniform micro-satisfaction
            sat = {d: max(0.0, reward * 0.05) for d in DRIVES} if reward > 0 else None
            agent.step(ctx, reward, drive_satisfaction=sat)

# ══════════════════════════════════════════════
# The Agent: Living Personality
# ══════════════════════════════════════════════

class Agent:
    """
    A personality entity with internal drives, random neural network,
    and evolvable weights via Hebbian learning.

    No hardcoded personality traits — all behavior emerges from
    the random network's computation.
    """

    def __init__(self, seed: int, engine_params: dict = None):
        self.seed = seed
        rng = random.Random(seed)

        # Per-persona engine parameters
        params = engine_params or {}
        self.hebbian_lr = params.get('hebbian_lr', 0.02)
        self.phase_threshold = params.get('phase_threshold', 2.0)

        # ── Genome: drive parameters ──
        self.drive_baseline = {d: rng.uniform(0.2, 0.8) for d in DRIVES}
        self.drive_accumulation_rate = {d: rng.uniform(0.01, 0.05) for d in DRIVES}
        self.drive_decay_rate = {d: rng.uniform(0.05, 0.15) for d in DRIVES}

        # ── Current drive state ──
        self.drive_state = {d: self.drive_baseline[d] for d in DRIVES}

        # ── Genome: random neural network weights ──
        self.W1 = [[rng.gauss(0, 0.6) for _ in range(INPUT_SIZE)] for _ in range(HIDDEN_SIZE)]
        self.b1 = [rng.gauss(0, 0.3) for _ in range(HIDDEN_SIZE)]
        self.W2 = [[rng.gauss(0, 0.2) for _ in range(HIDDEN_SIZE)] for _ in range(N_SIGNALS)]
        self.b2 = [rng.gauss(0, 0.2) for _ in range(N_SIGNALS)]

        # ── Recurrent state (internal "mood") ──
        self.recurrent_state = [rng.gauss(0, 0.1) for _ in range(RECURRENT_SIZE)]

        # ── Tracking ──
        self.interaction_count = 0
        self.total_reward = 0.0
        self.age = 0
        self._frustration = 0.0
        self._last_hidden = None
        self._last_input = None
        self.signal_history = []

    def compute_signals(self, context: dict) -> dict:
        """
        Core computation: context + drives + internal state → 8D behavioral signals.
        No personality logic — just matrix multiplication and activation functions.
        """
        drive_vec = [self.drive_state[d] for d in DRIVES]
        ctx_vec = [context.get(f, 0.0) for f in CONTEXT_FEATURES]
        full_input = drive_vec + ctx_vec + self.recurrent_state

        # Perception noise (biological realism)
        full_input = [v + random.gauss(0, 0.03) for v in full_input]

        # Forward pass: hidden layer
        hidden = []
        for i in range(HIDDEN_SIZE):
            z = self.b1[i]
            for j, x in enumerate(full_input):
                z += self.W1[i][j] * x
            hidden.append(math.tanh(z))

        # Update recurrent state
        self.recurrent_state = hidden[:RECURRENT_SIZE]
        self._last_hidden = list(hidden)
        self._last_input = list(full_input)

        # Output layer: behavioral signals
        raw_signals = []
        for i in range(N_SIGNALS):
            z = self.b2[i]
            for j, h in enumerate(hidden):
                z += self.W2[i][j] * h
            z /= math.sqrt(HIDDEN_SIZE / 3)  # Scaled normalization — prevents sigmoid saturation while preserving signal spread
            raw_signals.append(z)

        # Sigmoid → [0, 1]
        signals = {}
        for i, name in enumerate(SIGNALS):
            signals[name] = 1.0 / (1.0 + math.exp(-max(-10, min(10, raw_signals[i]))))

        # Track for personality_fingerprint
        self.signal_history.append(dict(signals))
        if len(self.signal_history) > 200:
            self.signal_history = self.signal_history[-100:]

        return signals

    def satisfy_drive(self, drive_name: str, amount: float):
        """Satisfy a drive (reduce its current level)."""
        if drive_name in self.drive_state:
            self.drive_state[drive_name] = max(0, self.drive_state[drive_name] - amount)

    def tick_drives(self):
        """Natural drive accumulation per step."""
        for d in DRIVES:
            self.drive_state[d] = min(1.0, self.drive_state[d] + self.drive_accumulation_rate[d])

    def learn(self, signals: dict, reward: float, context: dict,
              drive_satisfaction: dict = None):
        """
        Hebbian learning: reinforce connections that produced good results.
        Includes frustration accumulation, phase transitions, and drive satisfaction.

        drive_satisfaction: If provided (from Critic LLM), uses LLM-judged satisfaction.
                          If None (pre-warming/smoke test), uses rule-based fallback.
        """
        lr = self.hebbian_lr * (1 + abs(reward))

        hidden = getattr(self, '_last_hidden',
                         self.recurrent_state + [0.0] * (HIDDEN_SIZE - RECURRENT_SIZE))
        full_input = getattr(self, '_last_input', None)

        # Update output layer weights W2
        for i, sig_name in enumerate(SIGNALS):
            sig_val = signals[sig_name]
            for j in range(HIDDEN_SIZE):
                if abs(hidden[j]) > 0.05:
                    self.W2[i][j] += lr * reward * hidden[j] * (sig_val - 0.5)

        # Update hidden layer weights W1
        if abs(reward) > 0.05:
            for i in range(HIDDEN_SIZE):
                if abs(hidden[i]) > 0.15:
                    for j in range(INPUT_SIZE):
                        if full_input and abs(full_input[j]) > 0.05:
                            self.W1[i][j] += lr * 0.3 * reward * full_input[j] * hidden[i]

        # Frustration accumulation → phase transition
        if reward < -0.1:
            self._frustration += abs(reward)
        else:
            self._frustration = max(0, self._frustration - reward * 0.5)

        # Phase transition when frustration exceeds threshold
        if self._frustration > self.phase_threshold:
            for i in range(N_SIGNALS):
                sig_val = signals[SIGNALS[i]]
                kick = -0.3 * (sig_val - 0.5) + random.gauss(0, 0.15)
                self.b2[i] += kick
            for i in range(HIDDEN_SIZE):
                self.b1[i] += random.gauss(0, 0.1)
            self._frustration = 0.0

        # Drive satisfaction (LLM-judged — caller must provide)
        if drive_satisfaction:
            for d in DRIVES:
                self.satisfy_drive(d, drive_satisfaction.get(d, 0.0))

        self.total_reward += reward
        self.interaction_count += 1

        # Weight decay + clamp — prevent weight explosion / signal saturation
        for i in range(N_SIGNALS):
            for j in range(HIDDEN_SIZE):
                self.W2[i][j] *= WEIGHT_DECAY
                self.W2[i][j] = max(-1.5, min(1.5, self.W2[i][j]))
        for i in range(HIDDEN_SIZE):
            for j in range(INPUT_SIZE):
                self.W1[i][j] *= WEIGHT_DECAY
                self.W1[i][j] = max(-2.0, min(2.0, self.W1[i][j]))

    def step(self, context: dict, reward: float = 0.0,
             drive_satisfaction: dict = None) -> dict:
        """One full cycle: sense → compute signals → learn → tick drives."""
        signals = self.compute_signals(context)
        self.learn(signals, reward, context, drive_satisfaction=drive_satisfaction)
        self.tick_drives()
        self.age += 1
        return signals

    def get_dominant_drive(self) -> str:
        """Return the most urgent drive."""
        return max(self.drive_state, key=self.drive_state.get)

    def personality_fingerprint(self, window_size: int = 30) -> dict:
        """
        Analyzes recent signal history to identify stable traits and contradictions.
        """
        if not self.signal_history:
            return {'traits': {}, 'contradictions': []}

        recent_signals = self.signal_history[-window_size:]
        num_signals = len(recent_signals)

        if num_signals == 0:
            return {'traits': {}, 'contradictions': []}

        # Calculate average signal values
        avg_signals = {sig_name: 0.0 for sig_name in SIGNALS}
        for signals_t in recent_signals:
            for sig_name, value in signals_t.items():
                avg_signals[sig_name] += value
        for sig_name in SIGNALS:
            avg_signals[sig_name] /= num_signals

        # Identify stable traits (signals consistently high or low)
        traits = {}
        for sig_name in SIGNALS:
            if avg_signals[sig_name] > 0.7:
                traits[sig_name] = 'high'
            elif avg_signals[sig_name] < 0.3:
                traits[sig_name] = 'low'
            else:
                traits[sig_name] = 'neutral'

        # Identify contradictions (signals that frequently swing from high to low)
        contradictions = []
        for i in range(N_SIGNALS):
            for j in range(i + 1, N_SIGNALS):
                sig1_name = SIGNALS[i]
                sig2_name = SIGNALS[j]

                high_low_count = 0
                low_high_count = 0

                for k in range(num_signals - 1):
                    s_t = recent_signals[k]
                    s_t1 = recent_signals[k+1]

                    # Check for high-to-low swing for sig1 while sig2 is low-to-high
                    if (s_t[sig1_name] > 0.7 and s_t1[sig1_name] < 0.3 and
                        s_t[sig2_name] < 0.3 and s_t1[sig2_name] > 0.7):
                        high_low_count += 1
                    # Check for low-to-high swing for sig1 while sig2 is high-to-low
                    elif (s_t[sig1_name] < 0.3 and s_t1[sig1_name] > 0.7 and
                          s_t[sig2_name] > 0.7 and s_t1[sig2_name] < 0.3):
                        low_high_count += 1

                # If both swings happen frequently, it's a contradiction
                if high_low_count > num_signals * 0.1 and low_high_count > num_signals * 0.1:
                    contradictions.append((sig1_name, sig2_name))

        return {
            'traits': traits,
            'avg_signals': avg_signals,
            'contradictions': contradictions,
        }

    def to_prompt_injection(self, context: dict) -> str:
        """Legacy compat: compute signals from context, then format.
        Prefer to_prompt_injection_from_signals() when signals are pre-computed.
        """
        signals = self.compute_signals(context)
        return self.to_prompt_injection_from_signals(signals)

    def to_prompt_injection_from_signals(self, signals: dict, signal_overrides: dict = None) -> str:
        """
        Convert pre-computed behavioral signals into text for LLM system prompt.
        v11: 3-bucket descriptions + numeric value tags + multi-drive tension + signal trends.

        Signal descriptions, labels, and drive labels are loaded from
        config/prompts/signal_buckets.yaml (falls back to module-level hardcoded defaults).
        """
        from core.prompt_registry import load_signal_config

        # ── Load from YAML (or use module-level fallbacks) ──
        config = load_signal_config(
            fallback_signals=_FB_SIGNAL_CONFIG,
            fallback_drives=_FB_DRIVE_CONFIG,
        )
        sig_config = config.get('signals', _FB_SIGNAL_CONFIG)
        drv_config = config.get('drives', _FB_DRIVE_CONFIG)

        # Per-persona signal description overrides (deep copy to avoid polluting cache)
        if signal_overrides:
            import copy
            sig_config = copy.deepcopy(sig_config)
            for sig_name, override in signal_overrides.items():
                if sig_name in sig_config:
                    if 'buckets' in override:
                        sig_config[sig_name]['buckets'] = [
                            (b['low'], b['high'], b['desc']) for b in override['buckets']
                        ]
                    if 'label' in override:
                        sig_config[sig_name]['label'] = override['label']
                    if 'emoji_label' in override:
                        sig_config[sig_name]['emoji_label'] = override['emoji_label']

        # ── Build signal state lines with numeric tags ──
        lines = ["【你当前的状态】"]
        for sig_name in SIGNALS:
            val = signals[sig_name]
            info = sig_config.get(sig_name, {})
            fb_info = _FB_SIGNAL_CONFIG.get(sig_name, {})
            sig_label = info.get('label', fb_info.get('label', sig_name))
            buckets = info.get('buckets', fb_info.get('buckets', []))
            for low, high, desc in buckets:
                if val < high or high == 1.0:
                    lines.append(f"- {desc} [{sig_label}: {val:.2f}]")
                    break

        # ── Multi-drive tension injection (top-2 drives) ──
        sorted_drives = sorted(self.drive_state.items(), key=lambda x: x[1], reverse=True)
        d1_name, d1_val = sorted_drives[0]
        d2_name, d2_val = sorted_drives[1]

        d1_label = drv_config.get(d1_name, {}).get('emoji_label', DRIVE_LABELS.get(d1_name, d1_name))
        d2_label = drv_config.get(d2_name, {}).get('emoji_label', DRIVE_LABELS.get(d2_name, d2_name))

        lines.append(f"\n【内在需求】")
        lines.append(f"主驱力：{d1_label} ({d1_val:.2f})")
        if d2_val > d1_val * 0.7:  # Only inject tension when secondary drive is strong enough
            lines.append(f"次驱力：{d2_label} ({d2_val:.2f})")
            lines.append(f"内心张力：{d1_name} 和 {d2_name} 之间的拉扯影响着你的表达方式")

        # ── Internal contradiction hint ──
        fp = self.personality_fingerprint(30)
        if fp.get('contradictions'):
            top_c = fp['contradictions'][0]
            # Use emoji_label from config, split to get action word
            c0_label = sig_config.get(top_c[0], {}).get('emoji_label', SIGNAL_LABELS.get(top_c[0], top_c[0]))
            c1_label = sig_config.get(top_c[1], {}).get('emoji_label', SIGNAL_LABELS.get(top_c[1], top_c[1]))
            lines.append(
                f"【矛盾】你一方面想{c0_label.split(' ')[1]}，"
                f"一方面又想{c1_label.split(' ')[1]}，这让你纠结"
            )

        return '\n'.join(lines)

    # ── Serialization ──

    def to_dict(self) -> dict:
        """Serialize agent state for persistence."""
        return {
            'seed': self.seed,
            'drive_state': dict(self.drive_state),
            'drive_baseline': dict(self.drive_baseline),
            'W1': self.W1,
            'b1': self.b1,
            'W2': self.W2,
            'b2': self.b2,
            'recurrent_state': self.recurrent_state,
            'interaction_count': self.interaction_count,
            'total_reward': self.total_reward,
            'age': self.age,
            '_frustration': self._frustration,
            'signal_history': self.signal_history[-100:],  # Persist last 100 for personality_fingerprint
        }

    @classmethod
    def from_dict(cls, data: dict) -> Agent:
        """Restore agent from serialized state.

        Handles backward compatibility: old agents have 21D input (8D context)
        while new agents have 25D input (12D context with EverMemOS dims).
        """
        agent = cls(seed=data['seed'])
        agent.drive_state = data.get('drive_state', agent.drive_state)
        agent.drive_baseline = data.get('drive_baseline', agent.drive_baseline)  # P1: restore evolved baseline

        saved_W1 = data.get('W1', agent.W1)
        # Backward compat: expand 21D → 25D if loading old weights
        if saved_W1 and len(saved_W1[0]) < INPUT_SIZE:
            rng = random.Random(data['seed'] + 9999)  # deterministic expansion
            extra_cols = INPUT_SIZE - len(saved_W1[0])
            for row in saved_W1:
                row.extend([rng.gauss(0, 0.3) for _ in range(extra_cols)])
        agent.W1 = saved_W1

        agent.b1 = data.get('b1', agent.b1)
        agent.W2 = data.get('W2', agent.W2)
        agent.b2 = data.get('b2', agent.b2)
        agent.recurrent_state = data.get('recurrent_state', agent.recurrent_state)
        agent.interaction_count = data.get('interaction_count', 0)
        agent.total_reward = data.get('total_reward', 0.0)
        agent.signal_history = data.get('signal_history', [])
        agent.age = data.get('age', 0)
        agent._frustration = data.get('_frustration', 0.0)
        return agent
