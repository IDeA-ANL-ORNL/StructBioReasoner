#!/usr/bin/env python3
"""
Evolutionary conservation analysis using MUSCLE multiple sequence alignment.

Wraps MUSCLE alignment and computes per-residue conservation scores from the
resulting MSA.  Integrates with the Artifact DAG (Layer 3) for provenance.

Ported from:
  - evolution branch: struct_bio_reasoner/tools/muscle_wrapper.py
  - evolution branch: struct_bio_reasoner/agents/evolutionary/conservation_agent.py
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Artifact DAG integration (Layer 3)
# ---------------------------------------------------------------------------
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_SKILLS_DIR))

from _shared.artifact import ArtifactMetadata, ArtifactType, create_artifact
from _shared.artifact_store import ArtifactStore
from _shared.provenance import ProvenanceTracker

logger = logging.getLogger(__name__)

SKILL_NAME = "evolutionary-conservation"
SKILL_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# MUSCLE wrapper (ported from evolution branch muscle_wrapper.py)
# ---------------------------------------------------------------------------

def _find_muscle() -> str:
    """Locate a MUSCLE executable on PATH."""
    for name in ("muscle", "muscle5"):
        path = shutil.which(name)
        if path:
            return path
    raise FileNotFoundError(
        "MUSCLE executable not found. Install MUSCLE v5 and ensure "
        "'muscle' or 'muscle5' is on your PATH."
    )


def run_muscle(
    input_fasta: Path,
    output_fasta: Path,
    muscle_bin: Optional[str] = None,
) -> Path:
    """Run MUSCLE to produce a multiple sequence alignment.

    Args:
        input_fasta: Path to an unaligned FASTA file.
        output_fasta: Where to write the aligned FASTA.
        muscle_bin: Explicit path to muscle binary (auto-detected if *None*).

    Returns:
        *output_fasta* on success.

    Raises:
        FileNotFoundError: MUSCLE binary not found.
        subprocess.CalledProcessError: MUSCLE returned non-zero exit code.
    """
    exe = muscle_bin or _find_muscle()
    cmd = [exe, "-align", str(input_fasta), "-output", str(output_fasta)]
    logger.info("Running MUSCLE: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    logger.info("MUSCLE alignment written to %s", output_fasta)
    return output_fasta


# ---------------------------------------------------------------------------
# FASTA helpers
# ---------------------------------------------------------------------------

def read_fasta(path: Path) -> List[Tuple[str, str]]:
    """Parse a FASTA file into a list of (header, sequence) tuples."""
    records: List[Tuple[str, str]] = []
    header = ""
    seq_parts: List[str] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if header:
                records.append((header, "".join(seq_parts)))
            header = line[1:].strip()
            seq_parts = []
        else:
            seq_parts.append(line)
    if header:
        records.append((header, "".join(seq_parts)))
    return records


def write_fasta(records: Sequence[Tuple[str, str]], path: Path) -> Path:
    """Write (header, sequence) tuples to a FASTA file."""
    with path.open("w") as fh:
        for header, seq in records:
            fh.write(f">{header}\n{seq}\n")
    return path


def sequences_to_fasta(sequences: List[str], path: Path) -> Path:
    """Write bare sequences (no headers) to a FASTA file with auto-headers."""
    records = [(f"seq_{i}", seq) for i, seq in enumerate(sequences)]
    return write_fasta(records, path)


# ---------------------------------------------------------------------------
# Conservation scoring
# ---------------------------------------------------------------------------

_STANDARD_AA = set("ACDEFGHIKLMNPQRSTVWY")


def shannon_entropy(column: str) -> float:
    """Shannon entropy of a single MSA column (ignoring gaps)."""
    residues = [c for c in column.upper() if c in _STANDARD_AA]
    n = len(residues)
    if n == 0:
        return 0.0
    freq: Dict[str, int] = {}
    for r in residues:
        freq[r] = freq.get(r, 0) + 1
    entropy = 0.0
    for count in freq.values():
        p = count / n
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def conservation_scores_shannon(
    aligned_sequences: List[str],
) -> List[float]:
    """Compute per-column conservation scores from aligned sequences.

    Returns a list of scores in [0, 1] where 1 = perfectly conserved.
    The score is ``1 - H / H_max`` where *H* is Shannon entropy and
    *H_max = log2(20)*.
    """
    if not aligned_sequences:
        return []
    length = len(aligned_sequences[0])
    h_max = math.log2(20)  # max entropy for 20 amino acids
    scores: List[float] = []
    for col_idx in range(length):
        column = "".join(seq[col_idx] for seq in aligned_sequences if col_idx < len(seq))
        h = shannon_entropy(column)
        scores.append(max(0.0, 1.0 - h / h_max))
    return scores


def _property_group(aa: str) -> int:
    """Map amino acid to a physicochemical property group (Taylor 1986)."""
    groups = {
        "G": 0, "A": 0, "V": 0, "L": 0, "I": 0, "P": 0,  # small/hydrophobic
        "F": 1, "W": 1, "Y": 1,                              # aromatic
        "D": 2, "E": 2,                                       # acidic
        "R": 3, "K": 3, "H": 3,                              # basic
        "S": 4, "T": 4, "N": 4, "Q": 4, "C": 4, "M": 4,    # polar/neutral
    }
    return groups.get(aa.upper(), -1)


def conservation_scores_property(
    aligned_sequences: List[str],
) -> List[float]:
    """Property-based conservation: fraction of sequences sharing the
    dominant physicochemical group at each position."""
    if not aligned_sequences:
        return []
    length = len(aligned_sequences[0])
    scores: List[float] = []
    for col_idx in range(length):
        groups: Dict[int, int] = {}
        total = 0
        for seq in aligned_sequences:
            if col_idx >= len(seq):
                continue
            aa = seq[col_idx].upper()
            if aa not in _STANDARD_AA:
                continue
            g = _property_group(aa)
            if g >= 0:
                groups[g] = groups.get(g, 0) + 1
                total += 1
        if total == 0:
            scores.append(0.0)
        else:
            scores.append(max(groups.values()) / total)
    return scores


def identify_conserved_regions(
    scores: List[float],
    threshold: float = 0.8,
    min_length: int = 3,
) -> List[Dict[str, Any]]:
    """Find contiguous regions where conservation exceeds *threshold*."""
    regions: List[Dict[str, Any]] = []
    start: Optional[int] = None
    for i, s in enumerate(scores):
        if s >= threshold:
            if start is None:
                start = i
        else:
            if start is not None and (i - start) >= min_length:
                region_scores = scores[start:i]
                regions.append({
                    "start": start + 1,  # 1-based
                    "end": i,            # 1-based inclusive
                    "length": i - start,
                    "mean_score": sum(region_scores) / len(region_scores),
                })
            start = None
    # handle region at end
    if start is not None and (len(scores) - start) >= min_length:
        region_scores = scores[start:]
        regions.append({
            "start": start + 1,
            "end": len(scores),
            "length": len(scores) - start,
            "mean_score": sum(region_scores) / len(region_scores),
        })
    return regions


# ---------------------------------------------------------------------------
# Main analysis pipeline
# ---------------------------------------------------------------------------

def run_conservation_analysis(
    *,
    input_fasta: Optional[Path] = None,
    sequences: Optional[List[str]] = None,
    output_dir: Path,
    method: str = "shannon",
    conserved_threshold: float = 0.8,
    min_region_length: int = 3,
    muscle_bin: Optional[str] = None,
    artifact_store_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """End-to-end conservation analysis.

    Either *input_fasta* (path to an unaligned FASTA) or *sequences* (list of
    bare sequence strings) must be provided.

    Returns a results dict with alignment path, scores, and conserved regions.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Prepare input FASTA ---
    if input_fasta is not None:
        src_fasta = input_fasta
    elif sequences:
        src_fasta = output_dir / "input_sequences.fasta"
        sequences_to_fasta(sequences, src_fasta)
    else:
        raise ValueError("Provide either --input-fasta or --sequences")

    # --- Provenance ---
    store: Optional[ArtifactStore] = None
    tracker: Optional[ProvenanceTracker] = None
    run_id: Optional[str] = None
    if artifact_store_root:
        store = ArtifactStore(artifact_store_root)
        tracker = ProvenanceTracker(artifact_store_root)
        prov = tracker.start_run(
            skill_name=SKILL_NAME,
            skill_version=SKILL_VERSION,
            parameters={
                "method": method,
                "conserved_threshold": conserved_threshold,
                "min_region_length": min_region_length,
                "input_fasta": str(src_fasta),
            },
        )
        run_id = prov.run_id

    # --- Run MUSCLE ---
    msa_path = output_dir / "alignment.fasta"
    run_muscle(src_fasta, msa_path, muscle_bin=muscle_bin)

    # --- Parse alignment ---
    aligned = read_fasta(msa_path)
    aligned_seqs = [seq for _, seq in aligned]
    headers = [hdr for hdr, _ in aligned]

    # --- Score conservation ---
    if method == "property":
        scores = conservation_scores_property(aligned_seqs)
    else:
        scores = conservation_scores_shannon(aligned_seqs)

    # --- Identify conserved regions ---
    regions = identify_conserved_regions(
        scores,
        threshold=conserved_threshold,
        min_length=min_region_length,
    )

    # --- Build results ---
    results: Dict[str, Any] = {
        "alignment_file": str(msa_path),
        "num_sequences": len(aligned),
        "alignment_length": len(aligned_seqs[0]) if aligned_seqs else 0,
        "method": method,
        "conservation_scores": [round(s, 4) for s in scores],
        "conserved_regions": regions,
        "conserved_threshold": conserved_threshold,
        "sequence_headers": headers,
    }

    # --- Write JSON output ---
    results_path = output_dir / "conservation_results.json"
    results_path.write_text(json.dumps(results, indent=2))
    logger.info("Results written to %s", results_path)

    # --- Store artifacts ---
    output_artifact_ids: List[str] = []
    if store is not None:
        # Alignment artifact
        alignment_art = create_artifact(
            metadata=ArtifactMetadata(
                artifact_type=ArtifactType.ALIGNMENT,
                skill_name=SKILL_NAME,
                skill_version=SKILL_VERSION,
                tags=frozenset({"msa", "muscle"}),
            ),
            data={
                "alignment_file": str(msa_path),
                "num_sequences": len(aligned),
                "alignment_length": len(aligned_seqs[0]) if aligned_seqs else 0,
            },
            run_id=run_id,
        )
        store.put(alignment_art)
        output_artifact_ids.append(alignment_art.artifact_id)

        # Conservation scores artifact
        scores_art = create_artifact(
            parent_ids=(alignment_art.artifact_id,),
            metadata=ArtifactMetadata(
                artifact_type=ArtifactType.SCORE_TABLE,
                skill_name=SKILL_NAME,
                skill_version=SKILL_VERSION,
                tags=frozenset({"conservation", method}),
            ),
            data={
                "method": method,
                "scores": [round(s, 4) for s in scores],
                "conserved_regions": regions,
            },
            run_id=run_id,
        )
        store.put(scores_art)
        output_artifact_ids.append(scores_art.artifact_id)

    if tracker is not None and run_id is not None:
        tracker.finish_run(
            run_id=run_id,
            output_artifact_ids=output_artifact_ids,
            status="success",
        )

    results["artifact_ids"] = output_artifact_ids
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_conservation",
        description=(
            "Evolutionary conservation analysis using MUSCLE alignment. "
            "Aligns input sequences, computes per-residue conservation "
            "scores, and identifies conserved regions."
        ),
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input-fasta",
        type=Path,
        help="Path to an unaligned FASTA file of homologous sequences.",
    )
    input_group.add_argument(
        "--sequences",
        nargs="+",
        help="Bare protein sequences to align (space-separated).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("conservation_output"),
        help="Directory for output files (default: conservation_output).",
    )
    parser.add_argument(
        "--method",
        choices=["shannon", "property"],
        default="shannon",
        help="Conservation scoring method (default: shannon).",
    )
    parser.add_argument(
        "--conserved-threshold",
        type=float,
        default=0.8,
        help="Score threshold for identifying conserved regions (default: 0.8).",
    )
    parser.add_argument(
        "--min-region-length",
        type=int,
        default=3,
        help="Minimum length for a conserved region (default: 3).",
    )
    parser.add_argument(
        "--muscle-bin",
        type=str,
        default=None,
        help="Path to MUSCLE executable (auto-detected if omitted).",
    )
    parser.add_argument(
        "--artifact-store",
        type=Path,
        default=None,
        help="Root directory for artifact DAG storage (optional).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results = run_conservation_analysis(
        input_fasta=args.input_fasta,
        sequences=args.sequences,
        output_dir=args.output_dir,
        method=args.method,
        conserved_threshold=args.conserved_threshold,
        min_region_length=args.min_region_length,
        muscle_bin=args.muscle_bin,
        artifact_store_root=args.artifact_store,
    )

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
