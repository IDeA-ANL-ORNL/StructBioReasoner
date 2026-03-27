# OpenClaw AKV Branch — Changes and Implementation Roadmap

Branch: `openclaw_akv` (based on `openclaw-structbioreasoner`)

## What Changed

### 1. MCP Server — Real Transport + Human-in-the-Loop

**File:** `struct_bio_reasoner/mcp/server.py`

The MCP server previously had no working transport — `main()` just printed JSON and exited. It now implements full stdio transport using the official `mcp` Python SDK. Any MCP client (OpenClaw, Claude Code, a web UI) can launch `python -m struct_bio_reasoner.mcp.server` as a subprocess and communicate via JSON-RPC over stdin/stdout.

#### New MCP Tools (15 total, up from 9)

| Tool | Category | Purpose |
|------|----------|---------|
| `send_directive` | Human-in-the-loop | Inject steering instructions mid-campaign (with priority and category) |
| `get_campaign_status` | Human-in-the-loop | Research goal, elapsed time, tasks submitted/completed, pending directives |
| `get_pending_directives` | Human-in-the-loop | View queued directives not yet consumed by the reasoner |
| `get_queue_status` | Orchestration | Pending/running counts, per-executor breakdown, running tool names |
| `reprioritize_task` | Orchestration | Change priority of a pending task (0=critical, 1=high, 2=default, 3=low) |
| `cancel_task` | Orchestration | Cancel a pending task by ID |

#### Directive Injection

When `jnana_recommend_action` is called, pending directives are automatically popped from the inbox and appended to the LLM's `previous_conclusion` context as:

```
[HUMAN DIRECTIVE (high)]: Focus on hydrophobic hotspots
```

The reasoner sees them on its next decision cycle. Directives support priority levels (`low`, `normal`, `high`, `urgent`) and categories (`focus_change`, `parameter_override`, `add_constraint`, `remove_constraint`, `reprioritize`, `stop`, `other`).

#### Backwards Compatibility

A `StructBioReasonerMCPServer` wrapper class preserves the old `list_tools()` / `call_tool()` API used by tests. All 59 existing tests pass unchanged.

---

### 2. Executor Mapping and Data Model

**File:** `struct_bio_reasoner/academy/executors.py` (new)

Leaf module with no external dependencies. Defines the data model that all orchestration modules import from.

#### Tool-to-Executor Mapping

Every skill is mapped to either a GPU executor (`tool_gpu`) or CPU-only (`None`):

| Executor | Skills |
|----------|--------|
| `tool_gpu` | bindcraft, folding, structure_prediction, md, simulation, molecular_dynamics, protein_lm |
| CPU-only | rag, literature, hiperrag, conservation, trajectory_analysis, clustering |

#### Priority Levels

| Priority | Value | Skills |
|----------|-------|--------|
| Critical | 0 | folding, structure_prediction |
| High | 1 | md, simulation, molecular_dynamics, trajectory_analysis, clustering |
| Default | 2 | bindcraft, binder_design, protein_lm |
| Low | 3 | rag, literature, hiperrag, conservation |

#### Preconditions

Tool-specific preconditions checked before dispatch:

- `md` / `simulation` / `molecular_dynamics` — requires at least 1 artifact with `structure_path`
- `trajectory_analysis` / `clustering` — requires at least 1 artifact with `trajectory_path`

#### Group-Analysis Triggers (`TOOL_GROUP_BETA`)

After N results from the same tool/batch accumulate, the reasoner is triggered to analyse them as a group:

| Tool | Threshold |
|------|-----------|
| bindcraft / binder_design | 10 |
| folding | 5 |
| md | 3 |
| protein_lm | 10 |

#### Data Classes

- **`TaskNode`** — Graph metadata: task_id, tool_name, depth, parent_id, priority. `effective_priority()` falls back to `DEFAULT_TOOL_PRIORITIES` when no explicit priority is set.
- **`QueueItem`** — Sortable priority queue entry with FIFO tie-breaking and retry count.
- **`TaskResult`** — Result wrapper with tool_name and duration_seconds.

---

### 3. Priority Frontier

**File:** `struct_bio_reasoner/academy/frontier.py` (new)

Ported from AgenticFramework's `bindify/core/frontier.py`. Decouples *deciding to run a task* from *submitting it to Parsl*.

#### Core Design: Per-Executor Backlogs

Each executor label gets its own priority heap. When `_fill()` runs, it iterates over all backlogs and only pops tasks whose executor has capacity. A burst of GPU tasks no longer blocks CPU tasks that could run on idle workers.

#### API

| Method | Description |
|--------|-------------|
| `enqueue(tool_name, config, node)` | Add to correct per-executor backlog |
| `drain()` | Async generator yielding `(TaskResult, TaskNode)` as each task completes |
| `cancel_pending(task_id)` | Cancel a pending (not yet running) task |
| `reprioritize(task_id, new_priority)` | Change priority via lazy deletion + re-insert |
| `status_snapshot()` | JSON-serializable status dict for MCP tools |
| `pending_count` / `running_count` / `is_empty` | Status properties |

#### Scheduling Flow

```
enqueue() → per-executor heap
                │
_fill() ────────┤  (called at start of each drain() iteration)
                │  for each executor backlog:
                │    while heap AND global_running < max_concurrent AND executor_has_capacity:
                │      pop highest-priority entry → submit to RoundRobinParslPool
                │
drain() ────────┤  asyncio.wait(FIRST_COMPLETED)
                │  yield (TaskResult, TaskNode) for each completed task
                │  caller enqueues child tasks between yields
                │
                └─ exits when all backlogs empty AND running set empty
```

---

### 4. Orchestration Agents

**File:** `struct_bio_reasoner/academy/orchestration.py` (new)

Ported from AgenticFramework's `bindify/core/orchestration.py`. All use Academy's `@action` / `@loop` decorators.

#### CoordinatingAgent

Validates preconditions and hydrates configs before enqueueing.

```
submit_task_type(tool_name, config, ...)
  ├─ _preconditions_met() → query artifact DAG for required artifacts
  ├─ _hydrate() → inject data paths (structure_path, trajectory_path, etc.)
  │               from artifacts into LLM-generated policy config
  └─ execution_handle.enqueue() → forward to ExecutionAgent
```

#### ExecutionAgent

Owns the priority queue and drives submission via a `@loop` polling tick.

```
@loop run()  (called repeatedly by Academy until shutdown)
  ├─ _try_submit() → pop from queue, check executor capacity, submit to pool
  ├─ _collect_completions() → for each done task:
  │     ├─ store result as artifact in DAG
  │     ├─ accumulate in group; if len(group) >= TOOL_GROUP_BETA:
  │     │     trigger reasoner_handle.analyze_group()
  │     └─ log completion
  └─ _handle_failure() → retry up to 3x, then log permanent failure
```

#### ParslAgent

Wraps a single Parsl DataFlowKernel (DFK). One per node to avoid DFK scheduling bottleneck.

- `agent_on_startup()` — loads Parsl DFK (falls back to direct mode if Parsl unavailable)
- `run()` — stays alive via `asyncio.Event().wait()` until Academy shuts it down
- `@action submit(tool_name, config)` — routes to worker via dispatch

#### RoundRobinParslPool

Distributes tasks across ParslAgents with per-executor capacity tracking.

| Method | Description |
|--------|-------------|
| `executor_for_tool(tool_name)` | Returns executor label or `"_ungated"` |
| `executor_has_capacity(tool_name)` | Checks against per-executor limits |
| `submit(tool_name, config)` | Round-robin to next ParslAgent handle |
| `all_outstanding()` | Snapshot of in-flight counts per executor |

---

### 5. Minor Changes

| File | Change |
|------|--------|
| `pyproject.toml` | Added `mcp>=1.0.0` to dependencies |
| `struct_bio_reasoner/academy/__init__.py` | Exports all new classes and data model constants |
| `struct_bio_reasoner/mcp/__init__.py` | Exports `create_server` |
| `tests/conftest.py` | Added `loop` decorator to fake academy module |

---

## Architecture After Changes

```
Human (via OpenClaw / Claude Code / Web UI)
  │
  ├─ send_directive("focus on hydrophobic hotspots")
  ├─ reprioritize_task(task_id, 0)
  ├─ cancel_task(task_id)
  ├─ get_queue_status()
  │
  ▼
MCP Server (stdio transport)
  │
  ├─ jnana_recommend_action() ← directives injected automatically
  │
  ▼
CoordinatingAgent
  ├─ _preconditions_met() → artifact DAG query
  ├─ _hydrate() → inject data paths from artifacts
  └─ execution_handle.enqueue()
       │
       ▼
ExecutionAgent (@loop tick)
  ├─ _try_submit() → check executor capacity → submit to pool
  ├─ _collect_completions() → store artifacts, trigger group analysis
  └─ _handle_failure() → retry up to 3x
       │
       ▼
RoundRobinParslPool → ParslAgent(s) → Parsl DFK → HPC workers
```

---

## Implementation Roadmap

### Stage 1: Campaign Controller (next)

The frontier and orchestration agents exist but nothing calls them yet. Build a `CampaignController` that replaces the synchronous `HybridLoop`:

- Set goal via Jnana
- Get initial recommendations → enqueue via CoordinatingAgent
- `async for result, node in frontier.drain()`: store artifact, check alpha-trigger, check directives, check convergence, enqueue child tasks
- This is the most impactful next step — it connects the frontier to the reasoner and makes the system run parallel campaigns.

### Stage 2: Alpha-Trigger for Reasoner Invocation

Instead of calling the reasoner on every completion, check: `queued_cost < running_cost * alpha`. Only fire the reasoner when the queue is getting thin. Prevents the LLM from becoming the bottleneck while HPC tasks are running. Reference: AgenticFramework's `SupervisorAgent` with `supervisor_poll_interval` + alpha check.

### Stage 3: Config Hydration with Real Artifact Queries

`CoordinatingAgent._hydrate()` currently does basic artifact DAG queries. It needs tool-specific extractor functions (the `TOOL_INPUT_EXTRACTORS` pattern from AgenticFramework) where each tool registers a function that knows how to extract the right data fields from artifacts and inject them into configs.

### Stage 4: Workflow Graph Constraints

Define valid task transitions so the reasoner cannot recommend folding before sequence generation. AgenticFramework does this with `allowed_next_tasks` injected into the LLM prompt. `CampaignPhase.step_sequence` in `hybrid_loop.py` was designed for this but is never enforced.

### Stage 5: Blackboard / Multi-Objective Convergence

Port the Pareto archive, MinHash conflict detection, and convergence criteria from AgenticFramework's `blackboard.py`. Replace the current string-matching convergence with real criteria: coverage threshold, diversity, scaffold representation.

### Stage 6: Database-Backed Persistence

Add a `MockDatabase` / `SQLAlchemyDatabase` abstraction (from AgenticFramework's `bindify/db/`) for campaign, iteration, and binder records. The artifact DAG works for provenance but is awkward for queries like "top-k binders by binding energy". A proper DB makes `_hydrate()` and group-analysis patterns much cleaner.

### Stage 7: Complete Placeholder Workers

Implement `ConservationWorker`, `ProteinLMWorker`, and `TrajectoryAnalysisWorker` with real tool integrations instead of returning stub dicts.
