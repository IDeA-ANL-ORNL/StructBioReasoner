# Hierarchical Workflow - Function Reference Guide

## Quick Function Lookup

This is a quick reference for all functions in the hierarchical workflow system.

---

## HierarchicalBinderWorkflow (12 functions)

### Public Methods

| Function | Type | Description |
|----------|------|-------------|
| `__init__(config_path, jnana_config_path, total_compute_nodes, num_managers, max_rounds)` | sync | Initialize workflow |
| `initialize()` | async | Initialize all components (BinderDesignSystem, Academy Manager, Executive) |
| `run(research_goal)` | async | **Main entry point** - Execute complete workflow |
| `execute_round(round_num, active_managers, seed_binder, research_goal)` | async | Execute single round |
| `cleanup()` | async | Cleanup resources |

### Private Methods

| Function | Type | Description |
|----------|------|-------------|
| `_launch_executive()` | async | Launch Executive Agent |
| `_launch_managers(manager_ids, resource_allocation)` | async | Launch Manager Agents |
| `_prepare_worker_handles()` | async | Prepare worker agent handles |
| `_execute_manager_campaign(manager_id, seed_binder, research_goal)` | async | Execute single Manager campaign |
| `_execute_manager_task(manager_handle, task_type, current_state)` | async | Execute specific task for Manager |
| `_build_task_params(task_type, current_state)` | sync | Build parameters for task |
| `_get_manager_history(manager_handle)` | async | Get task history from Manager |

---

## ExecutiveAgent (8 functions)

### Public Methods (Academy @action)

| Function | Type | Description |
|----------|------|-------------|
| `__init__(rag_handle, llm_interface, total_compute_nodes, config)` | sync | Initialize Executive Agent |
| `query_hiper_rag(research_goal)` | async @action | Query HiPerRAG for strategy |
| `allocate_resources(manager_ids, round_num, previous_performance)` | async @action | Allocate compute nodes to Managers |
| `evaluate_managers(manager_results)` | async @action | Evaluate Manager performance |
| `decide_manager_lifecycle(evaluations, round_num)` | async @action | Decide which Managers continue/terminate |
| `select_best_binder(manager_results)` | async @action | Select best binder across all Managers |

### Private Methods

| Function | Type | Description |
|----------|------|-------------|
| `_performance_based_allocation(manager_ids, performance)` | async | Allocate resources based on performance |
| `_calculate_performance_score(results)` | sync | Calculate performance score for Manager |

---

## ManagerAgent (13 functions)

### Public Methods (Academy @action)

| Function | Type | Description |
|----------|------|-------------|
| `__init__(manager_id, allocated_nodes, worker_handles, llm_interface, config)` | sync | Initialize Manager Agent |
| `decide_next_task(current_state)` | async @action | Decide next task to execute |
| `execute_folding(params)` | async @action | Execute protein folding task |
| `execute_simulation(params)` | async @action | Execute MD simulation task |
| `execute_clustering(params)` | async @action | Execute trajectory clustering task |
| `execute_hotspot_analysis(params)` | async @action | Execute hotspot analysis task |
| `execute_binder_design(params)` | async @action | Execute binder design task |
| `should_stop(history)` | async @action | Decide if campaign should stop |
| `summarize_campaign()` | async @action | Summarize campaign results |

### Private Methods

| Function | Type | Description |
|----------|------|-------------|
| `_record_task(task_type, params, result)` | sync | Record task in history |
| `_build_task_decision_prompt(current_state)` | sync | Build LLM prompt for task decision |
| `_format_task_history()` | sync | Format task history for prompt |
| `_parse_task_decision(llm_response)` | sync | Parse LLM response to extract task |

---

## Function Call Patterns

### Initialization Pattern

```python
workflow = HierarchicalBinderWorkflow(...)
await workflow.initialize()
  └─> BinderDesignSystem.__init__()
  └─> BinderDesignSystem.start()
  └─> Manager.from_exchange_factory()
  └─> workflow._launch_executive()
      └─> academy_manager.launch(ExecutiveAgent)
          └─> ExecutiveAgent.__init__()
```

### Main Execution Pattern

```python
results = await workflow.run(research_goal)
  └─> ExecutiveAgent.query_hiper_rag(research_goal)
  └─> FOR each round:
      └─> workflow.execute_round(...)
          └─> ExecutiveAgent.allocate_resources(...)
          └─> workflow._launch_managers(...)
          └─> asyncio.gather(*manager_campaigns)
              └─> workflow._execute_manager_campaign(...)
                  └─> WHILE not stop:
                      └─> ManagerAgent.decide_next_task(...)
                      └─> workflow._execute_manager_task(...)
                          └─> ManagerAgent.execute_[task_type](...)
                      └─> ManagerAgent.should_stop(...)
                  └─> ManagerAgent.summarize_campaign()
          └─> ExecutiveAgent.evaluate_managers(...)
      └─> ExecutiveAgent.decide_manager_lifecycle(...)
      └─> ExecutiveAgent.select_best_binder(...)
```

### Task Execution Pattern

```python
# Manager decides task
task = await ManagerAgent.decide_next_task(state)
  └─> ManagerAgent._build_task_decision_prompt(state)
  └─> llm.generate(prompt)
  └─> ManagerAgent._parse_task_decision(response)

# Workflow executes task
result = await workflow._execute_manager_task(handle, task, state)
  └─> workflow._build_task_params(task, state)
  └─> ManagerAgent.execute_[task](params)
      └─> worker_handle.[task_method](...)
      └─> ManagerAgent._record_task(task, params, result)
```

---

## Worker Agent Methods (External)

### Existing Agents

| Agent | Method | Description |
|-------|--------|-------------|
| ChaiAgent | `fold_protein(sequence, target_sequence, device)` | Fold protein structure |
| MDAgentAdapter | `run_simulation(pdb_path, timesteps, temperature, solvent)` | Run MD simulation |
| BindCraftAgent | `design_binder(target_sequence, hotspot_residues, scaffold_type, num_designs)` | Design binder |
| RAGWrapper | `rag_with_model(prompt)` | Query HiPerRAG |

### New Agents Needed

| Agent | Method | Description |
|-------|--------|-------------|
| ClusteringAgent | `cluster_trajectories(trajectory_paths, n_clusters, algorithm)` | Cluster trajectories |
| HotspotAgent | `analyze_hotspots(simulation_results, cluster_results, threshold)` | Analyze hotspots |

---

## Function Categories

### Strategic (Executive)
- `query_hiper_rag()` - Get literature strategy
- `allocate_resources()` - Distribute compute nodes
- `evaluate_managers()` - Assess performance
- `decide_manager_lifecycle()` - Continue/terminate decisions
- `select_best_binder()` - Choose best result

### Tactical (Manager)
- `decide_next_task()` - Task sequencing
- `should_stop()` - Stopping criteria
- `summarize_campaign()` - Results summary

### Operational (Manager → Workers)
- `execute_folding()` - Protein folding
- `execute_simulation()` - MD simulations
- `execute_clustering()` - Trajectory clustering
- `execute_hotspot_analysis()` - Hotspot identification
- `execute_binder_design()` - Binder design

### Orchestration (Workflow)
- `initialize()` - Setup
- `run()` - Main execution
- `execute_round()` - Round execution
- `cleanup()` - Teardown

---

## Common Usage Examples

### Basic Workflow

```python
workflow = HierarchicalBinderWorkflow(
    config_path="config/binder_config.yaml",
    jnana_config_path="config/jnana_config.yaml",
    total_compute_nodes=50,
    num_managers=5,
    max_rounds=3
)

await workflow.initialize()
results = await workflow.run("Design binder for NMNAT-2")
await workflow.cleanup()
```

### Access Results

```python
# Overall best binder
best_binder = results['best_binder_overall']

# Round-by-round history
for round_data in results['round_history']:
    print(f"Round {round_data['round_num']}")
    print(f"  Resource allocation: {round_data['resource_allocation']}")
    print(f"  Evaluations: {round_data['evaluations']}")
```

---

## See Also

- **Detailed Flow Diagram**: `HIERARCHICAL_WORKFLOW_DETAILED_FUNCTION_FLOW.txt`
- **Complete Guide**: `HIERARCHICAL_WORKFLOW_COMPLETE_GUIDE.md`
- **Quick Start**: `HIERARCHICAL_WORKFLOW_QUICK_START.md`

