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
            agent.step(ctx, reward)

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

    def __init__(self, seed: int):
        self.seed = seed
        rng = random.Random(seed)

        # ── Genome: drive parameters ──
        self.drive_baseline = {d: rng.uniform(0.2, 0.8) for d in DRIVES}
        self.drive_accumulation_rate = {d: rng.uniform(0.01, 0.05) for d in DRIVES}
        self.drive_decay_rate = {d: rng.uniform(0.05, 0.15) for d in DRIVES}

        # ── Current drive state ──
        self.drive_state = {d: self.drive_baseline[d] for d in DRIVES}

        # ── Genome: random neural network weights ──
        self.W1 = [[rng.gauss(0, 0.6) for _ in range(INPUT_SIZE)] for _ in range(HIDDEN_SIZE)]
        self.b1 = [rng.gauss(0, 0.3) for _ in range(HIDDEN_SIZE)]
        self.W2 = [[rng.gauss(0, 0.5) for _ in range(HIDDEN_SIZE)] for _ in range(N_SIGNALS)]
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

    def learn(self, signals: dict, reward: float, context: dict):
        """
        Hebbian learning: reinforce connections that produced good results.
        Includes frustration accumulation and phase transitions.
        """
        lr = 0.005 * (1 + abs(reward))

        hidden = getattr(self, '_last_hidden',
                         self.recurrent_state + [0.0] * (HIDDEN_SIZE - RECURRENT_SIZE))
        full_input = getattr(self, '_last_input', None)

        # Update output layer weights W2
        for i, sig_name in enumerate(SIGNALS):
            sig_val = signals[sig_name]
            for j in range(HIDDEN_SIZE):
                if abs(hidden[j]) > 0.1:
                    self.W2[i][j] += lr * reward * hidden[j] * (sig_val - 0.5)

        # Update hidden layer weights W1
        if abs(reward) > 0.15:
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
        if self._frustration > 3.0:
            for i in range(N_SIGNALS):
                sig_val = signals[SIGNALS[i]]
                kick = -0.3 * (sig_val - 0.5) + random.gauss(0, 0.15)
                self.b2[i] += kick
            for i in range(HIDDEN_SIZE):
                self.b1[i] += random.gauss(0, 0.1)
            self._frustration = 0.0

        # Drive satisfaction
        if reward > 0.3:
            self.satisfy_drive('connection', reward * 0.15)
            self.satisfy_drive('expression', reward * 0.1)
        if context.get('novelty_level', 0) > 0.5:
            self.satisfy_drive('novelty', 0.1)
        if context.get('conflict_level', 0) < 0.2 and reward > 0:
            self.satisfy_drive('safety', 0.05)

        self.total_reward += reward
        self.interaction_count += 1

    def step(self, context: dict, reward: float = 0.0) -> dict:
        """One full cycle: sense → compute signals → learn → tick drives."""
        signals = self.compute_signals(context)
        self.learn(signals, reward, context)
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

    def to_prompt_injection_from_signals(self, signals: dict) -> str:
        """
        Convert pre-computed behavioral signals into text for LLM system prompt.
        v10: Injects ALL 8 signals (5^8 = 390,625 combinations) instead of top-3.
        """
        dominant_drive = self.get_dominant_drive()

        descriptions = {
            'directness': [
                (0.0, 0.2, '说话绕弯子，用暗示和隐喻，从不直说想法'),
                (0.2, 0.4, '说话比较委婉，倾向于用"可能""也许"这种词'),
                (0.4, 0.6, '说话正常，不特别直也不特别绕'),
                (0.6, 0.8, '说话直接，想到什么说什么，不太修饰'),
                (0.8, 1.0, '说话非常直接甚至冲，不在乎对方能不能接受'),
            ],
            'vulnerability': [
                (0.0, 0.2, '完全封闭自己，绝不暴露任何真实感受'),
                (0.2, 0.4, '很少表达真实感受，被追问也只是轻描淡写'),
                (0.4, 0.6, '偶尔会流露一点真心话，但不会太深入'),
                (0.6, 0.8, '愿意说出自己的感受和脆弱的一面'),
                (0.8, 1.0, '非常坦诚地暴露内心，包括恐惧、不安、依赖感'),
            ],
            'playfulness': [
                (0.0, 0.2, '非常严肃，不开玩笑，语气平淡甚至有点冷'),
                (0.2, 0.4, '偶尔带一点幽默但整体偏正经'),
                (0.4, 0.6, '正常聊天，有时轻松有时认真'),
                (0.6, 0.8, '喜欢开玩笑、逗人，语气轻快活泼'),
                (0.8, 1.0, '各种撒娇卖萌、搞怪、调皮，对话充满笑点'),
            ],
            'initiative': [
                (0.0, 0.2, '完全被动，只回答问题，从不主动说话或换话题'),
                (0.2, 0.4, '基本跟着对方走，偶尔追问一句'),
                (0.4, 0.6, '有来有回，不特别主动也不特别被动'),
                (0.6, 0.8, '经常主动提问、换话题、推动对话往前走'),
                (0.8, 1.0, '强势主导对话，自己抛话题、追问、引导方向'),
            ],
            'depth': [
                (0.0, 0.2, '只聊表面的事，天气、吃饭、日常琐事'),
                (0.2, 0.4, '聊天偏浅，不怎么深入感受层面'),
                (0.4, 0.6, '有时浅聊有时深聊，看情况'),
                (0.6, 0.8, '倾向于深入话题，探讨感受、价值观、关系'),
                (0.8, 1.0, '每句话都想往深了聊，挖掘本质'),
            ],
            'warmth': [
                (0.0, 0.2, '冷淡疏离，语气冷冰冰的，不关心对方感受'),
                (0.2, 0.4, '比较冷淡，不太主动表达关心，回应简短'),
                (0.4, 0.6, '不冷不热，正常回应但不特别热情'),
                (0.6, 0.8, '温暖关心，语气柔和，会主动关心对方状态'),
                (0.8, 1.0, '非常热情体贴，嘘寒问暖，充满关怀和包容'),
            ],
            'defiance': [
                (0.0, 0.2, '非常顺从，对方说什么都同意，从不反驳'),
                (0.2, 0.4, '比较随和，即使不同意也不太会说出来'),
                (0.4, 0.6, '有自己的想法但不会太坚持'),
                (0.6, 0.8, '嘴硬，喜欢反驳，不轻易认错或服软'),
                (0.8, 1.0, '非常倔强，死不认错，越被质疑越硬杠'),
            ],
            'curiosity': [
                (0.0, 0.2, '对对方的事完全不感兴趣，不追问任何细节'),
                (0.2, 0.4, '偶尔问一句但不怎么深入'),
                (0.4, 0.6, '正常程度的好奇，会追问一两句'),
                (0.6, 0.8, '对对方很好奇，喜欢追问细节和原因'),
                (0.8, 1.0, '刨根问底，什么都想知道，追着问不放'),
            ],
        }

        # v10: Inject ALL 8 signals (not just top-3)
        lines = ["【你当前的状态】"]
        for sig_name in SIGNALS:
            val = signals[sig_name]
            for low, high, desc in descriptions[sig_name]:
                if val < high or high == 1.0:
                    lines.append(f"- {desc}")
                    break

        lines.append(f"\n【内在需求】你现在最需要的是{DRIVE_LABELS[dominant_drive]}")

        # Internal contradiction hint
        fp = self.personality_fingerprint(30)
        if fp.get('contradictions'):
            top_c = fp['contradictions'][0]
            lines.append(
                f"【矛盾】你一方面想{SIGNAL_LABELS[top_c[0]].split(' ')[1]}，"
                f"一方面又想{SIGNAL_LABELS[top_c[1]].split(' ')[1]}，这让你纠结"
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
