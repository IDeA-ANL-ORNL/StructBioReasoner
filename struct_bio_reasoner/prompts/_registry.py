"""
Task registry infrastructure for StructBioReasoner prompts.

Provides the ``TaskDef`` base class (with ``__init_subclass__``
auto-registration), ``PromptContext``, ``serialize_history``, and the
public API functions consumed by agents.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from struct_bio_reasoner.models import (
    PLAN_MODELS,
    RUNNABLE_TASKS,
    WorkflowHistory,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PromptContext",
    "TaskDef",
    "TASK_REGISTRY",
    "serialize_history",
    "build_prompt_context",
    "get_conclusion_prompt",
    "get_plan_model",
    "get_running_prompt",
]


# ---------------------------------------------------------------------------
# Shared context dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PromptContext:
    """Immutable bag of inputs shared by every prompt function."""
    research_goal: str
    target_prot: str
    prompt_type: str
    history: WorkflowHistory
    input_json: dict[str, Any] | list[dict]
    resource_summary: str = ""


def serialize_history(h: WorkflowHistory) -> dict[str, str]:
    """Serialize history entries for prompt embedding.

    All prompt functions should use this helper (not inline attribute access)
    to ensure consistent JSON formatting and fallback strings.
    """
    return {
        'decisions': json.dumps(h.decisions, indent=2, default=str) if h.decisions else 'No history',
        'results': json.dumps(h.results, indent=2, default=str) if h.results else 'No history',
        'configurations': json.dumps(h.configurations, indent=2, default=str) if h.configurations else 'No history',
        'key_items': json.dumps(h.key_items, indent=2, default=str) if h.key_items else 'No key items yet',
    }


# ---------------------------------------------------------------------------
# Registry + TaskDef base
# ---------------------------------------------------------------------------

TASK_REGISTRY: dict[str, TaskDef] = {}


class TaskDef:
    """Base class for task prompt definitions.

    Subclasses set ``name`` as a class attribute and override ``running()``
    and ``conclusion()``.  Registration into ``TASK_REGISTRY`` happens
    automatically via ``__init_subclass__``.
    """

    name: str = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.name:
            if cls.name in TASK_REGISTRY:
                raise RuntimeError(
                    f"Duplicate TaskDef for {cls.name!r}: "
                    f"{TASK_REGISTRY[cls.name].__class__.__name__} already registered"
                )
            TASK_REGISTRY[cls.name] = cls()

    def running(self, ctx: PromptContext) -> str:
        raise NotImplementedError

    def conclusion(self, ctx: PromptContext) -> str:
        raise NotImplementedError

    @property
    def plan_model(self) -> type[BaseModel] | None:
        return PLAN_MODELS.get(self.name)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _get_task_def(task: str) -> TaskDef:
    """Look up a task in the registry, raising a helpful error on miss."""
    td = TASK_REGISTRY.get(task)
    if td is None:
        raise KeyError(
            f"Unknown task type: {task!r}. "
            f"Available tasks: {sorted(TASK_REGISTRY.keys())}"
        )
    return td


def get_conclusion_prompt(task: str, ctx: PromptContext) -> str:
    """Return the conclusion prompt for *task*."""
    return _get_task_def(task).conclusion(ctx)


def get_running_prompt(task: str, ctx: PromptContext) -> str:
    """Return the running (plan-generation) prompt for *task*."""
    return _get_task_def(task).running(ctx)


def get_plan_model(task: str) -> type[BaseModel] | None:
    """Return the Pydantic plan model for *task*, or ``None``."""
    return _get_task_def(task).plan_model


def build_prompt_context(
    agent_type: str,
    research_goal: str,
    input_json: dict[str, Any] | list[dict],
    target_prot: str,
    prompt_type: str,
    history: dict | WorkflowHistory,
    resource_summary: str = "",
) -> PromptContext:
    """Build a ``PromptContext`` for the given task type."""
    hist = WorkflowHistory.from_raw(history)
    return PromptContext(
        research_goal=research_goal,
        target_prot=target_prot,
        prompt_type=prompt_type,
        history=hist,
        input_json=input_json,
        resource_summary=resource_summary,
    )


# Backward-compatible alias
get_prompt_manager = build_prompt_context


def validate_task_registry() -> None:
    """Ensure TASK_REGISTRY covers all RUNNABLE_TASKS with non-null plan_model."""
    registry_keys = set(TASK_REGISTRY.keys())
    for task in RUNNABLE_TASKS:
        if task not in registry_keys:
            raise RuntimeError(
                f"TaskName.{task.name} is in RUNNABLE_TASKS but missing from "
                f"TASK_REGISTRY. Add a TaskDef subclass for it."
            )
        td = TASK_REGISTRY[task]
        if td.plan_model is None:
            raise RuntimeError(
                f"TASK_REGISTRY[{task!r}].plan_model is None but {task!r} is a "
                f"runnable task. Check that PLAN_MODELS has an entry for it."
            )
