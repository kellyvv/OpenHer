"""
Genome v10 Hybrid Engine — Core personality engine package.

Provides the living personality system based on:
  - Random neural network with Hebbian learning (Agent)
  - Drive metabolism with time-arrow physics (DriveMetabolism)
  - LLM Critic perception: 8D context + frustration delta (critic_sense)
  - KNN style memory with Hawking radiation (ContinuousStyleMemory)
"""

from core.genome.genome_engine import Agent, DRIVES, SIGNALS, SIGNAL_LABELS, DRIVE_LABELS
from core.genome.drive_metabolism import DriveMetabolism, apply_thermodynamic_noise
from core.genome.critic import critic_sense
from core.genome.style_memory import ContinuousStyleMemory

__all__ = [
    'Agent', 'DRIVES', 'SIGNALS', 'SIGNAL_LABELS', 'DRIVE_LABELS',
    'DriveMetabolism', 'apply_thermodynamic_noise',
    'critic_sense',
    'ContinuousStyleMemory',
]
