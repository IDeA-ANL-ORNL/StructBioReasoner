"""
Role-based Agentic System for StructBioReasoner

This package implements a sophisticated role-based agentic workflow where
specialized expert agents work together with critic agents to provide
self-improving protein engineering capabilities.

Architecture:
- Expert Agents: Specialized in specific domains (MD simulation, structure prediction, etc.)
- Critic Agents: Evaluate and provide feedback on expert agent performance
- Role Orchestrator: Manages multi-agent workflows and communication
- Performance Monitor: Tracks agent performance and improvement over time
"""

from .base_role import BaseRole, ExpertRole, CriticRole
from .md_expert import MDSimulationExpert
from .structure_expert import StructurePredictionExpert
from .md_critic import MDSimulationCritic
from .structure_critic import StructurePredictionCritic
from .role_orchestrator import RoleOrchestrator

__all__ = [
    "BaseRole",
    "ExpertRole", 
    "CriticRole",
    "MDSimulationExpert",
    "StructurePredictionExpert",
    "MDSimulationCritic",
    "StructurePredictionCritic",
    "RoleOrchestrator"
]
