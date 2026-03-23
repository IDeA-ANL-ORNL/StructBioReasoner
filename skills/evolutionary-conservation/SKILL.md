---
name: evolutionary-conservation
description: Multiple sequence alignment and conservation analysis using MUSCLE
metadata:
  openclaw:
    requires:
      env:
        - OPENAI_API_KEY
      bins:
        - python3
      anyBins:
        - muscle
        - muscle5
    primaryEnv: OPENAI_API_KEY
---

# Evolutionary Conservation — MUSCLE Alignment

Analyze evolutionary conservation of protein sequences using multiple sequence alignment.

## Capabilities

- **MSA generation**: Align homologous sequences using MUSCLE
- **Conservation scoring**: Per-residue conservation scores
- **Functional site prediction**: Identify conserved functional regions
- **Phylogenetic analysis**: Basic phylogenetic tree construction

## Usage

Provide a protein sequence or UniProt ID. The skill retrieves homologs,
performs alignment, and computes conservation scores.

## Parameters

- `sequence`: Protein sequence or UniProt accession ID
- `num_homologs`: Number of homologs to retrieve (default: 100)
- `database`: Sequence database — "uniref90" or "nr" (default: "uniref90")
- `conservation_method`: Scoring method — "shannon" or "property" (default: "shannon")
