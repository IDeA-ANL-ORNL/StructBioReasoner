"""PriorityFrontier — executor-aware, priority-based task scheduler.

The frontier decouples *deciding to run a task* from *actually submitting it
to Parsl*.  Tasks are enqueued with a priority derived from their
:class:`~.executors.TaskNode` and released to the
:class:`~.orchestration.RoundRobinParslPool` only when the **specific
executor required by the task** has capacity.

Key properties
--------------
* **Per-executor backlogs** — one priority heap per executor label
  (``tool_gpu``, ``_ungated``).  Tasks are routed to the correct backlog
  on :meth:`enqueue`.
* **Executor-aware fill** — :meth:`_fill` iterates over all executor
  backlogs and only pops tasks whose executor has room in the pool.
  A burst of GPU tasks no longer blocks CPU tasks that could run on idle
  workers.
* **Priority ordering** — within each executor backlog, lower
  ``TaskNode.effective_priority()`` values are dequeued first.
* **Bounded concurrency** — a global ``max_concurrent`` cap prevents
  DFK overload even when all executors have capacity.
* **Cancellation / Re-prioritization** — supported via lazy deletion.

Usage (inside a supervisor loop)::

    frontier = PriorityFrontier(pool, max_concurrent=12)
    frontier.enqueue(tool_name, config, node)
    ...
    async for completed_task, completed_node in frontier.drain():
        children = decide_next_tasks(completed_task.result())
        for child_tool, child_cfg, child_node in children:
            frontier.enqueue(child_tool, child_cfg, child_node)

Adapted from ``bindify.core.frontier``.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, TYPE_CHECKING

from .executors import TaskNode, TaskResult

if TYPE_CHECKING:
    from .orchestration import RoundRobinParslPool

logger = logging.getLogger(__name__)

# Monotonic counter to break ties in the priority queue (FIFO among equal
# priorities).
_tie_breaker = itertools.count()


@dataclass(order=True)
class _QueueEntry:
    """Wrapper that makes (priority, counter, payload) sortable."""

    priority: int
    counter: int = field(compare=True)
    # --- non-comparable payload ---
    tool_name: str = field(compare=False, default="")
    config: Any = field(compare=False, default=None)
    node: TaskNode = field(compare=False, default_factory=TaskNode)
    cancelled: bool = field(compare=False, default=False)


class PriorityFrontier:
    """Executor-aware, priority-based async task scheduler.

    Parameters
    ----------
    pool : RoundRobinParslPool
        The pool used to submit tasks to Parsl DFKs.  Must expose
        :meth:`executor_for_tool` and :meth:`executor_has_capacity`.
    max_concurrent : int
        Global cap on tasks submitted to Parsl simultaneously (across
        all executors).
    """

    def __init__(
        self,
        pool: RoundRobinParslPool,
        max_concurrent: int = 12,
    ) -> None:
        self._pool = pool
        self._max_concurrent = max_concurrent

        # Per-executor priority heaps.  Keys are executor labels
        # (e.g. "tool_gpu") or "_ungated" for CPU-only tools.
        self._backlogs: dict[str, list[_QueueEntry]] = {}

        # Currently running asyncio.Tasks and their metadata.
        self._running: dict[asyncio.Task, TaskNode] = {}

        # Index from task_id → _QueueEntry for cancel / reprioritize.
        self._pending_index: dict[str, _QueueEntry] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def pending_count(self) -> int:
        """Number of tasks waiting across all backlogs (excludes cancelled)."""
        return sum(
            1
            for heap in self._backlogs.values()
            for e in heap
            if not e.cancelled
        )

    @property
    def running_count(self) -> int:
        """Number of tasks currently submitted to Parsl."""
        return len(self._running)

    @property
    def is_empty(self) -> bool:
        """True when no pending *and* no running tasks remain."""
        return self.pending_count == 0 and self.running_count == 0

    def enqueue(
        self,
        tool_name: str,
        config: Any,
        node: TaskNode,
    ) -> None:
        """Add a task to the correct per-executor backlog (does not submit yet)."""
        entry = _QueueEntry(
            priority=node.effective_priority(),
            counter=next(_tie_breaker),
            tool_name=tool_name,
            config=config,
            node=node,
        )
        label = self._pool.executor_for_tool(tool_name)
        if label not in self._backlogs:
            self._backlogs[label] = []
        heapq.heappush(self._backlogs[label], entry)
        self._pending_index[node.task_id] = entry
        logger.debug(
            "Enqueued '%s' → backlog[%s] (priority=%d, task_id=%s). "
            "Pending=%d, Running=%d",
            tool_name,
            label,
            entry.priority,
            node.task_id,
            self.pending_count,
            self.running_count,
        )

    def cancel_pending(self, task_id: str) -> bool:
        """Cancel a pending (not yet submitted) task by its task_id.

        Returns True if the task was found and cancelled, False otherwise.
        Already-running tasks cannot be cancelled through this method.
        """
        entry = self._pending_index.pop(task_id, None)
        if entry is None or entry.cancelled:
            return False
        entry.cancelled = True
        logger.info(
            "Cancelled pending task '%s' (task_id=%s)",
            entry.tool_name,
            task_id,
        )
        return True

    def reprioritize(self, task_id: str, new_priority: int) -> bool:
        """Change the priority of a pending task.

        Uses lazy deletion: the old entry is marked cancelled and a fresh
        one with the new priority is pushed.  Returns False if the task is
        not pending.
        """
        entry = self._pending_index.get(task_id)
        if entry is None or entry.cancelled:
            return False

        # Mark old entry as cancelled (lazy deletion) and push a fresh one
        entry.cancelled = True
        label = self._pool.executor_for_tool(entry.tool_name)
        new_entry = _QueueEntry(
            priority=new_priority,
            counter=next(_tie_breaker),
            tool_name=entry.tool_name,
            config=entry.config,
            node=entry.node,
        )
        new_entry.node.priority = new_priority
        if label not in self._backlogs:
            self._backlogs[label] = []
        heapq.heappush(self._backlogs[label], new_entry)
        self._pending_index[task_id] = new_entry
        logger.info(
            "Reprioritized '%s' (task_id=%s) → priority=%d",
            entry.tool_name,
            task_id,
            new_priority,
        )
        return True

    def status_snapshot(self) -> dict[str, Any]:
        """Return a JSON-serialisable status snapshot for MCP tools."""
        per_executor = {}
        for label, heap in self._backlogs.items():
            per_executor[label] = sum(1 for e in heap if not e.cancelled)
        return {
            "pending": self.pending_count,
            "running": self.running_count,
            "is_empty": self.is_empty,
            "max_concurrent": self._max_concurrent,
            "per_executor_pending": per_executor,
            "running_tools": [
                node.tool_name for node in self._running.values()
            ],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fill(self) -> None:
        """Submit tasks from per-executor backlogs while capacity exists.

        For each executor backlog we check whether the pool has room for
        that executor.  If so, the highest-priority task (lowest value)
        is popped and submitted.  We also respect the global
        ``max_concurrent`` cap.

        This is the core scheduling improvement: a full ``tool_gpu``
        executor no longer blocks CPU tasks from being submitted.
        """
        for label in list(self._backlogs.keys()):
            heap = self._backlogs[label]
            while (
                heap
                and len(self._running) < self._max_concurrent
                and self._pool.executor_has_capacity(heap[0].tool_name)
            ):
                entry = heapq.heappop(heap)
                if entry.cancelled:
                    self._pending_index.pop(entry.node.task_id, None)
                    continue

                # Remove from index — it's now running, not pending
                self._pending_index.pop(entry.node.task_id, None)

                task = asyncio.create_task(
                    self._pool.submit(entry.tool_name, entry.config),
                )
                self._running[task] = entry.node
                logger.debug(
                    "Submitted '%s' (executor=%s, priority=%d) to pool. "
                    "Running=%d/%d",
                    entry.tool_name,
                    label,
                    entry.priority,
                    self.running_count,
                    self._max_concurrent,
                )

    # ------------------------------------------------------------------
    # Main drain loop
    # ------------------------------------------------------------------

    async def drain(self) -> AsyncIterator[tuple[TaskResult, TaskNode]]:
        """Yield ``(TaskResult, TaskNode)`` pairs as tasks finish.

        This is an async generator that the supervisor consumes in an
        ``async for`` loop.  On each iteration it:

        1. Fills the running set from per-executor backlogs (only where
           the pool reports capacity for that executor).
        2. Waits for any running task to complete (``FIRST_COMPLETED``).
        3. Yields each completed ``(result, node)`` pair.

        The caller is expected to call :meth:`enqueue` with child tasks
        between yields.  The generator exits when both all backlogs
        and the running set are empty.
        """
        while True:
            self._fill()
            if not self._running:
                return

            done, _ = await asyncio.wait(
                self._running.keys(),
                return_when=asyncio.FIRST_COMPLETED,
            )

            for completed_task in done:
                node = self._running.pop(completed_task)
                try:
                    raw_result = completed_task.result()
                    task_result = TaskResult(
                        result=raw_result,
                        tool_name=node.tool_name,
                        task_id=node.task_id,
                    )
                except Exception as exc:
                    task_result = TaskResult(
                        result={"error": str(exc)},
                        tool_name=node.tool_name,
                        task_id=node.task_id,
                    )
                yield task_result, node
