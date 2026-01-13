# Required Changes to prompts.py for Agentic Loop

## Change 1: Update BindCraftPromptManager.running_prompt()

**File**: `struct_bio_reasoner/prompts/prompts.py`  
**Lines**: 116-131

### Current Code:
```python
def running_prompt(self):
    prompt = f"""
    You are an expert in computational peptide design optimization. Evaluate the current optimization progress and decide whether to continue optimization or proceed to validation.

    RECOMMENDATION FROM PREVIOUS RUN ({self.previous_run_type}):
    run {self.recommendation.metadata['next_task']} for this reason: {self.recommendation.metadata['rationale']}
    This is the history of decisions (least recent first):
    {self.history['decisions'] if self.history['decisions'] != [] else 'No history'}
    and the history of results (least recent first):
    {self.history['results'] if self.history['results'] != [] else 'No history'}
    and the history of configurations (least recent first):
    {self.history['configurations'] if self.history['configurations'] != [] else 'No history'}.
    There are a few very important items to consider encoded here:
    {self.history['key_items']}
    Please provide your decision and reasoning as a json format with the following format: {config_master['computational_design']}"""
    return prompt
```

### Replacement Code:
```python
def running_prompt(self):
    # Handle both dict and object formats for recommendation
    if isinstance(self.recommendation, dict):
        next_task = self.recommendation.get('next_task', 'unknown')
        rationale = self.recommendation.get('rationale', 'No rationale provided')
    else:
        next_task = getattr(self.recommendation, 'metadata', {}).get('next_task', 'unknown')
        rationale = getattr(self.recommendation, 'metadata', {}).get('rationale', 'No rationale provided')
    
    # Serialize history components for better LLM readability
    decisions_str = json.dumps(
        self.history.get('decisions', []) if self.history.get('decisions') else [],
        indent=2,
        default=str
    )
    results_str = json.dumps(
        self.history.get('results', []) if self.history.get('results') else [],
        indent=2,
        default=str
    )
    configs_str = json.dumps(
        self.history.get('configurations', []) if self.history.get('configurations') else [],
        indent=2,
        default=str
    )
    key_items_str = json.dumps(
        self.history.get('key_items', []) if self.history.get('key_items') else [],
        indent=2,
        default=str
    )
    config_schema_str = json.dumps(config_master['computational_design'], indent=2)
    
    prompt = f"""
    You are an expert in computational peptide design optimization. Evaluate the current optimization progress and decide whether to continue optimization or proceed to validation.

    RECOMMENDATION FROM PREVIOUS RUN ({self.previous_run_type}):
    Run {next_task} for this reason: {rationale}
    
    HISTORY OF DECISIONS (least recent first):
    {decisions_str}
    
    HISTORY OF RESULTS (least recent first):
    {results_str}
    
    HISTORY OF CONFIGURATIONS (least recent first):
    {configs_str}
    
    KEY ITEMS TO CONSIDER:
    {key_items_str}
    
    Please provide your decision and reasoning in JSON format with the following schema:
    {config_schema_str}
    """
    return prompt
```

---

## Change 2: Update BindCraftPromptManager.conclusion_prompt()

**File**: `struct_bio_reasoner/prompts/prompts.py`  
**Lines**: 133-145

### Current Code:
```python
def conclusion_prompt(self):
    prompt = f"""
    You are an expert in computational peptide design optimization. Evaluate the current optimization progress and decide which step to take next (bindcraft, md_simulation).
    If you choose to take bindcraft, should we use a binder that was already generated as the starting or use a scaffold in the research goal ({self.research_goal})?
    BINDCRAFT OPTIMIZATION RESULTS:
    - Total rounds completed: {self.num_rounds}
    - Total sequences generated: {self.total_sequences}
    - Passing sequences: {self.passing_sequences}
    - Passing structures: {self.passing_structures}
    - Top 5 binders: {self.top_binders}
    This is the history of decisions (least recent first):
    {self.history_list[:self.num_history]}
    Please provide your decision and reasoning."""
    return prompt
```

### Replacement Code:
```python
def conclusion_prompt(self):
    # Serialize top binders and history for better readability
    top_binders_str = json.dumps(self.top_binders, indent=2, default=str)
    history_str = json.dumps(self.history_list[:self.num_history], indent=2, default=str)
    
    # Truncate research goal if too long
    research_goal_excerpt = self.research_goal[:300] + "..." if len(self.research_goal) > 300 else self.research_goal
    
    prompt = f"""
    You are an expert in computational peptide design optimization. Evaluate the current optimization progress and decide which step to take next.
    
    AVAILABLE NEXT STEPS:
    - computational_design: Run another round of BindCraft optimization
    - molecular_dynamics: Run MD simulations on top candidates
    - free_energy: Calculate binding free energies
    - stop: Optimization complete, finalize results
    
    If you choose computational_design, should we use a binder that was already generated as the starting point, or use a scaffold from the research goal?
    
    BINDCRAFT OPTIMIZATION RESULTS:
    - Total rounds completed: {self.num_rounds}
    - Total sequences generated: {self.total_sequences}
    - Passing sequences: {self.passing_sequences}
    - Passing structures: {self.passing_structures}
    
    Top 5 binders:
    {top_binders_str}
    
    RESEARCH GOAL (excerpt):
    {research_goal_excerpt}
    
    HISTORY OF DECISIONS (least recent first):
    {history_str}
    
    Please provide your decision and reasoning in JSON format with:
    {{
        "next_task": "computational_design|molecular_dynamics|free_energy|stop",
        "rationale": "detailed explanation",
        "confidence": 0.0-1.0
    }}
    """
    return prompt
```

---

## Change 3: Add recommendation schema to config_master

**File**: `struct_bio_reasoner/prompts/prompts.py`  
**Lines**: After line 39 (after 'free_energy' entry)

### Add This:
```python
    'recommendation': {
        'next_task': 'string',  # One of: computational_design, molecular_dynamics, free_energy, stop
        'rationale': 'string',
        'confidence': 'float'
    }
```

### Full config_master with addition:
```python
config_master = {
    'rag': {'prompt': 'string'},

    'rag_output': {'interactions': 'list[string]',
                   'interacting_protein_uniprot_ids': 'list[string]',
                   'cancer_pathways': 'list[string]',
                   'interaction_types': 'list[string]',
                   'therapeutic_rationales': 'list[string]'},

    'computational_design': {
                    "binder_sequence": 'string',
                    'num_rounds': 'int',
                     'batch_size': 'int', 
                     'max_retries': 'int', 
                     'sampling_temp': 'float', 
                     'qc_kwargs': {'max_repeat': 'int', 
                                   'max_appearance_ratio': 'float', 
                                   'max_charge': 'int', 
                                   'max_charge_ratio': 'float', 
                                   'max_hydrophobic_ratio': 'float', 
                                   'min_diversity': 'int'}},

    'structure_prediction': {'sequences_to_fold': 'list[list[str]', 'interacting_protein_name': 'list[str]'},

    'molecular_dynamics': {'paths_to_simulate': 'list[str]', 'root_output_path': 'str', 'steps': 'int'},

    'hotspot': {'paths_to_analyze': 'list[int]'},

    'free_energy': {''},
    
    'recommendation': {
        'next_task': 'string',  # One of: computational_design, molecular_dynamics, free_energy, stop
        'rationale': 'string',
        'confidence': 'float'
    }
}
```

---

## Summary of Changes

1. **BindCraftPromptManager.running_prompt()**: 
   - Handle both dict and object recommendation formats
   - Serialize all history components with `json.dumps()`
   - Better formatting for LLM readability

2. **BindCraftPromptManager.conclusion_prompt()**:
   - Serialize top_binders and history
   - Add clear list of available next steps
   - Request structured JSON output with next_task, rationale, confidence

3. **config_master**:
   - Add 'recommendation' schema for LLM output validation

## Testing

After making these changes, test with:

```python
# Test prompt generation
pm = BindCraftPromptManager(
    research_goal="Design binders...",
    input_json={'rounds_completed': 1, 'total_sequences_generated': 100, ...},
    target_prot="NMNAT-2",
    prompt_type='conclusion',
    history={'decisions': [], 'results': [], 'configurations': [], 'key_items': []},
    num_history=3
)

print(pm.prompt_c)
```

All changes are isolated to `struct_bio_reasoner/prompts/prompts.py` - no other files need modification!

