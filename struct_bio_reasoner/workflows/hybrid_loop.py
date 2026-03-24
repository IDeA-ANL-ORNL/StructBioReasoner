"""Hybrid Loop — 4-layer orchestrator (Wave 3).

Wires all four layers together into a single execution loop:

    Layer 1 (OpenClaw) — skill selection based on Jnana recommendations
    Layer 2 (Jnana)    — scientific reasoning, parameter bounding, evaluation
    Layer 3 (Artifact DAG) — shared state / computational provenance
    Layer 4 (Academy)  — distributed execution via AcademyDispatch

The loop supports both *interactive* (single-step) and *batch* (run-to-
convergence) modes.

Usage::

    loop = HybridLoop(artifact_store_root="/tmp/artifacts")
    await loop.start()

    # Batch mode: runs until convergence or max_iterations
    result = await loop.run("Design a binder for IL-17", max_iterations=5)

    # Interactive mode: step-by-step
    loop.set_goal("Design a binder for IL-17")
    step = await loop.step()

    await loop.stop()
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from skills._shared.artifact import ArtifactMetadata, ArtifactType, create_artifact
from skills._shared.artifact_dag import ArtifactDAG


def _import_jnana_bridge():
    """Import JnanaReasoningBridge from the hyphenated skills/jnana-reasoning dir."""
    mod_name = "_jnana_reason"
    if mod_name in sys.modules:
        return sys.modules[mod_name].JnanaReasoningBridge
    reason_path = (
        Path(__file__).resolve().parent.parent.parent
        / "skills" / "jnana-reasoning" / "scripts" / "reason.py"
    )
    spec = importlib.util.spec_from_file_location(mod_name, str(reason_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod.JnanaReasoningBridge

logger = logging.getLogger(__name__)

# Map Jnana task_type recommendations to canonical skill names
_TASK_TYPE_TO_SKILL: Dict[str, str] = {
    "computational_design": "bindcraft",
    "molecular_dynamics": "md",
    "analysis": "trajectory_analysis",
    "free_energy": "md",
    "structure_prediction": "folding",
    "rag": "rag",
    "literature": "rag",
    "conservation": "conservation",
    "protein_lm": "protein_lm",
}


@dataclass
class LoopStep:
    """Result of a single iteration of the hybrid loop."""
    iteration: int
    task_type: str
    skill_name: str
    recommendation: Dict[str, Any] = field(default_factory=dict)
    bounded_config: Dict[str, Any] = field(default_factory=dict)
    dispatch_result: Dict[str, Any] = field(default_factory=dict)
    artifact_id: Optional[str] = None
    evaluation: Dict[str, Any] = field(default_factory=dict)
    converged: bool = False


class HybridLoop:
    """4-layer hybrid orchestrator.

    Connects:
    - JnanaReasoningBridge (Layer 2) for scientific reasoning
    - ArtifactDAG (Layer 3) for shared state
    - AcademyDispatch (Layer 4) for distributed execution

    Layer 1 (OpenClaw) calls this loop through the MCP server.
    """

    def __init__(
        self,
        artifact_store_root: str = "artifact_store",
        academy_config: Optional[Any] = None,
    ) -> None:
        self._artifact_store_root = artifact_store_root
        self._academy_config = academy_config

        # Lazy-initialised layers
        self._reasoning_bridge = None
        self._artifact_dag = None
        self._academy_dispatch = None

        # Loop state
        self._iteration = 0
        self._steps: List[LoopStep] = []
        self._started = False

    # ------------------------------------------------------------------
    # Layer accessors (lazy)
    # ------------------------------------------------------------------

    @property
    def reasoning_bridge(self):
        if self._reasoning_bridge is None:
            JnanaReasoningBridge = _import_jnana_bridge()
            self._reasoning_bridge = JnanaReasoningBridge(
                artifact_store_root=self._artifact_store_root,
            )
        return self._reasoning_bridge

    @property
    def artifact_dag(self) -> ArtifactDAG:
        if self._artifact_dag is None:
            self._artifact_dag = ArtifactDAG(self._artifact_store_root)
        return self._artifact_dag

    @property
    def academy_dispatch(self):
        if self._academy_dispatch is None:
            from struct_bio_reasoner.academy.dispatch import AcademyDispatch
            from struct_bio_reasoner.academy.config import AcademyConfig
            config = self._academy_config or AcademyConfig()
            self._academy_dispatch = AcademyDispatch(config)
        return self._academy_dispatch

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the Academy dispatch layer."""
        if self._started:
            return
        await self.academy_dispatch.start()
        self._started = True
        logger.info("HybridLoop started")

    async def stop(self) -> None:
        """Shut down the Academy dispatch layer."""
        if not self._started:
            return
        await self.academy_dispatch.stop()
        self._started = False
        logger.info("HybridLoop stopped")

    # ------------------------------------------------------------------
    # Goal & interactive mode
    # ------------------------------------------------------------------

    def set_goal(self, research_goal: str) -> Dict[str, Any]:
        """Set the research goal (Layer 2). Returns the initial plan."""
        plan = self.reasoning_bridge.set_research_goal(research_goal)
        self._iteration = 0
        self._steps = []
        return plan.to_dict()

    async def step(
        self,
        previous_run_type: str = "starting",
        previous_conclusion: str = "",
    ) -> LoopStep:
        """Execute a single iteration of the hybrid loop.

        1. Jnana recommends next action (Tier 1)
        2. Map recommendation → skill name
        3. Jnana bounds parameters (Tier 2)
        4. Academy dispatches to worker
        5. Store result in Artifact DAG
        6. Jnana evaluates results
        7. Check convergence
        """
        self._iteration += 1

        # 1. Jnana Tier-1: recommend next action
        rec = self.reasoning_bridge.recommend_next_action(
            previous_run_type=previous_run_type,
            previous_conclusion=previous_conclusion,
        )

        task_type = rec.task_type

        # Early exit if Jnana says "stop"
        if task_type == "stop":
            step = LoopStep(
                iteration=self._iteration,
                task_type="stop",
                skill_name="",
                recommendation=rec.to_dict(),
                converged=True,
            )
            self._steps.append(step)
            return step

        # 2. Map to skill name
        skill_name = _TASK_TYPE_TO_SKILL.get(task_type, task_type)

        # 3. Jnana Tier-2: bound parameters
        bounded = self.reasoning_bridge.bound_parameters(
            skill_name=skill_name,
            task_type=task_type,
        )

        # 4. Academy dispatch
        dispatch_result = await self.academy_dispatch.dispatch(
            skill_name, bounded.parameters
        )

        # 5. Store result in Artifact DAG
        meta = ArtifactMetadata(
            artifact_type=ArtifactType.RAW_OUTPUT,
            skill_name=skill_name,
            tags=frozenset([f"iteration:{self._iteration}", f"task:{task_type}"]),
        )
        artifact = create_artifact(metadata=meta, data=dispatch_result)
        self.artifact_dag.store(artifact)

        # 6. Jnana evaluate results
        evaluation = self.reasoning_bridge.evaluate_results([artifact.artifact_id])

        # 7. Check convergence
        converged = self.reasoning_bridge.check_convergence()

        step = LoopStep(
            iteration=self._iteration,
            task_type=task_type,
            skill_name=skill_name,
            recommendation=rec.to_dict(),
            bounded_config=bounded.to_dict(),
            dispatch_result=dispatch_result,
            artifact_id=artifact.artifact_id,
            evaluation=evaluation.to_dict(),
            converged=converged,
        )
        self._steps.append(step)
        return step

    # ------------------------------------------------------------------
    # Batch mode
    # ------------------------------------------------------------------

    async def run(
        self,
        research_goal: str,
        max_iterations: int = 10,
    ) -> Dict[str, Any]:
        """Run the full hybrid loop to convergence or max_iterations.

        This is the batch-mode entry point. It:
        1. Sets the research goal
        2. Generates an initial hypothesis
        3. Loops: recommend → dispatch → evaluate → converge?
        4. Returns summary with all steps and artifacts
        """
        self.set_goal(research_goal)

        # Generate an initial hypothesis so evaluation has something to work with
        self.reasoning_bridge._generate_hypotheses(count=1)

        previous_run_type = "starting"
        previous_conclusion = ""

        for _ in range(max_iterations):
            step = await self.step(
                previous_run_type=previous_run_type,
                previous_conclusion=previous_conclusion,
            )

            if step.converged:
                logger.info("Converged after %d iterations", step.iteration)
                break

            # Carry forward for next iteration
            previous_run_type = step.task_type
            previous_conclusion = str(step.evaluation.get("evaluation", ""))

        return {
            "research_goal": research_goal,
            "iterations": len(self._steps),
            "converged": self._steps[-1].converged if self._steps else False,
            "steps": [
                {
                    "iteration": s.iteration,
                    "task_type": s.task_type,
                    "skill_name": s.skill_name,
                    "artifact_id": s.artifact_id,
                    "converged": s.converged,
                }
                for s in self._steps
            ],
            "final_evaluation": self._steps[-1].evaluation if self._steps else {},
        }

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def iteration(self) -> int:
        return self._iteration

    @property
    def steps(self) -> List[LoopStep]:
        return list(self._steps)

    def get_status(self) -> Dict[str, Any]:
        return {
            "iteration": self._iteration,
            "started": self._started,
            "reasoning_status": self.reasoning_bridge.get_status(),
            "active_workers": (
                self.academy_dispatch.list_active_workers()
                if self._started else []
            ),
        }

    # Async context manager
    async def __aenter__(self) -> "HybridLoop":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()
