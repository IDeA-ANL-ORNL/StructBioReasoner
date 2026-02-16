"""
Backward-compatibility stub — re-exports from ``struct_bio_reasoner.prompts``.

All implementation has moved to ``prompts/_registry.py``, ``prompts/_recommender.py``,
and individual task files under ``prompts/tasks/``.  This file can be removed once
all call-sites import from ``struct_bio_reasoner.prompts`` directly.
"""

from struct_bio_reasoner.prompts import (  # noqa: F401
    TASK_REGISTRY,
    PromptContext,
    TaskDef,
    build_prompt_context,
    build_recommender_prompt,
    get_conclusion_prompt,
    get_plan_model,
    get_prompt_manager,
    get_running_prompt,
    serialize_history,
)

# Legacy name kept for any code that references it directly
TaskPromptConfig = TaskDef

__all__ = [
    "PromptContext",
    "TaskPromptConfig",
    "TASK_REGISTRY",
    "build_prompt_context",
    "build_recommender_prompt",
    "get_conclusion_prompt",
    "get_plan_model",
    "get_prompt_manager",
    "get_running_prompt",
    "serialize_history",
]
