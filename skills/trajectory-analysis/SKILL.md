---
name: trajectory-analysis
description: Analysis of molecular dynamics trajectories (RMSD, RMSF, contacts, hotspot analysis)
metadata:
  openclaw:
    requires:
      env:
        - OPENAI_API_KEY
      bins:
        - python3
      pip:
        - MDAnalysis
        - numpy
    primaryEnv: OPENAI_API_KEY
---

# Trajectory Analysis — MD Post-Processing

Analyze molecular dynamics trajectories to extract structural and dynamic
properties. Supports both static (PDB-only) and dynamic (trajectory + topology)
analysis modes.

## Capabilities

- **Static/basic**: Distance-based residue contact maps from PDB structures
- **Dynamic/basic**: RMSD, RMSF, and radius of gyration from trajectories
- **Dynamic/advanced**: Residue contact frequency (hotspot) analysis — identifies which residues interact most frequently across trajectory frames
- **Both**: Run basic + advanced together

## Analysis Modes

The skill follows the two-axis config_master schema:

| data_type | analysis_type | What it computes |
|-----------|--------------|------------------|
| static    | basic        | Contact map from PDB distance matrix |
| static    | advanced     | (reserved for future analyses) |
| dynamic   | basic        | RMSD, RMSF, radius of gyration |
| dynamic   | advanced     | Residue contact frequency / hotspots |
| dynamic   | both         | All dynamic analyses combined |

## Usage

```bash
# Static contact analysis
python skills/trajectory-analysis/scripts/run_analysis.py \
  --data-type static --analysis-type basic \
  --paths structure.pdb --distance-cutoff 4.5

# Dynamic RMSD/RMSF/RoG
python skills/trajectory-analysis/scripts/run_analysis.py \
  --data-type dynamic --analysis-type basic \
  --paths trajectory.dcd --topology system.pdb

# Dynamic hotspot analysis
python skills/trajectory-analysis/scripts/run_analysis.py \
  --data-type dynamic --analysis-type advanced \
  --paths trajectory.dcd --topology system.pdb \
  --distance-cutoff 4.5 --n-top 10

# Full dynamic analysis with artifact DAG provenance
python skills/trajectory-analysis/scripts/run_analysis.py \
  --data-type dynamic --analysis-type both \
  --paths trajectory.dcd --topology system.pdb \
  --artifact-dir ./artifacts -o results.json
```

## Parameters

- `--data-type`: `static` (PDB only) or `dynamic` (trajectory + topology)
- `--analysis-type`: `basic`, `advanced`, or `both`
- `--paths`: Trajectory file(s) (DCD, XTC, TRR) or PDB file(s)
- `--topology`: Topology file (PDB or PSF) — required for trajectory formats
- `--selection`: MDAnalysis atom selection string (default: `protein and name CA`)
- `--reference-frame`: Reference frame for RMSD alignment (default: 0)
- `--distance-cutoff`: Distance cutoff in Angstroms for contact analysis (default: 4.5)
- `--n-top`: Number of top contact pairs to report (default: 10)
- `--artifact-dir`: Directory for Artifact DAG storage (enables provenance tracking)
- `--parent-artifacts`: Parent artifact IDs for DAG lineage
- `--output` / `-o`: Output JSON file (default: stdout)

## Requirements

- **MDAnalysis** (`pip install MDAnalysis`) — trajectory I/O, RMSD/RMSF, contact analysis
- **NumPy** — numerical computations (installed with MDAnalysis)

## Artifact DAG Integration

When `--artifact-dir` is provided, the skill:
1. Starts a provenance run via `ProvenanceTracker`
2. Creates a content-addressed `Artifact` (type: `ANALYSIS`) with full results
3. Links to parent artifacts if `--parent-artifacts` are specified
4. Returns `_artifact_id` and `_run_id` in the output JSON
