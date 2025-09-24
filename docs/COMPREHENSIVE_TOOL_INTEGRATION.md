# Comprehensive Tool Integration Guide

## Overview

StructBioReasoner now integrates six major computational tools for protein engineering, providing a comprehensive platform that combines AI-powered hypothesis generation with physics-based validation and experimental design guidance.

## Integrated Tools

### 1. **RFDiffusion3** - Generative Protein Design
- **Purpose**: De novo protein structure generation and design
- **Capabilities**:
  - De novo protein design from scratch
  - Motif scaffolding (designing proteins around functional motifs)
  - Protein-protein interaction design
  - Structure optimization and refinement
- **Agent**: `RFDiffusionAgent`
- **Wrapper**: `RFDiffusionWrapper`
- **Status**: Optional (requires separate installation)

### 2. **Rosetta** - Computational Protein Design
- **Purpose**: Physics-based protein modeling and design
- **Capabilities**:
  - Energy-based structure scoring and optimization
  - Protein stability enhancement
  - Loop modeling and design
  - Protein-protein interface optimization
- **Agent**: `RosettaAgent`
- **Wrapper**: `RosettaWrapper`
- **Status**: Optional (requires license and installation)

### 3. **AlphaFold** - Structure Prediction
- **Purpose**: AI-powered protein structure prediction
- **Capabilities**:
  - High-accuracy structure prediction
  - Confidence analysis and quality assessment
  - Mutation impact prediction
  - Comparative structure analysis
- **Agent**: `AlphaFoldAgent`
- **Wrapper**: `AlphaFoldWrapper`
- **Status**: Optional (requires installation and databases)

### 4. **ESM (Evolutionary Scale Modeling)** - Protein Language Models
- **Purpose**: Sequence-based protein analysis using language models
- **Capabilities**:
  - Protein sequence embeddings and analysis
  - Conservation analysis across homologs
  - Functional site prediction
  - Mutation effect prediction
- **Agent**: `ESMAgent`
- **Wrapper**: `ESMWrapper`
- **Status**: Enabled by default (installable via pip)

### 5. **OpenMM** - Molecular Dynamics Simulations
- **Purpose**: Physics-based molecular dynamics simulations
- **Capabilities**:
  - Thermostability prediction
  - Mutation validation through MD
  - Protein flexibility analysis
  - Dynamics-based hypothesis generation
- **Agent**: `MolecularDynamicsAgent`
- **Wrapper**: `OpenMMWrapper`
- **Status**: Optional (best installed via conda)

### 6. **PyMOL** - Molecular Visualization
- **Purpose**: Professional molecular visualization and analysis
- **Capabilities**:
  - Publication-quality structure visualization
  - Mutation highlighting and comparison
  - Surface and cavity analysis
  - Animation and presentation graphics
- **Wrapper**: `PyMOLWrapper`
- **Status**: Optional (installable via homebrew/conda)

## Architecture Overview

```
StructBioReasoner
├── Core System
│   ├── Jnana Integration (AI hypothesis generation)
│   ├── ProtoGnosis Multi-Agent System
│   └── Configuration Management
├── Tool Wrappers
│   ├── RFDiffusionWrapper
│   ├── RosettaWrapper
│   ├── AlphaFoldWrapper
│   ├── ESMWrapper
│   ├── OpenMMWrapper
│   └── PyMOLWrapper
├── Specialized Agents
│   ├── RFDiffusionAgent (Generative Design)
│   ├── RosettaAgent (Computational Design)
│   ├── AlphaFoldAgent (Structure Prediction)
│   ├── ESMAgent (Language Model Analysis)
│   ├── MolecularDynamicsAgent (Physics Validation)
│   └── Existing Agents (Structural, Evolutionary, etc.)
└── Integration Layer
    ├── Multi-tool workflows
    ├── Consensus analysis
    └── Comprehensive reporting
```

## Key Features

### 1. **Unified Interface**
- All tools accessible through consistent Python API
- Standardized configuration via YAML
- Common data formats and exchange protocols

### 2. **Mock Implementation Support**
- Full functionality testing without external tool installation
- Realistic mock outputs for development and testing
- Graceful degradation when tools are unavailable

### 3. **Async Operations**
- Non-blocking tool operations
- Parallel hypothesis generation
- Efficient resource management

### 4. **Comprehensive Validation**
- Multi-tool consensus analysis
- Cross-validation between different approaches
- Confidence scoring and reliability assessment

### 5. **Experimental Integration**
- Detailed experimental validation protocols
- Cost-benefit analysis for proposed experiments
- Prioritized testing recommendations

## Installation and Setup

### Core Dependencies (Always Required)
```bash
pip install torch fair-esm biotite numpy scipy pandas matplotlib
```

### Optional Tool Installation

#### ESM (Recommended - Enabled by Default)
```bash
pip install fair-esm torch
```

#### OpenMM (Recommended for MD)
```bash
conda install -c conda-forge openmm pdbfixer mdtraj
```

#### PyMOL (Recommended for Visualization)
```bash
# macOS
brew install pymol

# Linux/Windows
conda install -c conda-forge pymol-open-source
```

#### RFDiffusion (Advanced Users)
```bash
# Requires separate installation from GitHub
git clone https://github.com/RosettaCommons/RFdiffusion.git
# Follow RFDiffusion installation instructions
```

#### Rosetta (Academic/Commercial License Required)
```bash
# Requires license and separate installation
# Download from https://www.rosettacommons.org/
```

#### AlphaFold (Advanced Users)
```bash
# Requires significant setup and database downloads
# Follow AlphaFold installation instructions
# Requires ~2.2TB for full databases
```

## Configuration

### Enable/Disable Tools
Edit `config/protein_config.yaml`:

```yaml
tools:
  esm:
    enabled: true  # Always recommended
  openmm:
    enabled: true  # For MD validation
  rfdiffusion:
    enabled: false  # Set to true when installed
  rosetta:
    enabled: false  # Set to true when licensed
  alphafold:
    enabled: false  # Set to true when installed
```

### Agent Configuration
```yaml
agents:
  esm_agent:
    enabled: true
    analysis_strategies:
      - "sequence_analysis"
      - "conservation_analysis"
      - "functional_prediction"
      - "mutation_design"
  
  molecular_dynamics:
    enabled: true
    capabilities:
      - "thermostability_prediction"
      - "mutation_validation"
```

## Usage Examples

### 1. Basic Multi-Tool Analysis
```python
from struct_bio_reasoner.core.protein_system import ProteinSystem
from struct_bio_reasoner.agents import ESMAgent, MolecularDynamicsAgent

# Initialize system
system = ProteinSystem("config/protein_config.yaml")
await system.initialize()

# Run ESM analysis
esm_agent = ESMAgent(system.config)
await esm_agent.initialize()

context = {
    "target_protein": "ubiquitin",
    "protein_sequence": "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG"
}

hypotheses = await esm_agent.generate_hypotheses(context)
```

### 2. Comprehensive Analysis
```python
# Run the comprehensive multi-tool example
python examples/comprehensive_multi_tool_analysis.py
```

### 3. Tool-Specific Analysis
```python
# RFDiffusion for de novo design
rfdiffusion_agent = RFDiffusionAgent(config)
design_hypotheses = await rfdiffusion_agent.generate_hypotheses(context)

# Rosetta for energy optimization
rosetta_agent = RosettaAgent(config)
optimization_hypotheses = await rosetta_agent.generate_hypotheses(context)
```

## Workflow Integration

### 1. **Discovery Phase**
- ESM sequence analysis for functional insights
- AlphaFold structure prediction for structural context
- Literature analysis for experimental precedents

### 2. **Design Phase**
- RFDiffusion for generative design options
- Rosetta for physics-based optimization
- Multi-agent consensus for design selection

### 3. **Validation Phase**
- OpenMM molecular dynamics for stability validation
- AlphaFold confidence analysis for structure quality
- Cross-tool validation for reliability assessment

### 4. **Experimental Phase**
- Prioritized experimental recommendations
- Cost-benefit analysis for proposed tests
- Detailed protocols for validation experiments

## Performance Considerations

### Computational Requirements
- **ESM**: GPU recommended, 4-8GB VRAM
- **OpenMM**: GPU strongly recommended for MD
- **RFDiffusion**: GPU required, 8-16GB VRAM
- **Rosetta**: CPU-intensive, benefits from multiple cores
- **AlphaFold**: GPU recommended, requires large databases

### Resource Management
- Automatic GPU memory management
- Configurable batch sizes for large analyses
- Efficient caching of intermediate results
- Parallel processing where possible

## Troubleshooting

### Common Issues

1. **Tool Not Found**
   - Check installation status
   - Verify PATH configuration
   - Enable mock mode for testing

2. **GPU Memory Issues**
   - Reduce batch sizes in configuration
   - Use CPU fallback when available
   - Monitor GPU memory usage

3. **Database Access**
   - Verify database paths for AlphaFold
   - Check internet connectivity for online databases
   - Use local caches when possible

### Mock Mode Testing
All tools support mock mode for testing without installation:
```yaml
development:
  mock_expensive_tools: true
```

## Future Enhancements

### Planned Integrations
- **ChimeraX** for advanced visualization
- **GROMACS** for additional MD capabilities
- **FoldX** for mutation effect prediction
- **DSSP** for secondary structure analysis

### Workflow Improvements
- Automated design-test-learn cycles
- Real-time experimental feedback integration
- Machine learning model training on results
- Automated literature mining and integration

## Support and Documentation

- **Main Documentation**: `docs/`
- **API Reference**: Auto-generated from docstrings
- **Examples**: `examples/` directory
- **Configuration**: `config/protein_config.yaml`
- **Issues**: GitHub Issues for bug reports and feature requests

## Contributing

We welcome contributions to expand tool integrations and improve workflows. Please see `CONTRIBUTING.md` for guidelines on:
- Adding new tool wrappers
- Implementing new agents
- Improving existing integrations
- Documentation and examples
