"""Manager Agent for the Academy execution fabric (Layer 4).

The Manager Agent is the tactical coordinator in the
Executive → Manager → Worker hierarchy.  One Manager runs per
RAG-identified target.  It:

1. Decides task sequence (folding → simulation → clustering → design)
2. Dispatches tasks to Worker agents via Handle RPC
3. Tracks campaign state (structures, simulations, designs)
4. Evaluates stopping criteria
5. Summarises campaign results for the Executive

Ported from ``struct_bio_reasoner.agents.manager.manager_agent``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from academy.agent import Agent, action
    from academy.handle import Handle
except ImportError:
    raise ImportError(
        "The 'academy' package is required for the ManagerAgent. "
        "Install Jnana with: pip install git+https://github.com/acadev/Jnana.git --no-deps"
    )

logger = logging.getLogger(__name__)


class ManagerAgent(Agent):
    """Tactical agent — coordinates a single binder-design campaign."""

    def __init__(
        self,
        manager_id: str,
        allocated_nodes: int,
        worker_handles: Dict[str, Handle],
        llm_interface: Any,
        config: Dict[str, Any],
    ) -> None:
        self.manager_id = manager_id
        self.allocated_nodes = allocated_nodes
        self.workers = worker_handles
        self.llm = llm_interface
        self.config = config

        # Campaign state
        self.task_history: List[Dict[str, Any]] = []
        self.current_structures: List[Dict[str, Any]] = []
        self.simulation_results: List[Dict[str, Any]] = []
        self.cluster_results: Optional[Dict[str, Any]] = None
        self.hotspot_results: Optional[Dict[str, Any]] = None
        self.binder_designs: List[Dict[str, Any]] = []

        # Perf tracking
        self.start_time = datetime.now()
        self.tasks_completed = 0

        logger.info(
            "ManagerAgent %s initialised (nodes=%d)", manager_id, allocated_nodes
        )

    # ------------------------------------------------------------------
    # Task decision
    # ------------------------------------------------------------------

    @action
    async def decide_next_task(self, current_state: Dict[str, Any]) -> str:
        """Decide the next task to execute.

        Returns one of: ``folding``, ``simulation``, ``clustering``,
        ``hotspot_analysis``, ``binder_design``, or ``stop``.
        """
        prompt = self._build_task_decision_prompt(current_state)
        response = self.llm.generate(
            prompt=prompt,
            temperature=self.config.get("temperature", 0.5),
            max_tokens=500,
        )
        task = self._parse_task_decision(response)
        logger.info("Manager %s: next task = %s", self.manager_id, task)
        return task

    # ------------------------------------------------------------------
    # Task execution — each dispatches to a Worker via Handle
    # ------------------------------------------------------------------

    @action
    async def execute_folding(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute protein folding via the folding worker."""
        handle = self.workers.get("folding")
        if not handle:
            raise ValueError("Folding worker not available")
        result = await handle.fold_sequences(
            sequences=params["sequences"],
            names=params["names"],
            constraints=params.get("constraints", {}),
        )
        self.current_structures.append(result)
        self._record_task("folding", params, result)
        return result

    @action
    async def execute_simulation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute MD simulation via the simulation worker."""
        handle = self.workers.get("simulation")
        if not handle:
            raise ValueError("Simulation worker not available")
        result = await handle.analyze_hypothesis(None, params)
        self.simulation_results.append(result)
        self._record_task("simulation", params, result)
        return result

    @action
    async def execute_clustering(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute trajectory clustering via the clustering worker."""
        handle = self.workers.get("clustering")
        if not handle:
            raise ValueError("Clustering worker not available")
        result = await handle.analyze_hypothesis(None, params)
        self.cluster_results = result
        self._record_task("clustering", params, result)
        return result

    @action
    async def execute_hotspot_analysis(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute hotspot analysis via the hotspot worker."""
        handle = self.workers.get("hotspot")
        if not handle:
            raise ValueError("Hotspot worker not available")
        result = await handle.analyze_hypothesis(None, params)
        self.hotspot_results = result
        self._record_task("hotspot_analysis", params, result)
        return result

    @action
    async def execute_binder_design(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute binder design via the BindCraft worker."""
        handle = self.workers.get("binder_design")
        if not handle:
            raise ValueError("Binder design worker not available")
        result = await handle.analyze_hypothesis(None, params)
        self.binder_designs.append(result)
        self._record_task("binder_design", params, result)
        return result

    # ------------------------------------------------------------------
    # Stopping & summary
    # ------------------------------------------------------------------

    @action
    async def should_stop(self, history: List[Dict[str, Any]]) -> bool:
        """Decide if the campaign should stop."""
        max_tasks = self.config.get("max_tasks_per_campaign", 10)
        min_affinity = self.config.get("min_binder_affinity", -10.0)

        if len(history) >= max_tasks:
            return True

        if self.binder_designs:
            best = max(d.get("affinity", float("-inf")) for d in self.binder_designs)
            if best <= min_affinity:
                return True

        return False

    @action
    async def summarize_campaign(self) -> Dict[str, Any]:
        """Summarise campaign results for the Executive."""
        best_binder = None
        best_affinity = float("-inf")
        for design in self.binder_designs:
            aff = design.get("affinity", float("-inf"))
            if aff > best_affinity:
                best_affinity = aff
                best_binder = design

        duration = (datetime.now() - self.start_time).total_seconds()
        return {
            "manager_id": self.manager_id,
            "allocated_nodes": self.allocated_nodes,
            "tasks_executed": self.task_history,
            "num_tasks": len(self.task_history),
            "duration_seconds": duration,
            "best_binder": best_binder,
            "all_binders": self.binder_designs,
            "structures_generated": len(self.current_structures),
            "simulations_run": len(self.simulation_results),
            "hotspots_identified": self.hotspot_results,
            "timestamp": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _record_task(
        self, task_type: str, params: Dict[str, Any], result: Dict[str, Any]
    ) -> None:
        self.task_history.append(
            {
                "task_type": task_type,
                "params": params,
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
        )
        self.tasks_completed += 1

    def _build_task_decision_prompt(self, current_state: Dict[str, Any]) -> str:
        return f"""You are a Manager agent coordinating a binder design campaign.

Current State:
- Structures generated: {len(self.current_structures)}
- Simulations completed: {len(self.simulation_results)}
- Hotspots identified: {self.hotspot_results is not None}
- Binders designed: {len(self.binder_designs)}
- Tasks completed: {self.tasks_completed}

Task History:
{self._format_task_history()}

Based on the current state, what should be the next task?

Options:
1. 'folding' - Fold protein structures
2. 'simulation' - Run MD simulations
3. 'clustering' - Cluster simulation trajectories
4. 'hotspot_analysis' - Identify binding hotspots
5. 'binder_design' - Design binder molecules
6. 'stop' - Campaign complete

Respond with ONLY the task name."""

    def _format_task_history(self) -> str:
        if not self.task_history:
            return "No tasks completed yet"
        lines = []
        for i, task in enumerate(self.task_history[-5:], 1):
            lines.append(f"{i}. {task['task_type']}")
        return "\n".join(lines)

    def _parse_task_decision(self, llm_response: str) -> str:
        response_lower = llm_response.lower().strip()
        valid = [
            "folding",
            "simulation",
            "clustering",
            "hotspot_analysis",
            "binder_design",
            "stop",
        ]
        for task in valid:
            if task in response_lower:
                return task
        logger.warning("Could not parse task decision: %s", llm_response)
        return "stop"
