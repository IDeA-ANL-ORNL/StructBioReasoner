"""
RBD Glycan + Disulfide Binder Design Pipeline

Agentic binder design workflow targeting the SARS-CoV-2 Spike Receptor Binding
Domain (RBD, residues 176–602 of Spike), with full glycan and disulfide bond
support wired into the MD preparation step.

Target features (RBD numbering):
  - Glycosylation sites : N131, N203, N306, N354
  - Disulfide bonds     : C41–C65, C107–C120, C318–C328, C390–C399,
                          C207–C220, C14–C426, C212–C324
  - Hotspots            : F183, Y343, I413

The pipeline inherits the full checkpointing, LLM-guided agentic loop, and
hotspot-discovery machinery from AgenticBinderPipelineWithCheckpointing and
overrides only the research goal and default CLI arguments.

Author: StructBioReasoner Team
Date: 2026-03-25
"""

import sys
import asyncio
import logging
import json
import argparse
import dill as pickle
from pathlib import Path
from typing import Dict, Any, List, Optional

from .agentic_binder_pipeline_checkpointing import (
    AgenticBinderPipelineWithCheckpointing,
    PipelineCheckpoint,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logging.getLogger("parsl").propagate = False
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RBD research goal
# ---------------------------------------------------------------------------

RBD_RESEARCH_GOAL = """Design biologic binders for the SARS-CoV-2 Spike Receptor Binding Domain (RBD).

Target: SARS-CoV-2 Spike RBD (residues 176–602 of full-length Spike, UniProt P0DTC2)
Target Sequence: RVQPTESIVRFPNITNLCPFDEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFKCYGVSPTKLNDLCFTNVYADSFVIRGDEVRQIAPGQTGNIADYNYKLPDDFTGCVIAWNSNNLDSKVGGNYNYLYRLFRKSNLKPFERDISTEIYQAGSKPCNGVEGFNCYFPLQSYGFQPTNGVGYQPYRVVVLSFELLHAPATVCGPKKSTNLVKNKCVNFNFNGLTGTGVLTESNKKFLPFQQFGRDIADTTDAVRDPQTLEILDITPCSFGGVSVITPGTNTSNQVAVLYQGVNCTEVPVAIHADQLTPTWRVYSTGSNVFQTRAGCLIGAEHVNNSYECDIPIGAGICASYQTQTNSPGSASSVASQSIIAYTMSLGAENSVAYSNNSIAIPTNFTISVTTEILPVSMTKTSVDCTMYICGDSTECSNLLLQYGSFCTQLNRALTGIAVEQDKNTQEVFAQVKQIYKTPPIKDFGGFNFSQILPDPSKPSKRSFIEDLLFNKVTLADAGFIKQYGDCLGDIAARDLICAQKFNGLTVLPPLLTDEMIAQYTSALLAGTITSGWTFGAGAALQIPFAMQMAYRFNGIGVTQNVLYENQKLIANQFNSAIGKIQDSLSSTASALGKLQDVVNQNAQALNTLVKQLSSNFGAISSVLNDILSRLDPPEAEVQIDRLITGRLQSLQTYVTQQLIRAAEIRASANLAATKMSECVLGQSKRVDFCGKGYHLMSFPQSAPHGVVFLHVTYVPAQEKNFTTAPAICHDGKAHFPREGVFVSNGTHWFVTQRNFYEPQIITTDNTFVSGNCDVVIGIVNNTVYDPLQPELDSFKEELDKYFKNHTSPDVDLGDISGINASVVNIQKEIDRLNEVAKNLNESLIDLQELGKYEQYIKWPWYIWLGFIAGLIAIVMVTIMLCCMTSCCSCLKGCCSCGSCCKFDEDDSEPVLKGVKLHYT

Glycosylation sites (RBD numbering, GLYCAM/AMBER convention):
  N131: NAG(6-1 FUC)(4-1 NAG(4-1 MAN(6-1 MAN(2-1 NAG))(3-1 MAN(2-1 NAG))))
  N203: NAG(6-1 FUC)(4-1 NAG(4-1 MAN(6-1 MAN(2-1 NAG))(3-1 MAN(2-1 NAG))))
  N306: NAG(6-1 FUC)(4-1 NAG(4-1 MAN(6-1 MAN(2-1 NAG))(3-1 MAN(2-1 NAG))))
  N354: NAG(6-1 FUC)(4-1 NAG(4-1 MAN(6-1 MAN(2-1 NAG(4-1 GAL)))(3-1 MAN(2-1 NAG))))

Disulfide bonds (RBD numbering): C41-C65, C107-C120, C318-C328, C390-C399, C207-C220, C14-C426, C212-C324

Objectives:
- Design high-affinity binders (< 10 nM) that are stable under glycan shielding
- Target accessible hotspots: F183, Y343, I413
- Scaffolds: affibody, affitin, or nanobody

Goals:
- High binding affinity (< 10 nM)
- Stable complex in MD simulation (RMSD < 3 Å)
- Robust under glycosylated and disulfide-constrained MD topology
- Prioritize epitopes not occluded by the N131/N203/N306/N354 glycan shield

Default Scaffolds:
- Affibody: VDNKFNKEQQNAFYEILHLPNLNEEQRNAFIQSLKDDPSQSANLLAEAKKLNDAQAPK
- Affitin: MGSWAEFKQRLAAIKTRLQALGGSEAELAAFEKEIAAFESELQAYKGKGNPEVEALRKEAAAIRDELQAYRHN
- Nanobody: QVKLEESGGGSVQTGGSLRLTCAASGRTSRSYGMGWFRQAPGKEREFVSGISWRGDSTGYADSVKGRFTISRDNAKNTVDLQMNSLKPEDTAIYYCAAAAGSAWYGTLYEYDYWGQGTQVTVSSALE
"""

# Known hotspots in RBD numbering (F183, Y343, I413)
RBD_HOTSPOT_RESIDUES: List[int] = [183, 343, 413]




# ---------------------------------------------------------------------------
# Pipeline subclass
# ---------------------------------------------------------------------------

class RBDGlycanDisulfidePipeline(AgenticBinderPipelineWithCheckpointing):
    """
    Binder design pipeline pre-configured for the glycosylated, disulfide-rich
    SARS-CoV-2 RBD target.

    Key differences from the base class:
      - Research goal is fixed to ``RBD_RESEARCH_GOAL``.
      - Default hotspot residues are ``RBD_HOTSPOT_RESIDUES`` (F183, Y343, I413).
      - ``_prepare_md_config`` passes ``glycan_aware=True`` so that
        ``MDAgentAdapter.analyze_hypothesis`` runs ``GlycanConverter`` on each
        folded structure, detecting both glycan bonds and disulfide bonds and
        injecting the resulting ``bond_commands`` into the AMBER build step.
      - Checkpoint directory defaults to ``checkpoints_rbd``.
      - wandb run name defaults to ``rbd_glycan_disulfide``.
    """

    def __init__(
        self,
        config_path: str = "config/binder_config.yaml",
        jnana_config_path: str = "config/jnana_config.yaml",
        max_iterations: int = 1_000_000_000,
        enable_agents: Optional[List[str]] = None,
        checkpoint_dir: str = "checkpoints_rbd",
        checkpoint_interval: int = 1,
        wandb_project: str = "binder_design",
        wandb_name: str = "rbd_glycan_disulfide",
    ):
        super().__init__(
            config_path=config_path,
            jnana_config_path=jnana_config_path,
            max_iterations=max_iterations,
            enable_agents=enable_agents,
            checkpoint_dir=checkpoint_dir,
            checkpoint_interval=checkpoint_interval,
            wandb_project=wandb_project,
            wandb_name=wandb_name,
        )

    # ------------------------------------------------------------------
    # Override: inject glycan_aware flag into MD config
    # ------------------------------------------------------------------

    def _prepare_md_config(
        self,
        config: Dict[str, Any],
        hypothesis: Any,
        iteration: int,
    ) -> Dict[str, Any]:
        """
        Extend the base MD config preparation with glycan/disulfide awareness.

        Sets ``glycan_aware=True`` so that ``MDAgentAdapter`` triggers
        ``GlycanConverter.convert_pdb()`` on each structure — which now
        automatically detects both glycosidic bonds and disulfide bonds,
        renames CYS->CYX, and injects the combined ``bond_commands`` list
        into the AMBER ``ImplicitSolvent`` / ``ExplicitSolvent`` build.
        """
        config = super()._prepare_md_config(config, hypothesis, iteration)
        config["glycan_aware"] = True
        logger.info(
            "[RBD] glycan_aware=True — GlycanConverter will handle "
            "4 glycan sites + 7 disulfide bonds automatically."
        )
        return config

    # ------------------------------------------------------------------
    # Override: run() — supply RBD defaults so callers need zero args
    # ------------------------------------------------------------------

    async def run(  # type: ignore[override]
        self,
        research_goal: str = RBD_RESEARCH_GOAL,
        hotspot_residues: Optional[List[int]] = None,
        discover_hotspots: bool = False,
        target_prot_name: str = "RBD",
        use_actual_hotspot_analysis: bool = False,
    ) -> Dict[str, Any]:
        """
        Run the RBD glycan + disulfide pipeline.

        Defaults to the pre-built ``RBD_RESEARCH_GOAL`` and
        ``RBD_HOTSPOT_RESIDUES`` so the pipeline can be launched with a
        single ``await pipeline.run()`` call.
        """
        if hotspot_residues is None and not discover_hotspots:
            hotspot_residues = RBD_HOTSPOT_RESIDUES
            logger.info(
                "[RBD] Using pre-defined hotspot residues: %s", hotspot_residues
            )

        return await super().run(
            research_goal=research_goal,
            hotspot_residues=hotspot_residues,
            discover_hotspots=discover_hotspots,
            target_prot_name=target_prot_name,
            use_actual_hotspot_analysis=use_actual_hotspot_analysis,
        )


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

async def main() -> bool:
    """Command-line entry point for the RBD glycan + disulfide pipeline."""
    parser = argparse.ArgumentParser(
        description=(
            "RBD Glycan + Disulfide Binder Design Pipeline — "
            "LLM-guided iterative binder optimisation against the "
            "glycosylated, disulfide-rich SARS-CoV-2 RBD."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with pre-defined RBD hotspots (F183, Y343, I413)
  python -m struct_bio_reasoner.workflows.rbd_glycan_disulfide_pipeline

  # Resume from a checkpoint
  python -m struct_bio_reasoner.workflows.rbd_glycan_disulfide_pipeline \\
      --resume checkpoints_rbd/checkpoint_latest.pkl

  # Discover hotspots via RAG -> Folding -> MD instead of using defaults
  python -m struct_bio_reasoner.workflows.rbd_glycan_disulfide_pipeline \\
      --discover-hotspots

  # Limit to 20 iterations, save report
  python -m struct_bio_reasoner.workflows.rbd_glycan_disulfide_pipeline \\
      --max-iterations 20 --output results/rbd_report.json
        """,
    )

    parser.add_argument(
        "--config",
        type=str,
        default="config/binder_config.yaml",
        help="Path to binder configuration file (default: config/binder_config.yaml)",
    )
    parser.add_argument(
        "--jnana-config",
        type=str,
        default="config/jnana_config.yaml",
        help="Path to Jnana configuration file (default: config/jnana_config.yaml)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=25,
        help="Maximum number of design iterations (default: 25)",
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default="checkpoints_rbd",
        help="Directory to save checkpoints (default: checkpoints_rbd)",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=1,
        help="Save checkpoint every N iterations (default: 1, 0 to disable)",
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Path to checkpoint file to resume from",
    )
    parser.add_argument(
        "--hotspot-residues",
        type=str,
        default=None,
        help=(
            "Comma-separated hotspot residue indices in RBD numbering "
            "(e.g. '183,343,413').  Defaults to F183,Y343,I413."
        ),
    )
    parser.add_argument(
        "--discover-hotspots",
        action="store_true",
        help="Run RAG->Folding->MD->Hotspot pipeline instead of using defaults.",
    )
    parser.add_argument(
        "--use-actual-hotspot-analysis",
        action="store_true",
        help="Use MD trajectory analysis for hotspots (requires --discover-hotspots).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to save final report JSON (default: no file output)",
    )
    parser.add_argument(
        "--wandb-project",
        type=str,
        default="binder_design",
        help="W&B project name (default: binder_design)",
    )
    parser.add_argument(
        "--wandb-name",
        type=str,
        default="rbd_glycan_disulfide",
        help="W&B run name (default: rbd_glycan_disulfide)",
    )

    args = parser.parse_args()

    # Parse hotspot residues if provided on CLI
    hotspot_residues: Optional[List[int]] = None
    if args.hotspot_residues:
        hotspot_residues = [int(x.strip()) for x in args.hotspot_residues.split(",")]

    try:
        pipeline = RBDGlycanDisulfidePipeline(
            config_path=args.config,
            jnana_config_path=args.jnana_config,
            max_iterations=args.max_iterations,
            checkpoint_dir=args.checkpoint_dir,
            checkpoint_interval=args.checkpoint_interval,
            wandb_project=args.wandb_project,
            wandb_name=args.wandb_name,
        )

        if args.resume:
            logger.info("Resuming from checkpoint: %s", args.resume)
            final_report = await pipeline.run_from_checkpoint(args.resume)
        else:
            logger.info(
                "Starting RBD glycan + disulfide pipeline.\n"
                "  Glycan sites : N131, N203, N306, N354\n"
                "  Disulfides   : C41-C65, C107-C120, C318-C328, C390-C399, "
                "C207-C220, C14-C426, C212-C324\n"
                "  Hotspots     : %s",
                hotspot_residues or RBD_HOTSPOT_RESIDUES,
            )
            final_report = await pipeline.run(
                research_goal=RBD_RESEARCH_GOAL,
                hotspot_residues=hotspot_residues,
                discover_hotspots=args.discover_hotspots,
                target_prot_name="RBD",
                use_actual_hotspot_analysis=args.use_actual_hotspot_analysis,
            )

        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(final_report, f, indent=2, default=str)
            logger.info("Final report saved to: %s", output_path)

        logger.info("RBD pipeline completed successfully.")
        return True

    except Exception as e:
        logger.error("Pipeline error: %s", e)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
