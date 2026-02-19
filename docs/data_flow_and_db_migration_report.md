# StructBioReasoner: Data Flow, LLM/Decision History, and SQL Database Migration Report

> **Scope**: This report covers only `agents/` and `prompts/tasks/` (plus the
> `_registry.py` / `_recommender.py` infrastructure they import). Nothing from
> `core/`, `workflows/`, or `data/` is considered.

## Table of Contents

1. [Current Architecture Overview](#1-current-architecture-overview)
2. [LLM & Decision History: Current State](#2-llm--decision-history-current-state)
3. [Agent Data Flow](#3-agent-data-flow)
4. [Gaps and Pain Points](#4-gaps-and-pain-points)
5. [DB 1 — Decision/LLM History Schema](#5-db-1--decisionllm-history-schema)
6. [DB 2 — Scientific Data Schema](#6-db-2--scientific-data-schema)
7. [DuckDB Integration Strategy](#7-duckdb-integration-strategy)
8. [Parallel LLM/Decision History Treatment](#8-parallel-llmdecision-history-treatment)
9. [DataAgent: A New Database-Managing Agent](#9-dataagent-a-new-database-managing-agent)
10. [Migration Path & Implementation Steps](#10-migration-path--implementation-steps)
11. [Risks and Considerations](#11-risks-and-considerations)

---

## 1. Current Architecture Overview

### 1.1 Agent Hierarchy

```
TestExecutive  (agents/executive/test_executive.py)
   │
   │  Loads Parsl once, launches N LocalDirectors via Academy Manager.
   │  Review loop: polls check_status() periodically.
   │  Signals: time-based shutdown only (no KILL/ADVISE yet).
   │
   ├──► LocalDirector  (extends Director; shares executive's Parsl DFK)
   │
   └──► ...
         │
Director  (agents/director/director_agent.py)
   │
   │  Owns the main agentic_run() while-loop.
   │  Delegates LLM reasoning to ReasonerAgent.
   │  Dispatches work to Worker Agents via AgentRegistry.
   │
   ├──► ReasonerAgent         (agents/language_model/pydantic_ai_agent.py)
   ├──► BindCraftCoordinator  (agents/computational_design/bindcraft_coordinator.py)
   ├──► MDAgent               (agents/molecular_dynamics/MD.py)
   ├──► FEAgent               (agents/molecular_dynamics/mmpbsa_agent.py)
   ├──► ChaiAgent             (agents/structure_prediction/chai_agent.py)
   ├──► GenSLMAgent           (agents/embedding/sampling_agent.py)
   └──► RAGWrapper → RAGAgent (agents/hiper_rag/rag_agent.py)
```

There is also an alternative **role-based expert/critic system** in
`agents/roles/` (`RoleOrchestrator`, `MDSimulationExpert`, `StructurePredictionExpert`,
`MDSimulationCritic`, `StructurePredictionCritic`) but it operates on its own
`workflow_history` dict and is not currently wired into the Director loop.

### 1.2 Key Frameworks

| Framework | Role |
|-----------|------|
| **Academy** | Agent lifecycle (`Agent` base class, `@action` decorators, `Handle` objects, `Manager` for launch) |
| **Parsl** | Distributed task scheduling across HPC accelerators (folding, inverse folding, MD, energy, QC) |
| **pydantic-ai** | Structured LLM output via `PromptedOutput` against OpenAI-compatible endpoints |

### 1.3 AgentRegistry (director_agent.py:18-46)

```python
class AgentRegistry(BaseModel):
    reasoner:  str = '...pydantic_ai_agent:ReasonerAgent'
    bindcraft: str = '...bindcraft_coordinator:BindCraftCoordinator'
    md:        str = '...MD:MDAgent'
    mmpbsa:    str = '...mmpbsa_agent:FEAgent'
    folding:   str = '...chai_agent:ChaiAgent'

    TASK_TO_AGENT: dict[str, str] = {
        'computational_design':  'bindcraft',
        'molecular_dynamics':    'md',
        'structure_prediction':  'folding',
        'free_energy':           'mmpbsa',
        'rag':                   'reasoner',
        'analysis':              'reasoner',
    }
```

The Director calls `agent_registry.resolve_task(task_name)` to translate a
`TaskName` (from the LLM recommendation) into a registry label, then
`agent_registry.get(label)` to dynamically import the agent class.

---

## 2. LLM & Decision History: Current State

### 2.1 History Data Structures

There are **two** active history representations within the `agents/` + `prompts/` scope:

#### A. `WorkflowHistory` (Pydantic model — `models.py:226`)

```python
class WorkflowHistory(BaseModel):
    decisions:      list[dict[str, Any]]
    results:        list[dict[str, Any]]
    configurations: list[dict[str, Any]]
    key_items:      list[dict[str, Any]]
```

This is the **canonical schema** consumed by the prompt system. `from_raw()`
coerces plain dicts and empty lists into this shape. `serialize_history()`
in `prompts/_registry.py` converts each field to a JSON string (or the
fallback `'No history'` / `'No key items yet'`).

#### B. `Director.history` (plain list — `director_agent.py:57`)

```python
self.previous_run = 'starting'
self.history = []
```

On every call to `query_reasoner()`, the Director does:

```python
self.previous_run = data['previous_run']
self.history.append(data['history'])
```

This list grows **unbounded** — there is no maxlen or eviction. Each element
is whatever `data['history']` happened to be (could be a dict, a
`WorkflowHistory`, an empty string, etc.). The entire list is then passed
to the ReasonerAgent on the next iteration.

### 2.2 How History Flows Through the Director Loop

```
Director.agentic_run()                    (director_agent.py:125)
  │
  │  results = {'results': 'none'}
  │
  ▼  while True:
  │
  │  ┌─ reasoner_input = {
  │  │      'results': results,         ← output of last worker
  │  │      'previous_run': self.previous_run,
  │  │      'history': self.history,    ← full accumulated list
  │  │  }
  │  │
  │  ▼
  │  Director.query_reasoner(data)       (director_agent.py:139)
  │    │
  │    │  ① ReasonerAgent.generate_recommendation(results, previous_run, history)
  │    │       → build_prompt_context()          (_registry.py:135)
  │    │           → WorkflowHistory.from_raw(history)
  │    │       → get_conclusion_prompt()         (task-specific)
  │    │       → build_recommender_prompt()      (_recommender.py:10)
  │    │           → json.dumps(history.model_dump())  ← FULL history in prompt
  │    │       → LLM call via pydantic-ai
  │    │       → Returns: RecommendationResult(previous_run, Recommendation)
  │    │
  │    │  ② ReasonerAgent.plan_run(recommendation, history)
  │    │       → build_prompt_context() with next_task
  │    │       → get_running_prompt()            (task-specific)
  │    │       → LLM call via pydantic-ai with PromptedOutput(PlanModel)
  │    │       → Returns: typed Plan (e.g. ComputationalDesignPlan)
  │    │
  │    │  ③ Side effects:
  │    │       self.previous_run = data['previous_run']
  │    │       self.history.append(data['history'])
  │    │
  │    └── Returns: (next_task, plan)
  │
  │  Director.tool_call(tool, plan)      (director_agent.py:157)
  │    │
  │    │  agent_key = self.agent_registry.resolve_task(tool)
  │    │  kwargs = plan.new_config.model_dump()
  │    │  results = await self.agents[agent_key].run(**kwargs)
  │    │
  │    └── Returns: results dict (untyped, agent-specific)
  │
  └── results fed back into next iteration
```

### 2.3 How Task Prompts Consume History

Each task in `prompts/tasks/` receives a `PromptContext` containing a `WorkflowHistory`
and calls `serialize_history()` to embed four JSON sections into the LLM prompt.
The pattern is consistent across tasks:

| Task File | `running()` uses history? | `conclusion()` uses history? | History sections used |
|-----------|:---:|:---:|---|
| `starting.py` | No | No | — (bootstrap, hardcoded recommendation) |
| `computational_design.py` | Yes (`serialize_history`) | Yes (`serialize_history`) | decisions, results, configurations, key_items |
| `molecular_dynamics.py` | Yes (`serialize_history`) | Yes (`serialize_history`) | decisions, results, configurations, key_items |
| `structure_prediction.py` | No | Yes (`history.model_dump()`) | Full history dump as one blob |
| `analysis.py` | No | Yes (`history.model_dump()`) | Full history dump as one blob |
| `free_energy.py` | No (returns static string) | Yes (`serialize_history`) | decisions, results, configurations, key_items |
| `rag.py` | No | No | — (uses `input_json` only) |

Two different serialization approaches are used:
- **`serialize_history(ctx.history)`** — the structured four-section approach (computational_design, molecular_dynamics, free_energy)
- **`json.dumps(ctx.history.model_dump())`** — a single monolithic JSON blob (structure_prediction, analysis)

### 2.4 The Recommender Prompt (`_recommender.py`)

After the task-specific conclusion prompt runs, `build_recommender_prompt()` is
called with the full `WorkflowHistory`. It serializes the **entire** history
object as one JSON blob:

```python
history_str = json.dumps(history.model_dump(), indent=2, default=str)
```

This string is embedded verbatim in the prompt alongside the previous conclusion,
research goal, enabled agents list, and resource summary.

### 2.5 Executive-Level History

The `TestExecutive` (`test_executive.py`) review loop only calls:

```python
status = await handle.check_status()
logger.info("%s status: %s", director_id, status)
```

`Director.check_status()` delegates to:

```python
status = await self.agents['reasoner'].evaluate_history(self.history)
```

Which produces a free-form LLM evaluation of the entire `self.history` list.
The result is logged but **not stored, not acted upon, and not fed back** into
the Director's decision loop. The `simple_executive.py` (unused) version has
stubs for KILL/ADVISE/CONTINUE but passes `history=''` — empty.

### 2.6 Worker Agent History Contributions

Worker agents do **not** write to history. They return results dicts that the
Director feeds into the next `query_reasoner()` call as `data['results']`.
The ReasonerAgent then decides what to put in history via the Pydantic models.

Specifically:

| Worker Agent | `run()` Return Shape | Key Fields |
|---|---|---|
| **BindCraftCoordinator** | `dict` with per-round results | `num_rounds`, `total_sequences`, `passing_sequences`, `passing_structures`, `top_binders` |
| **MDAgent** | `dict` of simulation outputs | Paths to trajectories, simulation metadata |
| **FEAgent** | `dict` of free energy results | MM-PBSA binding free energies |
| **ChaiAgent** | `str` or `list` of fold paths | PDB paths with Chai scores |
| **RAGWrapper** | `ProteinHypothesis` | RAG response text wrapped in hypothesis |

### 2.7 Role System History (Separate, Not Wired In)

The `RoleOrchestrator` in `agents/roles/role_orchestrator.py` maintains its own:

```python
self.workflow_history = []    # completed workflows
self.workflow_metrics = {}    # aggregated stats
```

Each expert/critic role also tracks `performance_history`, `interaction_count`,
and `success_rate`. This system is not connected to the Director loop.

---

## 3. Agent Data Flow

### 3.1 Complete Data Flow Diagram

```
┌───────────────────────────────────────────────────────────────────┐
│                     TestExecutive                                  │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  for each director_handle:                                   │  │
│  │    status = await handle.check_status()  ──► log only       │  │
│  │    (no action taken on status)                               │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                           │ launch                                 │
│                           ▼                                        │
│  ┌──────────────── LocalDirector ──────────────────────────────┐  │
│  │                                                              │  │
│  │  ┌── agentic_run() ──────────────────────────────────────┐  │  │
│  │  │                                                        │  │  │
│  │  │  ┌──────────────┐     ┌────────────────┐              │  │  │
│  │  │  │ previous_run │     │   self.history  │              │  │  │
│  │  │  │  (string)    │     │   (list)        │              │  │  │
│  │  │  └──────┬───────┘     └───────┬────────┘              │  │  │
│  │  │         │                     │                        │  │  │
│  │  │         ▼                     ▼                        │  │  │
│  │  │  ┌─────────────────────────────────────┐              │  │  │
│  │  │  │       query_reasoner()              │              │  │  │
│  │  │  │                                     │              │  │  │
│  │  │  │  ┌─ ReasonerAgent ──────────────┐   │              │  │  │
│  │  │  │  │                              │   │              │  │  │
│  │  │  │  │  generate_recommendation()   │   │              │  │  │
│  │  │  │  │    │                         │   │              │  │  │
│  │  │  │  │    ├─ build_prompt_context() │   │              │  │  │
│  │  │  │  │    ├─ conclusion prompt      │◄──┼── prompts/   │  │  │
│  │  │  │  │    ├─ recommender prompt     │   │   tasks/     │  │  │
│  │  │  │  │    └─ LLM call ─► Recommen-  │   │              │  │  │
│  │  │  │  │                   dation     │   │              │  │  │
│  │  │  │  │                              │   │              │  │  │
│  │  │  │  │  plan_run()                  │   │              │  │  │
│  │  │  │  │    │                         │   │              │  │  │
│  │  │  │  │    ├─ build_prompt_context() │   │              │  │  │
│  │  │  │  │    ├─ running prompt         │◄──┼── prompts/   │  │  │
│  │  │  │  │    └─ LLM call ─► Plan model │   │   tasks/     │  │  │
│  │  │  │  │                              │   │              │  │  │
│  │  │  │  └──────────────────────────────┘   │              │  │  │
│  │  │  │                                     │              │  │  │
│  │  │  │  Side effects:                      │              │  │  │
│  │  │  │    self.history.append(...)          │              │  │  │
│  │  │  │    self.previous_run = ...           │              │  │  │
│  │  │  │                                     │              │  │  │
│  │  │  │  Returns: (next_task, plan)         │              │  │  │
│  │  │  └─────────────────────────────────────┘              │  │  │
│  │  │         │                                              │  │  │
│  │  │         ▼                                              │  │  │
│  │  │  ┌─────────────────────────────────────┐              │  │  │
│  │  │  │       tool_call(task, plan)         │              │  │  │
│  │  │  │                                     │              │  │  │
│  │  │  │  AgentRegistry.resolve_task(task)   │              │  │  │
│  │  │  │           │                         │              │  │  │
│  │  │  │           ▼                         │              │  │  │
│  │  │  │  ┌──────────────────────────────┐   │              │  │  │
│  │  │  │  │  Worker Agent                │   │              │  │  │
│  │  │  │  │  .run(**plan.model_dump())   │   │              │  │  │
│  │  │  │  │                              │   │              │  │  │
│  │  │  │  │  BindCraftCoordinator        │   │              │  │  │
│  │  │  │  │    └─ Chai fold              │   │              │  │  │
│  │  │  │  │    └─ ProteinMPNN inv_fold   │   │              │  │  │
│  │  │  │  │    └─ QC filter              │   │              │  │  │
│  │  │  │  │    └─ Refold                 │   │              │  │  │
│  │  │  │  │    └─ Energy evaluation      │   │              │  │  │
│  │  │  │  │                              │   │              │  │  │
│  │  │  │  │  MDAgent                     │   │              │  │  │
│  │  │  │  │    └─ parsl_build            │   │              │  │  │
│  │  │  │  │    └─ parsl_simulate         │   │              │  │  │
│  │  │  │  │                              │   │              │  │  │
│  │  │  │  │  FEAgent                     │   │              │  │  │
│  │  │  │  │    └─ parsl_mmpbsa           │   │              │  │  │
│  │  │  │  │                              │   │              │  │  │
│  │  │  │  │  ChaiAgent                   │   │              │  │  │
│  │  │  │  │    └─ fold_sequence_task     │   │              │  │  │
│  │  │  │  │                              │   │              │  │  │
│  │  │  │  └──────────┬───────────────────┘   │              │  │  │
│  │  │  │             │ results dict          │              │  │  │
│  │  │  └─────────────┼───────────────────────┘              │  │  │
│  │  │                │                                       │  │  │
│  │  │                ▼                                       │  │  │
│  │  │         results fed back ──► next iteration            │  │  │
│  │  └────────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Types at Each Boundary

| Boundary | Data Shape | Notes |
|----------|-----------|-------|
| **Director → ReasonerAgent (recommend)** | `results: Any`, `previous_run: str`, `history: list` | history is the raw `self.history` list |
| **ReasonerAgent internals** | `WorkflowHistory.from_raw(history)` | Coerces to the canonical Pydantic model |
| **Prompt builder → LLM** | Serialized JSON string in prompt text | Full history dump; grows each iteration |
| **LLM → ReasonerAgent** | `Recommendation(next_task, change_parameters, rationale)` | Validated via `PromptedOutput` |
| **Director → ReasonerAgent (plan)** | `recommendation: RecommendationResult`, `history: list` | Same history passed again |
| **LLM → ReasonerAgent** | Plan Pydantic model (e.g. `ComputationalDesignPlan`) | Validated via `PromptedOutput` |
| **Director → Worker Agent** | `**kwargs` from `plan.new_config.model_dump()` | Fully typed per `Config` model |
| **Worker Agent → Director** | Results dict (untyped) | Structure varies by agent |
| **TestExecutive → Director** | `check_status()` call | Returns `tuple[str]` from LLM |

### 3.3 What Is NOT Persisted

| Data | Current State |
|------|--------------|
| LLM prompts sent | Reconstructed from history each call; never stored |
| LLM raw responses | Only the parsed Pydantic output is retained |
| Token usage / latency | Not tracked |
| Worker intermediate files | Written to disk but paths not tracked in history |
| Executive observations | Logged via `logger.info()` only |
| Cross-Director context | Each Director has isolated history; no sharing mechanism |
| BindCraft per-round metrics | Returned to Director but not accumulated in structured form |

---

## 4. Gaps and Pain Points

### 4.1 Unbounded History Growth

`Director.history` is a plain `list` with no size limit. Every iteration appends
the full `data['history']` object. The entire list is serialized into every LLM
prompt via `json.dumps(history.model_dump())` in `_recommender.py`. For
long-running campaigns (dozens of iterations), this will eventually exceed
the LLM context window and/or waste tokens on stale context.

### 4.2 Weak Type Coercion

`WorkflowHistory.from_raw()` handles `dict`, `list`, and existing instances —
but `Director.history` is a **list of** whatever was appended. When this list
is passed to `from_raw()`, it hits the `isinstance(data, list) and len(data) == 0`
branch only if empty, otherwise falls through to `return cls()` — **discarding
all accumulated history** in the non-empty list case. This means the history
that reaches the prompt builder may not reflect what the Director actually
accumulated.

### 4.3 Inconsistent Serialization in Prompts

Some task prompts use `serialize_history()` (structured four-section approach),
while `structure_prediction.py` and `analysis.py` use `json.dumps(ctx.history.model_dump())`.
This means the LLM sees history formatted differently depending on the task type,
making it harder for it to reason consistently.

### 4.4 No Queryability

History lives in Python objects in memory. There is no way to:
- Query past decisions ("show me all times the LLM recommended MD after a failed fold")
- Aggregate metrics ("average execution time by task type")
- Audit LLM reasoning traces post-hoc
- Compare decision patterns across Directors

### 4.5 No Persistence Across Restarts

If the process crashes, all history is lost. There is no checkpoint/resume
capability for the decision history.

### 4.6 No LLM Call Logging

Raw prompts, raw completions, token counts, latencies, and model parameters are
not recorded anywhere — making debugging and cost tracking impossible.

### 4.7 Executive Is Passive

`TestExecutive` logs status strings but takes no action on them. The
`simple_executive.py` stubs for KILL/ADVISE/CONTINUE pass empty history to the
reasoner. The Executive has no aggregate view of what decisions were made and
why across the fleet of Directors.

### 4.8 Worker Results Are Opaque

Worker agents return untyped `dict` results. The Director passes them straight
to the ReasonerAgent as `results: Any`. There are no structured result models
for MD, free energy, or analysis outputs, making it impossible to programmatically
extract key metrics without parsing free-form dicts.

---

## 5. DB 1 — Decision/LLM History Schema

### 5.1 Why SQL / DuckDB

- **DuckDB** is an embedded analytical database — no server to manage, single-file storage, ideal for append-heavy analytical workloads
- Excellent Python integration (`import duckdb`), supports Parquet export, rich SQL dialect with window functions
- Columnar storage is well-suited for the analytical queries we need (aggregations, time-series over history)
- Can coexist alongside the in-memory data flow without adding network hops
- Each Director process can open a DuckDB connection to the same file for reads

### 5.2 Core Tables

```sql
-- Experiments: top-level container for a TestExecutive run
CREATE TABLE experiments (
    experiment_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_goal       TEXT NOT NULL,
    config_snapshot     JSON,           -- full YAML config at launch time
    num_directors       INTEGER,
    started_at          TIMESTAMPTZ DEFAULT now(),
    ended_at            TIMESTAMPTZ,
    status              TEXT DEFAULT 'running'  -- running | completed | failed
);

-- Directors: one row per Director/LocalDirector instance
CREATE TABLE directors (
    director_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id       UUID REFERENCES experiments(experiment_id),
    external_label      TEXT,           -- 'director_0', 'director_1', etc.
    accelerator_ids     TEXT[],         -- which GPUs this director got
    target_protein      TEXT,
    config_snapshot     JSON,
    launched_at         TIMESTAMPTZ DEFAULT now(),
    terminated_at       TIMESTAMPTZ,
    termination_reason  TEXT            -- completed | killed | timeout | error
);

-- LLM Calls: every call to ReasonerAgent._agent.run()
CREATE TABLE llm_calls (
    call_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    director_id         UUID REFERENCES directors(director_id),
    call_type           TEXT NOT NULL,  -- 'recommendation' | 'plan' | 'evaluation' | 'query'
    model_name          TEXT,           -- e.g. 'openai/gpt-oss-120b'
    prompt_text         TEXT,           -- full prompt sent to LLM
    response_text       TEXT,           -- raw LLM response
    parsed_output       JSON,           -- validated Pydantic model as JSON
    temperature         FLOAT,
    max_tokens          INTEGER,
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    latency_ms          INTEGER,
    error               TEXT,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- Decisions: parsed Recommendation from generate_recommendation()
CREATE TABLE decisions (
    decision_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    llm_call_id         UUID REFERENCES llm_calls(call_id),
    director_id         UUID REFERENCES directors(director_id),
    iteration           INTEGER,        -- loop iteration number
    previous_task       TEXT,           -- task that just completed
    next_task           TEXT NOT NULL,  -- recommended TaskName
    change_parameters   BOOLEAN,
    rationale           TEXT,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- Task Plans: the configuration generated by plan_run()
CREATE TABLE task_plans (
    plan_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id         UUID REFERENCES decisions(decision_id),
    llm_call_id         UUID REFERENCES llm_calls(call_id),
    director_id         UUID REFERENCES directors(director_id),
    task_type           TEXT NOT NULL,  -- TaskName value
    plan_model_name     TEXT,           -- e.g. 'ComputationalDesignPlan'
    plan_config         JSON NOT NULL,  -- plan.new_config.model_dump()
    rationale           TEXT,           -- plan.rationale
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- Task Executions: what actually ran via tool_call() and what came back
CREATE TABLE task_executions (
    execution_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id             UUID REFERENCES task_plans(plan_id),
    director_id         UUID REFERENCES directors(director_id),
    agent_key           TEXT NOT NULL,  -- 'bindcraft' | 'md' | 'folding' | 'mmpbsa'
    status              TEXT DEFAULT 'running',  -- running | completed | failed
    input_kwargs        JSON,           -- the **kwargs sent to agent.run()
    result_data         JSON,           -- full results dict from worker
    error               TEXT,
    started_at          TIMESTAMPTZ DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    duration_ms         INTEGER
);

-- Key Items: important artifacts flagged during the workflow
-- (top binders, hotspot residues, best structures, etc.)
CREATE TABLE key_items (
    item_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    director_id         UUID REFERENCES directors(director_id),
    execution_id        UUID REFERENCES task_executions(execution_id),
    item_type           TEXT,           -- 'top_binder' | 'structure_path' | 'hotspot_residues' | ...
    item_data           JSON NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- Executive Actions: what the Executive did to/about each Director
CREATE TABLE executive_actions (
    action_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id       UUID REFERENCES experiments(experiment_id),
    director_id         UUID REFERENCES directors(director_id),
    llm_call_id         UUID REFERENCES llm_calls(call_id),
    action_type         TEXT NOT NULL,  -- 'continue' | 'advise' | 'kill'
    advice_text         TEXT,
    status_snapshot     TEXT,           -- the check_status() result that triggered this
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- View: reconstruct WorkflowHistory shape for any Director
CREATE VIEW workflow_history_by_director AS
SELECT
    d.director_id,
    (SELECT list(json_object('next_task', dec.next_task,
                              'rationale', dec.rationale,
                              'change_parameters', dec.change_parameters)
                ORDER BY dec.created_at)
     FROM decisions dec WHERE dec.director_id = d.director_id) AS decisions,
    (SELECT list(te.result_data ORDER BY te.completed_at)
     FROM task_executions te
     WHERE te.director_id = d.director_id AND te.status = 'completed') AS results,
    (SELECT list(tp.plan_config ORDER BY tp.created_at)
     FROM task_plans tp WHERE tp.director_id = d.director_id) AS configurations,
    (SELECT list(ki.item_data ORDER BY ki.created_at)
     FROM key_items ki WHERE ki.director_id = d.director_id) AS key_items
FROM directors d;
```

### 5.3 Useful Analytical Queries

```sql
-- Decision frequency by task type
SELECT next_task, COUNT(*) as cnt
FROM decisions GROUP BY next_task ORDER BY cnt DESC;

-- Average execution time by agent
SELECT agent_key, AVG(duration_ms)/1000.0 as avg_seconds
FROM task_executions WHERE status = 'completed'
GROUP BY agent_key;

-- Task transition matrix (what follows what?)
SELECT previous_task, next_task, COUNT(*) as transitions
FROM decisions
GROUP BY previous_task, next_task ORDER BY transitions DESC;

-- LLM token usage over time
SELECT date_trunc('hour', created_at) as hour,
       SUM(prompt_tokens) as prompt_tok, SUM(completion_tokens) as completion_tok
FROM llm_calls GROUP BY hour ORDER BY hour;

-- Per-Director decision history for prompt construction (last N)
SELECT next_task, rationale, change_parameters, created_at
FROM decisions WHERE director_id = ?
ORDER BY created_at DESC LIMIT ?;

-- BindCraft best binders across all Directors in an experiment
SELECT d.external_label, d.target_protein,
       te.result_data->>'top_binders' as top_binders,
       te.completed_at
FROM task_executions te
JOIN directors d ON d.director_id = te.director_id
WHERE d.experiment_id = ? AND te.agent_key = 'bindcraft' AND te.status = 'completed'
ORDER BY te.completed_at DESC;
```

---

## 6. DB 2 — Scientific Data Schema

### 6.1 Motivation: Two Databases, Two Concerns

DB 1 (Section 5) tracks **agent decisions**: what did the LLM say, what plan was
generated, how long did each task take. DB 2 tracks the **scientific artifacts**
those decisions produce: sequences, structures, simulation metrics, free energies,
embeddings.

These are separate concerns because:

- **Different lifecycles**: Decision history is append-only and tied to a single
  experiment run. Scientific data accumulates across experiments — a binder
  sequence discovered in experiment 1 may be reused in experiment 5.
- **Different query patterns**: Decision history is queried temporally ("what
  happened in the last 5 iterations?"). Scientific data is queried by property
  ("show me all sequences with free energy < -12 kcal/mol and RMSD < 2 Å").
- **Different consumers**: Decision history feeds back into the LLM prompt loop.
  Scientific data feeds into analysis notebooks, visualization tools, and
  downstream wet-lab selection.
- **Traceability**: A key goal is to trace a single binder sequence from its
  generation through folding, simulation, analysis, and free energy evaluation.
  This requires a sequence-centric schema, not a decision-centric one.

### 6.2 What Scientific Data Do the Agents Produce?

Auditing each worker agent's return values and internal data structures:

| Agent | Data Produced | Key Fields |
|-------|--------------|------------|
| **BindCraftCoordinator** `run()` | Per-round design results | `sequence`, `structure_path`, `energy` (contact-based), `trial`, `passed_qc` (bool), `passed_energy` (bool) |
| **BindCraftCoordinator** `refold_sequences()` | Per-sequence fold results | `sequence`, `structure_path`, `energy` (null initially), `rmsd` (null initially) |
| **BindCraftCoordinator** `evaluate_structures()` | Energy-evaluated structures | `sequence`, `structure_path`, `energy` (SimpleEnergy contact count) |
| **Chai/ChaiBinder** `__call__()` | Folded structures + Chai scores | `model_path` (PDB), `aggregate_score`, `ptm`, `iptm`, `per_chain_ptm`, `per_chain_pair_iptm`, `has_inter_chain_clashes` |
| **MDAgent** `run()` | Simulation output paths | `sim_path`, `topology_path`, `trajectory_path`, `equil_steps`, `prod_steps`, `solvent_model`, `platform` |
| **FEAgent** `run()` | MM-PBSA free energies | `sim_path`, `free_energy` (kcal/mol), `success` (bool) |
| **TrajectoryAnalysisAgent** `analyze_hypothesis()` | Trajectory statistics | `protein_id`, `rmsd` (mean/std), `rmsf` (per-residue), `radius_of_gyration`, `binding_sites` (contact residues) |
| **GenSLMAgent** `embed_sequences()` | Embedding vectors | `sequence`, `embedding_coords` (high-dim vector) |
| **SequenceQualityControl** `__call__()` | QC pass/fail + per-check results | `sequence`, `passed` (bool), `length`, `diversity`, `net_charge`, `hydrophobic_ratio`, `max_repeat` |

### 6.3 Core Tables

The central entity is a **binder sequence**. Every other measurement is a property
of that sequence observed at a particular stage of the workflow.

```sql
-- ═══════════════════════════════════════════════════════════════════
-- DB 2: Scientific Data  (file: scientific.duckdb)
-- ═══════════════════════════════════════════════════════════════════

-- Sequences: the central entity. One row per unique binder sequence.
CREATE TABLE sequences (
    sequence_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sequence            TEXT NOT NULL,       -- amino acid string
    sequence_hash       TEXT NOT NULL,       -- SHA256 of sequence (for dedup)
    length              INTEGER NOT NULL,
    target_sequence     TEXT,                -- the target this was designed against
    origin              TEXT,                -- 'inverse_folding' | 'scaffold' | 'rag_suggested' | 'mutant'
    parent_sequence_id  UUID REFERENCES sequences(sequence_id),  -- lineage tracking
    scaffold_type       TEXT,                -- 'affibody' | 'affitin' | 'nanobody' | 'de_novo'
    experiment_id       UUID,                -- links to DB1 experiments table
    director_id         UUID,                -- links to DB1 directors table
    design_round        INTEGER,             -- which BindCraft trial produced this
    created_at          TIMESTAMPTZ DEFAULT now(),

    UNIQUE(sequence_hash)                    -- prevent duplicate sequences
);

-- QC Results: one row per QC evaluation of a sequence.
-- A sequence may be QC'd multiple times across experiments.
CREATE TABLE qc_results (
    qc_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sequence_id         UUID NOT NULL REFERENCES sequences(sequence_id),
    passed              BOOLEAN NOT NULL,
    diversity           INTEGER,             -- number of unique AA types
    max_repeat_length   INTEGER,             -- longest consecutive repeat
    net_charge          INTEGER,
    charge_ratio        FLOAT,
    hydrophobic_ratio   FLOAT,
    max_appearance_ratio FLOAT,              -- most frequent AA / length
    bad_motifs_found    TEXT[],              -- which bad motifs were present
    bad_terminus        BOOLEAN,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- Folding Results: one row per folding event (Chai/ChaiBinder).
-- A sequence may be folded multiple times (different trials, constraints).
CREATE TABLE folding_results (
    fold_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sequence_id         UUID NOT NULL REFERENCES sequences(sequence_id),
    fold_backend        TEXT NOT NULL,       -- 'chai' | 'chai_binder' | 'boltz'
    structure_path      TEXT,                -- path to PDB file on disk
    model_index         INTEGER,             -- which Chai model (0-4)
    aggregate_score     FLOAT,               -- Chai aggregate score
    ptm                 FLOAT,               -- predicted TM-score
    iptm                FLOAT,               -- interface predicted TM-score
    per_chain_ptm       FLOAT[],             -- per-chain pTM values
    per_chain_pair_iptm FLOAT[],             -- pairwise chain ipTM values
    has_inter_chain_clashes BOOLEAN,
    diffusion_steps     INTEGER,
    constraints_used    JSON,                -- constraint dict if any
    trial_label         TEXT,                -- 'trial_0', 'trial_1', etc.
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- Contact Energy: one row per SimpleEnergy or RosettaEnergy evaluation.
CREATE TABLE energy_results (
    energy_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fold_id             UUID REFERENCES folding_results(fold_id),
    sequence_id         UUID NOT NULL REFERENCES sequences(sequence_id),
    energy_method       TEXT NOT NULL,       -- 'simple_contact' | 'rosetta'
    energy_score        FLOAT,               -- negative = favorable
    n_interface_contacts INTEGER,            -- for SimpleEnergy
    passed_threshold    BOOLEAN,             -- energy < energy_threshold
    energy_threshold    FLOAT,               -- what threshold was used
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- Simulation Runs: one row per MD simulation.
-- Links to the folded structure that was simulated.
CREATE TABLE simulation_runs (
    simulation_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fold_id             UUID REFERENCES folding_results(fold_id),
    sequence_id         UUID NOT NULL REFERENCES sequences(sequence_id),
    sim_path            TEXT,                -- root directory of simulation
    topology_path       TEXT,                -- system.prmtop
    trajectory_path     TEXT,                -- prod.dcd
    solvent_model       TEXT,                -- 'implicit' | 'explicit'
    equil_steps         INTEGER,
    prod_steps          INTEGER,
    platform            TEXT,                -- 'CUDA' | 'OpenCL' | 'CPU'
    sim_time_ns         FLOAT,               -- prod_steps * dt / 1e6
    build_success       BOOLEAN,
    sim_success         BOOLEAN,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- Trajectory Analysis: one row per analysis run on a simulation.
CREATE TABLE trajectory_analyses (
    analysis_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id       UUID REFERENCES simulation_runs(simulation_id),
    sequence_id         UUID NOT NULL REFERENCES sequences(sequence_id),
    analysis_type       TEXT,                -- 'basic' | 'advanced' | 'both'

    -- Basic metrics
    rmsd_mean           FLOAT,
    rmsd_std            FLOAT,
    rmsf_mean           FLOAT,               -- mean over residues
    rmsf_per_residue    FLOAT[],             -- full per-residue array
    radius_of_gyration  FLOAT,
    n_frames            INTEGER,

    -- Advanced metrics (hotspot analysis)
    binding_site_residues TEXT[],            -- top contact residues
    contact_frequencies JSON,                -- {residue_pair: frequency}

    confidence_score    FLOAT,               -- calculated from RMSD stability
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- Free Energy: one row per MM-PBSA calculation.
CREATE TABLE free_energy_results (
    fe_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id       UUID REFERENCES simulation_runs(simulation_id),
    sequence_id         UUID NOT NULL REFERENCES sequences(sequence_id),
    method              TEXT DEFAULT 'mmpbsa',  -- 'mmpbsa' | future methods
    free_energy         FLOAT,               -- kcal/mol (negative = favorable)
    success             BOOLEAN,
    error               TEXT,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- Embeddings: one row per embedding of a sequence (GenSLM/ESM).
CREATE TABLE embeddings (
    embedding_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sequence_id         UUID NOT NULL REFERENCES sequences(sequence_id),
    model_name          TEXT NOT NULL,       -- 'genslm_esmc' | 'esm2' | etc.
    embedding_dim       INTEGER,             -- dimensionality
    embedding_vector    FLOAT[] NOT NULL,    -- the actual coordinates
    created_at          TIMESTAMPTZ DEFAULT now()
);
```

### 6.4 Sequence Lifecycle View

The key analytical view: one row per sequence with its best/latest metrics
across all workflow stages. This is the "trace a sequence through the workflow"
query.

```sql
CREATE VIEW sequence_lifecycle AS
SELECT
    s.sequence_id,
    s.sequence,
    s.length,
    s.origin,
    s.scaffold_type,
    s.design_round,
    s.created_at                                    AS designed_at,

    -- QC
    qc.passed                                       AS qc_passed,
    qc.diversity                                    AS qc_diversity,
    qc.net_charge                                   AS qc_net_charge,
    qc.hydrophobic_ratio                            AS qc_hydrophobic_ratio,

    -- Best fold (highest iptm)
    f.fold_id,
    f.structure_path,
    f.iptm,
    f.ptm,
    f.aggregate_score                               AS chai_score,
    f.has_inter_chain_clashes,

    -- Energy (from best fold)
    e.energy_score                                  AS contact_energy,
    e.n_interface_contacts,
    e.passed_threshold                              AS energy_passed,

    -- Best simulation
    sim.simulation_id,
    sim.sim_time_ns,
    sim.prod_steps,

    -- Trajectory analysis (from best simulation)
    ta.rmsd_mean,
    ta.rmsd_std,
    ta.rmsf_mean,
    ta.radius_of_gyration,
    ta.binding_site_residues,
    ta.confidence_score                             AS analysis_confidence,

    -- Free energy (from best simulation)
    fe.free_energy,

    -- Embedding
    emb.model_name                                  AS embedding_model,
    emb.embedding_vector                            AS embedding_coords

FROM sequences s
LEFT JOIN LATERAL (
    SELECT * FROM qc_results q WHERE q.sequence_id = s.sequence_id
    ORDER BY q.created_at DESC LIMIT 1
) qc ON true
LEFT JOIN LATERAL (
    SELECT * FROM folding_results fr WHERE fr.sequence_id = s.sequence_id
    ORDER BY fr.iptm DESC NULLS LAST LIMIT 1
) f ON true
LEFT JOIN LATERAL (
    SELECT * FROM energy_results er WHERE er.fold_id = f.fold_id
    ORDER BY er.energy_score ASC LIMIT 1
) e ON true
LEFT JOIN LATERAL (
    SELECT * FROM simulation_runs sr WHERE sr.sequence_id = s.sequence_id
    AND sr.sim_success = true
    ORDER BY sr.prod_steps DESC LIMIT 1
) sim ON true
LEFT JOIN LATERAL (
    SELECT * FROM trajectory_analyses t WHERE t.simulation_id = sim.simulation_id
    ORDER BY t.created_at DESC LIMIT 1
) ta ON true
LEFT JOIN LATERAL (
    SELECT * FROM free_energy_results fer WHERE fer.simulation_id = sim.simulation_id
    AND fer.success = true
    ORDER BY fer.free_energy ASC LIMIT 1
) fe ON true
LEFT JOIN LATERAL (
    SELECT * FROM embeddings eb WHERE eb.sequence_id = s.sequence_id
    ORDER BY eb.created_at DESC LIMIT 1
) emb ON true;
```

### 6.5 Key Scientific Queries

```sql
-- The "master query": flat table of all sequences with their pipeline metrics
SELECT * FROM sequence_lifecycle
ORDER BY free_energy ASC NULLS LAST;

-- Top binders by free energy
SELECT sequence, length, scaffold_type, contact_energy, free_energy,
       rmsd_mean, iptm, design_round
FROM sequence_lifecycle
WHERE free_energy IS NOT NULL
ORDER BY free_energy ASC
LIMIT 20;

-- Sequences that passed all filters
SELECT sequence, length, contact_energy, free_energy, rmsd_mean, iptm
FROM sequence_lifecycle
WHERE qc_passed = true
  AND energy_passed = true
  AND rmsd_std < 2.0
  AND free_energy < -10.0
ORDER BY free_energy ASC;

-- Design round yield: how many sequences pass each stage per round?
SELECT s.design_round,
       COUNT(*)                                                AS generated,
       COUNT(*) FILTER (WHERE qc.passed)                       AS passed_qc,
       COUNT(*) FILTER (WHERE e.passed_threshold)              AS passed_energy,
       COUNT(*) FILTER (WHERE sim.sim_success)                 AS simulated,
       COUNT(*) FILTER (WHERE fe.success AND fe.free_energy < -10) AS good_fe
FROM sequences s
LEFT JOIN qc_results qc ON qc.sequence_id = s.sequence_id
LEFT JOIN energy_results e ON e.sequence_id = s.sequence_id
LEFT JOIN simulation_runs sim ON sim.sequence_id = s.sequence_id
LEFT JOIN free_energy_results fe ON fe.sequence_id = s.sequence_id
GROUP BY s.design_round
ORDER BY s.design_round;

-- Scaffold comparison: which scaffold type produces the best binders?
SELECT s.scaffold_type,
       COUNT(*) as n_sequences,
       AVG(fe.free_energy) as avg_fe,
       MIN(fe.free_energy) as best_fe,
       AVG(ta.rmsd_mean) as avg_rmsd
FROM sequences s
LEFT JOIN free_energy_results fe ON fe.sequence_id = s.sequence_id AND fe.success
LEFT JOIN trajectory_analyses ta ON ta.sequence_id = s.sequence_id
WHERE s.scaffold_type IS NOT NULL
GROUP BY s.scaffold_type;

-- Sequence lineage: trace a binder back through its ancestors
WITH RECURSIVE lineage AS (
    SELECT sequence_id, sequence, parent_sequence_id, design_round, 0 as depth
    FROM sequences WHERE sequence_id = ?
    UNION ALL
    SELECT s.sequence_id, s.sequence, s.parent_sequence_id, s.design_round, l.depth + 1
    FROM sequences s JOIN lineage l ON s.sequence_id = l.parent_sequence_id
)
SELECT * FROM lineage ORDER BY depth DESC;

-- Embedding-space neighbors (for diversity analysis or clustering prep)
SELECT a.sequence_id, b.sequence_id,
       list_cosine_similarity(a.embedding_vector, b.embedding_vector) as similarity
FROM embeddings a, embeddings b
WHERE a.sequence_id < b.sequence_id
  AND a.model_name = b.model_name
ORDER BY similarity DESC
LIMIT 100;

-- Cross-director comparison: which director found the best binders?
SELECT s.director_id, COUNT(*) as n_sequences,
       MIN(fe.free_energy) as best_fe,
       AVG(f.iptm) as avg_iptm
FROM sequences s
LEFT JOIN folding_results f ON f.sequence_id = s.sequence_id
LEFT JOIN free_energy_results fe ON fe.sequence_id = s.sequence_id AND fe.success
GROUP BY s.director_id;
```

### 6.6 How DB 1 and DB 2 Relate

The two databases share referential context via `experiment_id` and `director_id`
columns on the `sequences` table, but they are not formally foreign-keyed across
files. This is intentional:

```
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│  DB 1: decisions.duckdb         │       │  DB 2: scientific.duckdb        │
│                                 │       │                                 │
│  experiments ◄─── directors     │       │  sequences                      │
│       │               │        │       │    │  (experiment_id, director_id│
│       │               │        │       │    │   are informational only)   │
│  executive_actions    │        │  ───► │    │                             │
│                       │        │       │    ├──► qc_results               │
│  decisions ◄── task_plans      │       │    ├──► folding_results          │
│       │                        │       │    │       └──► energy_results   │
│  llm_calls    task_executions  │       │    ├──► simulation_runs          │
│                                 │       │    │       ├──► trajectory_an.  │
│                                 │       │    │       └──► free_energy_r.  │
│                                 │       │    └──► embeddings              │
│                                 │       │                                 │
│  Queried by: LLM prompt builder│       │  Queried by: analysis notebooks,│
│  Executive, DataAgent           │       │  DataAgent, visualization tools │
└─────────────────────────────────┘       └─────────────────────────────────┘
```

To join across databases (e.g., "what decision led to the best binder?"), DuckDB's
`ATTACH` command can open both files:

```sql
ATTACH 'decisions.duckdb' AS db1;
ATTACH 'scientific.duckdb' AS db2;

-- Which LLM decisions led to the best free energy outcomes?
SELECT d.next_task, d.rationale, s.sequence, fe.free_energy
FROM db1.decisions d
JOIN db1.task_executions te ON te.plan_id = (
    SELECT plan_id FROM db1.task_plans WHERE decision_id = d.decision_id
)
JOIN db2.sequences s ON s.director_id::TEXT = d.director_id::TEXT
    AND s.design_round = d.iteration
JOIN db2.free_energy_results fe ON fe.sequence_id = s.sequence_id
WHERE fe.success = true
ORDER BY fe.free_energy ASC
LIMIT 10;
```

---

## 7. DuckDB Integration Strategy

### 6.1 Connection Management

```python
import duckdb
from pathlib import Path
from contextlib import contextmanager

class WorkflowDB:
    """Thin wrapper around DuckDB for StructBioReasoner."""

    def __init__(self, db_path: str | Path = "workflow.duckdb"):
        self.db_path = str(db_path)
        self._conn = duckdb.connect(self.db_path)
        self._init_schema()

    def _init_schema(self):
        """Run CREATE TABLE IF NOT EXISTS for all tables."""
        schema_path = Path(__file__).parent / "schema.sql"
        self._conn.execute(schema_path.read_text())

    @contextmanager
    def cursor(self):
        """Thread-safe read cursor (separate connection)."""
        local_conn = duckdb.connect(self.db_path, read_only=True)
        try:
            yield local_conn
        finally:
            local_conn.close()

    def close(self):
        self._conn.close()
```

### 6.2 Integration Points

DuckDB writes should happen at well-defined boundaries in the `agents/` code:

| Event | Table(s) Written | Where in Code |
|-------|-----------------|---------------|
| Experiment starts | `experiments` | `TestExecutive.start()` |
| Director launched | `directors` | `TestExecutive.start()` inner loop |
| LLM recommendation call | `llm_calls` | `ReasonerAgent.generate_recommendation()` |
| Recommendation parsed | `decisions` | `ReasonerAgent.generate_recommendation()` return |
| LLM plan call | `llm_calls` | `ReasonerAgent.plan_run()` |
| Plan generated | `task_plans` | `ReasonerAgent.plan_run()` return |
| Worker starts | `task_executions` (INSERT) | `Director.tool_call()` entry |
| Worker finishes | `task_executions` (UPDATE) | `Director.tool_call()` return |
| Key item identified | `key_items` | Post-processing of BindCraft/analysis results |
| Executive checks status | `executive_actions` | `TestExecutive.run()` review loop |
| Director terminated | `directors` (UPDATE) | `TestExecutive.stop()` |
| Experiment ends | `experiments` (UPDATE) | `TestExecutive.stop()` |

### 6.3 Read Path: Replacing In-Memory History

Instead of passing the growing in-memory list, the prompt builder can query
DuckDB for the last N entries:

```python
def get_history_for_prompt(
    db: WorkflowDB, director_id: str, limit: int = 5
) -> WorkflowHistory:
    """Fetch recent history from DB instead of in-memory list."""
    with db.cursor() as conn:
        decisions = conn.execute("""
            SELECT json_object('next_task', next_task,
                               'rationale', rationale,
                               'change_parameters', change_parameters)
            FROM decisions
            WHERE director_id = ? ORDER BY created_at DESC LIMIT ?
        """, [director_id, limit]).fetchall()

        results = conn.execute("""
            SELECT result_data FROM task_executions
            WHERE director_id = ? AND status = 'completed'
            ORDER BY completed_at DESC LIMIT ?
        """, [director_id, limit]).fetchall()

        configs = conn.execute("""
            SELECT plan_config FROM task_plans
            WHERE director_id = ? ORDER BY created_at DESC LIMIT ?
        """, [director_id, limit]).fetchall()

        items = conn.execute("""
            SELECT item_data FROM key_items
            WHERE director_id = ? ORDER BY created_at DESC LIMIT ?
        """, [director_id, limit]).fetchall()

    return WorkflowHistory(
        decisions=[r[0] for r in reversed(decisions)],
        results=[r[0] for r in reversed(results)],
        configurations=[r[0] for r in reversed(configs)],
        key_items=[r[0] for r in reversed(items)],
    )
```

---

## 7. Parallel LLM/Decision History Treatment

The current architecture has a tension: the in-memory history is needed for
low-latency prompt construction within the Director loop, but a DB provides
durability, queryability, and cross-Director visibility. Rather than forcing
one to replace the other, they can operate in parallel.

### 7.1 Dual-Write Architecture

```
                       ┌─────────────────────┐
                       │   Director Loop      │
                       │                      │
                       │  results, decision,  │
                       │  plan, execution     │
                       └──────────┬───────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           ▼
          ┌─────────────────┐        ┌──────────────────┐
          │  In-Memory Path │        │  DB Write Path   │
          │  (hot path)     │        │  (async/bg)      │
          │                 │        │                   │
          │ WorkflowHistory │        │ DataAgent receives│
          │ updated inline  │        │ events via action │
          │ for next LLM    │        │ calls; writes to  │
          │ prompt          │        │ DuckDB in batches │
          └─────────────────┘        └──────────────────┘
                    │                           │
                    ▼                           ▼
          ┌─────────────────┐        ┌──────────────────┐
          │ Prompt Builder  │        │ Analytical Queries│
          │ (latency-       │        │ (Executive review,│
          │  sensitive)     │        │  cross-Director   │
          │                 │        │  insights, audits)│
          └─────────────────┘        └──────────────────┘
```

### 7.2 Event Types

The Director emits structured events at each boundary. The DataAgent consumes
them asynchronously:

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import time

class EventType(Enum):
    LLM_CALL         = "llm_call"
    DECISION          = "decision"
    PLAN              = "plan"
    EXECUTION_START   = "execution_start"
    EXECUTION_END     = "execution_end"
    KEY_ITEM          = "key_item"
    EXECUTIVE_ACTION  = "executive_action"

@dataclass
class WorkflowEvent:
    event_type: EventType
    director_id: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
```

### 7.3 Why Parallel?

1. **Latency**: The Director loop should not block on I/O. The DataAgent's
   `record_event()` Academy action is fire-and-forget from the Director's
   perspective. Batch writes to DuckDB happen on a background timer.

2. **Decoupling**: The in-memory `WorkflowHistory` remains the prompt builder's
   source for the current Director. The DB becomes the source for cross-Director
   analysis, Executive-level queries, and post-hoc auditing.

3. **Graceful degradation**: If the DB write fails, the Director loop is
   unaffected. Events can be retried or buffered.

4. **Executive enrichment**: When the Executive evaluates a Director, it can
   query the DB for rich aggregate statistics instead of relying on the
   free-form `check_status()` string.

5. **Replay & debugging**: The DB provides a complete audit trail of every LLM
   call, every decision, and every execution — enabling offline analysis of
   decision patterns and prompt effectiveness.

### 7.4 When to Read from DB vs. Memory

| Use Case | Source |
|----------|--------|
| Next LLM prompt (recommendation/plan) | In-memory `WorkflowHistory` (fast, local to Director) |
| Executive evaluating Directors | DB query (aggregated, cross-Director) |
| Cross-Director insight sharing | DB query (compare decision patterns) |
| Post-experiment analysis | DB query (full historical record) |
| Crash recovery / resume | DB (reconstruct in-memory state from last N rows) |
| Monitoring / dashboard | DB (live analytical queries via DuckDB CLI or Python) |

---

## 8. DataAgent: A New Database-Managing Agent

### 8.1 Responsibilities

The `DataAgent` is a new Academy agent (`agents/data/data_agent.py`) that:

1. **Consumes events** from the Director and Executive via `@action` calls
2. **Writes to DuckDB** in batches for efficiency
3. **Serves analytical queries** to the Executive and other agents
4. **Manages schema migrations** (versioned DDL)
5. **Exports data** to Parquet for offline analysis
6. **Provides crash-recovery state** to Directors on restart

### 8.2 Proposed Implementation

```python
from academy.agent import Agent, action
import duckdb
import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class DataAgent(Agent):
    """Academy agent managing all DuckDB operations for the workflow."""

    def __init__(
        self,
        db_path: str = "workflow.duckdb",
        batch_size: int = 50,
        flush_interval: float = 2.0,  # seconds
    ):
        self.db_path = db_path
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._event_buffer: list[dict] = []
        self._conn: duckdb.DuckDBPyConnection | None = None
        super().__init__()

    async def agent_on_startup(self) -> None:
        self._conn = duckdb.connect(self.db_path)
        self._init_schema()
        self._flush_task = asyncio.create_task(self._periodic_flush())
        logger.info("DataAgent started, db=%s", self.db_path)

    async def agent_on_shutdown(self) -> None:
        self._flush_task.cancel()
        await self._flush()  # final flush
        if self._conn:
            self._conn.close()
        logger.info("DataAgent shut down")

    def _init_schema(self):
        """Initialize all tables (CREATE IF NOT EXISTS)."""
        # Execute the DDL from Section 5.2
        ...

    # ── Write Path ──────────────────────────────────────────────

    @action
    async def record_event(self, event: dict[str, Any]) -> None:
        """Accept a workflow event for batched DB insertion.

        Called by Director.query_reasoner(), Director.tool_call(),
        and TestExecutive.run() at well-defined boundaries.
        """
        self._event_buffer.append(event)
        if len(self._event_buffer) >= self.batch_size:
            await self._flush()

    async def _periodic_flush(self):
        """Background task: flush buffered events on a timer."""
        while True:
            await asyncio.sleep(self.flush_interval)
            if self._event_buffer:
                await self._flush()

    async def _flush(self):
        """Write buffered events to DuckDB."""
        if not self._event_buffer:
            return
        events = self._event_buffer.copy()
        self._event_buffer.clear()

        for event in events:
            try:
                match event['event_type']:
                    case 'llm_call':
                        self._insert_llm_call(event)
                    case 'decision':
                        self._insert_decision(event)
                    case 'plan':
                        self._insert_plan(event)
                    case 'execution_start':
                        self._insert_execution_start(event)
                    case 'execution_end':
                        self._update_execution_end(event)
                    case 'key_item':
                        self._insert_key_item(event)
                    case 'executive_action':
                        self._insert_executive_action(event)
            except Exception as e:
                logger.error("Failed to write event %s: %s", event['event_type'], e)

    # ── Read Path (Query Actions) ──────────────────────────────

    @action
    async def get_director_history(
        self,
        director_id: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Reconstruct WorkflowHistory for a Director from DB."""
        decisions = self._conn.execute("""
            SELECT json_object('next_task', next_task,
                               'rationale', rationale,
                               'change_parameters', change_parameters)
            FROM decisions WHERE director_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, [director_id, limit]).fetchall()

        results = self._conn.execute("""
            SELECT result_data FROM task_executions
            WHERE director_id = ? AND status = 'completed'
            ORDER BY completed_at DESC LIMIT ?
        """, [director_id, limit]).fetchall()

        configs = self._conn.execute("""
            SELECT plan_config FROM task_plans
            WHERE director_id = ? ORDER BY created_at DESC LIMIT ?
        """, [director_id, limit]).fetchall()

        items = self._conn.execute("""
            SELECT item_data FROM key_items
            WHERE director_id = ? ORDER BY created_at DESC LIMIT ?
        """, [director_id, limit]).fetchall()

        return {
            'decisions':      [r[0] for r in reversed(decisions)],
            'results':        [r[0] for r in reversed(results)],
            'configurations': [r[0] for r in reversed(configs)],
            'key_items':      [r[0] for r in reversed(items)],
        }

    @action
    async def get_experiment_summary(
        self,
        experiment_id: str,
    ) -> dict[str, Any]:
        """Aggregate statistics across all Directors in an experiment."""
        return self._conn.execute("""
            SELECT
                COUNT(DISTINCT d.director_id) as num_directors,
                COUNT(te.execution_id) as total_tasks,
                COUNT(te.execution_id) FILTER (WHERE te.status = 'completed') as completed,
                COUNT(te.execution_id) FILTER (WHERE te.status = 'failed') as failed,
                AVG(te.duration_ms) FILTER (WHERE te.status = 'completed') as avg_ms,
                SUM(lc.prompt_tokens) as prompt_tokens,
                SUM(lc.completion_tokens) as completion_tokens
            FROM directors d
            LEFT JOIN task_executions te ON te.director_id = d.director_id
            LEFT JOIN llm_calls lc ON lc.director_id = d.director_id
            WHERE d.experiment_id = ?
        """, [experiment_id]).fetchdf().to_dict('records')[0]

    @action
    async def get_cross_director_insights(
        self,
        experiment_id: str,
    ) -> dict[str, Any]:
        """Provide the Executive with cross-Director comparative data."""
        transitions = self._conn.execute("""
            SELECT d.external_label, dec.previous_task, dec.next_task,
                   COUNT(*) as count
            FROM decisions dec
            JOIN directors d ON d.director_id = dec.director_id
            WHERE d.experiment_id = ?
            GROUP BY d.external_label, dec.previous_task, dec.next_task
            ORDER BY count DESC
        """, [experiment_id]).fetchdf().to_dict('records')

        return {'task_transitions': transitions}

    @action
    async def get_recovery_state(
        self,
        director_id: str,
    ) -> dict[str, Any]:
        """Provide state needed to resume a Director after crash."""
        last_decision = self._conn.execute("""
            SELECT next_task, rationale FROM decisions
            WHERE director_id = ? ORDER BY created_at DESC LIMIT 1
        """, [director_id]).fetchone()

        last_execution = self._conn.execute("""
            SELECT agent_key, status, result_data FROM task_executions
            WHERE director_id = ? ORDER BY started_at DESC LIMIT 1
        """, [director_id]).fetchone()

        return {
            'last_decision': last_decision,
            'last_execution': last_execution,
        }

    @action
    async def export_to_parquet(
        self,
        experiment_id: str,
        output_dir: str,
    ) -> list[str]:
        """Export all tables for an experiment to Parquet files."""
        tables = ['llm_calls', 'decisions', 'task_plans',
                  'task_executions', 'key_items', 'executive_actions']
        paths = []
        for table in tables:
            path = f"{output_dir}/{table}.parquet"
            self._conn.execute(f"""
                COPY (
                    SELECT t.* FROM {table} t
                    JOIN directors d ON t.director_id = d.director_id
                    WHERE d.experiment_id = ?
                ) TO '{path}' (FORMAT PARQUET)
            """, [experiment_id])
            paths.append(path)
        return paths
```

### 8.3 Integration with Existing Agents

The DataAgent is launched alongside worker agents by the Director:

```python
# In Director.load_agents(), add:
from struct_bio_reasoner.agents.data.data_agent import DataAgent

self.data_agent = await self.agent_launch_alongside(
    DataAgent,
    kwargs={'db_path': f'{self.runtime_config.get("output_dir", ".")}/workflow.duckdb'},
)
```

Directors emit events at each boundary:

```python
# In Director.query_reasoner(), after getting recommendation:
await self.data_agent.record_event({
    'event_type': 'decision',
    'director_id': self._director_label,
    'payload': {
        'iteration': len(self.history),
        'previous_task': data['previous_run'],
        'next_task': str(recommendation.recommendation.next_task),
        'change_parameters': recommendation.recommendation.change_parameters,
        'rationale': recommendation.recommendation.rationale,
    },
})

# In Director.tool_call(), at entry:
await self.data_agent.record_event({
    'event_type': 'execution_start',
    'director_id': self._director_label,
    'payload': {'agent_key': agent_key, 'input_kwargs': kwargs},
})

# In Director.tool_call(), at return:
await self.data_agent.record_event({
    'event_type': 'execution_end',
    'director_id': self._director_label,
    'payload': {'agent_key': agent_key, 'result_data': results, 'duration_ms': elapsed},
})
```

The Executive queries the DataAgent for cross-Director insights:

```python
# In TestExecutive.run() review loop, replace log-only with:
insights = await self.data_agent.get_cross_director_insights(self.experiment_id)
summary = await self.data_agent.get_experiment_summary(self.experiment_id)
```

### 8.4 AgentRegistry Update

```python
class AgentRegistry(BaseModel):
    reasoner:  str = '...pydantic_ai_agent:ReasonerAgent'
    bindcraft: str = '...bindcraft_coordinator:BindCraftCoordinator'
    md:        str = '...MD:MDAgent'
    mmpbsa:    str = '...mmpbsa_agent:FEAgent'
    folding:   str = '...chai_agent:ChaiAgent'
    data:      str = 'struct_bio_reasoner.agents.data.data_agent:DataAgent'  # NEW

    # data agent is NOT in TASK_TO_AGENT — it's infrastructure, not a task target
```

---

## 9. Migration Path & Implementation Steps

### Phase 1: Foundation (Non-Breaking)

1. **Add DuckDB dependency** to `pyproject.toml`
2. **Create `agents/data/` package**:
   - `__init__.py`
   - `data_agent.py` — the DataAgent class (Section 8.2)
   - `schema.sql` — DDL from Section 5.2
   - `events.py` — `WorkflowEvent`, `EventType` definitions
3. **Add `data` entry to `AgentRegistry`** (not in `TASK_TO_AGENT`)
4. **Write tests** for schema creation, event insertion, query functions

### Phase 2: Instrumentation (Additive, No Behavioral Changes)

5. **Add DataAgent launch** to `Director.load_agents()`
6. **Emit events in `Director.query_reasoner()`**:
   - `LLM_CALL` event wrapping `ReasonerAgent.generate_recommendation()`
   - `DECISION` event with the parsed `Recommendation`
   - `LLM_CALL` event wrapping `ReasonerAgent.plan_run()`
   - `PLAN` event with the parsed Plan model
7. **Emit events in `Director.tool_call()`**:
   - `EXECUTION_START` at entry
   - `EXECUTION_END` at return (or on error)
8. **Emit `EXECUTIVE_ACTION` in `TestExecutive.run()`** review loop
9. **Add experiment/director registration** in `TestExecutive.start()`

### Phase 3: Read Integration (Executive Upgrade)

10. **TestExecutive queries DataAgent** for `get_cross_director_insights()` and
    `get_experiment_summary()` during the review loop
11. **Replace passive logging** with structured decision-making:
    the Executive can now compare Directors and take action (advise, kill, etc.)
12. **Add `get_recovery_state()` support**: on Director restart, query DB for
    last known state to reconstruct `self.previous_run` and seed `self.history`
13. **Add Parquet export** in `TestExecutive.stop()`

### Phase 4: History Optimization

14. **Cap `Director.history` list** at a fixed window (e.g., last 10 entries)
    and rely on DB for anything older
15. **Implement `get_history_for_prompt()`** (Section 6.3) as an alternative to
    the current `self.history` list — fetch windowed history from DataAgent
16. **Standardize prompt serialization**: migrate `structure_prediction.py` and
    `analysis.py` from `json.dumps(ctx.history.model_dump())` to
    `serialize_history(ctx.history)` for consistency
17. **Add DB-based stopping criteria**: e.g., stop Director if no affinity
    improvement in last K decisions (queryable via DataAgent)

---

## 10. Risks and Considerations

### 10.1 DuckDB Concurrency

DuckDB supports multiple reader connections but only one writer at a time per
file. Since the DataAgent is the sole writer, this is safe. For multi-node
deployments where Directors run on separate machines:
- Each Director can write to a **local DuckDB file**, and the DataAgent merges
  them periodically
- Or use DuckDB's `ATTACH` to query across multiple database files

### 10.2 Academy Serialization

Academy serializes data crossing agent boundaries (action calls). All
`record_event()` payloads must be JSON-serializable — use `.model_dump()` on
Pydantic models before emitting. The `WorkflowEvent` dataclass should be
passed as a plain `dict` to the action, not as a dataclass instance.

### 10.3 Parsl Interaction

DuckDB connections are not picklable. The DataAgent must never be submitted as
a Parsl task. It should run in the same process as the Director (via
`agent_launch_alongside`), not on a Parsl worker node.

### 10.4 Schema Evolution

Include a `schema_version` table and migration scripts. DuckDB supports
`ALTER TABLE ADD COLUMN` for additive changes. For breaking changes, export to
Parquet (via `export_to_parquet()`) and re-import.

### 10.5 Disk Space

For a typical campaign with ~1000 LLM calls and ~500 task executions, the DB
file will be well under 100MB. DuckDB's columnar compression keeps this small.
Parquet export compresses further (~10x).

### 10.6 Performance Impact

DuckDB in-process writes are ~0.1ms per row. The batched flush in DataAgent
(every 2s or 50 events, whichever comes first) means the Director loop sees
effectively zero write latency. Read queries for prompt construction (last 5-10
rows with simple WHERE + ORDER BY + LIMIT) take <1ms.

### 10.7 WorkflowHistory.from_raw() Bug

As noted in Section 4.2, `from_raw()` discards non-empty lists. This should be
fixed regardless of the DB migration — either by teaching `from_raw()` to
handle `list[dict]` by merging entries, or by ensuring `Director.history` is
always a `dict` matching `WorkflowHistory` fields rather than a list of
arbitrary objects.
