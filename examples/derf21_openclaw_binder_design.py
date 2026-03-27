#!/usr/bin/env python3
"""
Der f 21 Binder Design — OpenClaw HybridLoop Campaign

Implements the Der f 21 (house dust mite allergen) case study from
Section 4.1 of the PASC'26 paper using the 4-layer architecture:

  Layer 1 (OpenClaw) — skill selection via HybridLoop
  Layer 2 (Jnana)    — scientific reasoning / hypothesis management
  Layer 3 (Artifact DAG) — computational provenance
  Layer 4 (Academy)  — distributed execution

Campaign phases:
  1. Exploration: HiPerRAG literature mining → structure prediction → MD hotspot analysis
  2. Design: BindCraft binder tournament → MD validation → MM-PBSA free energy ranking

Usage:
  python examples/derf21_openclaw_binder_design.py --help
  python examples/derf21_openclaw_binder_design.py --dry-run
  python examples/derf21_openclaw_binder_design.py --config config/derf21_config.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# ---------------------------------------------------------------------------
# Resolve project root so imports work when run from the repo root
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from struct_bio_reasoner.workflows.hybrid_loop import (
    CampaignMemory,
    CampaignPhase,
    HybridLoop,
)

logger = logging.getLogger("derf21")

# ============================================================================
# Paper constants (Section 4.1)
# ============================================================================

DERF21_PDB = "4WKY"

# Der f 21 sequence from PDB 4WKY
DERF21_SEQUENCE = (
    "MKFFVFALILALMATQAIPEEVKKVEAEHGKLVPDDIPFNISTGKTLYYTISETKEALK"
    "KEYGATTDKQTFEINPEHIFLTQNSYTVKADIPEDNFKPETTKEYLKHTEGKSDPRDKY"
    "KEFIDEALKHSGFKY"
)

# Known epitopes from mutagenesis [45]
EPITOPE_RESIDUES = ["K10", "K26", "K42", "E43", "K46", "K48"]
KEY_RESIDUE = "E7"  # E7A mutation abrogates symptoms

# Reference baseline: BindCraft binder 10
REFERENCE_AFFINITY_NM = 793
REFERENCE_FREE_ENERGY = -135.00  # kcal/mol
REFERENCE_FREE_ENERGY_STD = 10.25

# Paper statistics
TOTAL_BINDERS_DESIGNED = 842
BINDERS_PASSED_QC = 787
QC_SUCCESS_RATE = 0.9347
FRACTION_OUTPERFORMING = 0.5098

# Default scaffolds
SCAFFOLDS = {
    "affibody": "VDNKFNKEQQNAFYEILHLPNLNEEQRNAFIQSLKDDPSQSANLLAEAKKLNDAQAPK",
    "affitin": "MGSWAEFKQRLAAIKTRLQALGGSEAELAAFEKEIAAFESELQAYKGKGNPEVEALRKEAAAIRDELQAYRHN",
    "nanobody": "QVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEWVSAISGSGGSTYYADSVKGRFTISRDNSKNTLYLQMNSLRAEDTAVYYCAA",
}

RESEARCH_GOAL = (
    f"Design biologic binders for Der f 21 allergen (PDB: {DERF21_PDB}) "
    f"that target IgE-binding epitopes. Prioritize the E7 salt-bridge "
    f"interface and known epitopes ({', '.join(EPITOPE_RESIDUES)}) identified "
    f"by mutagenesis. Aim to exceed the reference BindCraft binder 10 baseline "
    f"(free energy: {REFERENCE_FREE_ENERGY} +/- {REFERENCE_FREE_ENERGY_STD} "
    f"kcal/mol, affinity: {REFERENCE_AFFINITY_NM} nM)."
)

# ============================================================================
# Dry-run mocks — replaces Jnana reasoning bridge and Academy dispatch
# ============================================================================


class _MockRecommendation:
    """Mimics Recommendation dataclass from Jnana."""

    def __init__(self, task_type: str, rationale: str, confidence: float = 0.8):
        self.task_type = task_type
        self.rationale = rationale
        self.confidence = confidence
        self.priority = 1
        self.metadata: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_type": self.task_type,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "priority": self.priority,
            "metadata": self.metadata,
        }


class _MockBoundedConfig:
    """Mimics BoundedConfig dataclass from Jnana."""

    def __init__(self, parameters: Dict[str, Any], rationale: str = ""):
        self.parameters = parameters
        self.constraints: Dict[str, Any] = {}
        self.rationale = rationale

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameters": self.parameters,
            "constraints": self.constraints,
            "rationale": self.rationale,
        }


class _MockEvaluation:
    """Mimics Evaluation dataclass from Jnana."""

    def __init__(self, evaluation: str, scores: Dict[str, float]):
        self.evaluation = evaluation
        self.decision = "continue"
        self.updated_hypothesis = ""
        self.scores = scores
        self.artifact_ids_evaluated: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evaluation": self.evaluation,
            "decision": self.decision,
            "updated_hypothesis": self.updated_hypothesis,
            "scores": self.scores,
            "artifact_ids_evaluated": self.artifact_ids_evaluated,
        }


class _MockPlanConfig:
    """Mimics PlanConfig from Jnana."""

    def __init__(self, goal: str):
        self.goal = goal
        self.plan_id = "mock-plan-001"
        self.target_sequence = DERF21_SEQUENCE
        self.binder_sequence = SCAFFOLDS["affibody"]
        self.strategies = ["literature_exploration", "structure_prediction", "md_hotspot"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "plan_id": self.plan_id,
            "target_sequence": self.target_sequence,
            "binder_sequence": self.binder_sequence,
            "strategies": self.strategies,
        }


# Step-by-step mock data for each task type
_MOCK_DISPATCH_RESULTS: Dict[str, Dict[str, Any]] = {
    "rag": {
        "skill": "HiPerRAG",
        "papers_retrieved": 47,
        "key_findings": [
            "Der f 21 is a 14 kDa lipid-binding allergen from Dermatophagoides farinae",
            "E7 forms a salt bridge with IgE heavy chain residue D83 — critical for binding",
            "Epitope mapping via mutagenesis identified K10, K26, K42, E43, K46, K48",
            "Group 21 allergens share structural homology with ML-domain proteins",
        ],
        "recommended_hotspots": ["E7", "K10", "K26", "K42", "E43", "K46", "K48"],
    },
    "structure_prediction": {
        "skill": "Chai/Boltz folding",
        "method": "Chai-1",
        "target_pdb": DERF21_PDB,
        "predicted_complex": "Der_f_21_IgE_complex.pdb",
        "pLDDT": 0.87,
        "ipTM": 0.72,
        "interface_residues": [7, 10, 26, 42, 43, 46, 48],
        "contact_area_A2": 1247.3,
    },
    "molecular_dynamics": {
        "skill": "OpenMM MD",
        "engine": "OpenMM",
        "force_field": "AMBER19",
        "temperature_K": 310,
        "timestep_fs": 4,
        "hmr": True,
        "production_ns": 50,
        "rmsd_mean_A": 1.82,
        "rmsd_std_A": 0.34,
        "hotspot_residues": [7, 10, 26, 42, 43, 46, 48],
        "interface_contacts_mean": 34.5,
        "salt_bridge_E7_occupancy": 0.89,
    },
    "computational_design": {
        "skill": "BindCraft",
        "scaffold_type": "affibody",
        "binders_designed": 842,
        "binders_passed_qc": 787,
        "qc_success_rate": QC_SUCCESS_RATE,
        "top_binders": [
            {
                "name": "DerF21_binder_01",
                "sequence": "VDNKFNKEQQNAFYEILHLPNLNEEQRNAFIQSLKDDPSQSANLLAEAKKLNDAQAPK",
                "pae_interaction": 4.2,
                "plddt": 0.91,
                "i_pTM": 0.78,
            },
            {
                "name": "DerF21_binder_02",
                "sequence": "MGSWAEFKQRLAAIKTRLQALGGSEAELAAFEKEIAAFESELQAYKGKGNPEVEALRKE",
                "pae_interaction": 5.1,
                "plddt": 0.88,
                "i_pTM": 0.74,
            },
        ],
        "hotspot_coverage": 0.86,
    },
    "free_energy": {
        "skill": "MM-PBSA",
        "method": "MM-PBSA (3-trajectory)",
        "num_binders_evaluated": 50,
        "reference_energy_kcal_mol": REFERENCE_FREE_ENERGY,
        "best_binder_energy": -152.30,
        "best_binder_std": 8.75,
        "fraction_outperforming_reference": FRACTION_OUTPERFORMING,
        "top_5_energies": [-152.30, -148.67, -145.92, -142.11, -139.88],
    },
}

# Sequence of mock recommendations for each phase
_MOCK_RECOMMENDATIONS: Dict[str, List[Dict[str, Any]]] = {
    "exploration": [
        {
            "task_type": "rag",
            "rationale": (
                "Begin with HiPerRAG literature mining to gather known "
                "epitope data and structural information on Der f 21."
            ),
            "confidence": 0.95,
        },
        {
            "task_type": "structure_prediction",
            "rationale": (
                "Predict Der f 21:IgE complex structure using Chai-1 to "
                "identify interface residues for hotspot analysis."
            ),
            "confidence": 0.90,
        },
        {
            "task_type": "molecular_dynamics",
            "rationale": (
                "Run 50 ns MD simulation to assess interface stability "
                "and confirm E7 salt-bridge occupancy."
            ),
            "confidence": 0.88,
        },
    ],
    "design": [
        {
            "task_type": "computational_design",
            "rationale": (
                "Launch BindCraft binder design campaign targeting "
                "confirmed hotspot residues from MD analysis."
            ),
            "confidence": 0.92,
        },
        {
            "task_type": "molecular_dynamics",
            "rationale": (
                "Validate top binder candidates with MD simulation to "
                "assess complex stability and RMSD."
            ),
            "confidence": 0.85,
        },
        {
            "task_type": "free_energy",
            "rationale": (
                "Rank surviving binders by MM-PBSA free energy. "
                "Compare against reference baseline (-135.00 kcal/mol)."
            ),
            "confidence": 0.90,
        },
    ],
}

_MOCK_EVALUATIONS: Dict[str, Dict[str, Any]] = {
    "rag": {
        "evaluation": (
            "Literature mining identified 7 key epitope residues and "
            "confirmed E7 as critical for IgE binding. Proceed to "
            "structure prediction."
        ),
        "scores": {"coverage": 0.95, "confidence": 0.90, "novelty": 0.75},
    },
    "structure_prediction": {
        "evaluation": (
            "Complex prediction achieved pLDDT=0.87 and ipTM=0.72. "
            "Interface residues match known epitopes. Ready for MD."
        ),
        "scores": {"pLDDT": 0.87, "ipTM": 0.72, "interface_quality": 0.82},
    },
    "molecular_dynamics": {
        "evaluation": (
            "50 ns MD shows stable complex (RMSD 1.82 +/- 0.34 A). "
            "E7 salt bridge occupancy 89%. Hotspots confirmed."
        ),
        "scores": {"stability": 0.88, "salt_bridge": 0.89, "contact_quality": 0.85},
    },
    "computational_design": {
        "evaluation": (
            f"BindCraft produced {BINDERS_PASSED_QC}/{TOTAL_BINDERS_DESIGNED} "
            f"passing binders ({QC_SUCCESS_RATE:.1%} QC rate). "
            f"Top binder pLDDT=0.91, iPTM=0.78."
        ),
        "scores": {"qc_rate": QC_SUCCESS_RATE, "top_plddt": 0.91, "top_iptm": 0.78},
    },
    "free_energy": {
        "evaluation": (
            f"MM-PBSA ranking complete. Best binder: -152.30 kcal/mol "
            f"(vs reference {REFERENCE_FREE_ENERGY}). "
            f"{FRACTION_OUTPERFORMING:.1%} outperform reference."
        ),
        "scores": {
            "best_energy": -152.30,
            "fraction_better": FRACTION_OUTPERFORMING,
            "mean_top5": -145.78,
        },
    },
}


class MockReasoningBridge:
    """Drop-in replacement for JnanaReasoningBridge in dry-run mode.

    Replays pre-canned recommendations and evaluations that mirror
    the paper's Der f 21 workflow.
    """

    def __init__(self, artifact_store_root: str = "artifact_store"):
        self._goal: str = ""
        self._history: Dict[str, List] = {
            "decisions": [],
            "results": [],
            "configurations": [],
            "key_items": [],
        }
        self._phase_name: str = ""
        self._step_idx: int = 0
        self._converge_after: int = 0

    def set_research_goal(self, goal: str) -> _MockPlanConfig:
        self._goal = goal
        self._step_idx = 0
        # Detect phase from goal string
        if "exploration" in goal.lower() or "Phase: exploration" in goal:
            self._phase_name = "exploration"
        elif "design" in goal.lower() or "Phase: design" in goal:
            self._phase_name = "design"
        else:
            self._phase_name = "exploration"
        self._converge_after = len(
            _MOCK_RECOMMENDATIONS.get(self._phase_name, [])
        )
        logger.info(
            "  [Jnana] Research goal set: %s (phase=%s, steps=%d)",
            goal[:80], self._phase_name, self._converge_after,
        )
        return _MockPlanConfig(goal)

    def _generate_hypotheses(self, count: int = 1) -> None:
        logger.info("  [Jnana] Generated %d hypothesis(es) for %s", count, self._phase_name)

    def recommend_next_action(
        self,
        previous_run_type: str = "starting",
        previous_conclusion: str = "",
    ) -> _MockRecommendation:
        recs = _MOCK_RECOMMENDATIONS.get(self._phase_name, [])
        if self._step_idx < len(recs):
            rec_data = recs[self._step_idx]
        else:
            return _MockRecommendation("stop", "All phase steps complete", 1.0)

        rec = _MockRecommendation(
            task_type=rec_data["task_type"],
            rationale=rec_data["rationale"],
            confidence=rec_data["confidence"],
        )
        logger.info(
            "  [Jnana] Tier-1 recommend: %s (confidence=%.2f)",
            rec.task_type, rec.confidence,
        )
        return rec

    def bound_parameters(
        self, skill_name: str, task_type: str
    ) -> _MockBoundedConfig:
        params: Dict[str, Any] = {
            "target_pdb": DERF21_PDB,
            "target_sequence": DERF21_SEQUENCE,
            "epitope_residues": EPITOPE_RESIDUES,
            "key_residue": KEY_RESIDUE,
            "task_type": task_type,
        }
        if task_type == "computational_design":
            params["scaffold_sequences"] = SCAFFOLDS
            params["hotspot_residues"] = EPITOPE_RESIDUES
            params["num_designs"] = TOTAL_BINDERS_DESIGNED
        elif task_type == "molecular_dynamics":
            params["engine"] = "OpenMM"
            params["force_field"] = "AMBER19"
            params["temperature_K"] = 310
            params["timestep_fs"] = 4
            params["production_ns"] = 50
        elif task_type == "free_energy":
            params["method"] = "MM-PBSA"
            params["reference_energy"] = REFERENCE_FREE_ENERGY
        logger.info("  [Jnana] Tier-2 bounded params for %s (%s)", skill_name, task_type)
        return _MockBoundedConfig(params, f"Bounded config for {task_type}")

    def evaluate_results(self, artifact_ids: List[str]) -> _MockEvaluation:
        recs = _MOCK_RECOMMENDATIONS.get(self._phase_name, [])
        if self._step_idx < len(recs):
            task_type = recs[self._step_idx]["task_type"]
        else:
            task_type = "free_energy"
        eval_data = _MOCK_EVALUATIONS.get(task_type, {})
        ev = _MockEvaluation(
            evaluation=eval_data.get("evaluation", "Evaluation complete"),
            scores=eval_data.get("scores", {}),
        )
        ev.artifact_ids_evaluated = list(artifact_ids)
        self._step_idx += 1
        logger.info(
            "  [Jnana] Evaluated %d artifact(s): %s",
            len(artifact_ids), ev.evaluation[:80],
        )
        return ev

    def check_convergence(self) -> bool:
        converged = self._step_idx >= self._converge_after
        if converged:
            logger.info("  [Jnana] Phase '%s' converged after %d steps", self._phase_name, self._step_idx)
        return converged

    def _append_history(self, **kwargs) -> None:
        pass

    def get_status(self) -> Dict[str, Any]:
        return {
            "goal": self._goal,
            "phase": self._phase_name,
            "step_idx": self._step_idx,
        }


class MockAcademyDispatch:
    """Drop-in replacement for AcademyDispatch in dry-run mode.

    Returns pre-canned results that mirror the paper's experimental outcomes.
    """

    def __init__(self, config: Any = None):
        self._started = False
        self._call_count = 0

    async def start(self) -> None:
        self._started = True
        logger.info("  [Academy] Dispatch started (dry-run mode)")

    async def stop(self) -> None:
        self._started = False
        logger.info("  [Academy] Dispatch stopped")

    async def dispatch(
        self, skill_name: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        self._call_count += 1
        task_type = params.get("task_type", skill_name)

        # Map skill names to task type keys
        skill_to_task = {
            "rag": "rag",
            "folding": "structure_prediction",
            "md": "molecular_dynamics",
            "bindcraft": "computational_design",
        }
        mock_key = skill_to_task.get(skill_name, task_type)
        result = _MOCK_DISPATCH_RESULTS.get(mock_key, {"status": "completed"})
        logger.info(
            "  [Academy] Dispatched skill=%s (call #%d) -> %d result keys",
            skill_name, self._call_count, len(result),
        )
        return result

    def list_active_workers(self) -> List[str]:
        return []


# ============================================================================
# Configuration loader
# ============================================================================


def load_config(config_path: Optional[str]) -> Dict[str, Any]:
    """Load campaign configuration from YAML, with sensible defaults."""
    defaults = {
        "target": {
            "name": "Der f 21",
            "pdb_id": DERF21_PDB,
            "sequence": DERF21_SEQUENCE,
        },
        "epitopes": {
            "known_residues": EPITOPE_RESIDUES,
            "key_residue": KEY_RESIDUE,
        },
        "reference": {
            "free_energy_kcal_mol": REFERENCE_FREE_ENERGY,
            "free_energy_std": REFERENCE_FREE_ENERGY_STD,
            "binding_affinity_nM": REFERENCE_AFFINITY_NM,
        },
        "campaign": {
            "research_goal": RESEARCH_GOAL,
            "phases": {
                "exploration": {
                    "name": "exploration",
                    "goal": "Literature mining, structure prediction, and MD hotspot analysis",
                    "step_sequence": ["rag", "structure_prediction", "molecular_dynamics"],
                    "max_iterations": 10,
                },
                "design": {
                    "name": "design",
                    "goal": "Binder design tournament with iterative optimization",
                    "step_sequence": [
                        "computational_design",
                        "molecular_dynamics",
                        "free_energy",
                    ],
                    "max_iterations": 10,
                },
            },
        },
        "artifact_store": {"root": "artifact_store/derf21"},
    }
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            user_cfg = yaml.safe_load(f) or {}
        # Shallow merge — user overrides per top-level key
        for key, val in user_cfg.items():
            if key in defaults and isinstance(defaults[key], dict) and isinstance(val, dict):
                defaults[key].update(val)
            else:
                defaults[key] = val
    return defaults


# ============================================================================
# Campaign builder
# ============================================================================


def build_campaign_phases(cfg: Dict[str, Any]) -> List[CampaignPhase]:
    """Build CampaignPhase objects from configuration."""
    phase_cfgs = cfg.get("campaign", {}).get("phases", {})
    phases = []
    for phase_key in ["exploration", "design"]:
        pc = phase_cfgs.get(phase_key, {})
        phases.append(
            CampaignPhase(
                name=pc.get("name", phase_key),
                goal=pc.get("goal", f"Phase: {phase_key}"),
                step_sequence=pc.get("step_sequence", []),
                max_iterations=pc.get("max_iterations", 10),
            )
        )
    return phases


def build_initial_memory(cfg: Dict[str, Any]) -> CampaignMemory:
    """Seed long-term memory with known paper data."""
    memory = CampaignMemory()
    # Seed epitope hotspots
    epitopes = cfg.get("epitopes", {})
    for res in epitopes.get("known_residues", EPITOPE_RESIDUES):
        memory.add_long_term("hotspots", {"residue": res, "source": "mutagenesis [45]"})
    memory.add_long_term(
        "hotspots",
        {"residue": epitopes.get("key_residue", KEY_RESIDUE), "source": "E7A abrogation study"},
    )
    # Seed reference baseline
    ref = cfg.get("reference", {})
    memory.add_long_term(
        "experimental_data",
        {
            "type": "reference_baseline",
            "binder": "BindCraft binder 10",
            "free_energy": ref.get("free_energy_kcal_mol", REFERENCE_FREE_ENERGY),
            "std": ref.get("free_energy_std", REFERENCE_FREE_ENERGY_STD),
            "affinity_nM": ref.get("binding_affinity_nM", REFERENCE_AFFINITY_NM),
        },
    )
    # Seed design constraints
    memory.add_long_term(
        "design_constraints",
        {"constraint": "target_epitope_residues", "residues": EPITOPE_RESIDUES},
    )
    memory.add_long_term(
        "design_constraints",
        {"constraint": "E7_salt_bridge", "importance": "critical"},
    )
    return memory


# ============================================================================
# Main entry point
# ============================================================================


async def run_derf21_campaign(
    config_path: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Run the Der f 21 binder design campaign.

    Parameters
    ----------
    config_path : str, optional
        Path to YAML configuration file.
    dry_run : bool
        If True, mock all external calls (Jnana, Academy) and simulate
        the full workflow end-to-end.
    """
    cfg = load_config(config_path)
    research_goal = cfg.get("campaign", {}).get("research_goal", RESEARCH_GOAL)
    store_root = cfg.get("artifact_store", {}).get("root", "artifact_store/derf21")

    if dry_run:
        store_root = tempfile.mkdtemp(prefix="derf21_dryrun_")

    logger.info("=" * 72)
    logger.info("DER F 21 BINDER DESIGN CAMPAIGN (OpenClaw HybridLoop)")
    logger.info("=" * 72)
    logger.info("PDB: %s | Sequence length: %d", DERF21_PDB, len(DERF21_SEQUENCE))
    logger.info(
        "Epitopes: %s | Key residue: %s",
        ", ".join(EPITOPE_RESIDUES), KEY_RESIDUE,
    )
    logger.info(
        "Reference baseline: %.2f +/- %.2f kcal/mol (%d nM)",
        REFERENCE_FREE_ENERGY, REFERENCE_FREE_ENERGY_STD, REFERENCE_AFFINITY_NM,
    )
    logger.info("Artifact store: %s", store_root)
    logger.info("Dry-run: %s", dry_run)
    logger.info("-" * 72)

    # Build campaign components
    phases = build_campaign_phases(cfg)
    memory = build_initial_memory(cfg)

    logger.info(
        "Campaign: %d phases — %s",
        len(phases), " -> ".join(p.name for p in phases),
    )
    for i, phase in enumerate(phases):
        logger.info(
            "  Phase %d: %s — %s (steps: %s)",
            i + 1, phase.name, phase.goal, " -> ".join(phase.step_sequence),
        )
    logger.info(
        "Initial memory: %d hotspots, %d experimental data, %d constraints",
        len(memory.long_term["hotspots"]),
        len(memory.long_term["experimental_data"]),
        len(memory.long_term["design_constraints"]),
    )
    logger.info("-" * 72)

    # Build worker_configs from YAML so Academy workers get the right paths/device
    bindcraft_cfg = cfg.get("bindcraft", {})
    # Fall back to target sequence constant if not in YAML
    if "target_sequence" not in bindcraft_cfg:
        bindcraft_cfg["target_sequence"] = DERF21_SEQUENCE
    worker_configs = {"bindcraft": bindcraft_cfg} if bindcraft_cfg else {}

    # Create HybridLoop
    loop = HybridLoop(artifact_store_root=store_root, worker_configs=worker_configs)

    if dry_run:
        # Inject mocks for Jnana reasoning bridge and Academy dispatch
        loop._reasoning_bridge = MockReasoningBridge(store_root)
        loop._academy_dispatch = MockAcademyDispatch()
        loop._started = True
        logger.info("[DRY-RUN] Injected MockReasoningBridge and MockAcademyDispatch")
    else:
        await loop.start()

    # Run campaign
    logger.info("")
    logger.info("Starting campaign: %s", research_goal[:80])
    logger.info("=" * 72)

    result = await loop.run_campaign(
        research_goal=research_goal,
        phases=phases,
        memory=memory,
    )

    if not dry_run:
        await loop.stop()

    # Print summary
    _print_summary(result)

    return result


def _print_summary(result: Dict[str, Any]) -> None:
    """Print a human-readable campaign summary."""
    logger.info("")
    logger.info("=" * 72)
    logger.info("CAMPAIGN SUMMARY")
    logger.info("=" * 72)
    logger.info(
        "Phases completed: %d/%d",
        result["phases_completed"], result["total_phases"],
    )
    logger.info(
        "Tournament rounds: %d", len(result.get("tournament_rounds", [])),
    )
    logger.info(
        "Cross-hypothesis patterns: %d",
        len(result.get("cross_hypothesis_patterns", [])),
    )

    for pr in result.get("phase_results", []):
        logger.info("-" * 72)
        logger.info(
            "Phase: %s | Goal: %s | Iterations: %d | Converged: %s",
            pr["phase_name"], pr["phase_goal"], pr["iterations"], pr["converged"],
        )
        for step in pr.get("steps", []):
            logger.info(
                "  Step %d: %s (%s) -> artifact %s",
                step["iteration"],
                step["task_type"],
                step["skill_name"],
                step.get("artifact_id", "N/A")[:12],
            )
        if pr.get("tournament"):
            t = pr["tournament"]
            logger.info(
                "  Tournament round %d: %d promoted, %d culled",
                t["round_number"], len(t["promoted"]), len(t["culled"]),
            )

    # Memory summary
    mem = result.get("memory", {})
    lt = mem.get("long_term", {})
    logger.info("-" * 72)
    logger.info(
        "Memory: %d hotspots, %d experimental data, %d constraints, %d top binders",
        len(lt.get("hotspots", [])),
        len(lt.get("experimental_data", [])),
        len(lt.get("design_constraints", [])),
        len(lt.get("top_binders", [])),
    )
    logger.info("=" * 72)
    logger.info("Campaign complete.")


# ============================================================================
# CLI
# ============================================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Der f 21 Binder Design — OpenClaw HybridLoop Campaign\n\n"
            "Implements the Der f 21 (house dust mite allergen) case study from\n"
            "Section 4.1 of the PASC'26 paper using the 4-layer architecture."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --dry-run              # Mock run — no external calls\n"
            "  %(prog)s --config config/derf21_config.yaml\n"
            "  %(prog)s --config config/derf21_config.yaml --dry-run\n"
        ),
    )
    parser.add_argument(
        "--config",
        default="config/derf21_config.yaml",
        help="Path to YAML configuration file (default: config/derf21_config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Mock all external calls and simulate the full workflow",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    result = asyncio.run(
        run_derf21_campaign(
            config_path=args.config,
            dry_run=args.dry_run,
        )
    )

    if result.get("phases_completed", 0) == result.get("total_phases", 0):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
