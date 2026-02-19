"""
Data Agent Package

Provides the DataAgent for managing persistence of both
decision/LLM history and scientific pipeline data via SQLAlchemy ORM.
Supports PostgreSQL (asyncpg) in production and SQLite (aiosqlite) for tests.
"""

from .data_agent import DataAgent
from .events import EventType, WorkflowEvent, ScientificEventType, ScientificEvent
from .models import Base

__all__ = [
    'DataAgent',
    'EventType',
    'WorkflowEvent',
    'ScientificEventType',
    'ScientificEvent',
    'Base',
]
