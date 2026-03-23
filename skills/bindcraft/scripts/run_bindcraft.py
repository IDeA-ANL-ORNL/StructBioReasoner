#!/usr/bin/env python3
"""
BindCraft computational peptide binder design skill.

Orchestrates the BindCraft pipeline:
  1. ProteinMPNN inverse folding → candidate binder sequences
  2. Sequence quality control filtering
  3. Chai/ESMFold structure prediction → folded complexes
  4. Energy scoring → ranked binders
  5. Iterative refinement over N rounds

Integrates with the Artifact DAG (Layer 3) to produce immutable,
provenance-tracked artifacts for each stage of the pipeline.

Usage:
    python run_bindcraft.py --target-sequence "MKWVT..." --num-rounds 3
    python run_bindcraft.py --config config.json
    python run_bindcraft.py --help
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Artifact DAG integration (Layer 3)
# ---------------------------------------------------------------------------

# Resolve the skills root so we can import _shared
_SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILLS_ROOT))

from _shared.artifact import (
    ArtifactMetadata,
    ArtifactType,
    create_artifact,
)
from _shared.artifact_store import ArtifactStore
from _shared.provenance import ProvenanceTracker

logger = logging.getLogger("bindcraft")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default BindCraft config_master schema (from prompts.py)
DESIGN_CONFIG_SCHEMA = {
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
}


@dataclass
class BindCraftConfig:
    """Configuration for a BindCraft design run."""

    target_sequence: str = ""
    binder_sequence: str = "MKQHKAMIVALIVICITAVVAALVTRKDLCEVHIRTGQTEVAVF"
    num_rounds: int = 3
    num_seq: int = 25
    batch_size: int = 250
    max_retries: int = 5
    sampling_temp: float = 0.1
    device: str = "cuda:0"
    output_dir: str = "./bindcraft_output"
    artifact_store_path: Optional[str] = None

    # ProteinMPNN model settings
    mpnn_model: str = "v_48_020"
    mpnn_weights: str = "soluble_model_weights"
    proteinmpnn_path: str = ""

    # QC thresholds
    max_repeat: int = 4
    max_appearance_ratio: float = 0.33
    max_charge: int = 5
    max_charge_ratio: float = 0.5
    max_hydrophobic_ratio: float = 0.8
    min_diversity: int = 8

    # Constraints
    constraints: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_sequence": self.target_sequence,
            "binder_sequence": self.binder_sequence,
            "num_rounds": self.num_rounds,
            "num_seq": self.num_seq,
            "batch_size": self.batch_size,
            "max_retries": self.max_retries,
            "sampling_temp": self.sampling_temp,
            "device": self.device,
            "output_dir": self.output_dir,
            "mpnn_model": self.mpnn_model,
            "mpnn_weights": self.mpnn_weights,
            "proteinmpnn_path": self.proteinmpnn_path,
            "max_repeat": self.max_repeat,
            "max_appearance_ratio": self.max_appearance_ratio,
            "max_charge": self.max_charge,
            "max_charge_ratio": self.max_charge_ratio,
            "max_hydrophobic_ratio": self.max_hydrophobic_ratio,
            "min_diversity": self.min_diversity,
            "constraints": self.constraints,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BindCraftConfig":
        return cls(
            target_sequence=d.get("target_sequence", ""),
            binder_sequence=d.get(
                "binder_sequence",
                "MKQHKAMIVALIVICITAVVAALVTRKDLCEVHIRTGQTEVAVF",
            ),
            num_rounds=d.get("num_rounds", 3),
            num_seq=d.get("num_seq", 25),
            batch_size=d.get("batch_size", 250),
            max_retries=d.get("max_retries", 5),
            sampling_temp=d.get("sampling_temp", 0.1),
            device=d.get("device", "cuda:0"),
            output_dir=d.get("output_dir", "./bindcraft_output"),
            artifact_store_path=d.get("artifact_store_path"),
            mpnn_model=d.get("mpnn_model", "v_48_020"),
            mpnn_weights=d.get("mpnn_weights", "soluble_model_weights"),
            proteinmpnn_path=d.get("proteinmpnn_path", ""),
            max_repeat=d.get("max_repeat", 4),
            max_appearance_ratio=d.get("max_appearance_ratio", 0.33),
            max_charge=d.get("max_charge", 5),
            max_charge_ratio=d.get("max_charge_ratio", 0.5),
            max_hydrophobic_ratio=d.get("max_hydrophobic_ratio", 0.8),
            min_diversity=d.get("min_diversity", 8),
            constraints=d.get("constraints"),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "BindCraftConfig":
        with open(path) as f:
            return cls.from_dict(json.load(f))


# ---------------------------------------------------------------------------
# BindCraft runner — wraps the pipeline with artifact production
# ---------------------------------------------------------------------------


class BindCraftRunner:
    """
    Orchestrates the BindCraft binder design pipeline.

    Wraps the core BindCraft components (ProteinMPNN, Chai, energy scoring,
    QC) and integrates with the Artifact DAG for provenance tracking.
    """

    SKILL_NAME = "bindcraft"
    SKILL_VERSION = "0.1.0"

    def __init__(self, config: BindCraftConfig) -> None:
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Artifact integration (optional — works without a store too)
        self.store: Optional[ArtifactStore] = None
        self.tracker: Optional[ProvenanceTracker] = None
        if config.artifact_store_path:
            store_root = Path(config.artifact_store_path)
            self.store = ArtifactStore(store_root)
            self.tracker = ProvenanceTracker(store_root)

    # -- Lazy imports of BindCraft components --------------------------------

    def _import_components(self):
        """
        Lazily import BindCraft components.

        Returns a dict of component classes, or raises ImportError with
        a helpful message if BindCraft is not installed.
        """
        try:
            from bindcraft.core.folding import ChaiBinder
            from bindcraft.core.inverse_folding import ProteinMPNN
            from bindcraft.analysis.energy import SimpleEnergy
            from bindcraft.util.quality_control import SequenceQualityControl

            return {
                "ChaiBinder": ChaiBinder,
                "ProteinMPNN": ProteinMPNN,
                "SimpleEnergy": SimpleEnergy,
                "SequenceQualityControl": SequenceQualityControl,
            }
        except ImportError as e:
            raise ImportError(
                f"BindCraft components not available: {e}\n"
                "Install from: https://github.com/msinclair-py/bindcraft/tree/agent_acad\n"
                "  git clone -b agent_acad https://github.com/msinclair-py/bindcraft.git\n"
                "  cd bindcraft && pip install -e ."
            ) from e

    def _try_import_coordinator(self):
        """Try to import the ParslDesignCoordinator for full pipeline mode."""
        try:
            from bindcraft.core.coordinators import ParslDesignCoordinator

            return ParslDesignCoordinator
        except ImportError:
            return None

    # -- Artifact helpers ----------------------------------------------------

    def _emit_artifact(
        self,
        artifact_type: ArtifactType,
        data: Any,
        parent_ids: tuple = (),
        tags: frozenset = frozenset(),
        run_id: Optional[str] = None,
    ) -> Optional[str]:
        """Create and store an artifact. Returns artifact_id or None."""
        if self.store is None:
            return None
        artifact = create_artifact(
            parent_ids=parent_ids,
            metadata=ArtifactMetadata(
                artifact_type=artifact_type,
                skill_name=self.SKILL_NAME,
                skill_version=self.SKILL_VERSION,
                tags=tags,
            ),
            data=data,
            run_id=run_id,
        )
        self.store.put(artifact)
        logger.info("Stored artifact %s (%s)", artifact.artifact_id, artifact_type.value)
        return artifact.artifact_id

    # -- Pipeline stages -----------------------------------------------------

    def _build_if_kwargs(self) -> Dict[str, Any]:
        """Build inverse folding kwargs from config."""
        cfg = self.config
        return {
            "num_seq": cfg.num_seq,
            "batch_size": cfg.batch_size,
            "max_retries": cfg.max_retries,
            "sampling_temp": str(cfg.sampling_temp),
            "model_name": cfg.mpnn_model,
            "model_weights": cfg.mpnn_weights,
            "proteinmpnn_path": cfg.proteinmpnn_path,
            "device": cfg.device,
        }

    def _build_qc_kwargs(self) -> Dict[str, Any]:
        """Build quality control kwargs from config."""
        cfg = self.config
        return {
            "max_repeat": cfg.max_repeat,
            "max_appearance_ratio": cfg.max_appearance_ratio,
            "max_charge": cfg.max_charge,
            "max_charge_ratio": cfg.max_charge_ratio,
            "max_hydrophobic_ratio": cfg.max_hydrophobic_ratio,
            "min_diversity": cfg.min_diversity,
            "bad_motifs": None,
            "bad_n_termini": None,
        }

    async def run(self) -> Dict[str, Any]:
        """
        Execute the BindCraft binder design pipeline.

        Returns a results dict with keys:
          - rounds_completed: int
          - total_sequences_generated: int
          - total_sequences_filtered: int
          - all_cycles: list of per-round results
          - top_binders: dict of top-ranked binders
          - artifact_ids: list of produced artifact IDs
        """
        cfg = self.config
        if not cfg.target_sequence:
            raise ValueError("target_sequence is required")

        # Start provenance tracking
        run_id = None
        if self.tracker:
            record = self.tracker.start_run(
                skill_name=self.SKILL_NAME,
                skill_version=self.SKILL_VERSION,
                parameters=cfg.to_dict(),
            )
            run_id = record.run_id

        # Emit the input config as a PARAMETER_SET artifact
        config_artifact_id = self._emit_artifact(
            ArtifactType.PARAMETER_SET,
            data=cfg.to_dict(),
            tags=frozenset({"input", "config"}),
            run_id=run_id,
        )

        artifact_ids: List[str] = []
        if config_artifact_id:
            artifact_ids.append(config_artifact_id)

        # Try to import and run the full pipeline
        try:
            components = self._import_components()
            CoordinatorCls = self._try_import_coordinator()

            if CoordinatorCls is not None:
                results = await self._run_coordinator_pipeline(
                    components, CoordinatorCls, run_id, artifact_ids
                )
            else:
                logger.info(
                    "ParslDesignCoordinator not available; "
                    "running component-level pipeline"
                )
                results = await self._run_component_pipeline(
                    components, run_id, artifact_ids
                )
        except ImportError as e:
            logger.warning(
                "BindCraft not installed — running in dry-run mode: %s", e
            )
            results = self._dry_run(run_id, artifact_ids)

        # Finalize provenance
        if self.tracker and run_id:
            self.tracker.finish_run(
                run_id=run_id,
                output_artifact_ids=artifact_ids,
                status="success",
            )

        # Write results summary to disk
        results_path = self.output_dir / "results.json"
        results_path.write_text(json.dumps(results, indent=2, default=str))
        logger.info("Results written to %s", results_path)

        return results

    async def _run_coordinator_pipeline(
        self,
        components: Dict[str, Any],
        CoordinatorCls: type,
        run_id: Optional[str],
        artifact_ids: List[str],
    ) -> Dict[str, Any]:
        """Run the full BindCraft pipeline via ParslDesignCoordinator."""
        from academy.exchange import LocalExchangeFactory
        from academy.manager import Manager
        from concurrent.futures import ThreadPoolExecutor

        cfg = self.config
        fasta_dir = self.output_dir / "fastas"
        folds_dir = self.output_dir / "folds"
        fasta_dir.mkdir(exist_ok=True)
        folds_dir.mkdir(exist_ok=True)

        if_kwargs = self._build_if_kwargs()
        qc_kwargs = self._build_qc_kwargs()

        # Instantiate BindCraft algorithm components
        chai = components["ChaiBinder"](
            fasta_dir=fasta_dir,
            out=folds_dir,
            diffusion_steps=100,
            device=cfg.device,
        )
        proteinmpnn = components["ProteinMPNN"](**if_kwargs)
        qc_alg = components["SequenceQualityControl"](**qc_kwargs)
        energy_alg = components["SimpleEnergy"]()

        # Launch coordinator via Academy Manager
        manager = await Manager.from_exchange_factory(
            factory=LocalExchangeFactory(),
            executors=ThreadPoolExecutor(),
        )
        await manager.__aenter__()

        try:
            coordinator = await manager.launch(
                CoordinatorCls,
                args=(
                    chai,
                    proteinmpnn,
                    energy_alg,
                    qc_alg,
                    None,  # parsl_settings (not needed for local mode)
                    cfg.num_seq,
                    cfg.max_retries,
                    -10.0,  # energy threshold
                ),
            )

            raw_results = await coordinator.run_full_workflow(
                target_sequence=cfg.target_sequence,
                binder_sequence=cfg.binder_sequence,
                fasta_base_path=fasta_dir,
                pdb_base_path=folds_dir,
                constraints=cfg.constraints,
                remodel_indices=None,
                num_rounds=cfg.num_rounds,
            )
        finally:
            await manager.__aexit__(None, None, None)

        return self._process_results(raw_results, run_id, artifact_ids)

    async def _run_component_pipeline(
        self,
        components: Dict[str, Any],
        run_id: Optional[str],
        artifact_ids: List[str],
    ) -> Dict[str, Any]:
        """
        Run BindCraft components individually without the coordinator.

        This mode works when BindCraft is installed but the
        ParslDesignCoordinator is not available.
        """
        cfg = self.config
        fasta_dir = self.output_dir / "fastas"
        folds_dir = self.output_dir / "folds"
        fasta_dir.mkdir(exist_ok=True)
        folds_dir.mkdir(exist_ok=True)

        if_kwargs = self._build_if_kwargs()
        qc_kwargs = self._build_qc_kwargs()

        proteinmpnn = components["ProteinMPNN"](**if_kwargs)
        chai = components["ChaiBinder"](
            fasta_dir=fasta_dir,
            out=folds_dir,
            diffusion_steps=100,
            device=cfg.device,
        )
        qc_alg = components["SequenceQualityControl"](**qc_kwargs)
        energy_alg = components["SimpleEnergy"]()

        all_cycles = []
        total_generated = 0
        total_filtered = 0

        for round_idx in range(cfg.num_rounds):
            logger.info("Round %d/%d", round_idx + 1, cfg.num_rounds)

            # 1. Inverse folding — generate sequences
            sequences = proteinmpnn.design(
                target_sequence=cfg.target_sequence,
                binder_sequence=cfg.binder_sequence,
            )
            total_generated += len(sequences)

            # Emit sequence artifacts
            seq_parent = tuple(artifact_ids[-1:]) if artifact_ids else ()
            seq_artifact_id = self._emit_artifact(
                ArtifactType.SEQUENCE,
                data={"round": round_idx, "sequences": sequences},
                parent_ids=seq_parent,
                tags=frozenset({"round_%d" % round_idx, "proteinmpnn"}),
                run_id=run_id,
            )
            if seq_artifact_id:
                artifact_ids.append(seq_artifact_id)

            # 2. Quality control
            passing = qc_alg.filter(sequences)
            total_filtered += len(passing)

            # 3. Fold and score passing sequences
            evaluated = {}
            for i, seq in enumerate(passing):
                fold_result = chai.fold(
                    target_sequence=cfg.target_sequence,
                    binder_sequence=seq,
                )
                energy = energy_alg.score(fold_result)
                evaluated[f"seq_{round_idx}_{i}"] = {
                    "sequence": seq,
                    "fold_result": str(fold_result),
                    "energy": energy,
                }

            # Emit score artifact for this round
            score_artifact_id = self._emit_artifact(
                ArtifactType.SCORE,
                data={
                    "round": round_idx,
                    "num_evaluated": len(evaluated),
                    "evaluated": evaluated,
                },
                parent_ids=(seq_artifact_id,) if seq_artifact_id else (),
                tags=frozenset({"round_%d" % round_idx, "scores"}),
                run_id=run_id,
            )
            if score_artifact_id:
                artifact_ids.append(score_artifact_id)

            passing_structures = [
                k for k, v in evaluated.items()
                if v["energy"] is not None and v["energy"] < -10.0
            ]

            all_cycles.append(
                {
                    "round": round_idx,
                    "sequences_generated": len(sequences),
                    "sequences_filtered": len(passing),
                    "evaluated_structures": evaluated,
                    "passing_structures": passing_structures,
                }
            )

        top_binders = self._extract_top_binders(all_cycles, n=5)

        # Emit summary score table
        self._emit_artifact(
            ArtifactType.SCORE_TABLE,
            data={
                "rounds_completed": cfg.num_rounds,
                "total_sequences_generated": total_generated,
                "total_sequences_filtered": total_filtered,
                "top_binders": top_binders,
            },
            tags=frozenset({"summary", "score_table"}),
            run_id=run_id,
        )

        return {
            "rounds_completed": cfg.num_rounds,
            "total_sequences_generated": total_generated,
            "total_sequences_filtered": total_filtered,
            "all_cycles": all_cycles,
            "top_binders": top_binders,
            "artifact_ids": artifact_ids,
        }

    def _dry_run(
        self, run_id: Optional[str], artifact_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Dry-run mode when BindCraft is not installed.

        Validates the configuration and produces placeholder artifacts
        to verify the pipeline wiring and artifact DAG integration.
        """
        cfg = self.config
        logger.info("DRY RUN — BindCraft not installed; validating config only")

        placeholder_data = {
            "mode": "dry_run",
            "target_sequence_length": len(cfg.target_sequence),
            "binder_sequence_length": len(cfg.binder_sequence),
            "num_rounds": cfg.num_rounds,
            "num_seq": cfg.num_seq,
            "device": cfg.device,
            "constraints": cfg.constraints,
        }

        art_id = self._emit_artifact(
            ArtifactType.RAW_OUTPUT,
            data=placeholder_data,
            tags=frozenset({"dry_run"}),
            run_id=run_id,
        )
        if art_id:
            artifact_ids.append(art_id)

        return {
            "rounds_completed": 0,
            "total_sequences_generated": 0,
            "total_sequences_filtered": 0,
            "all_cycles": [],
            "top_binders": {},
            "artifact_ids": artifact_ids,
            "dry_run": True,
            "message": (
                "BindCraft is not installed. Install from: "
                "https://github.com/msinclair-py/bindcraft/tree/agent_acad"
            ),
        }

    def _process_results(
        self,
        raw_results: Dict[str, Any],
        run_id: Optional[str],
        artifact_ids: List[str],
    ) -> Dict[str, Any]:
        """Process coordinator results and emit artifacts."""
        all_cycles = raw_results.get("all_cycles", [])
        top_binders = self._extract_top_binders(all_cycles, n=5)

        # Emit score table artifact
        table_id = self._emit_artifact(
            ArtifactType.SCORE_TABLE,
            data={
                "rounds_completed": raw_results.get("rounds_completed", 0),
                "total_sequences_generated": raw_results.get(
                    "total_sequences_generated", 0
                ),
                "total_sequences_filtered": raw_results.get(
                    "total_sequences_filtered", 0
                ),
                "top_binders": top_binders,
            },
            tags=frozenset({"summary", "score_table"}),
            run_id=run_id,
        )
        if table_id:
            artifact_ids.append(table_id)

        return {
            "rounds_completed": raw_results.get("rounds_completed", 0),
            "total_sequences_generated": raw_results.get(
                "total_sequences_generated", 0
            ),
            "total_sequences_filtered": raw_results.get(
                "total_sequences_filtered", 0
            ),
            "all_cycles": all_cycles,
            "top_binders": top_binders,
            "artifact_ids": artifact_ids,
        }

    @staticmethod
    def _extract_top_binders(
        all_cycles: List[Dict[str, Any]], n: int = 5
    ) -> Dict[int, Dict[str, Any]]:
        """Extract top N binders by energy across all cycles."""
        candidates = []
        for cycle in all_cycles:
            evaluated = cycle.get("evaluated_structures", {})
            for val in evaluated.values():
                if val.get("energy") is not None:
                    candidates.append(val)

        candidates.sort(key=lambda x: x.get("energy", float("inf")))
        return {i: c for i, c in enumerate(candidates[:n])}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_bindcraft",
        description=(
            "BindCraft computational peptide binder design. "
            "Runs ProteinMPNN inverse folding → QC → Chai folding → energy scoring "
            "in an iterative loop."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --target-sequence MKWVTFIS... --num-rounds 3\n"
            "  %(prog)s --config design_config.json\n"
            "  %(prog)s --target-sequence MKWV... --artifact-store ./dag_store\n"
        ),
    )

    p.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to JSON config file (overrides individual flags)",
    )

    # Required inputs
    p.add_argument(
        "--target-sequence",
        type=str,
        default=None,
        help="Amino acid sequence of the target protein (required unless --config given)",
    )
    p.add_argument(
        "--binder-sequence",
        type=str,
        default="MKQHKAMIVALIVICITAVVAALVTRKDLCEVHIRTGQTEVAVF",
        help="Initial binder scaffold sequence (default: standard test peptide)",
    )

    # Pipeline settings
    p.add_argument(
        "--num-rounds", type=int, default=3, help="Number of design rounds (default: 3)"
    )
    p.add_argument(
        "--num-seq",
        type=int,
        default=25,
        help="Sequences per ProteinMPNN batch (default: 25)",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=250,
        help="ProteinMPNN batch size (default: 250)",
    )
    p.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Max retries for inverse folding (default: 5)",
    )
    p.add_argument(
        "--sampling-temp",
        type=float,
        default=0.1,
        help="ProteinMPNN sampling temperature (default: 0.1)",
    )
    p.add_argument(
        "--device",
        type=str,
        default="cuda:0",
        help="Compute device (default: cuda:0)",
    )

    # ProteinMPNN model
    p.add_argument(
        "--mpnn-model",
        type=str,
        default="v_48_020",
        help="ProteinMPNN model name (default: v_48_020)",
    )
    p.add_argument(
        "--mpnn-weights",
        type=str,
        default="soluble_model_weights",
        help="ProteinMPNN weight set (default: soluble_model_weights)",
    )
    p.add_argument(
        "--proteinmpnn-path",
        type=str,
        default="",
        help="Path to ProteinMPNN installation",
    )

    # QC thresholds
    qc = p.add_argument_group("quality control thresholds")
    qc.add_argument("--max-repeat", type=int, default=4)
    qc.add_argument("--max-appearance-ratio", type=float, default=0.33)
    qc.add_argument("--max-charge", type=int, default=5)
    qc.add_argument("--max-charge-ratio", type=float, default=0.5)
    qc.add_argument("--max-hydrophobic-ratio", type=float, default=0.8)
    qc.add_argument("--min-diversity", type=int, default=8)

    # Constraints
    p.add_argument(
        "--constraints",
        type=str,
        default=None,
        help='Binding constraints as JSON string, e.g. \'{"residues_bind": ["R45", "K78"]}\'',
    )

    # Output
    p.add_argument(
        "--output-dir",
        type=str,
        default="./bindcraft_output",
        help="Output directory (default: ./bindcraft_output)",
    )
    p.add_argument(
        "--artifact-store",
        type=str,
        default=None,
        help="Path to artifact store directory for DAG integration",
    )

    # Misc
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config without running the pipeline",
    )
    p.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    return p


def config_from_args(args: argparse.Namespace) -> BindCraftConfig:
    """Build a BindCraftConfig from parsed CLI arguments."""
    if args.config:
        cfg = BindCraftConfig.from_json(args.config)
        # CLI overrides still apply on top of config file
        if args.target_sequence:
            cfg = BindCraftConfig(
                **{**cfg.to_dict(), "target_sequence": args.target_sequence}
            )
        return cfg

    constraints = None
    if args.constraints:
        constraints = json.loads(args.constraints)

    return BindCraftConfig(
        target_sequence=args.target_sequence or "",
        binder_sequence=args.binder_sequence,
        num_rounds=args.num_rounds,
        num_seq=args.num_seq,
        batch_size=args.batch_size,
        max_retries=args.max_retries,
        sampling_temp=args.sampling_temp,
        device=args.device,
        output_dir=args.output_dir,
        artifact_store_path=args.artifact_store,
        mpnn_model=args.mpnn_model,
        mpnn_weights=args.mpnn_weights,
        proteinmpnn_path=args.proteinmpnn_path,
        max_repeat=args.max_repeat,
        max_appearance_ratio=args.max_appearance_ratio,
        max_charge=args.max_charge,
        max_charge_ratio=args.max_charge_ratio,
        max_hydrophobic_ratio=args.max_hydrophobic_ratio,
        min_diversity=args.min_diversity,
        constraints=constraints,
    )


async def async_main(args: argparse.Namespace) -> int:
    cfg = config_from_args(args)

    if not cfg.target_sequence and not args.dry_run:
        print(
            "Error: --target-sequence is required (or provide --config)",
            file=sys.stderr,
        )
        return 1

    runner = BindCraftRunner(cfg)

    if args.dry_run:
        # Force dry-run mode
        results = runner._dry_run(None, [])
    else:
        results = await runner.run()

    print(json.dumps(results, indent=2, default=str))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    return asyncio.run(async_main(args))


if __name__ == "__main__":
    sys.exit(main())
