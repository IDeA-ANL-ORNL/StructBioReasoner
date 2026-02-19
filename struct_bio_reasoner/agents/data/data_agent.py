"""
DataAgent: Academy agent managing persistence via SQLAlchemy ORM.

Launched alongside worker agents by the Director. Accepts structured
events via ``record_event`` / ``record_scientific_event`` actions and
writes them to the database in batches. Provides query actions for the
Executive and prompt builder.

Supports PostgreSQL (via asyncpg) in production and SQLite (via
aiosqlite) for testing.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from academy.agent import Agent, action

from .events import EventType, ScientificEventType
from .models import (
    Base,
    Decision,
    DirectorRecord,
    Embedding,
    EnergyResult,
    ExecutiveAction,
    Experiment,
    FoldingResult,
    FreeEnergyResult,
    KeyItem,
    LLMCall,
    QCResult,
    SchemaVersion,
    Sequence,
    SimulationRun,
    TaskExecution,
    TaskPlan,
    TrajectoryAnalysis,
)

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DataAgent(Agent):
    """Academy agent managing all database operations for the workflow."""

    def __init__(
        self,
        database_url: str = "sqlite+aiosqlite:///data.db",
        batch_size: int = 50,
        flush_interval: float = 2.0,
    ) -> None:
        self.database_url = database_url
        self.batch_size = batch_size
        self.flush_interval = flush_interval

        self._buffer: list[dict[str, Any]] = []

        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._flush_task: asyncio.Task | None = None

        super().__init__()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def agent_on_startup(self) -> None:
        self._engine = create_async_engine(self.database_url)
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False
        )
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # Seed schema version (idempotent)
        async with self._session_factory() as session:
            async with session.begin():
                existing = await session.get(SchemaVersion, 1)
                if existing is None:
                    session.add(SchemaVersion(version=1))
        self._flush_task = asyncio.create_task(self._periodic_flush())
        logger.info("DataAgent started: %s", self.database_url)

    async def agent_on_shutdown(self) -> None:
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush()
        if self._engine:
            await self._engine.dispose()
        logger.info("DataAgent shut down")

    # ------------------------------------------------------------------
    # Write Path: Decision Events
    # ------------------------------------------------------------------

    @action
    async def record_event(self, event: dict[str, Any]) -> None:
        """Accept a workflow event for batched insertion.

        Called by Director.query_reasoner(), Director.tool_call(),
        and TestExecutive at well-defined boundaries.
        """
        self._buffer.append(event)
        if len(self._buffer) >= self.batch_size:
            await self._flush()

    # ------------------------------------------------------------------
    # Write Path: Scientific Events
    # ------------------------------------------------------------------

    @action
    async def record_scientific_event(self, event: dict[str, Any]) -> None:
        """Accept a scientific data event for batched insertion.

        Called by worker agents (BindCraftCoordinator, MDAgent, etc.)
        after producing results.
        """
        self._buffer.append(event)
        if len(self._buffer) >= self.batch_size:
            await self._flush()

    # ------------------------------------------------------------------
    # Read Path: Decision Queries
    # ------------------------------------------------------------------

    @action
    async def get_director_history(
        self,
        director_id: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Reconstruct WorkflowHistory for a Director."""
        async with self._session_factory() as session:
            decisions = (
                await session.execute(
                    select(
                        Decision.next_task,
                        Decision.rationale,
                        Decision.change_parameters,
                    )
                    .where(Decision.director_id == director_id)
                    .order_by(Decision.created_at.desc())
                    .limit(limit)
                )
            ).all()

            results = (
                await session.execute(
                    select(TaskExecution.result_data)
                    .where(
                        TaskExecution.director_id == director_id,
                        TaskExecution.status == "completed",
                    )
                    .order_by(TaskExecution.completed_at.desc())
                    .limit(limit)
                )
            ).all()

            configs = (
                await session.execute(
                    select(TaskPlan.plan_config)
                    .where(TaskPlan.director_id == director_id)
                    .order_by(TaskPlan.created_at.desc())
                    .limit(limit)
                )
            ).all()

            items = (
                await session.execute(
                    select(KeyItem.item_data)
                    .where(KeyItem.director_id == director_id)
                    .order_by(KeyItem.created_at.desc())
                    .limit(limit)
                )
            ).all()

        return {
            "decisions": [
                json.dumps({
                    "next_task": r.next_task,
                    "rationale": r.rationale,
                    "change_parameters": r.change_parameters,
                })
                for r in reversed(decisions)
            ],
            "results": [r.result_data for r in reversed(results)],
            "configurations": [r.plan_config for r in reversed(configs)],
            "key_items": [r.item_data for r in reversed(items)],
        }

    @action
    async def get_experiment_summary(
        self,
        experiment_id: str,
    ) -> dict[str, Any]:
        """Aggregate statistics across all Directors in an experiment."""
        async with self._session_factory() as session:
            stmt = (
                select(
                    func.count(func.distinct(DirectorRecord.director_id)).label(
                        "num_directors"
                    ),
                    func.count(TaskExecution.execution_id).label("total_tasks"),
                    func.sum(
                        case(
                            (TaskExecution.status == "completed", 1),
                            else_=0,
                        )
                    ).label("completed"),
                    func.sum(
                        case(
                            (TaskExecution.status == "failed", 1),
                            else_=0,
                        )
                    ).label("failed"),
                    func.avg(
                        case(
                            (TaskExecution.status == "completed", TaskExecution.duration_ms),
                            else_=None,
                        )
                    ).label("avg_duration_ms"),
                    func.sum(LLMCall.prompt_tokens).label("total_prompt_tokens"),
                    func.sum(LLMCall.completion_tokens).label(
                        "total_completion_tokens"
                    ),
                )
                .select_from(DirectorRecord)
                .outerjoin(
                    TaskExecution,
                    TaskExecution.director_id == DirectorRecord.director_id,
                )
                .outerjoin(
                    LLMCall, LLMCall.director_id == DirectorRecord.director_id
                )
                .where(DirectorRecord.experiment_id == experiment_id)
            )
            row = (await session.execute(stmt)).one_or_none()

        if row is None:
            return {}

        return {
            "num_directors": row.num_directors,
            "total_tasks": row.total_tasks,
            "completed": row.completed,
            "failed": row.failed,
            "avg_duration_ms": row.avg_duration_ms,
            "total_prompt_tokens": row.total_prompt_tokens,
            "total_completion_tokens": row.total_completion_tokens,
        }

    @action
    async def get_cross_director_insights(
        self,
        experiment_id: str,
    ) -> dict[str, Any]:
        """Provide the Executive with cross-Director comparative data."""
        async with self._session_factory() as session:
            stmt = (
                select(
                    DirectorRecord.external_label,
                    Decision.previous_task,
                    Decision.next_task,
                    func.count().label("count"),
                )
                .select_from(Decision)
                .join(
                    DirectorRecord,
                    DirectorRecord.director_id == Decision.director_id,
                )
                .where(DirectorRecord.experiment_id == experiment_id)
                .group_by(
                    DirectorRecord.external_label,
                    Decision.previous_task,
                    Decision.next_task,
                )
                .order_by(func.count().desc())
            )
            rows = (await session.execute(stmt)).all()

        transitions = [
            {
                "director": r.external_label,
                "previous_task": r.previous_task,
                "next_task": r.next_task,
                "count": r.count,
            }
            for r in rows
        ]
        return {"task_transitions": transitions}

    @action
    async def get_recovery_state(
        self,
        director_id: str,
    ) -> dict[str, Any]:
        """Provide state needed to resume a Director after crash."""
        async with self._session_factory() as session:
            last_decision = (
                await session.execute(
                    select(Decision.next_task, Decision.rationale)
                    .where(Decision.director_id == director_id)
                    .order_by(Decision.created_at.desc())
                    .limit(1)
                )
            ).one_or_none()

            last_execution = (
                await session.execute(
                    select(
                        TaskExecution.agent_key,
                        TaskExecution.status,
                        TaskExecution.result_data,
                    )
                    .where(TaskExecution.director_id == director_id)
                    .order_by(TaskExecution.started_at.desc())
                    .limit(1)
                )
            ).one_or_none()

        return {
            "last_decision": (
                {"next_task": last_decision.next_task, "rationale": last_decision.rationale}
                if last_decision
                else None
            ),
            "last_execution": (
                {
                    "agent_key": last_execution.agent_key,
                    "status": last_execution.status,
                    "result_data": last_execution.result_data,
                }
                if last_execution
                else None
            ),
        }

    # ------------------------------------------------------------------
    # Read Path: Scientific Queries
    # ------------------------------------------------------------------

    @action
    async def get_sequence_lifecycle(
        self,
        sequence_id: str | None = None,
        limit: int = 20,
        order_by: str = "free_energy",
    ) -> list[dict[str, Any]]:
        """Query the sequence lifecycle — Python-side joins for
        cross-database compatibility (PostgreSQL and SQLite)."""
        async with self._session_factory() as session:
            if sequence_id:
                seq_rows = (
                    await session.execute(
                        select(Sequence).where(
                            Sequence.sequence_id == sequence_id
                        )
                    )
                ).scalars().all()
            else:
                seq_rows = (
                    await session.execute(select(Sequence))
                ).scalars().all()

            results: list[dict[str, Any]] = []
            for s in seq_rows:
                row: dict[str, Any] = {
                    "sequence_id": s.sequence_id,
                    "sequence": s.sequence,
                    "length": s.length,
                    "origin": s.origin,
                    "scaffold_type": s.scaffold_type,
                    "design_round": s.design_round,
                    "designed_at": s.created_at,
                }

                # QC (latest)
                qc = (
                    await session.execute(
                        select(QCResult)
                        .where(QCResult.sequence_id == s.sequence_id)
                        .order_by(QCResult.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                row["qc_passed"] = qc.passed if qc else None
                row["qc_diversity"] = qc.diversity if qc else None
                row["qc_net_charge"] = qc.net_charge if qc else None
                row["qc_hydrophobic_ratio"] = qc.hydrophobic_ratio if qc else None

                # Best fold (highest iptm)
                f = (
                    await session.execute(
                        select(FoldingResult)
                        .where(FoldingResult.sequence_id == s.sequence_id)
                        .order_by(FoldingResult.iptm.desc().nulls_last())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                row["fold_id"] = f.fold_id if f else None
                row["structure_path"] = f.structure_path if f else None
                row["iptm"] = f.iptm if f else None
                row["ptm"] = f.ptm if f else None
                row["chai_score"] = f.aggregate_score if f else None
                row["has_inter_chain_clashes"] = f.has_inter_chain_clashes if f else None

                # Energy (from best fold)
                e = None
                if f:
                    e = (
                        await session.execute(
                            select(EnergyResult)
                            .where(EnergyResult.fold_id == f.fold_id)
                            .order_by(EnergyResult.energy_score.asc())
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                row["contact_energy"] = e.energy_score if e else None
                row["n_interface_contacts"] = e.n_interface_contacts if e else None
                row["energy_passed"] = e.passed_threshold if e else None

                # Best simulation
                sim = (
                    await session.execute(
                        select(SimulationRun)
                        .where(
                            SimulationRun.sequence_id == s.sequence_id,
                            SimulationRun.sim_success.is_(True),
                        )
                        .order_by(SimulationRun.prod_steps.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                row["simulation_id"] = sim.simulation_id if sim else None
                row["sim_time_ns"] = sim.sim_time_ns if sim else None
                row["prod_steps"] = sim.prod_steps if sim else None

                # Trajectory analysis
                ta = None
                if sim:
                    ta = (
                        await session.execute(
                            select(TrajectoryAnalysis)
                            .where(
                                TrajectoryAnalysis.simulation_id == sim.simulation_id,
                            )
                            .order_by(TrajectoryAnalysis.created_at.desc())
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                row["rmsd_mean"] = ta.rmsd_mean if ta else None
                row["rmsd_std"] = ta.rmsd_std if ta else None
                row["rmsf_mean"] = ta.rmsf_mean if ta else None
                row["radius_of_gyration"] = ta.radius_of_gyration if ta else None
                row["binding_site_residues"] = ta.binding_site_residues if ta else None
                row["analysis_confidence"] = ta.confidence_score if ta else None

                # Free energy
                fe = None
                if sim:
                    fe = (
                        await session.execute(
                            select(FreeEnergyResult)
                            .where(
                                FreeEnergyResult.simulation_id == sim.simulation_id,
                                FreeEnergyResult.success.is_(True),
                            )
                            .order_by(FreeEnergyResult.free_energy.asc())
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                row["free_energy"] = fe.free_energy if fe else None

                # Embedding
                emb = (
                    await session.execute(
                        select(Embedding)
                        .where(Embedding.sequence_id == s.sequence_id)
                        .order_by(Embedding.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                row["embedding_model"] = emb.model_name if emb else None
                row["embedding_coords"] = emb.embedding_vector if emb else None

                results.append(row)

            # Sort and limit
            allowed_order = {
                "free_energy", "contact_energy", "iptm",
                "rmsd_mean", "designed_at",
            }
            if order_by not in allowed_order:
                order_by = "free_energy"

            results.sort(
                key=lambda r: (
                    r.get(order_by) is None,
                    r.get(order_by),
                ),
            )
            if not sequence_id:
                results = results[:limit]

            return results

    @action
    async def get_top_binders(
        self,
        limit: int = 20,
        max_free_energy: float | None = None,
    ) -> list[dict[str, Any]]:
        """Return the best binder sequences by free energy."""
        rows = await self.get_sequence_lifecycle(
            limit=limit, order_by="free_energy"
        )
        binders = [r for r in rows if r.get("free_energy") is not None]
        if max_free_energy is not None:
            binders = [r for r in binders if r["free_energy"] < max_free_energy]
        return [
            {
                "sequence": r["sequence"],
                "length": r["length"],
                "scaffold_type": r["scaffold_type"],
                "contact_energy": r["contact_energy"],
                "free_energy": r["free_energy"],
                "rmsd_mean": r["rmsd_mean"],
                "iptm": r["iptm"],
                "design_round": r["design_round"],
            }
            for r in binders[:limit]
        ]

    @action
    async def get_design_round_yield(self) -> list[dict[str, Any]]:
        """How many sequences pass each stage per design round."""
        async with self._session_factory() as session:
            # Get all sequences with their design rounds
            seqs = (
                await session.execute(
                    select(Sequence.sequence_id, Sequence.design_round)
                )
            ).all()

            rounds: dict[int, dict[str, int]] = {}
            for seq_id, design_round in seqs:
                dr = design_round or 0
                if dr not in rounds:
                    rounds[dr] = {
                        "design_round": dr,
                        "generated": 0,
                        "passed_qc": 0,
                        "passed_energy": 0,
                        "simulated": 0,
                        "good_fe": 0,
                    }
                rounds[dr]["generated"] += 1

                qc = (
                    await session.execute(
                        select(QCResult.passed)
                        .where(QCResult.sequence_id == seq_id)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if qc:
                    rounds[dr]["passed_qc"] += 1

                en = (
                    await session.execute(
                        select(EnergyResult.passed_threshold)
                        .where(EnergyResult.sequence_id == seq_id)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if en:
                    rounds[dr]["passed_energy"] += 1

                sim = (
                    await session.execute(
                        select(SimulationRun.sim_success)
                        .where(
                            SimulationRun.sequence_id == seq_id,
                            SimulationRun.sim_success.is_(True),
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if sim:
                    rounds[dr]["simulated"] += 1

                fe = (
                    await session.execute(
                        select(FreeEnergyResult.free_energy)
                        .where(
                            FreeEnergyResult.sequence_id == seq_id,
                            FreeEnergyResult.success.is_(True),
                            FreeEnergyResult.free_energy < -10,
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if fe is not None:
                    rounds[dr]["good_fe"] += 1

        return sorted(rounds.values(), key=lambda r: r["design_round"])

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @action
    async def export_to_parquet(
        self,
        output_dir: str,
        experiment_id: str | None = None,
    ) -> list[str]:
        """Export tables to Parquet files for offline analysis.

        Requires pandas and pyarrow to be installed.
        """
        from pathlib import Path

        import pandas as pd

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []

        table_models = [
            ("experiments", Experiment),
            ("directors", DirectorRecord),
            ("llm_calls", LLMCall),
            ("decisions", Decision),
            ("task_plans", TaskPlan),
            ("task_executions", TaskExecution),
            ("key_items", KeyItem),
            ("executive_actions", ExecutiveAction),
            ("sequences", Sequence),
            ("qc_results", QCResult),
            ("folding_results", FoldingResult),
            ("energy_results", EnergyResult),
            ("simulation_runs", SimulationRun),
            ("trajectory_analyses", TrajectoryAnalysis),
            ("free_energy_results", FreeEnergyResult),
            ("embeddings", Embedding),
        ]

        async with self._session_factory() as session:
            for name, model in table_models:
                stmt = select(model)
                result = await session.execute(stmt)
                rows = result.scalars().all()
                if rows:
                    records = [
                        {c.key: getattr(r, c.key) for c in model.__table__.columns}
                        for r in rows
                    ]
                    df = pd.DataFrame(records)
                else:
                    df = pd.DataFrame()
                path = str(out / f"{name}.parquet")
                df.to_parquet(path, index=False)
                paths.append(path)

        logger.info("Exported %d tables to %s", len(paths), output_dir)
        return paths

    # ------------------------------------------------------------------
    # Internal: Flush Logic
    # ------------------------------------------------------------------

    async def _periodic_flush(self) -> None:
        while True:
            await asyncio.sleep(self.flush_interval)
            await self._flush()

    async def _flush(self) -> None:
        if not self._buffer:
            return

        events = self._buffer.copy()
        self._buffer.clear()

        async with self._session_factory() as session:
            async with session.begin():
                for event in events:
                    try:
                        et = event.get("event_type", "")
                        handler = self._ALL_HANDLERS.get(et)
                        if handler:
                            await handler(self, session, event)
                        else:
                            logger.warning("Unknown event type: %s", et)
                    except Exception:
                        logger.exception(
                            "Failed to write event %s",
                            event.get("event_type"),
                        )

    # ------------------------------------------------------------------
    # Internal: Decision Event Handlers
    # ------------------------------------------------------------------

    async def _handle_experiment_start(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        session.add(
            Experiment(
                experiment_id=p["experiment_id"],
                research_goal=p.get("research_goal", ""),
                config_snapshot=p.get("config_snapshot"),
                num_directors=p.get("num_directors"),
            )
        )

    async def _handle_experiment_end(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        await session.execute(
            update(Experiment)
            .where(Experiment.experiment_id == p["experiment_id"])
            .values(ended_at=_utcnow(), status=p.get("status", "completed"))
        )

    async def _handle_director_start(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        session.add(
            DirectorRecord(
                director_id=event["director_id"],
                experiment_id=event.get("experiment_id", ""),
                external_label=p.get("external_label", ""),
                accelerator_ids=p.get("accelerator_ids"),
                target_protein=p.get("target_protein", ""),
                config_snapshot=p.get("config_snapshot"),
            )
        )

    async def _handle_director_end(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        await session.execute(
            update(DirectorRecord)
            .where(DirectorRecord.director_id == event["director_id"])
            .values(
                terminated_at=_utcnow(),
                termination_reason=p.get("reason", "completed"),
            )
        )

    async def _handle_llm_call(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        session.add(
            LLMCall(
                call_id=p.get("call_id", _new_id()),
                director_id=event["director_id"],
                call_type=p["call_type"],
                model_name=p.get("model_name"),
                prompt_text=p.get("prompt_text"),
                response_text=p.get("response_text"),
                parsed_output=p.get("parsed_output"),
                temperature=p.get("temperature"),
                max_tokens=p.get("max_tokens"),
                prompt_tokens=p.get("prompt_tokens"),
                completion_tokens=p.get("completion_tokens"),
                latency_ms=p.get("latency_ms"),
                error=p.get("error"),
            )
        )

    async def _handle_decision(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        session.add(
            Decision(
                decision_id=p.get("decision_id", _new_id()),
                llm_call_id=p.get("llm_call_id"),
                director_id=event["director_id"],
                iteration=p.get("iteration"),
                previous_task=p.get("previous_task"),
                next_task=p["next_task"],
                change_parameters=p.get("change_parameters"),
                rationale=p.get("rationale"),
            )
        )

    async def _handle_plan(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        session.add(
            TaskPlan(
                plan_id=p.get("plan_id", _new_id()),
                decision_id=p.get("decision_id"),
                llm_call_id=p.get("llm_call_id"),
                director_id=event["director_id"],
                task_type=p["task_type"],
                plan_model_name=p.get("plan_model_name"),
                plan_config=p["plan_config"],
                rationale=p.get("rationale"),
            )
        )

    async def _handle_execution_start(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        session.add(
            TaskExecution(
                execution_id=p.get("execution_id", _new_id()),
                plan_id=p.get("plan_id"),
                director_id=event["director_id"],
                agent_key=p["agent_key"],
                status="running",
                input_kwargs=p.get("input_kwargs"),
            )
        )

    async def _handle_execution_end(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        await session.execute(
            update(TaskExecution)
            .where(TaskExecution.execution_id == p["execution_id"])
            .values(
                status=p.get("status", "completed"),
                result_data=p.get("result_data"),
                error=p.get("error"),
                completed_at=_utcnow(),
                duration_ms=p.get("duration_ms"),
            )
        )

    async def _handle_key_item(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        session.add(
            KeyItem(
                item_id=_new_id(),
                director_id=event["director_id"],
                execution_id=p.get("execution_id"),
                item_type=p.get("item_type"),
                item_data=p["item_data"],
            )
        )

    async def _handle_executive_action(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        session.add(
            ExecutiveAction(
                action_id=_new_id(),
                experiment_id=event.get("experiment_id", ""),
                director_id=event["director_id"],
                llm_call_id=p.get("llm_call_id"),
                action_type=p["action_type"],
                advice_text=p.get("advice_text"),
                status_snapshot=p.get("status_snapshot"),
            )
        )

    # ------------------------------------------------------------------
    # Internal: Scientific Event Handlers
    # ------------------------------------------------------------------

    async def _handle_sequence_generated(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        seq = p["sequence"]
        seq_hash = hashlib.sha256(seq.encode()).hexdigest()
        # Check-then-skip for dedup (cross-DB compatible)
        existing = (
            await session.execute(
                select(Sequence.sequence_id).where(
                    Sequence.sequence_hash == seq_hash
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return
        session.add(
            Sequence(
                sequence_id=p.get("sequence_id", _new_id()),
                sequence=seq,
                sequence_hash=seq_hash,
                length=len(seq),
                target_sequence=p.get("target_sequence"),
                origin=p.get("origin"),
                parent_sequence_id=p.get("parent_sequence_id"),
                scaffold_type=p.get("scaffold_type"),
                experiment_id=event.get("experiment_id"),
                director_id=event.get("director_id"),
                design_round=p.get("design_round"),
            )
        )

    async def _handle_qc_result(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        session.add(
            QCResult(
                qc_id=_new_id(),
                sequence_id=p["sequence_id"],
                passed=p["passed"],
                diversity=p.get("diversity"),
                max_repeat_length=p.get("max_repeat_length"),
                net_charge=p.get("net_charge"),
                charge_ratio=p.get("charge_ratio"),
                hydrophobic_ratio=p.get("hydrophobic_ratio"),
                max_appearance_ratio=p.get("max_appearance_ratio"),
                bad_motifs_found=p.get("bad_motifs_found"),
                bad_terminus=p.get("bad_terminus"),
            )
        )

    async def _handle_folding_result(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        session.add(
            FoldingResult(
                fold_id=p.get("fold_id", _new_id()),
                sequence_id=p["sequence_id"],
                fold_backend=p["fold_backend"],
                structure_path=p.get("structure_path"),
                model_index=p.get("model_index"),
                aggregate_score=p.get("aggregate_score"),
                ptm=p.get("ptm"),
                iptm=p.get("iptm"),
                per_chain_ptm=p.get("per_chain_ptm"),
                per_chain_pair_iptm=p.get("per_chain_pair_iptm"),
                has_inter_chain_clashes=p.get("has_inter_chain_clashes"),
                diffusion_steps=p.get("diffusion_steps"),
                constraints_used=p.get("constraints_used"),
                trial_label=p.get("trial_label"),
            )
        )

    async def _handle_energy_result(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        session.add(
            EnergyResult(
                energy_id=_new_id(),
                fold_id=p.get("fold_id"),
                sequence_id=p["sequence_id"],
                energy_method=p["energy_method"],
                energy_score=p.get("energy_score"),
                n_interface_contacts=p.get("n_interface_contacts"),
                passed_threshold=p.get("passed_threshold"),
                energy_threshold=p.get("energy_threshold"),
            )
        )

    async def _handle_simulation_run(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        session.add(
            SimulationRun(
                simulation_id=p.get("simulation_id", _new_id()),
                fold_id=p.get("fold_id"),
                sequence_id=p["sequence_id"],
                sim_path=p.get("sim_path"),
                topology_path=p.get("topology_path"),
                trajectory_path=p.get("trajectory_path"),
                solvent_model=p.get("solvent_model"),
                equil_steps=p.get("equil_steps"),
                prod_steps=p.get("prod_steps"),
                platform=p.get("platform"),
                sim_time_ns=p.get("sim_time_ns"),
                build_success=p.get("build_success"),
                sim_success=p.get("sim_success"),
            )
        )

    async def _handle_trajectory_analysis(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        session.add(
            TrajectoryAnalysis(
                analysis_id=_new_id(),
                simulation_id=p.get("simulation_id"),
                sequence_id=p["sequence_id"],
                analysis_type=p.get("analysis_type"),
                rmsd_mean=p.get("rmsd_mean"),
                rmsd_std=p.get("rmsd_std"),
                rmsf_mean=p.get("rmsf_mean"),
                rmsf_per_residue=p.get("rmsf_per_residue"),
                radius_of_gyration=p.get("radius_of_gyration"),
                n_frames=p.get("n_frames"),
                binding_site_residues=p.get("binding_site_residues"),
                contact_frequencies=p.get("contact_frequencies"),
                confidence_score=p.get("confidence_score"),
            )
        )

    async def _handle_free_energy_result(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        session.add(
            FreeEnergyResult(
                fe_id=_new_id(),
                simulation_id=p.get("simulation_id"),
                sequence_id=p["sequence_id"],
                method=p.get("method", "mmpbsa"),
                free_energy=p.get("free_energy"),
                success=p.get("success"),
                error=p.get("error"),
            )
        )

    async def _handle_embedding(
        self, session: AsyncSession, event: dict
    ) -> None:
        p = event["payload"]
        session.add(
            Embedding(
                embedding_id=_new_id(),
                sequence_id=p["sequence_id"],
                model_name=p["model_name"],
                embedding_dim=p.get("embedding_dim"),
                embedding_vector=p["embedding_vector"],
            )
        )

    # ------------------------------------------------------------------
    # Handler dispatch table
    # ------------------------------------------------------------------

    _ALL_HANDLERS: dict[str, Any] = {
        EventType.EXPERIMENT_START.value: _handle_experiment_start,
        EventType.EXPERIMENT_END.value: _handle_experiment_end,
        EventType.DIRECTOR_START.value: _handle_director_start,
        EventType.DIRECTOR_END.value: _handle_director_end,
        EventType.LLM_CALL.value: _handle_llm_call,
        EventType.DECISION.value: _handle_decision,
        EventType.PLAN.value: _handle_plan,
        EventType.EXECUTION_START.value: _handle_execution_start,
        EventType.EXECUTION_END.value: _handle_execution_end,
        EventType.KEY_ITEM.value: _handle_key_item,
        EventType.EXECUTIVE_ACTION.value: _handle_executive_action,
        ScientificEventType.SEQUENCE_GENERATED.value: _handle_sequence_generated,
        ScientificEventType.QC_RESULT.value: _handle_qc_result,
        ScientificEventType.FOLDING_RESULT.value: _handle_folding_result,
        ScientificEventType.ENERGY_RESULT.value: _handle_energy_result,
        ScientificEventType.SIMULATION_RUN.value: _handle_simulation_run,
        ScientificEventType.TRAJECTORY_ANALYSIS.value: _handle_trajectory_analysis,
        ScientificEventType.FREE_ENERGY_RESULT.value: _handle_free_energy_result,
        ScientificEventType.EMBEDDING.value: _handle_embedding,
    }
