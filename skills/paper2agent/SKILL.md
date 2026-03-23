---
name: paper2agent
description: Convert scientific papers into executable computational workflows
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

Extract computational methods from scientific papers and generate executable workflows.

## Capabilities

- **Method extraction**: Parse papers to identify computational methods and parameters
- **Workflow generation**: Generate runnable scripts from extracted methods
- **Parameter mapping**: Map paper parameters to tool configurations
- **Reproducibility**: Create reproducible workflows from published results

## Usage

Provide a paper (PDF, DOI, or URL). The skill extracts computational methods
and generates executable workflow configurations.

## Parameters

- `paper_source`: DOI, URL, or path to PDF file
- `target_method`: Specific method to extract (optional — extracts all if omitted)
- `output_format`: Output format — "script" or "config" (default: "config")
