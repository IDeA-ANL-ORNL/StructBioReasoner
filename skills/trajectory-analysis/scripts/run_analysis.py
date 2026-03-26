#!/usr/bin/env python3
"""
Trajectory analysis skill — MD post-processing.

Supports both static (PDB-only) and dynamic (trajectory + topology) analysis
modes, mirroring the config_master analysis schema:

  static/basic:  distance-based contact maps
  static/advanced: (placeholder for future analyses)
  dynamic/basic: RMSD, RMSF, radius of gyration
  dynamic/advanced: residue contact frequency (hotspot) analysis
  dynamic/both: basic + advanced combined

Integrates with the Artifact DAG (Layer 3) for provenance tracking.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Artifact DAG integration (Layer 3)
# ---------------------------------------------------------------------------
_SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_SKILLS_ROOT))

from _shared.artifact import ArtifactMetadata, ArtifactType, create_artifact
from _shared.artifact_store import ArtifactStore
from _shared.provenance import ProvenanceTracker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Analysis implementations
# ---------------------------------------------------------------------------


def _require(module_name: str):
    """Import helper with a user-friendly error."""
    try:
        return __import__(module_name)
    except ImportError:
        sys.exit(
            f"Error: '{module_name}' is required but not installed. "
            f"Install it with: pip install {module_name}"
        )


# -- Static analyses --------------------------------------------------------


def static_basic(
    paths: List[str],
    distance_cutoff: float = 4.5,
) -> Dict[str, Any]:
    """Contact map from static PDB structures."""
    mdanalysis = _require("MDAnalysis")
    from MDAnalysis.analysis import distances  # noqa: E402

    results: Dict[str, Any] = {}
    for pdb_path in paths:
        u = mdanalysis.Universe(pdb_path)
        ca = u.select_atoms("protein and name CA")
        dist_matrix = distances.distance_array(ca.positions, ca.positions)
        n_residues = len(ca)
        contacts = []
        for i in range(n_residues):
            for j in range(i + 1, n_residues):
                if dist_matrix[i, j] < distance_cutoff:
                    contacts.append(
                        {
                            "residue_i": int(ca[i].resid),
                            "residue_j": int(ca[j].resid),
                            "distance": round(float(dist_matrix[i, j]), 3),
                        }
                    )
        results[pdb_path] = {
            "n_residues": n_residues,
            "n_contacts": len(contacts),
            "distance_cutoff": distance_cutoff,
            "contacts": contacts,
        }
    return {"static_basic": results}


def static_advanced(paths: List[str], **kwargs) -> Dict[str, Any]:
    """Placeholder for future static advanced analyses."""
    return {"static_advanced": {p: {"status": "not_implemented"} for p in paths}}


# -- Dynamic analyses -------------------------------------------------------


def dynamic_basic(
    paths: List[str],
    topology: Optional[str] = None,
    selection: str = "protein and name CA",
    reference_frame: int = 0,
) -> Dict[str, Any]:
    """RMSD, RMSF, and radius of gyration from trajectory."""
    mdanalysis = _require("MDAnalysis")
    from MDAnalysis.analysis import rms, align  # noqa: E402

    results: Dict[str, Any] = {}
    for traj_path in paths:
        if topology:
            u = mdanalysis.Universe(topology, traj_path)
        else:
            u = mdanalysis.Universe(traj_path)

        atoms = u.select_atoms(selection)
        n_frames = u.trajectory.n_frames

        # Align to reference frame
        ref = mdanalysis.Universe(topology, traj_path) if topology else mdanalysis.Universe(traj_path)
        align.AlignTraj(u, ref, select=selection, in_memory=True).run()

        # RMSD
        rmsd_analysis = rms.RMSD(u, ref, select=selection, ref_frame=reference_frame)
        rmsd_analysis.run()
        rmsd_values = rmsd_analysis.results.rmsd[:, 2].tolist()  # column 2 = RMSD
        rmsd_mean = float(sum(rmsd_values) / len(rmsd_values)) if rmsd_values else 0.0
        rmsd_std = float(
            (sum((v - rmsd_mean) ** 2 for v in rmsd_values) / len(rmsd_values)) ** 0.5
        ) if rmsd_values else 0.0

        # RMSF
        rmsf_analysis = rms.RMSF(atoms).run()
        rmsf_values = rmsf_analysis.results.rmsf.tolist()
        rmsf_mean = float(sum(rmsf_values) / len(rmsf_values)) if rmsf_values else 0.0

        # Radius of gyration per frame
        rog_values = []
        for _ts in u.trajectory:
            rog_values.append(float(atoms.radius_of_gyration()))
        rog_mean = float(sum(rog_values) / len(rog_values)) if rog_values else 0.0

        results[traj_path] = {
            "trajectory_info": {
                "n_frames": n_frames,
                "n_atoms": len(atoms),
                "selection": selection,
                "reference_frame": reference_frame,
            },
            "rmsd": {
                "mean": round(rmsd_mean, 4),
                "std": round(rmsd_std, 4),
                "values": [round(v, 4) for v in rmsd_values],
            },
            "rmsf": {
                "mean": round(rmsf_mean, 4),
                "values": [round(v, 4) for v in rmsf_values],
            },
            "radius_of_gyration": {
                "mean": round(rog_mean, 4),
                "values": [round(v, 4) for v in rog_values],
            },
            "summary": {
                "rmsd": round(rmsd_mean, 4),
                "rmsf": round(rmsf_mean, 4),
                "radius_of_gyration": round(rog_mean, 4),
            },
        }
    return {"dynamic_basic": results}


def dynamic_advanced(
    paths: List[str],
    topology: Optional[str] = None,
    selection: str = "protein",
    distance_cutoff: float = 4.5,
    n_top: int = 10,
) -> Dict[str, Any]:
    """Residue contact frequency (hotspot) analysis across trajectory frames."""
    mdanalysis = _require("MDAnalysis")
    from MDAnalysis.analysis import distances  # noqa: E402

    results: Dict[str, Any] = {}
    for traj_path in paths:
        if topology:
            u = mdanalysis.Universe(topology, traj_path)
        else:
            u = mdanalysis.Universe(traj_path)

        atoms = u.select_atoms(selection)
        residue_ids = sorted(set(a.resid for a in atoms))
        n_frames = u.trajectory.n_frames

        # Count contact frequency between residue pairs
        contact_counts: Dict[str, int] = {}
        for _ts in u.trajectory:
            ca = u.select_atoms(f"({selection}) and name CA")
            dist_matrix = distances.distance_array(ca.positions, ca.positions)
            for i in range(len(ca)):
                for j in range(i + 1, len(ca)):
                    if dist_matrix[i, j] < distance_cutoff:
                        key = f"{ca[i].resid}-{ca[j].resid}"
                        contact_counts[key] = contact_counts.get(key, 0) + 1

        # Normalize to frequencies
        contact_freqs = {
            k: round(v / n_frames, 4) for k, v in contact_counts.items()
        }

        # Top contacts (hotspots)
        sorted_contacts = sorted(
            contact_freqs.items(), key=lambda x: x[1], reverse=True
        )
        top_contacts = sorted_contacts[:n_top]

        results[traj_path] = {
            "n_frames": n_frames,
            "distance_cutoff": distance_cutoff,
            "n_top": n_top,
            "total_contact_pairs": len(contact_freqs),
            "top_contacts": [
                {"pair": k, "frequency": v} for k, v in top_contacts
            ],
            "summary": contact_freqs,
        }
    return {"dynamic_advanced": results}


# ---------------------------------------------------------------------------
# Dispatcher — maps (data_type, analysis_type) to functions
# ---------------------------------------------------------------------------

_DISPATCH = {
    ("static", "basic"): static_basic,
    ("static", "advanced"): static_advanced,
    ("dynamic", "basic"): dynamic_basic,
    ("dynamic", "advanced"): dynamic_advanced,
}


def run_analysis(
    data_type: str,
    analysis_type: str,
    paths: List[str],
    topology: Optional[str] = None,
    selection: str = "protein and name CA",
    reference_frame: int = 0,
    distance_cutoff: float = 4.5,
    n_top: int = 10,
    artifact_dir: Optional[str] = None,
    parent_artifact_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Run trajectory analysis and optionally register results in the Artifact DAG.

    Parameters
    ----------
    data_type : str
        "static" or "dynamic"
    analysis_type : str
        "basic", "advanced", or "both"
    paths : list[str]
        Trajectory or PDB file paths
    topology : str, optional
        Topology file (PDB/PSF) for trajectory loading
    selection : str
        MDAnalysis atom selection string
    reference_frame : int
        Reference frame for RMSD alignment
    distance_cutoff : float
        Distance cutoff for contact analysis (Angstroms)
    n_top : int
        Number of top contacts to report in advanced analysis
    artifact_dir : str, optional
        Directory for artifact DAG storage (enables provenance tracking)
    parent_artifact_ids : list[str], optional
        Parent artifact IDs for DAG lineage
    """
    if data_type not in ("static", "dynamic"):
        raise ValueError(f"data_type must be 'static' or 'dynamic', got '{data_type}'")
    if analysis_type not in ("basic", "advanced", "both"):
        raise ValueError(
            f"analysis_type must be 'basic', 'advanced', or 'both', got '{analysis_type}'"
        )

    # Shared kwargs passed to analysis functions
    kwargs: Dict[str, Any] = {
        "paths": paths,
        "distance_cutoff": distance_cutoff,
    }
    if data_type == "dynamic":
        kwargs.update(
            topology=topology,
            selection=selection,
            reference_frame=reference_frame,
            n_top=n_top,
        )

    # Determine which analyses to run
    if analysis_type == "both":
        types_to_run = ["basic", "advanced"]
    else:
        types_to_run = [analysis_type]

    combined: Dict[str, Any] = {"data_type": data_type, "analysis_type": analysis_type}
    for atype in types_to_run:
        fn = _DISPATCH.get((data_type, atype))
        if fn is None:
            combined[f"{data_type}_{atype}"] = {"error": "not implemented"}
            continue
        # Filter kwargs to only those accepted by the function
        import inspect
        sig = inspect.signature(fn)
        valid_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
        combined.update(fn(**valid_kwargs))

    # -- Artifact DAG integration -------------------------------------------
    if artifact_dir:
        store = ArtifactStore(artifact_dir)
        tracker = ProvenanceTracker(artifact_dir)

        record = tracker.start_run(
            skill_name="trajectory-analysis",
            input_artifact_ids=parent_artifact_ids or [],
            parameters={
                "data_type": data_type,
                "analysis_type": analysis_type,
                "paths": paths,
                "topology": topology,
                "selection": selection,
                "distance_cutoff": distance_cutoff,
            },
        )

        artifact = create_artifact(
            parent_ids=tuple(parent_artifact_ids or []),
            metadata=ArtifactMetadata(
                artifact_type=ArtifactType.ANALYSIS,
                skill_name="trajectory-analysis",
                tags=frozenset([data_type, analysis_type, "trajectory"]),
            ),
            data=combined,
            run_id=record.run_id,
        )
        store.put(artifact)

        tracker.finish_run(
            run_id=record.run_id,
            output_artifact_ids=[artifact.artifact_id],
        )

        combined["_artifact_id"] = artifact.artifact_id
        combined["_run_id"] = record.run_id

    return combined


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_analysis",
        description=(
            "Trajectory analysis skill — MD post-processing.\n\n"
            "Supports static (PDB-only) and dynamic (trajectory + topology) modes.\n"
            "  static/basic:    distance-based contact maps\n"
            "  dynamic/basic:   RMSD, RMSF, radius of gyration\n"
            "  dynamic/advanced: residue contact frequency (hotspot) analysis\n"
            "  dynamic/both:    basic + advanced combined"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-type",
        choices=["static", "dynamic"],
        required=True,
        help="Input data type: 'static' (PDB only) or 'dynamic' (trajectory)",
    )
    parser.add_argument(
        "--analysis-type",
        choices=["basic", "advanced", "both"],
        required=True,
        help="Analysis rigor: 'basic', 'advanced', or 'both'",
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        required=True,
        help="Trajectory file(s) or PDB file(s) to analyze",
    )
    parser.add_argument(
        "--topology",
        default=None,
        help="Topology file (PDB/PSF) — required for trajectory formats like DCD/XTC/TRR",
    )
    parser.add_argument(
        "--selection",
        default="protein and name CA",
        help="MDAnalysis atom selection string (default: 'protein and name CA')",
    )
    parser.add_argument(
        "--reference-frame",
        type=int,
        default=0,
        help="Reference frame for RMSD alignment (default: 0)",
    )
    parser.add_argument(
        "--distance-cutoff",
        type=float,
        default=4.5,
        help="Distance cutoff in Angstroms for contact analysis (default: 4.5)",
    )
    parser.add_argument(
        "--n-top",
        type=int,
        default=10,
        help="Number of top contact pairs to report (default: 10)",
    )
    parser.add_argument(
        "--artifact-dir",
        default=None,
        help="Directory for Artifact DAG storage (enables provenance tracking)",
    )
    parser.add_argument(
        "--parent-artifacts",
        nargs="*",
        default=None,
        help="Parent artifact IDs for DAG lineage",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output JSON file (default: print to stdout)",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results = run_analysis(
        data_type=args.data_type,
        analysis_type=args.analysis_type,
        paths=args.paths,
        topology=args.topology,
        selection=args.selection,
        reference_frame=args.reference_frame,
        distance_cutoff=args.distance_cutoff,
        n_top=args.n_top,
        artifact_dir=args.artifact_dir,
        parent_artifact_ids=args.parent_artifacts,
    )

    output_json = json.dumps(results, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(output_json)
        logger.info("Results written to %s", args.output)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
