---
name: trajectory-analysis
description: Analysis of molecular dynamics trajectories (RMSD, RMSF, clustering, contacts)
metadata:
  openclaw:
    requires:
      env:
        - OPENAI_API_KEY
      bins:
        - python3
    primaryEnv: OPENAI_API_KEY
---

# Trajectory Analysis — MD Post-Processing

Analyze molecular dynamics trajectories to extract structural and dynamic properties.

## Capabilities

- **RMSD/RMSF**: Root-mean-square deviation and fluctuation analysis
- **Clustering**: Structural clustering of trajectory frames
- **Contact analysis**: Residue contact maps and interaction frequencies
- **Free energy landscapes**: 2D free energy surface projections

## Usage

Provide a trajectory file and topology. The skill computes the requested
analysis metrics.

## Parameters

- `trajectory`: Path to trajectory file (DCD, XTC, or TRR)
- `topology`: Path to topology file (PDB or PSF)
- `analysis_type`: Analysis to perform — "rmsd", "rmsf", "cluster", "contacts", "free_energy"
- `selection`: Atom selection string (default: "protein and name CA")
- `reference_frame`: Reference frame for RMSD (default: 0)
