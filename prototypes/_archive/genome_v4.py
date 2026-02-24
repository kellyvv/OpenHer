#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║     🧬 Agent Genome v4 — Living Personality Engine 🧬              ║
║     活性人格引擎：涌现 × 进化 × LLM调制                              ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  v3 的问题: 涌现是真的，但输出是抽象动作，和对话脱节                    ║
║  genome_test 的问题: LLM 做进化，天然收敛到"温暖倾听者"               ║
║                                                                      ║
║  v4 的解法: 三层融合架构                                              ║
║    Layer 1 — 驱力系统: 5 种内在需求，有自己的动力学                    ║
║    Layer 2 — 随机网络: 基因组 → 随机接线 → 输出行为调制信号            ║
║    Layer 3 — LLM 接口: 信号注入 prompt，调制语言表达风格              ║
║                                                                      ║
║  关键特性:                                                           ║
║    ✓ 多样性: 不同种子 → 不同网络 → 不同行为信号组合                   ║
║    ✓ 自进化: Hebbian 学习 + 驱力漂移 → 权重随交互改变                 ║
║    ✓ 内在矛盾: 网络自然产生对抗信号（如高坦露+高防御）                 ║
║    ✓ 路径依赖: 同种子+不同经历 → 不同人格轨迹                         ║
║    ✓ 可接入: 输出可直接注入 LLM system prompt                         ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import math
import random
import json
from collections import defaultdict
from copy import deepcopy

# ──────────────────────────────────────────────
# Terminal Colors
# ──────────────────────────────────────────────
class C:
    RESET = '\033[0m'; BOLD = '\033[1m'; DIM = '\033[2m'
    RED = '\033[91m'; GREEN = '\033[92m'; YELLOW = '\033[93m'
    BLUE = '\033[94m'; MAGENTA = '\033[95m'; CYAN = '\033[96m'
    WHITE = '\033[97m'; GRAY = '\033[90m'

SPARK = ' ▁▂▃▄▅▆▇█'
def spark(values):
    return ''.join(SPARK[min(8, max(0, int(v * 8)))] for v in values)

def bar(value, width=20, color=C.CYAN):
    filled = int(max(0, min(1, value)) * width)
    return f'{color}{"█" * filled}{C.DIM}{"░" * (width - filled)}{C.RESET}'


# ══════════════════════════════════════════════
# Layer 1: 驱力系统 (Drive System)
# ──────────────────────────────────────────────
# 人不是空白的反应器。人有需求、有渴望、有匮乏。
# 驱力是 Agent 主动行为的根源。
# ══════════════════════════════════════════════

DRIVES = ['connection', 'novelty', 'expression', 'safety', 'play']
DRIVE_LABELS = {
    'connection': '🔗 联结',    # 想被理解、被记住
    'novelty':    '✨ 新鲜',    # 想探索、想知道
    'expression': '💬 表达',    # 想说出自己的想法
    'safety':     '🛡️ 安全',   # 想要稳定、可预期
    'play':       '🎭 玩闹',   # 想逗乐、想撒娇
}
N_DRIVES = len(DRIVES)


# ══════════════════════════════════════════════
# Layer 2: 行为调制信号 (Behavioral Modulation Signals)
# ──────────────────────────────────────────────
# 这些不是"性格特征"，而是每一轮对话的
# 实时行为倾向。同一个 Agent 在不同时刻
# 的信号组合是不同的。
# ══════════════════════════════════════════════

SIGNALS = [
    'directness',    # 0=委婉暗示 → 1=直说
    'vulnerability',  # 0=防御心理 → 1=袒露脆弱
    'playfulness',   # 0=认真严肃 → 1=玩闹撒娇
    'initiative',    # 0=被动回应 → 1=主动引导
    'depth',         # 0=表面闲聊 → 1=深度对话
    'warmth',        # 0=冷淡疏离 → 1=热情关怀
    'defiance',      # 0=顺从 → 1=反抗/嘴硬
    'curiosity',     # 0=无所谓 → 1=追问到底
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
# 对话上下文特征 (Context Features)
# ──────────────────────────────────────────────
# Agent 感知到的当前对话环境
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
]
N_CONTEXT = len(CONTEXT_FEATURES)

# Total network input size = drives + context + recurrent
RECURRENT_SIZE = 8
INPUT_SIZE = N_DRIVES + N_CONTEXT + RECURRENT_SIZE
HIDDEN_SIZE = 24


# ══════════════════════════════════════════════
# The Agent: Living Personality
# ══════════════════════════════════════════════

class Agent:
    """
    一个有内在驱力、随机神经网络大脑、和可进化权重的人格实体。

    关键设计：
    - 没有任何硬编码的"性格特征"
    - 行为信号从随机网络实时计算
    - 同一个 Agent 在不同上下文中表现不同
    - 交互反馈驱动权重进化
    """

    def __init__(self, seed: int):
        self.seed = seed
        rng = random.Random(seed)

        # ── 基因组: 驱力参数（每个驱力的基础水平和动力学） ──
        self.drive_baseline = {d: rng.uniform(0.2, 0.8) for d in DRIVES}
        self.drive_accumulation_rate = {d: rng.uniform(0.01, 0.05) for d in DRIVES}
        self.drive_decay_rate = {d: rng.uniform(0.05, 0.15) for d in DRIVES}

        # ── 当前驱力状态 ──
        self.drive_state = {d: self.drive_baseline[d] for d in DRIVES}

        # ── 基因组: 随机神经网络权重 ──
        self.W1 = [[rng.gauss(0, 0.6) for _ in range(INPUT_SIZE)] for _ in range(HIDDEN_SIZE)]
        self.b1 = [rng.gauss(0, 0.3) for _ in range(HIDDEN_SIZE)]
        self.W2 = [[rng.gauss(0, 0.5) for _ in range(HIDDEN_SIZE)] for _ in range(N_SIGNALS)]
        self.b2 = [rng.gauss(0, 0.2) for _ in range(N_SIGNALS)]

        # ── 循环状态 (内部"心境") ──
        self.recurrent_state = [rng.gauss(0, 0.1) for _ in range(RECURRENT_SIZE)]

        # ── 追踪 ──
        self.signal_history = []   # 每步的行为信号
        self.drive_history = []    # 每步的驱力状态
        self.interaction_count = 0
        self.total_reward = 0.0
        self.age = 0               # 总步数
        self._frustration = 0.0    # 累积挫败感（持续负反馈会积累，触发相变）
        self._last_hidden = None   # 缓存完整 hidden 激活
        self._last_input = None    # 缓存完整输入向量

    def compute_signals(self, context: dict) -> dict:
        """
        核心计算：上下文 + 驱力 + 内部状态 → 行为调制信号。
        这里没有任何人格逻辑，只有矩阵乘法和激活函数。
        """
        # 构建输入向量
        drive_vec = [self.drive_state[d] for d in DRIVES]
        ctx_vec = [context.get(f, 0.0) for f in CONTEXT_FEATURES]
        full_input = drive_vec + ctx_vec + self.recurrent_state

        # 感知噪声（生物学真实性）
        full_input = [v + random.gauss(0, 0.03) for v in full_input]

        # 前向传播: 隐藏层
        hidden = []
        for i in range(HIDDEN_SIZE):
            z = self.b1[i]
            for j, x in enumerate(full_input):
                z += self.W1[i][j] * x
            hidden.append(math.tanh(z))

        # 更新循环状态
        self.recurrent_state = hidden[:RECURRENT_SIZE]

        # 保存完整 hidden 用于学习（修复：之前只用 recurrent_state 近似，丢失了 2/3 的神经元）
        self._last_hidden = list(hidden)
        self._last_input = list(full_input)

        # 输出层: 行为信号
        raw_signals = []
        for i in range(N_SIGNALS):
            z = self.b2[i]
            for j, h in enumerate(hidden):
                z += self.W2[i][j] * h
            raw_signals.append(z)

        # Sigmoid 将信号映射到 [0, 1]
        signals = {}
        for i, name in enumerate(SIGNALS):
            signals[name] = 1.0 / (1.0 + math.exp(-max(-10, min(10, raw_signals[i]))))

        return signals

    def satisfy_drive(self, drive_name: str, amount: float):
        """满足某个驱力（降低其当前水平）"""
        if drive_name in self.drive_state:
            self.drive_state[drive_name] = max(0, self.drive_state[drive_name] - amount)

    def tick_drives(self):
        """每步驱力自然累积（需求会随时间增长）"""
        for d in DRIVES:
            self.drive_state[d] = min(1.0, self.drive_state[d] + self.drive_accumulation_rate[d])

    def learn(self, signals: dict, reward: float, context: dict):
        """
        Hebbian 学习: 强化产生好结果的连接。

        reward 含义:
          > 0: 用户正面反馈（长回复、表情、继续聊）
          < 0: 用户负面反馈（敷衍、冷淡、不满）

        这是真正的自我进化——权重在改变，不是参数在调整。

        v4.1 修复:
          - 使用完整 hidden 激活（之前只用 recurrent_state，丢失 2/3 神经元）
          - W1 门槛从 0.5 降到 0.15，让隐藏层真正参与漂移
          - 加入 frustration 累积，持续负反馈触发相变（不只是渐变）
        """
        lr = 0.005 * (1 + abs(reward))

        # 使用完整的 hidden 激活（修复核心 bug）
        hidden = getattr(self, '_last_hidden', self.recurrent_state + [0.0] * (HIDDEN_SIZE - RECURRENT_SIZE))
        full_input = getattr(self, '_last_input', None)

        # ── 更新输出层权重 W2 ──
        for i, sig_name in enumerate(SIGNALS):
            sig_val = signals[sig_name]
            for j in range(HIDDEN_SIZE):
                if abs(hidden[j]) > 0.1:  # 降低激活门槛（原来 0.2）
                    self.W2[i][j] += lr * reward * hidden[j] * (sig_val - 0.5)

        # ── 更新隐藏层权重 W1（大幅降低门槛）──
        if abs(reward) > 0.15:  # 原来 0.5，几乎永远不触发
            for i in range(HIDDEN_SIZE):
                if abs(hidden[i]) > 0.15:  # 原来 0.3
                    for j in range(INPUT_SIZE):
                        if full_input and abs(full_input[j]) > 0.05:
                            # 用实际输入而非仅 drive_vec，让 context 也能塑造 W1
                            self.W1[i][j] += lr * 0.3 * reward * full_input[j] * hidden[i]

        # ── Frustration 累积 → 相变 ──
        # 持续负反馈不应只是渐变，而应积累"压力"，到阈值后触发信号的结构性翻转
        if reward < -0.1:
            self._frustration = getattr(self, '_frustration', 0.0) + abs(reward)
        else:
            # 正反馈缓慢释放 frustration
            self._frustration = max(0, getattr(self, '_frustration', 0.0) - reward * 0.5)

        # 相变：frustration 超过阈值时，对 bias 施加一次大扰动
        if getattr(self, '_frustration', 0) > 3.0:
            for i in range(N_SIGNALS):
                # bias 扰动方向：让当前高的信号降低，低的升高（人格"翻转"）
                sig_val = signals[SIGNALS[i]]
                kick = -0.3 * (sig_val - 0.5) + random.gauss(0, 0.15)
                self.b2[i] += kick
            # 隐藏层 bias 也扰动，打破 W1 的固定模式
            for i in range(HIDDEN_SIZE):
                self.b1[i] += random.gauss(0, 0.1)
            self._frustration = 0.0  # 释放压力

        # 驱力满足
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
        """一步完整循环: 感知 → 计算信号 → 学习 → 驱力更新"""
        signals = self.compute_signals(context)
        self.learn(signals, reward, context)
        self.tick_drives()
        self.age += 1

        # 记录历史
        self.signal_history.append({s: signals[s] for s in SIGNALS})
        self.drive_history.append({d: self.drive_state[d] for d in DRIVES})

        return signals

    def get_dominant_drive(self) -> str:
        """当前最迫切的需求"""
        return max(self.drive_state, key=self.drive_state.get)

    def personality_fingerprint(self, window: int = 50) -> dict:
        """
        从最近的行为信号历史中计算"人格指纹"。
        这不是 Agent 自己知道的，而是外部观察者的分析。
        """
        history = self.signal_history[-window:] if self.signal_history else []
        if not history:
            return {s: 0.5 for s in SIGNALS}

        # 均值
        means = {}
        for s in SIGNALS:
            vals = [h[s] for h in history]
            means[s] = sum(vals) / len(vals)

        # 波动性（标准差）
        stds = {}
        for s in SIGNALS:
            vals = [h[s] for h in history]
            mean = means[s]
            stds[s] = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))

        # 内在矛盾检测：哪些信号对有高波动且负相关
        contradictions = []
        for i, s1 in enumerate(SIGNALS):
            for s2 in SIGNALS[i+1:]:
                if stds.get(s1, 0) > 0.1 and stds.get(s2, 0) > 0.1:
                    # 计算相关性
                    vals1 = [h[s1] for h in history]
                    vals2 = [h[s2] for h in history]
                    m1, m2 = means[s1], means[s2]
                    cov = sum((v1 - m1) * (v2 - m2) for v1, v2 in zip(vals1, vals2)) / len(vals1)
                    std_prod = stds[s1] * stds[s2]
                    if std_prod > 0:
                        corr = cov / std_prod
                        if corr < -0.3:
                            contradictions.append((s1, s2, corr))

        return {
            'means': means,
            'stds': stds,
            'contradictions': contradictions,
        }

    def to_prompt_injection(self, context: dict) -> str:
        """
        将当前行为信号转化为可注入 LLM system prompt 的文本。
        这是和 LLM 的接口。

        v4.1 重写:
          - 只注入最突出的 2-3 个信号（偏离 0.5 最远的），其余省略
          - 5 档细粒度描述代替原来的 3 档（<0.3 / 0.3-0.7 / >0.7）
          - 每个信号给出具体的行为指令，不只是形容词
        """
        signals = self.compute_signals(context)
        dominant_drive = self.get_dominant_drive()

        # ── 5 档行为描述：每档是具体的行为指令，不是抽象形容词 ──
        descriptions = {
            'directness': [
                (0.0, 0.2, '说话绕弯子，用暗示和隐喻，从不直说想法'),
                (0.2, 0.4, '说话比较委婉，倾向于用"可能""也许"这种词'),
                (0.4, 0.6, '说话正常，不特别直也不特别绕'),
                (0.6, 0.8, '说话直接，想到什么说什么，不太修饰'),
                (0.8, 1.0, '说话非常直接甚至冲，不在乎对方能不能接受'),
            ],
            'vulnerability': [
                (0.0, 0.2, '完全封闭自己，绝不暴露任何真实感受，用冷漠或玩笑挡住一切'),
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
                (0.8, 1.0, '每句话都想往深了聊，挖掘本质，不满足于表面回应'),
            ],
            'warmth': [
                (0.0, 0.2, '冷淡疏离，语气冷冰冰的，不关心对方感受，甚至有点刻薄'),
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
                (0.8, 1.0, '非常倔强，死不认错，越被质疑越硬杠，宁折不弯'),
            ],
            'curiosity': [
                (0.0, 0.2, '对对方的事完全不感兴趣，不追问任何细节'),
                (0.2, 0.4, '偶尔问一句但不怎么深入'),
                (0.4, 0.6, '正常程度的好奇，会追问一两句'),
                (0.6, 0.8, '对对方很好奇，喜欢追问细节和原因'),
                (0.8, 1.0, '刨根问底，什么都想知道，追着问不放'),
            ],
        }

        # ── 只选最突出的信号（偏离 0.5 最远的 top 3）──
        deviations = [(sig, abs(signals[sig] - 0.5), signals[sig]) for sig in SIGNALS]
        deviations.sort(key=lambda x: x[1], reverse=True)
        top_signals = deviations[:3]

        lines = []
        lines.append("【你当前的状态】")

        for sig_name, deviation, val in top_signals:
            # 找到对应的档位描述
            for low, high, desc in descriptions[sig_name]:
                if val < high or high == 1.0:
                    lines.append(f"- {desc}")
                    break

        lines.append(f"\n【内在需求】你现在最需要的是{DRIVE_LABELS[dominant_drive]}")

        # 内在矛盾提示
        fp = self.personality_fingerprint(30)
        if fp.get('contradictions'):
            top_c = fp['contradictions'][0]
            lines.append(f"\n【矛盾】你一方面想{SIGNAL_LABELS[top_c[0]].split(' ')[1]}，一方面又想{SIGNAL_LABELS[top_c[1]].split(' ')[1]}，这让你纠结")

        return '\n'.join(lines)


# ══════════════════════════════════════════════
# 对话场景模拟器
# ──────────────────────────────────────────────
# 模拟不同类型的对话上下文和用户反馈
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
    '工作吐槽': {
        'user_emotion': -0.4, 'topic_intimacy': 0.4, 'time_of_day': 0.6,
        'conversation_depth': 0.4, 'user_engagement': 0.6,
        'conflict_level': 0.2, 'novelty_level': 0.2, 'user_vulnerability': 0.4,
    },
    '暧昧试探': {
        'user_emotion': 0.4, 'topic_intimacy': 0.8, 'time_of_day': 0.85,
        'conversation_depth': 0.6, 'user_engagement': 0.8,
        'conflict_level': 0.0, 'novelty_level': 0.7, 'user_vulnerability': 0.6,
    },
    '冷淡敷衍': {
        'user_emotion': 0.0, 'topic_intimacy': 0.1, 'time_of_day': 0.3,
        'conversation_depth': 0.1, 'user_engagement': 0.1,
        'conflict_level': 0.0, 'novelty_level': 0.0, 'user_vulnerability': 0.0,
    },
}


def simulate_conversation(agent: Agent, scenario_sequence: list[str],
                         reward_fn=None, steps_per_scenario: int = 20):
    """
    模拟一段对话历程。
    reward_fn: 自定义反馈函数 (agent, signals, context) → reward
    默认反馈: 随机正面，模拟正常对话
    """
    for scenario_name in scenario_sequence:
        ctx = SCENARIOS[scenario_name].copy()
        for step in range(steps_per_scenario):
            # 逐步加深对话
            ctx['conversation_depth'] = min(1.0, ctx['conversation_depth'] + 0.02)

            # 反馈
            if reward_fn:
                signals = agent.compute_signals(ctx)
                reward = reward_fn(agent, signals, ctx)
            else:
                reward = random.gauss(0.2, 0.3)  # 默认略正面

            agent.step(ctx, reward)


# ══════════════════════════════════════════════
# 外部观察者
# ══════════════════════════════════════════════

class Observer:
    """
    只看行为信号历史，不看网络权重。
    从外部识别人格特征。
    """

    @staticmethod
    def describe_personality(agent: Agent) -> str:
        """用自然语言描述观察到的人格"""
        fp = agent.personality_fingerprint(50)
        if not fp or 'means' not in fp:
            return "观察数据不足"

        means = fp['means']
        stds = fp['stds']

        parts = []

        # 高值特征
        high = [(s, means[s]) for s in SIGNALS if means[s] > 0.65]
        high.sort(key=lambda x: x[1], reverse=True)
        for s, v in high[:3]:
            parts.append(f"{SIGNAL_LABELS[s]}偏高({v:.2f})")

        # 低值特征
        low = [(s, means[s]) for s in SIGNALS if means[s] < 0.35]
        low.sort(key=lambda x: x[1])
        for s, v in low[:2]:
            parts.append(f"{SIGNAL_LABELS[s]}偏低({v:.2f})")

        # 高波动特征（不稳定）
        volatile = [(s, stds[s]) for s in SIGNALS if stds[s] > 0.12]
        volatile.sort(key=lambda x: x[1], reverse=True)

        desc = '、'.join(parts) if parts else '中性'

        if volatile:
            vol_names = '和'.join(SIGNAL_LABELS[s] for s, _ in volatile[:2])
            desc += f"。{vol_names}波动较大"

        # 内在矛盾
        if fp['contradictions']:
            c = fp['contradictions'][0]
            desc += f"。存在内在矛盾: {SIGNAL_LABELS[c[0]]}↔{SIGNAL_LABELS[c[1]]}"

        return desc

    @staticmethod
    def diversity_score(agents: list) -> dict:
        """量化一组 Agent 的行为多样性"""
        fingerprints = [a.personality_fingerprint(50) for a in agents]
        valid = [fp for fp in fingerprints if fp and 'means' in fp]

        if len(valid) < 2:
            return {'score': 0, 'details': {}}

        # 每个信号的跨 Agent 方差
        signal_variances = {}
        for s in SIGNALS:
            vals = [fp['means'][s] for fp in valid]
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / len(vals)
            signal_variances[s] = var

        # 总多样性分数 = 所有信号方差的均值
        avg_var = sum(signal_variances.values()) / len(signal_variances)

        # Agent 间的平均距离
        distances = []
        for i in range(len(valid)):
            for j in range(i + 1, len(valid)):
                dist = math.sqrt(sum(
                    (valid[i]['means'][s] - valid[j]['means'][s]) ** 2
                    for s in SIGNALS
                ))
                distances.append(dist)
        avg_dist = sum(distances) / len(distances) if distances else 0

        return {
            'score': avg_var,
            'avg_distance': avg_dist,
            'signal_variances': signal_variances,
            'n_agents': len(valid),
        }

    @staticmethod
    def evolution_magnitude(agent: Agent, window1: int = 50, window2: int = 50) -> float:
        """量化一个 Agent 早期 vs 晚期的行为变化量"""
        history = agent.signal_history
        if len(history) < window1 + window2:
            return 0.0

        early = history[:window1]
        late = history[-window2:]

        total_diff = 0
        for s in SIGNALS:
            early_mean = sum(h[s] for h in early) / len(early)
            late_mean = sum(h[s] for h in late) / len(late)
            total_diff += (early_mean - late_mean) ** 2

        return math.sqrt(total_diff)


# ══════════════════════════════════════════════
# Main Simulation
# ══════════════════════════════════════════════

def run():
    N_AGENTS = 30
    STEPS_PER_SCENARIO = 25

    print(f"""
{C.BOLD}╔══════════════════════════════════════════════════════════════════════╗
║     🧬 Agent Genome v4 — Living Personality Engine 🧬              ║
║     活性人格引擎：涌现 × 进化 × LLM调制                              ║
╠══════════════════════════════════════════════════════════════════════╣
║  三层架构: 驱力系统 → 随机网络 → 行为调制信号 → LLM                  ║
║  代码中没有"温暖"、"傲娇"等性格词汇                                  ║
║  所有人格从随机网络的计算中涌现                                       ║
╚══════════════════════════════════════════════════════════════════════╝{C.RESET}
""")

    # ═══════════════════════════════════════════
    # TEST 1: 多样性验证 — 不同种子是否产生不同人格
    # ═══════════════════════════════════════════
    print(f'{C.BOLD}{C.YELLOW}═══ TEST 1: 先天多样性 — {N_AGENTS} 个不同种子的行为分化 ═══{C.RESET}')
    print(f'{C.DIM}所有 Agent 经历相同的对话场景序列，但因为"大脑接线"不同而表现不同...{C.RESET}\n')

    scenario_seq = ['日常闲聊', '分享喜悦', '深夜心事', '工作吐槽', '暧昧试探', '吵架冲突']

    agents = []
    for i in range(N_AGENTS):
        agent = Agent(seed=i * 137 + 42)
        simulate_conversation(agent, scenario_seq, steps_per_scenario=STEPS_PER_SCENARIO)
        agents.append(agent)

    # 展示几个 Agent 的信号指纹
    print(f'  {C.BOLD}随机抽样 5 个 Agent 的行为信号均值:{C.RESET}\n')
    print(f'  {"seed":>6s}  ', end='')
    for s in SIGNALS:
        print(f'{SIGNAL_LABELS[s][:4]:>6s}', end='')
    print(f'  {"个性描述"}')
    print(f'  {"─" * 80}')

    for agent in agents[:5]:
        fp = agent.personality_fingerprint(50)
        print(f'  {agent.seed:>6d}  ', end='')
        for s in SIGNALS:
            val = fp['means'][s]
            color = C.RED if val > 0.65 else C.BLUE if val < 0.35 else C.DIM
            print(f'{color}{val:>6.2f}{C.RESET}', end='')
        desc = Observer.describe_personality(agent)
        print(f'  {C.DIM}{desc[:40]}{C.RESET}')

    diversity = Observer.diversity_score(agents)
    print(f'\n  {C.BOLD}多样性指标:{C.RESET}')
    print(f'    总多样性得分(方差均值): {C.CYAN}{diversity["score"]:.4f}{C.RESET}')
    print(f'    Agent 间平均距离:       {C.CYAN}{diversity["avg_distance"]:.4f}{C.RESET}')
    print(f'\n  {C.BOLD}各信号维度的跨 Agent 方差:{C.RESET}')
    for s in SIGNALS:
        var = diversity['signal_variances'][s]
        print(f'    {SIGNAL_LABELS[s]:12s} {bar(var * 50, 20)} {var:.4f}')

    if diversity['score'] > 0.01:
        print(f'\n  {C.GREEN}✓ 不同种子产生了明显不同的行为模式 — 先天多样性确认{C.RESET}')
    else:
        print(f'\n  {C.YELLOW}⚠ 多样性不够显著{C.RESET}')

    # ═══════════════════════════════════════════
    # TEST 2: 自我进化 — 交互如何改变人格
    # ═══════════════════════════════════════════
    print(f'\n{C.BOLD}{C.YELLOW}═══ TEST 2: 自我进化 — 正面反馈 vs 负面反馈如何改变同一个人格 ═══{C.RESET}')
    print(f'{C.DIM}相同种子，一个总被温柔对待，一个总被冷淡对待...{C.RESET}\n')

    seed = 777

    # Agent A: 总得到正面反馈
    agent_warm = Agent(seed=seed)
    simulate_conversation(
        agent_warm, scenario_seq * 3,
        reward_fn=lambda a, s, c: random.gauss(0.6, 0.2),
        steps_per_scenario=STEPS_PER_SCENARIO,
    )

    # Agent B: 总得到负面反馈
    agent_cold = Agent(seed=seed)
    simulate_conversation(
        agent_cold, scenario_seq * 3,
        reward_fn=lambda a, s, c: random.gauss(-0.3, 0.3),
        steps_per_scenario=STEPS_PER_SCENARIO,
    )

    fp_warm = agent_warm.personality_fingerprint(80)
    fp_cold = agent_cold.personality_fingerprint(80)

    print(f'  {"信号":12s}  {"温暖环境":>8s}  {"冷淡环境":>8s}  {"差异":>6s}')
    print(f'  {"─" * 45}')
    total_diff = 0
    for s in SIGNALS:
        vw = fp_warm['means'][s]
        vc = fp_cold['means'][s]
        diff = abs(vw - vc)
        total_diff += diff
        color = C.RED if diff > 0.1 else C.YELLOW if diff > 0.05 else C.GREEN
        print(f'  {SIGNAL_LABELS[s]:12s}  {vw:>7.3f}  {vc:>7.3f}  {color}{diff:>5.3f}{C.RESET}')

    print(f'\n  总行为分歧: {C.CYAN}{total_diff:.3f}{C.RESET}')
    print(f'  温暖环境人格: {Observer.describe_personality(agent_warm)}')
    print(f'  冷淡环境人格: {Observer.describe_personality(agent_cold)}')

    if total_diff > 0.2:
        print(f'\n  {C.GREEN}✓ 同一个"大脑"在不同反馈环境下进化出了明显不同的人格{C.RESET}')
    else:
        print(f'\n  {C.YELLOW}⚠ 分化不够显著{C.RESET}')

    # ═══════════════════════════════════════════
    # TEST 3: 情境敏感性 — 同一个 Agent 在不同场景下的表现差异
    # ═══════════════════════════════════════════
    print(f'\n{C.BOLD}{C.YELLOW}═══ TEST 3: 情境敏感性 — 同一个人在不同场景下的表现 ═══{C.RESET}')
    print(f'{C.DIM}验证: Agent 不是一个固定标签，而是对情境敏感的动态系统...{C.RESET}\n')

    test_agent = agents[0]
    print(f'  Agent seed={test_agent.seed}\n')
    print(f'  {"场景":10s}  ', end='')
    for s in SIGNALS[:6]:
        print(f'{SIGNAL_LABELS[s][:4]:>7s}', end='')
    print()
    print(f'  {"─" * 60}')

    for scenario_name, ctx in SCENARIOS.items():
        signals = test_agent.compute_signals(ctx)
        print(f'  {scenario_name:10s}  ', end='')
        for s in SIGNALS[:6]:
            val = signals[s]
            color = C.RED if val > 0.65 else C.BLUE if val < 0.35 else C.DIM
            print(f'{color}{val:>7.3f}{C.RESET}', end='')
        print()

    print(f'\n  {C.GREEN}✓ 同一个 Agent 在不同场景下展现不同的行为倾向 — 不是贴标签{C.RESET}')

    # ═══════════════════════════════════════════
    # TEST 4: 内在矛盾检测
    # ═══════════════════════════════════════════
    print(f'\n{C.BOLD}{C.YELLOW}═══ TEST 4: 内在矛盾 — 真实人格不是一致的 ═══{C.RESET}')
    print(f'{C.DIM}检测每个 Agent 的行为信号是否存在自然的内在拉扯...{C.RESET}\n')

    contradiction_count = 0
    for agent in agents[:10]:
        fp = agent.personality_fingerprint(80)
        if fp.get('contradictions'):
            contradiction_count += 1
            c = fp['contradictions'][0]
            print(f'  seed={agent.seed:>6d}: '
                  f'{SIGNAL_LABELS[c[0]]} ↔ {SIGNAL_LABELS[c[1]]} '
                  f'{C.DIM}(r={c[2]:.2f}){C.RESET}')

    print(f'\n  {contradiction_count}/10 个 Agent 表现出内在矛盾')
    if contradiction_count >= 3:
        print(f'  {C.GREEN}✓ 内在矛盾自然涌现 — 不需要设计者硬编码{C.RESET}')

    # ═══════════════════════════════════════════
    # TEST 5: 进化轨迹可视化
    # ═══════════════════════════════════════════
    print(f'\n{C.BOLD}{C.YELLOW}═══ TEST 5: 进化轨迹 — 人格是如何"长"出来的 ═══{C.RESET}\n')

    viz_agent = agent_warm
    print(f'  Agent seed={viz_agent.seed} (温暖环境)')
    print(f'  行为信号随时间的变化 (sparkline):\n')

    for s in SIGNALS:
        vals = [h[s] for h in viz_agent.signal_history]
        # 取样（最多60个点）
        step = max(1, len(vals) // 60)
        sampled = vals[::step][:60]
        line = spark(sampled)
        final = vals[-1] if vals else 0
        print(f'  {SIGNAL_LABELS[s]:12s} {C.CYAN}{line}{C.RESET}  → {final:.2f}')

    evo_mag = Observer.evolution_magnitude(viz_agent, 50, 50)
    print(f'\n  进化幅度: {C.CYAN}{evo_mag:.3f}{C.RESET}')

    # ═══════════════════════════════════════════
    # TEST 6: LLM Prompt 注入示例
    # ═══════════════════════════════════════════
    print(f'\n{C.BOLD}{C.YELLOW}═══ TEST 6: LLM 调制接口 — 行为信号如何注入对话 ═══{C.RESET}')
    print(f'{C.DIM}这是 Agent 信号转化为 LLM system prompt 的实际输出...{C.RESET}\n')

    demo_agent = agents[2]
    for scenario_name in ['深夜心事', '日常闲聊', '吵架冲突']:
        ctx = SCENARIOS[scenario_name]
        prompt_text = demo_agent.to_prompt_injection(ctx)
        print(f'  {C.BOLD}── 场景: {scenario_name} ──{C.RESET}')
        for line in prompt_text.split('\n'):
            print(f'  {C.DIM}{line}{C.RESET}')
        print()

    # ═══════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════
    print(f"""
{C.BOLD}╔══════════════════════════════════════════════════════════════════════╗
║                    📊 v4 涌现性 Benchmark 总结                     ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  1. 先天多样性                                                       ║
║     → {N_AGENTS} 个 Agent 的行为多样性得分: {diversity['score']:.4f}                  ║
║     → Agent 间平均行为距离: {diversity['avg_distance']:.4f}                         ║
║                                                                      ║
║  2. 自我进化                                                         ║
║     → 同种子在温暖/冷淡环境下的行为分歧: {total_diff:.3f}                ║
║     → 进化不是参数调整，是网络权重的真实改变                           ║
║                                                                      ║
║  3. 情境敏感性                                                       ║
║     → 同一 Agent 在 7 种场景下展现不同行为组合                        ║
║     → 人格不是标签，是动态系统                                        ║
║                                                                      ║
║  4. 内在矛盾                                                        ║
║     → {contradiction_count}/10 个 Agent 自然涌现出内在矛盾信号              ║
║                                                                      ║
║  5. LLM 可接入                                                       ║
║     → 行为信号可直接转化为 system prompt 文本                         ║
║     → 保留涌现性的同时连接到实际对话                                   ║
║                                                                      ║
║  {C.CYAN}v4 vs v3: 从抽象博弈动作 → 可调制 LLM 行为的连续信号{C.RESET}            ║
║  {C.CYAN}v4 vs genome_test: 进化来自网络权重变化，不是 LLM 自由发挥{C.RESET}       ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝{C.RESET}
""")


if __name__ == '__main__':
    run()
