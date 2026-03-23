"""Tests for the Academy execution fabric (Layer 4).

External dependencies (``academy``, ``jnana``) are mocked via conftest.py.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from struct_bio_reasoner.academy.config import (
    AcademyConfig,
    create_exchange_factory,
    create_parsl_executor,
)
from struct_bio_reasoner.academy.dispatch import AcademyDispatch
from struct_bio_reasoner.academy.executive import ExecutiveAgent
from struct_bio_reasoner.academy.manager_agent import ManagerAgent
from struct_bio_reasoner.academy.worker_agents import (
    BindCraftWorker,
    ConservationWorker,
    FoldingWorker,
    MDWorker,
    ProteinLMWorker,
    RAGWorker,
    TrajectoryAnalysisWorker,
    WORKER_REGISTRY,
)


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestAcademyConfig:
    def test_default_config(self):
        cfg = AcademyConfig()
        assert cfg.exchange_mode == "local"
        assert cfg.use_parsl is False
        assert cfg.total_compute_nodes == 4

    def test_local_exchange_factory(self):
        cfg = AcademyConfig(exchange_mode="local")
        factory = create_exchange_factory(cfg)
        assert type(factory).__name__ == "_LocalExchangeFactory"

    def test_redis_exchange_factory(self):
        cfg = AcademyConfig(
            exchange_mode="redis", redis_host="my-redis", redis_port=6380
        )
        factory = create_exchange_factory(cfg)
        assert factory.host == "my-redis"
        assert factory.port == 6380

    def test_create_executor_threadpool_fallback(self):
        from concurrent.futures import ThreadPoolExecutor

        cfg = AcademyConfig(use_parsl=False, thread_pool_workers=2)
        executor = create_parsl_executor(cfg)
        assert isinstance(executor, ThreadPoolExecutor)


# ---------------------------------------------------------------------------
# Worker agent tests
# ---------------------------------------------------------------------------


class TestWorkerAgents:
    def test_worker_registry_has_all_skills(self):
        expected = {
            "bindcraft", "binder_design", "folding", "structure_prediction",
            "md", "simulation", "molecular_dynamics",
            "rag", "literature", "hiperrag",
            "conservation", "protein_lm",
            "trajectory_analysis", "clustering",
        }
        assert expected.issubset(set(WORKER_REGISTRY.keys()))

    def test_conservation_worker_action(self):
        worker = ConservationWorker({})
        result = asyncio.get_event_loop().run_until_complete(
            worker.run_conservation({"sequence": "MKQHKAM"})
        )
        assert result["sequence_length"] == 7
        assert result["status"] == "placeholder"

    def test_protein_lm_worker_embed(self):
        worker = ProteinLMWorker({})
        result = asyncio.get_event_loop().run_until_complete(
            worker.embed_sequence({"sequence": "ACDEFG"})
        )
        assert result["sequence_length"] == 6
        assert result["embedding_dim"] == 1280

    def test_protein_lm_worker_score(self):
        worker = ProteinLMWorker({})
        result = asyncio.get_event_loop().run_until_complete(
            worker.score_mutations({"mutations": []})
        )
        assert result["status"] == "placeholder"

    def test_trajectory_analysis_cluster(self):
        worker = TrajectoryAnalysisWorker({})
        result = asyncio.get_event_loop().run_until_complete(
            worker.cluster_trajectories({"n_clusters": 3})
        )
        assert result["n_clusters"] == 3

    def test_trajectory_analysis_hotspots(self):
        worker = TrajectoryAnalysisWorker({})
        result = asyncio.get_event_loop().run_until_complete(
            worker.analyze_hotspots({})
        )
        assert result["status"] == "placeholder"

    def test_bindcraft_worker_class_exists(self):
        assert BindCraftWorker is not None
        worker = BindCraftWorker({"agent_id": "test"})
        assert worker.config["agent_id"] == "test"

    def test_folding_worker_class_exists(self):
        assert FoldingWorker is not None

    def test_md_worker_class_exists(self):
        assert MDWorker is not None

    def test_rag_worker_class_exists(self):
        assert RAGWorker is not None


# ---------------------------------------------------------------------------
# Executive Agent tests
# ---------------------------------------------------------------------------


class TestExecutiveAgent:
    def _make_executive(self):
        return ExecutiveAgent(
            research_goal="Design binder for NMNAT2",
            target_name="NMNAT2",
            target_seq="MKQHKAM",
            rag_handle=MagicMock(),
            fold_handle=MagicMock(),
            sim_handle=MagicMock(),
            llm_interface=MagicMock(),
            total_compute_nodes=10,
            config={"max_tasks_per_campaign": 5},
        )

    def test_construction(self):
        agent = self._make_executive()
        assert agent.total_nodes == 10
        assert agent.target_name == "NMNAT2"
        assert agent.research_goal == "Design binder for NMNAT2"

    def test_allocate_resources_round_1(self):
        agent = self._make_executive()
        result = asyncio.get_event_loop().run_until_complete(
            agent.allocate_resources(["m1", "m2", "m3"], round_num=1)
        )
        assert len(result) == 3
        assert all(v > 0 for v in result.values())
        assert sum(result.values()) <= 10

    def test_allocate_resources_performance_based(self):
        agent = self._make_executive()
        perf = {
            "m1": {"score": 0.9},
            "m2": {"score": 0.1},
        }
        result = asyncio.get_event_loop().run_until_complete(
            agent.allocate_resources(["m1", "m2"], round_num=2, previous_performance=perf)
        )
        assert result["m1"] > result["m2"]

    def test_evaluate_managers(self):
        agent = self._make_executive()
        # Affinity scoring: (affinity + 20) / 20, so -5 → 0.75, -12 → 0.40
        # Task scoring: len(tasks) / 10
        # m2 has better affinity score but fewer tasks
        results = {
            "m1": {"best_binder": {"affinity": -5.0}, "tasks_executed": [1, 2, 3]},
            "m2": {"best_binder": {"affinity": -12.0}, "tasks_executed": [1]},
        }
        evals = asyncio.get_event_loop().run_until_complete(
            agent.evaluate_managers(results)
        )
        assert "m1" in evals and "m2" in evals
        # m1: 0.7*0.75 + 0.3*0.3 = 0.615
        # m2: 0.7*0.40 + 0.3*0.1 = 0.31
        assert evals["m1"]["score"] > evals["m2"]["score"]

    def test_decide_manager_lifecycle(self):
        agent = self._make_executive()
        evals = {"m1": {"score": 0.9}, "m2": {"score": 0.3}, "m3": {"score": 0.6}}
        decisions = asyncio.get_event_loop().run_until_complete(
            agent.decide_manager_lifecycle(evals, round_num=2)
        )
        assert "continue" in decisions and "terminate" in decisions
        assert len(decisions["continue"]) >= 2

    def test_select_best_binder(self):
        agent = self._make_executive()
        results = {
            "m1": {"best_binder": {"affinity": -8.0, "seq": "AAA"}},
            "m2": {"best_binder": {"affinity": -15.0, "seq": "BBB"}},
        }
        best = asyncio.get_event_loop().run_until_complete(
            agent.select_best_binder(results)
        )
        # Higher affinity value = better (closer to 0)
        assert best["score"] == -8.0
        assert best["source_manager"] == "m1"

    def test_performance_score_calculation(self):
        agent = self._make_executive()
        score = agent._calculate_performance_score(
            {"best_binder": {"affinity": -10.0}, "tasks_executed": [1, 2, 3, 4, 5]}
        )
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Manager Agent tests
# ---------------------------------------------------------------------------


class TestManagerAgent:
    def _make_manager(self):
        return ManagerAgent(
            manager_id="mgr_1",
            allocated_nodes=4,
            worker_handles={
                "folding": MagicMock(),
                "simulation": MagicMock(),
                "binder_design": MagicMock(),
            },
            llm_interface=MagicMock(),
            config={"max_tasks_per_campaign": 5, "temperature": 0.5},
        )

    def test_construction(self):
        mgr = self._make_manager()
        assert mgr.manager_id == "mgr_1"
        assert mgr.allocated_nodes == 4
        assert mgr.tasks_completed == 0

    def test_should_stop_max_tasks(self):
        mgr = self._make_manager()
        history = [{"task": i} for i in range(10)]
        assert asyncio.get_event_loop().run_until_complete(mgr.should_stop(history))

    def test_should_stop_no_history(self):
        mgr = self._make_manager()
        assert not asyncio.get_event_loop().run_until_complete(mgr.should_stop([]))

    def test_should_stop_good_binder(self):
        mgr = self._make_manager()
        mgr.binder_designs = [{"affinity": -12.0}]
        assert asyncio.get_event_loop().run_until_complete(mgr.should_stop([]))

    def test_summarize_campaign(self):
        mgr = self._make_manager()
        summary = asyncio.get_event_loop().run_until_complete(mgr.summarize_campaign())
        assert summary["manager_id"] == "mgr_1"
        assert summary["num_tasks"] == 0
        assert "timestamp" in summary

    def test_parse_task_decision(self):
        mgr = self._make_manager()
        assert mgr._parse_task_decision("The next task should be folding.") == "folding"
        assert mgr._parse_task_decision("simulation") == "simulation"
        assert mgr._parse_task_decision("BINDER_DESIGN please") == "binder_design"
        assert mgr._parse_task_decision("random nonsense") == "stop"

    def test_record_task(self):
        mgr = self._make_manager()
        mgr._record_task("folding", {"seq": "A"}, {"pdb": "x.pdb"})
        assert mgr.tasks_completed == 1
        assert len(mgr.task_history) == 1
        assert mgr.task_history[0]["task_type"] == "folding"


# ---------------------------------------------------------------------------
# Dispatch tests
# ---------------------------------------------------------------------------


class TestAcademyDispatch:
    def test_dispatch_not_started_raises(self):
        disp = AcademyDispatch()
        with pytest.raises(RuntimeError, match="not started"):
            asyncio.get_event_loop().run_until_complete(
                disp.dispatch("conservation", {})
            )

    def test_list_available_skills(self):
        disp = AcademyDispatch()
        skills = disp.list_available_skills()
        assert "bindcraft" in skills
        assert "folding" in skills
        assert "md" in skills
        assert "conservation" in skills

    def test_dispatch_unknown_skill_raises(self):
        disp = AcademyDispatch()
        asyncio.get_event_loop().run_until_complete(disp.start())
        with pytest.raises(ValueError, match="Unknown skill"):
            asyncio.get_event_loop().run_until_complete(
                disp.dispatch("nonexistent_skill", {})
            )

    def test_dispatch_conservation(self):
        disp = AcademyDispatch()
        asyncio.get_event_loop().run_until_complete(disp.start())
        result = asyncio.get_event_loop().run_until_complete(
            disp.dispatch("conservation", {"sequence": "MKQH"})
        )
        assert result["sequence_length"] == 4
        assert "conservation" in disp.list_active_workers()

    def test_dispatch_protein_lm(self):
        disp = AcademyDispatch()
        asyncio.get_event_loop().run_until_complete(disp.start())
        result = asyncio.get_event_loop().run_until_complete(
            disp.dispatch("protein_lm", {"sequence": "ACDE"})
        )
        assert result["sequence_length"] == 4

    def test_dispatch_reuses_handle(self):
        disp = AcademyDispatch()
        asyncio.get_event_loop().run_until_complete(disp.start())
        asyncio.get_event_loop().run_until_complete(
            disp.dispatch("conservation", {"sequence": "A"})
        )
        asyncio.get_event_loop().run_until_complete(
            disp.dispatch("conservation", {"sequence": "B"})
        )
        assert disp.list_active_workers().count("conservation") == 1

    def test_context_manager(self):
        async def _run():
            async with AcademyDispatch() as disp:
                result = await disp.dispatch("protein_lm", {"sequence": "ACDE"})
                assert result["sequence_length"] == 4
            assert not disp._started

        asyncio.get_event_loop().run_until_complete(_run())

    def test_stop_clears_handles(self):
        disp = AcademyDispatch()
        asyncio.get_event_loop().run_until_complete(disp.start())
        asyncio.get_event_loop().run_until_complete(
            disp.dispatch("conservation", {"sequence": "A"})
        )
        assert len(disp.list_active_workers()) == 1
        asyncio.get_event_loop().run_until_complete(disp.stop())
        assert len(disp.list_active_workers()) == 0
        assert not disp._started


# ---------------------------------------------------------------------------
# Module-level import tests
# ---------------------------------------------------------------------------


class TestModuleImports:
    def test_academy_module_exports(self):
        import struct_bio_reasoner.academy as academy_mod

        assert hasattr(academy_mod, "AcademyDispatch")
        assert hasattr(academy_mod, "ExecutiveAgent")
        assert hasattr(academy_mod, "ManagerAgent")
        assert hasattr(academy_mod, "WORKER_REGISTRY")
        assert hasattr(academy_mod, "AcademyConfig")
        assert hasattr(academy_mod, "create_exchange_factory")
        assert hasattr(academy_mod, "create_parsl_executor")

    def test_dispatch_importable(self):
        from struct_bio_reasoner.academy.dispatch import AcademyDispatch as AD

        assert AD is not None
