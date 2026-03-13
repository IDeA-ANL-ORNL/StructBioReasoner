# Two-Tier Prompting Strategy

## Overview

The StructBioReasoner uses a **two-tier prompting architecture** to separate high-level decision-making from detailed parameter configuration. This design pattern improves LLM reliability and enables human-in-the-loop intervention between steps.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Step 1: RECOMMENDATION PROMPT (What to do next?)          │
│  - Evaluates current results                                │
│  - Recommends next task: computational_design, MD, FE, stop │
│  - Provides rationale and confidence                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 2: PLANNING PROMPT (How to configure it?)            │
│  - Takes recommendation from Step 1                         │
│  - Generates specific tool configuration                    │
│  - Returns JSON config for execution                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Step 1: Recommendation Prompts

These prompts evaluate results and decide **which task** to execute next.

### 1.1 After `computational_design` (BindCraft)

**Purpose:** Evaluate binder generation success and recommend next validation step.

**Prompt Template:**
```
You are an expert in computational peptide design optimization. Evaluate the current optimization progress and recommend the next task.

BINDCRAFT OPTIMIZATION RESULTS:
- Total rounds completed: {num_rounds}
- Total sequences generated: {total_sequences}
- Passing sequences: {passing_sequences}
- Passing structures: {passing_structures}
- Top 5 binders: {top_binders_json}

HISTORY OF DECISIONS (least recent first): {decision_history}
HISTORY OF RESULTS (least recent first): {results_history}
HISTORY OF CONFIGURATIONS (least recent first): {config_history}
KEY ITEMS TO CONSIDER: {key_items}

AVAILABLE NEXT STEPS:
1. computational_design - Run more BindCraft optimization rounds
2. molecular_dynamics - Validate binders with MD simulations
3. free_energy - Calculate binding free energies
4. stop - Sufficient optimization achieved

Please provide your recommendation in JSON format:
{
    "next_task": "computational_design|molecular_dynamics|free_energy|stop",
    "rationale": "detailed explanation of why this is the best next step",
    "confidence": 0.0-1.0
}
```

**Example Output:**
```json
{
    "next_task": "molecular_dynamics",
    "rationale": "The computational_design stage has produced several high-scoring binders (energy ~ -55) but RMSD and dynamic stability have not been evaluated. MD simulations are the logical next step to verify stable complex formation.",
    "confidence": 0.85
}
```

---

### 1.2 After `molecular_dynamics`

**Purpose:** Evaluate MD trajectory completion and recommend analysis or free energy calculation.

**Prompt Template:**
```
You are an expert in computational peptide design optimization and MD simulations. Evaluate the current optimization progress and decide which step to take next ('analysis', 'free_energy').

Previous round results: {md_results}
History of decisions: {decision_history}
History of results: {results_history}
History of configurations: {config_history}
Key items to consider: {key_items}

AVAILABLE NEXT STEPS:
1. analysis - Analyze MD trajectories (RMSD, RMSF, hotspot contacts)
2. free_energy - Calculate binding free energies
3. computational_design - Generate new binders

Provide recommendation in JSON format.
```

**Example Output:**
```json
{
    "next_task": "analysis",
    "rationale": "MD simulations completed 20,000 steps for 50 trajectories. Should evaluate RMSD, RMSF, and hotspot contacts before free-energy calculations.",
    "confidence": 0.90
}
```

---

### 1.3 After `analysis`

**Purpose:** Evaluate stability metrics and recommend free energy or redesign.

**Prompt Template:**
```
You are an expert in evaluating MD simulation analyses. Evaluate the analyses here and decide what step should be taken next.

The following analyses have generated the following statistics:
{analysis_statistics}

History of decisions: {decision_history}
History of results: {results_history}

AVAILABLE NEXT STEPS:
1. free_energy - Calculate binding affinities
2. computational_design - Redesign based on stability issues
3. stop - Sufficient validation achieved

Provide recommendation in JSON format.
```

---

### 1.4 After `free_energy`

**Purpose:** Evaluate binding affinities and decide whether to iterate or stop.

**Prompt Template:**
```
You are an expert in evaluating free energy calculations, especially MM-PBSA. Evaluate the following results and decide whether to use current binders for next round or access new scaffold.

Results: {free_energy_results}

Inform the scaffold to use 'affibody', 'affitin', or 'use_top_binders'. Only suggest 'use_top_binders' if previous binders produced good free energies.

AVAILABLE NEXT STEPS:
1. computational_design - Generate new round with specified scaffold
2. stop - Achieved target affinity

Provide recommendation in JSON format with scaffold choice in rationale.
```

**Example Output:**
```json
{
    "next_task": "computational_design",
    "rationale": "MM-PBSA produced strong binding energies (-100 to -200 kcal/mol). Should seed next round with 'use_top_binders' to refine these candidates.",
    "confidence": 0.88
}
```

---

## Step 2: Planning Prompts

These prompts generate **specific configurations** for the recommended task.

### 2.1 For `molecular_dynamics`

**Purpose:** Determine simulation length based on workflow stage.

**Prompt Template:**
```
You are an expert in setting up molecular dynamics simulations. Evaluate the following history and decide how long to run the simulations.

Instructions:
- At the beginning: run shorter simulations (10,000 to 50,000 steps) to test setup
- Once enough binders identified: run longer simulations (1,000,000 to 2,500,000 steps) for statistics

History of decisions: {decision_history}
History of results: {results_history}
History of configurations: {config_history}
Key items to consider: {key_items}

Provide response in format:
{
  "simulation_paths": ["list", "of", "pdb", "paths"],
  "root_output_path": "str",
  "steps": int
}
```

**Example Output:**
```json
{
  "simulation_paths": ["/path/to/seq_0.pdb", "/path/to/seq_1.pdb", ...],
  "root_output_path": "/lus/flare/.../molecular_dynamics/1",
  "steps": 20000
}
```

---

### 2.2 For `analysis`

**Purpose:** Choose analysis type (static vs dynamic, basic vs advanced).

**Prompt Template:**
```
You are an expert in molecular dynamics analysis. Evaluate the recommendation and decide which analysis to perform.

RECOMMENDATION FROM PREVIOUS RUN: {previous_task}
Task: analyze
Rationale: {rationale}

Input types ('data_type'):
  static: performed on PDBs
  dynamic: performed on simulation trajectories

Rigor ('analysis_type'):
  static, basic: interface contacts
  dynamic, basic: RMSD, RMSF, radius of gyration
  dynamic, advanced: hotspot analysis (residue interaction frequencies)
  dynamic, both: all dynamic analyses

Output format:
{
  "data_type": "static|dynamic",
  "analysis_type": "basic|advanced|both"
}
```

**Example Output:**
```json
{
  "data_type": "dynamic",
  "analysis_type": "both"
}
```

---

### 2.3 For `free_energy`

**Purpose:** Configure free energy calculation (typically uses defaults).

**Prompt Template:**
```
Run free energy with default configs
```

**Example Output:**
```json
{
  "next_task": "run_free_energy",
  "new_config": {"simulation_paths": ["configs/free_energy/default.yaml"]},
  "rationale": "Using default MM-PBSA configuration"
}
```

---

### 2.4 For `computational_design`

**Purpose:** Configure BindCraft parameters including scaffold choice.

**Prompt Template:**
```
You are an expert in computational peptide design optimization. Generate the next configuration.

RECOMMENDATION FROM PREVIOUS RUN ({previous_task}):
Task: computational_design
Rationale: {rationale}

HISTORY OF DECISIONS: {decision_history}
HISTORY OF RESULTS: {results_history}
HISTORY OF CONFIGURATIONS: {config_history}

Provide configuration in format:
{
  "binder_sequence": "str (if use_top_binders)",
  "num_rounds": int,
  "batch_size": int,
  "scaffold": "affibody|affitin|use_top_binders",
  "constraint": {...}
}
```

---

## Benefits of Two-Tier Architecture

1. **Separation of Concerns:** "What" vs "How" decisions are independent
2. **Human-in-the-Loop:** Can intervene between recommendation and execution
3. **Improved Reliability:** Smaller, focused prompts reduce hallucination
4. **Auditability:** Clear decision trail with rationales
5. **Flexibility:** Can swap recommendation logic without changing planning

