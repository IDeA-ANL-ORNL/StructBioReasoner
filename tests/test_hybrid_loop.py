"""Tests for the Wave 3 hybrid integration — 4-layer loop.

Tests the full cycle:
    Jnana.set_research_goal() → recommend_next_action() → OpenClaw skill
    selection → Academy dispatch → Artifact DAG → Jnana evaluation →
    convergence check

All LLM-calling methods are mocked (no API key needed).
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import importlib.util
import sys

from skills._shared.artifact import ArtifactMetadata, ArtifactType, create_artifact
from skills._shared.artifact_dag import ArtifactDAG
from skills._shared.artifact_store import ArtifactStore

# skills/jnana-reasoning uses a hyphen — can't be imported as a normal package.
# Load the module from its file path.
_reason_path = str(Path(__file__).resolve().parent.parent / "skills" / "jnana-reasoning" / "scripts" / "reason.py")
_spec = importlib.util.spec_from_file_location("_jnana_reason", _reason_path)
_reason_mod = importlib.util.module_from_spec(_spec)
sys.modules["_jnana_reason"] = _reason_mod
_spec.loader.exec_module(_reason_mod)

BoundedConfig = _reason_mod.BoundedConfig
Evaluation = _reason_mod.Evaluation
JnanaReasoningBridge = _reason_mod.JnanaReasoningBridge
PlanConfig = _reason_mod.PlanConfig
Recommendation = _reason_mod.Recommendation

from struct_bio_reasoner.mcp.server import StructBioReasonerMCPServer, create_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bridge(tmp_path: Path) -> JnanaReasoningBridge:
    """Create a JnanaReasoningBridge with a temp artifact store and no LLM."""
    return JnanaReasoningBridge(
        artifact_store_root=str(tmp_path / "artifacts"),
        llm_provider="openai",
    )


def _mock_llm_json_call(bridge: JnanaReasoningBridge, responses: List[Dict[str, Any]]):
    """Replace _llm_json_call with a mock that returns successive responses."""
    call_count = {"n": 0}
    orig = bridge._llm_json_call

    def _fake(prompt, schema, system_prompt=""):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    bridge._llm_json_call = _fake
    return call_count


# ---------------------------------------------------------------------------
# Layer 2: JnanaReasoningBridge unit-level integration
# ---------------------------------------------------------------------------


class TestJnanaReasoningBridgeFlow:
    """Test the Jnana reasoning flow (Layer 2) standalone."""

    def test_set_research_goal(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        plan = bridge.set_research_goal("Design a binder for IL-17")

        assert isinstance(plan, PlanConfig)
        assert plan.goal == "Design a binder for IL-17"
        assert bridge.research_goal == "Design a binder for IL-17"

    def test_recommend_next_action_stub(self, tmp_path):
        """Without LLM, recommend_next_action returns stub defaults."""
        bridge = _make_bridge(tmp_path)
        bridge.set_research_goal("Design a binder for IL-17")

        # Mock _llm_json_call to simulate no-LLM stub behavior
        _mock_llm_json_call(bridge, [
            {"next_task": "", "rationale": "", "confidence": 0.0},
        ])

        rec = bridge.recommend_next_action()
        assert isinstance(rec, Recommendation)
        # Stub returns empty next_task which maps to "stop" in the bridge
        assert rec.task_type in ("stop", "")

    def test_recommend_with_mock_llm(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge.set_research_goal("Design a binder for IL-17")

        _mock_llm_json_call(bridge, [
            {"next_task": "computational_design", "rationale": "Start with BindCraft", "confidence": 0.8},
        ])

        rec = bridge.recommend_next_action()
        assert rec.task_type == "computational_design"
        assert rec.confidence == 0.8

    def test_bound_parameters_with_mock(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge.set_research_goal("Design a binder for IL-17")

        _mock_llm_json_call(bridge, [
            {"next_task": "computational_design", "rationale": "test", "confidence": 0.9},
            {"binder_sequence": "ACDEF", "num_rounds": 3, "batch_size": 8},
        ])

        rec = bridge.recommend_next_action()
        config = bridge.bound_parameters("bindcraft", "computational_design")
        assert isinstance(config, BoundedConfig)
        assert config.parameters.get("binder_sequence") == "ACDEF"

    def test_evaluate_results(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge.set_research_goal("Design a binder for IL-17")

        # Create a test artifact in the store
        meta = ArtifactMetadata(
            artifact_type=ArtifactType.RAW_OUTPUT,
            skill_name="bindcraft",
        )
        art = create_artifact(metadata=meta, data={"affinity": -12.5})
        bridge.artifact_store.put(art)

        _mock_llm_json_call(bridge, [
            {
                "evaluation": "Good binding affinity",
                "decision": "continue",
                "updated_hypothesis": "IL-17 binding confirmed",
                "scores": {"affinity": -12.5},
            },
        ])

        evaluation = bridge.evaluate_results([art.artifact_id])
        assert isinstance(evaluation, Evaluation)
        assert evaluation.decision == "continue"

    def test_convergence_on_stop_recommendation(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge.set_research_goal("Design a binder for IL-17")

        _mock_llm_json_call(bridge, [
            {"next_task": "stop", "rationale": "Goal achieved", "confidence": 0.95},
        ])

        bridge.recommend_next_action()
        assert bridge.check_convergence() is True

    def test_convergence_on_complete_evaluation(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge.set_research_goal("Design a binder for IL-17")

        # Simulate an evaluation with "complete" decision in results history
        bridge._append_history(
            decision="Evaluated",
            results={"evaluation": "Excellent", "decision": "complete"},
        )
        assert bridge.check_convergence() is True

    def test_no_convergence_initially(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge.set_research_goal("Design a binder for IL-17")
        assert bridge.check_convergence() is False


# ---------------------------------------------------------------------------
# Layer 3: Artifact DAG in the loop
# ---------------------------------------------------------------------------


class TestArtifactDAGInLoop:
    """Verify artifacts are created and linked during the loop."""

    def test_reasoning_artifacts_stored(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge.set_research_goal("Design a binder for IL-17")

        # set_research_goal stores a hypothesis artifact
        store = bridge.artifact_store
        all_ids = store.list_all()
        assert len(all_ids) >= 1

    def test_recommendation_stored_as_artifact(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge.set_research_goal("Design a binder for IL-17")

        _mock_llm_json_call(bridge, [
            {"next_task": "computational_design", "rationale": "Start design", "confidence": 0.85},
        ])

        bridge.recommend_next_action()
        artifacts = bridge.artifact_store.query_by_skill("jnana-reasoning")
        # At least 2: one from set_research_goal, one from recommend
        assert len(artifacts) >= 2


# ---------------------------------------------------------------------------
# MCP Server integration (Layer 1 ↔ Layer 2)
# ---------------------------------------------------------------------------


class TestMCPServerJnanaIntegration:
    """Test MCP server routes to JnanaReasoningBridge."""

    def test_server_has_jnana_tools(self):
        server = create_server()
        tool_names = {t["name"] for t in server.list_tools()}
        assert "jnana_set_goal" in tool_names
        assert "jnana_recommend_action" in tool_names
        assert "jnana_bound_parameters" in tool_names
        assert "jnana_evaluate_results" in tool_names
        assert "jnana_check_convergence" in tool_names

    def test_server_has_skill_tools(self):
        server = create_server()
        tool_names = {t["name"] for t in server.list_tools()}
        assert "run_skill" in tool_names
        assert "list_skills" in tool_names

    def test_server_has_academy_tools(self):
        server = create_server()
        tool_names = {t["name"] for t in server.list_tools()}
        assert "academy_agent_status" in tool_names

    @pytest.mark.asyncio
    async def test_jnana_set_goal_via_mcp(self, tmp_path):
        server = create_server(artifact_store_root=str(tmp_path / "artifacts"))
        result = await server.call_tool("jnana_set_goal", {"research_goal": "Design a binder for IL-17"})
        assert result["status"] == "success"
        assert result["plan"]["goal"] == "Design a binder for IL-17"

    @pytest.mark.asyncio
    async def test_jnana_recommend_via_mcp(self, tmp_path):
        server = create_server(artifact_store_root=str(tmp_path / "artifacts"))
        # First set goal
        await server.call_tool("jnana_set_goal", {"research_goal": "Design a binder for IL-17"})

        # Mock the LLM on the bridge
        _mock_llm_json_call(server.reasoning_bridge, [
            {"next_task": "computational_design", "rationale": "Start design", "confidence": 0.85},
        ])

        result = await server.call_tool("jnana_recommend_action", {})
        assert result["status"] == "success"
        assert result["recommendation"]["task_type"] == "computational_design"

    @pytest.mark.asyncio
    async def test_jnana_check_convergence_via_mcp(self, tmp_path):
        server = create_server(artifact_store_root=str(tmp_path / "artifacts"))
        await server.call_tool("jnana_set_goal", {"research_goal": "Design a binder for IL-17"})
        result = await server.call_tool("jnana_check_convergence", {})
        assert result["status"] == "success"
        assert result["converged"] is False

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        server = create_server()
        result = await server.call_tool("nonexistent_tool", {})
        assert "error" in result


# ---------------------------------------------------------------------------
# Full hybrid loop (all 4 layers)
# ---------------------------------------------------------------------------


class TestHybridLoop:
    """End-to-end tests for the hybrid loop with mocked Academy workers."""

    @pytest.fixture
    def mock_dispatch(self):
        """Create a mock AcademyDispatch that returns canned results."""
        dispatch = MagicMock()
        dispatch._started = True
        dispatch.list_available_skills.return_value = [
            "bindcraft", "folding", "md", "rag",
        ]
        dispatch.list_active_workers.return_value = []
        dispatch.start = AsyncMock()
        dispatch.stop = AsyncMock()
        dispatch.dispatch = AsyncMock(return_value={
            "result": "mock_design_output",
            "affinity": -12.5,
            "status": "success",
        })
        return dispatch

    @pytest.mark.asyncio
    async def test_single_step(self, tmp_path, mock_dispatch):
        from struct_bio_reasoner.workflows.hybrid_loop import HybridLoop

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))
        loop._academy_dispatch = mock_dispatch
        loop._started = True

        # Set goal
        plan = loop.set_goal("Design a binder for IL-17")
        assert plan["goal"] == "Design a binder for IL-17"

        # Mock the LLM calls: recommend → bound_params → evaluate
        _mock_llm_json_call(loop.reasoning_bridge, [
            # Recommendation (Tier 1)
            {"next_task": "computational_design", "rationale": "Start with design", "confidence": 0.8},
            # Bounded parameters (Tier 2)
            {"binder_sequence": "MKQHKAMIVALIVICITAVVAA", "num_rounds": 3},
            # Evaluation
            {"evaluation": "Good initial design", "decision": "continue", "updated_hypothesis": "Looks promising", "scores": {"affinity": -12.5}},
        ])

        step = await loop.step()
        assert step.iteration == 1
        assert step.task_type == "computational_design"
        assert step.skill_name == "bindcraft"
        assert step.artifact_id is not None
        assert not step.converged

        # Verify Academy dispatch was called
        mock_dispatch.dispatch.assert_called_once_with(
            "bindcraft", {"binder_sequence": "MKQHKAMIVALIVICITAVVAA", "num_rounds": 3}
        )

        # Verify artifact was stored in DAG
        art = loop.artifact_dag.get(step.artifact_id)
        assert art is not None
        assert art.metadata.skill_name == "bindcraft"

    @pytest.mark.asyncio
    async def test_multi_iteration_convergence(self, tmp_path, mock_dispatch):
        """Run 3+ iterations, then converge."""
        from struct_bio_reasoner.workflows.hybrid_loop import HybridLoop

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))
        loop._academy_dispatch = mock_dispatch
        loop._started = True

        # Build responses for 3 iterations + convergence
        llm_responses = [
            # Iter 1: recommend
            {"next_task": "computational_design", "rationale": "Initial design", "confidence": 0.7},
            # Iter 1: bound_params
            {"binder_sequence": "AAAAAA", "num_rounds": 3},
            # Iter 1: evaluate
            {"evaluation": "Weak binding", "decision": "continue", "updated_hypothesis": "Need improvement", "scores": {"affinity": -8.0}},
            # Iter 2: recommend
            {"next_task": "molecular_dynamics", "rationale": "Run MD simulation", "confidence": 0.8},
            # Iter 2: bound_params
            {"simulation_paths": ["/sim1"], "steps": 1000},
            # Iter 2: evaluate
            {"evaluation": "Good dynamics", "decision": "continue", "updated_hypothesis": "Stable complex", "scores": {"rmsd": 2.1}},
            # Iter 3: recommend stop
            {"next_task": "stop", "rationale": "Goal achieved", "confidence": 0.95},
        ]

        _mock_llm_json_call(loop.reasoning_bridge, llm_responses)

        result = await loop.run("Design a binder for IL-17", max_iterations=10)

        assert result["converged"] is True
        assert result["iterations"] == 3
        assert result["research_goal"] == "Design a binder for IL-17"
        assert len(result["steps"]) == 3
        assert result["steps"][0]["task_type"] == "computational_design"
        assert result["steps"][1]["task_type"] == "molecular_dynamics"
        assert result["steps"][2]["task_type"] == "stop"

    @pytest.mark.asyncio
    async def test_max_iterations_limit(self, tmp_path, mock_dispatch):
        """Loop stops at max_iterations even if not converged."""
        from struct_bio_reasoner.workflows.hybrid_loop import HybridLoop

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))
        loop._academy_dispatch = mock_dispatch
        loop._started = True

        # Always recommend design, never converge
        never_stop_responses = [
            {"next_task": "computational_design", "rationale": "Keep going", "confidence": 0.6},
            {"binder_sequence": "GGGG", "num_rounds": 1},
            {"evaluation": "Not done", "decision": "continue", "updated_hypothesis": "More work", "scores": {}},
        ] * 5  # enough for 5 iterations

        _mock_llm_json_call(loop.reasoning_bridge, never_stop_responses)

        result = await loop.run("Design a binder for IL-17", max_iterations=3)

        assert result["iterations"] == 3
        assert result["converged"] is False

    @pytest.mark.asyncio
    async def test_interactive_mode_multiple_steps(self, tmp_path, mock_dispatch):
        """Interactive mode: call step() multiple times."""
        from struct_bio_reasoner.workflows.hybrid_loop import HybridLoop

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))
        loop._academy_dispatch = mock_dispatch
        loop._started = True

        loop.set_goal("Design a binder for IL-17")

        responses = [
            # Step 1
            {"next_task": "computational_design", "rationale": "Design first", "confidence": 0.7},
            {"binder_sequence": "AAA", "num_rounds": 1},
            {"evaluation": "OK", "decision": "continue", "updated_hypothesis": "Continue", "scores": {}},
            # Step 2
            {"next_task": "stop", "rationale": "Done", "confidence": 0.9},
        ]
        _mock_llm_json_call(loop.reasoning_bridge, responses)

        step1 = await loop.step()
        assert step1.iteration == 1
        assert not step1.converged

        step2 = await loop.step(
            previous_run_type=step1.task_type,
            previous_conclusion="OK",
        )
        assert step2.iteration == 2
        assert step2.converged

        assert loop.iteration == 2
        assert len(loop.steps) == 2

    @pytest.mark.asyncio
    async def test_artifacts_accumulate_in_dag(self, tmp_path, mock_dispatch):
        """Verify each iteration creates artifacts in the DAG."""
        from struct_bio_reasoner.workflows.hybrid_loop import HybridLoop

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))
        loop._academy_dispatch = mock_dispatch
        loop._started = True

        responses = [
            {"next_task": "computational_design", "rationale": "Start", "confidence": 0.8},
            {"binder_sequence": "TEST", "num_rounds": 1},
            {"evaluation": "Good", "decision": "continue", "updated_hypothesis": "OK", "scores": {}},
            {"next_task": "stop", "rationale": "Done", "confidence": 0.95},
        ]
        _mock_llm_json_call(loop.reasoning_bridge, responses)

        result = await loop.run("Design a binder for IL-17", max_iterations=5)

        # Should have artifacts from:
        # - set_research_goal (plan artifact)
        # - hypothesis generation
        # - recommendation artifacts
        # - bounded config artifacts
        # - dispatch result artifact
        # - evaluation artifacts
        all_ids = loop.artifact_dag.artifact_store.list_all()
        assert len(all_ids) >= 3  # At minimum: plan + recommendation + dispatch result


# ---------------------------------------------------------------------------
# MCP → Academy dispatch integration
# ---------------------------------------------------------------------------


class TestMCPAcademyIntegration:
    """Test MCP server routing run_skill to AcademyDispatch."""

    @pytest.mark.asyncio
    async def test_run_skill_routes_to_dispatch(self, tmp_path):
        server = create_server(artifact_store_root=str(tmp_path / "artifacts"))

        mock_dispatch = MagicMock()
        mock_dispatch._started = True
        mock_dispatch.dispatch = AsyncMock(return_value={"result": "mock_output"})
        mock_dispatch.start = AsyncMock()
        mock_dispatch.list_available_skills.return_value = ["bindcraft"]
        mock_dispatch.list_active_workers.return_value = []
        server._academy_dispatch = mock_dispatch

        result = await server.call_tool("run_skill", {
            "skill_name": "bindcraft",
            "parameters": {"target": "IL-17"},
        })

        assert result["status"] == "success"
        mock_dispatch.dispatch.assert_called_once_with("bindcraft", {"target": "IL-17"})

    @pytest.mark.asyncio
    async def test_list_skills_routes_to_dispatch(self, tmp_path):
        server = create_server(artifact_store_root=str(tmp_path / "artifacts"))

        mock_dispatch = MagicMock()
        mock_dispatch._started = False
        mock_dispatch.list_available_skills.return_value = ["bindcraft", "folding", "md"]
        server._academy_dispatch = mock_dispatch

        result = await server.call_tool("list_skills", {})
        assert result["status"] == "success"
        assert "bindcraft" in result["skills"]

    @pytest.mark.asyncio
    async def test_academy_status(self, tmp_path):
        server = create_server(artifact_store_root=str(tmp_path / "artifacts"))

        mock_dispatch = MagicMock()
        mock_dispatch._started = True
        mock_dispatch.list_available_skills.return_value = ["bindcraft"]
        mock_dispatch.list_active_workers.return_value = ["bindcraft"]
        server._academy_dispatch = mock_dispatch

        result = await server.call_tool("academy_agent_status", {})
        assert result["status"] == "success"
        assert result["started"] is True
        assert "bindcraft" in result["active_workers"]


# ---------------------------------------------------------------------------
# Convergence detection
# ---------------------------------------------------------------------------


class TestConvergenceDetection:
    """Test convergence wired into the loop termination."""

    def test_stop_recommendation_triggers_convergence(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge.set_research_goal("Test goal")

        # Directly inject a "stop" recommendation into history
        bridge.history["recommendations"].append(
            {"task_type": "stop", "rationale": "Done", "confidence": 0.95}
        )
        assert bridge.check_convergence() is True

    def test_complete_evaluation_triggers_convergence(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge.set_research_goal("Test goal")

        # Inject a "complete" evaluation into results history
        bridge._append_history(
            decision="Evaluated",
            results={"decision": "complete", "evaluation": "Done"},
        )
        assert bridge.check_convergence() is True

    def test_no_convergence_with_continue(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge.set_research_goal("Test goal")

        bridge._append_history(
            decision="Evaluated",
            results={"decision": "continue", "evaluation": "Need more data"},
        )
        assert bridge.check_convergence() is False

    @pytest.mark.asyncio
    async def test_convergence_terminates_hybrid_loop(self, tmp_path):
        """The hybrid loop stops when convergence is detected."""
        from struct_bio_reasoner.workflows.hybrid_loop import HybridLoop

        dispatch = MagicMock()
        dispatch._started = True
        dispatch.dispatch = AsyncMock(return_value={"result": "output"})
        dispatch.start = AsyncMock()
        dispatch.stop = AsyncMock()
        dispatch.list_available_skills.return_value = ["bindcraft"]
        dispatch.list_active_workers.return_value = []

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))
        loop._academy_dispatch = dispatch
        loop._started = True

        _mock_llm_json_call(loop.reasoning_bridge, [
            # Iteration 1 — converges immediately via "stop"
            {"next_task": "stop", "rationale": "Already done", "confidence": 0.99},
        ])

        result = await loop.run("Test goal", max_iterations=10)
        assert result["converged"] is True
        assert result["iterations"] == 1
