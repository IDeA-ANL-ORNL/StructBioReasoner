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
    primaryEnv: OPENAI_API_KEY
---

# Jnana Reasoning — Scientific Intelligence Layer

Access Jnana's CoScientist for hypothesis-driven scientific reasoning.

## Capabilities

- **Research goal setting**: Initialize a scientific investigation with a research goal
- **Hypothesis generation**: Generate testable hypotheses using literature and domain knowledge
- **Parameter bounding**: Recommend parameter ranges for computational experiments
- **Result evaluation**: Evaluate experimental results against hypotheses
- **Convergence detection**: Determine when sufficient evidence has been gathered

## Usage

This skill provides the scientific reasoning layer (Layer 2) of the StructBioReasoner.
It wraps Jnana's CoScientist API to provide hypothesis-driven guidance to the OpenClaw
agent loop.

## Parameters

- `action`: Reasoning action — "set_goal", "generate_hypothesis", "recommend_params", "evaluate_results", "check_convergence"
- `research_goal`: Research goal description (for "set_goal")
- `context`: Current experimental context (for "generate_hypothesis", "recommend_params")
- `results`: Experimental results to evaluate (for "evaluate_results")
- `skill_name`: Target skill for parameter recommendations (for "recommend_params")
