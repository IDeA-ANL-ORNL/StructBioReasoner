---
name: structure-prediction
description: Protein structure prediction using Chai-1 or AlphaFold
metadata:
  openclaw:
    requires:
      env:
        - OPENAI_API_KEY
      bins:
        - python3
      anyBins:
        - chai
        - alphafold
    primaryEnv: OPENAI_API_KEY
---

# Structure Prediction — Chai-1 / AlphaFold

Predict 3D protein structures from amino acid sequences.

## Capabilities

- **Single-chain folding**: Predict monomer structures
- **Complex prediction**: Predict multi-chain protein complexes
- **Confidence scoring**: pLDDT, pAE, and ipTM metrics
- **Multiple models**: Support for Chai-1 and AlphaFold backends

## Usage

Provide a protein sequence (FASTA format or raw string) and optionally specify
the prediction backend.

## Parameters

- `sequence`: Amino acid sequence or path to FASTA file
- `backend`: Prediction backend — "chai" or "alphafold" (default: "chai")
- `num_models`: Number of models to generate (default: 5)
- `use_templates`: Whether to use template structures (default: true)
