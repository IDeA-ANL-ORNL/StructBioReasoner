# NMNAT-2 Agentic Binder Design Workflow Guide

## Overview

This guide explains the new agentic workflow implemented in `nmnat2_agentic_binder_workflow.py` for designing biologic binders to NMNAT-2 that disrupt cancer pathway interactions.

## Workflow Architecture

```
Research Goal
    ↓
Recommender Agent (Jnana) → Optimized HiPerRAG Prompt
    ↓
HiPerRAG → Interacting Protein Names
    ↓
UniProt API → Protein Sequences
    ↓
Chai Agent → Folded Structures
    ↓
Reasoner → Select Systems to Simulate
    ↓
MD Analysis Agent → Binding Hotspots
    ↓
┌─────────────────────────────────────┐
│  AGENTIC OPTIMIZATION LOOP          │
│  ┌───────────────────────────────┐  │
│  │ Reasoner → Task Decision      │  │
│  │   ↓                           │  │
│  │ if task == "bindcraft":       │  │
│  │   → BindCraft Agent           │  │
│  │ elif task == "md_simulation": │  │
│  │   → MD Agent                  │  │
│  │ elif task == "free_energy":   │  │
│  │   → Free Energy Agent         │  │
│  │ elif task == "stop":          │  │
│  │   → Exit loop                 │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
    ↓
Final Reasoner → Report + Best Binders
```

## Key Features

### 1. **LLM-Guided Decision Making**
- Reasoner agent decides which computational task to run next
- Adaptive workflow based on intermediate results
- Iteration 1 hardcoded to BindCraft, then LLM decides

### 2. **Multi-Agent Coordination**
- HiPerRAG for literature mining
- Chai for structure prediction
- MDAgent for simulations
- BindCraft for binder design
- FEAgent for free energy calculations

### 3. **Structured Data Flow**
- JSON schemas for all LLM outputs
- Type-safe data passing between agents
- Comprehensive state tracking

## Workflow Steps

### Step 1: Initialize System
```python
system = BinderDesignSystem(
    config_path="config/binder_config.yaml",
    jnana_config_path="config/test_jnana_config.yaml",
    enable_agents=['computational_design', 'molecular_dynamics', 'rag', 'structure_prediction']
)
```

### Step 2: Recommender Agent
- Uses Jnana LLM to generate optimal HiPerRAG prompt
- Tailored to find cancer pathway interactors
- Requests structured JSON output

### Step 3: HiPerRAG Literature Mining
- Queries scientific literature
- Identifies NMNAT-2 interacting proteins
- Returns protein names + UniProt IDs

### Step 4: UniProt API
- Fetches sequences for all interacting proteins
- Uses REST API: `https://rest.uniprot.org/uniprotkb/{id}.fasta`

### Step 5: Chai Structure Prediction
- Folds NMNAT-2 and all interacting partners
- Returns PDB structures with confidence scores

### Step 6: System Selection Reasoner
- LLM selects 2-4 protein complexes to simulate
- Based on confidence, literature evidence, feasibility
- Prioritizes systems

### Step 7: MD Analysis
- Simulates selected protein-protein complexes
- Identifies binding hotspot residues
- Uses contact frequency analysis

### Step 8: Agentic Optimization Loop
**Iteration 1 (Hardcoded):**
- Task: BindCraft
- Generates initial peptide binders targeting hotspots

**Iterations 2-N (LLM-Decided):**
- Reasoner evaluates current state
- Decides next task: BindCraft / MD / FreeEnergy / Stop
- Executes task
- Updates state

**Task Options:**
- `bindcraft`: Generate/optimize peptides
- `md_simulation`: Simulate peptide-target complexes
- `free_energy`: Calculate binding affinities (MM-PBSA)
- `stop`: Terminate and report results

### Step 9: Final Report
- LLM generates comprehensive report
- Top 5 binders with sequences and affinities
- Experimental validation recommendations
- Limitations and caveats

## Required Code Changes

### 1. Fix RAGAgent Launch (CRITICAL)

**File:** `struct_bio_reasoner/agents/hiper_rag/rag_agent.py`

**Line 182:**
```python
# ❌ CURRENT (INCORRECT):
self.rag_coord = await self.manager.launch(
    RAGAgent,
    args=(self.rag_config),  # Not a tuple!
)

# ✅ FIXED (CORRECT):
self.rag_coord = await self.manager.launch(
    RAGAgent,
    args=(self.rag_config,),  # Trailing comma makes it a tuple
)
```

### 2. Add `fold_proteins` Method to ChaiAgent

**File:** `struct_bio_reasoner/agents/structure_prediction/chai_agent.py`

Add this method:
```python
async def fold_proteins(self, sequences: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """
    Fold multiple protein sequences.
    
    Args:
        sequences: Dict mapping protein names to sequences
        
    Returns:
        Dict mapping protein names to folding results
    """
    results = {}
    
    for name, sequence in sequences.items():
        logger.info(f"Folding {name}...")
        
        # Use existing folding infrastructure
        result = await self.fold_single_protein(name, sequence)
        results[name] = result
    
    return results
```

### 3. Add `generate_binders` Method to BindCraftAgent

**File:** `struct_bio_reasoner/agents/computational_design/bindcraft_agent.py`

Add this method:
```python
async def generate_binders(self, task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate peptide binders for a target.
    
    Args:
        task: Dict with:
            - target_sequence: str
            - hotspot_residues: List[int]
            - num_rounds: int
            - num_sequences: int
            - scaffold_type: str
            
    Returns:
        Dict with optimized_sequences and metrics
    """
    target_seq = task['target_sequence']
    hotspots = task['hotspot_residues']
    num_rounds = task.get('num_rounds', 3)
    num_seq = task.get('num_sequences', 25)
    
    # Run BindCraft workflow
    results = await self.run_bindcraft_workflow(
        target_sequence=target_seq,
        hotspot_residues=hotspots,
        num_rounds=num_rounds,
        num_sequences_per_round=num_seq
    )
    
    return results
```

### 4. Ensure MDAgent Has `analyze_hypothesis` Method

**File:** `struct_bio_reasoner/agents/molecular_dynamics/mdagent_adapter.py`

The method already exists (line 589-632), but ensure it accepts `None` for hypothesis:

```python
async def analyze_hypothesis(self,
                             hypothesis: Optional[ProteinHypothesis],
                             task_params: dict[str, Any]) -> SimAnalysis:
    """
    Run MD analysis. Hypothesis can be None - will create internally.
    """
    # If hypothesis is None, create a placeholder
    if hypothesis is None:
        hypothesis = ProteinHypothesis(
            title="MD Analysis",
            content="Automated MD simulation",
            hypothesis_type="simulation"
        )

    # Rest of existing implementation...
```

### 5. Ensure FEAgent Has `analyze_hypothesis` Method

**File:** `struct_bio_reasoner/agents/molecular_dynamics/free_energy_agent.py`

The method already exists (line 389-407), but ensure it accepts `None` for hypothesis:

```python
async def analyze_hypothesis(self,
                             hypothesis: Optional[ProteinHypothesis],
                             task_params: dict[str, Any]) -> EnergeticAnalysis:
    """
    Run free energy calculations. Hypothesis can be None.
    """
    # If hypothesis is None, create a placeholder
    if hypothesis is None:
        hypothesis = ProteinHypothesis(
            title="Free Energy Analysis",
            content="Automated MM-PBSA calculation",
            hypothesis_type="energetic"
        )

    # Rest of existing implementation...
```

## Configuration Requirements

### binder_config.yaml

Ensure these agents are configured:

```yaml
agents:
  computational_design:
    enabled: true
    bindcraft:
      num_rounds: 3
      num_sequences: 25
      device: "cuda:0"

  molecular_dynamics:
    enabled: true
    mdagent:
      backend: "mdagent"  # or "openmm"
      equil_steps: 100000
      prod_steps: 5000000
      platform: "CUDA"

  structure_prediction:
    enabled: true
    chai:
      device: "cuda:0"
      diffusion_steps: 100

  rag:
    enabled: true
    config_path: "config/hiperrag_config.yaml"

  free_energy:
    enabled: true
    cpus: 8
    cpus_per_node: 64
    selections: ['chain A', 'not chain A']
```

### hiperrag_config.yaml

```yaml
rag_configs:
  generator_config:
    model: "gpt-4"
    temperature: 0.0
    max_tokens: 16384

  retriever_config:
    index_path: "/path/to/hiperrag/index"
    top_k: 20

  verbose: true

save_conversation_path: "./data/rag_conversations"
```

## Usage

### Basic Usage

```bash
cd examples
python nmnat2_agentic_binder_workflow.py
```

### Expected Output

```
================================================================================
NMNAT-2 AGENTIC BINDER DESIGN WORKFLOW
================================================================================

[STEP 1] Initializing BinderDesignSystem...
✓ System initialized
✓ Research goal set (session: abc123)

[STEP 2] Using Recommender Agent to optimize HiPerRAG prompt...
✓ Optimized HiPerRAG prompt generated

[STEP 3] Querying HiPerRAG for interacting proteins...
✓ HiPerRAG response received
✓ Identified 5 interacting proteins

[STEP 4] Fetching sequences from UniProt...
✓ Fetched 5 protein sequences

[STEP 5] Folding protein structures with Chai...
✓ Folded 6 structures

[STEP 6] Using Reasoner to select systems for MD simulation...
✓ Selected 3 systems for MD simulation

[STEP 7] Running MD simulations to identify binding hotspots...
✓ Completed MD simulation for NMNAT2_HUMAN_PARTNER1
✓ Identified 8 hotspot residues

[STEP 8] Starting agentic optimization loop...

================================================================================
ITERATION 1
================================================================================
[Iteration 1] Hardcoded task: bindcraft
[TASK: BindCraft] Generating/optimizing peptide binders...
✓ BindCraft generated 25 peptide binders

================================================================================
ITERATION 2
================================================================================
[Iteration 2] Reasoner recommends: md_simulation
Rationale: Need to validate peptide-target binding through MD simulations
[TASK: MD Simulation] Simulating peptide-target complexes...
✓ Completed MD for peptide_2_1

================================================================================
ITERATION 3
================================================================================
[Iteration 3] Reasoner recommends: free_energy
Rationale: Calculate binding affinities to rank peptides
[TASK: Free Energy] Calculating binding free energies...
✓ Calculated free energies for 5 peptides
✓ Top 5 binders identified

================================================================================
ITERATION 4
================================================================================
[Iteration 4] Reasoner recommends: stop
Rationale: Sufficient high-quality binders identified (5 with ΔG < -10 kcal/mol)
[TASK: Stop] Reasoner decided to stop optimization

[STEP 9] Generating final report with best binders...
✓ Final report generated
✓ Report saved to ./data/nmnat2_workflow_results/nmnat2_binder_report_20251208_143022.json

================================================================================
WORKFLOW COMPLETE!
================================================================================

Executive Summary:
Successfully designed 5 high-affinity peptide binders for NMNAT-2 targeting
cancer pathway disruption. Top binder shows ΔG = -12.3 kcal/mol with stable
binding to hotspot residues 45, 67, 89, 102.

Top 5 Binders:
  1. peptide_2_1: ΔG = -12.30 kcal/mol
     Sequence: WKFLDANWMLDWEQRPSFKGM
     Rationale: Strong electrostatic interactions with hotspot residues
  2. peptide_2_3: ΔG = -11.80 kcal/mol
     Sequence: YFKLDPNWQLDWERPSFKGM
     Rationale: Hydrophobic packing with binding pocket
  ...

Report saved to: ./data/nmnat2_workflow_results/nmnat2_binder_report_20251208_143022.json
================================================================================
```

## Troubleshooting

### Issue: RAGAgent initialization fails

**Error:** `TypeError: RAGAgent.__init__() missing 1 required positional argument: 'config_inp'`

**Solution:** Apply the fix in section "Required Code Changes #1"

### Issue: ChaiAgent doesn't have `fold_proteins` method

**Error:** `AttributeError: 'ChaiAgent' object has no attribute 'fold_proteins'`

**Solution:** Add the method as shown in section "Required Code Changes #2"

### Issue: BindCraft doesn't have `generate_binders` method

**Error:** `AttributeError: 'BindCraftAgent' object has no attribute 'generate_binders'`

**Solution:** Add the method as shown in section "Required Code Changes #3"

## Advanced Customization

### Custom Scaffold Types

Modify the research goal to specify different scaffolds:

```python
research_goal = """
Design biologic binders for NMNAT-2 using:
- Affibody scaffold (preferred)
- Nanobody scaffold (if affibody fails)
- Custom peptide (fallback)
...
"""
```

### Adjust Iteration Limits

```python
max_iterations = 15  # Allow more optimization rounds
```

### Custom Decision Logic

Override the reasoner's decision at specific iterations:

```python
if iteration == 5:
    recommended_task = "free_energy"  # Force free energy calculation
```

## Performance Considerations

- **HiPerRAG**: Requires GPU for fast retrieval (~2-5 min)
- **Chai Folding**: GPU required, ~5-10 min per protein
- **MD Simulations**: GPU recommended, ~30-60 min per system (10 ns)
- **BindCraft**: GPU required, ~20-40 min per round
- **Free Energy**: CPU-based, ~10-20 min per peptide

**Total Runtime:** 4-8 hours for complete workflow

## Output Files

```
data/
├── nmnat2_workflow_results/
│   └── nmnat2_binder_report_TIMESTAMP.json
├── md_simulations/
│   ├── NMNAT2_HUMAN_PARTNER1/
│   └── NMNAT2_HUMAN_PARTNER2/
├── peptide_complexes/
│   ├── peptide_1_1.pdb
│   └── peptide_1_2.pdb
└── md_peptides/
    ├── peptide_2_1/
    └── peptide_2_2/
```

## Next Steps

1. **Apply code changes** listed in "Required Code Changes"
2. **Configure agents** in `config/binder_config.yaml`
3. **Set up HiPerRAG** index and configuration
4. **Run workflow** with `python nmnat2_agentic_binder_workflow.py`
5. **Analyze results** in generated JSON report
6. **Experimental validation** of top binders

## References

- **StructBioReasoner**: https://github.com/IDeA-ANL-ORNL/StructBioReasoner
- **Jnana**: https://github.com/architvasan/Jnana
- **BindCraft**: https://github.com/msinclair-py/bindcraft
- **MDAgent**: https://github.com/msinclair-py/MDAgent
- **Chai-1**: https://github.com/chaidiscovery/chai-lab
- **UniProt API**: https://www.uniprot.org/help/api
