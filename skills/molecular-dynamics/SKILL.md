---
name: molecular-dynamics
description: Molecular dynamics simulations using OpenMM with MDAgent-style automation and free energy calculations via MM-PBSA
metadata:
  openclaw:
    requires:
      env:
        - OPENAI_API_KEY
      bins:
        - python3
      anyBins:
        - gmx
        - cpptraj
    primaryEnv: OPENAI_API_KEY
---

# Molecular Dynamics — OpenMM Simulations

Run molecular dynamics simulations on protein structures using OpenMM and calculate
binding free energies via MM-PBSA.

## Capabilities

- **System setup**: Prepare protein systems with solvent, ions, and force fields (AMBER14/CHARMM36)
- **Energy minimization**: Minimize system energy before production runs
- **Production MD**: Run NVT/NPT simulations with configurable parameters
- **Free energy calculations**: MM-PBSA binding free energy via AmberTools/cpptraj
- **Trajectory analysis**: Basic RMSD, RMSF, and contact analysis (see trajectory-analysis skill for advanced)

## Scripts

### `scripts/run_md.py` — MD simulation launcher

Wraps the MDAgent/OpenMM simulation pipeline. Accepts a PDB input, builds the system
(implicit or explicit solvent), runs equilibration and production MD, and records
artifacts to the Artifact DAG for provenance tracking.

```bash
python skills/molecular-dynamics/scripts/run_md.py \
  --input-pdb structure.pdb \
  --output-dir results/ \
  --forcefield amber14-all \
  --water-model tip3p \
  --temperature 300 \
  --pressure 1.0 \
  --equil-steps 10000 \
  --prod-steps 500000 \
  --solvent explicit \
  --platform CUDA
```

### `scripts/run_free_energy.py` — MM-PBSA free energy calculation

Runs MM-PBSA binding free energy calculations on completed MD trajectories.
Requires AmberTools (cpptraj) and a production trajectory with topology.

```bash
python skills/molecular-dynamics/scripts/run_free_energy.py \
  --sim-dir trajectory_dir/ \
  --output-dir fe_results/ \
  --n-cpus 4 \
  --amberhome /path/to/amber
```

## Parameters

### MD Simulation
- `input_pdb`: Path to input PDB structure
- `forcefield`: Force field to use (default: "amber14-all")
- `water_model`: Water model (default: "tip3p")
- `temperature_k`: Simulation temperature in Kelvin (default: 300)
- `pressure_atm`: Pressure in atm for NPT (default: 1.0)
- `equil_steps`: Equilibration steps (default: 10000)
- `prod_steps`: Production MD steps (default: 500000)
- `timestep_fs`: Integration timestep in femtoseconds (default: 2.0)
- `solvent`: Solvent model — "explicit" or "implicit" (default: "explicit")
- `platform`: OpenMM platform — "CUDA", "OpenCL", or "CPU" (default: "CUDA")

### Free Energy (MM-PBSA)
- `sim_dir`: Directory containing production trajectory (prod.dcd + system.prmtop)
- `n_cpus`: Number of CPUs for parallel MM-PBSA (default: 4)
- `amberhome`: Path to AmberTools installation

## Requirements

- **OpenMM** (`openmm`): MD simulation engine
- **MDAnalysis** (`MDAnalysis`): Trajectory I/O and atom selection
- **AmberTools** (`cpptraj`): MM-PBSA free energy calculations
- **MDAgent** (optional): Academy-based MD orchestration agents
- **Academy** (optional): Distributed agent execution (Layer 4)
