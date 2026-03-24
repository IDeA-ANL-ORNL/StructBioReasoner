"""Hybrid Loop — 4-layer orchestrator (Wave 3).

Wires all four layers together into a single execution loop:

    Layer 1 (OpenClaw) — skill selection based on Jnana recommendations
    Layer 2 (Jnana)    — scientific reasoning, parameter bounding, evaluation
    Layer 3 (Artifact DAG) — shared state / computational provenance
    Layer 4 (Academy)  — distributed execution via AcademyDispatch

The loop supports both *interactive* (single-step) and *batch* (run-to-
convergence) modes, as well as *campaign* mode for multi-phase workflows
described in the PASC'26 paper.

Usage::

    loop = HybridLoop(artifact_store_root="/tmp/artifacts")
    await loop.start()

    # Batch mode: runs until convergence or max_iterations
    result = await loop.run("Design a binder for IL-17", max_iterations=5)

    # Interactive mode: step-by-step
    loop.set_goal("Design a binder for IL-17")
    step = await loop.step()

    # Campaign mode: multi-phase workflow
    phases = [
        CampaignPhase(name="exploration", goal="Identify hotspots",
                       step_sequence=["rag", "structure_prediction", "molecular_dynamics"]),
        CampaignPhase(name="design", goal="Design binders",
                       step_sequence=["computational_design", "molecular_dynamics", "free_energy"]),
    ]
    result = await loop.run_campaign("Design binder for NMNAT-2", phases)

    await loop.stop()
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

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


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------

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


@dataclass
class CampaignPhase:
    """A single phase in a multi-phase campaign.

    Each phase has its own sub-goal and a prescribed sequence of task types.
    Phases pass context to the next phase via artifacts stored in the DAG.
    """
    name: str
    goal: str
    step_sequence: List[str] = field(default_factory=list)
    max_iterations: int = 10

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TournamentRound:
    """Tracks a tournament round where hypotheses compete.

    The reasoning bridge's evaluate_results feeds into tournament scoring.
    Hypotheses are promoted (winners) or culled (losers) each round.
    """
    round_number: int
    phase_name: str = ""
    hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    scores: Dict[str, float] = field(default_factory=dict)
    promoted: List[str] = field(default_factory=list)
    culled: List[str] = field(default_factory=list)
    artifact_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CampaignMemory:
    """Long-term and short-term memory for multi-phase campaigns.

    Long-term memory persists across phases (key hotspots, top binders,
    experimental data). Short-term memory evolves and is periodically
    trimmed (workflow decisions, task outcomes).
    """
    long_term: Dict[str, Any] = field(default_factory=lambda: {
        "hotspots": [],
        "top_binders": [],
        "experimental_data": [],
        "design_constraints": [],
    })
    short_term: List[Dict[str, Any]] = field(default_factory=list)
    max_short_term: int = 20

    def add_long_term(self, category: str, entry: Any) -> None:
        """Add an entry to a long-term memory category."""
        if category not in self.long_term:
            self.long_term[category] = []
        self.long_term[category].append(entry)

    def add_short_term(self, entry: Dict[str, Any]) -> None:
        """Add an entry to short-term memory, trimming oldest if over limit."""
        self.short_term.append(entry)
        while len(self.short_term) > self.max_short_term:
            self.short_term.pop(0)

    def trim_short_term(self, keep: int = 10) -> None:
        """Manually trim short-term memory to *keep* most recent entries."""
        if len(self.short_term) > keep:
            self.short_term = self.short_term[-keep:]

    def get_context(self) -> Dict[str, Any]:
        """Return combined memory for Jnana reasoning context."""
        return {
            "long_term": self.long_term,
            "short_term": self.short_term[-10:],  # last 10 for context window
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "long_term": self.long_term,
            "short_term": self.short_term,
            "max_short_term": self.max_short_term,
        }


# Type alias for checkpoint callbacks
CheckpointCallback = Callable[
    [List[Dict[str, Any]], List[Dict[str, Any]], List[str]],
    Optional[Dict[str, Any]],
]


# ------------------------------------------------------------------
# HybridLoop
# ------------------------------------------------------------------

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
        checkpoint_callback: Optional[CheckpointCallback] = None,
        checkpoint_interval: int = 5,
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

        # Campaign state
        self._campaign_memory: Optional[CampaignMemory] = None
        self._tournament_rounds: List[TournamentRound] = []
        self._cross_hypothesis_patterns: List[Dict[str, Any]] = []

        # Checkpoint configuration
        self._checkpoint_callback = checkpoint_callback
        self._checkpoint_interval = checkpoint_interval
        self._last_checkpoint_scores: Dict[str, float] = {}

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

    @property
    def campaign_memory(self) -> Optional[CampaignMemory]:
        return self._campaign_memory

    @property
    def tournament_rounds(self) -> List[TournamentRound]:
        return list(self._tournament_rounds)

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

        # Inject campaign memory context into reasoning history if available
        if self._campaign_memory is not None:
            mem_ctx = self._campaign_memory.get_context()
            if mem_ctx["long_term"].get("design_constraints"):
                previous_conclusion = (
                    previous_conclusion
                    + f"\n[Memory constraints: {mem_ctx['long_term']['design_constraints'][-3:]}]"
                )

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

        # Update campaign memory if active
        if self._campaign_memory is not None:
            self._campaign_memory.add_short_term({
                "iteration": self._iteration,
                "task_type": task_type,
                "skill_name": skill_name,
                "evaluation": evaluation.to_dict(),
                "artifact_id": artifact.artifact_id,
            })

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
    # Campaign mode — multi-phase workflow
    # ------------------------------------------------------------------

    async def run_campaign(
        self,
        research_goal: str,
        phases: List[CampaignPhase],
        memory: Optional[CampaignMemory] = None,
    ) -> Dict[str, Any]:
        """Run a multi-phase campaign as described in the PASC'26 paper.

        Each phase has its own sub-goal and step sequence. Context flows
        between phases via the Artifact DAG and CampaignMemory.

        Parameters
        ----------
        research_goal : str
            The overarching campaign objective.
        phases : list of CampaignPhase
            Ordered phases to execute.
        memory : CampaignMemory, optional
            Pre-populated memory. A fresh one is created if not provided.
        """
        self._campaign_memory = memory or CampaignMemory()
        self._tournament_rounds = []

        # Store campaign start artifact
        campaign_meta = ArtifactMetadata(
            artifact_type=ArtifactType.WORKFLOW_CONFIG,
            skill_name="hybrid-loop",
            tags=frozenset(["campaign", "start"]),
        )
        campaign_artifact = create_artifact(
            metadata=campaign_meta,
            data={
                "research_goal": research_goal,
                "phases": [p.to_dict() for p in phases],
            },
        )
        self.artifact_dag.store(campaign_artifact)

        phase_results: List[Dict[str, Any]] = []
        all_steps: List[LoopStep] = []

        for phase_idx, phase in enumerate(phases):
            logger.info(
                "Campaign phase %d/%d: %s — %s",
                phase_idx + 1, len(phases), phase.name, phase.goal,
            )

            phase_result = await self._run_phase(
                research_goal=research_goal,
                phase=phase,
                phase_idx=phase_idx,
            )
            phase_results.append(phase_result)
            all_steps.extend(phase_result.get("_steps_raw", []))

            # Transfer phase artifacts into long-term memory
            for step_info in phase_result.get("steps", []):
                if step_info.get("artifact_id"):
                    self._campaign_memory.add_long_term(
                        "experimental_data",
                        {
                            "phase": phase.name,
                            "artifact_id": step_info["artifact_id"],
                            "task_type": step_info["task_type"],
                        },
                    )

            # Trim short-term memory between phases
            self._campaign_memory.trim_short_term()

            # Run cross-hypothesis learning between phases
            self._update_cross_hypothesis_patterns()

        return {
            "research_goal": research_goal,
            "phases_completed": len(phase_results),
            "total_phases": len(phases),
            "phase_results": [
                {k: v for k, v in pr.items() if k != "_steps_raw"}
                for pr in phase_results
            ],
            "tournament_rounds": [r.to_dict() for r in self._tournament_rounds],
            "memory": self._campaign_memory.to_dict(),
            "cross_hypothesis_patterns": self._cross_hypothesis_patterns,
        }

    async def _run_phase(
        self,
        research_goal: str,
        phase: CampaignPhase,
        phase_idx: int,
    ) -> Dict[str, Any]:
        """Execute a single campaign phase.

        If the phase has a step_sequence, we use it to guide recommendations.
        Otherwise we fall back to Jnana's free-form recommendations.
        """
        # Set the phase sub-goal
        phase_goal = f"{research_goal} — Phase: {phase.name} — {phase.goal}"
        self.set_goal(phase_goal)
        self.reasoning_bridge._generate_hypotheses(count=1)

        phase_steps: List[LoopStep] = []
        previous_run_type = "starting"
        previous_conclusion = ""

        sequence = list(phase.step_sequence) if phase.step_sequence else []
        step_idx = 0

        for iter_num in range(phase.max_iterations):
            step = await self.step(
                previous_run_type=previous_run_type,
                previous_conclusion=previous_conclusion,
            )
            phase_steps.append(step)

            if step.converged:
                break

            previous_run_type = step.task_type
            previous_conclusion = str(step.evaluation.get("evaluation", ""))

            # Advance step sequence pointer
            step_idx += 1
            if sequence and step_idx >= len(sequence):
                break

            # Check if checkpoint should fire
            self._maybe_fire_checkpoint(phase_steps, phase.name)

        # Run tournament scoring for the phase
        tournament = self._score_tournament_round(phase_steps, phase.name)
        if tournament:
            self._tournament_rounds.append(tournament)

        return {
            "phase_name": phase.name,
            "phase_goal": phase.goal,
            "iterations": len(phase_steps),
            "converged": phase_steps[-1].converged if phase_steps else False,
            "steps": [
                {
                    "iteration": s.iteration,
                    "task_type": s.task_type,
                    "skill_name": s.skill_name,
                    "artifact_id": s.artifact_id,
                    "converged": s.converged,
                }
                for s in phase_steps
            ],
            "tournament": tournament.to_dict() if tournament else None,
            "_steps_raw": phase_steps,
        }

    # ------------------------------------------------------------------
    # Tournament framework
    # ------------------------------------------------------------------

    def _score_tournament_round(
        self,
        phase_steps: List[LoopStep],
        phase_name: str,
    ) -> Optional[TournamentRound]:
        """Score a tournament round from phase steps.

        Collects evaluation scores from each step, ranks hypotheses,
        and determines which are promoted vs culled.
        """
        if not phase_steps:
            return None

        round_number = len(self._tournament_rounds) + 1

        # Collect all hypotheses and scores from evaluations
        all_scores: Dict[str, float] = {}
        artifact_ids: List[str] = []
        hypotheses: List[Dict[str, Any]] = []

        for step in phase_steps:
            if step.evaluation:
                scores = step.evaluation.get("scores", {})
                for k, v in scores.items():
                    if isinstance(v, (int, float)):
                        all_scores[f"{step.skill_name}:{k}"] = float(v)

            if step.artifact_id:
                artifact_ids.append(step.artifact_id)

            # Collect hypothesis info from recommendations
            if step.recommendation:
                hypotheses.append({
                    "task_type": step.task_type,
                    "rationale": step.recommendation.get("rationale", ""),
                    "confidence": step.recommendation.get("confidence", 0.0),
                })

        # Determine promoted vs culled based on scores
        promoted: List[str] = []
        culled: List[str] = []

        if all_scores:
            avg_score = sum(all_scores.values()) / len(all_scores)
            for key, score in all_scores.items():
                if score >= avg_score:
                    promoted.append(key)
                else:
                    culled.append(key)

        tournament = TournamentRound(
            round_number=round_number,
            phase_name=phase_name,
            hypotheses=hypotheses,
            scores=all_scores,
            promoted=promoted,
            culled=culled,
            artifact_ids=artifact_ids,
        )

        # Store tournament round in Artifact DAG
        meta = ArtifactMetadata(
            artifact_type=ArtifactType.SCORE_TABLE,
            skill_name="hybrid-loop",
            tags=frozenset([
                "tournament",
                f"round:{round_number}",
                f"phase:{phase_name}",
            ]),
        )
        art = create_artifact(
            metadata=meta,
            data=tournament.to_dict(),
            parent_ids=tuple(artifact_ids[:10]),  # link to phase artifacts
        )
        self.artifact_dag.store(art)

        logger.info(
            "Tournament round %d: %d promoted, %d culled",
            round_number, len(promoted), len(culled),
        )
        return tournament

    # ------------------------------------------------------------------
    # Checkpoint / human-in-the-loop
    # ------------------------------------------------------------------

    def _maybe_fire_checkpoint(
        self,
        phase_steps: List[LoopStep],
        phase_name: str,
    ) -> None:
        """Fire checkpoint callback if conditions are met."""
        if self._checkpoint_callback is None:
            return

        should_fire = False

        # Fire at interval
        if len(phase_steps) % self._checkpoint_interval == 0:
            should_fire = True

        # Fire on score plateau
        if len(phase_steps) >= 2:
            current_scores = phase_steps[-1].evaluation.get("scores", {})
            previous_scores = phase_steps[-2].evaluation.get("scores", {})
            if current_scores and previous_scores and current_scores == previous_scores:
                should_fire = True

        if not should_fire:
            return

        # Build checkpoint data
        top_hypotheses = [
            {
                "task_type": s.task_type,
                "evaluation": s.evaluation,
                "artifact_id": s.artifact_id,
            }
            for s in phase_steps[-5:]  # last 5 steps
        ]
        evidence = [
            s.evaluation.get("evaluation", "")
            for s in phase_steps[-3:]
        ]
        uncertainties = [
            f"Phase {phase_name} iteration {len(phase_steps)}",
        ]

        try:
            override = self._checkpoint_callback(
                top_hypotheses, evidence, uncertainties,
            )
            if override and isinstance(override, dict):
                # Inject override into reasoning bridge history
                self.reasoning_bridge._append_history(
                    decision=f"Human override at checkpoint",
                    key_items=override.get("key_items"),
                    configuration=override.get("configuration"),
                )
                logger.info("Checkpoint override applied at iteration %d", len(phase_steps))
        except Exception as exc:
            logger.warning("Checkpoint callback failed: %s", exc)

    # ------------------------------------------------------------------
    # Cross-hypothesis learning
    # ------------------------------------------------------------------

    def _update_cross_hypothesis_patterns(self) -> None:
        """Identify shared success/failure patterns across hypotheses.

        When multiple hypotheses target related proteins/motifs, extract
        common patterns and store them as design constraints in long-term
        memory.
        """
        if self._campaign_memory is None:
            return

        # Collect all evaluation data from short-term memory
        task_evaluations: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for entry in self._campaign_memory.short_term:
            task_type = entry.get("task_type", "")
            evaluation = entry.get("evaluation", {})
            if task_type and evaluation:
                task_evaluations[task_type].append(evaluation)

        # Find patterns in task types that appear multiple times
        for task_type, evals in task_evaluations.items():
            if len(evals) < 2:
                continue

            # Collect scores across evaluations for this task type
            score_keys: Dict[str, List[float]] = defaultdict(list)
            for ev in evals:
                for k, v in ev.get("scores", {}).items():
                    if isinstance(v, (int, float)):
                        score_keys[k].append(float(v))

            # Identify consistently high/low scoring metrics
            for metric, values in score_keys.items():
                if len(values) < 2:
                    continue
                avg = sum(values) / len(values)
                pattern = {
                    "task_type": task_type,
                    "metric": metric,
                    "avg_score": avg,
                    "count": len(values),
                    "trend": "consistent" if max(values) - min(values) < abs(avg) * 0.3 else "variable",
                }
                self._cross_hypothesis_patterns.append(pattern)

                # Store as design constraint in long-term memory
                if pattern["trend"] == "consistent":
                    self._campaign_memory.add_long_term(
                        "design_constraints",
                        {
                            "source": "cross_hypothesis",
                            "task_type": task_type,
                            "metric": metric,
                            "target_value": avg,
                        },
                    )

        logger.info(
            "Cross-hypothesis learning: %d patterns found",
            len(self._cross_hypothesis_patterns),
        )

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
