---
name: structure-prediction
description: Protein structure prediction using Chai-1 or AlphaFold with confidence scoring, quality assessment, and critic evaluation
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

Predict 3D protein structures from amino acid sequences using Chai-1 or AlphaFold backends. Includes confidence scoring, quality assessment, and an integrated critic evaluation step that flags low-quality predictions.

## Capabilities

- **Single-chain folding**: Predict monomer structures from amino acid sequences
- **Complex prediction**: Predict multi-chain protein complexes (co-folding)
- **Confidence scoring**: pLDDT, pAE, ipTM, and aggregate metrics
- **Multiple backends**: Support for Chai-1 and AlphaFold prediction engines
- **Quality assessment**: Automated critic evaluation with weighted scoring (prediction quality, analysis depth, methodology, efficiency)
- **Artifact DAG integration**: All predictions stored as immutable artifacts with full provenance

## Usage

```bash
python skills/structure-prediction/scripts/run_prediction.py \
  --sequence "MKWVTFISLLLLFSSAYSRGV..." \
  --backend chai \
  --num-models 5 \
  --output-dir ./prediction_output
```

Or with a FASTA file:

```bash
python skills/structure-prediction/scripts/run_prediction.py \
  --fasta input.fasta \
  --backend alphafold \
  --use-templates \
  --output-dir ./prediction_output
```

The skill will:

1. Parse the input sequence (raw string or FASTA file)
2. Run structure prediction with the selected backend (Chai-1 or AlphaFold)
3. Score models with confidence metrics (pLDDT, pAE, ipTM)
4. Run critic evaluation to assess prediction quality
5. Store results as artifacts in the Artifact DAG with provenance tracking

## Parameters

- `sequence`: Amino acid sequence (raw string)
- `fasta`: Path to FASTA file (alternative to `sequence`)
- `backend`: Prediction backend — "chai" or "alphafold" (default: "chai")
- `num_models`: Number of models to generate (default: 5)
- `use_templates`: Whether to use template structures (default: false)
- `device`: Compute device, e.g. "cuda:0" or "cpu" (default: "cuda:0")
- `output_dir`: Output directory for results (default: ./prediction_output)
- `artifact_store`: Path to artifact store for DAG integration
- `sequence_name`: Name for the sequence (default: "query")
- `constraints`: JSON string of folding constraints

## Quality Thresholds

- `min_confidence`: Minimum acceptable pLDDT confidence (default: 60.0)
- `high_confidence`: High-confidence threshold (default: 80.0)
- `min_coverage`: Minimum sequence coverage (default: 0.9)
- `max_clash_score`: Maximum acceptable clash score (default: 10.0)

## Critic Evaluation Weights

- `prediction_quality`: 0.30
- `analysis_depth`: 0.25
- `interpretation_accuracy`: 0.20
- `methodology`: 0.15
- `efficiency`: 0.10

## Output Artifacts

The skill produces artifacts in the Artifact DAG (Layer 3):

- `SEQUENCE` artifacts: Input sequences with metadata
- `PDB_STRUCTURE` artifacts: Predicted 3D structures with confidence scores
- `SCORE` artifacts: Per-model quality metrics (pLDDT, pAE, ipTM)
- `ANALYSIS` artifacts: Critic evaluation results with improvement suggestions
