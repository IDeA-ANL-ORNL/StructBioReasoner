"""
Computational Design Agents for StructBioReasoner

This module contains agents that use computational design tools:
- Rosetta Agent: Uses Rosetta for protein design and optimization
- Other computational design agents
"""

from .rosetta_agent import RosettaAgent

__all__ = [
    'RosettaAgent'
]
