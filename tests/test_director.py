"""
Tests for the Director agent and AgentRegistry.

These tests mock Academy and Parsl to test orchestration logic
without requiring the full HPC stack.
"""

from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from struct_bio_reasoner.agents.director.director_agent import (
    AgentRegistry,
    Director,
)
from struct_bio_reasoner.models import TaskName, Recommendation, RecommendationResult


# ---------------------------------------------------------------------------
# AgentRegistry
# ---------------------------------------------------------------------------

class TestAgentRegistry:
    def test_default_agents(self):
        reg = AgentRegistry()
        assert "reasoner" in reg.reasoner
        assert "bindcraft" in reg.bindcraft
        assert "MD" in reg.md or "MDAgent" in reg.md
        assert "mmpbsa" in reg.mmpbsa
        assert "chai" in reg.folding
        assert "data" in reg.data

    def test_task_to_agent_mapping(self):
        reg = AgentRegistry()
        assert reg.TASK_TO_AGENT["computational_design"] == "bindcraft"
        assert reg.TASK_TO_AGENT["molecular_dynamics"] == "md"
        assert reg.TASK_TO_AGENT["structure_prediction"] == "folding"
        assert reg.TASK_TO_AGENT["free_energy"] == "mmpbsa"
        assert reg.TASK_TO_AGENT["rag"] == "reasoner"
        assert reg.TASK_TO_AGENT["analysis"] == "reasoner"

    def test_data_not_in_task_to_agent(self):
        reg = AgentRegistry()
        assert "data" not in reg.TASK_TO_AGENT.values()

    def test_resolve_task_string(self):
        reg = AgentRegistry()
        assert reg.resolve_task("computational_design") == "bindcraft"
        assert reg.resolve_task("molecular_dynamics") == "md"
        assert reg.resolve_task("free_energy") == "mmpbsa"

    def test_resolve_task_enum(self):
        reg = AgentRegistry()
        assert reg.resolve_task(TaskName.COMPUTATIONAL_DESIGN) == "bindcraft"
        assert reg.resolve_task(TaskName.MOLECULAR_DYNAMICS) == "md"

    def test_resolve_task_unknown_returns_key(self):
        reg = AgentRegistry()
        assert reg.resolve_task("unknown_thing") == "unknown_thing"

    def test_available(self):
        reg = AgentRegistry()
        available = reg.available()
        assert "reasoner" in available
        assert "bindcraft" in available
        assert "md" in available
        assert "mmpbsa" in available
        assert "folding" in available
        assert "data" in available

    def test_is_pydantic_model(self):
        reg = AgentRegistry()
        assert isinstance(reg, BaseModel)

    def test_serialization(self):
        reg = AgentRegistry()
        data = reg.model_dump()
        reg2 = AgentRegistry(**data)
        assert reg.reasoner == reg2.reasoner
        assert reg.TASK_TO_AGENT == reg2.TASK_TO_AGENT


# ---------------------------------------------------------------------------
# Director Initialization
# ---------------------------------------------------------------------------

class TestDirectorInit:
    def test_init_with_base_compute_settings(self):
        """Director can be initialized with BaseComputeSettings."""
        from struct_bio_reasoner.utils.parsl_settings import BaseComputeSettings

        mock_settings = MagicMock(spec=BaseComputeSettings)
        mock_settings.resource_summary.return_value = "4 GPUs"

        d = Director(
            runtime_config={"director_id": "test-id"},
            parsl_config=mock_settings,
        )
        assert d._director_id == "test-id"
        assert d.resource_summary == "4 GPUs"
        assert d.previous_run == "starting"
        assert d._iteration == 0
        assert d.history == []

    def test_init_with_parsl_config_dict(self):
        """Director derives resource_summary from runtime_config['parsl']."""
        d = Director(
            runtime_config={
                "director_id": "d1",
                "parsl": {
                    "nodes": 2,
                    "available_accelerators": ["0", "1", "2", "3"],
                },
            },
            parsl_config=MagicMock(),  # not a BaseComputeSettings
        )
        assert "Nodes: 2" in d.resource_summary
        assert "Total accelerators (GPUs/tiles): 8" in d.resource_summary

    def test_init_no_parsl_dict(self):
        """Director with no parsl dict gets empty resource_summary."""
        d = Director(
            runtime_config={"director_id": "d2"},
            parsl_config=MagicMock(),
        )
        assert d.resource_summary == ""

    def test_auto_generates_director_id(self):
        d = Director(
            runtime_config={},
            parsl_config=MagicMock(),
        )
        assert d._director_id  # non-empty UUID string
        assert len(d._director_id) > 10

    def test_agent_registry_created(self):
        d = Director(
            runtime_config={},
            parsl_config=MagicMock(),
        )
        assert isinstance(d.agent_registry, AgentRegistry)


# ---------------------------------------------------------------------------
# Director._emit
# ---------------------------------------------------------------------------

class TestDirectorEmit:
    @pytest.mark.asyncio
    async def test_emit_success(self):
        d = Director(runtime_config={}, parsl_config=MagicMock())
        d.agents = {"data": AsyncMock()}
        await d._emit({"event_type": "test", "payload": {}})
        d.agents["data"].record_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_failure_logged_not_raised(self):
        d = Director(runtime_config={}, parsl_config=MagicMock())
        mock_data = AsyncMock()
        mock_data.record_event.side_effect = RuntimeError("DB error")
        d.agents = {"data": mock_data}
        # Should not raise
        await d._emit({"event_type": "test", "payload": {}})


# ---------------------------------------------------------------------------
# Director.tool_call
# ---------------------------------------------------------------------------

class TestDirectorToolCall:
    @pytest.mark.asyncio
    async def test_tool_call_with_pydantic_plan(self):
        """tool_call extracts kwargs from Pydantic plan model."""
        d = Director(runtime_config={}, parsl_config=MagicMock())

        mock_agent = AsyncMock()
        mock_agent.run.return_value = {"result": "ok"}
        mock_data = AsyncMock()

        d.agents = {"bindcraft": mock_agent, "data": mock_data}

        # Create a plan-like model
        from struct_bio_reasoner.models import (
            ComputationalDesignConfig,
            ComputationalDesignPlan,
        )
        cfg = ComputationalDesignConfig(binder_sequence="ACDEF", num_rounds=2)
        plan = ComputationalDesignPlan(new_config=cfg, rationale="test")

        result = await d.tool_call("computational_design", plan)
        assert result == {"result": "ok"}
        mock_agent.run.assert_called_once()
        call_kwargs = mock_agent.run.call_args[1]
        assert call_kwargs["binder_sequence"] == "ACDEF"
        assert call_kwargs["num_rounds"] == 2

    @pytest.mark.asyncio
    async def test_tool_call_with_dict_plan(self):
        d = Director(runtime_config={}, parsl_config=MagicMock())

        mock_agent = AsyncMock()
        mock_agent.run.return_value = {"ok": True}
        mock_data = AsyncMock()

        d.agents = {"md": mock_agent, "data": mock_data}

        plan = {
            "new_config": {
                "simulation_paths": ["/a.pdb"],
                "root_output_path": "/out",
                "steps": 10000,
            },
            "rationale": "test",
        }
        result = await d.tool_call("molecular_dynamics", plan)
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_tool_call_emits_execution_events(self):
        d = Director(runtime_config={}, parsl_config=MagicMock())

        mock_agent = AsyncMock()
        mock_agent.run.return_value = "done"
        mock_data = AsyncMock()
        d.agents = {"reasoner": mock_agent, "data": mock_data}

        await d.tool_call("rag", {"prompt": "test"})

        # Should have emitted EXECUTION_START and EXECUTION_END
        assert mock_data.record_event.call_count == 2
        calls = [c.args[0] for c in mock_data.record_event.call_args_list]
        event_types = [c["event_type"] for c in calls]
        assert "execution_start" in event_types
        assert "execution_end" in event_types

    @pytest.mark.asyncio
    async def test_tool_call_handles_failure(self):
        d = Director(runtime_config={}, parsl_config=MagicMock())

        mock_agent = AsyncMock()
        mock_agent.run.side_effect = RuntimeError("Agent crashed")
        mock_data = AsyncMock()
        d.agents = {"bindcraft": mock_agent, "data": mock_data}

        with pytest.raises(RuntimeError, match="Agent crashed"):
            await d.tool_call("computational_design", {"binder_sequence": "A"})

        # Should still emit EXECUTION_END with status=failed
        end_call = mock_data.record_event.call_args_list[-1].args[0]
        assert end_call["payload"]["status"] == "failed"
        assert "Agent crashed" in end_call["payload"]["error"]
