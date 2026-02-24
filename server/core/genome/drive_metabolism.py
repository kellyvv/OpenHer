"""
DriveMetabolism — Time-aware drive metabolism engine.

Extracted from genome_v8_timearrow.py. Two core time equations:
  1. Frustration decay: frustration *= e^(-λ * Δt_hours)  (cooling off)
  2. Connection hunger: frustration += k * Δt_hours  (loneliness grows)

Also provides thermodynamic noise injection and stimulus processing.
"""

from __future__ import annotations

import math
import random
import time

from core.genome.genome_engine import DRIVES


# Physical constants
FRUSTRATION_DECAY_LAMBDA = 0.08   # Decay rate (per hour): ~8.7h half-life
CONNECTION_HUNGER_K = 0.15        # Loneliness accumulation rate (per hour)
NOVELTY_HUNGER_K = 0.05           # Boredom accumulation rate (per hour)


class DriveMetabolism:
    """
    Drive metabolism engine v3 (time-aware).

    Two pure physics time equations:
    1. Cooling: frustration *= e^(-λΔt) → time cools all heat
    2. Hunger: connection.f += k * Δt → loneliness grows linearly
    """

    def __init__(self, clock=None):
        self.frustration = {d: 0.0 for d in DRIVES}
        self.decay_rate = 0.1  # Per-turn real-time decay
        self._last_tick = clock or time.time()

    def time_metabolism(self, now=None):
        """
        Time-arrow metabolism (two equations).

        Between interactions, physical time automatically changes drive state:
        - Cooling: all frustration decays exponentially
        - Hunger: connection and novelty grow linearly
        """
        if now is None:
            now = time.time()

        delta_hours = max(0.0, (now - self._last_tick) / 3600.0)
        self._last_tick = now

        if delta_hours < 0.001:
            return delta_hours  # Skip for sub-second intervals

        # ── Cooling: e^(-λΔt) ──
        decay_factor = math.exp(-FRUSTRATION_DECAY_LAMBDA * delta_hours)
        for d in DRIVES:
            self.frustration[d] *= decay_factor

        # ── Hunger: linear accumulation ──
        self.frustration['connection'] += CONNECTION_HUNGER_K * delta_hours
        self.frustration['novelty'] += NOVELTY_HUNGER_K * delta_hours

        # ── Clamp ──
        for d in DRIVES:
            self.frustration[d] = max(0.0, min(5.0, self.frustration[d]))

        return delta_hours

    def process_stimulus(self, critic_json: dict) -> float:
        """
        Process Critic output → update drives → return reward.

        critic_json: {'affiliation': float, 'dominance': float, 'entropy': float}
        """
        a = critic_json.get('affiliation', 0.5)
        d = critic_json.get('dominance', 0.3)
        e = critic_json.get('entropy', 0.5)

        old_total = self.total()

        self.frustration['connection'] -= a * 2.0
        self.frustration['connection'] += d * 0.8
        self.frustration['safety'] += d * 1.5
        self.frustration['safety'] -= a * 0.5
        self.frustration['novelty'] += (0.5 - e) * 3.0
        self.frustration['expression'] += d * 1.0
        self.frustration['expression'] -= a * 0.8
        self.frustration['play'] += (0.4 - e) * 2.0

        for dr in DRIVES:
            self.frustration[dr] *= (1.0 - self.decay_rate)

        for dr in DRIVES:
            self.frustration[dr] = max(0.0, min(5.0, self.frustration[dr]))

        new_total = self.total()
        return old_total - new_total  # Positive = frustration decreased = good

    def total(self) -> float:
        """Total frustration across all drives."""
        return sum(self.frustration.values())

    def sync_to_agent(self, agent):
        """Sync metabolism state back to agent's drive state."""
        for d in DRIVES:
            agent.drive_state[d] = min(1.0, agent.drive_baseline.get(d, 0.5)
                                       + self.frustration[d] * 0.15)
        agent._frustration = self.total()

    def status_summary(self) -> dict:
        """Return a summary of the current drive metabolism state."""
        return {
            'frustration': dict(self.frustration),
            'total': round(self.total(), 2),
            'temperature': round(self.total() * 0.05, 3),
        }

    # ── Serialization ──

    def to_dict(self) -> dict:
        return {
            'frustration': dict(self.frustration),
            'decay_rate': self.decay_rate,
            '_last_tick': self._last_tick,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DriveMetabolism:
        m = cls(clock=data.get('_last_tick'))
        m.frustration = data.get('frustration', m.frustration)
        m.decay_rate = data.get('decay_rate', 0.1)
        return m


def apply_thermodynamic_noise(base_signals: dict, total_frustration: float) -> dict:
    """
    Apply thermodynamic noise to signals based on total frustration.
    Higher frustration = more noise = more unpredictable behavior.
    """
    temperature = total_frustration * 0.05
    noisy = {}
    for key, val in base_signals.items():
        noise = random.gauss(0.0, temperature)
        noisy[key] = max(0.0, min(1.0, val + noise))
    return noisy
