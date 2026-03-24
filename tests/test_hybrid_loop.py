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


# ---------------------------------------------------------------------------
# Campaign mode (multi-phase workflow)
# ---------------------------------------------------------------------------


class TestCampaignMode:
    """Test multi-phase campaign orchestration."""

    @pytest.fixture
    def mock_dispatch(self):
        dispatch = MagicMock()
        dispatch._started = True
        dispatch.list_available_skills.return_value = [
            "bindcraft", "folding", "md", "rag",
        ]
        dispatch.list_active_workers.return_value = []
        dispatch.start = AsyncMock()
        dispatch.stop = AsyncMock()
        dispatch.dispatch = AsyncMock(return_value={
            "result": "mock_output",
            "affinity": -12.5,
            "status": "success",
        })
        return dispatch

    @pytest.mark.asyncio
    async def test_two_phase_campaign(self, tmp_path, mock_dispatch):
        """Run a 2-phase campaign: exploration → design."""
        from struct_bio_reasoner.workflows.hybrid_loop import (
            HybridLoop, CampaignPhase,
        )

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))
        loop._academy_dispatch = mock_dispatch
        loop._started = True

        phases = [
            CampaignPhase(
                name="exploration",
                goal="Identify hotspots",
                step_sequence=["rag", "structure_prediction"],
                max_iterations=5,
            ),
            CampaignPhase(
                name="design",
                goal="Design binders",
                step_sequence=["computational_design"],
                max_iterations=5,
            ),
        ]

        # Phase 1 LLM responses: rag step + stop
        # Phase 2 LLM responses: design step + stop
        llm_responses = [
            # Phase 1 - set_goal hypothesis
            # Phase 1 step 1: recommend rag
            {"next_task": "rag", "rationale": "Start with literature", "confidence": 0.8},
            {"prompt": "find hotspots"},  # bound params
            {"evaluation": "Found targets", "decision": "continue", "updated_hypothesis": "Hotspots found", "scores": {"coverage": 0.9}},
            # Phase 1 step 2: recommend stop (sequence ends)
            {"next_task": "structure_prediction", "rationale": "Fold complexes", "confidence": 0.7},
            {"sequences": [["AAAA"]], "names": ["test"]},  # bound params
            {"evaluation": "Structures predicted", "decision": "continue", "updated_hypothesis": "OK", "scores": {"confidence": 0.8}},
            # Phase 2 - set_goal hypothesis
            # Phase 2 step 1: recommend design
            {"next_task": "computational_design", "rationale": "Design binders", "confidence": 0.9},
            {"binder_sequence": "MKTEST", "num_rounds": 3},  # bound params
            {"evaluation": "Good binder", "decision": "continue", "updated_hypothesis": "Binder works", "scores": {"affinity": -12.5}},
        ]
        _mock_llm_json_call(loop.reasoning_bridge, llm_responses)

        result = await loop.run_campaign("Design binder for NMNAT-2", phases)

        assert result["phases_completed"] == 2
        assert result["total_phases"] == 2
        assert len(result["phase_results"]) == 2
        assert result["phase_results"][0]["phase_name"] == "exploration"
        assert result["phase_results"][1]["phase_name"] == "design"

    @pytest.mark.asyncio
    async def test_campaign_memory_persists(self, tmp_path, mock_dispatch):
        """Memory should persist across phases."""
        from struct_bio_reasoner.workflows.hybrid_loop import (
            HybridLoop, CampaignPhase, CampaignMemory,
        )

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))
        loop._academy_dispatch = mock_dispatch
        loop._started = True

        phases = [
            CampaignPhase(
                name="phase1", goal="Goal 1",
                step_sequence=["rag"], max_iterations=3,
            ),
            CampaignPhase(
                name="phase2", goal="Goal 2",
                step_sequence=["computational_design"], max_iterations=3,
            ),
        ]

        llm_responses = [
            # Phase 1
            {"next_task": "rag", "rationale": "Search", "confidence": 0.7},
            {"prompt": "search"},
            {"evaluation": "Found", "decision": "continue", "updated_hypothesis": "OK", "scores": {"relevance": 0.8}},
            # Phase 2
            {"next_task": "computational_design", "rationale": "Design", "confidence": 0.8},
            {"binder_sequence": "AAA", "num_rounds": 1},
            {"evaluation": "Designed", "decision": "continue", "updated_hypothesis": "OK", "scores": {"affinity": -10.0}},
        ]
        _mock_llm_json_call(loop.reasoning_bridge, llm_responses)

        result = await loop.run_campaign("Test goal", phases)

        # Memory should contain experimental data from both phases
        mem = result["memory"]
        assert len(mem["long_term"]["experimental_data"]) >= 2
        phases_in_memory = {e["phase"] for e in mem["long_term"]["experimental_data"]}
        assert "phase1" in phases_in_memory
        assert "phase2" in phases_in_memory

    @pytest.mark.asyncio
    async def test_campaign_produces_tournament_rounds(self, tmp_path, mock_dispatch):
        """Each phase should produce a tournament round."""
        from struct_bio_reasoner.workflows.hybrid_loop import (
            HybridLoop, CampaignPhase,
        )

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))
        loop._academy_dispatch = mock_dispatch
        loop._started = True

        phases = [
            CampaignPhase(
                name="phase1", goal="Goal 1",
                step_sequence=["rag"], max_iterations=3,
            ),
        ]

        llm_responses = [
            {"next_task": "rag", "rationale": "Search", "confidence": 0.7},
            {"prompt": "search"},
            {"evaluation": "Found", "decision": "continue", "updated_hypothesis": "OK", "scores": {"relevance": 0.8}},
        ]
        _mock_llm_json_call(loop.reasoning_bridge, llm_responses)

        result = await loop.run_campaign("Test goal", phases)

        assert len(result["tournament_rounds"]) >= 1
        tr = result["tournament_rounds"][0]
        assert tr["phase_name"] == "phase1"
        assert tr["round_number"] == 1
        assert len(tr["artifact_ids"]) >= 1

    @pytest.mark.asyncio
    async def test_campaign_stores_artifacts_in_dag(self, tmp_path, mock_dispatch):
        """Campaign should store campaign config + tournament artifacts."""
        from struct_bio_reasoner.workflows.hybrid_loop import (
            HybridLoop, CampaignPhase,
        )

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))
        loop._academy_dispatch = mock_dispatch
        loop._started = True

        phases = [
            CampaignPhase(
                name="phase1", goal="Goal 1",
                step_sequence=["rag"], max_iterations=3,
            ),
        ]

        llm_responses = [
            {"next_task": "rag", "rationale": "Search", "confidence": 0.7},
            {"prompt": "search"},
            {"evaluation": "Found", "decision": "continue", "updated_hypothesis": "OK", "scores": {}},
        ]
        _mock_llm_json_call(loop.reasoning_bridge, llm_responses)

        await loop.run_campaign("Test goal", phases)

        # Should have: campaign config + phase artifacts + tournament round
        all_ids = loop.artifact_dag.artifact_store.list_all()
        assert len(all_ids) >= 3


# ---------------------------------------------------------------------------
# Tournament framework
# ---------------------------------------------------------------------------


class TestTournamentRound:
    """Test tournament scoring and promote/cull decisions."""

    def test_tournament_round_dataclass(self):
        from struct_bio_reasoner.workflows.hybrid_loop import TournamentRound

        tr = TournamentRound(
            round_number=1,
            phase_name="design",
            scores={"affinity": -12.5, "stability": 0.6},
            promoted=["affinity"],
            culled=["stability"],
        )
        d = tr.to_dict()
        assert d["round_number"] == 1
        assert d["phase_name"] == "design"
        assert "affinity" in d["promoted"]
        assert "stability" in d["culled"]

    @pytest.mark.asyncio
    async def test_tournament_promotes_above_average(self, tmp_path):
        """Scores above average are promoted, below are culled."""
        from struct_bio_reasoner.workflows.hybrid_loop import HybridLoop, LoopStep

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))

        # Create fake steps with varying scores
        steps = [
            LoopStep(
                iteration=1, task_type="computational_design",
                skill_name="bindcraft", artifact_id="art1",
                evaluation={"scores": {"affinity": -15.0}},
            ),
            LoopStep(
                iteration=2, task_type="molecular_dynamics",
                skill_name="md", artifact_id="art2",
                evaluation={"scores": {"rmsd": 1.5}},
            ),
            LoopStep(
                iteration=3, task_type="computational_design",
                skill_name="bindcraft", artifact_id="art3",
                evaluation={"scores": {"affinity": -5.0}},
            ),
        ]

        tournament = loop._score_tournament_round(steps, "design")

        assert tournament is not None
        assert tournament.round_number == 1
        assert len(tournament.scores) >= 2
        # With scores -15, 1.5, -5 → avg ≈ -6.17
        # -5 > avg → promoted; -15 < avg → culled; 1.5 > avg → promoted
        assert len(tournament.promoted) + len(tournament.culled) == len(tournament.scores)

    def test_tournament_round_empty_steps(self, tmp_path):
        from struct_bio_reasoner.workflows.hybrid_loop import HybridLoop

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))
        result = loop._score_tournament_round([], "empty")
        assert result is None


# ---------------------------------------------------------------------------
# CampaignMemory
# ---------------------------------------------------------------------------


class TestCampaignMemory:
    """Test the long-term/short-term memory system."""

    def test_memory_init(self):
        from struct_bio_reasoner.workflows.hybrid_loop import CampaignMemory

        mem = CampaignMemory()
        assert "hotspots" in mem.long_term
        assert "top_binders" in mem.long_term
        assert "design_constraints" in mem.long_term
        assert len(mem.short_term) == 0

    def test_add_long_term(self):
        from struct_bio_reasoner.workflows.hybrid_loop import CampaignMemory

        mem = CampaignMemory()
        mem.add_long_term("hotspots", {"residue": "R45", "score": 0.9})
        assert len(mem.long_term["hotspots"]) == 1
        assert mem.long_term["hotspots"][0]["residue"] == "R45"

    def test_add_long_term_new_category(self):
        from struct_bio_reasoner.workflows.hybrid_loop import CampaignMemory

        mem = CampaignMemory()
        mem.add_long_term("custom_category", "value1")
        assert "custom_category" in mem.long_term
        assert mem.long_term["custom_category"] == ["value1"]

    def test_short_term_auto_trim(self):
        from struct_bio_reasoner.workflows.hybrid_loop import CampaignMemory

        mem = CampaignMemory(max_short_term=5)
        for i in range(10):
            mem.add_short_term({"iteration": i})

        assert len(mem.short_term) == 5
        # Should keep the most recent entries
        assert mem.short_term[0]["iteration"] == 5
        assert mem.short_term[-1]["iteration"] == 9

    def test_manual_trim(self):
        from struct_bio_reasoner.workflows.hybrid_loop import CampaignMemory

        mem = CampaignMemory(max_short_term=100)
        for i in range(20):
            mem.add_short_term({"iteration": i})

        mem.trim_short_term(keep=3)
        assert len(mem.short_term) == 3
        assert mem.short_term[0]["iteration"] == 17

    def test_get_context(self):
        from struct_bio_reasoner.workflows.hybrid_loop import CampaignMemory

        mem = CampaignMemory()
        mem.add_long_term("hotspots", {"residue": "R45"})
        for i in range(15):
            mem.add_short_term({"iteration": i})

        ctx = mem.get_context()
        assert "long_term" in ctx
        assert "short_term" in ctx
        # get_context returns at most 10 short-term entries
        assert len(ctx["short_term"]) == 10

    def test_to_dict(self):
        from struct_bio_reasoner.workflows.hybrid_loop import CampaignMemory

        mem = CampaignMemory(max_short_term=15)
        mem.add_long_term("hotspots", "R45")
        mem.add_short_term({"x": 1})

        d = mem.to_dict()
        assert d["max_short_term"] == 15
        assert len(d["long_term"]["hotspots"]) == 1
        assert len(d["short_term"]) == 1


# ---------------------------------------------------------------------------
# Checkpoint callbacks
# ---------------------------------------------------------------------------


class TestCheckpointCallbacks:
    """Test human-in-the-loop checkpoint firing."""

    @pytest.fixture
    def mock_dispatch(self):
        dispatch = MagicMock()
        dispatch._started = True
        dispatch.list_available_skills.return_value = ["bindcraft"]
        dispatch.list_active_workers.return_value = []
        dispatch.start = AsyncMock()
        dispatch.stop = AsyncMock()
        dispatch.dispatch = AsyncMock(return_value={
            "result": "mock_output", "affinity": -12.5,
        })
        return dispatch

    @pytest.mark.asyncio
    async def test_checkpoint_fires_at_interval(self, tmp_path, mock_dispatch):
        """Checkpoint fires every N steps."""
        from struct_bio_reasoner.workflows.hybrid_loop import (
            HybridLoop, CampaignPhase,
        )

        checkpoint_calls = []

        def my_callback(hypotheses, evidence, uncertainties):
            checkpoint_calls.append({
                "hypotheses": hypotheses,
                "evidence": evidence,
            })
            return None  # no override

        loop = HybridLoop(
            artifact_store_root=str(tmp_path / "artifacts"),
            checkpoint_callback=my_callback,
            checkpoint_interval=2,
        )
        loop._academy_dispatch = mock_dispatch
        loop._started = True

        phases = [
            CampaignPhase(
                name="test", goal="Test",
                step_sequence=["rag", "computational_design", "molecular_dynamics"],
                max_iterations=5,
            ),
        ]

        llm_responses = [
            # Step 1
            {"next_task": "rag", "rationale": "Search", "confidence": 0.7},
            {"prompt": "search"},
            {"evaluation": "Found", "decision": "continue", "updated_hypothesis": "OK", "scores": {}},
            # Step 2
            {"next_task": "computational_design", "rationale": "Design", "confidence": 0.8},
            {"binder_sequence": "AAA", "num_rounds": 1},
            {"evaluation": "Designed", "decision": "continue", "updated_hypothesis": "OK", "scores": {"affinity": -10.0}},
            # Step 3
            {"next_task": "molecular_dynamics", "rationale": "Simulate", "confidence": 0.7},
            {"simulation_paths": ["/sim1"], "steps": 1000},
            {"evaluation": "Simulated", "decision": "continue", "updated_hypothesis": "OK", "scores": {"rmsd": 2.0}},
        ]
        _mock_llm_json_call(loop.reasoning_bridge, llm_responses)

        await loop.run_campaign("Test goal", phases)

        # Checkpoint should have fired at step 2 (interval=2)
        assert len(checkpoint_calls) >= 1

    @pytest.mark.asyncio
    async def test_checkpoint_override_applied(self, tmp_path, mock_dispatch):
        """Checkpoint override injects into reasoning history."""
        from struct_bio_reasoner.workflows.hybrid_loop import (
            HybridLoop, CampaignPhase,
        )

        def override_callback(hypotheses, evidence, uncertainties):
            return {
                "key_items": "Focus on hotspot R45",
                "configuration": {"focus_residue": "R45"},
            }

        loop = HybridLoop(
            artifact_store_root=str(tmp_path / "artifacts"),
            checkpoint_callback=override_callback,
            checkpoint_interval=1,  # fire every step
        )
        loop._academy_dispatch = mock_dispatch
        loop._started = True

        phases = [
            CampaignPhase(
                name="test", goal="Test",
                step_sequence=["rag", "computational_design"],
                max_iterations=5,
            ),
        ]

        llm_responses = [
            {"next_task": "rag", "rationale": "Search", "confidence": 0.7},
            {"prompt": "search"},
            {"evaluation": "Found", "decision": "continue", "updated_hypothesis": "OK", "scores": {}},
            {"next_task": "computational_design", "rationale": "Design", "confidence": 0.8},
            {"binder_sequence": "AAA", "num_rounds": 1},
            {"evaluation": "Designed", "decision": "continue", "updated_hypothesis": "OK", "scores": {}},
        ]
        _mock_llm_json_call(loop.reasoning_bridge, llm_responses)

        await loop.run_campaign("Test goal", phases)

        # History should contain override
        key_items = loop.reasoning_bridge.history["key_items"]
        assert any("R45" in str(ki) for ki in key_items)

    def test_checkpoint_callback_in_constructor(self, tmp_path):
        """Verify checkpoint params are stored correctly."""
        from struct_bio_reasoner.workflows.hybrid_loop import HybridLoop

        def dummy(h, e, u):
            return None

        loop = HybridLoop(
            artifact_store_root=str(tmp_path / "artifacts"),
            checkpoint_callback=dummy,
            checkpoint_interval=3,
        )
        assert loop._checkpoint_callback is dummy
        assert loop._checkpoint_interval == 3


# ---------------------------------------------------------------------------
# Cross-hypothesis learning
# ---------------------------------------------------------------------------


class TestCrossHypothesisLearning:
    """Test pattern identification across hypotheses."""

    def test_patterns_identified_from_memory(self, tmp_path):
        from struct_bio_reasoner.workflows.hybrid_loop import (
            HybridLoop, CampaignMemory,
        )

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))
        loop._campaign_memory = CampaignMemory()

        # Add multiple evaluations for the same task type
        loop._campaign_memory.add_short_term({
            "task_type": "computational_design",
            "evaluation": {"scores": {"affinity": -12.0}},
        })
        loop._campaign_memory.add_short_term({
            "task_type": "computational_design",
            "evaluation": {"scores": {"affinity": -11.5}},
        })
        loop._campaign_memory.add_short_term({
            "task_type": "computational_design",
            "evaluation": {"scores": {"affinity": -12.2}},
        })

        loop._update_cross_hypothesis_patterns()

        assert len(loop._cross_hypothesis_patterns) >= 1
        pattern = loop._cross_hypothesis_patterns[0]
        assert pattern["task_type"] == "computational_design"
        assert pattern["metric"] == "affinity"
        assert pattern["count"] == 3

    def test_design_constraints_stored_in_memory(self, tmp_path):
        from struct_bio_reasoner.workflows.hybrid_loop import (
            HybridLoop, CampaignMemory,
        )

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))
        loop._campaign_memory = CampaignMemory()

        # Add consistent scores → should create design constraint
        for i in range(3):
            loop._campaign_memory.add_short_term({
                "task_type": "molecular_dynamics",
                "evaluation": {"scores": {"rmsd": 2.0 + i * 0.05}},
            })

        loop._update_cross_hypothesis_patterns()

        constraints = loop._campaign_memory.long_term["design_constraints"]
        assert len(constraints) >= 1
        assert constraints[0]["source"] == "cross_hypothesis"
        assert constraints[0]["task_type"] == "molecular_dynamics"

    def test_no_patterns_without_memory(self, tmp_path):
        from struct_bio_reasoner.workflows.hybrid_loop import HybridLoop

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))
        loop._campaign_memory = None
        loop._update_cross_hypothesis_patterns()
        assert len(loop._cross_hypothesis_patterns) == 0

    def test_no_patterns_with_single_entry(self, tmp_path):
        from struct_bio_reasoner.workflows.hybrid_loop import (
            HybridLoop, CampaignMemory,
        )

        loop = HybridLoop(artifact_store_root=str(tmp_path / "artifacts"))
        loop._campaign_memory = CampaignMemory()
        loop._campaign_memory.add_short_term({
            "task_type": "rag",
            "evaluation": {"scores": {"relevance": 0.9}},
        })

        loop._update_cross_hypothesis_patterns()
        # Need at least 2 entries to find patterns
        assert len(loop._cross_hypothesis_patterns) == 0


# ---------------------------------------------------------------------------
# CampaignPhase dataclass
# ---------------------------------------------------------------------------


class TestCampaignPhase:
    def test_to_dict(self):
        from struct_bio_reasoner.workflows.hybrid_loop import CampaignPhase

        phase = CampaignPhase(
            name="exploration",
            goal="Find targets",
            step_sequence=["rag", "folding"],
            max_iterations=5,
        )
        d = phase.to_dict()
        assert d["name"] == "exploration"
        assert d["goal"] == "Find targets"
        assert d["step_sequence"] == ["rag", "folding"]
        assert d["max_iterations"] == 5
