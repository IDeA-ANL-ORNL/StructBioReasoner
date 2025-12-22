"""
Manager Agent Package

This package contains the Manager Agent for hierarchical multi-agent workflows.
The Manager Agent coordinates binder design campaigns and makes tactical
decisions about task sequencing. It receives and acts on executive advice.
"""

from .manager_agent import ManagerAgent, AdviceType

__all__ = ['ManagerAgent', 'AdviceType']

