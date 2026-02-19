"""
Tests for the prompt system: registry, context building, recommender, task defs.
"""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from struct_bio_reasoner.models import (
    PLAN_MODELS,
    RUNNABLE_TASKS,
    TaskName,
    WorkflowHistory,
)
from struct_bio_reasoner.prompts._registry import (
    TASK_REGISTRY,
    PromptContext,
    TaskDef,
    build_prompt_context,
    get_conclusion_prompt,
    get_plan_model,
    get_running_prompt,
    serialize_history,
    validate_task_registry,
)
from struct_bio_reasoner.prompts._recommender import build_recommender_prompt


# ---------------------------------------------------------------------------
# PromptContext
# ---------------------------------------------------------------------------

class TestPromptContext:
    def test_construction(self):
        wh = WorkflowHistory()
        ctx = PromptContext(
            research_goal="Design IL-6 binder",
            target_prot="IL6",
            prompt_type="binder_design",
            history=wh,
            input_json={"foo": "bar"},
        )
        assert ctx.research_goal == "Design IL-6 binder"
        assert ctx.target_prot == "IL6"
        assert ctx.resource_summary == ""

    def test_frozen(self):
        wh = WorkflowHistory()
        ctx = PromptContext(
            research_goal="goal",
            target_prot="prot",
            prompt_type="type",
            history=wh,
            input_json={},
        )
        with pytest.raises(AttributeError):
            ctx.research_goal = "new goal"

    def test_with_resource_summary(self):
        wh = WorkflowHistory()
        ctx = PromptContext(
            research_goal="goal",
            target_prot="prot",
            prompt_type="type",
            history=wh,
            input_json={},
            resource_summary="4 GPUs available",
        )
        assert ctx.resource_summary == "4 GPUs available"


# ---------------------------------------------------------------------------
# serialize_history
# ---------------------------------------------------------------------------

class TestSerializeHistory:
    def test_empty_history(self):
        wh = WorkflowHistory()
        sh = serialize_history(wh)
        assert sh["decisions"] == "No history"
        assert sh["results"] == "No history"
        assert sh["configurations"] == "No history"
        assert sh["key_items"] == "No key items yet"

    def test_with_data(self):
        wh = WorkflowHistory(
            decisions=[{"next_task": "md", "rationale": "test"}],
            results=[{"rmsd": 1.5}],
            key_items=[{"type": "binder", "seq": "ACDEF"}],
        )
        sh = serialize_history(wh)
        assert "md" in sh["decisions"]
        assert "1.5" in sh["results"]
        assert "No history" == sh["configurations"]
        assert "binder" in sh["key_items"]

    def test_returns_valid_json(self):
        wh = WorkflowHistory(
            decisions=[{"a": 1}],
            results=[{"b": 2}],
        )
        sh = serialize_history(wh)
        parsed = json.loads(sh["decisions"])
        assert parsed[0]["a"] == 1


# ---------------------------------------------------------------------------
# TASK_REGISTRY
# ---------------------------------------------------------------------------

class TestTaskRegistry:
    def test_all_runnable_tasks_registered(self):
        for task in RUNNABLE_TASKS:
            assert task in TASK_REGISTRY, f"{task} missing from TASK_REGISTRY"

    def test_registered_instances_are_task_defs(self):
        for name, td in TASK_REGISTRY.items():
            assert isinstance(td, TaskDef)

    def test_each_has_plan_model(self):
        for task in RUNNABLE_TASKS:
            td = TASK_REGISTRY[task]
            assert td.plan_model is not None, f"{task} has no plan_model"
            assert issubclass(td.plan_model, BaseModel)

    def test_plan_model_matches_plan_models_registry(self):
        for task in RUNNABLE_TASKS:
            td = TASK_REGISTRY[task]
            assert td.plan_model is PLAN_MODELS[task]

    def test_validate_task_registry_passes(self):
        """Should not raise if registries are consistent."""
        validate_task_registry()


# ---------------------------------------------------------------------------
# build_prompt_context
# ---------------------------------------------------------------------------

class TestBuildPromptContext:
    def test_basic(self):
        ctx = build_prompt_context(
            agent_type="computational_design",
            research_goal="Test goal",
            input_json={"data": 123},
            target_prot="MKKLL",
            prompt_type="binder_design",
            history={},
        )
        assert isinstance(ctx, PromptContext)
        assert ctx.research_goal == "Test goal"
        assert ctx.target_prot == "MKKLL"
        assert isinstance(ctx.history, WorkflowHistory)

    def test_with_workflow_history_instance(self):
        wh = WorkflowHistory(decisions=[{"x": 1}])
        ctx = build_prompt_context(
            agent_type="molecular_dynamics",
            research_goal="MD run",
            input_json={},
            target_prot="ACDEF",
            prompt_type="",
            history=wh,
        )
        assert ctx.history is wh

    def test_with_dict_history(self):
        ctx = build_prompt_context(
            agent_type="analysis",
            research_goal="Analyze",
            input_json={},
            target_prot="PROT",
            prompt_type="",
            history={"decisions": [{"a": 1}], "results": []},
        )
        assert len(ctx.history.decisions) == 1

    def test_with_resource_summary(self):
        ctx = build_prompt_context(
            agent_type="computational_design",
            research_goal="goal",
            input_json={},
            target_prot="p",
            prompt_type="",
            history={},
            resource_summary="8 GPUs",
        )
        assert ctx.resource_summary == "8 GPUs"


# ---------------------------------------------------------------------------
# get_conclusion_prompt / get_running_prompt
# ---------------------------------------------------------------------------

class TestPromptGeneration:
    @pytest.fixture
    def ctx(self):
        wh = WorkflowHistory(
            decisions=[{"next_task": "md"}],
            results=[{"rmsd": 1.5}],
        )
        return PromptContext(
            research_goal="Design IL-6 binder",
            target_prot="IL6",
            prompt_type="binder_design",
            history=wh,
            input_json={
                "previous_run": "starting",
                "recommendation": {"next_task": "computational_design", "rationale": "first run"},
                "num_rounds": 2,
                "total_sequences": 50,
            },
        )

    def test_get_conclusion_prompt_computational_design(self, ctx):
        prompt = get_conclusion_prompt("computational_design", ctx)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_running_prompt_computational_design(self, ctx):
        prompt = get_running_prompt("computational_design", ctx)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_conclusion_prompt_molecular_dynamics(self, ctx):
        prompt = get_conclusion_prompt("molecular_dynamics", ctx)
        assert isinstance(prompt, str)

    def test_get_running_prompt_molecular_dynamics(self, ctx):
        prompt = get_running_prompt("molecular_dynamics", ctx)
        assert isinstance(prompt, str)

    def test_get_conclusion_prompt_starting(self, ctx):
        prompt = get_conclusion_prompt("starting", ctx)
        assert isinstance(prompt, str)

    def test_get_running_prompt_starting(self, ctx):
        prompt = get_running_prompt("starting", ctx)
        assert isinstance(prompt, str)

    def test_unknown_task_raises(self, ctx):
        with pytest.raises(KeyError, match="Unknown task type"):
            get_conclusion_prompt("nonexistent_task", ctx)

    def test_all_runnable_tasks_have_conclusion(self, ctx):
        for task in RUNNABLE_TASKS:
            prompt = get_conclusion_prompt(task, ctx)
            assert isinstance(prompt, str)

    def test_all_runnable_tasks_have_running(self, ctx):
        for task in RUNNABLE_TASKS:
            prompt = get_running_prompt(task, ctx)
            assert isinstance(prompt, str)


# ---------------------------------------------------------------------------
# get_plan_model
# ---------------------------------------------------------------------------

class TestGetPlanModel:
    def test_known_task(self):
        for task in RUNNABLE_TASKS:
            model = get_plan_model(task)
            assert model is not None
            assert issubclass(model, BaseModel)

    def test_unknown_task_raises(self):
        with pytest.raises(KeyError):
            get_plan_model("nonexistent_task")


# ---------------------------------------------------------------------------
# build_recommender_prompt
# ---------------------------------------------------------------------------

class TestBuildRecommenderPrompt:
    def test_basic(self):
        prompt = build_recommender_prompt(
            enabled_agents=["computational_design", "molecular_dynamics"],
            research_goal="Design IL-6 binder",
            previous_run="starting",
            previous_conclusion="Begin with design",
            history=WorkflowHistory(),
        )
        assert "AI co-scientist" in prompt
        assert "Design IL-6 binder" in prompt
        assert "starting" in prompt

    def test_includes_enabled_agents(self):
        agents = ["computational_design", "molecular_dynamics", "free_energy"]
        prompt = build_recommender_prompt(
            enabled_agents=agents,
            research_goal="goal",
            previous_run="starting",
            previous_conclusion="",
            history={},
        )
        for agent in agents:
            assert agent in prompt

    def test_with_resource_summary(self):
        prompt = build_recommender_prompt(
            enabled_agents=["md"],
            research_goal="goal",
            previous_run="starting",
            previous_conclusion="",
            history=WorkflowHistory(),
            resource_summary="4 GPUs on Polaris",
        )
        assert "COMPUTE RESOURCES AVAILABLE" in prompt
        assert "4 GPUs on Polaris" in prompt
        assert "Scale your recommendations" in prompt

    def test_without_resource_summary(self):
        prompt = build_recommender_prompt(
            enabled_agents=["md"],
            research_goal="goal",
            previous_run="starting",
            previous_conclusion="",
            history=WorkflowHistory(),
        )
        assert "COMPUTE RESOURCES" not in prompt

    def test_dict_history(self):
        prompt = build_recommender_prompt(
            enabled_agents=["md"],
            research_goal="goal",
            previous_run="md",
            previous_conclusion="done",
            history={"decisions": [{"x": 1}]},
        )
        assert isinstance(prompt, str)
        assert "goal" in prompt

    def test_workflow_history_instance(self):
        wh = WorkflowHistory(decisions=[{"next_task": "md"}])
        prompt = build_recommender_prompt(
            enabled_agents=["md"],
            research_goal="goal",
            previous_run="design",
            previous_conclusion="good",
            history=wh,
        )
        assert "md" in prompt
