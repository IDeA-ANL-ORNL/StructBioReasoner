"""
Structured event types emitted by agents and consumed by the DataAgent.

Two families of events:
  - WorkflowEvent / EventType: decision-level events
  - ScientificEvent / ScientificEventType: scientific data events

Both event families are persisted to a single database via SQLAlchemy ORM.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Decision / LLM History Events
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    LLM_CALL = "llm_call"
    DECISION = "decision"
    PLAN = "plan"
    EXECUTION_START = "execution_start"
    EXECUTION_END = "execution_end"
    KEY_ITEM = "key_item"
    EXECUTIVE_ACTION = "executive_action"
    EXPERIMENT_START = "experiment_start"
    EXPERIMENT_END = "experiment_end"
    DIRECTOR_START = "director_start"
    DIRECTOR_END = "director_end"


@dataclass
class WorkflowEvent:
    """A single decision-level event to be persisted."""

    event_type: EventType
    director_id: str
    payload: dict[str, Any]
    experiment_id: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value
                if isinstance(self.event_type, EventType)
                else self.event_type,
            "director_id": self.director_id,
            "experiment_id": self.experiment_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Scientific Data Events
# ---------------------------------------------------------------------------

class ScientificEventType(str, Enum):
    SEQUENCE_GENERATED = "sequence_generated"
    QC_RESULT = "qc_result"
    FOLDING_RESULT = "folding_result"
    ENERGY_RESULT = "energy_result"
    SIMULATION_RUN = "simulation_run"
    TRAJECTORY_ANALYSIS = "trajectory_analysis"
    FREE_ENERGY_RESULT = "free_energy_result"
    EMBEDDING = "embedding"


@dataclass
class ScientificEvent:
    """A single scientific data event to be persisted."""

    event_type: ScientificEventType
    payload: dict[str, Any]
    experiment_id: str = ""
    director_id: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value
                if isinstance(self.event_type, ScientificEventType)
                else self.event_type,
            "experiment_id": self.experiment_id,
            "director_id": self.director_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }
