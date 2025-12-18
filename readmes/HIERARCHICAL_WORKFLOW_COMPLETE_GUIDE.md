# Hierarchical Multi-Agent Workflow - Complete Guide

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Workflow Flow](#workflow-flow)
4. [Components](#components)
5. [Usage](#usage)
6. [Configuration](#configuration)
7. [Implementation Status](#implementation-status)

## Overview

The Hierarchical Multi-Agent Workflow implements a three-tier adaptive binder design system inspired by organizational management structures:

- **Executive Agent**: CEO-level strategic decision maker
- **Manager Agents**: Department heads running parallel campaigns
- **Worker Agents**: Specialized employees executing tasks

This architecture enables:
- **Dynamic resource allocation** based on performance
- **Parallel exploration** of multiple design strategies
- **Adaptive learning** across rounds
- **Literature-guided strategy** via HiPerRAG

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Executive Agent                         │
│  - Queries HiPerRAG for strategy                            │
│  - Allocates compute nodes to Managers                      │
│  - Evaluates Manager performance                            │
│  - Decides Manager lifecycle (hire/fire)                    │
│  - Selects best binder for next round                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────────┐
        │         Resource Allocation                  │
        │  Manager 1: 15 nodes                        │
        │  Manager 2: 12 nodes                        │
        │  Manager 3: 10 nodes                        │
        │  Manager 4: 8 nodes                         │
        │  Manager 5: 5 nodes                         │
        └─────────────────────────────────────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  Manager 1    │    │  Manager 2    │    │  Manager 3    │
│  Campaign A   │    │  Campaign B   │    │  Campaign C   │
└───────────────┘    └───────────────┘    └───────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────────────────────────────────────────────────┐
│                    Worker Agents                           │
│  - Folding (Chai)                                         │
│  - Simulation (MDAgent)                                   │
│  - Clustering                                             │
│  - Hotspot Analysis                                       │
│  - Binder Design (BindCraft)                             │
└───────────────────────────────────────────────────────────┘
```

## Workflow Flow

### Complete Flow Chart

```
START
  │
  ▼
Executive Agent
  │
  ├─► Query HiPerRAG
  │   └─► Get literature-guided strategy
  │
  ├─► Allocate Resources
  │   └─► Distribute compute nodes to Managers
  │
  ▼
Manager Agents (Parallel Execution)
  │
  ├─► Manager 1 Campaign
  │   ├─► Decide: What to fold?
  │   ├─► Execute: Folding
  │   ├─► Decide: What to simulate?
  │   ├─► Execute: Simulations
  │   ├─► Decide: What to cluster?
  │   ├─► Execute: Clustering
  │   ├─► Decide: Hotspot analysis strategy?
  │   ├─► Execute: Hotspot Analysis
  │   ├─► Decide: How to initiate binder design?
  │   ├─► Execute: Task 1 (binder design or MD)
  │   ├─► Decide: What is next task?
  │   ├─► Execute: Task 2
  │   ├─► ...
  │   ├─► Execute: Task N
  │   ├─► Decide: Stop?
  │   │   ├─► Yes → Summarize Campaign
  │   │   └─► No → Continue
  │   └─► Return: Best binder + history
  │
  ├─► Manager 2 Campaign (similar flow)
  ├─► Manager 3 Campaign (similar flow)
  └─► ...
  │
  ▼
Executive Evaluation
  │
  ├─► Evaluate all Manager results
  ├─► Calculate performance scores
  ├─► Decide Manager lifecycle
  │   ├─► Continue: High performers
  │   └─► Terminate: Low performers
  │
  ├─► Select best binder overall
  │
  ├─► Reallocate resources for next round
  │   ├─► High performers: More nodes
  │   └─► Medium performers: Fewer nodes
  │
  ▼
Next Round?
  ├─► Yes → Return to Manager Agents with:
  │         - New resource allocation
  │         - Best binder as seed
  │         - Reduced Manager pool
  │
  └─► No → Final Results
            └─► Best binder across all rounds
```

### Round-by-Round Evolution

**Round 1:**
- 5 Managers, 10 nodes each (equal allocation)
- All explore different strategies
- Executive evaluates performance

**Round 2:**
- 3 Managers continue (2 terminated)
- Resource reallocation: 20, 15, 15 nodes
- Best binder from Round 1 seeds new designs
- Managers adapt strategies

**Round 3:**
- 2 Managers continue (1 terminated)
- Resource reallocation: 25, 25 nodes
- Best binder from Round 2 seeds new designs
- Final optimization

**Result:**
- Best binder selected from all rounds
- Complete history of decisions and results

## Components

### 1. Executive Agent
**File**: `struct_bio_reasoner/agents/executive/executive_agent.py`

**Key Methods**:
```python
@action
async def query_hiper_rag(research_goal: str) -> dict
    # Query literature for strategic guidance

@action
async def allocate_resources(manager_ids: list, round_num: int, 
                            previous_performance: dict) -> dict
    # Distribute compute nodes based on performance

@action
async def evaluate_managers(manager_results: dict) -> dict
    # Assess Manager performance

@action
async def decide_manager_lifecycle(evaluations: dict, round_num: int) -> dict
    # Decide which Managers continue vs. terminate

@action
async def select_best_binder(manager_results: dict) -> dict
    # Choose best binder for next round
```

### 2. Manager Agent
**File**: `struct_bio_reasoner/agents/manager/manager_agent.py`

**Key Methods**:
```python
@action
async def decide_next_task(current_state: dict) -> str
    # Decide next task: folding, simulation, clustering, etc.

@action
async def execute_folding(params: dict) -> dict
    # Execute protein folding

@action
async def execute_simulation(params: dict) -> dict
    # Execute MD simulation

@action
async def execute_clustering(params: dict) -> dict
    # Cluster trajectories

@action
async def execute_hotspot_analysis(params: dict) -> dict
    # Identify binding hotspots

@action
async def execute_binder_design(params: dict) -> dict
    # Design binder molecules

@action
async def should_stop(history: list) -> bool
    # Decide if campaign is complete

@action
async def summarize_campaign() -> dict
    # Generate campaign summary
```

### 3. Hierarchical Workflow Orchestrator
**File**: `struct_bio_reasoner/workflows/hierarchical_workflow.py`

**Key Methods**:
```python
async def initialize()
    # Initialize all components

async def run(research_goal: str) -> dict
    # Execute complete workflow

async def execute_round(round_num: int, active_managers: list, 
                       seed_binder: dict, research_goal: str) -> dict
    # Execute single round

async def cleanup()
    # Cleanup resources
```

## Usage

### Basic Usage

```python
from struct_bio_reasoner.workflows.hierarchical_workflow import HierarchicalBinderWorkflow

# Initialize workflow
workflow = HierarchicalBinderWorkflow(
    config_path="config/binder_config.yaml",
    jnana_config_path="config/jnana_config.yaml",
    total_compute_nodes=50,
    num_managers=5,
    max_rounds=3
)

# Run workflow
await workflow.initialize()
results = await workflow.run(
    research_goal="Design a binder for NMNAT-2 that disrupts cancer pathways"
)
await workflow.cleanup()
```

### Running the Example

```bash
cd /path/to/StructBioReasoner
python examples/hierarchical_binder_workflow.py
```

## Configuration

See `config/hierarchical_workflow_config.yaml` for full configuration options.

**Key Configuration Sections**:

1. **Executive Settings**: Resource allocation strategy, lifecycle decisions
2. **Manager Settings**: Task sequencing, stopping criteria
3. **Worker Settings**: Folding, simulation, clustering, design parameters
4. **Performance Metrics**: What to track and how to weight

## Implementation Status

### ✅ Completed
- Executive Agent skeleton
- Manager Agent skeleton
- Hierarchical Workflow orchestrator
- Example workflow script
- Configuration file
- Documentation

### ⚠️ Needs Implementation
- Clustering Agent (new component)
- Hotspot Agent wrapper (exists as utility, needs Agent wrapper)
- Worker agent Academy handles (currently using direct references)
- Full LLM prompt templates for decisions
- Performance metrics collection
- Dynamic Parsl resource allocation

### 🔧 Needs Modification
- `BinderDesignSystem`: Add hierarchical mode support
- `prompts.py`: Add Executive and Manager prompts
- `parsl_settings.py`: Add dynamic resource allocation

See `HIERARCHICAL_WORKFLOW_IMPLEMENTATION_GUIDE.md` for detailed implementation steps.

