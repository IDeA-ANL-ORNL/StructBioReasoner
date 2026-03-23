"""Executive Agent for the Academy execution fabric (Layer 4).

The Executive Agent is the top-level decision maker in the
Executive → Manager → Worker hierarchy.  It:

1. Queries HiPerRAG for literature-guided strategy
2. Allocates computational resources to Manager agents
3. Evaluates Manager performance
4. Decides Manager lifecycle (continue / kill / replace / duplicate)
5. Selects best binder across all campaigns

Ported from ``struct_bio_reasoner.agents.executive.executive_agent``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from academy.agent import Agent, action
from academy.handle import Handle

logger = logging.getLogger(__name__)


class ExecutiveAgent(Agent):
    """Strategic oversight agent — allocates resources, manages manager lifecycle."""

    def __init__(
        self,
        research_goal: str,
        target_name: str,
        target_seq: str,
        rag_handle: Handle,
        fold_handle: Handle,
        sim_handle: Handle,
        llm_interface: Any,
        total_compute_nodes: int,
        config: Dict[str, Any],
    ) -> None:
        self.research_goal = research_goal
        self.target_name = target_name
        self.target_seq = target_seq
        self.rag_handle = rag_handle
        self.fold_handle = fold_handle
        self.sim_handle = sim_handle
        self.llm = llm_interface
        self.total_nodes = total_compute_nodes
        self.config = config

        # State
        self.managers: Dict[str, Dict[str, Any]] = {}
        self.round_history: List[Dict[str, Any]] = []

        logger.info(
            "ExecutiveAgent initialised (nodes=%d, target=%s)",
            total_compute_nodes,
            target_name,
        )

    # ------------------------------------------------------------------
    # RAG & interactome actions
    # ------------------------------------------------------------------

    @action
    async def query_hiper_rag(self, research_goal: str) -> Dict[str, Any]:
        """Query HiPerRAG for literature-guided strategy and target identification."""
        logger.info("Querying HiPerRAG for strategy…")

        try:
            from struct_bio_reasoner.prompts.prompts import get_prompt_manager, config_master
            from struct_bio_reasoner.utils.uniprot_api import fetch_uniprot_sequence

            rag_prompt_manager = get_prompt_manager(
                "rag",
                research_goal,
                {},
                target_prot=self.target_name,
                prompt_type="interactome",
                history=[],
                num_history=3,
            )
            rag_prompt_manager.running_prompt()
            rag_prompt = self.llm.generate(
                prompt=rag_prompt_manager.prompt_r,
                temperature=0.3,
                max_tokens=32678,
            )
            rag_response = await self.rag_handle.generate_rag_hypothesis(
                {"prompt": rag_prompt}
            )
            rag_prompt_manager.input_json = rag_response
            rag_conclusion = rag_prompt_manager.conclusion_prompt()
            rag_result_json = self.llm.generate_with_json_output(
                prompt=rag_conclusion,
                json_schema=config_master["rag_output"],
                temperature=0.3,
                max_tokens=32678,
            )
            sequences = [
                await fetch_uniprot_sequence(uid)
                for uid in rag_result_json["interacting_protein_uniprot_ids"]
            ]
            rag_result_json["sequences"] = [s["sequence"] for s in sequences]
        except Exception:
            logger.exception("RAG query failed — returning empty strategy")
            rag_result_json = {}

        return {
            "research_goal": research_goal,
            "rag_strategy": rag_result_json,
            "timestamp": datetime.now().isoformat(),
        }

    @action
    async def fold_interactome(self) -> Dict[str, Any]:
        """Fold the interactome structures identified by RAG."""
        try:
            from struct_bio_reasoner.prompts.prompts import get_prompt_manager, config_master

            folding_pm = get_prompt_manager(
                "structure_prediction",
                self.research_goal,
                {},
                target_prot=self.target_seq,
                prompt_type="running",
                history=[],
                num_history=3,
            )
            folding_pm.running_prompt()
            folding_input = self.llm.generate_with_json_output(
                prompt=folding_pm.prompt_r,
                json_schema=config_master["structure_prediction"],
                temperature=0.3,
                max_tokens=32678,
            )[0]
            folding_output = await self.fold_handle.analyze_hypothesis({}, folding_input)
            return folding_output if isinstance(folding_output, dict) else {}
        except Exception:
            logger.exception("Fold interactome failed")
            return {}

    @action
    async def sim_interactome(self) -> Dict[str, Any]:
        """Run MD simulations on folded interactome structures."""
        try:
            from struct_bio_reasoner.prompts.prompts import get_prompt_manager, config_master

            md_pm = get_prompt_manager(
                "molecular_dynamics",
                self.research_goal,
                {},
                target_prot=self.target_seq,
                prompt_type="interactome_simulation",
                history=[],
                num_history=3,
            )
            md_input = self.llm.generate_with_json_output(
                prompt=md_pm.prompt_r,
                json_schema=config_master["molecular_dynamics"],
                temperature=0.3,
                max_tokens=32678,
            )[0]
            md_output = await self.sim_handle.analyze_hypothesis({}, md_input)
            return md_output if isinstance(md_output, dict) else {}
        except Exception:
            logger.exception("Sim interactome failed")
            return {}

    # ------------------------------------------------------------------
    # Resource allocation
    # ------------------------------------------------------------------

    @action
    async def allocate_resources(
        self,
        manager_ids: List[str],
        round_num: int,
        previous_performance: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, int]:
        """Allocate compute nodes to Manager agents."""
        logger.info("Allocating resources for round %d…", round_num)

        if round_num == 1 or previous_performance is None:
            nodes_per = self.total_nodes // max(1, len(manager_ids))
            return {mid: nodes_per for mid in manager_ids}

        return await self._performance_based_allocation(
            manager_ids, previous_performance
        )

    # ------------------------------------------------------------------
    # Manager evaluation & lifecycle
    # ------------------------------------------------------------------

    @action
    async def evaluate_managers(
        self, manager_results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Evaluate Manager performance and return scores."""
        evaluations = {}
        for manager_id, results in manager_results.items():
            score = self._calculate_performance_score(results)
            best_binder = results.get("best_binder", {})
            tasks_executed = results.get("tasks_executed", [])
            evaluations[manager_id] = {
                "score": score,
                "best_binder_affinity": best_binder.get("affinity", 0.0),
                "num_tasks": len(tasks_executed),
                "efficiency": score / len(tasks_executed) if tasks_executed else 0.0,
                "recommendation": "continue" if score > 0.5 else "terminate",
            }
        return evaluations

    @action
    async def decide_manager_lifecycle(
        self, evaluations: Dict[str, Any], round_num: int
    ) -> Dict[str, Any]:
        """Decide which Managers continue and which get terminated."""
        sorted_managers = sorted(
            evaluations.items(), key=lambda x: x[1]["score"], reverse=True
        )
        num_to_keep = max(2, len(sorted_managers) // 2)
        return {
            "continue": [m[0] for m in sorted_managers[:num_to_keep]],
            "terminate": [m[0] for m in sorted_managers[num_to_keep:]],
            "round": round_num,
        }

    @action
    async def select_best_binder(
        self, manager_results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Select the best binder across all managers."""
        best_binder = None
        best_score = float("-inf")
        best_manager = None

        for manager_id, results in manager_results.items():
            binder = results.get("best_binder", {})
            score = binder.get("affinity", float("-inf"))
            if score > best_score:
                best_score = score
                best_binder = binder
                best_manager = manager_id

        return {
            "binder": best_binder,
            "score": best_score,
            "source_manager": best_manager,
            "timestamp": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _performance_based_allocation(
        self,
        manager_ids: List[str],
        performance: Dict[str, Any],
    ) -> Dict[str, int]:
        scores = {
            mid: performance.get(mid, {}).get("score", 0.5) for mid in manager_ids
        }
        total_score = sum(scores.values()) or 1.0
        allocation: Dict[str, int] = {}
        allocated = 0
        for mid in manager_ids[:-1]:
            nodes = int((scores[mid] / total_score) * self.total_nodes)
            allocation[mid] = max(1, nodes)
            allocated += allocation[mid]
        allocation[manager_ids[-1]] = max(1, self.total_nodes - allocated)
        return allocation

    def _calculate_performance_score(self, results: Dict[str, Any]) -> float:
        best_binder = results.get("best_binder", {})
        affinity = best_binder.get("affinity", 0.0)
        tasks = results.get("tasks_executed", [])
        affinity_score = min(1.0, max(0.0, (affinity + 20) / 20))
        task_score = min(1.0, len(tasks) / 10.0)
        return 0.7 * affinity_score + 0.3 * task_score
