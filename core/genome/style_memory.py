"""
ContinuousStyleMemory — KNN-based style memory with time-aware retrieval.

Adapted from prototypes/style_memory.py for server use.
Features:
  - 8D signal space KNN retrieval with gravitational mass weighting
  - Hawking radiation: memory mass decays exponentially over time
  - Crystallization: nearby signals merge (mass grows), distant create new memories
  - Few-shot prompt builder with mass-tagged examples
"""

from __future__ import annotations

import json
import math
import os
import time


# Signal dimension order (consistent with genome_engine.py)
SIGNAL_KEYS = [
    'directness', 'vulnerability', 'playfulness', 'initiative',
    'depth', 'warmth', 'defiance', 'curiosity',
]

# Physics constant
HAWKING_GAMMA = 0.001  # Decay rate (per hour): ~29 day half-life


def _l2_distance(vec_a, vec_b):
    """8D Euclidean distance (zero-dependency)."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(vec_a, vec_b)))


def _signals_to_vec(signals):
    """Convert signal dict to ordered vector."""
    return [signals.get(k, 0.5) for k in SIGNAL_KEYS]


def _hawking_mass(mass_raw, last_used_at, now, gamma=HAWKING_GAMMA):
    """
    Hawking radiation: memory mass decays exponentially.
    mass_eff = 1.0 + (mass_raw - 1.0) * e^(-γ * Δt_hours)
    Base mass 1.0 never decays below (innate genes don't evaporate to 0).
    """
    delta_hours = max(0.0, (now - last_used_at) / 3600.0)
    excess = max(0.0, mass_raw - 1.0)
    decayed_excess = excess * math.exp(-gamma * delta_hours)
    return 1.0 + decayed_excess


class ContinuousStyleMemory:
    """
    Continuous memory manifold engine v3 (time-arrow + Hawking radiation).

    All memories live in a single pool, no public/private distinction.
    Mass grows with crystallization, decays with time (Hawking radiation).
    Retrieval uses time-decayed effective mass (mass_eff).
    """

    def __init__(self, agent_id, db_dir=None, now=None, persona_id=None, hawking_gamma=None):
        self.agent_id = agent_id
        self.hawking_gamma = hawking_gamma if hawking_gamma is not None else HAWKING_GAMMA
        self.db_dir = db_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            ".data", "genome"
        )
        os.makedirs(self.db_dir, exist_ok=True)

        # Per-persona genesis file (genesis_kai.json) → fallback to shared bank
        if persona_id:
            persona_genesis = os.path.join(self.db_dir, f"genesis_{persona_id}.json")
            if os.path.exists(persona_genesis):
                self.genesis_file = persona_genesis
            else:
                self.genesis_file = os.path.join(self.db_dir, "genesis_bank.json")
        else:
            self.genesis_file = os.path.join(self.db_dir, "genesis_bank.json")
        self.personal_file = os.path.join(self.db_dir, f"{agent_id}_memory.json")
        self._now = now or time.time()

        # Unified memory pool
        self._pool = []
        self._genesis_count = 0
        self._personal_count = 0
        self._load()

    def set_clock(self, now):
        """Inject external clock (for testing)."""
        self._now = now

    def _load(self):
        """Load innate genes + learned experience into unified pool."""
        self._pool = []

        if os.path.exists(self.genesis_file):
            with open(self.genesis_file, 'r', encoding='utf-8') as f:
                genesis = json.load(f)
            for mem in genesis:
                mem.setdefault('mass', 1.0)
                mem.setdefault('created_at', 0.0)
                mem.setdefault('last_used_at', 0.0)
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
        Gravitational mass + Hawking radiation retrieval.
        effective_distance = physical_distance / √mass_eff
        """
        target = _signals_to_vec(current_signals)
        now = self._now
        scored = []

        for mem in self._pool:
            physical_dist = _l2_distance(target, mem['vector'])
            mass_raw = mem.get('mass', 1.0)
            last_used = mem.get('last_used_at', 0.0)

            mass_eff = _hawking_mass(mass_raw, last_used, now, gamma=self.hawking_gamma)
            effective_dist = physical_dist / math.sqrt(max(mass_eff, 0.01))

            scored.append((effective_dist, physical_dist, mass_eff, mass_raw, mem))

        scored.sort(key=lambda x: x[0])

        results = []
        for eff_dist, phys_dist, mass_eff, mass_raw, mem in scored[:top_k]:
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
        Memory crystallization (time-aware).
        Nearby signals → gravitational thickening + refresh timestamp.
        New signals → create new memory with initial mass=2.0.
        """
        new_vec = [round(v, 4) for v in _signals_to_vec(signals)]
        now = self._now

        # Check if we can merge
        best_idx = -1
        best_dist = 999.0
        for i, mem in enumerate(self._pool):
            d = _l2_distance(new_vec, mem['vector'])
            if d < best_dist:
                best_dist = d
                best_idx = i

        if best_dist < 0.25 and best_idx >= 0:
            # Gravitational thickening: increase mass + refresh timestamp
            # but KEEP original content (don't overwrite distinctive memories)
            self._pool[best_idx]['mass'] = self._pool[best_idx].get('mass', 1.0) + 1.0
            self._pool[best_idx]['last_used_at'] = now
            # Only overwrite if new content is longer (richer)
            if len(reply) > len(self._pool[best_idx].get('reply', '')):
                self._pool[best_idx]['monologue'] = monologue
                self._pool[best_idx]['reply'] = reply
                self._pool[best_idx]['user_input'] = user_input
        else:
            # New memory
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

        # Save personal memories
        personal_mems = [m for m in self._pool if m.get('mass', 1.0) > 1.0]
        self._personal_count = len(personal_mems)

        with open(self.personal_file, 'w', encoding='utf-8') as f:
            json.dump(personal_mems, f, ensure_ascii=False, indent=2)

        return self._personal_count

    def build_few_shot_prompt(self, current_signals, top_k=3):
        """Build few-shot prompt from retrieval results (with mass tags)."""
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
        """Return memory statistics (with Hawking radiation-decayed mass)."""
        now = self._now
        masses_raw = [m.get('mass', 1.0) for m in self._pool]
        masses_eff = [
            _hawking_mass(m.get('mass', 1.0), m.get('last_used_at', 0.0), now, gamma=self.hawking_gamma)
            for m in self._pool
        ]
        return {
            'genesis_count': self._genesis_count,
            'personal_count': self._personal_count,
            'total': self.total_memories,
            'total_mass_raw': sum(masses_raw),
            'total_mass_eff': round(sum(masses_eff), 1),
        }
