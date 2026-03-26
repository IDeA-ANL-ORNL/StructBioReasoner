---
name: paper2agent
description: Convert scientific papers into executable computational workflows and MCP tools
metadata:
  openclaw:
    requires:
      env:
        - OPENAI_API_KEY
      bins:
        - python3
    primaryEnv: OPENAI_API_KEY
---

# Paper2Agent — Literature-to-Tool Conversion

Extract computational methods from scientific papers and generate executable
MCP tool specifications with verifiable reward criteria.

## Capabilities

- **Method extraction**: Parse papers to identify computational methodologies, input parameters, algorithm steps, and validation criteria
- **Reward criteria extraction**: Derive verifiable reward criteria (thermostability, structural accuracy, binding affinity, conservation) from paper content
- **MCP tool generation**: Generate MCP tool specifications with typed input/output schemas
- **Script generation**: Optionally generate runnable Python tool skeletons
- **Artifact DAG integration**: Record paper, methodology, and tool artifacts with full provenance tracking (Layer 3)
- **Domain classification**: Automatically classify papers into MD, structural, bioinformatics, or general domains

## Usage

Provide a paper (PDF, text file, or raw text). The skill extracts computational
methods and generates executable workflow configurations or scripts.

```bash
# Generate tool configs from a paper
python skills/paper2agent/scripts/run_paper2agent.py paper.txt -o output/

# Generate runnable scripts with artifact tracking
python skills/paper2agent/scripts/run_paper2agent.py paper.txt \
    --output-format script \
    --artifact-root .artifact_store

# Extract a specific method only
python skills/paper2agent/scripts/run_paper2agent.py paper.txt \
    --target-method stability_prediction
```

## Parameters

- `paper_source`: Path to paper (PDF/text file) or raw text string
- `output_dir`: Directory for output files (default: `output/paper2agent`)
- `artifact_root`: Root directory for artifact DAG storage (optional — enables provenance)
- `target_method`: Extract only a specific methodology (optional — extracts all if omitted)
- `output_format`: Output format — `config` (JSON specs, default) or `script` (runnable Python)

## Pipeline

1. **Load paper** — read PDF/text file or accept raw text
2. **Classify domain** — MD, structural biology, bioinformatics, or general
3. **Extract methodologies** — identify computational methods with inputs, outputs, algorithm steps
4. **Extract reward criteria** — derive verifiable evaluation criteria from paper content
5. **Generate MCP tool specs** — create typed tool specifications with confidence scores
6. **Record artifacts** — store paper, methodology, and tool artifacts in the DAG with parent lineage
7. **Write outputs** — JSON summary + optional generated Python scripts

## Supported Domains

| Domain | Example Methods |
|--------|----------------|
| Molecular Dynamics | MD simulation protocols, trajectory analysis |
| Structural Biology | Structure prediction, binding analysis |
| Bioinformatics | Conservation analysis, sequence alignment |
| Stability | Mutation stability prediction, thermostability |
