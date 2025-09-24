"""
Structure Prediction Agents for StructBioReasoner

This module contains agents that use structure prediction tools:
- AlphaFold Agent: Uses AlphaFold for structure prediction and analysis
- Other structure prediction agents
"""

from .alphafold_agent import AlphaFoldAgent

__all__ = [
    'AlphaFoldAgent'
]
