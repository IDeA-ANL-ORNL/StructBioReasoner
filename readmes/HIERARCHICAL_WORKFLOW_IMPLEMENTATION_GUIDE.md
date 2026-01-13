# Hierarchical Workflow Implementation Guide

## What Needs to Change in Existing Code

This document describes the changes needed to existing StructBioReasoner code to support the hierarchical multi-agent workflow.

## 1. New Components to Create

### 1.1 Executive Agent (`struct_bio_reasoner/agents/executive/executive_agent.py`)
**Status**: NEW FILE NEEDED

**Purpose**: Top-level decision maker for resource allocation and Manager lifecycle

**Key Dependencies**:
- `RAGWrapper` (already exists)
- `academy.agent.Agent` and `academy.manager.Manager`
- LLM interface for decision making

**Methods to Implement**:
```python
class ExecutiveAgent(Agent):
    @action
    async def query_hiper_rag(self, research_goal: str) -> dict
    
    @action
    async def allocate_resources(self, managers: list, total_nodes: int) -> dict
    
    @action
    async def evaluate_managers(self, manager_results: list) -> dict
    
    @action
    async def decide_manager_lifecycle(self, performance: dict) -> dict
    
    @action
    async def select_best_binder(self, manager_results: list) -> dict
```

### 1.2 Manager Agent (`struct_bio_reasoner/agents/manager/manager_agent.py`)
**Status**: NEW FILE NEEDED

**Purpose**: Mid-level coordinator for binder design campaigns

**Key Dependencies**:
- `ChaiAgent` (already exists)
- `MDAgentAdapter` (already exists)
- `BindCraftAgent` (already exists)
- `ClusteringAgent` (needs creation)
- `HotspotAnalyzer` (already exists in utils)
- LLM interface for task decisions

**Methods to Implement**:
```python
class ManagerAgent(Agent):
    @action
    async def decide_next_task(self, current_results: dict) -> str
    
    @action
    async def execute_folding(self, params: dict) -> dict
    
    @action
    async def execute_simulation(self, params: dict) -> dict
    
    @action
    async def execute_clustering(self, params: dict) -> dict
    
    @action
    async def execute_hotspot_analysis(self, params: dict) -> dict
    
    @action
    async def execute_binder_design(self, params: dict) -> dict
    
    @action
    async def should_stop(self, history: list) -> bool
    
    @action
    async def summarize_campaign(self) -> dict
```

### 1.3 Clustering Agent (`struct_bio_reasoner/agents/clustering/clustering_agent.py`)
**Status**: NEW FILE NEEDED

**Purpose**: Cluster MD trajectories to identify representative conformations

**Key Dependencies**:
- MDTraj or similar trajectory analysis library
- Scikit-learn for clustering algorithms

**Methods to Implement**:
```python
class ClusteringAgent:
    async def cluster_trajectories(self, trajectory_paths: list, n_clusters: int) -> dict
    async def extract_representative_structures(self, clusters: dict) -> list
    async def analyze_cluster_populations(self, clusters: dict) -> dict
```

### 1.4 Hierarchical Workflow Orchestrator (`struct_bio_reasoner/workflows/hierarchical_workflow.py`)
**Status**: NEW FILE NEEDED

**Purpose**: Main workflow orchestrator that coordinates Executive and Managers

**Methods to Implement**:
```python
class HierarchicalBinderWorkflow:
    async def initialize(self)
    async def run(self, research_goal: str) -> dict
    async def execute_round(self, round_num: int, seed_binder: dict) -> dict
    async def cleanup(self)
```

## 2. Modifications to Existing Code

### 2.1 BinderDesignSystem (`struct_bio_reasoner/core/binder_design_system.py`)
**Status**: MODIFY EXISTING

**Changes Needed**:
- Add method to support hierarchical workflow mode
- Add resource allocation tracking
- Add Manager registration and lifecycle management

**New Methods to Add**:
```python
class BinderDesignSystem:
    async def enable_hierarchical_mode(self, config: dict):
        """Enable hierarchical multi-agent mode"""
        
    async def register_manager(self, manager_id: str, resources: dict):
        """Register a Manager agent with allocated resources"""
        
    async def get_manager_performance(self, manager_id: str) -> dict:
        """Get performance metrics for a Manager"""
```

### 2.2 Prompt Manager (`struct_bio_reasoner/prompts/prompts.py`)
**Status**: MODIFY EXISTING

**Changes Needed**:
- Add prompts for Executive decision making
- Add prompts for Manager task sequencing
- Add prompts for resource allocation decisions

**New Prompt Types to Add**:
```python
# In config_master or similar
prompts = {
    "executive_resource_allocation": "...",
    "executive_manager_evaluation": "...",
    "manager_task_decision": "...",
    "manager_stopping_criteria": "...",
    "executive_binder_selection": "..."
}
```

### 2.3 Hotspot Utilities (`struct_bio_reasoner/utils/hotspot.py`)
**Status**: MODIFY EXISTING (if needed)

**Current Status**: Already has `get_hotspot_resids_from_simulations()`

**Potential Changes**:
- Ensure it works with Manager agent interface
- Add batch processing for multiple simulations
- Add scoring/ranking of hotspots

### 2.4 Parsl Configuration (`struct_bio_reasoner/utils/parsl_settings.py`)
**Status**: MODIFY EXISTING

**Changes Needed**:
- Support dynamic resource allocation
- Allow Managers to have different resource allocations
- Support resource reallocation between rounds

**New Methods to Add**:
```python
class DynamicResourceSettings:
    def allocate_nodes_to_manager(self, manager_id: str, num_nodes: int):
        """Allocate specific nodes to a Manager"""
        
    def reallocate_resources(self, allocation_map: dict):
        """Reallocate resources across Managers"""
```

## 3. Configuration Files

### 3.1 Hierarchical Workflow Config (`config/hierarchical_workflow_config.yaml`)
**Status**: NEW FILE NEEDED

**Structure**:
```yaml
hierarchical_workflow:
  total_compute_nodes: 50
  num_managers: 5
  max_rounds: 3
  
  executive:
    llm_model: "gpt-4"
    temperature: 0.3
    resource_allocation_strategy: "performance_based"
    
  manager:
    llm_model: "gpt-4"
    temperature: 0.5
    max_tasks_per_campaign: 10
    stopping_criteria:
      min_binder_affinity: -10.0
      max_iterations: 20
      
  agents:
    folding:
      backend: "chai"
      device: "cuda:0"
    simulation:
      backend: "mdagent"
      timesteps: 1000000
    clustering:
      algorithm: "kmeans"
      n_clusters: 5
    binder_design:
      backend: "bindcraft"
      num_designs: 25
```

## 4. Implementation Priority

### Phase 1: Core Infrastructure
1. Create `ExecutiveAgent` skeleton
2. Create `ManagerAgent` skeleton
3. Create `HierarchicalBinderWorkflow` orchestrator
4. Add hierarchical mode to `BinderDesignSystem`

### Phase 2: Agent Implementation
1. Implement `ExecutiveAgent` methods
2. Implement `ManagerAgent` methods
3. Create `ClusteringAgent`
4. Add new prompts to prompt manager

### Phase 3: Resource Management
1. Implement dynamic resource allocation in Parsl settings
2. Add Manager registration and tracking
3. Implement performance metrics collection

### Phase 4: Integration & Testing
1. Create example workflow script
2. Test with simple binder design task
3. Test multi-round execution
4. Test resource reallocation

## 5. Testing Strategy

### Unit Tests
- Test Executive resource allocation logic
- Test Manager task sequencing
- Test clustering algorithms
- Test performance evaluation

### Integration Tests
- Test Executive → Manager communication
- Test Manager → Worker agent communication
- Test resource allocation and reallocation
- Test multi-round workflow

### End-to-End Tests
- Run full hierarchical workflow on test protein
- Verify resource allocation changes between rounds
- Verify Manager lifecycle (termination/continuation)
- Verify best binder selection

## 6. Dependencies

### New Python Packages Needed
```
mdtraj>=1.9.7  # For trajectory clustering
scikit-learn>=1.0.0  # For clustering algorithms
```

### Existing Dependencies (already in project)
- academy (for Agent framework)
- bindcraft (for binder design)
- chai (for folding)
- mdagent (for simulations)

## 7. Timeline Estimate

- **Phase 1**: 2-3 days
- **Phase 2**: 5-7 days
- **Phase 3**: 3-4 days
- **Phase 4**: 3-5 days

**Total**: 13-19 days for full implementation

## 8. Notes

- The hierarchical workflow is designed to be **additive** - it doesn't break existing workflows
- Existing agents (Chai, MDAgent, BindCraft) are reused without modification
- The main new code is the Executive and Manager coordination layer
- Resource allocation is handled through Parsl configuration updates

