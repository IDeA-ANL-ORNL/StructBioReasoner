---
name: molecular-dynamics
description: Molecular dynamics simulations using OpenMM with MDAgent-style automation
metadata:
  openclaw:
    requires:
      env:
        - OPENAI_API_KEY
      bins:
        - python3
    primaryEnv: OPENAI_API_KEY
---

# Molecular Dynamics — OpenMM Simulations

Run molecular dynamics simulations on protein structures using OpenMM.

## Capabilities

- **System setup**: Prepare protein systems with solvent, ions, and force fields
- **Energy minimization**: Minimize system energy before production runs
- **Production MD**: Run NVT/NPT simulations with configurable parameters
- **Trajectory analysis**: Basic RMSD, RMSF, and contact analysis

## Usage

Provide a PDB file and simulation parameters. The skill handles system preparation,
equilibration, and production simulation.

## Parameters

- `input_pdb`: Path to input PDB structure
- `forcefield`: Force field to use (default: "amber14-all")
- `water_model`: Water model (default: "tip3p")
- `temperature_k`: Simulation temperature in Kelvin (default: 300)
- `pressure_atm`: Pressure in atm for NPT (default: 1.0)
- `simulation_steps`: Number of MD steps (default: 500000)
- `timestep_fs`: Integration timestep in femtoseconds (default: 2.0)
