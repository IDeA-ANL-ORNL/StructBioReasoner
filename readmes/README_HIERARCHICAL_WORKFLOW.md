# Hierarchical Multi-Agent Workflow - Complete Documentation Index

## Overview

This directory contains complete documentation and implementation for a **Hierarchical Multi-Agent Workflow** system for adaptive binder design with dynamic computational resource allocation.

## Quick Navigation

### 🚀 Start Here
- **[Quick Start Guide](HIERARCHICAL_WORKFLOW_QUICK_START.md)** - Fast introduction and getting started
- **[Visual Diagram](HIERARCHICAL_WORKFLOW_VISUAL.txt)** - ASCII art workflow visualization
- **[Summary](HIERARCHICAL_WORKFLOW_SUMMARY.md)** - High-level implementation summary

### 📚 Detailed Documentation
- **[Complete Guide](HIERARCHICAL_WORKFLOW_COMPLETE_GUIDE.md)** - Comprehensive documentation
- **[Architecture Overview](HIERARCHICAL_MULTI_AGENT_WORKFLOW.md)** - System architecture and design
- **[Implementation Guide](HIERARCHICAL_WORKFLOW_IMPLEMENTATION_GUIDE.md)** - What needs to change in existing code

### 📊 Diagrams
- **[Mermaid Diagram](HIERARCHICAL_WORKFLOW_DIAGRAM.mmd)** - Interactive workflow diagram
- **[Visual Flow](HIERARCHICAL_WORKFLOW_VISUAL.txt)** - ASCII art visualization

## File Structure

### Implementation Files

```
struct_bio_reasoner/
├── agents/
│   ├── executive/
│   │   ├── __init__.py
│   │   └── executive_agent.py          # Executive Agent implementation
│   └── manager/
│       ├── __init__.py
│       └── manager_agent.py            # Manager Agent implementation
└── workflows/
    ├── __init__.py
    └── hierarchical_workflow.py        # Workflow orchestrator

examples/
└── hierarchical_binder_workflow.py     # Example workflow script

config/
└── hierarchical_workflow_config.yaml   # Configuration file

readmes/
├── README_HIERARCHICAL_WORKFLOW.md     # This file
├── HIERARCHICAL_WORKFLOW_QUICK_START.md
├── HIERARCHICAL_WORKFLOW_SUMMARY.md
├── HIERARCHICAL_WORKFLOW_COMPLETE_GUIDE.md
├── HIERARCHICAL_MULTI_AGENT_WORKFLOW.md
├── HIERARCHICAL_WORKFLOW_IMPLEMENTATION_GUIDE.md
├── HIERARCHICAL_WORKFLOW_DIAGRAM.mmd
└── HIERARCHICAL_WORKFLOW_VISUAL.txt
```

## Documentation Guide

### For First-Time Users
1. Read **[Quick Start Guide](HIERARCHICAL_WORKFLOW_QUICK_START.md)**
2. View **[Visual Diagram](HIERARCHICAL_WORKFLOW_VISUAL.txt)**
3. Run the example: `python examples/hierarchical_binder_workflow.py`

### For Developers Implementing This
1. Read **[Implementation Guide](HIERARCHICAL_WORKFLOW_IMPLEMENTATION_GUIDE.md)**
2. Review **[Complete Guide](HIERARCHICAL_WORKFLOW_COMPLETE_GUIDE.md)**
3. Study the code in `struct_bio_reasoner/agents/executive/` and `struct_bio_reasoner/agents/manager/`

### For Understanding Architecture
1. Read **[Architecture Overview](HIERARCHICAL_MULTI_AGENT_WORKFLOW.md)**
2. View **[Mermaid Diagram](HIERARCHICAL_WORKFLOW_DIAGRAM.mmd)**
3. Review **[Summary](HIERARCHICAL_WORKFLOW_SUMMARY.md)**

## Key Concepts

### Three-Tier Architecture
1. **Executive Agent**: Strategic resource allocation and Manager lifecycle
2. **Manager Agents**: Tactical task sequencing for binder campaigns
3. **Worker Agents**: Operational execution (folding, simulation, design)

### Dynamic Resource Allocation
- Round 1: Equal allocation across all Managers
- Round 2+: Performance-based allocation
- High performers get more nodes, low performers get terminated

### Literature-Guided Strategy
- HiPerRAG provides initial strategy from scientific literature
- Executive uses RAG insights for resource allocation
- Managers can query RAG for domain-specific guidance

## Workflow Flow

```
Executive → HiPerRAG → Resource Allocation → Managers → Workers → 
Results → Executive Evaluation → Resource Reallocation → Next Round
```

### Detailed Flow
1. Executive queries HiPerRAG for strategy
2. Executive allocates compute nodes to Managers
3. Managers execute parallel binder campaigns
   - Decide: What to fold?
   - Execute: Folding
   - Decide: What to simulate?
   - Execute: Simulations
   - Decide: What to cluster?
   - Execute: Clustering
   - Decide: Hotspot strategy?
   - Execute: Hotspot analysis
   - Decide: How to design binder?
   - Execute: Binder design
   - Decide: Next task?
   - Execute: Tasks until stop
4. Executive evaluates all Managers
5. Executive decides resource reallocation and Manager lifecycle
6. Best binder seeds next round
7. Repeat for max rounds

## What Was Created

### ✅ Complete Implementation
- Executive Agent (full implementation)
- Manager Agent (full implementation)
- Hierarchical Workflow Orchestrator (full implementation)
- Example workflow script
- Configuration file
- Comprehensive documentation

### ⚠️ Needs Additional Work
- Clustering Agent (new component needed)
- Hotspot Agent wrapper (wrap existing utility)
- LLM prompts for decisions (add to prompts.py)
- Dynamic Parsl resource allocation (modify parsl_settings.py)

## Usage Example

```python
from struct_bio_reasoner.workflows.hierarchical_workflow import HierarchicalBinderWorkflow

# Initialize
workflow = HierarchicalBinderWorkflow(
    config_path="config/binder_config.yaml",
    jnana_config_path="config/jnana_config.yaml",
    total_compute_nodes=50,
    num_managers=5,
    max_rounds=3
)

# Run
await workflow.initialize()
results = await workflow.run(
    research_goal="Design a binder for NMNAT-2"
)
await workflow.cleanup()
```

## Configuration

Edit `config/hierarchical_workflow_config.yaml`:

```yaml
hierarchical_workflow:
  total_compute_nodes: 50
  num_managers: 5
  max_rounds: 3
  
  executive:
    resource_allocation:
      strategy: "performance_based"
  
  manager:
    stopping_criteria:
      max_tasks_per_campaign: 10
      min_binder_affinity: -10.0
```

## Next Steps

1. **Implement Clustering Agent**
   - Create `struct_bio_reasoner/agents/clustering/clustering_agent.py`
   - Use MDTraj for trajectory analysis
   - Implement k-means clustering

2. **Add LLM Prompts**
   - Modify `struct_bio_reasoner/prompts/prompts.py`
   - Add Executive decision prompts
   - Add Manager task sequencing prompts

3. **Test Basic Workflow**
   - Run with simple protein target
   - Verify resource allocation
   - Check Manager lifecycle decisions

4. **Implement Dynamic Resources**
   - Modify `struct_bio_reasoner/utils/parsl_settings.py`
   - Add resource reallocation methods
   - Test with Parsl

5. **Scale Up**
   - Test with complex targets
   - Optimize performance
   - Add advanced features

## Documentation Files

| File | Purpose | Audience |
|------|---------|----------|
| `HIERARCHICAL_WORKFLOW_QUICK_START.md` | Fast introduction | New users |
| `HIERARCHICAL_WORKFLOW_SUMMARY.md` | Implementation summary | All users |
| `HIERARCHICAL_WORKFLOW_COMPLETE_GUIDE.md` | Comprehensive guide | Developers |
| `HIERARCHICAL_MULTI_AGENT_WORKFLOW.md` | Architecture overview | Architects |
| `HIERARCHICAL_WORKFLOW_IMPLEMENTATION_GUIDE.md` | Implementation details | Implementers |
| `HIERARCHICAL_WORKFLOW_DIAGRAM.mmd` | Mermaid diagram | Visual learners |
| `HIERARCHICAL_WORKFLOW_VISUAL.txt` | ASCII visualization | Quick reference |

## Questions?

Refer to the appropriate documentation file above, or examine the example code in `examples/hierarchical_binder_workflow.py`.

## License

Same as StructBioReasoner project.

