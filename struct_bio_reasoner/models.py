"""
Central Pydantic models for StructBioReasoner.

All LLM output schemas, workflow data structures, and pipeline metrics
live here. Downstream modules (prompts/, agents/, utils/) import from
this module — it must NOT import from them.
"""

from __future__ import annotations

import sys
if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """Backport of StrEnum for Python <3.11."""
from typing import Any

from pydantic import BaseModel, Field, create_model


# ---------------------------------------------------------------------------
# Task name enum — single source of truth for valid task identifiers.
# Add new entries here when adding a new task type.
# ---------------------------------------------------------------------------

class TaskName(StrEnum):
    COMPUTATIONAL_DESIGN = "computational_design"
    MOLECULAR_DYNAMICS = "molecular_dynamics"
    STRUCTURE_PREDICTION = "structure_prediction"
    ANALYSIS = "analysis"
    FREE_ENERGY = "free_energy"
    RAG = "rag"
    STARTING = "starting"
    STOP = "stop"


# Tasks that have config/plan models (excludes bootstrapping and terminal)
RUNNABLE_TASKS: frozenset[TaskName] = frozenset(TaskName) - {
    TaskName.STARTING,
    TaskName.STOP,
}


# ---------------------------------------------------------------------------
# LLM Output Models (extracted from pydantic_ai_agent.py)
# ---------------------------------------------------------------------------

class Recommendation(BaseModel):
    """Schema for the reasoner's next-task recommendation."""
    next_task: TaskName = Field(
        description="Name of the next task to run",
    )
    change_parameters: bool = Field(
        description="Whether to change parameters from the previous run. "
        "Set true when results suggest current parameters are suboptimal",
    )
    rationale: str = Field(
        description="Detailed explanation of why this task and parameter choice "
        "were recommended, referencing recent results and history",
    )


class RecommendationResult(BaseModel):
    """Wrapper returned by generate_recommendation Academy actions."""
    previous_run: str
    recommendation: Recommendation


class QCKwargs(BaseModel):
    max_repeat: int = Field(default=3)
    max_appearance_ratio: float = Field(default=0.5)
    max_charge: int = Field(default=5)
    max_charge_ratio: float = Field(default=0.5)
    max_hydrophobic_ratio: float = Field(default=0.6)
    min_diversity: int = Field(default=3)


class Constraint(BaseModel):
    residues_bind: list[str] = Field(default_factory=list)


# --- Config models (one per task type) ---

class ComputationalDesignConfig(BaseModel):
    binder_sequence: str = Field(
        description="Full amino acid sequence for the binder to optimize",
    )
    num_rounds: int = Field(
        default=2,
        description="Number of BindCraft optimization rounds to run",
    )
    constraints: dict = Field(
        default_factory=dict,
        description="Binding constraints specifying target residues to interact with",
    )
    remodel_indices: list[int] = Field(
        default_factory=list,
        description="Residue indices to remodel. Empty list means auto-detect from structure",
    )


class MolecularDynamicsConfig(BaseModel):
    simulation_paths: list[str] = Field(
        description="Paths to input PDB/structure files for simulation",
    )
    root_output_path: str = Field(
        description="Root directory where simulation outputs will be written",
    )
    steps: int = Field(
        description="Number of simulation timesteps to run (e.g. 10000 for short, 1000000+ for production)",
    )


class StructurePredictionConfig(BaseModel):
    sequences: list[list[str]] = Field(
        description="List of sequence pairs [[target_seq, partner_seq], ...] to fold. "
        "Combined length of each pair must be <1500 residues",
    )
    names: list[str] = Field(
        description="Human-readable names for each sequence pair (e.g. 'target_partnerName')",
    )


class AnalysisConfig(BaseModel):
    data_type: str = Field(
        description="Input data type: 'static' (PDB files), 'dynamic' (trajectories), or 'both'",
    )
    analysis_type: str = Field(
        description="Analysis rigor: 'basic' (RMSD/RMSF/Rg or contacts), "
        "'advanced' (hotspot analysis), or 'both'",
    )
    distance_cutoff: float = Field(
        default=8.0,
        description="Alpha-carbon distance cutoff in angstroms for contact detection",
    )


class FreeEnergyConfig(BaseModel):
    simulation_paths: list[str] = Field(
        description="Paths to simulation trajectory files for free energy calculation (MM-PBSA)",
    )


class RAGConfig(BaseModel):
    prompt: str = Field(
        description="Optimized prompt text for the HiPerRAG literature mining system",
    )


# --- Config registry ---

CONFIG_MODELS: dict[str, type[BaseModel]] = {
    TaskName.COMPUTATIONAL_DESIGN: ComputationalDesignConfig,
    TaskName.MOLECULAR_DYNAMICS: MolecularDynamicsConfig,
    TaskName.STRUCTURE_PREDICTION: StructurePredictionConfig,
    TaskName.ANALYSIS: AnalysisConfig,
    TaskName.FREE_ENERGY: FreeEnergyConfig,
    TaskName.RAG: RAGConfig,
}


# --- Plan models (auto-generated: config + rationale) ---

def _make_plan_model(config_cls: type[BaseModel]) -> type[BaseModel]:
    """Create a Plan model wrapping a Config model with a rationale field."""
    plan_name = config_cls.__name__.replace("Config", "Plan")
    return create_model(
        plan_name,
        new_config=(config_cls, ...),
        rationale=(str, Field(description="Explanation of why these parameters were chosen")),
    )


PLAN_MODELS: dict[str, type[BaseModel]] = {
    name: _make_plan_model(cls) for name, cls in CONFIG_MODELS.items()
}

# Convenience aliases for direct imports (e.g. type hints in tests)
ComputationalDesignPlan = PLAN_MODELS[TaskName.COMPUTATIONAL_DESIGN]
MolecularDynamicsPlan = PLAN_MODELS[TaskName.MOLECULAR_DYNAMICS]
StructurePredictionPlan = PLAN_MODELS[TaskName.STRUCTURE_PREDICTION]
AnalysisPlan = PLAN_MODELS[TaskName.ANALYSIS]
FreeEnergyPlan = PLAN_MODELS[TaskName.FREE_ENERGY]
RAGPlan = PLAN_MODELS[TaskName.RAG]


def build_config_master() -> dict[str, dict]:
    """Replace hand-written string-type dicts with model JSON schemas."""
    return {name: cls.model_json_schema() for name, cls in CONFIG_MODELS.items()}


config_master = build_config_master()


# ---------------------------------------------------------------------------
# Registry validation — fail fast at import time if registries diverge
# ---------------------------------------------------------------------------

def _validate_registries() -> None:
    config_keys = set(CONFIG_MODELS.keys())
    plan_keys = set(PLAN_MODELS.keys())
    if config_keys != plan_keys:
        missing = config_keys - plan_keys
        extra = plan_keys - config_keys
        raise RuntimeError(
            f"CONFIG_MODELS / PLAN_MODELS mismatch. "
            f"Missing from PLAN_MODELS: {missing}. Extra: {extra}."
        )
    for task in RUNNABLE_TASKS:
        if task not in CONFIG_MODELS:
            raise RuntimeError(
                f"TaskName.{task.name} is in RUNNABLE_TASKS but missing from CONFIG_MODELS. "
                f"Add a Config model for it or remove it from TaskName."
            )

_validate_registries()


# ---------------------------------------------------------------------------
# Workflow History
# ---------------------------------------------------------------------------

class WorkflowHistory(BaseModel):
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    results: list[dict[str, Any]] = Field(default_factory=list)
    configurations: list[dict[str, Any]] = Field(default_factory=list)
    key_items: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def from_raw(cls, data: WorkflowHistory | dict[str, Any] | list) -> WorkflowHistory:
        """Coerce from plain dict, empty list, or existing instance."""
        if isinstance(data, cls):
            return data
        if isinstance(data, list):
            if len(data) == 0:
                return cls()
            # Merge a list of WorkflowHistory-shaped dicts into one
            merged = cls()
            for entry in data:
                if isinstance(entry, dict):
                    for field_name in cls.model_fields:
                        getattr(merged, field_name).extend(entry.get(field_name, []))
                elif isinstance(entry, cls):
                    for field_name in cls.model_fields:
                        getattr(merged, field_name).extend(getattr(entry, field_name))
            return merged
        if isinstance(data, dict):
            return cls(**{k: data.get(k, []) for k in cls.model_fields})
        return cls()


# ---------------------------------------------------------------------------
# Pipeline Metrics
# ---------------------------------------------------------------------------

class PipelineMetrics(BaseModel):
    decision_list: list[int] = Field(default_factory=list)
    best_binder_energy: list[float | None] = Field(default_factory=list)
    best_binder_free_energy: list[float | None] = Field(default_factory=list)
    best_binder_sequence: list[str | None] = Field(default_factory=list)
    binder_rmsds: list[float | None] = Field(default_factory=list)
    binder_rmsfs: list[float | None] = Field(default_factory=list)
