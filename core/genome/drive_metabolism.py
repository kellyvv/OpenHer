"""
DriveMetabolism — Time-aware drive metabolism engine.

Extracted from genome_v8_timearrow.py. Two core time equations:
  1. Frustration decay: frustration *= e^(-λ * Δt_hours)  (cooling off)
  2. Connection hunger: frustration += k * Δt_hours  (loneliness grows)

Also provides thermodynamic noise injection and stimulus processing.

All physical constants can be overridden per-persona via engine_params.
"""

from __future__ import annotations

import math
import random
import time

from core.genome.genome_engine import DRIVES


# ── Global defaults (used when engine_params not specified) ──
FRUSTRATION_DECAY_LAMBDA = 0.08   # Decay rate (per hour): ~8.7h half-life
CONNECTION_HUNGER_K = 0.15        # Loneliness accumulation rate (per hour)
NOVELTY_HUNGER_K = 0.05           # Boredom accumulation rate (per hour)
TEMP_COEFF = 0.12                 # Temperature coefficient
TEMP_FLOOR = 0.03                 # Temperature floor (minimum noise)


class DriveMetabolism:
    """
    Drive metabolism engine v3 (time-aware, per-persona configurable).

    Two pure physics time equations:
    1. Cooling: frustration *= e^(-λΔt) → time cools all heat
    2. Hunger: connection.f += k * Δt → loneliness grows linearly

    engine_params (all optional):
      frustration_decay, connection_hunger_k, novelty_hunger_k,
      temp_coeff, temp_floor
    """

    def __init__(self, clock=None, engine_params: dict = None):
        self.frustration = {d: 0.0 for d in DRIVES}
        self.decay_rate = 0.1  # Per-turn real-time decay
        self._last_tick = clock or time.time()

        # Per-persona overridable parameters
        params = engine_params or {}
        self.decay_lambda = params.get('frustration_decay', FRUSTRATION_DECAY_LAMBDA)
        self.connection_hunger_k = params.get('connection_hunger_k', CONNECTION_HUNGER_K)
        self.novelty_hunger_k = params.get('novelty_hunger_k', NOVELTY_HUNGER_K)
        self.temp_coeff = params.get('temp_coeff', TEMP_COEFF)
        self.temp_floor = params.get('temp_floor', TEMP_FLOOR)

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
        decay_factor = math.exp(-self.decay_lambda * delta_hours)
        for d in DRIVES:
            self.frustration[d] *= decay_factor

        # ── Hunger: linear accumulation ──
        self.frustration['connection'] += self.connection_hunger_k * delta_hours
        self.frustration['novelty'] += self.novelty_hunger_k * delta_hours

        # ── Clamp ──
        for d in DRIVES:
            self.frustration[d] = max(0.0, min(5.0, self.frustration[d]))

        return delta_hours

    def apply_llm_delta(self, delta_dict: dict) -> float:
        """
        Apply LLM-judged frustration changes (v10: replaces fixed algebraic rules).

        delta_dict: {'connection': float, 'novelty': float, ...}
            Positive = more frustrated, negative = relieved.
        Returns: reward (positive = frustration decreased = good).
        """
        old_total = self.total()

        for d in DRIVES:
            if d in delta_dict:
                self.frustration[d] += delta_dict[d]
            self.frustration[d] *= (1.0 - self.decay_rate)

        for d in DRIVES:
            self.frustration[d] = max(0.0, min(5.0, self.frustration[d]))

        return old_total - self.total()

    def total(self) -> float:
        """Total frustration across all drives."""
        return sum(self.frustration.values())

    def temperature(self) -> float:
        """Compute temperature from total frustration (tanh saturation curve).

        Linear formula caused signal destruction at high frustration:
          frust=5, coeff=0.10 → temp=0.52 → noise σ=0.52 → signals = random
        Tanh saturates: same inputs → temp≈0.26 → signals still directional.
        """
        import math
        total = self.total()
        max_temp = self.temp_coeff * 2.5  # Saturation ceiling
        return max_temp * math.tanh(total * self.temp_coeff / max_temp) + self.temp_floor

    def apply_thermodynamic_noise(self, base_signals: dict) -> dict:
        """
        Apply thermodynamic noise to signals based on total frustration.
        Higher frustration = more noise = more unpredictable behavior.
        Uses per-persona temp_coeff and temp_floor.
        """
        temp = self.temperature()
        noisy = {}
        for key, val in base_signals.items():
            noise = random.gauss(0.0, temp)
            noisy[key] = max(0.0, min(1.0, val + noise))
        return noisy

    def sync_to_agent(self, agent):
        """Sync metabolism state back to agent's drive state."""
        for d in DRIVES:
            agent.drive_state[d] = min(1.0, agent.drive_baseline.get(d, 0.5)
                                       + self.frustration[d] * 0.15)
        agent._frustration = self.total()

    def status_summary(self) -> dict:
        """Return a summary of the current drive metabolism state."""
        total = self.total()
        return {
            'frustration': dict(self.frustration),
            'total': round(total, 2),
            'temperature': round(total * self.temp_coeff + self.temp_floor, 3),
        }

    # ── Serialization ──

    def to_dict(self) -> dict:
        return {
            'frustration': dict(self.frustration),
            'decay_rate': self.decay_rate,
            '_last_tick': self._last_tick,
            'engine_params': {
                'frustration_decay': self.decay_lambda,
                'connection_hunger_k': self.connection_hunger_k,
                'novelty_hunger_k': self.novelty_hunger_k,
                'temp_coeff': self.temp_coeff,
                'temp_floor': self.temp_floor,
            },
        }

    @classmethod
    def from_dict(cls, data: dict, engine_params: dict = None) -> DriveMetabolism:
        """Restore from serialized state.

        engine_params: If provided, uses these (from persona).
                       If None, tries to restore from serialized data.
                       Falls back to global defaults.
        """
        # Prefer caller-provided params (from persona), fall back to serialized
        params = engine_params or data.get('engine_params', {})
        m = cls(clock=data.get('_last_tick'), engine_params=params)
        m.frustration = data.get('frustration', m.frustration)
        m.decay_rate = data.get('decay_rate', 0.1)
        return m


def apply_thermodynamic_noise(base_signals: dict, total_frustration: float,
                               temp_coeff: float = TEMP_COEFF,
                               temp_floor: float = TEMP_FLOOR) -> dict:
    """
    Module-level convenience function for thermodynamic noise.
    Prefer DriveMetabolism.apply_thermodynamic_noise() when instance is available.
    """
    temperature = total_frustration * temp_coeff + temp_floor
    noisy = {}
    for key, val in base_signals.items():
        noise = random.gauss(0.0, temperature)
        noisy[key] = max(0.0, min(1.0, val + noise))
    return noisy
