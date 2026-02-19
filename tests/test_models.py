"""
Tests for struct_bio_reasoner.models — Pydantic models, enums, registries.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from struct_bio_reasoner.models import (
    # Enums
    TaskName,
    RUNNABLE_TASKS,
    # Config models
    ComputationalDesignConfig,
    MolecularDynamicsConfig,
    StructurePredictionConfig,
    AnalysisConfig,
    FreeEnergyConfig,
    RAGConfig,
    QCKwargs,
    Constraint,
    # Registries
    CONFIG_MODELS,
    PLAN_MODELS,
    # Plan aliases
    ComputationalDesignPlan,
    MolecularDynamicsPlan,
    StructurePredictionPlan,
    AnalysisPlan,
    FreeEnergyPlan,
    RAGPlan,
    # LLM output models
    Recommendation,
    RecommendationResult,
    # Workflow models
    WorkflowHistory,
    PipelineMetrics,
    # Functions
    build_config_master,
    config_master,
    _make_plan_model,
)


# ---------------------------------------------------------------------------
# TaskName Enum
# ---------------------------------------------------------------------------

class TestTaskName:
    def test_all_members_present(self):
        expected = {
            "COMPUTATIONAL_DESIGN",
            "MOLECULAR_DYNAMICS",
            "STRUCTURE_PREDICTION",
            "ANALYSIS",
            "FREE_ENERGY",
            "RAG",
            "STARTING",
            "STOP",
        }
        assert {m.name for m in TaskName} == expected

    def test_str_value(self):
        assert TaskName.COMPUTATIONAL_DESIGN == "computational_design"
        assert TaskName.MOLECULAR_DYNAMICS == "molecular_dynamics"
        assert TaskName.STOP == "stop"

    def test_is_string(self):
        """TaskName members should behave like strings."""
        assert isinstance(TaskName.RAG, str)
        assert str(TaskName.RAG) in ("rag", "TaskName.RAG")

    def test_runnable_tasks_excludes_starting_and_stop(self):
        assert TaskName.STARTING not in RUNNABLE_TASKS
        assert TaskName.STOP not in RUNNABLE_TASKS

    def test_runnable_tasks_includes_all_others(self):
        for task in TaskName:
            if task not in (TaskName.STARTING, TaskName.STOP):
                assert task in RUNNABLE_TASKS

    def test_runnable_tasks_is_frozenset(self):
        assert isinstance(RUNNABLE_TASKS, frozenset)


# ---------------------------------------------------------------------------
# Config Models
# ---------------------------------------------------------------------------

class TestComputationalDesignConfig:
    def test_minimal(self):
        cfg = ComputationalDesignConfig(binder_sequence="ACDEF")
        assert cfg.binder_sequence == "ACDEF"
        assert cfg.num_rounds == 2  # default
        assert cfg.constraints == {}
        assert cfg.remodel_indices == []

    def test_full(self):
        cfg = ComputationalDesignConfig(
            binder_sequence="MKKLL",
            num_rounds=5,
            constraints={"residues_bind": ["A10", "B20"]},
            remodel_indices=[1, 2, 3],
        )
        assert cfg.num_rounds == 5
        assert cfg.remodel_indices == [1, 2, 3]

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            ComputationalDesignConfig()

    def test_serialization_roundtrip(self):
        cfg = ComputationalDesignConfig(binder_sequence="ACDEF", num_rounds=3)
        data = cfg.model_dump()
        cfg2 = ComputationalDesignConfig(**data)
        assert cfg == cfg2

    def test_json_schema(self):
        schema = ComputationalDesignConfig.model_json_schema()
        assert "binder_sequence" in schema["properties"]
        assert "num_rounds" in schema["properties"]


class TestMolecularDynamicsConfig:
    def test_valid(self):
        cfg = MolecularDynamicsConfig(
            simulation_paths=["/path/a.pdb", "/path/b.pdb"],
            root_output_path="/output",
            steps=10000,
        )
        assert cfg.steps == 10000
        assert len(cfg.simulation_paths) == 2

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            MolecularDynamicsConfig(simulation_paths=["/a.pdb"])


class TestStructurePredictionConfig:
    def test_valid(self):
        cfg = StructurePredictionConfig(
            sequences=[["ACDEF", "GHIKL"]],
            names=["target_partner"],
        )
        assert len(cfg.sequences) == 1
        assert cfg.names[0] == "target_partner"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            StructurePredictionConfig(sequences=[["A", "B"]])


class TestAnalysisConfig:
    def test_defaults(self):
        cfg = AnalysisConfig(data_type="static", analysis_type="basic")
        assert cfg.distance_cutoff == 8.0

    def test_custom_cutoff(self):
        cfg = AnalysisConfig(
            data_type="dynamic", analysis_type="advanced", distance_cutoff=5.0
        )
        assert cfg.distance_cutoff == 5.0


class TestFreeEnergyConfig:
    def test_valid(self):
        cfg = FreeEnergyConfig(simulation_paths=["/a/traj.dcd"])
        assert len(cfg.simulation_paths) == 1


class TestRAGConfig:
    def test_valid(self):
        cfg = RAGConfig(prompt="Find papers about IL-6")
        assert "IL-6" in cfg.prompt


class TestQCKwargs:
    def test_defaults(self):
        qc = QCKwargs()
        assert qc.max_repeat == 3
        assert qc.min_diversity == 3
        assert qc.max_charge == 5
        assert qc.max_hydrophobic_ratio == 0.6

    def test_custom(self):
        qc = QCKwargs(max_repeat=5, min_diversity=10)
        assert qc.max_repeat == 5
        assert qc.min_diversity == 10


class TestConstraint:
    def test_defaults(self):
        c = Constraint()
        assert c.residues_bind == []

    def test_with_residues(self):
        c = Constraint(residues_bind=["A10", "B20"])
        assert len(c.residues_bind) == 2


# ---------------------------------------------------------------------------
# Registry Consistency
# ---------------------------------------------------------------------------

class TestRegistries:
    def test_config_and_plan_models_same_keys(self):
        assert set(CONFIG_MODELS.keys()) == set(PLAN_MODELS.keys())

    def test_all_runnable_tasks_have_config(self):
        for task in RUNNABLE_TASKS:
            assert task in CONFIG_MODELS, f"Missing config for {task}"

    def test_all_runnable_tasks_have_plan(self):
        for task in RUNNABLE_TASKS:
            assert task in PLAN_MODELS, f"Missing plan for {task}"

    def test_plan_model_has_new_config_and_rationale(self):
        for name, plan_cls in PLAN_MODELS.items():
            fields = plan_cls.model_fields
            assert "new_config" in fields, f"{name} plan missing new_config"
            assert "rationale" in fields, f"{name} plan missing rationale"

    def test_plan_model_new_config_type(self):
        """new_config field should accept the corresponding Config model."""
        for name, plan_cls in PLAN_MODELS.items():
            config_cls = CONFIG_MODELS[name]
            # Plan model field annotation should reference the config class
            field_info = plan_cls.model_fields["new_config"]
            assert field_info.annotation is config_cls

    def test_config_master_has_all_tasks(self):
        for task in RUNNABLE_TASKS:
            assert task in config_master

    def test_config_master_returns_valid_schemas(self):
        master = build_config_master()
        for name, schema in master.items():
            assert "properties" in schema
            assert isinstance(schema, dict)


# ---------------------------------------------------------------------------
# Plan Model Generation
# ---------------------------------------------------------------------------

class TestMakePlanModel:
    def test_generates_correct_name(self):
        plan = _make_plan_model(ComputationalDesignConfig)
        assert plan.__name__ == "ComputationalDesignPlan"

    def test_plan_model_instantiation(self):
        cfg = ComputationalDesignConfig(binder_sequence="ACDEF")
        plan = ComputationalDesignPlan(new_config=cfg, rationale="test reason")
        assert plan.new_config.binder_sequence == "ACDEF"
        assert plan.rationale == "test reason"

    def test_plan_model_validation_error(self):
        with pytest.raises(ValidationError):
            ComputationalDesignPlan(rationale="missing config")

    def test_all_plan_aliases(self):
        aliases = [
            ComputationalDesignPlan,
            MolecularDynamicsPlan,
            StructurePredictionPlan,
            AnalysisPlan,
            FreeEnergyPlan,
            RAGPlan,
        ]
        for alias in aliases:
            assert issubclass(alias, BaseModel)
            assert "new_config" in alias.model_fields
            assert "rationale" in alias.model_fields


# ---------------------------------------------------------------------------
# LLM Output Models
# ---------------------------------------------------------------------------

class TestRecommendation:
    def test_valid(self):
        rec = Recommendation(
            next_task=TaskName.MOLECULAR_DYNAMICS,
            change_parameters=True,
            rationale="MD needed for validation",
        )
        assert rec.next_task == TaskName.MOLECULAR_DYNAMICS
        assert rec.change_parameters is True

    def test_from_string_task(self):
        rec = Recommendation(
            next_task="computational_design",
            change_parameters=False,
            rationale="Run design first",
        )
        assert rec.next_task == TaskName.COMPUTATIONAL_DESIGN

    def test_invalid_task(self):
        with pytest.raises(ValidationError):
            Recommendation(
                next_task="nonexistent_task",
                change_parameters=False,
                rationale="bad",
            )

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            Recommendation(next_task="rag")

    def test_serialization(self):
        rec = Recommendation(
            next_task=TaskName.RAG,
            change_parameters=False,
            rationale="Need literature",
        )
        data = rec.model_dump()
        assert data["next_task"] == "rag"
        rec2 = Recommendation(**data)
        assert rec == rec2


class TestRecommendationResult:
    def test_valid(self):
        rec = Recommendation(
            next_task=TaskName.ANALYSIS,
            change_parameters=False,
            rationale="Analyze trajectories",
        )
        result = RecommendationResult(
            previous_run="molecular_dynamics",
            recommendation=rec,
        )
        assert result.previous_run == "molecular_dynamics"
        assert result.recommendation.next_task == TaskName.ANALYSIS

    def test_serialization_roundtrip(self):
        rec = Recommendation(
            next_task=TaskName.FREE_ENERGY,
            change_parameters=True,
            rationale="Run MM-PBSA",
        )
        result = RecommendationResult(
            previous_run="analysis",
            recommendation=rec,
        )
        data = result.model_dump()
        result2 = RecommendationResult(**data)
        assert result == result2


# ---------------------------------------------------------------------------
# Workflow History
# ---------------------------------------------------------------------------

class TestWorkflowHistory:
    def test_defaults(self):
        wh = WorkflowHistory()
        assert wh.decisions == []
        assert wh.results == []
        assert wh.configurations == []
        assert wh.key_items == []

    def test_with_data(self):
        wh = WorkflowHistory(
            decisions=[{"next_task": "md"}],
            results=[{"rmsd": 1.5}],
        )
        assert len(wh.decisions) == 1
        assert len(wh.results) == 1

    def test_from_raw_dict(self):
        raw = {
            "decisions": [{"x": 1}],
            "results": [{"y": 2}],
            "configurations": [],
            "key_items": [],
        }
        wh = WorkflowHistory.from_raw(raw)
        assert len(wh.decisions) == 1

    def test_from_raw_empty_list(self):
        wh = WorkflowHistory.from_raw([])
        assert wh.decisions == []

    def test_from_raw_instance(self):
        original = WorkflowHistory(decisions=[{"a": 1}])
        wh = WorkflowHistory.from_raw(original)
        assert wh is original

    def test_from_raw_invalid_type(self):
        wh = WorkflowHistory.from_raw("garbage")
        assert wh.decisions == []

    def test_from_raw_partial_dict(self):
        raw = {"decisions": [{"x": 1}]}
        wh = WorkflowHistory.from_raw(raw)
        assert len(wh.decisions) == 1
        assert wh.results == []

    def test_serialization(self):
        wh = WorkflowHistory(decisions=[{"task": "md"}])
        data = wh.model_dump()
        wh2 = WorkflowHistory(**data)
        assert wh == wh2


# ---------------------------------------------------------------------------
# Pipeline Metrics
# ---------------------------------------------------------------------------

class TestPipelineMetrics:
    def test_defaults(self):
        pm = PipelineMetrics()
        assert pm.decision_list == []
        assert pm.best_binder_energy == []

    def test_with_data(self):
        pm = PipelineMetrics(
            decision_list=[1, 2, 3],
            best_binder_energy=[-10.0, -15.0, None],
            best_binder_free_energy=[-12.5],
            best_binder_sequence=["ACDEF"],
            binder_rmsds=[1.5, None],
            binder_rmsfs=[0.8],
        )
        assert len(pm.decision_list) == 3
        assert pm.best_binder_energy[1] == -15.0
        assert pm.best_binder_sequence[0] == "ACDEF"
