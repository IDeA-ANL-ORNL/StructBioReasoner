---
name: protein-lm
description: Protein language model embeddings and predictions using ESM or GenSLM
metadata:
  openclaw:
    requires:
      env:
        - OPENAI_API_KEY
      bins:
        - python3
    primaryEnv: OPENAI_API_KEY
---

# Protein Language Model — ESM / GenSLM

Generate protein embeddings and property predictions using large protein language models.

## Capabilities

- **Sequence embeddings**: Dense vector representations of protein sequences
- **Mutation effect prediction**: Predict functional impact of mutations
- **Contact prediction**: Predict residue-residue contacts from sequence
- **Property prediction**: Predict solubility, stability, and function

## Usage

Provide a protein sequence. The skill computes embeddings and predictions
using the selected protein language model.

## Parameters

- `sequence`: Amino acid sequence
- `model`: Model to use — "esm2" or "genslm" (default: "esm2")
- `task`: Task type — "embedding", "mutation_effect", "contact", "property" (default: "embedding")
- `mutations`: List of mutations for mutation_effect task (e.g., ["A50G", "L100F"])
