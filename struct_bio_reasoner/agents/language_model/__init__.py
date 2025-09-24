"""
Language Model Agents for StructBioReasoner

This module contains agents that use protein language models:
- ESM Agent: Uses ESM models for sequence analysis and prediction
- Other protein language model agents
"""

from .esm_agent import ESMAgent

__all__ = [
    'ESMAgent'
]
