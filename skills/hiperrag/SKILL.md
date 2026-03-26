---
name: hiperrag
description: HPC-scale literature mining and retrieval-augmented generation for structural biology
metadata:
  openclaw:
    requires:
      env:
        - OPENAI_API_KEY
      bins:
        - python3
    primaryEnv: OPENAI_API_KEY
---

# HiPerRAG — Literature Mining

Search and synthesize structural biology literature at scale using HiPerRAG.

## Capabilities

- **Literature search**: Query PubMed, bioRxiv, and local document stores via RAG retrieval
- **RAG synthesis**: Generate evidence-based summaries from retrieved papers
- **Target identification**: Identify druggable targets and interacting proteins from literature evidence
- **Binder discovery**: Find starting scaffolds and binder sequences from clinical/literature evidence
- **Evidence ranking**: Score and rank evidence quality with hallmark scoring

## Prompt Modes

- `interactome`: Identify interacting proteins, pathways, and therapeutic rationales for a target protein
- `binder_design`: Find starting binder sequences and scaffolds for BindCraft optimization

## Usage

```bash
python skills/hiperrag/scripts/run_rag.py \
  --query "Identify interacting proteins for KRAS" \
  --target-protein KRAS \
  --prompt-type interactome \
  --output-dir ./artifacts
```

## Parameters

- `query` (required): Research question or protein target
- `target_protein` (required): Target protein name (e.g., KRAS, TP53)
- `prompt_type`: Prompt mode — `interactome` or `binder_design` (default: `interactome`)
- `generator`: LLM backend — `openai`, `vllm`, or `argo` (default: `openai`)
- `model`: Model name for the generator (default: `gpt-4o`)
- `retrieval_top_k`: Number of documents to retrieve (default: 200)
- `output_dir`: Directory for artifact storage (default: `./artifacts`)
- `rag_config`: Path to a YAML/JSON RAG config file (optional, overrides CLI flags)
