"""Recommender prompt builder."""

from __future__ import annotations

import json

from struct_bio_reasoner.models import WorkflowHistory


def build_recommender_prompt(
    enabled_agents: list[str],
    research_goal: str,
    previous_run: str,
    previous_conclusion: str,
    history: WorkflowHistory | dict,
    resource_summary: str = "",
) -> str:
    """Build the recommender prompt (replaces RecommenderPromptManager)."""
    if isinstance(history, WorkflowHistory):
        history_str = json.dumps(history.model_dump(), indent=2, default=str)
    else:
        history_str = json.dumps(history, indent=2, default=str)

    resource_block = ""
    if resource_summary:
        resource_block = (
            f"COMPUTE RESOURCES AVAILABLE:\n{resource_summary}\n\n"
            f"Scale your recommendations to fit these resources. "
            f"For example, do not suggest designing more binders per round "
            f"than there are available GPUs, and do not suggest running more "
            f"parallel simulations than there are accelerators.\n\n"
        )

    return (
        f"You are an AI co-scientist specializing in recommending the next run "
        f"{enabled_agents} to perform based on previous conclusions.\n\n"
        f"Research goal:\n{research_goal}\n\n"
        f"{resource_block}"
        f"Please base this recommendation on previous run + conclusion and history.\n\n"
        f"Previous run type: {previous_run}\n\n"
        f"Previous run conclusion: {previous_conclusion}\n\n"
        f"History: {history_str}\n\n"
    )
