---
name: jnana-reasoning
description: Scientific reasoning via Jnana CoScientist — hypothesis generation, evaluation, and parameter bounding
metadata:
  openclaw:
    requires:
      env:
        - OPENAI_API_KEY
      bins:
        - python3
      anyBins:
        - python3.11
        - python3.12
    primaryEnv: OPENAI_API_KEY
  dependencies:
    - jnana
    - academy
---

# Jnana Reasoning — Scientific Intelligence Layer

Access Jnana's CoScientist for hypothesis-driven scientific reasoning.
This is **Layer 2** of the 4-layer hybrid architecture.

## Capabilities

- **Research goal setting**: Initialize a scientific investigation with a research goal
- **Hypothesis generation**: Generate testable hypotheses using literature and domain knowledge
- **Next action recommendation** (Tier 1): Evaluate current state, recommend next task type
- **Parameter bounding** (Tier 2): Generate bounded parameter configurations for computational skills
- **Result evaluation**: Evaluate experimental results against hypotheses via Artifact DAG
- **Convergence detection**: Determine when sufficient evidence has been gathered

## Two-Tier Prompting

The reasoning bridge uses a two-tier prompting strategy:

1. **Tier 1 — Recommendation**: `recommend_next_action()` evaluates the current state
   and recommends the next task type (computational_design, molecular_dynamics, analysis,
   free_energy, or stop).

2. **Tier 2 — Parameter Bounding**: `bound_parameters()` takes the recommendation and
   generates a bounded parameter configuration for the selected skill.

## MCP Endpoints

- `jnana.set_research_goal` — Initialize reasoning for a research goal
- `jnana.recommend_next_action` — Get next recommended task type (Tier 1)
- `jnana.bound_parameters` — Get parameter config for a skill (Tier 2)
- `jnana.evaluate_results` — Evaluate artifacts against hypotheses
- `jnana.check_convergence` — Check if research goal is met

## Script Usage

```bash
python skills/jnana-reasoning/scripts/reason.py --help
python skills/jnana-reasoning/scripts/reason.py set-goal "Design a binder for target X"
python skills/jnana-reasoning/scripts/reason.py recommend --previous-run starting
python skills/jnana-reasoning/scripts/reason.py bound-params --skill bindcraft --task-type computational_design
python skills/jnana-reasoning/scripts/reason.py evaluate --artifact-ids abc123 def456
python skills/jnana-reasoning/scripts/reason.py check-convergence
```

## Parameters

- `action`: Reasoning action — "set_goal", "recommend", "bound_params", "evaluate_results", "check_convergence"
- `research_goal`: Research goal description (for "set_goal")
- `previous_run_type`: Previous run type for context (for "recommend")
- `skill_name`: Target skill for parameter recommendations (for "bound_params")
- `task_type`: Task type for parameter schema (for "bound_params")
- `artifact_ids`: Artifact IDs to evaluate (for "evaluate_results")
