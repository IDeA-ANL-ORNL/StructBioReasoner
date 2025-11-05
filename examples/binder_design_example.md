# Binder Design Reasoner Examples

This document provides examples of how to use the `binder_design_reasoner.py` script for designing protein binders.

## Overview

The Binder Design Reasoner is a specialized system built on top of Jnana that focuses on:
- Computational binder design using BindCraft
- Molecular dynamics validation using MDAgent
- Energetic analysis of binder-target complexes
- Hypothesis generation and ranking for binder optimization

## Prerequisites

1. **Install StructBioReasoner** with binder design dependencies
2. **Configure BindCraft** (ProteinMPNN, structure prediction backend)
3. **Optional**: Install MDAgent for MD simulations
4. **Optional**: Configure AmberTools for explicit solvent simulations

## Basic Usage

### 1. Interactive Mode

Start an interactive session for binder design:

```bash
python binder_design_reasoner.py --mode interactive
```

You'll be prompted to enter your research goal, and then you can interactively:
- Generate binder design hypotheses
- Refine designs based on feedback
- Validate designs with MD simulations
- Compare and rank different binder candidates

### 2. Batch Mode

Generate multiple binder design hypotheses automatically:

```bash
python binder_design_reasoner.py \
  --mode batch \
  --goal "Design a high-affinity binder for SARS-CoV-2 spike protein" \
  --count 10 \
  --strategies computational_design molecular_dynamics
```

This will:
1. Generate 10 binder design hypotheses
2. Use computational design (BindCraft) and MD simulation strategies
3. Automatically rank the designs
4. Save results to the output directory

### 3. Hybrid Mode

Combine automated generation with interactive refinement:

```bash
python binder_design_reasoner.py \
  --mode hybrid \
  --goal "Optimize binder stability and affinity" \
  --count 5 \
  --interactive-refinement \
  --tournament-matches 25
```

## Advanced Examples

### Example 1: Design Binders with Specific Sequences

```bash
python binder_design_reasoner.py \
  --mode batch \
  --goal "Design binders for target protein" \
  --target-sequence "MSTGEELQK" \
  --binder-sequence "MKQHKAMIVALIVICITAVVAALVTRKDLCEVHIRTGQTEVAVF" \
  --count 5 \
  --n-rounds 3 \
  --device cuda:0
```

### Example 2: Design with Custom Configuration

```bash
python binder_design_reasoner.py \
  --mode batch \
  --goal "Design thermostable binders" \
  --config config/binder_config.yaml \
  --enable-agents computational_design molecular_dynamics energetic_analysis \
  --count 10 \
  --output ./results/thermostable_binders
```

### Example 3: Quick Design with Implicit Solvent

For faster iterations without AmberTools:

```bash
python binder_design_reasoner.py \
  --mode batch \
  --goal "Rapid binder design screening" \
  --count 20 \
  --strategies computational_design \
  --log-level DEBUG \
  --log-file binder_design.log
```

### Example 4: Full Pipeline with Validation

```bash
python binder_design_reasoner.py \
  --mode hybrid \
  --goal "Design and validate high-affinity binders" \
  --target "P0DTC2" \
  --count 10 \
  --strategies computational_design molecular_dynamics energetic_analysis \
  --tournament-matches 50 \
  --interactive-refinement \
  --enable-visualization \
  --output ./results/validated_binders
```

## Configuration Options

### Key Command-Line Arguments

- `--mode`: Operation mode (interactive, batch, hybrid, status)
- `--goal`: Research goal or design objective
- `--target`: Target protein ID (PDB, UniProt, etc.)
- `--target-sequence`: Target protein sequence
- `--binder-sequence`: Initial binder sequence (optional)
- `--count`: Number of hypotheses to generate
- `--strategies`: Design strategies to use
- `--n-rounds`: Number of design rounds (default: 3)
- `--device`: Computation device (default: cuda:0)
- `--config`: Configuration file path
- `--output`: Output directory for results

### Available Strategies

1. **computational_design**: BindCraft-based binder design
2. **molecular_dynamics**: MD simulation validation
3. **energetic_analysis**: Binding affinity and stability analysis

## Output

The system generates:

1. **Hypothesis Files**: JSON files with design hypotheses
2. **Structure Files**: PDB files of designed binders
3. **Analysis Reports**: MD simulation results, energy calculations
4. **Rankings**: Tournament-based ranking of designs
5. **Logs**: Detailed execution logs

## System Status

Check system status and available tools:

```bash
python binder_design_reasoner.py --mode status
```

This shows:
- Jnana availability
- Tool availability (PyMOL, BioPython, OpenMM, etc.)
- Agent status
- Configuration summary

## Tips and Best Practices

### 1. Start with Implicit Solvent
For initial screening, use implicit solvent MD (faster, no AmberTools needed):
- Edit `config/binder_config.yaml`
- Set `agents.molecular_dynamics.mdagent.solvent_model: "implicit"`

### 2. Use Batch Mode for Exploration
Generate many designs in batch mode, then refine the best ones interactively.

### 3. Leverage Tournament Ranking
Increase `--tournament-matches` for more robust ranking (but slower).

### 4. Monitor GPU Usage
Use `nvidia-smi` to monitor GPU utilization during design and MD simulations.

### 5. Save Intermediate Results
Always specify `--output` to save results for later analysis.

## Troubleshooting

### Issue: "leap.log not found"
**Solution**: Install AmberTools OR use implicit solvent:
```bash
conda install -c conda-forge ambertools
```

### Issue: "BindCraft not configured"
**Solution**: Update `config/binder_config.yaml` with correct ProteinMPNN path:
```yaml
agents:
  computational_design:
    bindcraft:
      proteinmpnn_path: "/path/to/ProteinMPNN"
```

### Issue: "CUDA out of memory"
**Solution**: Reduce batch size or use CPU:
```bash
python binder_design_reasoner.py --device cpu ...
```

## Next Steps

1. Review generated hypotheses in the output directory
2. Visualize top-ranked binders with PyMOL
3. Export sequences for experimental validation
4. Iterate on designs based on experimental feedback

## Example Workflow

```bash
# 1. Check system status
python binder_design_reasoner.py --mode status

# 2. Generate initial designs
python binder_design_reasoner.py \
  --mode batch \
  --goal "Design binders for target X" \
  --target-sequence "MSTGEELQK" \
  --count 20 \
  --output ./results/round1

# 3. Refine top candidates
python binder_design_reasoner.py \
  --mode hybrid \
  --goal "Optimize top 5 binders from round 1" \
  --count 5 \
  --strategies computational_design molecular_dynamics energetic_analysis \
  --interactive-refinement \
  --output ./results/round2

# 4. Final validation
python binder_design_reasoner.py \
  --mode batch \
  --goal "Validate final binder candidates" \
  --strategies molecular_dynamics energetic_analysis \
  --count 3 \
  --tournament-matches 100 \
  --output ./results/final
```

## References

- BindCraft: [GitHub](https://github.com/martinpacesa/BindCraft)
- MDAgent: [GitHub](https://github.com/ur-whitelab/md-agent)
- Jnana: [Documentation](../Jnana/README.md)
- StructBioReasoner: [Main README](../README.md)

