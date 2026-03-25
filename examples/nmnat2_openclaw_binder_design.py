#!/usr/bin/env python3
"""NMNAT-2 Binder Design via OpenClaw HybridLoop Campaign.

Implements the NMNAT-2 case study (Section 4.2, PASC'26 paper) using the
4-layer architecture:

  Layer 1 — OpenClaw skill selection
  Layer 2 — Jnana scientific reasoning
  Layer 3 — Artifact DAG (shared state / provenance)
  Layer 4 — Academy distributed execution

The workflow has TWO distinct phases:

  Phase 1 — Interactome Exploration (interactive mode)
      HiPerRAG literature mining for NMNAT-2 interactome (18 members),
      structure prediction of NMNAT-2 with partners, MD simulation of
      interfaces, analysis to identify NMNAT-2:p53 as key therapeutic target.

  Phase 2 — Binder Design Campaign (tournament mode)
      BindCraft binder generation targeting NMNAT-2:p53 interface,
      MD assessment of binder stability, free energy ranking (MM-PBSA),
      tournament: promote winners, cull losers, iterate.

Usage::

    # Show help
    python examples/nmnat2_openclaw_binder_design.py --help

    # Dry run (mocks all external calls)
    python examples/nmnat2_openclaw_binder_design.py --dry-run

    # Full run (requires Jnana, Academy, HPC resources)
    python examples/nmnat2_openclaw_binder_design.py --config config/nmnat2_openclaw_config.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is on sys.path for skill imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from struct_bio_reasoner.workflows.hybrid_loop import (
    CampaignMemory,
    CampaignPhase,
    HybridLoop,
)

logger = logging.getLogger(__name__)

# ============================================================================
# Constants from PASC'26 paper Section 4.2
# ============================================================================

NMNAT2_UNIPROT = "Q9BZQ4"
NMNAT2_SEQUENCE = (
    "MTETTKTHVILLACGSFNPITKGHIQMFERARDYLHKTGRFIVIGGIVSPVHDSYGKQGLVSSRHRL"
    "IMCQLAVQNSDWIRVDPWECYQDTWQTTCSVLEHHRDLMKRVTGCILSNVNTPSMTPVIGQPQNET"
    "PQPIYQNSNVATKPTAAKILGKVGESLSRICCVRPPVERFTFVDENANLGTVMRYEEIELRILLLCGS"
    "DLLESFCIPGLWNEADMEVIVGDFGIVVVPRDAADTDRIMNHSSILRKYKNNIMVVKDDINHPMSVV"
    "SSTKSRLALQHGDGHVVDYLSQPVIDYILKSQLYINASG"
)
NMNAT2_IDR_REGION = (104, 192)

# Interface residues between NMNAT-2 and p53
NMNAT2_INTERFACE_RESIDUES = ["R81", "M106", "V109", "L153", "L156", "L160"]
P53_INTERFACE_RESIDUES = ["L194", "L264", "V272", "L289"]

# 18 interactome members explored via HiPerRAG
INTERACTOME_TARGETS = [
    {"name": "p53", "uniprot": "P04637", "relevance": "high"},
    {"name": "ALDH3B1", "uniprot": "P43353", "relevance": "medium"},
    {"name": "ICAM1", "uniprot": "P05362", "relevance": "medium"},
    {"name": "FBXO7", "uniprot": "Q9UJR5", "relevance": "low"},
    {"name": "MUM", "uniprot": "Q9ULX3", "relevance": "low"},
    {"name": "FBXO45", "uniprot": "Q8NCF5", "relevance": "low"},
    {"name": "BAG5", "uniprot": "Q9UL15", "relevance": "medium"},
    {"name": "LRIF1", "uniprot": "Q5T3J3", "relevance": "low"},
    {"name": "APP", "uniprot": "P05067", "relevance": "high"},
    {"name": "SURF1", "uniprot": "Q15526", "relevance": "low"},
    {"name": "HSPA8", "uniprot": "P11142", "relevance": "medium"},
    {"name": "RLIM", "uniprot": "Q9NVW2", "relevance": "low"},
    {"name": "PTBP3", "uniprot": "O95758", "relevance": "low"},
    {"name": "SKP1", "uniprot": "P63208", "relevance": "medium"},
    {"name": "SPRYD3", "uniprot": "Q9H4I3", "relevance": "low"},
    {"name": "HSP90", "uniprot": "P07900", "relevance": "medium"},
    {"name": "USP9X", "uniprot": "Q93008", "relevance": "medium"},
    {"name": "SIAH1", "uniprot": "Q8IUQ4", "relevance": "low"},
]

SCAFFOLDS = {
    "affibody": "VDNKFNKEQQNAFYEILHLPNLNEEQRNAFIQSLKDDPSQSANLLAEAKKLNDAQAPK",
    "affitin": "MGSWAEFKQRLAAIKTRLQALGGSEAELAAFEKEIAAFESELQAYKGKGNPEVEALRKEAAAIRDELQAYRHN",
    "nanobody": "QVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEWVSAISGSGGSTYYADSVKGRFTISRDNSKNTLYLQMNSLRAEDTAVYYCAA",
}

RESEARCH_GOAL = (
    "Design biologic binders for NMNAT-2 (Q9BZQ4) that disrupt the "
    "NMNAT-2:p53 interaction interface. The hydrophobic interface between p53 "
    "and the intrinsically disordered region (residues 104-192) of NMNAT-2 "
    "has been identified as a key therapeutic target via interactome probing. "
    "Target affinity < 10 nM, RMSD < 3 A in MD. Use affibody, affitin, and "
    "nanobody scaffolds."
)


# ============================================================================
# Dry-run mock infrastructure
# ============================================================================

_MOCK_STEP_COUNTER = 0


def _build_mock_reasoning_bridge():
    """Build a mock JnanaReasoningBridge for dry-run mode.

    Simulates the two-tier reasoning:
      Tier 1 — recommend_next_action() returns task type based on step sequence
      Tier 2 — bound_parameters() returns bounded config for the skill
    """
    from skills._shared.artifact import ArtifactMetadata, ArtifactType, create_artifact

    bridge = MagicMock()

    # Track call counts for sequenced recommendations
    _call_state = {"recommend_count": 0, "phase_goal": ""}

    def mock_set_research_goal(goal: str):
        _call_state["recommend_count"] = 0
        _call_state["phase_goal"] = goal
        plan = MagicMock()
        plan.to_dict.return_value = {
            "goal": goal,
            "plan_id": "mock-plan-001",
            "strategies": ["interactome_exploration", "binder_design_campaign"],
        }
        logger.info("  [Jnana] Research goal set: %s", goal[:80])
        return plan

    def mock_generate_hypotheses(count=1):
        logger.info("  [Jnana] Generated %d hypothesis(es)", count)

    def mock_recommend_next_action(previous_run_type="starting", previous_conclusion=""):
        count = _call_state["recommend_count"]
        _call_state["recommend_count"] += 1
        goal = _call_state["phase_goal"]

        # Determine task type from phase goal context
        if "Interactome" in goal or "Exploration" in goal or "exploration" in goal:
            sequence = ["rag", "structure_prediction", "molecular_dynamics", "analysis"]
        elif "Binder" in goal or "Design" in goal or "design" in goal:
            sequence = ["computational_design", "molecular_dynamics", "free_energy"]
        else:
            sequence = ["rag"]

        idx = min(count, len(sequence) - 1)
        task_type = sequence[idx]

        rec = MagicMock()
        rec.task_type = task_type
        rec.to_dict.return_value = {
            "task_type": task_type,
            "rationale": f"Step {count + 1}: {task_type} recommended for {goal[:60]}",
            "confidence": 0.85 + count * 0.02,
        }
        logger.info(
            "  [Jnana Tier-1] Recommend: %s (confidence=%.2f)",
            task_type, 0.85 + count * 0.02,
        )
        return rec

    def mock_bound_parameters(skill_name="", task_type=""):
        bounded = MagicMock()
        params = _get_mock_params(task_type, skill_name)
        bounded.parameters = params
        bounded.to_dict.return_value = {
            "parameters": params,
            "constraints": {"max_iterations": 10},
            "rationale": f"Bounded parameters for {task_type}",
        }
        logger.info("  [Jnana Tier-2] Bounded params for %s: %d keys", task_type, len(params))
        return bounded

    def mock_evaluate_results(artifact_ids):
        evaluation = MagicMock()
        global _MOCK_STEP_COUNTER
        _MOCK_STEP_COUNTER += 1
        scores = {
            "confidence": 0.75 + _MOCK_STEP_COUNTER * 0.03,
            "binding_score": 0.6 + _MOCK_STEP_COUNTER * 0.05,
            "stability": 0.7 + _MOCK_STEP_COUNTER * 0.02,
        }
        evaluation.to_dict.return_value = {
            "evaluation": f"Step {_MOCK_STEP_COUNTER}: Results meet criteria",
            "decision": "continue",
            "scores": scores,
            "artifact_ids_evaluated": artifact_ids,
        }
        logger.info(
            "  [Jnana] Evaluation: confidence=%.2f, binding=%.2f",
            scores["confidence"], scores["binding_score"],
        )
        return evaluation

    def mock_check_convergence():
        return False

    def mock_get_status():
        return {"mode": "dry-run", "hypotheses": 1}

    def mock_append_history(**kwargs):
        pass

    bridge.set_research_goal = mock_set_research_goal
    bridge._generate_hypotheses = mock_generate_hypotheses
    bridge.recommend_next_action = mock_recommend_next_action
    bridge.bound_parameters = mock_bound_parameters
    bridge.evaluate_results = mock_evaluate_results
    bridge.check_convergence = mock_check_convergence
    bridge.get_status = mock_get_status
    bridge._append_history = mock_append_history

    return bridge


def _get_mock_params(task_type: str, skill_name: str) -> Dict[str, Any]:
    """Return realistic mock parameters for each task type."""
    if task_type == "rag":
        return {
            "prompt": (
                "Identify all known interaction partners of NMNAT-2 (Q9BZQ4). "
                "Focus on cancer pathway interactions, particularly tumor suppressors. "
                "Report UniProt IDs, interaction types, and binding interfaces."
            ),
            "top_k": 20,
            "reranking": True,
        }
    elif task_type == "structure_prediction":
        return {
            "sequences": [
                [NMNAT2_SEQUENCE, "MEEPQSDPSVEPPLSQETFSDLWKLLPENNVLSPLPSQAMDDLMLSPDDIEQWFTEDPGPDEAPRMPEAAPPVAPAPAAPTPAAPAPAPSWPLSSSVPSQKTYPQGLNGTVNLPGRNSFEV"],
            ],
            "names": ["NMNAT2_p53_complex"],
            "fold_backend": "chai",
        }
    elif task_type == "molecular_dynamics":
        return {
            "simulation_paths": ["/mock/structures/nmnat2_p53_complex.pdb"],
            "root_output_path": "/mock/simulations/nmnat2",
            "steps": 500000,
            "temperature": 300,
        }
    elif task_type == "analysis":
        return {
            "data_type": "trajectory",
            "analysis_type": "interface_hotspot",
            "distance_cutoff": 4.5,
            "target_residues": NMNAT2_INTERFACE_RESIDUES,
        }
    elif task_type == "computational_design":
        return {
            "target_sequence": NMNAT2_SEQUENCE,
            "binder_sequence": SCAFFOLDS["affibody"],
            "hotspot_residues": NMNAT2_INTERFACE_RESIDUES,
            "num_rounds": 5,
            "scaffolds": list(SCAFFOLDS.keys()),
            "constraint": {"residues_bind": NMNAT2_INTERFACE_RESIDUES},
        }
    elif task_type == "free_energy":
        return {
            "simulation_paths": [
                "/mock/simulations/binder_affibody_01.pdb",
                "/mock/simulations/binder_affitin_01.pdb",
                "/mock/simulations/binder_nanobody_01.pdb",
            ],
            "method": "mm_pbsa",
            "num_frames": 100,
        }
    return {"task_type": task_type}


def _build_mock_academy_dispatch():
    """Build a mock AcademyDispatch for dry-run mode."""
    dispatch = AsyncMock()
    dispatch.start = AsyncMock()
    dispatch.stop = AsyncMock()
    dispatch.list_active_workers = MagicMock(return_value=[])

    _dispatch_count = {"n": 0}

    async def mock_dispatch(skill_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        _dispatch_count["n"] += 1
        n = _dispatch_count["n"]
        logger.info(
            "  [Academy] Dispatching skill=%s to worker (call #%d)", skill_name, n,
        )

        if skill_name == "rag":
            return {
                "status": "success",
                "interactome_members": [t["name"] for t in INTERACTOME_TARGETS],
                "total_found": len(INTERACTOME_TARGETS),
                "top_therapeutic_target": "p53",
                "interface_type": "hydrophobic",
                "evidence_papers": 47,
            }
        elif skill_name == "folding":
            return {
                "status": "success",
                "structures_predicted": 3,
                "best_plddt": 0.89,
                "complex": "NMNAT-2:p53",
                "pdb_path": "/mock/structures/nmnat2_p53_complex.pdb",
            }
        elif skill_name == "md":
            return {
                "status": "success",
                "rmsd_mean": 2.1,
                "rmsd_std": 0.4,
                "rmsf_interface": 1.2,
                "hbonds_mean": 8.3,
                "trajectory_path": f"/mock/trajectories/run_{n}.dcd",
                "stable_contacts": NMNAT2_INTERFACE_RESIDUES,
            }
        elif skill_name == "trajectory_analysis":
            return {
                "status": "success",
                "hotspot_residues": NMNAT2_INTERFACE_RESIDUES,
                "interface_area_A2": 1240.5,
                "hydrophobic_fraction": 0.72,
                "selected_target": "NMNAT-2:p53",
                "rationale": "Strongest hydrophobic interface with IDR involvement",
            }
        elif skill_name == "bindcraft":
            scaffold_names = list(SCAFFOLDS.keys())
            scaffold_idx = (n - 1) % len(scaffold_names)
            scaffold = scaffold_names[scaffold_idx]
            return {
                "status": "success",
                "scaffold_type": scaffold,
                "candidates_generated": 32400,
                "passing_qc": 28900,
                "top_binders": [
                    {
                        "sequence": SCAFFOLDS[scaffold][:40] + "MODIFIED",
                        "ipae": 0.12 + n * 0.01,
                        "plddt": 0.91 - n * 0.005,
                        "scaffold": scaffold,
                    }
                    for _ in range(5)
                ],
            }
        return {"status": "success", "skill": skill_name, "mock": True}

    dispatch.dispatch = mock_dispatch
    return dispatch


# ============================================================================
# Campaign setup
# ============================================================================

def build_campaign_phases() -> List[CampaignPhase]:
    """Build the two-phase campaign described in Section 4.2."""
    phase1 = CampaignPhase(
        name="interactome_exploration",
        goal=(
            "Identify NMNAT-2 interactome members via HiPerRAG literature mining, "
            "predict structures of NMNAT-2 with top partners, simulate interfaces "
            "via MD, and identify NMNAT-2:p53 as the key therapeutic target"
        ),
        step_sequence=["rag", "structure_prediction", "molecular_dynamics", "analysis"],
        max_iterations=10,
    )

    phase2 = CampaignPhase(
        name="binder_design_campaign",
        goal=(
            "Design binders targeting the NMNAT-2:p53 hydrophobic interface using "
            "BindCraft with affibody/affitin/nanobody scaffolds, assess stability "
            "via MD, rank by MM-PBSA free energy, tournament promote/cull/iterate"
        ),
        step_sequence=[
            "computational_design",
            "molecular_dynamics",
            "free_energy",
        ],
        max_iterations=15,
    )

    return [phase1, phase2]


def build_campaign_memory() -> CampaignMemory:
    """Pre-populate CampaignMemory with NMNAT-2 interactome context."""
    memory = CampaignMemory()

    # Long-term: known hotspot residues from literature
    for res in NMNAT2_INTERFACE_RESIDUES:
        memory.add_long_term("hotspots", {
            "residue": res,
            "protein": "NMNAT-2",
            "source": "PASC26_paper_section_4.2",
        })

    # Long-term: design constraints from paper
    memory.add_long_term("design_constraints", {
        "source": "paper",
        "constraint": "target_affinity_nM",
        "value": 10.0,
        "description": "Binding affinity < 10 nM",
    })
    memory.add_long_term("design_constraints", {
        "source": "paper",
        "constraint": "max_rmsd_A",
        "value": 3.0,
        "description": "Complex RMSD < 3 A in MD simulation",
    })
    memory.add_long_term("design_constraints", {
        "source": "paper",
        "constraint": "interface_type",
        "value": "hydrophobic",
        "description": "Target the hydrophobic NMNAT-2:p53 IDR interface",
    })

    # Long-term: interactome context
    for target in INTERACTOME_TARGETS:
        if target["relevance"] in ("high", "medium"):
            memory.add_long_term("experimental_data", {
                "interactome_member": target["name"],
                "uniprot": target["uniprot"],
                "therapeutic_relevance": target["relevance"],
            })

    return memory


def checkpoint_callback(
    top_hypotheses: List[Dict[str, Any]],
    evidence: List[Any],
    uncertainties: List[str],
) -> Optional[Dict[str, Any]]:
    """Human-in-the-loop checkpoint (logs only in dry-run)."""
    logger.info("=" * 60)
    logger.info("CHECKPOINT — Human review point")
    logger.info("  Top hypotheses: %d", len(top_hypotheses))
    logger.info("  Evidence items: %d", len(evidence))
    logger.info("  Uncertainties: %s", uncertainties)
    logger.info("=" * 60)
    # In a real run, this would pause for human input
    return None


# ============================================================================
# Main workflow
# ============================================================================

async def run_nmnat2_campaign(
    dry_run: bool = False,
    config_path: Optional[str] = None,
    artifact_root: str = "artifact_store/nmnat2_openclaw",
) -> Dict[str, Any]:
    """Execute the NMNAT-2 binder design campaign.

    Parameters
    ----------
    dry_run : bool
        If True, mock all external calls (Jnana, Academy, skills).
    config_path : str, optional
        Path to YAML config file. Defaults to config/nmnat2_openclaw_config.yaml.
    artifact_root : str
        Root directory for artifact storage.
    """
    logger.info("=" * 80)
    logger.info("NMNAT-2 OpenClaw Binder Design Campaign")
    logger.info("=" * 80)
    logger.info("Target: NMNAT-2 (%s) — %d residues", NMNAT2_UNIPROT, len(NMNAT2_SEQUENCE))
    logger.info("IDR region: residues %d-%d", *NMNAT2_IDR_REGION)
    logger.info("Interface residues: %s", ", ".join(NMNAT2_INTERFACE_RESIDUES))
    logger.info("Interactome targets: %d members", len(INTERACTOME_TARGETS))
    logger.info("Selected interface: NMNAT-2:p53 (hydrophobic)")
    logger.info("Scaffolds: %s", ", ".join(SCAFFOLDS.keys()))
    logger.info("Mode: %s", "DRY RUN" if dry_run else "LIVE")
    logger.info("=" * 80)

    # Load config if provided
    config = {}
    if config_path:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)
        logger.info("Loaded config from %s", config_path)

    # ----------------------------------------------------------------
    # Build HybridLoop
    # ----------------------------------------------------------------
    loop = HybridLoop(
        artifact_store_root=artifact_root,
        checkpoint_callback=checkpoint_callback,
        checkpoint_interval=3,
    )

    if dry_run:
        # Inject mocks for Jnana reasoning bridge and Academy dispatch
        logger.info("Injecting dry-run mocks for Jnana + Academy...")
        loop._reasoning_bridge = _build_mock_reasoning_bridge()
        loop._academy_dispatch = _build_mock_academy_dispatch()
        loop._started = True
    else:
        await loop.start()

    # ----------------------------------------------------------------
    # Build campaign phases and memory
    # ----------------------------------------------------------------
    phases = build_campaign_phases()
    memory = build_campaign_memory()

    logger.info("")
    logger.info("Campaign phases:")
    for i, phase in enumerate(phases, 1):
        logger.info(
            "  Phase %d: %s — %s", i, phase.name, phase.goal[:70],
        )
        logger.info("    Steps: %s", " -> ".join(phase.step_sequence))
    logger.info("")
    logger.info(
        "Pre-loaded memory: %d hotspots, %d constraints, %d experimental entries",
        len(memory.long_term["hotspots"]),
        len(memory.long_term["design_constraints"]),
        len(memory.long_term["experimental_data"]),
    )

    # ----------------------------------------------------------------
    # Run the campaign
    # ----------------------------------------------------------------
    logger.info("")
    logger.info("Starting campaign: %s", RESEARCH_GOAL[:80])
    logger.info("-" * 80)

    t0 = time.time()
    result = await loop.run_campaign(
        research_goal=RESEARCH_GOAL,
        phases=phases,
        memory=memory,
    )
    elapsed = time.time() - t0

    # ----------------------------------------------------------------
    # Report results
    # ----------------------------------------------------------------
    logger.info("")
    logger.info("=" * 80)
    logger.info("CAMPAIGN COMPLETE")
    logger.info("=" * 80)
    logger.info("Phases completed: %d / %d", result["phases_completed"], result["total_phases"])
    logger.info("Tournament rounds: %d", len(result["tournament_rounds"]))
    logger.info(
        "Cross-hypothesis patterns: %d",
        len(result.get("cross_hypothesis_patterns", [])),
    )
    logger.info("Elapsed: %.1f seconds", elapsed)
    logger.info("")

    # Phase-by-phase summary
    for pr in result.get("phase_results", []):
        logger.info("Phase: %s", pr["phase_name"])
        logger.info("  Goal: %s", pr["phase_goal"][:70])
        logger.info("  Iterations: %d", pr["iterations"])
        logger.info("  Converged: %s", pr["converged"])
        if pr.get("tournament"):
            t = pr["tournament"]
            logger.info(
                "  Tournament round %d: %d promoted, %d culled",
                t["round_number"], len(t["promoted"]), len(t["culled"]),
            )
        for step in pr.get("steps", []):
            logger.info(
                "    Step %d: %s (skill=%s, artifact=%s)",
                step["iteration"], step["task_type"],
                step["skill_name"], step.get("artifact_id", "N/A")[:12],
            )
        logger.info("")

    # Memory summary
    mem = result.get("memory", {})
    lt = mem.get("long_term", {})
    logger.info("Campaign memory:")
    logger.info("  Hotspots: %d", len(lt.get("hotspots", [])))
    logger.info("  Top binders: %d", len(lt.get("top_binders", [])))
    logger.info("  Design constraints: %d", len(lt.get("design_constraints", [])))
    logger.info("  Experimental data: %d", len(lt.get("experimental_data", [])))
    logger.info("  Short-term entries: %d", len(mem.get("short_term", [])))

    if not dry_run:
        await loop.stop()

    return result


# ============================================================================
# CLI
# ============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "NMNAT-2 Binder Design Campaign via OpenClaw HybridLoop.\n\n"
            "Implements the NMNAT-2 case study (Section 4.2, PASC'26 paper) "
            "using the 4-layer architecture with two campaign phases:\n"
            "  Phase 1: Interactome Exploration (RAG + folding + MD + analysis)\n"
            "  Phase 2: Binder Design Tournament (BindCraft + MD + free energy)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mock all external calls (Jnana, Academy, skills) to demonstrate the workflow",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to YAML config file (default: config/nmnat2_openclaw_config.yaml)",
    )
    parser.add_argument(
        "--artifact-root",
        type=str,
        default="artifact_store/nmnat2_openclaw",
        help="Root directory for artifact storage (default: artifact_store/nmnat2_openclaw)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy loggers
    logging.getLogger("parsl").setLevel(logging.WARNING)

    result = asyncio.run(
        run_nmnat2_campaign(
            dry_run=args.dry_run,
            config_path=args.config,
            artifact_root=args.artifact_root,
        )
    )

    if result:
        print(f"\nCampaign completed: {result['phases_completed']}/{result['total_phases']} phases")
        print(f"Tournament rounds: {len(result['tournament_rounds'])}")
    else:
        print("\nCampaign failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
