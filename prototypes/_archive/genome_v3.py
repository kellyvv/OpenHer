#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║     🧬 Agent Genome v3 — 随机网络涌现式人格 🧬                       ║
║     Random Neural Network Emergence Simulator                       ║
╠══════════════════════════════════════════════════════════════════════╣
║  v2 的致命问题: warmth = sigmoid(w1*O + w2*S + ...)                  ║
║     → 所有行为都是设计者写的公式，不是涌现                             ║
║                                                                      ║
║  v3 的解法:                                                          ║
║     基因组 = 随机种子 → 生成随机接线的小型神经网络                      ║
║     行为 = 网络对输入的响应（设计者不知道会产生什么行为）                 ║
║     人格 = 外部观察者从行为日志中事后识别                               ║
║     代码中没有任何"人格特征"变量                                       ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import math
import random
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

# ──────────────────────────────────────────────
# Actions: raw, atomic, no personality meaning
# ──────────────────────────────────────────────
ACTIONS = ['SHARE', 'COOPERATE', 'COMPETE', 'AVOID', 'OBSERVE', 'PLAY', 'TAKE']
N_ACTIONS = len(ACTIONS)

# Payoff matrix: outcome for (my_action, their_action)
# Rows = my action, Cols = their action
# Values = (my_reward, their_reward)
PAYOFF = {
    ('SHARE',     'SHARE'):     ( 3,  3),
    ('SHARE',     'COOPERATE'): ( 2,  2),
    ('SHARE',     'COMPETE'):   (-2,  4),
    ('SHARE',     'AVOID'):     ( 1,  0),
    ('SHARE',     'OBSERVE'):   ( 1,  1),
    ('SHARE',     'PLAY'):      ( 2,  2),
    ('SHARE',     'TAKE'):      (-3,  5),
    ('COOPERATE', 'SHARE'):     ( 2,  2),
    ('COOPERATE', 'COOPERATE'): ( 2,  2),
    ('COOPERATE', 'COMPETE'):   (-1,  3),
    ('COOPERATE', 'AVOID'):     ( 1,  0),
    ('COOPERATE', 'OBSERVE'):   ( 1,  1),
    ('COOPERATE', 'PLAY'):      ( 2,  2),
    ('COOPERATE', 'TAKE'):      (-2,  4),
    ('COMPETE',   'SHARE'):     ( 4, -2),
    ('COMPETE',   'COOPERATE'): ( 3, -1),
    ('COMPETE',   'COMPETE'):   (-1, -1),
    ('COMPETE',   'AVOID'):     ( 1, -1),
    ('COMPETE',   'OBSERVE'):   ( 2,  0),
    ('COMPETE',   'PLAY'):      ( 1, -1),
    ('COMPETE',   'TAKE'):      (-2, -2),
    ('AVOID',     'SHARE'):     ( 0,  1),
    ('AVOID',     'COOPERATE'): ( 0,  1),
    ('AVOID',     'COMPETE'):   (-1,  1),
    ('AVOID',     'AVOID'):     ( 0,  0),
    ('AVOID',     'OBSERVE'):   ( 0,  0),
    ('AVOID',     'PLAY'):      ( 0,  0),
    ('AVOID',     'TAKE'):      ( 0,  1),
    ('OBSERVE',   'SHARE'):     ( 1,  1),
    ('OBSERVE',   'COOPERATE'): ( 1,  1),
    ('OBSERVE',   'COMPETE'):   ( 0,  2),
    ('OBSERVE',   'AVOID'):     ( 0,  0),
    ('OBSERVE',   'OBSERVE'):   ( 0,  0),
    ('OBSERVE',   'PLAY'):      ( 1,  1),
    ('OBSERVE',   'TAKE'):      ( 0,  1),
    ('PLAY',      'SHARE'):     ( 2,  2),
    ('PLAY',      'COOPERATE'): ( 2,  2),
    ('PLAY',      'COMPETE'):   (-1,  1),
    ('PLAY',      'AVOID'):     ( 0,  0),
    ('PLAY',      'OBSERVE'):   ( 1,  1),
    ('PLAY',      'PLAY'):      ( 3,  3),
    ('PLAY',      'TAKE'):      (-2,  3),
    ('TAKE',      'SHARE'):     ( 5, -3),
    ('TAKE',      'COOPERATE'): ( 4, -2),
    ('TAKE',      'COMPETE'):   (-2, -2),
    ('TAKE',      'AVOID'):     ( 1,  0),
    ('TAKE',      'OBSERVE'):   ( 1,  0),
    ('TAKE',      'PLAY'):      ( 3, -2),
    ('TAKE',      'TAKE'):      (-3, -3),
}

# ──────────────────────────────────────────────
# Agent: Random Neural Network brain
# ──────────────────────────────────────────────
INPUT_SIZE = 12   # see _build_input()
HIDDEN_SIZE = 16
RECURRENT_SIZE = 6  # part of hidden state fed back as input

class Agent:
    """
    No personality traits. No designed equations.
    Genome = random seed → random neural network weights.
    Behavior = network response to inputs.
    """

    def __init__(self, seed):
        self.seed = seed
        rng = random.Random(seed)

        # GENOME: random network weights (this IS the genome, like DNA)
        total_in = INPUT_SIZE + RECURRENT_SIZE
        self.W_hidden = [[rng.gauss(0, 0.5) for _ in range(total_in)] for _ in range(HIDDEN_SIZE)]
        self.b_hidden = [rng.gauss(0, 0.2) for _ in range(HIDDEN_SIZE)]
        self.W_out = [[rng.gauss(0, 0.5) for _ in range(HIDDEN_SIZE)] for _ in range(N_ACTIONS)]
        self.b_out = [rng.gauss(0, 0.2) for _ in range(N_ACTIONS)]

        # Recurrent state (internal "mood" / short-term memory)
        self.hidden_state = [0.0] * HIDDEN_SIZE

        # Internal metabolic state
        self.energy = 5.0
        self.total_reward = 0.0

        # Relational memory: {other_agent_seed: [list of (my_action, their_action, reward)]}
        self.memory = defaultdict(list)

        # Behavioral log (for external observer)
        self.action_log = []

    def _build_input(self, other_last_action_idx, relationship_with_other):
        """Build input vector from raw perceptions. NO PERSONALITY ENCODING."""
        # One-hot of other's last action (7 values)
        action_onehot = [0.0] * N_ACTIONS
        if other_last_action_idx >= 0:
            action_onehot[other_last_action_idx] = 1.0

        # My current energy (normalized)
        energy_norm = self.energy / 10.0

        # Relationship signal: average reward from THIS specific opponent
        if relationship_with_other:
            avg_reward = sum(r for _, _, r in relationship_with_other[-10:]) / min(10, len(relationship_with_other))
            n_interactions = min(len(relationship_with_other), 20) / 20.0
        else:
            avg_reward = 0.0
            n_interactions = 0.0

        # Total: 7 + 1 + 1 + 1 + recurrent = 10 + recurrent
        raw = action_onehot + [energy_norm, avg_reward / 5.0, n_interactions]

        # Add noise (sensory noise, very biological)
        raw = [v + random.gauss(0, 0.05) for v in raw]

        # Pad to INPUT_SIZE
        while len(raw) < INPUT_SIZE:
            raw.append(0.0)

        return raw[:INPUT_SIZE]

    def act(self, other_seed, other_last_action_idx):
        """Choose an action using the random neural network."""
        relationship = self.memory.get(other_seed, [])
        inputs = self._build_input(other_last_action_idx, relationship)

        # Add recurrent connections (last RECURRENT_SIZE hidden units)
        full_input = inputs + self.hidden_state[:RECURRENT_SIZE]

        # Forward pass through random network
        new_hidden = []
        for i in range(HIDDEN_SIZE):
            z = self.b_hidden[i]
            for j, x in enumerate(full_input):
                z += self.W_hidden[i][j] * x
            new_hidden.append(math.tanh(z))

        self.hidden_state = new_hidden

        # Output layer → action logits
        logits = []
        for i in range(N_ACTIONS):
            z = self.b_out[i]
            for j, h in enumerate(new_hidden):
                z += self.W_out[i][j] * h
            logits.append(z)

        # Softmax with temperature (some randomness in decision)
        temperature = 0.8
        max_logit = max(logits)
        exp_logits = [math.exp((l - max_logit) / temperature) for l in logits]
        total = sum(exp_logits)
        probs = [e / total for e in exp_logits]

        # Sample action
        r = random.random()
        cumsum = 0
        chosen = 0
        for i, p in enumerate(probs):
            cumsum += p
            if cumsum >= r:
                chosen = i
                break

        return chosen

    def learn(self, action_idx, reward):
        """
        Hebbian learning: strengthen connections that led to rewarded actions.
        This is NOT designed personality modification —
        it's raw neural plasticity.
        """
        lr = 0.003 * (1 + abs(reward) / 5.0)

        # Strengthen/weaken output weights for the chosen action
        # based on which hidden neurons were active
        for j in range(HIDDEN_SIZE):
            if abs(self.hidden_state[j]) > 0.3:  # active neuron
                delta = lr * reward * self.hidden_state[j]
                self.W_out[action_idx][j] += delta

        # Slight modification to hidden weights based on reward sign
        # (this creates longer-term behavioral drift)
        if abs(reward) > 2:
            for i in range(HIDDEN_SIZE):
                if abs(self.hidden_state[i]) > 0.5:
                    for j in range(min(INPUT_SIZE, len(self.W_hidden[i]))):
                        self.W_hidden[i][j] += lr * 0.1 * reward * random.gauss(0, 1)

    def record(self, other_seed, my_action, their_action, reward):
        """Store experience in memory and log."""
        self.memory[other_seed].append((my_action, their_action, reward))
        self.action_log.append({
            'action': ACTIONS[my_action],
            'other_action': ACTIONS[their_action],
            'reward': reward,
        })
        self.energy = max(0, min(15, self.energy + reward * 0.3))
        self.total_reward += reward


# ──────────────────────────────────────────────
# World: Multi-agent interaction
# ──────────────────────────────────────────────
class World:
    def __init__(self, agents):
        self.agents = {a.seed: a for a in agents}
        self.seeds = list(self.agents.keys())

    def step(self):
        """One round: random pairing + simultaneous action"""
        random.shuffle(self.seeds)
        pairs = [(self.seeds[i], self.seeds[i+1])
                 for i in range(0, len(self.seeds) - 1, 2)]

        for s1, s2 in pairs:
            a1, a2 = self.agents[s1], self.agents[s2]

            # Last known action of opponent (from memory)
            mem1 = a1.memory.get(s2, [])
            mem2 = a2.memory.get(s1, [])
            last1 = mem2[-1][0] if mem2 else -1  # a1 remembers a2's last action
            last2 = mem1[-1][0] if mem1 else -1  # a2 remembers a1's last action

            # Both choose simultaneously
            act1 = a1.act(s2, last1)
            act2 = a2.act(s1, last2)

            # Resolve
            r1, r2 = PAYOFF[(ACTIONS[act1], ACTIONS[act2])]

            # Learn and record
            a1.learn(act1, r1)
            a2.learn(act2, r2)
            a1.record(s2, act1, act2, r1)
            a2.record(s1, act2, act1, r2)

    def run(self, steps):
        for _ in range(steps):
            self.step()


# ──────────────────────────────────────────────
# External Observer: knows NOTHING about internals
# ──────────────────────────────────────────────
class Observer:
    """
    Analyzes behavioral logs ONLY.
    Cannot see genomes, weights, hidden states, or energy levels.
    This is the "psychologist" who watches behavior and labels personality.
    """

    def __init__(self, agents):
        self.agents = agents

    def behavioral_profile(self, agent, window=None):
        """Compute behavioral statistics from action log only."""
        log = agent.action_log
        if window:
            log = log[-window:]
        if not log:
            return {}

        total = len(log)
        profile = {}

        # Action frequencies
        for action in ACTIONS:
            count = sum(1 for e in log if e['action'] == action)
            profile[f'{action}_rate'] = count / total

        # Reciprocity: do I cooperate/share with those who cooperate with me?
        positive_after_positive = 0
        negative_after_negative = 0
        total_sequential = 0
        for i in range(1, len(log)):
            prev_other = log[i-1]['other_action']
            my_current = log[i]['action']
            if prev_other in ('SHARE', 'COOPERATE', 'PLAY'):
                total_sequential += 1
                if my_current in ('SHARE', 'COOPERATE', 'PLAY'):
                    positive_after_positive += 1
            elif prev_other in ('COMPETE', 'TAKE'):
                total_sequential += 1
                if my_current in ('COMPETE', 'TAKE', 'AVOID'):
                    negative_after_negative += 1

        profile['reciprocity'] = positive_after_positive / max(1, total_sequential)
        profile['retaliation'] = negative_after_negative / max(1, total_sequential)

        # Behavioral entropy (diversity of actions)
        import math as m
        probs = [profile[f'{a}_rate'] for a in ACTIONS]
        entropy = -sum(p * m.log2(p) if p > 0 else 0 for p in probs)
        profile['entropy'] = entropy / m.log2(N_ACTIONS)  # normalized 0-1

        # Prosocial ratio
        prosocial = profile.get('SHARE_rate', 0) + profile.get('COOPERATE_rate', 0) + profile.get('PLAY_rate', 0)
        antisocial = profile.get('COMPETE_rate', 0) + profile.get('TAKE_rate', 0)
        profile['prosocial_ratio'] = prosocial / max(0.01, prosocial + antisocial)

        return profile

    def cluster_agents(self, k=None):
        """Find emergent personality clusters using k-means on behavioral profiles."""
        profiles = []
        for agent in self.agents:
            p = self.behavioral_profile(agent)
            if not p:
                continue
            # Use a consistent feature vector
            vec = [
                p.get('SHARE_rate', 0), p.get('COOPERATE_rate', 0),
                p.get('COMPETE_rate', 0), p.get('TAKE_rate', 0),
                p.get('AVOID_rate', 0), p.get('OBSERVE_rate', 0),
                p.get('PLAY_rate', 0), p.get('reciprocity', 0),
                p.get('retaliation', 0), p.get('entropy', 0),
                p.get('prosocial_ratio', 0),
            ]
            profiles.append((agent, vec))

        if not profiles:
            return {}

        # Auto-detect good k using silhouette-like heuristic
        if k is None:
            best_k, best_score = 2, -1
            for try_k in range(2, min(8, len(profiles))):
                assignments, centroids = self._kmeans([v for _, v in profiles], try_k)
                score = self._silhouette_score([v for _, v in profiles], assignments, centroids)
                if score > best_score:
                    best_score = score
                    best_k = try_k
            k = best_k

        assignments, centroids = self._kmeans([v for _, v in profiles], k)

        # Group and name clusters
        clusters = defaultdict(list)
        for i, (agent, vec) in enumerate(profiles):
            clusters[assignments[i]].append(agent)

        named_clusters = {}
        for cluster_id, members in clusters.items():
            centroid = centroids[cluster_id]
            name = self._name_cluster(centroid)
            named_clusters[name] = {
                'members': members,
                'centroid': centroid,
                'count': len(members),
            }

        return named_clusters

    def _name_cluster(self, centroid):
        """Name a cluster based on dominant behavioral pattern. NOT pre-designed categories."""
        feature_names = ['SHARE', 'COOPERATE', 'COMPETE', 'TAKE', 'AVOID', 'OBSERVE', 'PLAY',
                         'reciprocity', 'retaliation', 'entropy', 'prosocial']

        # Find top 2 features
        indexed = sorted(enumerate(centroid), key=lambda x: x[1], reverse=True)
        top = indexed[:2]

        labels = {
            'SHARE': '给予', 'COOPERATE': '协作', 'COMPETE': '竞争',
            'TAKE': '掠夺', 'AVOID': '回避', 'OBSERVE': '观察',
            'PLAY': '玩乐', 'reciprocity': '互惠', 'retaliation': '报复',
            'entropy': '多变', 'prosocial': '亲社会',
        }

        parts = []
        for idx, val in top:
            if idx < len(feature_names):
                parts.append(labels.get(feature_names[idx], feature_names[idx]))

        return '·'.join(parts) if parts else '未知'

    def _kmeans(self, vectors, k, max_iter=50):
        n = len(vectors)
        dim = len(vectors[0])

        # k-means++ init
        centroids = [list(vectors[random.randint(0, n-1)])]
        for _ in range(k - 1):
            dists = [min(self._dist(v, c) for c in centroids) for v in vectors]
            total = sum(dists) or 1
            probs = [d / total for d in dists]
            r = random.random()
            cumsum = 0
            for i, p in enumerate(probs):
                cumsum += p
                if cumsum >= r:
                    centroids.append(list(vectors[i]))
                    break

        assignments = [0] * n
        for _ in range(max_iter):
            changed = False
            for i in range(n):
                best = min(range(k), key=lambda j: self._dist(vectors[i], centroids[j]))
                if assignments[i] != best:
                    changed = True
                    assignments[i] = best
            if not changed:
                break
            for j in range(k):
                members = [vectors[i] for i in range(n) if assignments[i] == j]
                if members:
                    centroids[j] = [sum(m[d] for m in members) / len(members) for d in range(dim)]

        return assignments, centroids

    def _dist(self, a, b):
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    def _silhouette_score(self, vectors, assignments, centroids):
        """Simplified silhouette score."""
        if len(set(assignments)) <= 1:
            return -1
        scores = []
        for i, v in enumerate(vectors):
            my_cluster = assignments[i]
            same = [vectors[j] for j in range(len(vectors)) if assignments[j] == my_cluster and j != i]
            if not same:
                continue
            a = sum(self._dist(v, s) for s in same) / len(same)
            b = float('inf')
            for c in range(len(centroids)):
                if c == my_cluster:
                    continue
                others = [vectors[j] for j in range(len(vectors)) if assignments[j] == c]
                if others:
                    b = min(b, sum(self._dist(v, o) for o in others) / len(others))
            if b == float('inf'):
                continue
            scores.append((b - a) / max(a, b))
        return sum(scores) / len(scores) if scores else -1

    def correlation_with_seed(self, agents):
        """Test if behavioral profile correlates with genome seed (it shouldn't strongly)."""
        profiles = []
        for agent in agents:
            p = self.behavioral_profile(agent)
            if p:
                profiles.append((agent.seed, p.get('prosocial_ratio', 0.5)))
        if len(profiles) < 3:
            return 0
        seeds = [s for s, _ in profiles]
        vals = [v for _, v in profiles]
        # Simple rank correlation
        seed_ranks = self._ranks(seeds)
        val_ranks = self._ranks(vals)
        n = len(seed_ranks)
        d_sq = sum((seed_ranks[i] - val_ranks[i]) ** 2 for i in range(n))
        rho = 1 - 6 * d_sq / (n * (n**2 - 1)) if n > 1 else 0
        return abs(rho)

    def _ranks(self, values):
        sorted_indices = sorted(range(len(values)), key=lambda i: values[i])
        ranks = [0] * len(values)
        for rank, idx in enumerate(sorted_indices):
            ranks[idx] = rank
        return ranks


# ──────────────────────────────────────────────
# Visualization helpers
# ──────────────────────────────────────────────
def bar(value, width=20, color=C.CYAN):
    filled = int(max(0, min(1, value)) * width)
    return f'{color}{"█" * filled}{C.DIM}{"░" * (width - filled)}{C.RESET}'

SPARK = ' ▁▂▃▄▅▆▇█'
def spark(values):
    return ''.join(SPARK[min(8, max(0, int(v * 8)))] for v in values)


# ──────────────────────────────────────────────
# Main Simulation
# ──────────────────────────────────────────────
def run():
    N_AGENTS = 20
    N_STEPS = 500

    print(f"""
{C.BOLD}╔══════════════════════════════════════════════════════════════════════╗
║     🧬 Agent Genome v3 — 随机网络涌现式人格 🧬                       ║
║     Random Neural Network Emergence Simulator                       ║
╠══════════════════════════════════════════════════════════════════════╣
║  基因组 = 随机种子 → 随机接线的神经网络                                ║
║  代码中没有任何"人格"、"温暖"、"果断"等词汇                            ║
║  人格由外部观察者从纯行为日志中事后识别                                 ║
╚══════════════════════════════════════════════════════════════════════╝{C.RESET}
""")

    # ═══════════════════════════════════════════
    # TEST 1: Generate population and let them interact
    # ═══════════════════════════════════════════
    print(f'{C.BOLD}{C.YELLOW}═══ TEST 1: 多Agent社会模拟 ═══{C.RESET}')
    print(f'{C.DIM}{N_AGENTS} 个Agent，每个有随机接线的神经网络大脑，互动 {N_STEPS} 轮...{C.RESET}\n')

    agents = [Agent(seed=i * 137 + 42) for i in range(N_AGENTS)]
    world = World(agents)
    world.run(N_STEPS)

    print(f'  {C.GREEN}✓ 模拟完成。{N_AGENTS} 个Agent共完成 {sum(len(a.action_log) for a in agents)} 次行为。{C.RESET}\n')

    # Show raw action distributions for a few agents
    print(f'  {C.BOLD}随机抽查 3 个Agent的行为分布（原始数据）:{C.RESET}\n')
    for agent in agents[:3]:
        print(f'  {C.BOLD}Agent seed={agent.seed}{C.RESET}  (total reward: {agent.total_reward:.0f})')
        total = len(agent.action_log)
        for action in ACTIONS:
            count = sum(1 for e in agent.action_log if e['action'] == action)
            pct = count / total if total else 0
            print(f'    {action:10s} {bar(pct, 25)} {pct:.1%}')
        print()

    # ═══════════════════════════════════════════
    # TEST 2: External Observer — blind personality recognition
    # ═══════════════════════════════════════════
    print(f'{C.BOLD}{C.YELLOW}═══ TEST 2: 盲分析 — 外部观察者仅从行为日志识别人格 ═══{C.RESET}')
    print(f'{C.DIM}观察者不知道基因组/网络权重/内部状态，只看行为记录...{C.RESET}\n')

    observer = Observer(agents)
    clusters = observer.cluster_agents()

    print(f'  {C.BOLD}涌现出的行为类型 ({len(clusters)} 种):{C.RESET}\n')
    for name, info in sorted(clusters.items(), key=lambda x: x[1]['count'], reverse=True):
        print(f'  {C.BOLD}{name:12s}{C.RESET}  {C.CYAN}{info["count"]:2d} agents{C.RESET}  '
              f'{C.DIM}{"●" * info["count"]}{C.RESET}')
        # Show 2 example members
        for agent in info['members'][:2]:
            profile = observer.behavioral_profile(agent)
            top_actions = sorted(
                [(a, profile.get(f'{a}_rate', 0)) for a in ACTIONS],
                key=lambda x: x[1], reverse=True
            )[:3]
            actions_str = ', '.join(f'{a}={v:.0%}' for a, v in top_actions)
            print(f'           {C.DIM}seed={agent.seed}: {actions_str}{C.RESET}')
    print()

    n_types = len(clusters)
    print(f'  {C.GREEN}✓ 外部观察者从纯行为数据中识别出 {n_types} 种行为类型{C.RESET}')
    print(f'  {C.DIM}  这些类型名称（给予·协作 等）是观察者命名的，不是系统预设的{C.RESET}')

    # ═══════════════════════════════════════════
    # TEST 3: De-correlation — personality ≠ genome
    # ═══════════════════════════════════════════
    print(f'\n{C.BOLD}{C.YELLOW}═══ TEST 3: 去相关 — 涌现的人格 ≠ 基因组参数的映射 ═══{C.RESET}')
    print(f'{C.DIM}检验行为模式是否与随机种子相关（不应该强相关）...{C.RESET}\n')

    corr = observer.correlation_with_seed(agents)
    print(f'  种子值与亲社会行为的秩相关系数: {C.CYAN}ρ = {corr:.3f}{C.RESET}')
    if corr < 0.3:
        print(f'  {C.GREEN}✓ 低相关 (ρ < 0.3): 人格不是基因组的简单函数{C.RESET}')
    else:
        print(f'  {C.YELLOW}⚠ 相关偏高，可能需要更多交互步数{C.RESET}')

    # ═══════════════════════════════════════════
    # TEST 4: Path Dependence — same genome, different history
    # ═══════════════════════════════════════════
    print(f'\n{C.BOLD}{C.YELLOW}═══ TEST 4: 路径依赖 — 同一大脑，不同经历 ═══{C.RESET}')
    print(f'{C.DIM}相同随机种子的Agent在两个不同的社会中成长...{C.RESET}\n')

    # Society A: mostly cooperative agents
    coop_agents = [Agent(seed=999)] + [Agent(seed=i * 37 + 100) for i in range(9)]
    world_a = World(coop_agents)
    world_a.run(N_STEPS)

    # Society B: same seed 999, but among different agents
    comp_agents = [Agent(seed=999)] + [Agent(seed=i * 73 + 5000) for i in range(9)]
    world_b = World(comp_agents)
    world_b.run(N_STEPS)

    obs_a = Observer(coop_agents)
    obs_b = Observer(comp_agents)
    profile_a = obs_a.behavioral_profile(coop_agents[0])
    profile_b = obs_b.behavioral_profile(comp_agents[0])

    print(f'  {C.BOLD}Agent seed=999 在两个不同社会中的行为:{C.RESET}\n')
    print(f'  {"行为":10s}  {"社会A":>8s}  {"社会B":>8s}  {"差异":>6s}')
    print(f'  {"─" * 40}')
    total_diff = 0
    for action in ACTIONS:
        key = f'{action}_rate'
        va = profile_a.get(key, 0)
        vb = profile_b.get(key, 0)
        diff = abs(va - vb)
        total_diff += diff
        diff_color = C.RED if diff > 0.1 else C.YELLOW if diff > 0.05 else C.GREEN
        print(f'  {action:10s}  {va:>7.1%}  {vb:>7.1%}  {diff_color}{diff:>5.1%}{C.RESET}')

    print(f'\n  亲社会比: A={profile_a.get("prosocial_ratio", 0):.2f}  '
          f'B={profile_b.get("prosocial_ratio", 0):.2f}')
    print(f'  总行为分歧: {C.CYAN}{total_diff:.3f}{C.RESET}')

    if total_diff > 0.15:
        print(f'  {C.GREEN}✓ 路径依赖确认: 相同"大脑"在不同社会中发展出不同行为模式{C.RESET}')
    else:
        print(f'  {C.YELLOW}⚠ 分歧较小，可能需要更极端的社会差异{C.RESET}')

    # ═══════════════════════════════════════════
    # TEST 5: Multi-agent vs Single-agent (social emergence)
    # ═══════════════════════════════════════════
    print(f'\n{C.BOLD}{C.YELLOW}═══ TEST 5: 社会涌现 — 有无社交是否影响人格多样性？ ═══{C.RESET}')
    print(f'{C.DIM}对比: 20个Agent互相交互 vs 20个Agent只与固定机器人交互...{C.RESET}\n')

    # Social condition: agents interact with each other (already done above)
    social_profiles = [observer.behavioral_profile(a) for a in agents]
    social_entropies = [p.get('entropy', 0) for p in social_profiles if p]

    # Isolated condition: each agent only interacts with a simple bot
    class SimpleBot(Agent):
        """A bot that always cooperates (static environment)"""
        def act(self, other_seed, other_last_action_idx):
            return ACTIONS.index('COOPERATE')
        def learn(self, action_idx, reward):
            pass

    isolated_agents = [Agent(seed=i * 137 + 42) for i in range(N_AGENTS)]  # same seeds!
    bot = SimpleBot(seed=-1)
    for agent in isolated_agents:
        for _ in range(N_STEPS):
            act_a = agent.act(bot.seed, ACTIONS.index('COOPERATE'))
            act_b = bot.act(agent.seed, act_a)
            r_a, r_b = PAYOFF[(ACTIONS[act_a], ACTIONS[act_b])]
            agent.learn(act_a, r_a)
            agent.record(bot.seed, act_a, act_b, r_a)

    iso_observer = Observer(isolated_agents)
    iso_profiles = [iso_observer.behavioral_profile(a) for a in isolated_agents]
    iso_entropies = [p.get('entropy', 0) for p in iso_profiles if p]

    # Compare diversity
    def variance(values):
        if not values:
            return 0
        mean = sum(values) / len(values)
        return sum((v - mean) ** 2 for v in values) / len(values)

    # Compute variance of action distributions
    social_variances = []
    iso_variances = []
    for action in ACTIONS:
        key = f'{action}_rate'
        social_vals = [p.get(key, 0) for p in social_profiles if p]
        iso_vals = [p.get(key, 0) for p in iso_profiles if p]
        social_variances.append(variance(social_vals))
        iso_variances.append(variance(iso_vals))

    avg_social_var = sum(social_variances) / len(social_variances)
    avg_iso_var = sum(iso_variances) / len(iso_variances)

    iso_clusters = iso_observer.cluster_agents()

    print(f'  {"指标":20s}  {"社交环境":>10s}  {"孤立环境":>10s}')
    print(f'  {"─" * 45}')
    print(f'  {"行为多样性(方差)":20s}  {C.CYAN}{avg_social_var:.4f}{C.RESET}     {C.CYAN}{avg_iso_var:.4f}{C.RESET}')
    print(f'  {"涌现类型数":20s}  {C.CYAN}{n_types:>6d}{C.RESET}     {C.CYAN}{len(iso_clusters):>6d}{C.RESET}')
    avg_social_ent = sum(social_entropies) / len(social_entropies) if social_entropies else 0
    avg_iso_ent = sum(iso_entropies) / len(iso_entropies) if iso_entropies else 0
    print(f'  {"平均行为熵":20s}  {C.CYAN}{avg_social_ent:.3f}{C.RESET}      {C.CYAN}{avg_iso_ent:.3f}{C.RESET}')

    if avg_social_var > avg_iso_var * 1.2:
        print(f'\n  {C.GREEN}✓ 社交环境产生了更大的行为多样性 — 人格是社会性的产物{C.RESET}')
    elif avg_social_var > avg_iso_var:
        print(f'\n  {C.GREEN}✓ 社交环境产生了略多的行为多样性{C.RESET}')
    else:
        print(f'\n  {C.YELLOW}⚠ 差异不显著，可能需要更长的交互时间{C.RESET}')

    # ═══════════════════════════════════════════
    # TEST 6: Behavioral Consistency (stability over time)
    # ═══════════════════════════════════════════
    print(f'\n{C.BOLD}{C.YELLOW}═══ TEST 6: 行为一致性 — 涌现的人格是否稳定？ ═══{C.RESET}')
    print(f'{C.DIM}比较每个Agent前半程 vs 后半程的行为模式...{C.RESET}\n')

    consistencies = []
    for agent in agents[:6]:
        half = len(agent.action_log) // 2
        first_half = agent.action_log[:half]
        second_half = agent.action_log[half:]

        # Create temp agents with split logs
        class FakeAgent:
            def __init__(self, log):
                self.action_log = log
        fa = FakeAgent(first_half)
        fb = FakeAgent(second_half)
        p1 = observer.behavioral_profile(fa)
        p2 = observer.behavioral_profile(fb)

        if p1 and p2:
            # Cosine similarity between action profiles
            vec1 = [p1.get(f'{a}_rate', 0) for a in ACTIONS]
            vec2 = [p2.get(f'{a}_rate', 0) for a in ACTIONS]
            dot = sum(a * b for a, b in zip(vec1, vec2))
            mag1 = math.sqrt(sum(a**2 for a in vec1))
            mag2 = math.sqrt(sum(b**2 for b in vec2))
            sim = dot / (mag1 * mag2) if mag1 and mag2 else 0
            consistencies.append(sim)

            # Show as sparkline: first half vs second half
            sp1 = spark(vec1)
            sp2 = spark(vec2)
            sim_color = C.GREEN if sim > 0.9 else C.YELLOW if sim > 0.7 else C.RED
            print(f'  Agent {agent.seed:>5}: 前半 {C.CYAN}{sp1}{C.RESET}  '
                  f'后半 {C.MAGENTA}{sp2}{C.RESET}  '
                  f'一致性={sim_color}{sim:.3f}{C.RESET}')

    avg_consistency = sum(consistencies) / len(consistencies) if consistencies else 0
    print(f'\n  平均一致性: {C.CYAN}{avg_consistency:.3f}{C.RESET}')
    if avg_consistency > 0.85:
        print(f'  {C.GREEN}✓ 高度稳定: 涌现的行为模式在时间上是持久的（= 真正的"人格"）{C.RESET}')
    elif avg_consistency > 0.7:
        print(f'  {C.GREEN}✓ 中等稳定: 行为模式基本持久，有自然漂移{C.RESET}')
    else:
        print(f'  {C.YELLOW}⚠ 不够稳定: 行为模式还在剧烈变化中{C.RESET}')

    # ═══════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════
    print(f"""
{C.BOLD}╔══════════════════════════════════════════════════════════════════════╗
║                    📊 涌现性 Benchmark 总结                          ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  Benchmark 1: 盲分析 (Blind Recognition)                            ║
║  → 外部观察者从纯行为数据中识别出 {n_types} 种行为类型                   ║
║                                                                      ║
║  Benchmark 2: 去相关 (De-correlation)                                ║
║  → 基因组与行为的相关系数 ρ = {corr:.3f}                               ║
║                                                                      ║
║  Benchmark 3: 路径依赖 (Path Dependence)                             ║
║  → 同一大脑在不同社会中的行为分歧 = {total_diff:.3f}                    ║
║                                                                      ║
║  Benchmark 4: 社会涌现 (Social Emergence)                            ║
║  → 社交环境行为方差 {avg_social_var:.4f} vs 孤立环境 {avg_iso_var:.4f}        ║
║                                                                      ║
║  Benchmark 5: 行为一致性 (Behavioral Consistency)                    ║
║  → 前后半程行为一致性 = {avg_consistency:.3f}                             ║
║                                                                      ║
║  {C.CYAN}关键区别: 代码中没有"温暖"、"果断"等任何人格词汇{C.RESET}              ║
║  {C.CYAN}所有人格类别都是外部观察者从行为日志中事后发现的{C.RESET}              ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝{C.RESET}
""")


if __name__ == '__main__':
    run()
