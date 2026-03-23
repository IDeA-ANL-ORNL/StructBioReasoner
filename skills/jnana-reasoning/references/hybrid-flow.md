# Hybrid Runtime Flow — Jnana Reasoning Layer

## Overview

Jnana (Layer 2) provides scientific intelligence to the 4-layer hybrid
architecture.  It does **not** orchestrate tools — it provides
recommendations, parameter bounds, and hypothesis evaluations that
OpenClaw (Layer 1) uses to select and invoke skills.

## Two-Tier Prompting

```
Tier 1: recommend_next_action()
  → "What task type should we run next?"
  → Returns: {task_type, rationale, confidence}
  → task_type ∈ {computational_design, molecular_dynamics, analysis, free_energy, stop}

Tier 2: bound_parameters(skill_name, task_type)
  → "How should we configure this skill?"
  → Returns: {parameters, constraints, rationale}
```

## Runtime Flow (all 4 layers)

```
1. User sets research goal via OpenClaw CLI         → Layer 1
2. OpenClaw invokes jnana-reasoning skill           → Layer 1 → Layer 2
3. Jnana.set_research_goal() initializes CoScientist  → Layer 2
4. Loop:
   a. Jnana.recommend_next_action()                 → Layer 2 (Tier 1)
   b. OpenClaw reads recommendation + SKILL.md      → Layer 1 selects skill
   c. Jnana.bound_parameters()                      → Layer 2 (Tier 2)
   d. Academy dispatches skill to worker agent       → Layer 4
   e. Worker produces artifacts → Artifact DAG       → Layer 3
   f. Jnana.evaluate_results() reads from DAG       → Layer 2
   g. Jnana.check_convergence()                     → Layer 2
   h. If not converged → goto (a)
5. OpenClaw presents results to user                → Layer 1
```

## Integration Points

- **Artifact DAG (Layer 3):** Jnana reads artifacts via `evaluate_results()`
  to assess experimental outcomes against hypotheses.  It writes reasoning
  artifacts (recommendations, evaluations) back to the DAG for provenance.

- **Academy (Layer 4):** Jnana's recommendations can be dispatched as
  `@action` calls via Academy Handle RPC.  The `_JnanaReasoningAgent`
  wrapper exposes `generate_recommendation()` and `plan_run()` as async
  actions.

- **MCP Endpoints:** All 5 public methods are registered as MCP tools
  (`jnana.set_research_goal`, `jnana.recommend_next_action`, etc.) for
  programmatic access from OpenClaw or external systems.

## History Management

The bridge maintains a rolling history (max 10 entries) of:
- `decisions` — what was decided at each step
- `configurations` — bounded parameter configs (truncated to 500 chars)
- `results` — evaluation outcomes
- `recommendations` — Tier-1 outputs
- `key_items` — important items (top binders, hotspot residues, etc.)

This history feeds into both Tier-1 and Tier-2 prompts to give the LLM
context about prior workflow steps.
