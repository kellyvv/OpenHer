"""
ContinuousStyleMemory — KNN-based style memory with time-aware retrieval.

Adapted from prototypes/style_memory.py for server use.
Features:
  - Context-space KNN retrieval with gravitational mass weighting
  - Hawking radiation: memory mass decays exponentially over time
  - Crystallization: nearby contexts merge (mass grows), distant create new memories
  - Few-shot prompt builder with mass-tagged examples
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import time


# Context dimension order (Critic output keys, used for KNN retrieval)
CONTEXT_KEYS = [
    'conflict_level', 'user_emotion', 'user_engagement', 'user_vulnerability',
    'topic_intimacy', 'conversation_depth', 'novelty_level', 'time_of_day',
]

# Physics constant
HAWKING_GAMMA = 0.001  # Decay rate (per hour): ~29 day half-life


def _l2_distance(vec_a, vec_b):
    """Euclidean distance (zero-dependency)."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(vec_a, vec_b)))


def _context_to_vec(context):
    """Convert Critic context dict to ordered vector for KNN retrieval."""
    return [context.get(k, 0.0) for k in CONTEXT_KEYS]


def clean_action_markers(text: str) -> str:
    """Remove action/emotion stage directions from text.

    Strips *action*, ＊action＊, （action）, (action), 「action」 patterns
    in both Chinese and English, full-width and half-width.
    """
    text = re.sub(r'\*[^*]+\*', '', text)       # *sighs*  *顿了顿*
    text = re.sub(r'＊[^＊]+＊', '', text)         # ＊轻笑＊  full-width asterisk
    text = re.sub(r'（[^）]+）', '', text)         # （沉默）  full-width parens
    text = re.sub(r'\([^)]+\)', '', text)        # (pauses) half-width parens
    text = re.sub(r'「[^」]+」', '', text)         # 「沉默」  occasional
    return re.sub(r'\s{2,}', ' ', text).strip()


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

    def __init__(self, agent_id, db_dir=None, now=None, persona_id=None, hawking_gamma=None,
                 state_db_path=None):
        self.agent_id = agent_id
        self.hawking_gamma = hawking_gamma if hawking_gamma is not None else HAWKING_GAMMA
        self.db_dir = db_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            ".data", "genome"
        )
        os.makedirs(self.db_dir, exist_ok=True)

        self._persona_id = persona_id or agent_id

        # Derive user_id from agent_id (format: "{persona_id}_{user_id}")
        if persona_id and agent_id.startswith(persona_id + "_"):
            self._user_id = agent_id[len(persona_id) + 1:]
        else:
            self._user_id = agent_id

        # SQLite for personal memories (fallback to JSON for backward compat)
        self._state_db_path = state_db_path or os.path.join(
            os.path.dirname(self.db_dir), "openher.db"
        )
        self._init_db()

        self._now = now or time.time()

        # Unified memory pool
        self._pool = []
        self._genesis_count = 0
        self._personal_count = 0
        self._load()

    def set_clock(self, now):
        """Inject external clock (for testing)."""
        self._now = now

    def _init_db(self):
        """Create style_memory and genesis_seed tables if not exists."""
        conn = sqlite3.connect(self._state_db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS style_memory (
                persona_id TEXT NOT NULL,
                user_id    TEXT NOT NULL,
                memories   TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (persona_id, user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS genesis_seed (
                persona_id TEXT PRIMARY KEY,
                seeds      TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def _load(self):
        """Load innate genes + learned experience into unified pool."""
        self._pool = []

        # Genesis from SQLite genesis_seed table
        conn = sqlite3.connect(self._state_db_path)
        row = conn.execute(
            "SELECT seeds FROM genesis_seed WHERE persona_id = ?",
            (self._persona_id,)
        ).fetchone()
        conn.close()

        if row:
            genesis = json.loads(row[0])
            for mem in genesis:
                mem.setdefault('mass', 1.0)
                mem.setdefault('created_at', 0.0)
                mem.setdefault('last_used_at', 0.0)
                self._pool.append(mem)
            self._genesis_count = len(genesis)

        # Personal memories from SQLite
        conn = sqlite3.connect(self._state_db_path)
        row = conn.execute(
            "SELECT memories FROM style_memory WHERE persona_id = ? AND user_id = ?",
            (self._persona_id, self._user_id)
        ).fetchone()
        conn.close()

        if row:
            personal = json.loads(row[0])
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

    def retrieve(self, context, top_k=3, lang_preference=None):
        """
        Gravitational mass + Hawking radiation retrieval.
        effective_distance = physical_distance / √mass_eff

        lang_preference: 'zh' or 'en'. When set, same-language seeds get
        a soft distance bonus (cross-language seeds penalized 25%).
        Language is auto-detected from monologue text.
        """
        target = _context_to_vec(context)
        now = self._now
        scored = []

        for mem in self._pool:
            # Hard language filter: skip cross-language seeds
            if lang_preference and mem.get('lang') and mem['lang'] != lang_preference:
                continue

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
                'lang': mem.get('lang', ''),
            })

        return results

    def crystallize(self, context, monologue, reply, user_input=""):
        """
        Memory crystallization (time-aware).
        Nearby contexts → gravitational thickening + refresh timestamp.
        New contexts → create new memory with initial mass=2.0.
        """
        new_vec = [round(v, 4) for v in _context_to_vec(context)]
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

        # Save personal memories to SQLite
        personal_mems = [m for m in self._pool if m.get('mass', 1.0) > 1.0]
        self._personal_count = len(personal_mems)

        conn = sqlite3.connect(self._state_db_path)
        conn.execute("""
            INSERT INTO style_memory (persona_id, user_id, memories, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(persona_id, user_id) DO UPDATE SET
                memories = excluded.memories,
                updated_at = excluded.updated_at
        """, (
            self._persona_id,
            self._user_id,
            json.dumps(personal_mems, ensure_ascii=False),
            self._now,
        ))
        conn.commit()
        conn.close()

        return self._personal_count

    def build_few_shot_prompt(self, context, top_k=3, monologue_only=False, lang='zh'):
        """Build few-shot prompt from retrieval results (with mass tags).

        Args:
            context: Critic context dict for KNN retrieval.
            monologue_only: If True, only include monologue (no reply).
                            Used by Pass 1 (Feel) of two-pass Actor.
            lang: Label language ('zh' or 'en').
        """
        memories = self.retrieve(context, top_k=top_k, lang_preference=lang)

        is_en = lang == 'en'
        if not memories:
            if monologue_only:
                return "（System: no inner feeling fragments available）" if is_en else "（系统：无可用的内心感受片段）"
            return "（System: no subconscious slices available）" if is_en else "（系统：无可用的潜意识切片）"

        parts = []
        for i, mem in enumerate(memories):
            mass_eff = mem.get('mass_eff', 1.0)
            mass_raw = mem.get('mass_raw', 1.0)
            if mass_raw > 1.0:
                mass_tag = f"mass={mass_eff:.1f}/{mass_raw:.0f}" if is_en else f"质量={mass_eff:.1f}/{mass_raw:.0f}"
            else:
                mass_tag = "genesis" if is_en else "基因"
            if monologue_only:
                frag_label = "Inner thought fragment" if is_en else "内心念头片段"
                parts.append(
                    f"--- {frag_label} {i+1} [{mass_tag}] ---\n"
                    f"{mem['monologue']}"
                )
            else:
                slice_label = "Subconscious slice" if is_en else "潜意识切片"
                parts.append(
                    f"--- {slice_label} {i+1} [{mass_tag}] ---\n"
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

    @staticmethod
    def save_genesis_to_db(persona_id: str, seeds: list, db_path: str):
        """Save genesis seeds to DB (used by calibrate and migration scripts).

        Cleans action markers from monologue/reply before storing.
        Upserts: existing data for the same persona_id will be replaced.
        """
        for seed in seeds:
            if 'monologue' in seed:
                seed['monologue'] = clean_action_markers(seed['monologue'])
            if 'reply' in seed:
                seed['reply'] = clean_action_markers(seed['reply'])

        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS genesis_seed (
                persona_id TEXT PRIMARY KEY,
                seeds      TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO genesis_seed (persona_id, seeds, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(persona_id) DO UPDATE SET
                seeds = excluded.seeds,
                created_at = excluded.created_at
        """, (persona_id, json.dumps(seeds, ensure_ascii=False), time.time()))
        conn.commit()
        conn.close()
