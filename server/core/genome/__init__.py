"""
Genome v8 Engine — Core personality engine package.

Provides the living personality system based on:
  - Random neural network with Hebbian learning (Agent)
  - Drive metabolism with time-arrow physics (DriveMetabolism)
  - LLM Critic perception (critic_sense)
  - KNN style memory with Hawking radiation (ContinuousStyleMemory)
"""

from core.genome.genome_engine import Agent, DRIVES, SIGNALS, SIGNAL_LABELS, DRIVE_LABELS
from core.genome.drive_metabolism import DriveMetabolism, apply_thermodynamic_noise
from core.genome.critic import critic_sense, build_context_from_critic
from core.genome.style_memory import ContinuousStyleMemory

__all__ = [
    'Agent', 'DRIVES', 'SIGNALS', 'SIGNAL_LABELS', 'DRIVE_LABELS',
    'DriveMetabolism', 'apply_thermodynamic_noise',
    'critic_sense', 'build_context_from_critic',
    'ContinuousStyleMemory',
]
