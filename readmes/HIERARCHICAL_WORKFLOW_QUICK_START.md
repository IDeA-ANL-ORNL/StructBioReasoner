# Hierarchical Workflow - Quick Start Guide

## What is This?

A hierarchical multi-agent system for adaptive binder design that mimics organizational structure:

- **Executive**: Allocates resources, evaluates performance, makes strategic decisions
- **Managers**: Run parallel binder design campaigns, decide task sequences
- **Workers**: Execute tasks (folding, simulation, clustering, design)

## Key Innovation

**Dynamic Resource Allocation**: High-performing Managers get more compute nodes in subsequent rounds, while poor performers get "laid off."

## Quick Start

### 1. Files Created

**Core Implementation**:
- `struct_bio_reasoner/agents/executive/executive_agent.py` - Executive Agent
- `struct_bio_reasoner/agents/manager/manager_agent.py` - Manager Agent
- `struct_bio_reasoner/workflows/hierarchical_workflow.py` - Workflow Orchestrator

**Example & Config**:
- `examples/hierarchical_binder_workflow.py` - Example workflow
- `config/hierarchical_workflow_config.yaml` - Configuration

**Documentation**:
- `readmes/HIERARCHICAL_MULTI_AGENT_WORKFLOW.md` - Architecture overview
- `readmes/HIERARCHICAL_WORKFLOW_IMPLEMENTATION_GUIDE.md` - Implementation details
- `readmes/HIERARCHICAL_WORKFLOW_COMPLETE_GUIDE.md` - Complete guide
- `readmes/HIERARCHICAL_WORKFLOW_DIAGRAM.mmd` - Visual diagram

### 2. Run the Example

```bash
cd /path/to/StructBioReasoner
python examples/hierarchical_binder_workflow.py
```

### 3. What Happens

**Round 1**:
- Executive queries HiPerRAG for strategy
- 5 Managers get 10 nodes each (equal allocation)
- Each Manager runs independent binder campaign
- Executive evaluates performance

**Round 2**:
- Top 3 Managers continue (2 terminated)
- Resources reallocated: 20, 15, 15 nodes
- Best binder from Round 1 seeds new designs
- Managers adapt strategies

**Round 3**:
- Top 2 Managers continue (1 terminated)
- Resources reallocated: 25, 25 nodes
- Best binder from Round 2 seeds new designs
- Final optimization

**Result**:
- Best binder selected across all rounds
- Complete decision history

### 4. Customize

Edit `config/hierarchical_workflow_config.yaml`:

```yaml
hierarchical_workflow:
  total_compute_nodes: 100  # More resources
  num_managers: 10          # More parallel campaigns
  max_rounds: 5             # More rounds
  
  manager:
    stopping_criteria:
      min_binder_affinity: -15.0  # Higher affinity threshold
```

## What Needs to Be Implemented

### High Priority

1. **Clustering Agent** (`struct_bio_reasoner/agents/clustering/clustering_agent.py`)
   - Cluster MD trajectories
   - Extract representative structures

2. **Hotspot Agent Wrapper** (wrap existing `utils/hotspot.py`)
   - Make it compatible with Manager agent interface

3. **LLM Prompts** (add to `prompts/prompts.py`)
   - Executive resource allocation prompts
   - Manager task decision prompts

### Medium Priority

4. **Dynamic Parsl Config** (modify `utils/parsl_settings.py`)
   - Support resource reallocation between rounds

5. **Worker Agent Handles** (modify `workflows/hierarchical_workflow.py`)
   - Convert direct references to Academy handles

### Low Priority

6. **Performance Metrics** (add to workflow)
   - Track detailed metrics
   - Generate performance reports

## Flow Chart Summary

```
Executive 
  ↓
HiPerRAG (literature strategy)
  ↓
Allocate nodes to Managers
  ↓
Managers (parallel campaigns)
  ↓
  For each Manager:
    Decide: What to fold? → Fold
    Decide: What to simulate? → Simulate
    Decide: What to cluster? → Cluster
    Decide: Hotspot strategy? → Analyze hotspots
    Decide: How to design binder? → Design
    Decide: Next task? → Task 1, Task 2, ..., Task N
    Decide: Stop? → Summarize
  ↓
Executive evaluates all Managers
  ↓
Executive decides:
  - Resource reallocation
  - Manager lifecycle (continue/terminate)
  - Best binder for next round
  ↓
Next round (if not max rounds)
  ↓
Final: Best binder overall
```

## Key Concepts

### Resource Allocation
- **Round 1**: Equal allocation
- **Round 2+**: Performance-based allocation
- **Formula**: `nodes = (manager_score / total_score) * total_nodes`

### Manager Lifecycle
- **Continue**: Score > 0.5
- **Terminate**: Score ≤ 0.5
- **Minimum**: Always keep at least 2 Managers

### Performance Score
```python
score = 0.7 * affinity_score + 0.3 * task_efficiency_score
```

### Stopping Criteria (per Manager)
- Max tasks reached (default: 10)
- Good binder found (affinity < -10 kcal/mol)
- LLM decides to stop

## Example Output

```
Round 1:
  Manager 1: 10 nodes → Score: 0.85 → Best affinity: -12.5
  Manager 2: 10 nodes → Score: 0.72 → Best affinity: -9.8
  Manager 3: 10 nodes → Score: 0.65 → Best affinity: -8.2
  Manager 4: 10 nodes → Score: 0.45 → Best affinity: -5.1 [TERMINATED]
  Manager 5: 10 nodes → Score: 0.38 → Best affinity: -4.3 [TERMINATED]

Round 2:
  Manager 1: 20 nodes → Score: 0.92 → Best affinity: -15.2
  Manager 2: 15 nodes → Score: 0.78 → Best affinity: -11.4
  Manager 3: 15 nodes → Score: 0.55 → Best affinity: -9.9 [TERMINATED]

Round 3:
  Manager 1: 25 nodes → Score: 0.95 → Best affinity: -18.7
  Manager 2: 25 nodes → Score: 0.82 → Best affinity: -13.1

Best Binder Overall: Manager 1, Affinity: -18.7 kcal/mol
```

## Next Steps

1. Review `HIERARCHICAL_WORKFLOW_IMPLEMENTATION_GUIDE.md` for detailed implementation
2. Implement Clustering Agent
3. Add LLM prompts for decisions
4. Test with simple protein target
5. Scale up to full workflow

## Questions?

See the complete documentation in:
- `readmes/HIERARCHICAL_WORKFLOW_COMPLETE_GUIDE.md`
- `readmes/HIERARCHICAL_WORKFLOW_IMPLEMENTATION_GUIDE.md`

