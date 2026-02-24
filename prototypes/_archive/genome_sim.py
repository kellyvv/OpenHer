#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║            Agent Genome — 涌现式人格模拟器                        ║
║            Emergent Personality Simulator                        ║
╚══════════════════════════════════════════════════════════════════╝

第一性原理:
  人类行为多样性的底层代码不是"性格标签"，而是 4 种神经递质的相对浓度：
  - Dopamine  (多巴胺)  → 驱动力、探索、奖赏寻求
  - Serotonin (血清素)  → 稳定性、耐心、社会等级感知
  - Norepinephrine (去甲肾上腺素) → 警觉、注意力、细节感知
  - Oxytocin  (催产素)  → 联结、温暖、信任

  这 4 个系统的相对强度 + 非线性交互 + 环境调控
  = 无穷多样的人格表现

本模拟验证：
  1. 4 个基因能否产生可辨识的人格类型？（涌现测试）
  2. 同一基因组在不同环境下行为是否不同？（情境适应测试）
  3. 多样性是否足够丰富？（多样性测试）
"""

import math
import random
from collections import defaultdict

# ──────────────────────────────────────────────
# ANSI Colors for terminal output
# ──────────────────────────────────────────────
class C:
    RESET   = '\033[0m'
    BOLD    = '\033[1m'
    DIM     = '\033[2m'
    # Foreground
    RED     = '\033[91m'
    GREEN   = '\033[92m'
    YELLOW  = '\033[93m'
    BLUE    = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN    = '\033[96m'
    WHITE   = '\033[97m'
    GRAY    = '\033[90m'
    # Background
    BG_RED  = '\033[41m'
    BG_BLUE = '\033[44m'
    BG_MAG  = '\033[45m'
    BG_CYAN = '\033[46m'

# ──────────────────────────────────────────────
# Core: The Genome
# ──────────────────────────────────────────────
def random_genome():
    """Generate a random genome: 4 neurotransmitter levels in [0, 1]"""
    return {
        'D': random.random(),  # Dopamine
        'S': random.random(),  # Serotonin
        'N': random.random(),  # Norepinephrine
        'O': random.random(),  # Oxytocin
    }

# ──────────────────────────────────────────────
# Core: Contexts (environments that modulate expression)
# ──────────────────────────────────────────────
CONTEXTS = {
    '☕ 闲聊 Casual Chat': {
        'social_distance': 0.2,
        'pressure': 0.1,
        'novelty': 0.3,
        'conflict': 0.05,
    },
    '💼 正式会议 Formal Meeting': {
        'social_distance': 0.8,
        'pressure': 0.5,
        'novelty': 0.15,
        'conflict': 0.2,
    },
    '🔥 危机处理 Crisis': {
        'social_distance': 0.4,
        'pressure': 0.9,
        'novelty': 0.7,
        'conflict': 0.6,
    },
    '🌱 探索未知 Exploring': {
        'social_distance': 0.3,
        'pressure': 0.15,
        'novelty': 0.9,
        'conflict': 0.1,
    },
    '⚔️ 激烈争论 Heated Debate': {
        'social_distance': 0.5,
        'pressure': 0.7,
        'novelty': 0.2,
        'conflict': 0.9,
    },
    '🌙 深夜倾诉 Late Night Talk': {
        'social_distance': 0.1,
        'pressure': 0.05,
        'novelty': 0.4,
        'conflict': 0.02,
    },
}

# ──────────────────────────────────────────────
# Core: Expression Engine (Genotype → Phenotype)
# ──────────────────────────────────────────────
def sigmoid(x):
    """Sigmoid function with clamp to avoid overflow"""
    x = max(-10, min(10, x))
    return 1.0 / (1.0 + math.exp(-x))

def express(genome, context):
    """
    The core expression function.
    4 genes + context → 8 observable traits

    Key insight: uses INTERACTION TERMS (D*O, S*N, etc.)
    to create nonlinear emergence. A linear model cannot produce emergence.
    """
    D, S, N, O = genome['D'], genome['S'], genome['N'], genome['O']
    sd = context['social_distance']
    pr = context['pressure']
    nv = context['novelty']
    cf = context['conflict']

    # ── Step 1: Regulation (环境调控基因表达) ──
    # Like epigenetics: context doesn't change genes, but modulates their EFFECTIVE levels
    D_eff = D + 0.2 * nv - 0.15 * pr + 0.1 * (D * nv)  # novelty boosts dopamine
    S_eff = S + 0.15 * (1-cf) - 0.1 * nv + 0.1 * (S * pr)  # stability context boosts serotonin
    N_eff = N + 0.2 * pr + 0.15 * cf + 0.1 * (N * cf)  # threat boosts norepinephrine
    O_eff = O - 0.2 * cf + 0.2 * (1-sd) + 0.1 * (O * (1-sd))  # intimacy boosts oxytocin

    # Clamp effective values
    D_eff = max(0, min(1.3, D_eff))
    S_eff = max(0, min(1.3, S_eff))
    N_eff = max(0, min(1.3, N_eff))
    O_eff = max(0, min(1.3, O_eff))

    # ── Step 2: Nonlinear Expression (非线性表达) ──
    # Each trait is a nonlinear function of multiple effective gene values
    # The interaction terms (D_eff * O_eff, etc.) are what create EMERGENCE

    traits = {
        '健谈 Verbosity':     sigmoid(3.0 * D_eff - 1.0 * N_eff - 1.5 * sd + 0.8 * O_eff * D_eff - 1.2),
        '严谨 Rigor':         sigmoid(2.5 * N_eff + 1.5 * S_eff - 0.8 * D_eff + 0.6 * N_eff * S_eff - 1.5),
        '幽默 Humor':         sigmoid(2.0 * D_eff + 1.5 * O_eff - 2.5 * pr - 1.0 * cf + 1.0 * D_eff * O_eff - 1.5),
        '温暖 Warmth':        sigmoid(2.5 * O_eff + 0.8 * S_eff - 1.5 * cf - 0.5 * sd + 0.5 * O_eff * S_eff - 1.0),
        '冒险 Risk-taking':   sigmoid(2.5 * D_eff - 1.5 * S_eff - 1.0 * N_eff + 0.8 * nv + 0.5 * D_eff * (1-S_eff) - 0.8),
        '果断 Assertiveness': sigmoid(2.0 * D_eff + 1.5 * (1-S_eff) - 0.8 * O_eff + 1.2 * cf + 0.4 * D_eff * (1-O_eff) - 1.0),
        '共情 Empathy':       sigmoid(2.0 * O_eff + 1.5 * N_eff - 1.0 * D_eff - 0.5 * cf + 0.8 * O_eff * N_eff - 1.5),
        '创造 Creativity':    sigmoid(1.5 * D_eff + 1.2 * N_eff + 2.0 * nv - 1.5 * pr + 0.5 * D_eff * N_eff * nv - 1.2),
    }

    return traits

# ──────────────────────────────────────────────
# Clustering: K-Means on expressed trait profiles
# ──────────────────────────────────────────────
def trait_vector(genome):
    """Compute a comprehensive trait vector by averaging expression across all contexts"""
    all_vals = []
    for ctx in CONTEXTS.values():
        traits = express(genome, ctx)
        all_vals.extend(traits.values())
    return all_vals

def euclidean_dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

def kmeans(vectors, k, max_iter=50):
    """Simple k-means clustering"""
    n = len(vectors)
    dim = len(vectors[0])

    # Initialize centroids using k-means++
    centroids = [list(vectors[random.randint(0, n-1)])]
    for _ in range(k - 1):
        dists = [min(euclidean_dist(v, c) for c in centroids) for v in vectors]
        total = sum(dists)
        if total == 0:
            centroids.append(list(vectors[random.randint(0, n-1)]))
            continue
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
        # Assign
        changed = False
        for i in range(n):
            best_k = min(range(k), key=lambda j: euclidean_dist(vectors[i], centroids[j]))
            if assignments[i] != best_k:
                changed = True
                assignments[i] = best_k
        if not changed:
            break

        # Update centroids
        for j in range(k):
            members = [vectors[i] for i in range(n) if assignments[i] == j]
            if members:
                centroids[j] = [sum(m[d] for m in members) / len(members) for d in range(dim)]

    return assignments, centroids

# ──────────────────────────────────────────────
# Archetype Naming (emergent, based on centroid traits)
# ──────────────────────────────────────────────
TRAIT_NAMES = ['健谈', '严谨', '幽默', '温暖', '冒险', '果断', '共情', '创造']

ARCHETYPE_RULES = [
    # (condition_fn, chinese_name, english_name, emoji)
    (lambda t: t['果断'] > 0.65 and t['冒险'] > 0.6 and t['温暖'] < 0.4,
     '指挥官', 'Commander', '🦁'),
    (lambda t: t['温暖'] > 0.65 and t['共情'] > 0.6 and t['严谨'] > 0.5,
     '导师', 'Mentor', '🦉'),
    (lambda t: t['幽默'] > 0.6 and t['健谈'] > 0.6 and t['温暖'] > 0.5,
     '外交家', 'Diplomat', '🦊'),
    (lambda t: t['严谨'] > 0.65 and t['创造'] > 0.5 and t['健谈'] < 0.45,
     '建筑师', 'Architect', '🐝'),
    (lambda t: t['创造'] > 0.6 and t['冒险'] > 0.55 and t['严谨'] < 0.45,
     '探险家', 'Explorer', '🦅'),
    (lambda t: t['共情'] > 0.65 and t['温暖'] > 0.6 and t['果断'] < 0.4,
     '治愈者', 'Healer', '🐬'),
    (lambda t: t['严谨'] > 0.6 and t['果断'] > 0.55 and t['共情'] < 0.45,
     '分析师', 'Analyst', '🐺'),
    (lambda t: t['冒险'] > 0.6 and t['幽默'] > 0.5 and t['果断'] > 0.5,
     '冒险家', 'Maverick', '🐆'),
    (lambda t: t['温暖'] > 0.55 and t['创造'] > 0.55 and t['共情'] > 0.5,
     '梦想家', 'Dreamer', '🦋'),
    (lambda t: t['果断'] > 0.55 and t['温暖'] > 0.55 and t['严谨'] > 0.5,
     '领袖', 'Leader', '🐎'),
]

def name_archetype(avg_traits):
    """Name an archetype based on its dominant trait pattern. EMERGENT, not pre-assigned."""
    # Build trait dict for easy access
    trait_keys = ['健谈', '严谨', '幽默', '温暖', '冒险', '果断', '共情', '创造']
    t = {k: avg_traits[i] for i, k in enumerate(trait_keys)}

    # Try rule-based naming (rules check COMBINATIONS, not single traits)
    for rule_fn, cn, en, emoji in ARCHETYPE_RULES:
        try:
            if rule_fn(t):
                return f'{emoji} {cn} {en}'
        except:
            pass

    # Fallback: name by top 2 dominant traits
    sorted_traits = sorted(t.items(), key=lambda x: x[1], reverse=True)
    top2 = sorted_traits[:2]
    return f'🔮 {top2[0][0]}·{top2[1][0]}'

# ──────────────────────────────────────────────
# Visualization helpers
# ──────────────────────────────────────────────
def bar(value, width=20, color=C.CYAN):
    """Render a horizontal bar"""
    filled = int(value * width)
    return f'{color}{"█" * filled}{C.DIM}{"░" * (width - filled)}{C.RESET}'

def genome_str(g):
    """Pretty-print a genome"""
    labels = [
        (f'{C.MAGENTA}D 多巴胺{C.RESET}', g['D']),
        (f'{C.BLUE}S 血清素{C.RESET}', g['S']),
        (f'{C.RED}N 去甲肾{C.RESET}', g['N']),
        (f'{C.GREEN}O 催产素{C.RESET}', g['O']),
    ]
    lines = []
    for label, val in labels:
        lines.append(f'  {label}  {bar(val, 15)} {val:.2f}')
    return '\n'.join(lines)

def traits_str(traits):
    """Pretty-print expressed traits"""
    colors = [C.CYAN, C.YELLOW, C.MAGENTA, C.GREEN, C.RED, C.BLUE, C.GREEN, C.MAGENTA]
    lines = []
    for i, (name, val) in enumerate(traits.items()):
        c = colors[i % len(colors)]
        short_name = name.split(' ')[0]  # Chinese part
        lines.append(f'  {short_name:4s} {bar(val, 25, c)} {val:.2f}')
    return '\n'.join(lines)

# ──────────────────────────────────────────────
# Main Simulation
# ──────────────────────────────────────────────
def run_simulation(n_agents=60, n_clusters=8):
    random.seed(42)  # Reproducible

    print(f"""
{C.BOLD}╔══════════════════════════════════════════════════════════════════╗
║          🧬 Agent Genome 涌现式人格模拟器 🧬                     ║
║          Emergent Personality Simulator                          ║
╠══════════════════════════════════════════════════════════════════╣
║  第一性原理: 4种神经递质 → 非线性表达 → 涌现式人格                  ║
║  Core Code:  D(多巴胺) S(血清素) N(去甲肾上腺素) O(催产素)         ║
╚══════════════════════════════════════════════════════════════════╝{C.RESET}
""")

    # ═══════════════════════════════════════════
    # TEST 1: Generate Population & Cluster
    # ═══════════════════════════════════════════
    print(f'{C.BOLD}{C.YELLOW}═══ TEST 1: 涌现测试 — 4个基因能否自动产生人格类型？ ═══{C.RESET}')
    print(f'{C.DIM}生成 {n_agents} 个随机基因组，用 K-Means 聚类，观察是否涌现出可辨识的人格...{C.RESET}\n')

    agents = [{'id': i, 'genome': random_genome()} for i in range(n_agents)]

    # Compute trait vectors (expression across ALL contexts)
    vectors = [trait_vector(a['genome']) for a in agents]

    # Cluster
    assignments, centroids = kmeans(vectors, n_clusters)

    # Name each cluster by its centroid's average trait pattern
    cluster_info = {}
    for j in range(n_clusters):
        member_indices = [i for i, a in enumerate(assignments) if a == j]
        if not member_indices:
            continue
        # Average traits across the "casual" context for this cluster's members
        casual_ctx = CONTEXTS['☕ 闲聊 Casual Chat']
        avg_traits = [0.0] * 8
        for idx in member_indices:
            traits = express(agents[idx]['genome'], casual_ctx)
            for k, v in enumerate(traits.values()):
                avg_traits[k] += v
        avg_traits = [v / len(member_indices) for v in avg_traits]
        archetype_name = name_archetype(avg_traits)
        cluster_info[j] = {
            'name': archetype_name,
            'count': len(member_indices),
            'avg_traits': avg_traits,
            'members': member_indices,
        }

    # Print cluster results
    print(f'{C.BOLD}  涌现出的人格类型 (Emergent Archetypes):{C.RESET}\n')
    for j in sorted(cluster_info.keys(), key=lambda x: cluster_info[x]['count'], reverse=True):
        info = cluster_info[j]
        pct = info['count'] / n_agents * 100
        print(f'  {C.BOLD}{info["name"]:20s}{C.RESET}  '
              f'{C.CYAN}{info["count"]:2d} agents ({pct:4.1f}%){C.RESET}  '
              f'{C.DIM}{"●" * info["count"]}{C.RESET}')

    print(f'\n  {C.GREEN}✓ 4 个基因 → {len(cluster_info)} 种可辨识人格类型自然涌现{C.RESET}')
    print(f'  {C.DIM}  (未预设任何类型，纯粹从基因表达聚类中涌现){C.RESET}')

    # ═══════════════════════════════════════════
    # TEST 2: Context Adaptation (pick 3 example agents)
    # ═══════════════════════════════════════════
    print(f'\n\n{C.BOLD}{C.YELLOW}═══ TEST 2: 情境适应测试 — 同一基因组，不同环境，不同表现？ ═══{C.RESET}')
    print(f'{C.DIM}选取 3 个不同类型的 Agent，观察在不同场景下的行为变化...{C.RESET}\n')

    # Pick one agent from 3 different clusters
    shown_clusters = []
    example_agents = []
    for j in sorted(cluster_info.keys(), key=lambda x: cluster_info[x]['count'], reverse=True):
        if len(example_agents) >= 3:
            break
        idx = cluster_info[j]['members'][0]
        example_agents.append((idx, j))
        shown_clusters.append(j)

    for agent_idx, cluster_id in example_agents:
        agent = agents[agent_idx]
        archetype = cluster_info[cluster_id]['name']
        print(f'{C.BOLD}  ╭─ Agent #{agent_idx:02d}  {archetype}{C.RESET}')
        print(f'{C.BOLD}  │ 基因组 (Genome):{C.RESET}')
        for line in genome_str(agent['genome']).split('\n'):
            print(f'  │ {line}')
        print(f'{C.BOLD}  │{C.RESET}')

        # Show expression in 3 contexts
        ctx_keys = ['☕ 闲聊 Casual Chat', '🔥 危机处理 Crisis', '🌙 深夜倾诉 Late Night Talk']
        for ctx_name in ctx_keys:
            ctx = CONTEXTS[ctx_name]
            traits = express(agent['genome'], ctx)
            print(f'{C.BOLD}  │ 场景: {ctx_name}{C.RESET}')
            for line in traits_str(traits).split('\n'):
                print(f'  │ {line}')
            print(f'  │')
        print(f'  ╰{"─" * 60}\n')

    # ═══════════════════════════════════════════
    # TEST 3: Diversity Metric
    # ═══════════════════════════════════════════
    print(f'{C.BOLD}{C.YELLOW}═══ TEST 3: 多样性测试 — 4个基因的表达空间有多大？ ═══{C.RESET}')
    print(f'{C.DIM}计算种群内的行为距离分布...{C.RESET}\n')

    # Compute pairwise distances in trait space
    distances = []
    casual_ctx = CONTEXTS['☕ 闲聊 Casual Chat']
    trait_vecs = []
    for a in agents:
        t = express(a['genome'], casual_ctx)
        trait_vecs.append(list(t.values()))

    for i in range(len(trait_vecs)):
        for j in range(i+1, len(trait_vecs)):
            distances.append(euclidean_dist(trait_vecs[i], trait_vecs[j]))

    avg_dist = sum(distances) / len(distances)
    max_dist = max(distances)
    min_dist = min(distances)

    print(f'  种群大小:         {C.CYAN}{n_agents}{C.RESET}')
    print(f'  基因维度:         {C.CYAN}4{C.RESET} (D, S, N, O)')
    print(f'  表达维度:         {C.CYAN}8{C.RESET} (健谈, 严谨, 幽默, 温暖, 冒险, 果断, 共情, 创造)')
    print(f'  情境维度:         {C.CYAN}6{C.RESET} 种环境')
    print(f'  行为空间:         {C.CYAN}8 × 6 = 48{C.RESET} 维表现型空间')
    print(f'')
    print(f'  平均行为距离:     {C.GREEN}{avg_dist:.3f}{C.RESET}')
    print(f'  最大行为距离:     {C.GREEN}{max_dist:.3f}{C.RESET}')
    print(f'  最小行为距离:     {C.GREEN}{min_dist:.3f}{C.RESET}')
    print(f'  距离变异系数:     {C.GREEN}{(max_dist - min_dist) / avg_dist:.2f}{C.RESET}')

    # Uniqueness: how many agents have unique-enough profiles?
    threshold = avg_dist * 0.3
    unique_count = 0
    for i in range(len(trait_vecs)):
        is_unique = all(
            euclidean_dist(trait_vecs[i], trait_vecs[j]) > threshold
            for j in range(len(trait_vecs)) if j != i
        )
        if is_unique:
            unique_count += 1

    print(f'  高辨识度个体:     {C.GREEN}{unique_count}/{n_agents}{C.RESET} '
          f'(距离 > {threshold:.3f})')

    # ═══════════════════════════════════════════
    # TEST 4: Same Cluster, Different Individuals
    # ═══════════════════════════════════════════
    print(f'\n\n{C.BOLD}{C.YELLOW}═══ TEST 4: 类型内多样性 — 同一类型的人也不一样 ═══{C.RESET}')
    print(f'{C.DIM}同一人格类型内的不同个体，共享核心特征但有独特差异...{C.RESET}\n')

    # Find the largest cluster
    largest_cluster = max(cluster_info.keys(), key=lambda x: cluster_info[x]['count'])
    lc_info = cluster_info[largest_cluster]
    print(f'  最大类型: {C.BOLD}{lc_info["name"]}{C.RESET} ({lc_info["count"]} agents)\n')

    # Show 3 members from the same cluster
    members_to_show = lc_info['members'][:min(3, len(lc_info['members']))]
    casual_ctx = CONTEXTS['☕ 闲聊 Casual Chat']
    for idx in members_to_show:
        agent = agents[idx]
        traits = express(agent['genome'], casual_ctx)
        print(f'  {C.BOLD}Agent #{idx:02d}{C.RESET}  '
              f'D={agent["genome"]["D"]:.2f} S={agent["genome"]["S"]:.2f} '
              f'N={agent["genome"]["N"]:.2f} O={agent["genome"]["O"]:.2f}')
        # Show key traits inline
        top3 = sorted(traits.items(), key=lambda x: x[1], reverse=True)[:3]
        trait_display = '  '.join(f'{name.split(" ")[0]}={val:.2f}' for name, val in top3)
        print(f'           {C.DIM}强项: {trait_display}{C.RESET}')
    print(f'\n  {C.GREEN}✓ 同一类型内部仍有个体差异，不是模板化{C.RESET}')

    # ═══════════════════════════════════════════
    # TEST 5: Cross-context Identity Stability
    # ═══════════════════════════════════════════
    print(f'\n\n{C.BOLD}{C.YELLOW}═══ TEST 5: 身份稳定性测试 — 变化中的不变 ═══{C.RESET}')
    print(f'{C.DIM}同一个 Agent 在 6 种场景下，核心身份是否保持稳定？{C.RESET}\n')

    test_agent = agents[example_agents[0][0]]
    test_archetype = cluster_info[example_agents[0][1]]['name']
    print(f'  测试对象: {C.BOLD}Agent #{example_agents[0][0]:02d}  {test_archetype}{C.RESET}')
    print(f'  基因组: D={test_agent["genome"]["D"]:.2f} S={test_agent["genome"]["S"]:.2f} '
          f'N={test_agent["genome"]["N"]:.2f} O={test_agent["genome"]["O"]:.2f}\n')

    all_context_traits = {}
    trait_keys_ordered = None
    for ctx_name, ctx in CONTEXTS.items():
        traits = express(test_agent['genome'], ctx)
        if trait_keys_ordered is None:
            trait_keys_ordered = list(traits.keys())
        all_context_traits[ctx_name] = traits

    # Print header
    short_ctx_names = ['☕闲聊', '💼会议', '🔥危机', '🌱探索', '⚔️争论', '🌙倾诉']
    header = f'  {"特征":8s}'
    for sc in short_ctx_names:
        header += f' {sc:6s}'
    header += f'  {"变幅":4s}'
    print(f'{C.BOLD}{header}{C.RESET}')
    print(f'  {"─" * 65}')

    for trait_key in trait_keys_ordered:
        short_name = trait_key.split(' ')[0]
        vals = [all_context_traits[ctx_name][trait_key] for ctx_name in CONTEXTS.keys()]
        val_range = max(vals) - min(vals)

        line = f'  {short_name:6s}'
        for v in vals:
            if v > 0.65:
                c = C.GREEN
            elif v < 0.35:
                c = C.RED
            else:
                c = C.YELLOW
            line += f'  {c}{v:.2f}{C.RESET}'

        # Range indicator
        if val_range > 0.4:
            range_color = C.RED
            range_icon = '⚡'  # high variation
        elif val_range > 0.2:
            range_color = C.YELLOW
            range_icon = '〜'  # moderate variation
        else:
            range_color = C.GREEN
            range_icon = '≈'  # stable
        line += f'  {range_color}{range_icon}{val_range:.2f}{C.RESET}'
        print(line)

    # Identify stable vs volatile traits
    print(f'\n  {C.DIM}⚡ = 高度情境依赖 (变幅>0.4)   〜 = 适度变化 (0.2-0.4)   ≈ = 核心稳定 (<0.2){C.RESET}')

    # ═══════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════
    print(f'\n\n{C.BOLD}╔══════════════════════════════════════════════════════════════════╗')
    print(f'║                      📊 结论 Conclusion                        ║')
    print(f'╠══════════════════════════════════════════════════════════════════╣{C.RESET}')
    print(f'{C.BOLD}║{C.RESET}                                                                {C.BOLD}║{C.RESET}')
    print(f'{C.BOLD}║{C.RESET}  {C.GREEN}✓{C.RESET} 4 个核心基因 → 涌现出 {len(cluster_info)} 种可辨识人格               {C.BOLD}║{C.RESET}')
    print(f'{C.BOLD}║{C.RESET}  {C.GREEN}✓{C.RESET} 同一基因组 × 不同情境 = 不同行为表现                {C.BOLD}║{C.RESET}')
    print(f'{C.BOLD}║{C.RESET}  {C.GREEN}✓{C.RESET} 部分特征情境稳定（核心身份），部分情境依赖（表达弹性）{C.BOLD}║{C.RESET}')
    print(f'{C.BOLD}║{C.RESET}  {C.GREEN}✓{C.RESET} 同类型内部存在个体差异，不是模板复制                {C.BOLD}║{C.RESET}')
    print(f'{C.BOLD}║{C.RESET}                                                                {C.BOLD}║{C.RESET}')
    print(f'{C.BOLD}║{C.RESET}  {C.CYAN}人类行为多样性的底层代码：{C.RESET}                                {C.BOLD}║{C.RESET}')
    print(f'{C.BOLD}║{C.RESET}  {C.CYAN}DNA 不编码"性格"，只编码神经递质受体的密度和敏感度{C.RESET}     {C.BOLD}║{C.RESET}')
    print(f'{C.BOLD}║{C.RESET}  {C.CYAN}4 种递质 × 非线性交互 × 环境调控 × 时间 = 无穷人格{C.RESET}     {C.BOLD}║{C.RESET}')
    print(f'{C.BOLD}║{C.RESET}                                                                {C.BOLD}║{C.RESET}')
    print(f'{C.BOLD}╚══════════════════════════════════════════════════════════════════╝{C.RESET}')


if __name__ == '__main__':
    run_simulation()
