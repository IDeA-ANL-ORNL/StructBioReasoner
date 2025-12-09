# NMNAT-2 Agentic Binder Design Workflow

## Quick Start

This directory contains a complete implementation of an **LLM-guided agentic workflow** for designing biologic binders to NMNAT-2 that disrupt cancer pathway interactions.

### Files in This Package

1. **`nmnat2_agentic_binder_workflow.py`** - Main workflow script (694 lines)
2. **`NMNAT2_WORKFLOW_GUIDE.md`** - Comprehensive documentation
3. **`REQUIRED_CODE_CHANGES.md`** - Code snippets for required changes to existing files

## What This Workflow Does

```
Research Goal (NMNAT-2 binder design)
    ↓
Jnana LLM → Optimizes HiPerRAG prompt
    ↓
HiPerRAG → Finds interacting proteins from literature
    ↓
UniProt API → Fetches protein sequences
    ↓
Chai-1 → Folds all structures
    ↓
Jnana LLM → Selects systems to simulate
    ↓
OpenMM MD → Identifies binding hotspots
    ↓
┌─────────────────────────────────────────┐
│  AGENTIC OPTIMIZATION LOOP              │
│  ┌───────────────────────────────────┐  │
│  │ Iteration 1: BindCraft (hardcoded)│  │
│  │ Iteration 2+: LLM decides:        │  │
│  │   - BindCraft (generate binders)  │  │
│  │   - MD Simulation (validate)      │  │
│  │   - Free Energy (rank)            │  │
│  │   - Stop (sufficient quality)     │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
    ↓
Final Report: Top 5 binders + rationale
```

## Installation & Setup

### 1. Apply Required Code Changes

**CRITICAL:** Before running the workflow, you MUST fix the RAGAgent bug:

```bash
# Edit struct_bio_reasoner/agents/hiper_rag/rag_agent.py
# Line 182: Change args=(self.rag_config) to args=(self.rag_config,)
```

See `REQUIRED_CODE_CHANGES.md` for all required changes.

### 2. Configure Agents

Ensure `config/binder_config.yaml` has all agents enabled:

```yaml
agents:
  computational_design:
    enabled: true
  molecular_dynamics:
    enabled: true
  structure_prediction:
    enabled: true
  rag:
    enabled: true
  free_energy:
    enabled: true
```

### 3. Set Up HiPerRAG

Configure HiPerRAG in `config/hiperrag_config.yaml`:

```yaml
rag_configs:
  generator_config:
    model: "gpt-4"
    temperature: 0.0
  retriever_config:
    index_path: "/path/to/hiperrag/index"
    top_k: 20
```

## Running the Workflow

```bash
cd examples
python nmnat2_agentic_binder_workflow.py
```

**Expected Runtime:** 4-8 hours (depends on hardware and number of iterations)

## Key Features

### 🤖 Agentic Decision-Making
- LLM reasoner decides which computational task to run next
- Adaptive workflow based on intermediate results
- Stops automatically when sufficient quality is achieved

### 🧬 Multi-Agent Coordination
- **HiPerRAG**: Literature mining for protein interactions
- **Chai-1**: Structure prediction with confidence scores
- **OpenMM**: Molecular dynamics simulations
- **BindCraft**: Peptide binder optimization
- **Amber MMPBSA**: Free energy calculations

### 📊 Structured Outputs
- JSON schemas for all LLM outputs
- Type-safe data passing between agents
- Comprehensive final report with top binders

### 🎯 Research Goal
Design biologic binders for NMNAT-2 using:
- Affibody scaffolds
- Affitin scaffolds
- Nanobody scaffolds
- Or other scaffolds if clinically supported

Target: Disrupt NMNAT-2 interactions with cancer pathway proteins

## Output

The workflow generates:

```
data/nmnat2_workflow_results/
└── nmnat2_binder_report_TIMESTAMP.json
    ├── executive_summary
    ├── top_binders (top 5)
    │   ├── rank
    │   ├── peptide_id
    │   ├── sequence
    │   ├── binding_affinity_kcal_mol
    │   └── rationale
    ├── experimental_recommendations
    └── limitations
```

**Example Output:**
```json
{
  "executive_summary": "Successfully designed 5 high-affinity peptide binders...",
  "top_binders": [
    {
      "rank": 1,
      "peptide_id": "peptide_2_1",
      "sequence": "WKFLDANWMLDWEQRPSFKGM",
      "binding_affinity_kcal_mol": -12.3,
      "rationale": "Strong electrostatic interactions with hotspot residues 45, 67, 89"
    }
  ]
}
```

## Documentation

- **`NMNAT2_WORKFLOW_GUIDE.md`**: Complete workflow documentation
  - Architecture diagrams
  - Step-by-step explanations
  - Configuration requirements
  - Troubleshooting guide
  - Performance considerations

- **`REQUIRED_CODE_CHANGES.md`**: Code snippets for modifications
  - Critical RAGAgent fix
  - ChaiAgent enhancements
  - BindCraft enhancements
  - MDAgent enhancements
  - FEAgent enhancements

## Troubleshooting

### RAGAgent fails with TypeError
**Solution:** Apply the critical fix in `REQUIRED_CODE_CHANGES.md` section 1

### ChaiAgent missing `fold_proteins` method
**Solution:** Add the method from `REQUIRED_CODE_CHANGES.md` section 2

### BindCraft missing `generate_binders` method
**Solution:** Add the method from `REQUIRED_CODE_CHANGES.md` section 3

## Advanced Usage

### Custom Scaffolds

Modify the research goal in the script:

```python
research_goal = """
Design biologic binders for NMNAT-2 using:
- DARPin scaffold (preferred)
- Affibody scaffold (alternative)
...
"""
```

### Adjust Iteration Limits

```python
max_iterations = 15  # Default is 10
```

### Force Specific Tasks

```python
if iteration == 3:
    recommended_task = "free_energy"  # Override LLM decision
```

## Performance Tips

- **GPU Required**: Chai, BindCraft, MD simulations
- **CPU Cores**: Free energy calculations benefit from 8+ cores
- **Memory**: 32GB+ recommended for large proteins
- **Storage**: ~10GB per complete workflow run

## Next Steps After Workflow Completes

1. **Review final report** in `data/nmnat2_workflow_results/`
2. **Analyze top 5 binders** - sequences and binding affinities
3. **Experimental validation**:
   - Synthesize top peptides
   - SPR/ITC binding assays
   - Cell-based functional assays
4. **Iterate if needed**:
   - Adjust hotspot residues
   - Try different scaffolds
   - Increase optimization rounds

## Citation

If you use this workflow in your research, please cite:
- StructBioReasoner: [GitHub](https://github.com/IDeA-ANL-ORNL/StructBioReasoner)
- Jnana: [GitHub](https://github.com/architvasan/Jnana)
- BindCraft: [Paper/GitHub]
- Chai-1: [Paper/GitHub]

## Support

For issues or questions:
1. Check `NMNAT2_WORKFLOW_GUIDE.md` troubleshooting section
2. Review `REQUIRED_CODE_CHANGES.md` for missing modifications
3. Open an issue on GitHub with logs and error messages

