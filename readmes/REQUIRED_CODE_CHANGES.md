# Required Code Changes for NMNAT-2 Agentic Workflow

This document lists all code changes needed in existing files to support the new `nmnat2_agentic_binder_workflow.py` script.

## ⚠️ CRITICAL FIX: RAGAgent Tuple Syntax

### File: `struct_bio_reasoner/agents/hiper_rag/rag_agent.py`

**Location:** Line 180-183

**Current Code (BROKEN):**
```python
self.rag_coord = await self.manager.launch(
    RAGAgent,
    args=(self.rag_config),  # ❌ This is NOT a tuple!
)
```

**Fixed Code:**
```python
self.rag_coord = await self.manager.launch(
    RAGAgent,
    args=(self.rag_config,),  # ✅ Trailing comma makes it a tuple
)
```

**Why This Matters:**
- In Python, `(x)` is just `x` with parentheses, NOT a tuple
- To create a single-element tuple, you MUST use `(x,)` with a trailing comma
- Without this fix, Academy's `Manager.launch()` cannot properly unpack arguments
- This causes: `TypeError: RAGAgent.__init__() missing 1 required positional argument: 'config_inp'`

---

## Enhancement 1: ChaiAgent `fold_proteins` Method

### File: `struct_bio_reasoner/agents/structure_prediction/chai_agent.py`

**Add this method to the `ChaiAgent` class:**

```python
async def fold_proteins(self, sequences: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """
    Fold multiple protein sequences using Chai-1.
    
    Args:
        sequences: Dict mapping protein names to amino acid sequences
                  Example: {'NMNAT2_HUMAN': 'MTETTKTH...', 'PARTNER1': 'MVKL...'}
        
    Returns:
        Dict mapping protein names to folding results
        Example: {
            'NMNAT2_HUMAN': {
                'pdb_path': '/path/to/structure.pdb',
                'confidence': 0.95,
                'plddt_scores': [85.2, 87.1, ...],
                'structure': <Bio.PDB.Structure>
            }
        }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    results = {}
    
    for name, sequence in sequences.items():
        logger.info(f"Folding {name} ({len(sequence)} residues)...")
        
        try:
            # Use existing Chai folding infrastructure
            # This assumes you have a method like fold_single_protein or similar
            result = await self.fold_single_protein(name, sequence)
            results[name] = result
            logger.info(f"✓ Successfully folded {name}")
            
        except Exception as e:
            logger.error(f"Failed to fold {name}: {e}")
            results[name] = {
                'pdb_path': None,
                'confidence': 0.0,
                'error': str(e)
            }
    
    return results
```

**Alternative Implementation (if `fold_single_protein` doesn't exist):**

```python
async def fold_proteins(self, sequences: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """Fold multiple protein sequences using Chai-1."""
    import logging
    from pathlib import Path
    logger = logging.getLogger(__name__)
    
    results = {}
    
    for name, sequence in sequences.items():
        logger.info(f"Folding {name} ({len(sequence)} residues)...")
        
        try:
            # Prepare input for Chai
            fasta_input = {
                'sequences': [
                    {
                        'protein': {
                            'id': name,
                            'sequence': sequence
                        }
                    }
                ]
            }
            
            # Run Chai folding (adjust based on your Chai integration)
            output = await self.run_chai_folding(fasta_input)
            
            results[name] = {
                'pdb_path': str(output['pdb_path']),
                'confidence': output.get('confidence', 0.0),
                'plddt_scores': output.get('plddt', []),
                'structure': output.get('structure')
            }
            logger.info(f"✓ Successfully folded {name}")
            
        except Exception as e:
            logger.error(f"Failed to fold {name}: {e}")
            results[name] = {
                'pdb_path': None,
                'confidence': 0.0,
                'error': str(e)
            }
    
    return results
```

---

## Enhancement 2: BindCraftAgent `generate_binders` Method

### File: `struct_bio_reasoner/agents/computational_design/bindcraft_agent.py`

**Add this method to the `BindCraftAgent` class:**

```python
async def generate_binders(self, task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate peptide binders for a target protein.
    
    Args:
        task: Dictionary containing:
            - target_sequence (str): Target protein sequence
            - hotspot_residues (List[int]): Residue indices to target
            - num_rounds (int): Number of optimization rounds (default: 3)
            - num_sequences (int): Sequences per round (default: 25)
            - scaffold_type (str): 'peptide', 'affibody', 'nanobody', etc.
            
    Returns:
        Dictionary with:
            - optimized_sequences (List[str]): Generated binder sequences
            - scores (List[float]): Quality scores for each sequence
            - metrics (Dict): Performance metrics
            
    Example:
        task = {
            'target_sequence': 'MTETTKTH...',
            'hotspot_residues': [45, 67, 89, 102],
            'num_rounds': 3,
            'num_sequences': 25,
            'scaffold_type': 'peptide'
        }
        results = await bindcraft_agent.generate_binders(task)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Extract task parameters
    target_seq = task['target_sequence']
    hotspots = task.get('hotspot_residues', [])
    num_rounds = task.get('num_rounds', 3)
    num_seq = task.get('num_sequences', 25)
    scaffold_type = task.get('scaffold_type', 'peptide')
    
    logger.info(f"Generating {scaffold_type} binders for target ({len(target_seq)} aa)")
    logger.info(f"Targeting {len(hotspots)} hotspot residues: {hotspots}")
    logger.info(f"Running {num_rounds} rounds with {num_seq} sequences each")
    
    try:
        # Run BindCraft workflow
        # Adjust this based on your actual BindCraft integration
        results = await self.run_bindcraft_workflow(
            target_sequence=target_seq,
            hotspot_residues=hotspots,
            num_rounds=num_rounds,
            num_sequences_per_round=num_seq,
            scaffold_type=scaffold_type
        )
        
        logger.info(f"✓ Generated {len(results.get('optimized_sequences', []))} binders")
        
        return results
        
    except Exception as e:
        logger.error(f"BindCraft generation failed: {e}")
        return {
            'optimized_sequences': [],
            'scores': [],
            'metrics': {},
            'error': str(e)
        }
```

---

## Enhancement 3: MDAgent `analyze_hypothesis` - Handle None Hypothesis

### File: `struct_bio_reasoner/agents/molecular_dynamics/mdagent_adapter.py`

**Location:** Around line 589-632 (the `analyze_hypothesis` method)

**Modify the method to handle `None` hypothesis:**

```python
async def analyze_hypothesis(self,
                             hypothesis: Optional[ProteinHypothesis],
                             task_params: dict[str, Any]) -> SimAnalysis:
    """
    Run MD analysis on a protein hypothesis.
    
    Args:
        hypothesis: ProteinHypothesis object (can be None - will create internally)
        task_params: Dictionary with simulation parameters
        
    Returns:
        SimAnalysis object with RMSD, RMSF, etc.
    """
    # ADD THIS CHECK AT THE BEGINNING:
    if hypothesis is None:
        # Create a placeholder hypothesis for automated workflows
        hypothesis = ProteinHypothesis(
            title="MD Analysis",
            content="Automated MD simulation",
            hypothesis_type="simulation",
            metadata=task_params
        )
    
    # Rest of existing implementation continues unchanged...
    simulation_paths = task_params.get('simulation_paths', [])
    root_output_path = task_params.get('root_output_path')
    # ... etc
```

---

## Enhancement 4: FEAgent `analyze_hypothesis` - Handle None Hypothesis

### File: `struct_bio_reasoner/agents/molecular_dynamics/free_energy_agent.py`

**Location:** Around line 389-407 (the `analyze_hypothesis` method)

**Modify the method to handle `None` hypothesis:**

```python
async def analyze_hypothesis(self,
                             hypothesis: Optional[ProteinHypothesis],
                             task_params: dict[str, Any]) -> EnergeticAnalysis:
    """
    Run free energy calculations on a protein hypothesis.

    Args:
        hypothesis: ProteinHypothesis object (can be None - will create internally)
        task_params: Dictionary with calculation parameters

    Returns:
        EnergeticAnalysis object with binding affinities
    """
    # ADD THIS CHECK AT THE BEGINNING:
    if hypothesis is None:
        # Create a placeholder hypothesis for automated workflows
        hypothesis = ProteinHypothesis(
            title="Free Energy Analysis",
            content="Automated MM-PBSA calculation",
            hypothesis_type="energetic",
            metadata=task_params
        )

    # Rest of existing implementation continues unchanged...
    simulation_paths = task_params.get('simulation_paths', [])
    # ... etc
```

---

## Summary of Changes

### Critical (Must Fix)
1. ✅ **RAGAgent tuple syntax** - Line 182 in `rag_agent.py`
   - Change `args=(self.rag_config)` to `args=(self.rag_config,)`

### Recommended (For Full Workflow Support)
2. ✅ **ChaiAgent.fold_proteins()** - Add method to `chai_agent.py`
3. ✅ **BindCraftAgent.generate_binders()** - Add method to `bindcraft_agent.py`
4. ✅ **MDAgent.analyze_hypothesis()** - Add None check in `mdagent_adapter.py`
5. ✅ **FEAgent.analyze_hypothesis()** - Add None check in `free_energy_agent.py`

### Testing After Changes

After applying these changes, test with:

```bash
# Test RAG agent fix
python examples/test_hiper_rag.py

# Test full workflow
python examples/nmnat2_agentic_binder_workflow.py
```

### Verification Checklist

- [ ] RAGAgent launches without TypeError
- [ ] ChaiAgent can fold multiple proteins
- [ ] BindCraft generates peptide binders
- [ ] MDAgent accepts None hypothesis
- [ ] FEAgent accepts None hypothesis
- [ ] Full workflow completes without errors

---

## Additional Notes

### Import Statements

Make sure these imports are present in the modified files:

**chai_agent.py:**
```python
from typing import Dict, Any, Optional
import logging
```

**bindcraft_agent.py:**
```python
from typing import Dict, Any, List, Optional
import logging
```

**mdagent_adapter.py:**
```python
from typing import Optional
from struct_bio_reasoner.core.data_models import ProteinHypothesis
```

**free_energy_agent.py:**
```python
from typing import Optional
from struct_bio_reasoner.core.data_models import ProteinHypothesis
```

### Configuration Files

Ensure your configuration files are set up correctly:

**config/binder_config.yaml:**
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

**config/test_jnana_config.yaml:**
```yaml
model_manager:
  model_name: "gpt-4"
  temperature: 0.3
  max_tokens: 4096
```

---

## Questions or Issues?

If you encounter any problems after applying these changes:

1. Check that all imports are correct
2. Verify configuration files are properly formatted
3. Ensure all required dependencies are installed
4. Check logs for detailed error messages
5. Test each component individually before running full workflow

For the RAGAgent tuple syntax error specifically, this is a **critical fix** that must be applied before any RAG-based workflows will function.


