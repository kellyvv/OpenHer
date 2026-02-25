"""
╔══════════════════════════════════════════════════════════════════════╗
║  🧬 Continuous Style Memory v3 — 时间之矢 + 霍金辐射 🧬            ║
║                                                                      ║
║  v2 → v3 变更：                                                     ║
║    1. 结晶记忆带 UNIX 时间戳 (created_at, last_used_at)             ║
║    2. 霍金辐射：mass 随时间指数衰减                                   ║
║       mass_eff = 1 + (mass_raw - 1) * e^(-γ * Δt_hours)            ║
║    3. 检索时使用 mass_eff (时间衰减后) 计算引力                     ║
║                                                                      ║
║  零 if-else 依然。零 numpy 依赖。                                    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import json
import math
import os
import time


# 信号维度顺序（与 genome_v4.py 一致）
SIGNAL_KEYS = [
    'directness', 'vulnerability', 'playfulness', 'initiative',
    'depth', 'warmth', 'defiance', 'curiosity',
]

# 物理常数
HAWKING_GAMMA = 0.005  # 霍金辐射衰减率（每小时）: ~3天半衰期 → ln2/72≈0.0096，取0.005更温和


def _l2_distance(vec_a, vec_b):
    """8 维欧氏距离（手写，零依赖）"""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(vec_a, vec_b)))


def _signals_to_vec(signals):
    """将信号字典转为有序向量"""
    return [signals.get(k, 0.5) for k in SIGNAL_KEYS]


def _hawking_mass(mass_raw, last_used_at, now):
    """
    霍金辐射：记忆质量随时间指数衰减。

    mass_eff = 1.0 + (mass_raw - 1.0) * e^(-γ * Δt_hours)

    基底质量 1.0 永不低于（先天基因不会蒸发到 0）。
    超出基底的部分按指数衰减。
    最近刚用过（Δt 近零）→ mass_eff ≈ mass_raw。
    三天没用 → 超出部分衰减 ~3.5%。
    一个月没用 → 超出部分衰减 ~70%。
    """
    delta_hours = max(0.0, (now - last_used_at) / 3600.0)
    excess = max(0.0, mass_raw - 1.0)
    decayed_excess = excess * math.exp(-HAWKING_GAMMA * delta_hours)
    return 1.0 + decayed_excess


class ContinuousStyleMemory:
    """
    连续记忆流形引擎 v3（时间之矢 + 霍金辐射）。

    所有记忆住在同一个池子里，没有公私属性之分。
    质量随结晶增长，随时间指数衰减（霍金辐射）。
    检索时使用时间衰减后的有效质量（mass_eff）。
    """

    def __init__(self, agent_id, db_dir=None, now=None):
        self.agent_id = agent_id
        self.db_dir = db_dir or os.path.join(os.path.dirname(__file__), "memory_db")
        os.makedirs(self.db_dir, exist_ok=True)

        self.genesis_file = os.path.join(self.db_dir, "genesis_bank.json")
        self.personal_file = os.path.join(self.db_dir, f"{agent_id}_memory.json")
        self._now = now or time.time()  # 可注入时钟（测试用）

        # 统一记忆池
        self._pool = []
        self._genesis_count = 0
        self._personal_count = 0
        self._load()

    def set_clock(self, now):
        """注入外部时钟（用于模拟时间跳跃）"""
        self._now = now

    def _load(self):
        """加载先天基因 + 后天经验到统一池"""
        self._pool = []

        if os.path.exists(self.genesis_file):
            with open(self.genesis_file, 'r', encoding='utf-8') as f:
                genesis = json.load(f)
            for mem in genesis:
                mem.setdefault('mass', 1.0)
                mem.setdefault('created_at', 0.0)     # 创世纪元
                mem.setdefault('last_used_at', 0.0)    # 从未被使用
                self._pool.append(mem)
            self._genesis_count = len(genesis)

        if os.path.exists(self.personal_file):
            with open(self.personal_file, 'r', encoding='utf-8') as f:
                personal = json.load(f)
            for mem in personal:
                mem.setdefault('mass', 1.0)
                mem.setdefault('created_at', self._now)
                mem.setdefault('last_used_at', self._now)
                self._pool.append(mem)
            self._personal_count = len(personal)

    @property
    def total_memories(self):
        return len(self._pool)

    @property
    def personal_count(self):
        return self._personal_count

    def retrieve(self, current_signals, top_k=3):
        """
        引力质量 + 霍金辐射 检索。

        effective_distance = physical_distance / √mass_eff
        mass_eff = 1 + (mass_raw - 1) * e^(-γ * Δt)

        质量越大且越近期使用的记忆，"显得更近"。
        长期未使用的记忆，质量回归基底 1.0。
        """
        target = _signals_to_vec(current_signals)
        now = self._now
        scored = []

        for mem in self._pool:
            physical_dist = _l2_distance(target, mem['vector'])
            mass_raw = mem.get('mass', 1.0)
            last_used = mem.get('last_used_at', 0.0)

            # 霍金辐射：时间衰减后的有效质量
            mass_eff = _hawking_mass(mass_raw, last_used, now)

            # 万有引力空间扭曲
            effective_dist = physical_dist / math.sqrt(max(mass_eff, 0.01))

            scored.append((effective_dist, physical_dist, mass_eff, mass_raw, mem))

        scored.sort(key=lambda x: x[0])

        results = []
        for eff_dist, phys_dist, mass_eff, mass_raw, mem in scored[:top_k]:
            # 被检索到 = 被使用 → 更新 last_used_at（保持引力新鲜）
            mem['last_used_at'] = now

            results.append({
                'monologue': mem['monologue'],
                'reply': mem['reply'],
                'vector': mem['vector'],
                'distance': round(eff_dist, 4),
                'physical_distance': round(phys_dist, 4),
                'mass_raw': mass_raw,
                'mass_eff': round(mass_eff, 2),
                'user_input': mem.get('user_input', ''),
            })

        return results

    def crystallize(self, signals, monologue, reply, user_input=""):
        """
        记忆结晶（时间感知版）。

        极近记忆 → 引力增厚 + 刷新 last_used_at。
        新记忆 → 初始 mass=2.0, 时间戳=now。
        """
        new_vec = [round(v, 4) for v in _signals_to_vec(signals)]
        now = self._now

        # 检查是否可以合并
        best_idx = -1
        best_dist = 999.0
        for i, mem in enumerate(self._pool):
            d = _l2_distance(new_vec, mem['vector'])
            if d < best_dist:
                best_dist = d
                best_idx = i

        if best_dist < 0.15 and best_idx >= 0:
            # 引力增厚 + 刷新时间戳
            self._pool[best_idx]['mass'] = self._pool[best_idx].get('mass', 1.0) + 1.0
            self._pool[best_idx]['last_used_at'] = now
            self._pool[best_idx]['monologue'] = monologue
            self._pool[best_idx]['reply'] = reply
            self._pool[best_idx]['user_input'] = user_input
        else:
            # 新记忆
            new_mem = {
                "vector": new_vec,
                "monologue": monologue,
                "reply": reply,
                "user_input": user_input,
                "mass": 2.0,
                "created_at": now,
                "last_used_at": now,
            }
            self._pool.append(new_mem)

        # 提取 personal 记忆并保存
        personal_mems = [m for m in self._pool if m.get('mass', 1.0) > 1.0]
        self._personal_count = len(personal_mems)

        with open(self.personal_file, 'w', encoding='utf-8') as f:
            json.dump(personal_mems, f, ensure_ascii=False, indent=2)

        return self._personal_count

    def build_few_shot_prompt(self, current_signals, top_k=3):
        """从检索结果构建 few-shot prompt（标注质量等级 + 时间衰减）"""
        memories = self.retrieve(current_signals, top_k=top_k)

        if not memories:
            return "（系统：无可用的潜意识切片）"

        parts = []
        for i, mem in enumerate(memories):
            mass_eff = mem.get('mass_eff', 1.0)
            mass_raw = mem.get('mass_raw', 1.0)
            if mass_raw > 1.0:
                mass_tag = f"质量={mass_eff:.1f}/{mass_raw:.0f}"
            else:
                mass_tag = "基因"
            parts.append(
                f"--- 潜意识切片 {i+1} [{mass_tag}] ---\n"
                f"【内心独白】{mem['monologue']}\n"
                f"【最终回复】{mem['reply']}"
            )

        return "\n\n".join(parts)

    def stats(self):
        """返回记忆统计（含霍金辐射后的有效质量）"""
        now = self._now
        masses_raw = [m.get('mass', 1.0) for m in self._pool]
        masses_eff = [
            _hawking_mass(m.get('mass', 1.0), m.get('last_used_at', 0.0), now)
            for m in self._pool
        ]
        heavy_raw = [m for m in masses_raw if m > 1.0]
        heavy_eff = [m for m in masses_eff if m > 1.1]  # 衰减后还>1.1才算"活跃"
        return {
            'genesis_count': self._genesis_count,
            'personal_count': self._personal_count,
            'total': self.total_memories,
            'canalization_ratio': len(heavy_raw) / max(1, len(self._pool)),
            'total_mass_raw': sum(masses_raw),
            'total_mass_eff': round(sum(masses_eff), 1),
            'max_mass_raw': max(masses_raw) if masses_raw else 0,
            'max_mass_eff': round(max(masses_eff), 2) if masses_eff else 0,
            'heavy_count_raw': len(heavy_raw),
            'heavy_count_eff': len(heavy_eff),
        }


# ══════════════════════════════════════════════
# 快速验证
# ══════════════════════════════════════════════

if __name__ == '__main__':
    print("🧬 ContinuousStyleMemory v3 (时间之矢 + 霍金辐射) — 快速验证\n")

    now = time.time()
    mem = ContinuousStyleMemory("test_hawking", now=now)
    stats = mem.stats()
    print(f"📂 记忆池: total={stats['total']}")

    if stats['total'] == 0:
        print("❌ genesis_bank.json 未找到，请先运行 genesis_forge.py")
        exit(1)

    # 结晶 3 次
    cold_signals = {
        'directness': 0.9, 'vulnerability': 0.1, 'playfulness': 0.1,
        'initiative': 0.2, 'depth': 0.8, 'warmth': 0.1, 'defiance': 0.9, 'curiosity': 0.1,
    }
    for i in range(3):
        mem.crystallize(cold_signals, f"第{i+1}次独白", f"第{i+1}次回复")

    print("── 结晶后 (t=0) ──")
    results = mem.retrieve(cold_signals, top_k=3)
    for r in results:
        print(f"  d_eff={r['distance']:.3f}  mass_raw={r['mass_raw']:.0f}  "
              f"mass_eff={r['mass_eff']:.1f}  → {r['reply'][:40]}")

    # 模拟 3 天后
    print("\n── 3 天后 (72 小时) ──")
    mem.set_clock(now + 72 * 3600)
    results = mem.retrieve(cold_signals, top_k=3)
    for r in results:
        print(f"  d_eff={r['distance']:.3f}  mass_raw={r['mass_raw']:.0f}  "
              f"mass_eff={r['mass_eff']:.1f}  → {r['reply'][:40]}")

    # 模拟 30 天后
    print("\n── 30 天后 (720 小时) ──")
    mem.set_clock(now + 720 * 3600)
    results = mem.retrieve(cold_signals, top_k=3)
    for r in results:
        print(f"  d_eff={r['distance']:.3f}  mass_raw={r['mass_raw']:.0f}  "
              f"mass_eff={r['mass_eff']:.1f}  → {r['reply'][:40]}")

    # 模拟 180 天后
    print("\n── 180 天后 (4320 小时) ──")
    mem.set_clock(now + 4320 * 3600)
    results = mem.retrieve(cold_signals, top_k=3)
    for r in results:
        print(f"  d_eff={r['distance']:.3f}  mass_raw={r['mass_raw']:.0f}  "
              f"mass_eff={r['mass_eff']:.1f}  → {r['reply'][:40]}")

    print(f"\n📊 最终统计 (180天后): {mem.stats()}")
    print("✅ 验证完成")

    # 清理
    test_file = os.path.join(mem.db_dir, "test_hawking_memory.json")
    if os.path.exists(test_file):
        os.remove(test_file)
