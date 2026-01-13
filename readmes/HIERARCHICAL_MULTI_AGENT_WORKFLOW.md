# Hierarchical Multi-Agent Workflow with Dynamic Resource Allocation

## Overview

This document describes a hierarchical multi-agent system for adaptive binder design with dynamic computational resource allocation. The system implements a three-tier architecture:

1. **Executive Agent**: Top-level decision maker that allocates computational resources across managers
2. **Manager Agents**: Mid-level coordinators that manage specific binder design campaigns
3. **Worker Agents**: Specialized agents (folding, simulation, clustering, binder design, etc.)

## Architecture

```
Executive Agent
    ├── HiPerRAG Agent (literature-guided strategy)
    ├── Resource Allocator (distributes compute nodes)
    └── Manager Agents (multiple parallel campaigns)
            ├── Folding Agent
            ├── Simulation Agent
            ├── Clustering Agent
            ├── Hotspot Analysis Agent
            ├── Binder Design Agent
            └── Task Sequencer
```

## Workflow Flow Chart

```
Executive 
    ↓
HiPerRAG Agent (literature-guided initial strategy)
    ↓
Executive (decides resource allocation)
    ↓
Distribute computational nodes to Managers
    ↓
Manager 1, Manager 2, ..., Manager N (parallel campaigns)
    ↓
Each Manager executes:
    1. Folding → What to simulate?
    2. Simulations → What to cluster?
    3. Clustering → Hotspot analysis
    4. Hotspot analysis → How to initiate binder design?
    5. Task 1 (binder design or MD sims)
    6. Task 2 (based on Task 1 results)
    7. ...
    8. Task N (until 'stop' decision)
    ↓
Manager summarizes all decisions and results
    ↓
Executive evaluates all Managers
    ↓
Executive decides:
    - How many nodes does each Manager get for next round?
    - Which Managers continue vs. get "laid off"?
    - Which Manager's best binder becomes seed for next round?
    ↓
Continue another round starting from best binder
```

## Key Features

### 1. Dynamic Resource Allocation
- Executive distributes computational nodes based on Manager performance
- Managers can gain or lose resources between rounds
- Poor-performing Managers can be terminated ("laid off")

### 2. Literature-Guided Strategy
- HiPerRAG provides initial strategy based on scientific literature
- Executive uses RAG insights to inform resource allocation
- Managers can query RAG for domain-specific guidance

### 3. Adaptive Task Sequencing
- Each Manager decides next task based on current results
- Tasks include: folding, MD simulation, clustering, hotspot analysis, binder design
- Managers autonomously decide when to stop their campaign

### 4. Multi-Campaign Parallelism
- Multiple Managers run parallel binder design campaigns
- Different strategies can be explored simultaneously
- Best results compete for resources in next round

### 5. Hierarchical Decision Making
- Executive: Strategic decisions (resource allocation, Manager lifecycle)
- Managers: Tactical decisions (task sequencing, stopping criteria)
- Workers: Operational execution (run simulations, design binders)

## Components

### Executive Agent
**Responsibilities:**
- Query HiPerRAG for literature-guided strategy
- Allocate computational nodes to Managers
- Evaluate Manager performance
- Decide Manager lifecycle (continue, reduce resources, terminate)
- Select best binder for next round

**Key Methods:**
- `query_hiper_rag(research_goal)`: Get literature-guided strategy
- `allocate_resources(managers, total_nodes)`: Distribute compute nodes
- `evaluate_managers(manager_results)`: Assess Manager performance
- `select_best_binder(manager_results)`: Choose top binder for next round
- `decide_manager_lifecycle(manager_performance)`: Continue/terminate Managers

### Manager Agent
**Responsibilities:**
- Execute binder design campaign with allocated resources
- Decide task sequence (folding → simulation → clustering → design)
- Determine stopping criteria
- Summarize campaign results and decisions

**Key Methods:**
- `decide_next_task(current_results)`: Choose next task in sequence
- `execute_task(task_type, params)`: Run folding/simulation/clustering/design
- `should_stop(history)`: Decide if campaign is complete
- `summarize_campaign()`: Generate campaign summary

### Worker Agents
**Existing agents used by Managers:**
- `ChaiAgent`: Protein folding
- `MDAgentAdapter`: Molecular dynamics simulations
- `ClusteringAgent`: Trajectory clustering (needs implementation)
- `HotspotAnalyzer`: Identify binding hotspots
- `BindCraftAgent`: Binder design

## Data Flow

### Round Structure
```python
{
    "round_id": 1,
    "executive_decision": {
        "rag_strategy": "...",
        "resource_allocation": {
            "manager_1": {"nodes": 10, "strategy": "aggressive"},
            "manager_2": {"nodes": 5, "strategy": "conservative"}
        }
    },
    "manager_results": {
        "manager_1": {
            "tasks_executed": [...],
            "best_binder": {...},
            "performance_metrics": {...}
        }
    },
    "next_round_decisions": {
        "continue_managers": ["manager_1"],
        "terminated_managers": ["manager_2"],
        "seed_binder": {...}
    }
}
```

## Usage Example

```python
from struct_bio_reasoner.workflows.hierarchical_workflow import HierarchicalBinderWorkflow

# Initialize workflow
workflow = HierarchicalBinderWorkflow(
    config_path="config/hierarchical_config.yaml",
    total_compute_nodes=50,
    num_managers=5,
    max_rounds=3
)

# Run workflow
results = await workflow.run(
    research_goal="Design a binder for NMNAT-2 that disrupts cancer pathways"
)

# Results contain:
# - All round histories
# - Best binder from each round
# - Resource allocation decisions
# - Manager performance metrics
```

## Configuration

See `config/hierarchical_workflow_config.yaml` for full configuration options.

## Next Steps

See `HIERARCHICAL_WORKFLOW_IMPLEMENTATION_GUIDE.md` for implementation details.

