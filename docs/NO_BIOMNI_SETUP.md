# StructBioReasoner without Biomni

This document explains how to use StructBioReasoner without the Biomni biomedical verification component.

## Overview

StructBioReasoner can operate without Biomni while still providing full protein engineering capabilities through:
- **ProtoGnosis**: Multi-agent hypothesis generation and tournament evaluation
- **Wisteria**: Interactive hypothesis refinement
- **Protein-specific agents**: Structural, evolutionary, energetic, and mutation design analysis
- **Tool integration**: BioPython, PyMOL, ESM protein models, and more

## Configuration

### Automatic Configuration

By default, StructBioReasoner is configured to run **without Biomni**:

```yaml
# config/protein_config.yaml
jnana:
  config_path: "../Jnana/config/models.yaml"
  enable_protognosis: true
  enable_biomni: false  # Disabled by default
  enable_wisteria_ui: true
```

### Manual Configuration

To explicitly disable Biomni, ensure your configuration has:

```yaml
jnana:
  enable_biomni: false
```

## System Capabilities without Biomni

### ✅ Available Features

1. **Hypothesis Generation**
   - Multi-agent hypothesis generation via ProtoGnosis
   - Interactive hypothesis refinement via Wisteria
   - Tournament-based hypothesis ranking

2. **Protein Analysis**
   - Structural analysis (active sites, cavities, interfaces)
   - Evolutionary conservation analysis
   - Energetic analysis (stability, binding affinity)
   - Rational mutation design

3. **Tool Integration**
   - BioPython for sequence/structure analysis
   - PyMOL for visualization (optional)
   - ESM protein language models
   - Custom protein analysis tools

4. **Knowledge Systems**
   - Protein database integration (PDB, UniProt, AlphaFold)
   - Literature processing (when configured)
   - Knowledge graph integration (when configured)

### ⚠️ Limitations without Biomni

- **No biomedical verification**: Hypotheses won't be automatically verified against biomedical databases
- **No experimental suggestions**: No automatic experimental protocol suggestions
- **No drug interaction checks**: No automatic drug-protein interaction analysis

## Usage Examples

### Command Line Interface

```bash
# Check system status
python struct_bio_reasoner.py --mode status

# Interactive mode
python struct_bio_reasoner.py --mode interactive --goal "Improve enzyme thermostability"

# Batch mode
python struct_bio_reasoner.py --mode batch --goal "Design mutations for protein stability" --count 5

# Hybrid mode
python struct_bio_reasoner.py --mode hybrid --goal "Enhance binding affinity" --count 3
```

### Python API

```python
from struct_bio_reasoner import ProteinEngineeringSystem

# Initialize system without Biomni
system = ProteinEngineeringSystem(
    config_path="config/protein_config.yaml",
    enable_tools=["biopython", "pymol"],
    enable_agents=["structural", "evolutionary", "energetic", "design"],
    knowledge_graph=True,
    literature_processing=False
)

# Start system
await system.start()

# Set research goal
session_id = await system.set_research_goal("Improve protein thermostability")

# Generate hypotheses
hypotheses = await system.generate_protein_hypotheses(
    count=5,
    protein_id="1ABC",
    strategies=["structural_analysis", "evolutionary_conservation"]
)

# Stop system
await system.stop()
```

## Verification

To verify that Biomni is properly disabled, run the test suite:

```bash
python test_no_biomni.py
```

Expected output:
```
🎉 ALL TESTS PASSED!
StructBioReasoner is working correctly without Biomni.
```

## Performance Benefits

Running without Biomni provides several advantages:

1. **Faster startup**: No biomedical database initialization
2. **Lower memory usage**: No biomedical knowledge base loading
3. **Simpler dependencies**: Fewer external service requirements
4. **Focused analysis**: Concentrated on protein engineering tasks

## Re-enabling Biomni

If you later want to enable Biomni:

1. Update configuration:
   ```yaml
   jnana:
     enable_biomni: true
   ```

2. Ensure Biomni dependencies are installed
3. Configure biomedical databases and API keys
4. Restart the system

## Troubleshooting

### Common Issues

1. **System still tries to initialize Biomni**
   - Check that `enable_biomni: false` is in your config
   - Verify you're using the correct config file path

2. **Missing functionality**
   - Ensure ProtoGnosis is enabled: `enable_protognosis: true`
   - Check that required agents are enabled in configuration

3. **Import errors**
   - Verify Jnana is properly installed and accessible
   - Check that all required dependencies are installed

### Getting Help

If you encounter issues:

1. Run the verification script: `python test_no_biomni.py`
2. Check system status: `python struct_bio_reasoner.py --mode status`
3. Review logs in `./logs/struct_bio_reasoner.log`

## Summary

StructBioReasoner provides full protein engineering capabilities without Biomni, focusing on:
- **Hypothesis generation** via ProtoGnosis multi-agent system
- **Interactive refinement** via Wisteria interface
- **Protein-specific analysis** via specialized agents
- **Tool integration** for structural biology workflows

This configuration is ideal for protein engineering research that doesn't require biomedical verification or experimental protocol suggestions.
