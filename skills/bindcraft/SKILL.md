---
name: bindcraft
description: Computational peptide binder design using BindCraft pipeline (ProteinMPNN inverse folding + Chai/ESMFold structure validation + energy scoring + quality control)
metadata:
  openclaw:
    requires:
      env:
        - OPENAI_API_KEY
      bins:
        - python3
      anyBins:
        - proteinmpnn
        - protein_mpnn
    primaryEnv: OPENAI_API_KEY
---

# BindCraft — Computational Peptide Binder Design

Design peptide binders for target proteins using the BindCraft pipeline. This skill orchestrates inverse folding (ProteinMPNN), structure prediction (Chai/ESMFold), energy scoring, and sequence quality control in an iterative refinement loop.

## Capabilities

- **Inverse folding (ProteinMPNN)**: Design amino acid sequences for binder backbones using ProteinMPNN with configurable sampling temperature, batch size, and model weights
- **Structure prediction (Chai)**: Validate designed sequences by folding target+binder complexes and evaluating structural metrics (pAE, ipTM, pLDDT)
- **Energy scoring**: Score folded complexes using a simplified energy function to rank binder candidates
- **Sequence quality control**: Filter sequences based on repeat content, charge, hydrophobicity, diversity, and problematic motifs
- **Iterative refinement**: Run multiple rounds of design→fold→score→filter to converge on high-quality binders

## Usage

```bash
python skills/bindcraft/scripts/run_bindcraft.py \
  --target-sequence "MKWVTFISLLLLFSSAYSRGV..." \
  --binder-sequence "MKQHKAMIVALIVICITAVVAALVTRKDLCEVHIRTGQTEVAVF" \
  --num-rounds 3 \
  --num-seq 25 \
  --output-dir ./bindcraft_output
```

Provide a target protein sequence and an initial binder scaffold sequence. The skill will:

1. Run ProteinMPNN inverse folding to generate candidate binder sequences
2. Filter sequences through quality control checks
3. Fold target+binder complexes with Chai structure prediction
4. Score complexes with energy function
5. Repeat for N rounds, refining the best candidates

## Parameters

- `target_sequence` (required): Amino acid sequence of the target protein
- `binder_sequence`: Initial binder scaffold sequence (default: standard test peptide)
- `num_rounds`: Number of design-fold-score rounds (default: 3)
- `num_seq`: Number of sequences per ProteinMPNN batch (default: 25)
- `batch_size`: ProteinMPNN batch size (default: 250)
- `sampling_temp`: ProteinMPNN sampling temperature (default: 0.1)
- `device`: Compute device, e.g. "cuda:0" or "cpu" (default: cuda:0)
- `output_dir`: Output directory for results and artifacts
- `artifact_store`: Path to artifact store for DAG integration
- `constraints`: JSON string of binding constraints (e.g. `{"residues_bind": ["R45", "K78"]}`)

## Quality Control Defaults

- `max_repeat`: Maximum consecutive repeat length (default: 4)
- `max_appearance_ratio`: Maximum single-residue frequency (default: 0.33)
- `max_charge`: Maximum net charge (default: 5)
- `max_charge_ratio`: Maximum charged residue fraction (default: 0.5)
- `max_hydrophobic_ratio`: Maximum hydrophobic fraction (default: 0.8)
- `min_diversity`: Minimum unique residue types (default: 8)

## Output Artifacts

The skill produces artifacts in the Artifact DAG (Layer 3):

- `SEQUENCE` artifacts: Designed binder sequences from ProteinMPNN
- `STRUCTURE` artifacts: Folded complex structures from Chai
- `SCORE` artifacts: Energy scores and QC metrics for each design
- `SCORE_TABLE` artifacts: Summary table of all designs ranked by energy
