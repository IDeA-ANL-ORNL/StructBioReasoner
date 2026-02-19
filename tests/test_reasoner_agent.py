"""
Tests for the ReasonerAgent (pydantic-ai backed LLM agent).

All LLM calls are mocked — no real API calls are made.
"""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from struct_bio_reasoner.models import (
    Recommendation,
    RecommendationResult,
    TaskName,
    WorkflowHistory,
)

# Import the module directly to avoid __init__.py cascading
_pai_mod = importlib.import_module("struct_bio_reasoner.agents.language_model.pydantic_ai_agent")
ReasonerAgent = _pai_mod.ReasonerAgent
ALCFTokenAuth = _pai_mod.ALCFTokenAuth
PydanticAIReasonerAgent = _pai_mod.PydanticAIReasonerAgent


# ---------------------------------------------------------------------------
# ReasonerAgent Initialization
# ---------------------------------------------------------------------------

class TestReasonerAgentInit:
    def test_basic_init(self):
        agent = ReasonerAgent(
            research_goal="Design IL-6 binder",
            enabled_agents=["computational_design", "molecular_dynamics"],
            llm_provider="openai",
            target_protein="MKKLL",
        )
        assert agent.research_goal == "Design IL-6 binder"
        assert agent.target_protein == "MKKLL"
        assert agent.resource_summary == ""
        assert agent.enabled_agents == ["computational_design", "molecular_dynamics"]

    def test_with_resource_summary(self):
        agent = ReasonerAgent(
            research_goal="goal",
            enabled_agents=["md"],
            llm_provider="openai",
            target_protein="ACDEF",
            resource_summary="4 GPUs",
        )
        assert agent.resource_summary == "4 GPUs"

    def test_stores_llm_provider(self):
        agent = ReasonerAgent(
            research_goal="goal",
            enabled_agents=["md"],
            llm_provider="alcf",
            target_protein="ACDEF",
        )
        assert agent.llm_provider == "alcf"


# ---------------------------------------------------------------------------
# ReasonerAgent.generate_recommendation
# ---------------------------------------------------------------------------

class TestGenerateRecommendation:
    @pytest.mark.asyncio
    async def test_generate_recommendation(self):
        agent = ReasonerAgent(
            research_goal="Design binder",
            enabled_agents=["computational_design"],
            llm_provider="openai",
            target_protein="MKKLL",
        )

        # Mock the internal pydantic-ai agent's run method
        mock_rec = Recommendation(
            next_task=TaskName.COMPUTATIONAL_DESIGN,
            change_parameters=False,
            rationale="Start with design",
        )
        mock_result = MagicMock()
        mock_result.output = mock_rec
        agent._agent = MagicMock()
        agent._agent.run = AsyncMock(return_value=mock_result)

        result = await agent.generate_recommendation(
            results={"results": "none"},
            previous_run="starting",
            history={},
        )

        assert isinstance(result, RecommendationResult)
        assert result.previous_run == "starting"
        assert result.recommendation.next_task == TaskName.COMPUTATIONAL_DESIGN


# ---------------------------------------------------------------------------
# ReasonerAgent.plan_run
# ---------------------------------------------------------------------------

class TestPlanRun:
    @pytest.mark.asyncio
    async def test_plan_run_with_plan_model(self):
        from struct_bio_reasoner.models import (
            ComputationalDesignConfig,
            ComputationalDesignPlan,
        )

        agent = ReasonerAgent(
            research_goal="Design",
            enabled_agents=["computational_design"],
            llm_provider="openai",
            target_protein="MKKLL",
        )

        # Mock plan output
        cfg = ComputationalDesignConfig(binder_sequence="ACDEF", num_rounds=2)
        mock_plan = ComputationalDesignPlan(new_config=cfg, rationale="first run")
        mock_result = MagicMock()
        mock_result.output = mock_plan

        agent._agent = MagicMock()
        agent._agent.run = AsyncMock(return_value=mock_result)

        rec = RecommendationResult(
            previous_run="starting",
            recommendation=Recommendation(
                next_task=TaskName.COMPUTATIONAL_DESIGN,
                change_parameters=False,
                rationale="first",
            ),
        )

        plan = await agent.plan_run(recommendation=rec, history={})
        assert hasattr(plan, "new_config")
        assert plan.new_config.binder_sequence == "ACDEF"


# ---------------------------------------------------------------------------
# ReasonerAgent.query
# ---------------------------------------------------------------------------

class TestQuery:
    @pytest.mark.asyncio
    async def test_query(self):
        agent = ReasonerAgent(
            research_goal="goal",
            enabled_agents=["md"],
            llm_provider="openai",
            target_protein="ACDEF",
        )

        mock_result = MagicMock()
        mock_result.output = "This is the LLM response"
        agent._agent = MagicMock()
        agent._agent.run = AsyncMock(return_value=mock_result)

        response = await agent.query("What should I do?")
        assert response == "This is the LLM response"


# ---------------------------------------------------------------------------
# ReasonerAgent.evaluate_history
# ---------------------------------------------------------------------------

class TestEvaluateHistory:
    @pytest.mark.asyncio
    async def test_evaluate_history(self):
        agent = ReasonerAgent(
            research_goal="goal",
            enabled_agents=["md"],
            llm_provider="openai",
            target_protein="ACDEF",
        )

        mock_result = MagicMock()
        mock_result.output = "Continue: progress is good"
        agent._agent = MagicMock()
        agent._agent.run = AsyncMock(return_value=mock_result)

        result = await agent.evaluate_history("some history text")
        assert isinstance(result, tuple)
        assert "Continue" in result[0]


# ---------------------------------------------------------------------------
# ALCFTokenAuth
# ---------------------------------------------------------------------------

class TestALCFTokenAuth:
    def test_auth_flow(self):
        import httpx

        with patch.object(_pai_mod, "get_access_token", return_value="test-token-123"):
            auth = ALCFTokenAuth()
            request = httpx.Request("GET", "https://example.com")
            flow = auth.auth_flow(request)
            modified_request = next(flow)
            assert modified_request.headers["Authorization"] == "Bearer test-token-123"


# ---------------------------------------------------------------------------
# Backward-compat alias
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_alias_exists(self):
        assert PydanticAIReasonerAgent is ReasonerAgent
