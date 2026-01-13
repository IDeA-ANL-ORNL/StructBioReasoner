# Agentic Loop Implementation - Notes and Required Changes

## Overview

The agentic while loop has been implemented in `nmnat2_agentic_binder_workflow.py` (lines 159-388). This document outlines potential changes needed in other files.

## Implementation Summary

### What Was Implemented

1. **Iteration 0 (Hardcoded)**:
   - Task: `computational_design` (BindCraft)
   - Configuration: Default values with affibody scaffold
   - No LLM decision-making

2. **Iteration 1+ (LLM-Guided)**:
   - Step 1: `system.generate_recommendation()` → decides next task
   - Step 2: `system.generate_recommendedconfig()` → decides configuration
   - Step 3: Execute task with new configuration
   - Step 4: Loop back to Step 1

3. **Task Execution**:
   - `computational_design`: Runs BindCraft
   - `molecular_dynamics`: Runs MD simulations
   - `free_energy`: Runs free energy calculations
   - `stop`: Exits loop and generates final report

4. **History Tracking**:
   - Uses `system.append_history()` to track:
     - `key_items`: Important results
     - `decision`: Task chosen
     - `configuration`: Config used
     - `results`: Full results

## Potential Issues and Required Changes

### 1. BindCraftPromptManager.running_prompt()

**Current Issue**: The prompt expects `recommendation.metadata['next_task']` but the recommendation might be a dict, not an object with metadata.

**Location**: `struct_bio_reasoner/prompts/prompts.py`, lines 116-131

**Suggested Fix**:

```python
def running_prompt(self):
    # Handle both dict and object formats
    if isinstance(self.recommendation, dict):
        next_task = self.recommendation.get('next_task', 'unknown')
        rationale = self.recommendation.get('rationale', 'No rationale provided')
    else:
        next_task = getattr(self.recommendation, 'metadata', {}).get('next_task', 'unknown')
        rationale = getattr(self.recommendation, 'metadata', {}).get('rationale', 'No rationale provided')
    
    # Serialize history for better readability
    decisions_str = json.dumps(self.history.get('decisions', []), indent=2, default=str)
    results_str = json.dumps(self.history.get('results', []), indent=2, default=str)
    configs_str = json.dumps(self.history.get('configurations', []), indent=2, default=str)
    key_items_str = json.dumps(self.history.get('key_items', []), indent=2, default=str)
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

### 2. BindCraftPromptManager.conclusion_prompt()

**Current Issue**: Expects specific keys in `input_json` that might not exist.

**Location**: `struct_bio_reasoner/prompts/prompts.py`, lines 133-145

**Suggested Fix**:

```python
def conclusion_prompt(self):
    # Safely extract values with defaults
    num_rounds = self.input_json.get('rounds_completed', self.input_json.get('num_rounds', 1))
    total_sequences = self.input_json.get('total_sequences_generated', 100)
    passing_sequences = self.input_json.get('total_sequences_filtered', 0)
    passing_structures = self.input_json.get('total_structures_passing', passing_sequences)
    
    # Extract top binders safely
    top_binders = {}
    if 'all_cycles' in self.input_json and num_rounds in self.input_json['all_cycles']:
        cycle_data = self.input_json['all_cycles'][num_rounds]
        # Sort by energy if available
        if cycle_data and isinstance(cycle_data, dict):
            sorted_binders = sorted(
                cycle_data.items(),
                key=lambda x: x[1].get('energy', float('inf')) if isinstance(x[1], dict) else float('inf')
            )[:5]
            top_binders = dict(sorted_binders)
    
    # Serialize for better readability
    top_binders_str = json.dumps(top_binders, indent=2, default=str)
    history_str = json.dumps(self.history_list[:self.num_history], indent=2, default=str)
    research_goal_excerpt = self.research_goal[:200] + "..." if len(self.research_goal) > 200 else self.research_goal
    
    prompt = f"""
    You are an expert in computational peptide design optimization. Evaluate the current optimization progress and decide which step to take next (computational_design, molecular_dynamics, free_energy, or stop).
    
    If you choose computational_design, should we use a binder that was already generated as the starting point, or use a scaffold from the research goal?
    
    BINDCRAFT OPTIMIZATION RESULTS:
    - Total rounds completed: {num_rounds}
    - Total sequences generated: {total_sequences}
    - Passing sequences: {passing_sequences}
    - Passing structures: {passing_structures}
    - Top 5 binders:
    {top_binders_str}
    
    RESEARCH GOAL (excerpt):
    {research_goal_excerpt}
    
    HISTORY OF DECISIONS (least recent first):
    {history_str}
    
    Please provide your decision and reasoning. Include:
    1. next_task: One of ['computational_design', 'molecular_dynamics', 'free_energy', 'stop']
    2. rationale: Detailed explanation of your decision
    3. confidence: Confidence score (0.0 to 1.0)
    """
    return prompt
```

### 3. system.generate_recommendation()

**Current Behavior**: Returns a list of recommendation objects/dicts.

**Expected by Workflow**: Returns a list where first element is a dict with keys:
- `next_task`: str
- `rationale`: str
- `confidence`: float

**Verification Needed**: Check if the return format matches expectations.

**Location**: `struct_bio_reasoner/core/binder_design_system.py`, lines 655-692

**Suggested Verification**:

```python
# In the workflow, after calling generate_recommendation:
recommendation_list = await system.generate_recommendation(
    results=previous_results,
    runtype=previous_task
)

# Verify format
if recommendation_list:
    rec = recommendation_list[0]
    print(f"Recommendation type: {type(rec)}")
    print(f"Recommendation keys: {rec.keys() if isinstance(rec, dict) else 'Not a dict'}")
    print(f"Recommendation: {rec}")
```

### 4. system.generate_recommendedconfig()

**Current Behavior**: Returns a list of config objects/dicts.

**Expected by Workflow**: Returns a list where first element is a dict matching `config_master['computational_design']` schema.

**Location**: `struct_bio_reasoner/core/binder_design_system.py`, lines 694-713

**Suggested Verification**:

```python
# In the workflow, after calling generate_recommendedconfig:
recommended_config_list = await system.generate_recommendedconfig(
    previous_run_type=previous_task,
    previous_run_config=previous_config,
    recommendation=recommendation
)

# Verify format
if recommended_config_list:
    config = recommended_config_list[0]
    print(f"Config type: {type(config)}")
    print(f"Config keys: {config.keys() if isinstance(config, dict) else 'Not a dict'}")
    print(f"Config: {json.dumps(config, indent=2, default=str)}")
```

### 5. config_master Schema

**Current Schema** (`struct_bio_reasoner/prompts/prompts.py`, lines 20-31):

```python
'computational_design': {
    "binder_sequence": 'string',
    'num_rounds': 'int',
    'batch_size': 'int', 
    'max_retries': 'int', 
    'sampling_temp': 'float', 
    'qc_kwargs': {
        'max_repeat': 'int', 
        'max_appearance_ratio': 'float', 
        'max_charge': 'int', 
        'max_charge_ratio': 'float', 
        'max_hydrophobic_ratio': 'float', 
        'min_diversity': 'int'
    }
}
```

**Potential Addition**: Add `next_task` and `rationale` to recommendation schema:

```python
'recommendation': {
    'next_task': 'string',  # One of: computational_design, molecular_dynamics, free_energy, stop
    'rationale': 'string',
    'confidence': 'float'
}
```

## Testing Checklist

- [ ] Verify `system.generate_recommendation()` returns correct format
- [ ] Verify `system.generate_recommendedconfig()` returns correct format
- [ ] Test iteration 0 (hardcoded) executes successfully
- [ ] Test iteration 1+ (LLM-guided) makes reasonable decisions
- [ ] Verify history tracking works correctly
- [ ] Test all task types: computational_design, molecular_dynamics, free_energy
- [ ] Test stop condition works
- [ ] Verify final report generation

## Example Test Run

```python
# Add debug logging to verify formats
logger.info(f"Recommendation: {json.dumps(recommendation, indent=2, default=str)}")
logger.info(f"Config: {json.dumps(current_config, indent=2, default=str)}")
logger.info(f"History: {json.dumps(system.history, indent=2, default=str)}")
```

## Summary

The agentic loop is implemented and should work, but you may need to:

1. **Update `BindCraftPromptManager.running_prompt()`** to handle dict vs object recommendations
2. **Update `BindCraftPromptManager.conclusion_prompt()`** to safely extract values
3. **Verify** `generate_recommendation()` and `generate_recommendedconfig()` return formats
4. **Add JSON serialization** to all prompts for better LLM readability
5. **Test** with actual system to verify integration

All changes should be made to `struct_bio_reasoner/prompts/prompts.py` only - no changes needed to the workflow file itself!

