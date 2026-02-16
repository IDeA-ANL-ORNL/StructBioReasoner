"""
Prompt system for StructBioReasoner.

Public API
----------
- ``build_prompt_context``   — create a ``PromptContext`` for a task
- ``get_conclusion_prompt``  — conclusion prompt text for a task
- ``get_running_prompt``     — running (plan-generation) prompt text
- ``get_plan_model``         — Pydantic plan model for a task
- ``build_recommender_prompt`` — recommender prompt text

Adding a new task
-----------------
1. ``models.py`` — add to ``TaskName`` enum, create a ``Config`` model,
   add to ``CONFIG_MODELS``.
2. Create ``prompts/tasks/<name>.py`` with a ``TaskDef`` subclass.

That's it — no registry wiring needed.
"""

from struct_bio_reasoner.prompts._registry import (
    TASK_REGISTRY,
    PromptContext,
    TaskDef,
    build_prompt_context,
    get_conclusion_prompt,
    get_plan_model,
    get_prompt_manager,
    get_running_prompt,
    serialize_history,
    validate_task_registry,
)
from struct_bio_reasoner.prompts._recommender import build_recommender_prompt

# Importing the tasks package triggers auto-discovery and registration
import struct_bio_reasoner.prompts.tasks  # noqa: F401

# Validate that all runnable tasks are registered with non-null plan models
validate_task_registry()

__all__ = [
    "TASK_REGISTRY",
    "PromptContext",
    "TaskDef",
    "build_prompt_context",
    "build_recommender_prompt",
    "get_conclusion_prompt",
    "get_plan_model",
    "get_prompt_manager",
    "get_running_prompt",
    "serialize_history",
]
