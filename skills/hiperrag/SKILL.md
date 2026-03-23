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

- **Literature search**: Query PubMed, bioRxiv, and local document stores
- **RAG synthesis**: Generate evidence-based summaries from retrieved papers
- **Target identification**: Identify druggable targets from literature evidence
- **Evidence ranking**: Score and rank evidence quality

## Usage

Provide a research question or protein target. The skill retrieves relevant
literature and synthesizes findings.

## Parameters

- `query`: Research question or protein name
- `max_papers`: Maximum papers to retrieve (default: 50)
- `sources`: Data sources to search (default: ["pubmed", "biorxiv"])
- `synthesis_mode`: "summary" or "evidence_table" (default: "summary")
