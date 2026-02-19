"""
Tests for struct_bio_reasoner.agents.data.events — WorkflowEvent, ScientificEvent, enums.
"""

from __future__ import annotations

import time

import pytest

from struct_bio_reasoner.agents.data.events import (
    EventType,
    ScientificEventType,
    WorkflowEvent,
    ScientificEvent,
)


# ---------------------------------------------------------------------------
# EventType Enum
# ---------------------------------------------------------------------------

class TestEventType:
    def test_all_members(self):
        expected = {
            "LLM_CALL", "DECISION", "PLAN",
            "EXECUTION_START", "EXECUTION_END",
            "KEY_ITEM", "EXECUTIVE_ACTION",
            "EXPERIMENT_START", "EXPERIMENT_END",
            "DIRECTOR_START", "DIRECTOR_END",
        }
        assert {m.name for m in EventType} == expected

    def test_is_str_enum(self):
        assert isinstance(EventType.DECISION, str)
        assert EventType.DECISION == "decision"

    def test_values(self):
        assert EventType.LLM_CALL.value == "llm_call"
        assert EventType.EXPERIMENT_START.value == "experiment_start"
        assert EventType.DIRECTOR_END.value == "director_end"
        assert EventType.KEY_ITEM.value == "key_item"
        assert EventType.EXECUTIVE_ACTION.value == "executive_action"


# ---------------------------------------------------------------------------
# ScientificEventType Enum
# ---------------------------------------------------------------------------

class TestScientificEventType:
    def test_all_members(self):
        expected = {
            "SEQUENCE_GENERATED", "QC_RESULT",
            "FOLDING_RESULT", "ENERGY_RESULT",
            "SIMULATION_RUN", "TRAJECTORY_ANALYSIS",
            "FREE_ENERGY_RESULT", "EMBEDDING",
        }
        assert {m.name for m in ScientificEventType} == expected

    def test_is_str_enum(self):
        assert isinstance(ScientificEventType.QC_RESULT, str)
        assert ScientificEventType.QC_RESULT == "qc_result"


# ---------------------------------------------------------------------------
# WorkflowEvent
# ---------------------------------------------------------------------------

class TestWorkflowEvent:
    def test_construction(self):
        e = WorkflowEvent(
            event_type=EventType.DECISION,
            director_id="dir_0",
            payload={"next_task": "md"},
        )
        assert e.event_type == EventType.DECISION
        assert e.director_id == "dir_0"
        assert e.payload == {"next_task": "md"}
        assert e.experiment_id == ""

    def test_to_dict(self):
        e = WorkflowEvent(
            event_type=EventType.DECISION,
            director_id="dir_0",
            payload={"next_task": "md"},
            experiment_id="exp_1",
        )
        d = e.to_dict()
        assert d["event_type"] == "decision"
        assert d["director_id"] == "dir_0"
        assert d["experiment_id"] == "exp_1"
        assert d["payload"] == {"next_task": "md"}
        assert "timestamp" in d

    def test_timestamp_default(self):
        before = time.time()
        e = WorkflowEvent(
            event_type=EventType.LLM_CALL,
            director_id="d",
            payload={},
        )
        after = time.time()
        assert before <= e.timestamp <= after

    def test_string_event_type(self):
        """Accepts raw string as event_type."""
        e = WorkflowEvent(
            event_type="decision",
            director_id="dir_0",
            payload={},
        )
        d = e.to_dict()
        assert d["event_type"] == "decision"

    def test_enum_event_type_to_dict(self):
        e = WorkflowEvent(
            event_type=EventType.PLAN,
            director_id="d",
            payload={"plan_id": "123"},
        )
        d = e.to_dict()
        assert d["event_type"] == "plan"

    def test_all_event_types_have_valid_value(self):
        for et in EventType:
            e = WorkflowEvent(
                event_type=et,
                director_id="test",
                payload={},
            )
            d = e.to_dict()
            assert d["event_type"] == et.value


# ---------------------------------------------------------------------------
# ScientificEvent
# ---------------------------------------------------------------------------

class TestScientificEvent:
    def test_construction(self):
        e = ScientificEvent(
            event_type=ScientificEventType.SEQUENCE_GENERATED,
            payload={"sequence": "ACDEF"},
        )
        assert e.event_type == ScientificEventType.SEQUENCE_GENERATED
        assert e.payload["sequence"] == "ACDEF"
        assert e.experiment_id == ""
        assert e.director_id == ""

    def test_to_dict(self):
        e = ScientificEvent(
            event_type=ScientificEventType.SEQUENCE_GENERATED,
            payload={"sequence": "ACDEF"},
            experiment_id="exp_1",
            director_id="dir_0",
        )
        d = e.to_dict()
        assert d["event_type"] == "sequence_generated"
        assert d["experiment_id"] == "exp_1"
        assert d["director_id"] == "dir_0"
        assert "timestamp" in d

    def test_timestamp_default(self):
        before = time.time()
        e = ScientificEvent(
            event_type=ScientificEventType.QC_RESULT,
            payload={},
        )
        after = time.time()
        assert before <= e.timestamp <= after

    def test_string_event_type(self):
        e = ScientificEvent(
            event_type="qc_result",
            payload={},
        )
        d = e.to_dict()
        assert d["event_type"] == "qc_result"

    def test_all_scientific_event_types(self):
        for set_ in ScientificEventType:
            e = ScientificEvent(
                event_type=set_,
                payload={"test": True},
            )
            d = e.to_dict()
            assert d["event_type"] == set_.value
