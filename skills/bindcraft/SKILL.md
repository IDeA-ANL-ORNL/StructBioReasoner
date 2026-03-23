---
name: bindcraft
description: Computational peptide binder design using BindCraft pipeline (RFdiffusion + ProteinMPNN + folding validation)
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

Design peptide binders for target proteins using the BindCraft pipeline.

## Capabilities

- **RFdiffusion backbone generation**: Generate binder backbone structures conditioned on a target protein
- **ProteinMPNN sequence design**: Design amino acid sequences for generated backbones
- **Folding validation**: Validate designs using structure prediction (AlphaFold/Chai)
- **Iterative refinement**: Filter and refine designs based on binding metrics (pAE, ipTM, pLDDT)

## Usage

Provide a target PDB file and specify the target chain/residues for binder design. The skill will:

1. Generate backbone candidates via RFdiffusion
2. Design sequences with ProteinMPNN
3. Validate via structure prediction
4. Score and rank results

## Parameters

- `target_pdb`: Path to target protein PDB file
- `target_chain`: Chain identifier for the binding target
- `target_residues`: Residue range to target (e.g., "10-50")
- `num_designs`: Number of binder candidates to generate (default: 10)
- `binder_length`: Length range for binder peptide (e.g., "30-50")
