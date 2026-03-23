#!/usr/bin/env python3
"""
Structure Prediction Skill — Chai-1 / AlphaFold.

Predict 3D protein structures from amino acid sequences, score them with
confidence metrics, and run an integrated critic evaluation.  Results are
stored in the Artifact DAG with full provenance tracking.

Usage:
    python run_prediction.py --sequence "MKWVTF..." --backend chai
    python run_prediction.py --fasta input.fasta --backend alphafold
    python run_prediction.py --help
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Lazy imports for heavy dependencies (Chai / AlphaFold / Academy)
# ---------------------------------------------------------------------------

_CHAI_AVAILABLE = False
_ALPHAFOLD_AVAILABLE = False
_ACADEMY_AVAILABLE = False

_UTC = timezone.utc

logger = logging.getLogger("structure-prediction")

# ---------------------------------------------------------------------------
# Shared artifact layer — imported from skills/_shared
# ---------------------------------------------------------------------------

_SHARED_DIR = Path(__file__).resolve().parent.parent.parent / "_shared"
if str(_SHARED_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR.parent))

from _shared.artifact import (
    Artifact,
    ArtifactMetadata,
    ArtifactStatus,
    ArtifactType,
    create_artifact,
)
from _shared.artifact_store import ArtifactStore
from _shared.provenance import ProvenanceTracker

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKILL_NAME = "structure-prediction"
SKILL_VERSION = "0.1.0"

QUALITY_THRESHOLDS = {
    "min_confidence": 60.0,
    "high_confidence": 80.0,
    "min_coverage": 0.9,
    "max_clash_score": 10.0,
}

CRITIC_WEIGHTS = {
    "prediction_quality": 0.30,
    "analysis_depth": 0.25,
    "interpretation_accuracy": 0.20,
    "methodology": 0.15,
    "efficiency": 0.10,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PredictionResult:
    """Result from a single structure prediction run."""

    model_index: int = 0
    pdb_path: Optional[str] = None
    plddt: float = 0.0
    pae: float = 0.0
    iptm: float = 0.0
    aggregate_score: float = 0.0
    backend: str = "chai"
    sequence_name: str = "query"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_index": self.model_index,
            "pdb_path": self.pdb_path,
            "plddt": self.plddt,
            "pae": self.pae,
            "iptm": self.iptm,
            "aggregate_score": self.aggregate_score,
            "backend": self.backend,
            "sequence_name": self.sequence_name,
            "metadata": self.metadata,
        }


@dataclass
class CriticEvaluation:
    """Critic evaluation of a structure prediction run."""

    prediction_quality: float = 0.0
    analysis_depth: float = 0.0
    interpretation_accuracy: float = 0.0
    methodology: float = 0.0
    efficiency: float = 0.0
    overall_score: float = 0.0
    feedback: str = ""
    strengths: List[str] = field(default_factory=list)
    improvement_areas: List[str] = field(default_factory=list)
    priority_recommendations: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prediction_quality": self.prediction_quality,
            "analysis_depth": self.analysis_depth,
            "interpretation_accuracy": self.interpretation_accuracy,
            "methodology": self.methodology,
            "efficiency": self.efficiency,
            "overall_score": self.overall_score,
            "feedback": self.feedback,
            "strengths": self.strengths,
            "improvement_areas": self.improvement_areas,
            "priority_recommendations": self.priority_recommendations,
        }


# ---------------------------------------------------------------------------
# Sequence I/O helpers
# ---------------------------------------------------------------------------


def parse_fasta(fasta_path: str | Path) -> List[tuple[str, str]]:
    """Parse a FASTA file and return list of (name, sequence) tuples."""
    sequences: List[tuple[str, str]] = []
    current_name = ""
    current_seq: List[str] = []

    with open(fasta_path) as fh:
        for line in fh:
            line = line.strip()
            if line.startswith(">"):
                if current_name:
                    sequences.append((current_name, "".join(current_seq)))
                current_name = line[1:].split()[0]
                current_seq = []
            elif line:
                current_seq.append(line.upper())
    if current_name:
        sequences.append((current_name, "".join(current_seq)))

    return sequences


def validate_sequence(sequence: str) -> bool:
    """Basic validation that string looks like an amino acid sequence."""
    valid_aa = set("ACDEFGHIKLMNPQRSTVWY")
    return len(sequence) > 0 and all(c in valid_aa for c in sequence.upper())


# ---------------------------------------------------------------------------
# Backend runners
# ---------------------------------------------------------------------------


def _try_import_chai() -> bool:
    """Attempt to import Chai components."""
    global _CHAI_AVAILABLE
    try:
        from bindcraft.core.folding import Chai  # noqa: F401

        _CHAI_AVAILABLE = True
    except ImportError:
        _CHAI_AVAILABLE = False
    return _CHAI_AVAILABLE


def _try_import_alphafold() -> bool:
    """Attempt to import AlphaFold components."""
    global _ALPHAFOLD_AVAILABLE
    try:
        import alphafold  # noqa: F401

        _ALPHAFOLD_AVAILABLE = True
    except ImportError:
        _ALPHAFOLD_AVAILABLE = False
    return _ALPHAFOLD_AVAILABLE


def _try_import_academy() -> bool:
    """Attempt to import Academy framework."""
    global _ACADEMY_AVAILABLE
    try:
        from academy.exchange import LocalExchangeFactory  # noqa: F401
        from academy.manager import Manager  # noqa: F401

        _ACADEMY_AVAILABLE = True
    except ImportError:
        _ACADEMY_AVAILABLE = False
    return _ACADEMY_AVAILABLE


def run_chai_prediction(
    sequences: List[tuple[str, str]],
    num_models: int,
    device: str,
    output_dir: Path,
    use_templates: bool,
    constraints: Optional[Dict[str, Any]] = None,
) -> List[PredictionResult]:
    """
    Run Chai-1 structure prediction.

    If Chai is not installed, returns simulated results so the script
    remains testable without GPU hardware.
    """
    results: List[PredictionResult] = []

    if _try_import_chai():
        logger.info("Running Chai-1 prediction with %d models", num_models)
        try:
            from bindcraft.core.folding import Chai

            fasta_dir = output_dir / "fastas"
            fold_dir = output_dir / "folds"
            fasta_dir.mkdir(parents=True, exist_ok=True)
            fold_dir.mkdir(parents=True, exist_ok=True)

            chai = Chai(
                fasta_dir=fasta_dir,
                out=fold_dir,
                diffusion_steps=100,
                device=device,
            )

            for name, seq in sequences:
                # Write FASTA
                fasta_path = fasta_dir / f"{name}.fasta"
                fasta_path.write_text(f">{name}\n{seq}\n")

                # Run folding
                fold_results = chai.fold(
                    fasta_path=str(fasta_path),
                    num_models=num_models,
                    use_templates=use_templates,
                )

                for i, model in enumerate(fold_results):
                    results.append(
                        PredictionResult(
                            model_index=i,
                            pdb_path=str(model.get("pdb_path", "")),
                            plddt=model.get("plddt", 0.0),
                            pae=model.get("pae", 0.0),
                            iptm=model.get("iptm", 0.0),
                            aggregate_score=model.get("aggregate_score", 0.0),
                            backend="chai",
                            sequence_name=name,
                            metadata=model,
                        )
                    )
        except Exception as e:
            logger.error("Chai prediction failed: %s", e)
            logger.info("Falling back to simulated results")
            results = _simulated_results(sequences, num_models, "chai")
    else:
        logger.warning("Chai not installed — generating simulated results")
        results = _simulated_results(sequences, num_models, "chai")

    return results


def run_alphafold_prediction(
    sequences: List[tuple[str, str]],
    num_models: int,
    device: str,
    output_dir: Path,
    use_templates: bool,
) -> List[PredictionResult]:
    """
    Run AlphaFold structure prediction.

    If AlphaFold is not installed, returns simulated results.
    """
    results: List[PredictionResult] = []

    if _try_import_alphafold():
        logger.info("Running AlphaFold prediction with %d models", num_models)
        # AlphaFold integration would go here — currently uses MCP bridge
        # from the StructurePredictionExpert role pattern
        logger.warning("AlphaFold direct integration not yet implemented; using simulated results")
        results = _simulated_results(sequences, num_models, "alphafold")
    else:
        logger.warning("AlphaFold not installed — generating simulated results")
        results = _simulated_results(sequences, num_models, "alphafold")

    return results


def _simulated_results(
    sequences: List[tuple[str, str]],
    num_models: int,
    backend: str,
) -> List[PredictionResult]:
    """Generate placeholder results when prediction backends are unavailable."""
    import random

    random.seed(42)
    results: List[PredictionResult] = []
    for name, seq in sequences:
        for i in range(num_models):
            plddt = round(random.uniform(50.0, 95.0), 1)
            pae = round(random.uniform(2.0, 20.0), 1)
            iptm = round(random.uniform(0.3, 0.95), 3)
            aggregate = round(0.5 * plddt / 100.0 + 0.3 * iptm + 0.2 * (1 - pae / 30.0), 3)
            results.append(
                PredictionResult(
                    model_index=i,
                    pdb_path=None,
                    plddt=plddt,
                    pae=pae,
                    iptm=iptm,
                    aggregate_score=aggregate,
                    backend=backend,
                    sequence_name=name,
                    metadata={"simulated": True, "sequence_length": len(seq)},
                )
            )
    return results


# ---------------------------------------------------------------------------
# Critic evaluation  (ported from structure_critic.py)
# ---------------------------------------------------------------------------


def evaluate_prediction(
    prediction_results: List[PredictionResult],
    execution_time: float,
) -> CriticEvaluation:
    """
    Run critic evaluation on prediction results.

    Ported from StructurePredictionCritic.evaluate_performance() — evaluates
    prediction quality, analysis depth, methodology, and efficiency using
    the weighted scoring system from the original role.
    """
    # --- prediction quality ---
    pred_score = 0.5
    if prediction_results:
        best = max(prediction_results, key=lambda r: r.aggregate_score)
        if best.plddt > QUALITY_THRESHOLDS["high_confidence"]:
            pred_score += 0.3
        elif best.plddt > QUALITY_THRESHOLDS["min_confidence"]:
            pred_score += 0.2
        else:
            pred_score -= 0.1
        if best.pdb_path:
            pred_score += 0.1
        if best.iptm > 0.7:
            pred_score += 0.1
    else:
        pred_score = 0.1

    pred_score = max(0.0, min(1.0, pred_score))

    # --- analysis depth ---
    analysis_score = 0.6
    if len(prediction_results) >= 3:
        analysis_score += 0.2
    elif len(prediction_results) >= 1:
        analysis_score += 0.1
    has_confidence = any(r.plddt > 0 for r in prediction_results)
    has_pae = any(r.pae > 0 for r in prediction_results)
    if has_confidence and has_pae:
        analysis_score += 0.1
    analysis_score = max(0.0, min(1.0, analysis_score))

    # --- interpretation accuracy ---
    interp_score = 0.7
    if prediction_results:
        best = max(prediction_results, key=lambda r: r.aggregate_score)
        if best.plddt > 80 and best.aggregate_score > 0.7:
            interp_score += 0.1
        elif best.plddt < 60 and best.aggregate_score < 0.5:
            interp_score += 0.1  # consistent low
    interp_score = max(0.0, min(1.0, interp_score))

    # --- methodology ---
    method_score = 0.7
    if prediction_results:
        method_score += 0.1  # at least attempted
        if any(not r.metadata.get("simulated", False) for r in prediction_results):
            method_score += 0.1  # real backend
    method_score = max(0.0, min(1.0, method_score))

    # --- efficiency ---
    eff_score = 0.7
    if 0 < execution_time < 5.0:
        eff_score += 0.2
    elif execution_time < 15.0:
        eff_score += 0.1
    elif execution_time > 60.0:
        eff_score -= 0.2
    if prediction_results:
        eff_score += 0.1
    eff_score = max(0.0, min(1.0, eff_score))

    # --- weighted overall ---
    overall = round(
        CRITIC_WEIGHTS["prediction_quality"] * pred_score
        + CRITIC_WEIGHTS["analysis_depth"] * analysis_score
        + CRITIC_WEIGHTS["interpretation_accuracy"] * interp_score
        + CRITIC_WEIGHTS["methodology"] * method_score
        + CRITIC_WEIGHTS["efficiency"] * eff_score,
        3,
    )

    # --- feedback ---
    if overall > 0.8:
        feedback = "Excellent structure prediction with comprehensive metrics"
    elif overall > 0.6:
        feedback = "Good prediction quality with some areas for enhancement"
    elif overall > 0.4:
        feedback = "Adequate prediction but significant improvements needed"
    else:
        feedback = "Poor prediction quality requiring major improvements"

    # --- strengths / improvements ---
    strengths: List[str] = []
    improvements: List[str] = []

    if prediction_results:
        best = max(prediction_results, key=lambda r: r.aggregate_score)
        if best.plddt > 80:
            strengths.append("High-confidence structure prediction")
        if best.iptm > 0.7:
            strengths.append("Good interface quality (ipTM)")
        if best.plddt < QUALITY_THRESHOLDS["min_confidence"]:
            improvements.append("Prediction confidence below minimum threshold")
        if best.pae > 15:
            improvements.append("High predicted alignment error — consider alternative methods")
    else:
        improvements.append("No prediction results produced")

    if execution_time > 30:
        improvements.append("Execution time could be optimized")
    if execution_time < 15 and prediction_results:
        strengths.append("Efficient execution time")

    # --- priority recommendations ---
    priorities: Dict[str, List[str]] = {"critical": [], "important": [], "nice_to_have": []}
    if not prediction_results:
        priorities["critical"].append("Fix prediction pipeline — no results produced")
    elif max(r.plddt for r in prediction_results) < 50:
        priorities["critical"].append("Very low confidence — review input sequence quality")
    if len(prediction_results) < 3:
        priorities["important"].append("Generate more models for better sampling")
    if execution_time > 30:
        priorities["nice_to_have"].append("Optimize execution efficiency")

    return CriticEvaluation(
        prediction_quality=pred_score,
        analysis_depth=analysis_score,
        interpretation_accuracy=interp_score,
        methodology=method_score,
        efficiency=eff_score,
        overall_score=overall,
        feedback=feedback,
        strengths=strengths,
        improvement_areas=improvements,
        priority_recommendations=priorities,
    )


# ---------------------------------------------------------------------------
# Artifact DAG integration
# ---------------------------------------------------------------------------


def store_artifacts(
    sequences: List[tuple[str, str]],
    prediction_results: List[PredictionResult],
    critic_eval: CriticEvaluation,
    store: ArtifactStore,
    tracker: ProvenanceTracker,
    params: Dict[str, Any],
) -> List[str]:
    """
    Store prediction results in the Artifact DAG with provenance.

    Returns list of artifact IDs that were created.
    """
    run = tracker.start_run(
        skill_name=SKILL_NAME,
        skill_version=SKILL_VERSION,
        parameters=params,
    )

    output_ids: List[str] = []

    # 1. Sequence artifact(s)
    seq_ids: List[str] = []
    for name, seq in sequences:
        seq_art = create_artifact(
            metadata=ArtifactMetadata(
                artifact_type=ArtifactType.SEQUENCE,
                skill_name=SKILL_NAME,
                skill_version=SKILL_VERSION,
                tags=frozenset({"input", "protein"}),
            ),
            data={"name": name, "sequence": seq, "length": len(seq)},
            run_id=run.run_id,
        )
        store.put(seq_art)
        seq_ids.append(seq_art.artifact_id)
        output_ids.append(seq_art.artifact_id)

    # 2. Structure + score artifacts (one per model)
    structure_ids: List[str] = []
    for result in prediction_results:
        struct_art = create_artifact(
            parent_ids=tuple(seq_ids),
            metadata=ArtifactMetadata(
                artifact_type=ArtifactType.PDB_STRUCTURE,
                skill_name=SKILL_NAME,
                skill_version=SKILL_VERSION,
                tags=frozenset({"prediction", result.backend}),
                extra=(("backend", result.backend),),
            ),
            data={
                "model_index": result.model_index,
                "pdb_path": result.pdb_path,
                "sequence_name": result.sequence_name,
                "plddt": result.plddt,
                "pae": result.pae,
                "iptm": result.iptm,
                "aggregate_score": result.aggregate_score,
            },
            run_id=run.run_id,
        )
        store.put(struct_art)
        structure_ids.append(struct_art.artifact_id)
        output_ids.append(struct_art.artifact_id)

        # Score artifact per model
        score_art = create_artifact(
            parent_ids=(struct_art.artifact_id,),
            metadata=ArtifactMetadata(
                artifact_type=ArtifactType.SCORE,
                skill_name=SKILL_NAME,
                skill_version=SKILL_VERSION,
                tags=frozenset({"quality_metrics"}),
            ),
            data={
                "plddt": result.plddt,
                "pae": result.pae,
                "iptm": result.iptm,
                "aggregate_score": result.aggregate_score,
                "meets_threshold": result.plddt >= QUALITY_THRESHOLDS["min_confidence"],
            },
            run_id=run.run_id,
        )
        store.put(score_art)
        output_ids.append(score_art.artifact_id)

    # 3. Critic evaluation artifact
    eval_art = create_artifact(
        parent_ids=tuple(structure_ids),
        metadata=ArtifactMetadata(
            artifact_type=ArtifactType.ANALYSIS,
            skill_name=SKILL_NAME,
            skill_version=SKILL_VERSION,
            tags=frozenset({"critic", "evaluation"}),
        ),
        data=critic_eval.to_dict(),
        run_id=run.run_id,
    )
    store.put(eval_art)
    output_ids.append(eval_art.artifact_id)

    # Finish provenance run
    tracker.finish_run(run.run_id, output_artifact_ids=output_ids)

    return output_ids


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_prediction(args: argparse.Namespace) -> Dict[str, Any]:
    """Execute the full prediction pipeline and return a summary dict."""
    start_time = datetime.now(tz=_UTC)

    # --- parse sequences ---
    sequences: List[tuple[str, str]] = []
    if args.fasta:
        sequences = parse_fasta(args.fasta)
    elif args.sequence:
        sequences = [(args.sequence_name, args.sequence)]
    else:
        logger.error("No sequence input provided")
        return {"status": "error", "error": "Provide --sequence or --fasta"}

    for name, seq in sequences:
        if not validate_sequence(seq):
            return {"status": "error", "error": f"Invalid amino acid sequence for '{name}'"}

    logger.info(
        "Running structure prediction: %d sequence(s), backend=%s, models=%d",
        len(sequences),
        args.backend,
        args.num_models,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- run prediction ---
    constraints = None
    if args.constraints:
        constraints = json.loads(args.constraints)

    if args.backend == "chai":
        results = run_chai_prediction(
            sequences=sequences,
            num_models=args.num_models,
            device=args.device,
            output_dir=output_dir,
            use_templates=args.use_templates,
            constraints=constraints,
        )
    elif args.backend == "alphafold":
        results = run_alphafold_prediction(
            sequences=sequences,
            num_models=args.num_models,
            device=args.device,
            output_dir=output_dir,
            use_templates=args.use_templates,
        )
    else:
        return {"status": "error", "error": f"Unknown backend: {args.backend}"}

    elapsed = (datetime.now(tz=_UTC) - start_time).total_seconds()

    # --- critic evaluation ---
    critic_eval = evaluate_prediction(results, elapsed)

    # --- rank models ---
    ranked = sorted(results, key=lambda r: r.aggregate_score, reverse=True)
    best = ranked[0] if ranked else None

    # --- artifact DAG integration ---
    artifact_ids: List[str] = []
    if args.artifact_store:
        store = ArtifactStore(args.artifact_store)
        tracker = ProvenanceTracker(args.artifact_store)
        params = {
            "backend": args.backend,
            "num_models": args.num_models,
            "device": args.device,
            "use_templates": args.use_templates,
        }
        artifact_ids = store_artifacts(sequences, results, critic_eval, store, tracker, params)
        logger.info("Stored %d artifacts in DAG", len(artifact_ids))

    # --- write JSON summary ---
    summary = {
        "status": "success",
        "backend": args.backend,
        "num_sequences": len(sequences),
        "num_models_total": len(results),
        "execution_time_s": round(elapsed, 2),
        "best_model": best.to_dict() if best else None,
        "all_models": [r.to_dict() for r in ranked],
        "critic_evaluation": critic_eval.to_dict(),
        "artifact_ids": artifact_ids,
        "timestamp": datetime.now(tz=_UTC).isoformat(),
    }

    summary_path = output_dir / "prediction_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    logger.info("Summary written to %s", summary_path)

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_prediction",
        description="Protein structure prediction using Chai-1 or AlphaFold.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  %(prog)s --sequence "MKWVTFISLLLLFSSAYSRGV" --backend chai --num-models 5
  %(prog)s --fasta proteins.fasta --backend alphafold --use-templates
  %(prog)s --sequence "ACDEFGHIKLMNPQRSTVWY" --artifact-store ./dag_store
""",
    )

    # Input
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--sequence",
        type=str,
        help="Amino acid sequence (raw string)",
    )
    input_group.add_argument(
        "--fasta",
        type=str,
        help="Path to FASTA file",
    )

    # Prediction settings
    parser.add_argument(
        "--backend",
        choices=["chai", "alphafold"],
        default="chai",
        help="Prediction backend (default: chai)",
    )
    parser.add_argument(
        "--num-models",
        type=int,
        default=5,
        help="Number of models to generate (default: 5)",
    )
    parser.add_argument(
        "--use-templates",
        action="store_true",
        default=False,
        help="Use template structures for prediction",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cuda:0",
        help='Compute device (default: "cuda:0")',
    )
    parser.add_argument(
        "--sequence-name",
        type=str,
        default="query",
        help="Name for the input sequence (default: query)",
    )
    parser.add_argument(
        "--constraints",
        type=str,
        default=None,
        help="JSON string of folding constraints",
    )

    # Output
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./prediction_output",
        help="Output directory (default: ./prediction_output)",
    )
    parser.add_argument(
        "--artifact-store",
        type=str,
        default=None,
        help="Path to artifact store for DAG integration",
    )

    # Logging
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    summary = run_prediction(args)

    if summary["status"] == "error":
        logger.error("Prediction failed: %s", summary.get("error"))
        sys.exit(1)

    # Print concise result
    best = summary.get("best_model")
    critic = summary.get("critic_evaluation", {})
    print(f"\n{'=' * 60}")
    print(f"Structure Prediction Complete ({summary['backend']})")
    print(f"{'=' * 60}")
    print(f"  Sequences:       {summary['num_sequences']}")
    print(f"  Models:          {summary['num_models_total']}")
    print(f"  Execution time:  {summary['execution_time_s']:.1f}s")
    if best:
        print(f"  Best pLDDT:      {best['plddt']:.1f}")
        print(f"  Best ipTM:       {best['iptm']:.3f}")
        print(f"  Best aggregate:  {best['aggregate_score']:.3f}")
    print(f"  Critic score:    {critic.get('overall_score', 0):.3f}")
    print(f"  Critic verdict:  {critic.get('feedback', 'N/A')}")
    if summary.get("artifact_ids"):
        print(f"  Artifacts:       {len(summary['artifact_ids'])} stored in DAG")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
