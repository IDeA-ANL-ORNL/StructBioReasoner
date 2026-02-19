"""
Tests for the DataAgent: schema creation, event insertion, and queries.

Uses SQLite via aiosqlite (no Academy runtime or PostgreSQL needed).

NOTE: We mock external dependencies (academy, struct_bio_reasoner root) so
tests can run without the full HPC stack installed.
"""

from __future__ import annotations

import hashlib
import json
import sys
import types
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------------
# Mock unavailable dependencies before any package imports.
# ---------------------------------------------------------------------------

_SBR_ROOT = Path(__file__).resolve().parent.parent / "struct_bio_reasoner"

# 1. Mock 'academy' (HPC-only)
if "academy" not in sys.modules:
    _academy = types.ModuleType("academy")
    _academy.__path__ = []

    _academy_agent = types.ModuleType("academy.agent")

    # Minimal Agent base class stub
    class _AgentStub:
        def __init__(self, *a, **kw):
            pass

    def _action_stub(fn):
        return fn

    _academy_agent.Agent = _AgentStub
    _academy_agent.action = _action_stub

    _academy.__dict__["agent"] = _academy_agent
    sys.modules["academy"] = _academy
    sys.modules["academy.agent"] = _academy_agent

# 2. Mock the struct_bio_reasoner root __init__ (avoids MDAnalysis, etc.)
if "struct_bio_reasoner" not in sys.modules:
    _root_pkg = types.ModuleType("struct_bio_reasoner")
    _root_pkg.__path__ = [str(_SBR_ROOT)]
    _root_pkg.__package__ = "struct_bio_reasoner"
    sys.modules["struct_bio_reasoner"] = _root_pkg

from struct_bio_reasoner.agents.data.data_agent import DataAgent, _new_id
from struct_bio_reasoner.agents.data.events import (
    EventType,
    ScientificEventType,
    WorkflowEvent,
    ScientificEvent,
)
from struct_bio_reasoner.agents.data.models import (
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest_asyncio.fixture
async def agent(tmp_dir):
    """Create a DataAgent with temp SQLite DB, manually init (no Academy)."""
    db_url = f"sqlite+aiosqlite:///{tmp_dir / 'test.db'}"
    a = DataAgent(
        database_url=db_url,
        batch_size=100,
        flush_interval=999,  # disable periodic flush in tests
    )
    # Manually init engine + schemas (bypasses Academy lifecycle)
    a._engine = create_async_engine(db_url)
    a._session_factory = async_sessionmaker(a._engine, expire_on_commit=False)
    async with a._engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Seed schema version
    async with a._session_factory() as session:
        async with session.begin():
            session.add(SchemaVersion(version=1))
    return a


@pytest.fixture
def experiment_id():
    return str(uuid.uuid4())


@pytest.fixture
def director_id():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------------------------

class TestSchemaCreation:
    @pytest.mark.asyncio
    async def test_all_tables_exist(self, agent):
        async with agent._engine.connect() as conn:
            table_names = await conn.run_sync(
                lambda sync_conn: set(inspect(sync_conn).get_table_names())
            )
        expected = {
            "schema_version",
            "experiments",
            "directors",
            "llm_calls",
            "decisions",
            "task_plans",
            "task_executions",
            "key_items",
            "executive_actions",
            "sequences",
            "qc_results",
            "folding_results",
            "energy_results",
            "simulation_runs",
            "trajectory_analyses",
            "free_energy_results",
            "embeddings",
        }
        assert expected.issubset(table_names), (
            f"Missing tables: {expected - table_names}"
        )

    @pytest.mark.asyncio
    async def test_schema_version(self, agent):
        async with agent._session_factory() as session:
            row = await session.get(SchemaVersion, 1)
            assert row is not None
            assert row.version == 1

    @pytest.mark.asyncio
    async def test_idempotent_schema_creation(self, agent):
        """Running create_all twice should not raise."""
        async with agent._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with agent._session_factory() as session:
            result = await session.execute(select(SchemaVersion))
            rows = result.scalars().all()
            assert len(rows) == 1


# ---------------------------------------------------------------------------
# Decision Event Insertion Tests
# ---------------------------------------------------------------------------

class TestDecisionEvents:
    def _insert_experiment(self, agent, experiment_id):
        agent._buffer.append({
            "event_type": EventType.EXPERIMENT_START.value,
            "director_id": "",
            "experiment_id": experiment_id,
            "payload": {
                "experiment_id": experiment_id,
                "research_goal": "Test binding",
                "config_snapshot": {"foo": "bar"},
                "num_directors": 2,
            },
        })

    def _insert_director(self, agent, experiment_id, director_id):
        agent._buffer.append({
            "event_type": EventType.DIRECTOR_START.value,
            "director_id": director_id,
            "experiment_id": experiment_id,
            "payload": {
                "external_label": "director_0",
                "accelerator_ids": ["0", "1"],
                "target_protein": "MKKLL",
                "config_snapshot": {"runtime": True},
            },
        })

    @pytest.mark.asyncio
    async def test_experiment_lifecycle(self, agent, experiment_id):
        self._insert_experiment(agent, experiment_id)
        await agent._flush()

        async with agent._session_factory() as session:
            row = await session.get(Experiment, experiment_id)
            assert row is not None
            assert row.research_goal == "Test binding"
            assert row.num_directors == 2
            assert row.status == "running"

        # End experiment
        agent._buffer.append({
            "event_type": EventType.EXPERIMENT_END.value,
            "director_id": "",
            "payload": {
                "experiment_id": experiment_id,
                "status": "completed",
            },
        })
        await agent._flush()

        async with agent._session_factory() as session:
            row = await session.get(Experiment, experiment_id)
            assert row.status == "completed"
            assert row.ended_at is not None

    @pytest.mark.asyncio
    async def test_director_lifecycle(self, agent, experiment_id, director_id):
        self._insert_experiment(agent, experiment_id)
        self._insert_director(agent, experiment_id, director_id)
        await agent._flush()

        async with agent._session_factory() as session:
            row = await session.get(DirectorRecord, director_id)
            assert row is not None
            assert row.external_label == "director_0"
            assert row.target_protein == "MKKLL"

        # End director
        agent._buffer.append({
            "event_type": EventType.DIRECTOR_END.value,
            "director_id": director_id,
            "payload": {"reason": "timeout"},
        })
        await agent._flush()

        async with agent._session_factory() as session:
            row = await session.get(DirectorRecord, director_id)
            assert row.termination_reason == "timeout"
            assert row.terminated_at is not None

    @pytest.mark.asyncio
    async def test_llm_call(self, agent, experiment_id, director_id):
        self._insert_experiment(agent, experiment_id)
        self._insert_director(agent, experiment_id, director_id)

        call_id = _new_id()
        agent._buffer.append({
            "event_type": EventType.LLM_CALL.value,
            "director_id": director_id,
            "payload": {
                "call_id": call_id,
                "call_type": "recommendation",
                "model_name": "test-model",
                "prompt_text": "What next?",
                "response_text": "Do MD",
                "parsed_output": {"next_task": "molecular_dynamics"},
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "latency_ms": 1200,
            },
        })
        await agent._flush()

        async with agent._session_factory() as session:
            row = await session.get(LLMCall, call_id)
            assert row.call_type == "recommendation"
            assert row.model_name == "test-model"
            assert row.prompt_tokens == 100
            assert row.completion_tokens == 50

    @pytest.mark.asyncio
    async def test_decision_and_plan(self, agent, experiment_id, director_id):
        self._insert_experiment(agent, experiment_id)
        self._insert_director(agent, experiment_id, director_id)

        decision_id = _new_id()
        agent._buffer.append({
            "event_type": EventType.DECISION.value,
            "director_id": director_id,
            "payload": {
                "decision_id": decision_id,
                "iteration": 1,
                "previous_task": "starting",
                "next_task": "computational_design",
                "change_parameters": False,
                "rationale": "First run",
            },
        })

        plan_id = _new_id()
        agent._buffer.append({
            "event_type": EventType.PLAN.value,
            "director_id": director_id,
            "payload": {
                "plan_id": plan_id,
                "decision_id": decision_id,
                "task_type": "computational_design",
                "plan_model_name": "ComputationalDesignPlan",
                "plan_config": {"binder_sequence": "ACDEF", "num_rounds": 2},
                "rationale": "Default params",
            },
        })
        await agent._flush()

        async with agent._session_factory() as session:
            dec = await session.get(Decision, decision_id)
            assert dec.next_task == "computational_design"
            assert dec.rationale == "First run"

            plan = await session.get(TaskPlan, plan_id)
            assert plan.task_type == "computational_design"
            assert plan.plan_model_name == "ComputationalDesignPlan"

    @pytest.mark.asyncio
    async def test_execution_lifecycle(self, agent, experiment_id, director_id):
        self._insert_experiment(agent, experiment_id)
        self._insert_director(agent, experiment_id, director_id)

        exec_id = _new_id()
        agent._buffer.append({
            "event_type": EventType.EXECUTION_START.value,
            "director_id": director_id,
            "payload": {
                "execution_id": exec_id,
                "agent_key": "bindcraft",
                "input_kwargs": {"num_rounds": 2},
            },
        })
        await agent._flush()

        async with agent._session_factory() as session:
            row = await session.get(TaskExecution, exec_id)
            assert row.status == "running"
            assert row.agent_key == "bindcraft"

        # Complete it
        agent._buffer.append({
            "event_type": EventType.EXECUTION_END.value,
            "director_id": director_id,
            "payload": {
                "execution_id": exec_id,
                "status": "completed",
                "result_data": {"passing_structures": 5},
                "duration_ms": 45000,
            },
        })
        await agent._flush()

        async with agent._session_factory() as session:
            row = await session.get(TaskExecution, exec_id)
            assert row.status == "completed"
            assert row.duration_ms == 45000

    @pytest.mark.asyncio
    async def test_key_item(self, agent, experiment_id, director_id):
        self._insert_experiment(agent, experiment_id)
        self._insert_director(agent, experiment_id, director_id)

        agent._buffer.append({
            "event_type": EventType.KEY_ITEM.value,
            "director_id": director_id,
            "payload": {
                "item_type": "top_binder",
                "item_data": {"sequence": "ACDEF", "energy": -15.0},
            },
        })
        await agent._flush()

        async with agent._session_factory() as session:
            result = await session.execute(
                select(KeyItem).where(KeyItem.director_id == director_id)
            )
            row = result.scalar_one()
            assert row.item_type == "top_binder"


# ---------------------------------------------------------------------------
# Scientific Event Insertion Tests
# ---------------------------------------------------------------------------

class TestScientificEvents:
    def _insert_sequence(self, agent, seq_id, sequence="ACDEFGHIK"):
        agent._buffer.append({
            "event_type": ScientificEventType.SEQUENCE_GENERATED.value,
            "experiment_id": "exp1",
            "director_id": "dir1",
            "payload": {
                "sequence_id": seq_id,
                "sequence": sequence,
                "origin": "inverse_folding",
                "design_round": 1,
            },
        })

    @pytest.mark.asyncio
    async def test_sequence_insert(self, agent):
        seq_id = _new_id()
        self._insert_sequence(agent, seq_id)
        await agent._flush()

        async with agent._session_factory() as session:
            row = await session.get(Sequence, seq_id)
            assert row.sequence == "ACDEFGHIK"
            assert row.length == 9
            assert row.origin == "inverse_folding"
            assert row.design_round == 1

    @pytest.mark.asyncio
    async def test_sequence_dedup(self, agent):
        """Inserting the same sequence twice should not raise (check-then-skip)."""
        seq_id1 = _new_id()
        seq_id2 = _new_id()
        self._insert_sequence(agent, seq_id1, "ACDEFG")
        self._insert_sequence(agent, seq_id2, "ACDEFG")
        await agent._flush()

        async with agent._session_factory() as session:
            result = await session.execute(
                select(Sequence).where(Sequence.sequence == "ACDEFG")
            )
            rows = result.scalars().all()
            assert len(rows) == 1  # dedup on sequence_hash

    @pytest.mark.asyncio
    async def test_qc_result(self, agent):
        seq_id = _new_id()
        self._insert_sequence(agent, seq_id)
        await agent._flush()

        agent._buffer.append({
            "event_type": ScientificEventType.QC_RESULT.value,
            "payload": {
                "sequence_id": seq_id,
                "passed": True,
                "diversity": 8,
                "net_charge": 2,
                "hydrophobic_ratio": 0.35,
            },
        })
        await agent._flush()

        async with agent._session_factory() as session:
            result = await session.execute(
                select(QCResult).where(QCResult.sequence_id == seq_id)
            )
            row = result.scalar_one()
            assert row.passed is True
            assert row.diversity == 8
            assert row.net_charge == 2

    @pytest.mark.asyncio
    async def test_folding_result(self, agent):
        seq_id = _new_id()
        fold_id = _new_id()
        self._insert_sequence(agent, seq_id)
        await agent._flush()

        agent._buffer.append({
            "event_type": ScientificEventType.FOLDING_RESULT.value,
            "payload": {
                "fold_id": fold_id,
                "sequence_id": seq_id,
                "fold_backend": "chai",
                "structure_path": "/tmp/fold.pdb",
                "iptm": 0.85,
                "ptm": 0.90,
                "aggregate_score": 0.87,
                "trial_label": "trial_1",
            },
        })
        await agent._flush()

        async with agent._session_factory() as session:
            row = await session.get(FoldingResult, fold_id)
            assert row.fold_backend == "chai"
            assert abs(row.iptm - 0.85) < 1e-6
            assert abs(row.ptm - 0.90) < 1e-6

    @pytest.mark.asyncio
    async def test_energy_result(self, agent):
        seq_id = _new_id()
        fold_id = _new_id()
        self._insert_sequence(agent, seq_id)
        await agent._flush()

        # Insert fold first
        agent._buffer.append({
            "event_type": ScientificEventType.FOLDING_RESULT.value,
            "payload": {
                "fold_id": fold_id,
                "sequence_id": seq_id,
                "fold_backend": "chai",
            },
        })
        await agent._flush()

        agent._buffer.append({
            "event_type": ScientificEventType.ENERGY_RESULT.value,
            "payload": {
                "fold_id": fold_id,
                "sequence_id": seq_id,
                "energy_method": "simple_contact",
                "energy_score": -15.0,
                "n_interface_contacts": 15,
                "passed_threshold": True,
                "energy_threshold": -10.0,
            },
        })
        await agent._flush()

        async with agent._session_factory() as session:
            result = await session.execute(
                select(EnergyResult).where(EnergyResult.sequence_id == seq_id)
            )
            row = result.scalar_one()
            assert row.energy_method == "simple_contact"
            assert abs(row.energy_score - (-15.0)) < 1e-6
            assert row.passed_threshold is True

    @pytest.mark.asyncio
    async def test_simulation_run(self, agent):
        seq_id = _new_id()
        sim_id = _new_id()
        self._insert_sequence(agent, seq_id)
        await agent._flush()

        agent._buffer.append({
            "event_type": ScientificEventType.SIMULATION_RUN.value,
            "payload": {
                "simulation_id": sim_id,
                "sequence_id": seq_id,
                "sim_path": "/tmp/sim",
                "prod_steps": 100000,
                "sim_time_ns": 2.0,
                "sim_success": True,
            },
        })
        await agent._flush()

        async with agent._session_factory() as session:
            row = await session.get(SimulationRun, sim_id)
            assert row.prod_steps == 100000
            assert abs(row.sim_time_ns - 2.0) < 1e-6
            assert row.sim_success is True

    @pytest.mark.asyncio
    async def test_free_energy_result(self, agent):
        seq_id = _new_id()
        sim_id = _new_id()
        self._insert_sequence(agent, seq_id)
        await agent._flush()

        agent._buffer.append({
            "event_type": ScientificEventType.SIMULATION_RUN.value,
            "payload": {
                "simulation_id": sim_id,
                "sequence_id": seq_id,
                "sim_success": True,
            },
        })
        await agent._flush()

        agent._buffer.append({
            "event_type": ScientificEventType.FREE_ENERGY_RESULT.value,
            "payload": {
                "simulation_id": sim_id,
                "sequence_id": seq_id,
                "free_energy": -12.5,
                "success": True,
            },
        })
        await agent._flush()

        async with agent._session_factory() as session:
            result = await session.execute(
                select(FreeEnergyResult).where(
                    FreeEnergyResult.sequence_id == seq_id
                )
            )
            row = result.scalar_one()
            assert abs(row.free_energy - (-12.5)) < 1e-6
            assert row.success is True

    @pytest.mark.asyncio
    async def test_embedding(self, agent):
        seq_id = _new_id()
        self._insert_sequence(agent, seq_id)
        await agent._flush()

        agent._buffer.append({
            "event_type": ScientificEventType.EMBEDDING.value,
            "payload": {
                "sequence_id": seq_id,
                "model_name": "genslm_esmc",
                "embedding_dim": 3,
                "embedding_vector": [0.1, 0.2, 0.3],
            },
        })
        await agent._flush()

        async with agent._session_factory() as session:
            result = await session.execute(
                select(Embedding).where(Embedding.sequence_id == seq_id)
            )
            row = result.scalar_one()
            assert row.model_name == "genslm_esmc"
            assert row.embedding_dim == 3


# ---------------------------------------------------------------------------
# Query Tests
# ---------------------------------------------------------------------------

class TestDecisionQueries:
    async def _seed_director_history(self, agent, experiment_id, director_id):
        """Insert experiment, director, decisions, plans, executions via ORM."""
        async with agent._session_factory() as session:
            async with session.begin():
                session.add(Experiment(
                    experiment_id=experiment_id,
                    research_goal="test",
                    num_directors=1,
                ))
                session.add(DirectorRecord(
                    director_id=director_id,
                    experiment_id=experiment_id,
                    external_label="director_0",
                ))
                for i in range(3):
                    session.add(Decision(
                        decision_id=_new_id(),
                        director_id=director_id,
                        iteration=i,
                        previous_task="starting",
                        next_task=f"task_{i}",
                        change_parameters=False,
                        rationale=f"reason_{i}",
                    ))
                    session.add(TaskPlan(
                        plan_id=_new_id(),
                        director_id=director_id,
                        task_type=f"task_{i}",
                        plan_config={"param": i},
                        rationale=f"plan_{i}",
                    ))
                    session.add(TaskExecution(
                        execution_id=_new_id(),
                        director_id=director_id,
                        agent_key="bindcraft",
                        status="completed",
                        result_data={"result": i},
                        duration_ms=1000 * (i + 1),
                        completed_at=_utcnow(),
                    ))

    @pytest.mark.asyncio
    async def test_get_director_history(self, agent, experiment_id, director_id):
        await self._seed_director_history(agent, experiment_id, director_id)
        history = await agent.get_director_history(director_id, limit=10)

        assert len(history["decisions"]) == 3
        assert len(history["results"]) == 3
        assert len(history["configurations"]) == 3

    @pytest.mark.asyncio
    async def test_get_director_history_limit(self, agent, experiment_id, director_id):
        await self._seed_director_history(agent, experiment_id, director_id)
        history = await agent.get_director_history(director_id, limit=2)

        assert len(history["decisions"]) == 2
        assert len(history["results"]) == 2

    @pytest.mark.asyncio
    async def test_get_experiment_summary(self, agent, experiment_id, director_id):
        await self._seed_director_history(agent, experiment_id, director_id)
        summary = await agent.get_experiment_summary(experiment_id)

        assert summary["num_directors"] == 1
        assert summary["total_tasks"] == 3
        assert summary["completed"] == 3
        assert summary["failed"] == 0

    @pytest.mark.asyncio
    async def test_get_recovery_state(self, agent, experiment_id, director_id):
        await self._seed_director_history(agent, experiment_id, director_id)
        state = await agent.get_recovery_state(director_id)

        assert state["last_decision"] is not None
        assert state["last_execution"] is not None
        assert state["last_execution"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_recovery_state_empty(self, agent):
        state = await agent.get_recovery_state("nonexistent")
        assert state["last_decision"] is None
        assert state["last_execution"] is None


class TestScientificQueries:
    async def _seed_pipeline(self, agent):
        """Insert a complete sequence lifecycle via ORM."""
        seq_id = _new_id()
        fold_id = _new_id()
        sim_id = _new_id()
        seq = "ACDEFGHIKLMNP"
        seq_hash = hashlib.sha256(seq.encode()).hexdigest()

        async with agent._session_factory() as session:
            async with session.begin():
                session.add(Sequence(
                    sequence_id=seq_id, sequence=seq,
                    sequence_hash=seq_hash, length=len(seq),
                    origin="inverse_folding", design_round=1,
                ))
                session.add(QCResult(
                    qc_id=_new_id(), sequence_id=seq_id,
                    passed=True, diversity=10,
                ))
                session.add(FoldingResult(
                    fold_id=fold_id, sequence_id=seq_id,
                    fold_backend="chai", iptm=0.85, ptm=0.90,
                ))
                session.add(EnergyResult(
                    energy_id=_new_id(), fold_id=fold_id,
                    sequence_id=seq_id, energy_method="simple_contact",
                    energy_score=-15.0, passed_threshold=True,
                ))
                session.add(SimulationRun(
                    simulation_id=sim_id, fold_id=fold_id,
                    sequence_id=seq_id, prod_steps=100000,
                    sim_success=True,
                ))
                session.add(TrajectoryAnalysis(
                    analysis_id=_new_id(), simulation_id=sim_id,
                    sequence_id=seq_id, rmsd_mean=1.5, rmsd_std=0.3,
                ))
                session.add(FreeEnergyResult(
                    fe_id=_new_id(), simulation_id=sim_id,
                    sequence_id=seq_id, free_energy=-12.5, success=True,
                ))
                session.add(Embedding(
                    embedding_id=_new_id(), sequence_id=seq_id,
                    model_name="genslm", embedding_dim=3,
                    embedding_vector=[0.1, 0.2, 0.3],
                ))

        return seq_id

    @pytest.mark.asyncio
    async def test_sequence_lifecycle_view(self, agent):
        seq_id = await self._seed_pipeline(agent)
        rows = await agent.get_sequence_lifecycle(sequence_id=seq_id)
        assert len(rows) == 1
        row = rows[0]
        assert row["sequence"] == "ACDEFGHIKLMNP"
        assert row["qc_passed"] is True
        assert abs(row["iptm"] - 0.85) < 1e-6
        assert abs(row["contact_energy"] - (-15.0)) < 1e-6
        assert abs(row["rmsd_mean"] - 1.5) < 1e-6
        assert abs(row["free_energy"] - (-12.5)) < 1e-6

    @pytest.mark.asyncio
    async def test_get_top_binders(self, agent):
        await self._seed_pipeline(agent)
        binders = await agent.get_top_binders(limit=10)
        assert len(binders) == 1
        assert abs(binders[0]["free_energy"] - (-12.5)) < 1e-6

    @pytest.mark.asyncio
    async def test_get_top_binders_with_filter(self, agent):
        await self._seed_pipeline(agent)
        binders = await agent.get_top_binders(max_free_energy=-20.0)
        assert len(binders) == 0  # -12.5 is not < -20.0

    @pytest.mark.asyncio
    async def test_get_design_round_yield(self, agent):
        await self._seed_pipeline(agent)
        yield_data = await agent.get_design_round_yield()
        assert len(yield_data) == 1
        assert yield_data[0]["generated"] == 1
        assert yield_data[0]["passed_qc"] == 1


# ---------------------------------------------------------------------------
# Event Dataclass Tests
# ---------------------------------------------------------------------------

class TestEventDataclasses:
    def test_workflow_event_to_dict(self):
        e = WorkflowEvent(
            event_type=EventType.DECISION,
            director_id="dir_0",
            payload={"next_task": "md"},
        )
        d = e.to_dict()
        assert d["event_type"] == "decision"
        assert d["director_id"] == "dir_0"
        assert "timestamp" in d

    def test_scientific_event_to_dict(self):
        e = ScientificEvent(
            event_type=ScientificEventType.SEQUENCE_GENERATED,
            payload={"sequence": "ACDEF"},
        )
        d = e.to_dict()
        assert d["event_type"] == "sequence_generated"
        assert "timestamp" in d

    def test_workflow_event_string_event_type(self):
        """Event type can be passed as string too."""
        e = WorkflowEvent(
            event_type="decision",
            director_id="dir_0",
            payload={},
        )
        d = e.to_dict()
        assert d["event_type"] == "decision"


# Need the _utcnow import for seeding helpers
from struct_bio_reasoner.agents.data.data_agent import _utcnow
