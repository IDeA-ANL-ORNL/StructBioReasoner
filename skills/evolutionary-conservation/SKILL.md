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

**Requires:** MUSCLE v5 binary (`muscle` or `muscle5`) on PATH.

## Capabilities

- **MSA generation**: Align homologous sequences using MUSCLE v5
- **Conservation scoring**: Per-residue conservation scores (Shannon entropy or property-based)
- **Conserved region detection**: Identify contiguous highly-conserved regions
- **Artifact DAG integration**: Results stored with full provenance tracking

## Usage

```bash
# From a FASTA file of homologous sequences
python skills/evolutionary-conservation/scripts/run_conservation.py \
    --input-fasta sequences.fasta --output-dir results/

# From bare sequences
python skills/evolutionary-conservation/scripts/run_conservation.py \
    --sequences MTEYKLVV... MTEYKLVVV... --output-dir results/

# With artifact DAG tracking
python skills/evolutionary-conservation/scripts/run_conservation.py \
    --input-fasta sequences.fasta --output-dir results/ \
    --artifact-store ./artifact_store
```

## Parameters

- `--input-fasta`: Path to unaligned FASTA file (mutually exclusive with `--sequences`)
- `--sequences`: Bare protein sequences to align (space-separated)
- `--output-dir`: Directory for output files (default: `conservation_output`)
- `--method`: Scoring method — `shannon` or `property` (default: `shannon`)
- `--conserved-threshold`: Score threshold for conserved regions (default: 0.8)
- `--min-region-length`: Minimum contiguous length for a conserved region (default: 3)
- `--muscle-bin`: Explicit path to MUSCLE binary (auto-detected if omitted)
- `--artifact-store`: Root directory for artifact DAG storage (optional)
