"""
Executive Agent Package

This package contains the Executive Agent for hierarchical multi-agent workflows.
The Executive Agent makes strategic decisions about resource allocation and
Manager lifecycle.
"""

from .simple_executive import Executive
from .test_executive import TestExecutive

__all__ = ['Executive', 'TestExecutive']

