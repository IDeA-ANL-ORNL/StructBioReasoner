"""
Generative Design Agents for StructBioReasoner

This module contains agents that use generative models for protein design:
- RFDiffusion Agent: Uses RFDiffusion for de novo protein design
- Other generative design agents
"""

from .rfdiffusion_agent import RFDiffusionAgent

__all__ = [
    'RFDiffusionAgent'
]
