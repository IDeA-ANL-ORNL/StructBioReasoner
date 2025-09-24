# StructBioReasoner: Jnana-Based Structural Biology Reasoning Model

## Project Overview

StructBioReasoner is a comprehensive reasoning model for protein engineering that integrates Jnana's hypothesis generation framework with specialized structural biology tools and knowledge systems.

**Goal**: Build an AI co-scientist specifically designed for protein engineering that combines:
- Jnana's interactive hypothesis generation and multi-agent processing
- AdaParse/HiPerRAG for literature processing
- Specialized structural biology tools (Rosetta, AlphaFold, PyMOL)
- Domain-specific knowledge graphs and databases

## Architecture

### Core Components

1. **Jnana Integration Layer**: Extends the base Jnana system with protein-specific capabilities
2. **Knowledge Foundation**: Protein databases, literature processing, and knowledge graphs
3. **Specialized Agents**: Protein-specific reasoning agents for different aspects of protein engineering
4. **Tool Integration**: Wrappers for computational biology tools
5. **Interactive Interface**: Extended UI for protein visualization and design

### Key Features

- **Protein-Specific Hypothesis Generation**: Agents specialized for structural, evolutionary, and energetic analysis
- **Literature-Informed Reasoning**: Integration with protein engineering literature via AdaParse/HiPerRAG
- **Computational Tool Integration**: Direct integration with Rosetta, AlphaFold, PyMOL, and other tools
- **Knowledge Graph Reasoning**: Neo4j-based protein knowledge graph with PDB, UniProt, and experimental data
- **Interactive Design Interface**: Real-time protein structure visualization and mutation design

## Installation

### Prerequisites

1. **Jnana Framework**: Ensure Jnana is installed and configured
2. **Computational Biology Tools**: 
   - PyMOL (for visualization)
   - BioPython (for sequence/structure analysis)
   - Optional: Rosetta (requires license), AlphaFold2
3. **Database Systems**:
   - Neo4j (for knowledge graph)
   - Optional: PostgreSQL (for large-scale data)

### Setup

```bash
# Clone and setup
git clone <repository-url>
cd StructBioReasoner

# Install dependencies
pip install -r requirements.txt

# Configure the system
cp config/protein_config.example.yaml config/protein_config.yaml
# Edit config/protein_config.yaml with your settings

# Initialize knowledge graph (optional)
python scripts/setup_knowledge_graph.py

# Run setup verification
python scripts/verify_setup.py
```

## Quick Start

### Basic Protein Engineering Session

```python
from struct_bio_reasoner import ProteinEngineeringSystem

# Initialize the system
system = ProteinEngineeringSystem(
    config_path="config/protein_config.yaml",
    enable_tools=["pymol", "biopython"],
    knowledge_graph=True
)

# Start a protein engineering session
await system.start()
session_id = await system.set_research_goal(
    "Design mutations to improve the thermostability of TEM-1 β-lactamase"
)

# Run in hybrid mode (batch generation + interactive refinement)
await system.run_hybrid_mode(
    hypothesis_count=10,
    strategies=["structural_analysis", "evolutionary_conservation", "energetic_optimization"],
    interactive_refinement=True
)
```

### Interactive Mode

```bash
# Launch interactive protein design interface
python struct_bio_reasoner.py --mode interactive \
    --goal "Improve enzyme thermostability" \
    --protein "1TEM" \
    --enable-visualization
```

## Project Structure

```
StructBioReasoner/
├── struct_bio_reasoner/          # Core package
│   ├── core/                     # Core integration with Jnana
│   │   ├── protein_system.py     # Main system class
│   │   ├── knowledge_foundation.py
│   │   └── session_manager.py
│   ├── agents/                   # Protein-specific agents
│   │   ├── structural/           # Structural analysis agents
│   │   ├── evolutionary/         # Evolutionary analysis agents
│   │   ├── energetic/           # Energy calculation agents
│   │   └── design/              # Mutation design agents
│   ├── data/                    # Data models and structures
│   │   ├── protein_hypothesis.py
│   │   ├── mutation_model.py
│   │   └── knowledge_graph.py
│   ├── tools/                   # Tool integrations
│   │   ├── adaparse_integration.py
│   │   ├── hiperrag_integration.py
│   │   ├── rosetta_wrapper.py
│   │   ├── alphafold_wrapper.py
│   │   └── pymol_wrapper.py
│   ├── ui/                      # User interface extensions
│   │   ├── protein_visualization.py
│   │   └── interactive_design.py
│   └── utils/                   # Utilities
├── config/                      # Configuration files
│   ├── protein_config.yaml      # Main configuration
│   ├── agents_config.yaml       # Agent configurations
│   └── tools_config.yaml        # Tool configurations
├── data/                        # Data storage
│   ├── knowledge_graph/         # Neo4j data
│   ├── literature/              # Processed papers
│   └── structures/              # PDB files and predictions
├── tests/                       # Test suite
├── benchmarks/                  # Benchmark datasets
├── examples/                    # Example workflows
└── scripts/                     # Setup and utility scripts
```

## Development Status

This project extends the Jnana framework for protein engineering applications.

### Phase 1: Foundation & Setup ✅
- [x] Repository structure
- [x] Configuration system
- [x] Basic Jnana integration
- [ ] Environment setup scripts

### Phase 2: Knowledge Foundation (In Progress)
- [ ] Knowledge graph implementation
- [ ] Literature processing pipeline
- [ ] Protein data integration

### Phase 3: Agent System (Planned)
- [ ] Structural analysis agents
- [ ] Evolutionary conservation agents
- [ ] Mutation design agents
- [ ] Agent orchestration

### Phase 4: Tool Integration (Planned)
- [ ] PyMOL integration
- [ ] Rosetta wrapper
- [ ] AlphaFold integration
- [ ] BioPython utilities

### Phase 5: UI Development (Planned)
- [ ] Protein visualization interface
- [ ] Interactive mutation design
- [ ] Real-time structure updates

### Phase 6: Testing & Validation (Planned)
- [ ] Unit and integration tests
- [ ] Benchmark validation
- [ ] Scientific case studies

## Contributing

This project builds upon the Jnana framework. Please see the main Jnana repository for core contribution guidelines.

For protein-specific contributions:
1. Follow the existing agent architecture patterns
2. Ensure compatibility with Jnana's data models
3. Add appropriate tests for new functionality
4. Document scientific rationale for new features

## License

[License information to be added]

## Acknowledgments

- **Jnana Framework**: Core AI co-scientist system
- **Wisteria**: Interactive hypothesis generation
- **ProtoGnosis**: Multi-agent processing system
- **Biomni**: Biomedical verification system
