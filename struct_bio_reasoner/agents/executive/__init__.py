"""
Executive Agent Package

This package contains the Executive Agent for hierarchical multi-agent workflows.
The Executive Agent makes strategic decisions about resource allocation and
Manager lifecycle.
"""

from .executive_agent import ExecutiveAgent, ExecutiveActionType

__all__ = ['ExecutiveAgent', 'ExecutiveActionType']

