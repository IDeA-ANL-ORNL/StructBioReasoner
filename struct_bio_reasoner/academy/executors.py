"""Executor labels, tool-to-executor mapping, priority constants, and task
data models for the StructBioReasoner orchestration layer.

This is the leaf module that all other orchestration modules import from,
kept small to avoid circular dependencies.

Adapted from ``bindify.tools._executors`` and ``bindify.core.data``.
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Executor labels
# ---------------------------------------------------------------------------

EXECUTOR_GPU = "tool_gpu"
"""Single executor label for all GPU-bound tools."""

# Tool → executor mapping.
# GPU tools share the unified ``tool_gpu`` executor.
# CPU-only / lightweight tasks map to ``None`` and are gated only by the
# global ``max_concurrent`` limit, not by per-executor capacity.
TOOL_TO_EXECUTOR: Dict[str, Optional[str]] = {
    # GPU tools
    "bindcraft": EXECUTOR_GPU,
    "binder_design": EXECUTOR_GPU,
    "folding": EXECUTOR_GPU,
    "structure_prediction": EXECUTOR_GPU,
    "md": EXECUTOR_GPU,
    "simulation": EXECUTOR_GPU,
    "molecular_dynamics": EXECUTOR_GPU,
    "protein_lm": EXECUTOR_GPU,
    # CPU-only / lightweight
    "rag": None,
    "literature": None,
    "hiperrag": None,
    "conservation": None,
    "trajectory_analysis": None,
    "clustering": None,
}

ALL_EXECUTOR_LABELS: list[str] = [EXECUTOR_GPU]
"""All GPU executor labels — used to initialise per-executor data structures."""

# ---------------------------------------------------------------------------
# Priority constants
# ---------------------------------------------------------------------------

PRIORITY_CRITICAL = 0  # evaluation / scoring / folding
PRIORITY_HIGH = 1  # MD validation, structure prediction
PRIORITY_DEFAULT = 2  # design / generation tasks
PRIORITY_LOW = 3  # lightweight lookups, RAG, conservation

# Maps skill name → default priority.  The supervisor can override per-task.
DEFAULT_TOOL_PRIORITIES: Dict[str, int] = {
    "folding": PRIORITY_CRITICAL,
    "structure_prediction": PRIORITY_CRITICAL,
    "md": PRIORITY_HIGH,
    "simulation": PRIORITY_HIGH,
    "molecular_dynamics": PRIORITY_HIGH,
    "bindcraft": PRIORITY_DEFAULT,
    "binder_design": PRIORITY_DEFAULT,
    "protein_lm": PRIORITY_DEFAULT,
    "trajectory_analysis": PRIORITY_HIGH,
    "clustering": PRIORITY_HIGH,
    "rag": PRIORITY_LOW,
    "literature": PRIORITY_LOW,
    "hiperrag": PRIORITY_LOW,
    "conservation": PRIORITY_LOW,
}

# ---------------------------------------------------------------------------
# Preconditions: tool X requires Y binders with field Z before it can run
# ---------------------------------------------------------------------------

TOOL_PRECONDITIONS: Dict[str, Dict[str, Any]] = {
    "md": {"field": "structure_path", "min_count": 1},
    "simulation": {"field": "structure_path", "min_count": 1},
    "molecular_dynamics": {"field": "structure_path", "min_count": 1},
    "trajectory_analysis": {"field": "trajectory_path", "min_count": 1},
    "clustering": {"field": "trajectory_path", "min_count": 1},
}

# Group-analysis trigger: after this many results from the same tool/batch
# accumulate, fire the reasoner to analyse them as a group.
TOOL_GROUP_BETA: Dict[str, int] = {
    "bindcraft": 10,
    "binder_design": 10,
    "folding": 5,
    "md": 3,
    "protein_lm": 10,
}

# ---------------------------------------------------------------------------
# Task data models
# ---------------------------------------------------------------------------


@dataclass
class TaskNode:
    """Graph-level metadata for one task in the priority frontier.

    Tracks the task's position in the spawning tree so the supervisor can
    route completions to the correct reasoner and enforce depth limits.
    """

    task_id: str = dc_field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str = ""
    reasoner_idx: int = 0
    iteration_id: str = ""
    campaign_id: str = ""
    depth: int = 0
    parent_id: Optional[str] = None
    priority: Optional[int] = None

    def effective_priority(self) -> int:
        """Return the scheduling priority for this node.

        If ``priority`` was set explicitly, return that value.  Otherwise
        fall back to ``DEFAULT_TOOL_PRIORITIES``, then ``PRIORITY_DEFAULT``.
        """
        if self.priority is not None:
            return self.priority
        return DEFAULT_TOOL_PRIORITIES.get(self.tool_name, PRIORITY_DEFAULT)


@dataclass
class TaskResult:
    """The result of a task submitted to a ParslAgent."""

    result: Any
    tool_name: str = ""
    task_id: str = ""
    duration_seconds: float = 0.0


# Monotonic counter used to break priority ties (guarantees FIFO ordering
# among items with equal priority).
_item_counter = itertools.count()


@dataclass(order=True)
class QueueItem:
    """A single atomic task in the ExecutionAgent's priority queue.

    Ordering: lower ``priority`` numbers are dequeued first.  Equal-priority
    items are dequeued in insertion order (FIFO) via the ``counter`` field.
    """

    priority: int
    counter: int = dc_field(
        compare=True,
        default_factory=lambda: next(_item_counter),
    )
    tool_name: str = dc_field(compare=False, default="")
    config: Any = dc_field(compare=False, default=None)
    node: TaskNode = dc_field(compare=False, default_factory=TaskNode)
    batch_id: str = dc_field(compare=False, default="")
    iteration_id: str = dc_field(compare=False, default="")
    generation: int = dc_field(compare=False, default=0)
    task_id: str = dc_field(
        compare=False,
        default_factory=lambda: str(uuid.uuid4()),
    )
    retry_count: int = dc_field(compare=False, default=0)
    cancelled: bool = dc_field(compare=False, default=False)
