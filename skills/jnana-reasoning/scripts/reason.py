#!/usr/bin/env python3
"""
Jnana Reasoning Bridge — Scientific intelligence layer (Layer 2).

Bridges the OpenClaw agent loop (Layer 1) and the Jnana CoScientist API
to provide hypothesis-driven scientific reasoning.  This module does NOT
orchestrate tools directly — it provides recommendations, parameter bounds,
and hypothesis evaluation that OpenClaw uses to select and invoke skills.

Two-tier prompting is preserved:
  Tier 1  recommend_next_action()  → what task type to run next
  Tier 2  bound_parameters()       → bounded config for the chosen skill
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
_UTC = timezone.utc

# ---------------------------------------------------------------------------
# Lazy imports — Jnana / Academy may not be installed in every environment.
# ---------------------------------------------------------------------------

_coscientist_cls = None
_academy_agent_cls = None
_academy_action = None
_academy_handle_cls = None
_academy_manager_cls = None
_academy_local_exchange = None


def _ensure_jnana():
    global _coscientist_cls
    if _coscientist_cls is not None:
        return
    try:
        from jnana.protognosis.core.coscientist import CoScientist
        _coscientist_cls = CoScientist
    except ImportError:
        logger.warning("Jnana not installed — CoScientist unavailable, using stub mode")


def _ensure_academy():
    global _academy_agent_cls, _academy_action, _academy_handle_cls
    global _academy_manager_cls, _academy_local_exchange
    if _academy_agent_cls is not None:
        return
    try:
        from academy.agent import Agent, action
        from academy.handle import Handle
        from academy.manager import Manager
        from academy.exchange import LocalExchangeFactory
        _academy_agent_cls = Agent
        _academy_action = action
        _academy_handle_cls = Handle
        _academy_manager_cls = Manager
        _academy_local_exchange = LocalExchangeFactory
    except ImportError:
        logger.warning("Academy not installed — agent dispatch unavailable")


# ---------------------------------------------------------------------------
# Artifact DAG helpers (Layer 3 integration)
# ---------------------------------------------------------------------------

def _get_artifact_store():
    """Import the shared ArtifactStore at call time to avoid circular deps."""
    from skills._shared.artifact_store import ArtifactStore
    return ArtifactStore


def _get_artifact_helpers():
    """Import create_artifact + metadata types."""
    from skills._shared.artifact import (
        ArtifactMetadata,
        ArtifactType,
        create_artifact,
    )
    return create_artifact, ArtifactMetadata, ArtifactType


# ---------------------------------------------------------------------------
# Data classes returned by the bridge
# ---------------------------------------------------------------------------

@dataclass
class PlanConfig:
    """Initial plan returned by set_research_goal."""
    goal: str
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    target_sequence: str = ""
    binder_sequence: str = ""
    strategies: List[str] = field(default_factory=lambda: ["literature_exploration"])
    created_at: str = field(default_factory=lambda: datetime.now(tz=_UTC).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Recommendation:
    """Tier-1 output: what to do next."""
    task_type: str  # computational_design | molecular_dynamics | analysis | free_energy | stop
    rationale: str = ""
    confidence: float = 0.0
    priority: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BoundedConfig:
    """Tier-2 output: bounded parameter configuration for a skill."""
    parameters: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Evaluation:
    """Result of evaluating artifacts against hypotheses."""
    evaluation: str = ""
    decision: str = "continue"  # continue | complete
    updated_hypothesis: str = ""
    scores: Dict[str, float] = field(default_factory=dict)
    artifact_ids_evaluated: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Hypothesis:
    """A scientific hypothesis."""
    hypothesis_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: str = ""
    strategies: List[str] = field(default_factory=list)
    confidence: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(tz=_UTC).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Prompt templates — ported from recommender_prompts.py and prompts.py
# ---------------------------------------------------------------------------

# Master config schema for each task type (from prompts.py config_master)
CONFIG_MASTER: Dict[str, Any] = {
    "rag": {"prompt": "string"},
    "computational_design": {
        "binder_sequence": "string",
        "num_rounds": "int",
        "batch_size": "int",
        "max_retries": "int",
        "sampling_temp": "float",
        "qc_kwargs": {
            "max_repeat": "int",
            "max_appearance_ratio": "float",
            "max_charge": "int",
            "max_charge_ratio": "float",
            "max_hydrophobic_ratio": "float",
            "min_diversity": "int",
        },
        "constraint": {"residues_bind": "list[string]"},
    },
    "structure_prediction": {
        "sequences": "list[list[str]]",
        "names": "list[str]",
    },
    "molecular_dynamics": {
        "simulation_paths": "list[str]",
        "root_output_path": "str",
        "steps": "int",
    },
    "analysis": {
        "data_type": "str",
        "analysis_type": "str",
        "distance_cutoff": "float",
    },
    "free_energy": {
        "simulation_paths": "list[str]",
    },
}

# Available task types for the recommendation tier
AVAILABLE_TASK_TYPES = [
    "computational_design",
    "molecular_dynamics",
    "analysis",
    "free_energy",
    "stop",
]


def _build_recommendation_prompt(
    research_goal: str,
    previous_run_type: str,
    previous_conclusion: str,
    history: Dict[str, List],
    enabled_agents: Optional[List[str]] = None,
) -> str:
    """Tier-1 prompt: recommend the next task type.

    Ported from RecommenderPromptManager.recommend_prompt() and the
    conclusion prompts in prompts.py.
    """
    agents = enabled_agents or AVAILABLE_TASK_TYPES
    decisions_str = json.dumps(history.get("decisions", []), indent=2, default=str) or "No history"
    results_str = json.dumps(history.get("results", []), indent=2, default=str) or "No history"
    configs_str = json.dumps(history.get("configurations", []), indent=2, default=str) or "No history"
    key_items_str = json.dumps(history.get("key_items", []), indent=2, default=str) or "No key items yet"

    return f"""You are an AI co-scientist specializing in recommending the next experiment to perform.

Research goal:
{research_goal}

Previous run type: {previous_run_type}
Previous run conclusion: {previous_conclusion}

HISTORY OF DECISIONS (least recent first):
{decisions_str}

HISTORY OF RESULTS (least recent first):
{results_str}

HISTORY OF CONFIGURATIONS (least recent first):
{configs_str}

KEY ITEMS TO CONSIDER:
{key_items_str}

AVAILABLE NEXT STEPS: {agents}

Your recommendation must be in JSON format:
{{
    "next_task": "one of {agents}",
    "rationale": "detailed explanation of why this is the best next step",
    "confidence": 0.0-1.0
}}

NOTE: This is a RECOMMENDATION only. The actual configuration will be generated in a separate step."""


def _build_parameter_prompt(
    research_goal: str,
    skill_name: str,
    task_type: str,
    recommendation: Dict[str, Any],
    history: Dict[str, List],
) -> str:
    """Tier-2 prompt: generate bounded parameter configuration.

    Ported from the various PromptManager.running_prompt() methods in prompts.py.
    """
    config_schema = CONFIG_MASTER.get(task_type, {})
    config_schema_str = json.dumps(config_schema, indent=2)

    decisions_str = json.dumps(history.get("decisions", []), indent=2, default=str) or "No history"
    results_str = json.dumps(history.get("results", []), indent=2, default=str) or "No history"
    configs_str = json.dumps(history.get("configurations", []), indent=2, default=str) or "No history"
    key_items_str = json.dumps(history.get("key_items", []), indent=2, default=str) or "No key items yet"

    return f"""You are an expert in computational peptide design optimization.
Generate the next configuration for the '{task_type}' task using skill '{skill_name}'.

RECOMMENDATION FROM PREVIOUS STEP:
Task: {recommendation.get('next_task', task_type)}
Rationale: {recommendation.get('rationale', 'N/A')}

HISTORY OF DECISIONS (least recent first):
{decisions_str}

HISTORY OF RESULTS (least recent first):
{results_str}

HISTORY OF CONFIGURATIONS (least recent first):
{configs_str}

KEY ITEMS TO CONSIDER:
{key_items_str}

Research goal: {research_goal}

IMPORTANT: You MUST provide a complete configuration in JSON format matching this schema:
{config_schema_str}

Generate the configuration now (return ONLY the JSON):"""


def _build_evaluation_prompt(
    research_goal: str,
    artifacts_data: List[Dict[str, Any]],
    hypotheses: List[Dict[str, Any]],
    history: Dict[str, List],
) -> str:
    """Prompt for evaluating experimental results against hypotheses."""
    artifacts_str = json.dumps(artifacts_data, indent=2, default=str)
    hypotheses_str = json.dumps(hypotheses, indent=2, default=str)
    history_str = json.dumps(history, indent=2, default=str)

    return f"""You are an expert in evaluating computational biology experimental results.

Research goal: {research_goal}

ARTIFACTS TO EVALUATE:
{artifacts_str}

CURRENT HYPOTHESES:
{hypotheses_str}

EXPERIMENT HISTORY:
{history_str}

Evaluate the artifacts against the hypotheses and provide your assessment in JSON format:
{{
    "evaluation": "detailed assessment of results",
    "decision": "continue|complete",
    "updated_hypothesis": "refined hypothesis based on evidence",
    "scores": {{"metric_name": score_value}}
}}"""


# ---------------------------------------------------------------------------
# Academy Agent wrapper — ported from jnana_agent.py
# ---------------------------------------------------------------------------

class _JnanaReasoningAgent:
    """Academy Agent subclass for async reasoning.

    This mirrors JnanaAgent from jnana_agent.py but adapted for the new
    bridge pattern.  The @action methods are only activated when Academy
    is installed.
    """

    def __init__(self, bridge: "JnanaReasoningBridge"):
        self.bridge = bridge

    async def generate_recommendation(
        self,
        results: Dict[str, Any],
        previous_run_type: str,
    ) -> Recommendation:
        """Academy @action: Tier-1 recommendation."""
        return self.bridge.recommend_next_action(
            previous_run_type=previous_run_type,
            previous_conclusion=json.dumps(results, default=str),
        )

    async def plan_run(
        self,
        recommendation: Dict[str, Any],
        skill_name: str,
        task_type: str,
    ) -> BoundedConfig:
        """Academy @action: Tier-2 parameter bounding."""
        return self.bridge.bound_parameters(skill_name=skill_name, task_type=task_type)


# ---------------------------------------------------------------------------
# JnanaReasoningBridge — main class
# ---------------------------------------------------------------------------

class JnanaReasoningBridge:
    """Bridge between the OpenClaw agent loop and Jnana scientific reasoning.

    This is Layer 2 of the 4-layer hybrid architecture.  It wraps:
      - Jnana CoScientist for hypothesis generation / improvement
      - Two-tier prompting (recommend -> bound_parameters)
      - Artifact DAG reads for result evaluation
      - Academy @action patterns for async operation

    The bridge does NOT invoke tools.  It returns typed recommendations
    that OpenClaw (Layer 1) uses to select and invoke skills.
    """

    def __init__(
        self,
        artifact_store_root: str | Path = "artifact_store",
        llm_provider: str = "openai",
        llm_model: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        enabled_agents: Optional[List[str]] = None,
    ):
        self._artifact_store_root = Path(artifact_store_root)
        self._artifact_store = None  # lazy
        self._llm_provider = llm_provider
        self._llm_model = llm_model
        self._llm_api_key = llm_api_key
        self._llm = None  # lazy

        self.coscientist = None  # set in set_research_goal
        self.research_goal: str = ""
        self.plan_config: Optional[PlanConfig] = None

        self.enabled_agents = enabled_agents or AVAILABLE_TASK_TYPES

        # Rolling history — mirrors BinderDesignSystem.history
        self.history: Dict[str, List] = {
            "key_items": [],
            "decisions": [],
            "configurations": [],
            "results": [],
            "recommendations": [],
        }
        self._max_history = 10

        # Internal hypothesis store
        self._hypotheses: List[Hypothesis] = []

        # Academy agent wrapper (lazy)
        self._academy_agent: Optional[_JnanaReasoningAgent] = None

        logger.info("JnanaReasoningBridge initialized (provider=%s)", llm_provider)

    # -- Lazy loaders -------------------------------------------------------

    @property
    def artifact_store(self):
        if self._artifact_store is None:
            ArtifactStore = _get_artifact_store()
            self._artifact_store = ArtifactStore(self._artifact_store_root)
        return self._artifact_store

    @property
    def llm(self):
        if self._llm is None:
            try:
                from struct_bio_reasoner.utils.llm_interface import create_llm
                self._llm = create_llm(
                    provider=self._llm_provider,
                    api_key=self._llm_api_key,
                    model=self._llm_model,
                )
            except ImportError:
                logger.warning("LLM interface not available — reasoning will return stubs")
        return self._llm

    # -- History helpers (ported from BinderDesignSystem.append_history) -----

    def _append_history(
        self,
        *,
        key_items: Any = None,
        decision: Optional[str] = None,
        configuration: Any = None,
        results: Any = None,
        recommendations: Any = None,
    ) -> None:
        if key_items is not None:
            self.history["key_items"].append(key_items)
        if recommendations is not None:
            self.history["recommendations"].append(
                recommendations if isinstance(recommendations, (str, dict))
                else str(recommendations)
            )
        self.history["decisions"].append(decision or "No decision")

        # Serialize config / results to string, truncated
        for key, value in [("configurations", configuration), ("results", results)]:
            if value is not None:
                try:
                    serialized = json.dumps(value, default=str)
                except Exception:
                    serialized = str(value)
                self.history[key].append(serialized[:500])
            else:
                self.history[key].append(f"No {key[:-1]}")

        # Trim to max_history
        for key in ("decisions", "configurations", "results", "recommendations"):
            while len(self.history[key]) > self._max_history:
                self.history[key].pop(0)

    # -----------------------------------------------------------------------
    # Public API — called by OpenClaw agent loop
    # -----------------------------------------------------------------------

    def set_research_goal(self, goal: str) -> PlanConfig:
        """Initialize CoScientist with a research goal.  Returns initial plan.

        This kicks off the scientific reasoning session.  If Jnana is
        installed it delegates to ``CoScientist.set_research_goal()``.
        """
        self.research_goal = goal
        logger.info("Setting research goal: %s", goal[:120])

        # Extract sequences from goal text
        target_seq = self._extract_sequence(goal, "target")
        binder_seq = self._extract_sequence(goal, "binder")

        # Try to initialize CoScientist
        _ensure_jnana()
        if _coscientist_cls is not None:
            try:
                self.coscientist = _coscientist_cls(llm_config=self._llm_provider)
                self.coscientist.set_research_goal(goal)
                logger.info("CoScientist initialized for goal")
            except Exception as exc:
                logger.warning("CoScientist init failed: %s — continuing in stub mode", exc)
                self.coscientist = None

        self.plan_config = PlanConfig(
            goal=goal,
            target_sequence=target_seq,
            binder_sequence=binder_seq,
        )

        # Store as initial artifact
        self._store_reasoning_artifact(
            data=self.plan_config.to_dict(),
            artifact_type_str="hypothesis",
            tags=frozenset(["plan", "initial"]),
        )

        self._append_history(decision="Set research goal", configuration=self.plan_config.to_dict())
        return self.plan_config

    def recommend_next_action(
        self,
        previous_run_type: str = "starting",
        previous_conclusion: str = "",
    ) -> Recommendation:
        """Tier 1: Evaluate current state, recommend next task type.

        Returns a Recommendation with task_type in
        {computational_design, molecular_dynamics, analysis, free_energy, stop}.
        """
        prompt = _build_recommendation_prompt(
            research_goal=self.research_goal,
            previous_run_type=previous_run_type,
            previous_conclusion=previous_conclusion,
            history=self.history,
            enabled_agents=self.enabled_agents,
        )

        parsed = self._llm_json_call(
            prompt,
            schema={"next_task": "string", "rationale": "string", "confidence": "float"},
            system_prompt="You are an AI co-scientist. Output ONLY valid JSON.",
        )

        rec = Recommendation(
            task_type=parsed.get("next_task", "stop"),
            rationale=parsed.get("rationale", ""),
            confidence=parsed.get("confidence", 0.0),
            metadata={"previous_run_type": previous_run_type},
        )

        self._append_history(
            decision=f"Recommended: {rec.task_type}",
            recommendations=rec.to_dict(),
        )

        self._store_reasoning_artifact(
            data=rec.to_dict(),
            artifact_type_str="analysis",
            tags=frozenset(["recommendation", f"tier1:{rec.task_type}"]),
        )

        logger.info("Tier-1 recommendation: %s (confidence=%.2f)", rec.task_type, rec.confidence)
        return rec

    def bound_parameters(self, skill_name: str, task_type: str) -> BoundedConfig:
        """Tier 2: Given selected skill, generate bounded parameter config.

        Uses the latest recommendation from history as context.
        """
        latest_rec = {}
        if self.history["recommendations"]:
            latest = self.history["recommendations"][-1]
            latest_rec = latest if isinstance(latest, dict) else {}

        prompt = _build_parameter_prompt(
            research_goal=self.research_goal,
            skill_name=skill_name,
            task_type=task_type,
            recommendation=latest_rec,
            history=self.history,
        )

        config_schema = CONFIG_MASTER.get(task_type, {})
        parsed = self._llm_json_call(
            prompt,
            schema=config_schema,
            system_prompt="You are an expert computational biologist. Output ONLY valid JSON.",
        )

        config = BoundedConfig(
            parameters=parsed,
            constraints={"task_type": task_type, "skill": skill_name},
            rationale=latest_rec.get("rationale", ""),
        )

        self._append_history(
            decision=f"Bounded params for {skill_name}/{task_type}",
            configuration=config.to_dict(),
        )

        self._store_reasoning_artifact(
            data=config.to_dict(),
            artifact_type_str="parameter_set",
            tags=frozenset(["tier2", f"skill:{skill_name}"]),
        )

        logger.info("Tier-2 bounded config for %s/%s", skill_name, task_type)
        return config

    def evaluate_results(self, artifact_ids: List[str]) -> Evaluation:
        """Read artifacts from the DAG, evaluate against hypotheses.

        Returns evaluation with a decision of ``continue`` or ``complete``.
        """
        artifacts_data = []
        for aid in artifact_ids:
            art = self.artifact_store.get(aid)
            if art is not None:
                artifacts_data.append(art.to_dict())
            else:
                logger.warning("Artifact %s not found in store", aid)

        hypotheses_data = [h.to_dict() for h in self._hypotheses]

        prompt = _build_evaluation_prompt(
            research_goal=self.research_goal,
            artifacts_data=artifacts_data,
            hypotheses=hypotheses_data,
            history=self.history,
        )

        parsed = self._llm_json_call(
            prompt,
            schema={
                "evaluation": "string",
                "decision": "string",
                "updated_hypothesis": "string",
                "scores": "dict",
            },
            system_prompt="You are an expert evaluator. Output ONLY valid JSON.",
        )

        evaluation = Evaluation(
            evaluation=parsed.get("evaluation", ""),
            decision=parsed.get("decision", "continue"),
            updated_hypothesis=parsed.get("updated_hypothesis", ""),
            scores=parsed.get("scores", {}),
            artifact_ids_evaluated=artifact_ids,
        )

        # Improve hypothesis if CoScientist is active
        if self.coscientist and self._hypotheses:
            try:
                self.coscientist.improve_hypothesis(
                    self._hypotheses[-1].hypothesis_id,
                    {"evaluation": evaluation.evaluation, "scores": evaluation.scores},
                )
            except Exception as exc:
                logger.warning("CoScientist improve_hypothesis failed: %s", exc)

        self._append_history(
            decision=f"Evaluated {len(artifact_ids)} artifacts → {evaluation.decision}",
            results=evaluation.to_dict(),
        )

        self._store_reasoning_artifact(
            data=evaluation.to_dict(),
            artifact_type_str="analysis",
            tags=frozenset(["evaluation", f"decision:{evaluation.decision}"]),
        )

        logger.info("Evaluation: decision=%s", evaluation.decision)
        return evaluation

    def check_convergence(self) -> bool:
        """Has the research goal been satisfied?

        Checks the latest evaluation decision and hypothesis confidence.
        """
        # If the last recommendation was "stop", we've converged
        if self.history["recommendations"]:
            latest = self.history["recommendations"][-1]
            if isinstance(latest, dict) and latest.get("task_type") == "stop":
                return True

        # If the latest evaluation says "complete"
        if self.history["results"]:
            latest_result = self.history["results"][-1]
            if isinstance(latest_result, str) and '"decision": "complete"' in latest_result:
                return True

        # Delegate to CoScientist if available
        if self.coscientist:
            try:
                hypotheses = self.coscientist.get_all_hypotheses()
                if hypotheses and all(
                    getattr(h, "confidence", 0) > 0.9 for h in hypotheses
                ):
                    return True
            except Exception:
                pass

        return False

    # -----------------------------------------------------------------------
    # Internal — Jnana / CoScientist integration
    # -----------------------------------------------------------------------

    def _generate_hypotheses(self, count: int = 1) -> List[Hypothesis]:
        """Generate hypotheses using CoScientist."""
        results: List[Hypothesis] = []
        if self.coscientist:
            try:
                self.coscientist.start()
                ids = self.coscientist.generate_hypotheses(
                    count=count,
                    strategies=["literature_exploration"],
                )
                self.coscientist.wait_for_completion(timeout=120)
                all_hyps = self.coscientist.get_all_hypotheses()
                for h in all_hyps:
                    hyp = Hypothesis(
                        hypothesis_id=getattr(h, "id", str(uuid.uuid4())[:8]),
                        content=getattr(h, "content", str(h)),
                        confidence=getattr(h, "confidence", 0.0),
                    )
                    results.append(hyp)
                    self._hypotheses.append(hyp)
            except Exception as exc:
                logger.warning("Hypothesis generation failed: %s", exc)
        else:
            # Stub mode — create a placeholder hypothesis
            hyp = Hypothesis(
                content=f"Hypothesis for: {self.research_goal[:100]}",
                strategies=["stub"],
            )
            results.append(hyp)
            self._hypotheses.append(hyp)
        return results

    def _improve_hypothesis(
        self, hypothesis_id: str, results: Dict[str, Any]
    ) -> Optional[Hypothesis]:
        """Improve a hypothesis based on experimental results."""
        if self.coscientist:
            try:
                improved = self.coscientist.improve_hypothesis(hypothesis_id, results)
                hyp = Hypothesis(
                    hypothesis_id=hypothesis_id,
                    content=getattr(improved, "content", str(improved)),
                    confidence=getattr(improved, "confidence", 0.0),
                )
                return hyp
            except Exception as exc:
                logger.warning("Hypothesis improvement failed: %s", exc)
        return None

    # -----------------------------------------------------------------------
    # LLM helpers
    # -----------------------------------------------------------------------

    def _llm_json_call(
        self,
        prompt: str,
        schema: Dict[str, Any],
        system_prompt: str = "",
    ) -> Dict[str, Any]:
        """Call the LLM and parse a JSON response."""
        if self.llm is None:
            logger.warning("No LLM available — returning stub response")
            return {k: "" if v == "string" else 0.0 for k, v in schema.items()}

        try:
            result = self.llm.generate_with_json_output(
                prompt=prompt,
                json_schema=schema,
                system_prompt=system_prompt,
            )
            # result can be (dict, prompt_tokens, completion_tokens) or just dict
            if isinstance(result, tuple):
                return result[0]
            return result
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            return {k: "" if v == "string" else 0.0 for k, v in schema.items()}

    # -----------------------------------------------------------------------
    # Artifact DAG helpers
    # -----------------------------------------------------------------------

    def _store_reasoning_artifact(
        self,
        data: Dict[str, Any],
        artifact_type_str: str = "analysis",
        tags: frozenset = frozenset(),
    ) -> Optional[str]:
        """Store a reasoning output as an artifact in the DAG."""
        try:
            create_artifact, ArtifactMetadata, ArtifactType = _get_artifact_helpers()
            art_type = ArtifactType(artifact_type_str)
            meta = ArtifactMetadata(
                artifact_type=art_type,
                skill_name="jnana-reasoning",
                tags=tags,
            )
            artifact = create_artifact(metadata=meta, data=data)
            self.artifact_store.put(artifact)
            return artifact.artifact_id
        except Exception as exc:
            logger.debug("Could not store reasoning artifact: %s", exc)
            return None

    # -----------------------------------------------------------------------
    # Sequence extraction — ported from BinderDesignSystem
    # -----------------------------------------------------------------------

    @staticmethod
    def _extract_sequence(text: str, seq_type: str = "target") -> str:
        """Extract a protein sequence from free text.

        Ported from BinderDesignSystem._extract_target_sequence() /
        _extract_binder_sequence().
        """
        label = seq_type.capitalize()
        # Pattern 1: "Target sequence: MKTAYIAK..."
        pattern1 = rf"[{label[0]}{label[0].lower()}]{label[1:]}\s+[Ss]equence:\s*([A-Z]{{20,}})"
        m = re.search(pattern1, text)
        if m:
            return m.group(1).strip()
        # Pattern 2: "target: MKTAYIAK..."
        pattern2 = rf"[{label[0]}{label[0].lower()}]{label[1:]}:\s*([A-Z]{{10,}})"
        m = re.search(pattern2, text)
        if m:
            return m.group(1).strip()
        # Pattern 3: Any long amino acid sequence (20+ standard residues)
        if seq_type == "target":
            pattern3 = r"\b([ACDEFGHIKLMNPQRSTVWY]{20,})\b"
            m = re.search(pattern3, text)
            if m:
                return m.group(1).strip()
        return ""

    # -----------------------------------------------------------------------
    # Academy integration
    # -----------------------------------------------------------------------

    def get_academy_agent(self) -> _JnanaReasoningAgent:
        """Return the Academy agent wrapper for async dispatch."""
        if self._academy_agent is None:
            self._academy_agent = _JnanaReasoningAgent(self)
        return self._academy_agent

    # -----------------------------------------------------------------------
    # MCP endpoint registrations
    # -----------------------------------------------------------------------

    def register_mcp_tools(self, server) -> None:
        """Register Jnana reasoning methods as MCP tools on *server*.

        Parameters
        ----------
        server : MCP server instance (e.g., from ``mcp.server.Server``)
        """
        bridge = self

        @server.tool("jnana.set_research_goal")
        def _set_goal(research_goal: str) -> dict:
            return bridge.set_research_goal(research_goal).to_dict()

        @server.tool("jnana.recommend_next_action")
        def _recommend(previous_run_type: str = "starting", previous_conclusion: str = "") -> dict:
            return bridge.recommend_next_action(previous_run_type, previous_conclusion).to_dict()

        @server.tool("jnana.bound_parameters")
        def _bound(skill_name: str, task_type: str) -> dict:
            return bridge.bound_parameters(skill_name, task_type).to_dict()

        @server.tool("jnana.evaluate_results")
        def _evaluate(artifact_ids: list) -> dict:
            return bridge.evaluate_results(artifact_ids).to_dict()

        @server.tool("jnana.check_convergence")
        def _convergence() -> dict:
            return {"converged": bridge.check_convergence()}

        logger.info("Registered 5 Jnana MCP tools")

    # -----------------------------------------------------------------------
    # Status / introspection
    # -----------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return current state for debugging / MCP status endpoint."""
        return {
            "research_goal": self.research_goal,
            "coscientist_active": self.coscientist is not None,
            "llm_provider": self._llm_provider,
            "hypothesis_count": len(self._hypotheses),
            "history_depth": {k: len(v) for k, v in self.history.items()},
            "converged": self.check_convergence(),
        }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Jnana Reasoning Bridge — Scientific intelligence layer (Layer 2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show status
  %(prog)s status

  # Set a research goal
  %(prog)s set-goal "Design a binder for SARS-CoV-2 spike protein RBD"

  # Get next action recommendation
  %(prog)s recommend --previous-run starting

  # Bound parameters for a skill
  %(prog)s bound-params --skill bindcraft --task-type computational_design

  # Evaluate artifacts
  %(prog)s evaluate --artifact-ids abc123 def456

  # Check convergence
  %(prog)s check-convergence
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status
    subparsers.add_parser("status", help="Show bridge status")

    # set-goal
    sp_goal = subparsers.add_parser("set-goal", help="Set research goal")
    sp_goal.add_argument("goal", help="Research goal text")

    # recommend
    sp_rec = subparsers.add_parser("recommend", help="Recommend next action (Tier 1)")
    sp_rec.add_argument("--previous-run", default="starting", help="Previous run type")
    sp_rec.add_argument("--conclusion", default="", help="Previous run conclusion")

    # bound-params
    sp_bp = subparsers.add_parser("bound-params", help="Bound parameters (Tier 2)")
    sp_bp.add_argument("--skill", required=True, help="Skill name")
    sp_bp.add_argument("--task-type", required=True, help="Task type")

    # evaluate
    sp_eval = subparsers.add_parser("evaluate", help="Evaluate artifacts")
    sp_eval.add_argument("--artifact-ids", nargs="+", required=True, help="Artifact IDs")

    # check-convergence
    subparsers.add_parser("check-convergence", help="Check if research goal is met")

    # Common options
    parser.add_argument("--store", default="artifact_store", help="Artifact store root directory")
    parser.add_argument("--provider", default="openai", help="LLM provider")
    parser.add_argument("--model", default=None, help="LLM model name")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if not args.command:
        parser.print_help()
        return

    bridge = JnanaReasoningBridge(
        artifact_store_root=args.store,
        llm_provider=args.provider,
        llm_model=args.model,
    )

    if args.command == "status":
        print(json.dumps(bridge.get_status(), indent=2))

    elif args.command == "set-goal":
        result = bridge.set_research_goal(args.goal)
        print(json.dumps(result.to_dict(), indent=2))

    elif args.command == "recommend":
        result = bridge.recommend_next_action(args.previous_run, args.conclusion)
        print(json.dumps(result.to_dict(), indent=2))

    elif args.command == "bound-params":
        result = bridge.bound_parameters(args.skill, args.task_type)
        print(json.dumps(result.to_dict(), indent=2))

    elif args.command == "evaluate":
        result = bridge.evaluate_results(args.artifact_ids)
        print(json.dumps(result.to_dict(), indent=2))

    elif args.command == "check-convergence":
        converged = bridge.check_convergence()
        print(json.dumps({"converged": converged}))


if __name__ == "__main__":
    main()
