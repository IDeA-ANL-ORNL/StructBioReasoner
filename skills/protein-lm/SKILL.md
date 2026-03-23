---
name: protein-lm
description: Protein language model embeddings, diversity sampling, and mutation prediction using ESM or GenSLM
metadata:
  openclaw:
    requires:
      env:
        - OPENAI_API_KEY
      bins:
        - python3
      pip:
        - torch
        - transformers
        - numpy
        - scipy
        - faiss-cpu
    primaryEnv: OPENAI_API_KEY
---

# Protein Language Model — ESM / GenSLM

Generate protein embeddings, cluster sequences for diversity sampling, and predict mutation effects using large protein language models.

## Capabilities

- **Sequence embeddings**: Dense vector representations via GenSLM-ESMc or ESM-2
- **Diversity sampling**: FAISS clustering + Boltzmann importance sampling over embedding space
- **Mutation effect prediction**: Log-likelihood ratio scoring of single-point mutations

## Scripts

### `scripts/run_embedding.py`

Compute embeddings for protein sequences from a FASTA file or inline list.

```bash
python skills/protein-lm/scripts/run_embedding.py \
  --sequences MKTL... MGSS... \
  --model esm2 \
  --output-dir ./artifacts
```

### `scripts/run_sampling.py`

Cluster pre-computed embeddings and sample representative sequences.

```bash
python skills/protein-lm/scripts/run_sampling.py \
  --embeddings-json ./artifacts/embeddings.json \
  --n-clusters 100 \
  --total-samples 500 \
  --output-dir ./artifacts
```

## Parameters

- `sequences`: Amino acid sequences (FASTA file or inline)
- `model`: Model backend — `esm2` (default) or `genslm`
- `task`: Task type — `embedding`, `sample`, `mutation_effect`
- `n_clusters`: Number of FAISS k-means clusters (default: 100)
- `total_samples`: Target number of sampled sequences (default: 500)
- `mutations`: Mutations for scoring (e.g., `A50G L100F`)
- `alpha`: Threshold ratio for mutation suggestions (default: 1.0)
