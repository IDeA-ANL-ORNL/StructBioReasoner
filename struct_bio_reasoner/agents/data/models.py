"""
SQLAlchemy ORM models for StructBioReasoner persistence.

All 17 tables (9 decision + 8 scientific) are defined here using
SQLAlchemy 2.0 Mapped classes.  A custom ``JSONBCompat`` type dispatches
to native JSONB on PostgreSQL and to a JSON-as-text column on SQLite,
so the same models work in both production and test environments.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)
from sqlalchemy.types import TypeDecorator


# ---------------------------------------------------------------------------
# Cross-database JSON type
# ---------------------------------------------------------------------------

class JSONBCompat(TypeDecorator):
    """JSONB on PostgreSQL, JSON-as-text on SQLite."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value  # asyncpg handles native JSONB
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        if isinstance(value, str):
            return json.loads(value)
        return value


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ═══════════════════════════════════════════════════════════════════════════
# Decision / LLM History Tables (formerly DB 1)
# ═══════════════════════════════════════════════════════════════════════════

class SchemaVersion(Base):
    __tablename__ = "schema_version"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class Experiment(Base):
    __tablename__ = "experiments"

    experiment_id: Mapped[str] = mapped_column(String, primary_key=True)
    research_goal: Mapped[str] = mapped_column(Text, default="")
    config_snapshot: Mapped[Optional[Any]] = mapped_column(JSONBCompat(), nullable=True)
    num_directors: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String, default="running")

    directors: Mapped[list["DirectorRecord"]] = relationship(back_populates="experiment")


class DirectorRecord(Base):
    __tablename__ = "directors"

    director_id: Mapped[str] = mapped_column(String, primary_key=True)
    experiment_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("experiments.experiment_id"), nullable=True
    )
    external_label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    accelerator_ids: Mapped[Optional[Any]] = mapped_column(JSONBCompat(), nullable=True)
    target_protein: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config_snapshot: Mapped[Optional[Any]] = mapped_column(JSONBCompat(), nullable=True)
    launched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    terminated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    termination_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    experiment: Mapped[Optional["Experiment"]] = relationship(back_populates="directors")


class LLMCall(Base):
    __tablename__ = "llm_calls"

    call_id: Mapped[str] = mapped_column(String, primary_key=True)
    director_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("directors.director_id"), nullable=True
    )
    call_type: Mapped[str] = mapped_column(String, nullable=False)
    model_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    prompt_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parsed_output: Mapped[Optional[Any]] = mapped_column(JSONBCompat(), nullable=True)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class Decision(Base):
    __tablename__ = "decisions"

    decision_id: Mapped[str] = mapped_column(String, primary_key=True)
    llm_call_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("llm_calls.call_id"), nullable=True
    )
    director_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("directors.director_id"), nullable=True
    )
    iteration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    previous_task: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_task: Mapped[str] = mapped_column(Text, nullable=False)
    change_parameters: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class TaskPlan(Base):
    __tablename__ = "task_plans"

    plan_id: Mapped[str] = mapped_column(String, primary_key=True)
    decision_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("decisions.decision_id"), nullable=True
    )
    llm_call_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("llm_calls.call_id"), nullable=True
    )
    director_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("directors.director_id"), nullable=True
    )
    task_type: Mapped[str] = mapped_column(String, nullable=False)
    plan_model_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    plan_config: Mapped[Any] = mapped_column(JSONBCompat(), nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class TaskExecution(Base):
    __tablename__ = "task_executions"

    execution_id: Mapped[str] = mapped_column(String, primary_key=True)
    plan_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("task_plans.plan_id"), nullable=True
    )
    director_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("directors.director_id"), nullable=True
    )
    agent_key: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="running")
    input_kwargs: Mapped[Optional[Any]] = mapped_column(JSONBCompat(), nullable=True)
    result_data: Mapped[Optional[Any]] = mapped_column(JSONBCompat(), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class KeyItem(Base):
    __tablename__ = "key_items"

    item_id: Mapped[str] = mapped_column(String, primary_key=True)
    director_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("directors.director_id"), nullable=True
    )
    execution_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("task_executions.execution_id"), nullable=True
    )
    item_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    item_data: Mapped[Any] = mapped_column(JSONBCompat(), nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class ExecutiveAction(Base):
    __tablename__ = "executive_actions"

    action_id: Mapped[str] = mapped_column(String, primary_key=True)
    experiment_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("experiments.experiment_id"), nullable=True
    )
    director_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("directors.director_id"), nullable=True
    )
    llm_call_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("llm_calls.call_id"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    advice_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


# ═══════════════════════════════════════════════════════════════════════════
# Scientific Data Tables (formerly DB 2)
# ═══════════════════════════════════════════════════════════════════════════

class Sequence(Base):
    __tablename__ = "sequences"
    __table_args__ = (UniqueConstraint("sequence_hash"),)

    sequence_id: Mapped[str] = mapped_column(String, primary_key=True)
    sequence: Mapped[str] = mapped_column(Text, nullable=False)
    sequence_hash: Mapped[str] = mapped_column(String, nullable=False)
    length: Mapped[int] = mapped_column(Integer, nullable=False)
    target_sequence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    origin: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    parent_sequence_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("sequences.sequence_id"), nullable=True
    )
    scaffold_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    experiment_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    director_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    design_round: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class QCResult(Base):
    __tablename__ = "qc_results"

    qc_id: Mapped[str] = mapped_column(String, primary_key=True)
    sequence_id: Mapped[str] = mapped_column(
        String, ForeignKey("sequences.sequence_id"), nullable=False
    )
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    diversity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_repeat_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    net_charge: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    charge_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hydrophobic_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_appearance_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bad_motifs_found: Mapped[Optional[Any]] = mapped_column(JSONBCompat(), nullable=True)
    bad_terminus: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class FoldingResult(Base):
    __tablename__ = "folding_results"

    fold_id: Mapped[str] = mapped_column(String, primary_key=True)
    sequence_id: Mapped[str] = mapped_column(
        String, ForeignKey("sequences.sequence_id"), nullable=False
    )
    fold_backend: Mapped[str] = mapped_column(String, nullable=False)
    structure_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    aggregate_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ptm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    iptm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    per_chain_ptm: Mapped[Optional[Any]] = mapped_column(JSONBCompat(), nullable=True)
    per_chain_pair_iptm: Mapped[Optional[Any]] = mapped_column(JSONBCompat(), nullable=True)
    has_inter_chain_clashes: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    diffusion_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    constraints_used: Mapped[Optional[Any]] = mapped_column(JSONBCompat(), nullable=True)
    trial_label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class EnergyResult(Base):
    __tablename__ = "energy_results"

    energy_id: Mapped[str] = mapped_column(String, primary_key=True)
    fold_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("folding_results.fold_id"), nullable=True
    )
    sequence_id: Mapped[str] = mapped_column(
        String, ForeignKey("sequences.sequence_id"), nullable=False
    )
    energy_method: Mapped[str] = mapped_column(String, nullable=False)
    energy_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    n_interface_contacts: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    passed_threshold: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    energy_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    simulation_id: Mapped[str] = mapped_column(String, primary_key=True)
    fold_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("folding_results.fold_id"), nullable=True
    )
    sequence_id: Mapped[str] = mapped_column(
        String, ForeignKey("sequences.sequence_id"), nullable=False
    )
    sim_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    topology_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trajectory_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    solvent_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    equil_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    prod_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    platform: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sim_time_ns: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    build_success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    sim_success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class TrajectoryAnalysis(Base):
    __tablename__ = "trajectory_analyses"

    analysis_id: Mapped[str] = mapped_column(String, primary_key=True)
    simulation_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("simulation_runs.simulation_id"), nullable=True
    )
    sequence_id: Mapped[str] = mapped_column(
        String, ForeignKey("sequences.sequence_id"), nullable=False
    )
    analysis_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rmsd_mean: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rmsd_std: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rmsf_mean: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rmsf_per_residue: Mapped[Optional[Any]] = mapped_column(JSONBCompat(), nullable=True)
    radius_of_gyration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    n_frames: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    binding_site_residues: Mapped[Optional[Any]] = mapped_column(JSONBCompat(), nullable=True)
    contact_frequencies: Mapped[Optional[Any]] = mapped_column(JSONBCompat(), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class FreeEnergyResult(Base):
    __tablename__ = "free_energy_results"

    fe_id: Mapped[str] = mapped_column(String, primary_key=True)
    simulation_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("simulation_runs.simulation_id"), nullable=True
    )
    sequence_id: Mapped[str] = mapped_column(
        String, ForeignKey("sequences.sequence_id"), nullable=False
    )
    method: Mapped[str] = mapped_column(String, default="mmpbsa")
    free_energy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class Embedding(Base):
    __tablename__ = "embeddings"

    embedding_id: Mapped[str] = mapped_column(String, primary_key=True)
    sequence_id: Mapped[str] = mapped_column(
        String, ForeignKey("sequences.sequence_id"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    embedding_dim: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    embedding_vector: Mapped[Any] = mapped_column(JSONBCompat(), nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
