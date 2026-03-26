"""Orchestration agents for StructBioReasoner's Academy execution fabric.

This module defines the three-tier agent hierarchy that drives parallel
task execution on HPC:

* **CoordinatingAgent** — validates preconditions, hydrates configs with
  artifact data, and submits tasks to the ExecutionAgent's queue.
* **ExecutionAgent** — owns the priority queue, drives submission to
  ParslAgents via a ``@loop`` tick, collects completions, and triggers
  the reasoner when enough results accumulate.
* **ParslAgent** — wraps a single Parsl DataFlowKernel (DFK).  One per
  node to avoid DFK bottleneck.
* **RoundRobinParslPool** — distributes tasks across ParslAgents with
  per-executor capacity tracking.

Adapted from ``bindify.core.orchestration``.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from academy.agent import Agent, action, loop
from academy.handle import Handle

from .executors import (
    ALL_EXECUTOR_LABELS,
    DEFAULT_TOOL_PRIORITIES,
    TOOL_GROUP_BETA,
    TOOL_PRECONDITIONS,
    TOOL_TO_EXECUTOR,
    QueueItem,
    TaskNode,
    TaskResult,
)
from .worker_agents import WORKER_REGISTRY

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CoordinatingAgent — policy + hydration
# ---------------------------------------------------------------------------


class CoordinatingAgent(Agent):
    """Academy agent that validates preconditions, hydrates configs with
    artifact/DB data, and routes tasks to the ExecutionAgent's queue.

    Parameters
    ----------
    max_queue_depth : int
        Maximum tasks to enqueue in a single ``submit_task_type`` call.
    execution_handle : Handle | None
        Handle to the :class:`ExecutionAgent`.  When ``None`` (unit-test /
        dry-run mode), tasks are logged but not dispatched.
    """

    def __init__(
        self,
        max_queue_depth: int = 500,
        execution_handle: Optional[Handle] = None,
    ) -> None:
        self.max_queue_depth = max_queue_depth
        self._execution_handle = execution_handle
        self._artifact_dag = None
        self.logger = logging.getLogger(f"{__name__}.CoordinatingAgent")

    async def agent_on_startup(self, artifact_dag: Any = None) -> None:
        self._artifact_dag = artifact_dag
        self.logger.info("CoordinatingAgent started up.")

    async def agent_on_shutdown(self) -> None:
        self.logger.info("CoordinatingAgent shut down.")

    @action
    async def submit_task_type(
        self,
        tool_name: str,
        config: Dict[str, Any],
        batch_id: str = "",
        iteration_id: str = "",
        campaign_id: str = "",
        generation: int = 0,
        priority: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Validate preconditions, hydrate config, and enqueue the task.

        Returns a dict with the submission status.
        """
        if not batch_id:
            batch_id = str(uuid.uuid4())

        # Guardrail: precondition check
        if not self._preconditions_met(tool_name):
            self.logger.warning(
                "Preconditions not met for '%s' — skipping.", tool_name
            )
            return {"status": "skipped", "reason": "preconditions_not_met"}

        # Hydrate: merge artifact/DB data into the config
        hydrated = self._hydrate(tool_name, config)

        effective_priority = (
            priority
            if priority is not None
            else DEFAULT_TOOL_PRIORITIES.get(tool_name, 2)
        )

        if self._execution_handle is not None:
            await self._execution_handle.enqueue(
                tool_name=tool_name,
                config=hydrated,
                batch_id=batch_id,
                iteration_id=iteration_id,
                priority=effective_priority,
                generation=generation,
            )
            self.logger.info(
                "Enqueued '%s' (batch=%s, priority=%d)",
                tool_name,
                batch_id,
                effective_priority,
            )
            return {"status": "enqueued", "batch_id": batch_id}
        else:
            self.logger.warning(
                "No execution_handle — '%s' batch '%s' was NOT dispatched.",
                tool_name,
                batch_id,
            )
            return {"status": "not_dispatched", "reason": "no_execution_handle"}

    def _preconditions_met(self, tool_name: str) -> bool:
        """Check tool-specific preconditions against the artifact DAG."""
        required = TOOL_PRECONDITIONS.get(tool_name)
        if required is None:
            return True
        if self._artifact_dag is None:
            # No DAG wired — assume preconditions met (dry-run mode)
            return True
        # Query artifact DAG for artifacts with the required field
        try:
            artifacts = self._artifact_dag.query(
                artifact_type=required.get("artifact_type", "RAW_OUTPUT"),
            )
            return len(artifacts) >= required.get("min_count", 1)
        except Exception:
            self.logger.warning(
                "Precondition check failed for '%s' — assuming met.",
                tool_name,
            )
            return True

    def _hydrate(
        self,
        tool_name: str,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge artifact-discovered data paths into the config.

        The reasoner sets *policy* fields (steps, parameters, constraints).
        This method adds *data* fields (PDB paths, sequences, trajectories)
        by querying the artifact DAG.
        """
        if self._artifact_dag is None:
            return config

        # Query recent artifacts relevant to this tool
        try:
            recent = self._artifact_dag.query(skill_name=tool_name)
            if recent:
                # Inject the most recent artifact's data paths
                latest = recent[-1]
                if hasattr(latest, "data") and isinstance(latest.data, dict):
                    # Only inject data fields, not policy fields
                    data_keys = {
                        "structure_path",
                        "trajectory_path",
                        "sequence",
                        "pdb_path",
                        "output_dir",
                    }
                    for key in data_keys:
                        if key in latest.data and key not in config:
                            config[key] = latest.data[key]
        except Exception:
            self.logger.debug(
                "Hydration query failed for '%s' — using config as-is.",
                tool_name,
            )
        return config


# ---------------------------------------------------------------------------
# ExecutionAgent — priority queue + dispatch
# ---------------------------------------------------------------------------


class ExecutionAgent(Agent):
    """Owns the PriorityQueue and drives submission to ParslAgents.

    Parameters
    ----------
    parsl_handles : list[Handle[ParslAgent]]
        Handles to live ``ParslAgent`` instances.
    reasoner_handle : Handle | None
        Handle to a ReasonerAgent for group-analysis triggers.
    """

    POLL_INTERVAL_SECONDS: float = 1.0
    MAX_RETRIES: int = 3

    def __init__(
        self,
        parsl_handles: Optional[List[Handle]] = None,
        reasoner_handle: Optional[Handle] = None,
    ) -> None:
        self._parsl_handles = parsl_handles or []
        self._reasoner_handle = reasoner_handle
        self._queue: asyncio.PriorityQueue[QueueItem] = asyncio.PriorityQueue(
            maxsize=500
        )
        self._running: Dict[str, tuple[asyncio.Task, QueueItem]] = {}
        self._groups: Dict[str, list] = defaultdict(list)
        self._group_analysis_fired: Dict[str, bool] = {}
        self._pool: Optional[RoundRobinParslPool] = None
        self._artifact_dag = None
        self.logger = logging.getLogger(f"{__name__}.ExecutionAgent")

    async def agent_on_startup(self, artifact_dag: Any = None) -> None:
        self._artifact_dag = artifact_dag
        self._queue = asyncio.PriorityQueue(maxsize=500)
        self._running = {}
        self._groups = defaultdict(list)
        self._group_analysis_fired = {}
        if self._parsl_handles:
            self._pool = RoundRobinParslPool(self._parsl_handles)
        self.logger.info("ExecutionAgent started up.")

    async def agent_on_shutdown(self) -> None:
        pending = self._queue.qsize()
        running = len(self._running)
        self.logger.info(
            "ExecutionAgent shutting down. Pending: %d. Running: %d.",
            pending,
            running,
        )

    @action
    async def enqueue(
        self,
        tool_name: str,
        config: Any,
        batch_id: str = "",
        iteration_id: str = "",
        priority: int = 2,
        generation: int = 0,
    ) -> None:
        """Add one task to the priority queue."""
        item = QueueItem(
            priority=priority,
            tool_name=tool_name,
            config=config,
            batch_id=batch_id,
            iteration_id=iteration_id,
            generation=generation,
        )
        await self._queue.put(item)
        self.logger.debug(
            "Enqueued '%s' (priority=%d, batch=%s). Queue depth: %d",
            tool_name,
            priority,
            batch_id,
            self._queue.qsize(),
        )

    @action
    async def queue_depth(self) -> int:
        """Return the current queue depth."""
        return self._queue.qsize()

    @action
    async def queue_status(self) -> Dict[str, Any]:
        """Return a status snapshot of the queue and running tasks."""
        return {
            "queue_depth": self._queue.qsize(),
            "running_count": len(self._running),
            "running_tasks": [
                {"task_id": tid, "tool_name": item.tool_name}
                for tid, (_, item) in self._running.items()
            ],
        }

    @loop
    async def run(self, shutdown: asyncio.Event) -> None:
        """One tick of the poll loop.

        Academy's ``@loop`` decorator calls this repeatedly until
        ``shutdown`` is set.  Each call performs one submit-and-collect
        cycle then yields.
        """
        await self._try_submit()
        await self._collect_completions()
        await asyncio.sleep(self.POLL_INTERVAL_SECONDS)

    async def _try_submit(self) -> None:
        """Pop items from the queue and submit where capacity exists."""
        while not self._queue.empty():
            item = self._queue.get_nowait()

            if item.cancelled:
                continue

            # Check executor capacity
            if (
                self._pool is not None
                and not self._pool.executor_has_capacity(item.tool_name)
            ):
                # Put it back — executor is full
                await self._queue.put(item)
                break

            if self._pool is None:
                self.logger.error(
                    "_try_submit: pool is None; cannot submit '%s'.",
                    item.task_id,
                )
                break

            task = asyncio.create_task(
                self._pool.submit(item.tool_name, item.config)
            )
            self._running[item.task_id] = (task, item)

    async def _collect_completions(self) -> None:
        """Check for completed tasks and process results."""
        done_ids = [
            tid
            for tid, (t, _) in self._running.items()
            if t.done()
        ]
        for tid in done_ids:
            task, item = self._running.pop(tid)
            try:
                result = task.result()
                self._groups[item.batch_id].append(result)

                # Store result as artifact
                if self._artifact_dag is not None:
                    try:
                        self._artifact_dag.create_and_store(
                            data=result if isinstance(result, dict) else {"result": str(result)},
                            metadata_kwargs={
                                "artifact_type": "RAW_OUTPUT",
                                "skill_name": item.tool_name,
                                "tags": frozenset(
                                    [f"batch:{item.batch_id}", f"gen:{item.generation}"]
                                ),
                            },
                        )
                    except Exception:
                        self.logger.debug(
                            "Failed to store artifact for task '%s'.", tid
                        )

                # Group-analysis trigger
                group = self._groups[item.batch_id]
                beta = TOOL_GROUP_BETA.get(item.tool_name, 10)
                if (
                    len(group) >= beta
                    and not self._group_analysis_fired.get(item.batch_id)
                    and self._reasoner_handle is not None
                ):
                    self._group_analysis_fired[item.batch_id] = True
                    asyncio.create_task(
                        self._reasoner_handle.analyze_group(
                            tool_name=item.tool_name,
                            batch_id=item.batch_id,
                            results=group,
                        )
                    )

                self.logger.info(
                    "Task completed: '%s' (batch=%s, task=%s)",
                    item.tool_name,
                    item.batch_id,
                    tid,
                )
            except Exception as exc:
                await self._handle_failure(item, exc)

    async def _handle_failure(self, item: QueueItem, exc: Exception) -> None:
        """Handle a failed task — retry or log permanent failure."""
        item.retry_count += 1
        self.logger.warning(
            "Task '%s' (tool=%s) failed (attempt %d): %s",
            item.task_id,
            item.tool_name,
            item.retry_count,
            exc,
        )
        if item.retry_count <= self.MAX_RETRIES:
            await self._queue.put(item)
        else:
            self.logger.error(
                "Task '%s' (tool=%s) failed permanently after %d retries: %s",
                item.task_id,
                item.tool_name,
                item.retry_count,
                exc,
            )


# ---------------------------------------------------------------------------
# ParslAgent — single DFK wrapper
# ---------------------------------------------------------------------------


class ParslAgent(Agent):
    """Academy agent wrapping a single Parsl DataFlowKernel (DFK).

    Why a separate agent per DFK?  A single Parsl DFK can become a
    scheduling bottleneck when hundreds of tasks are in-flight.  Wrapping
    each DFK inside an Academy agent lets us run multiple DFKs
    independently and distribute tasks across them via
    :class:`RoundRobinParslPool`.

    Parameters
    ----------
    tool_names : list[str]
        Subset of ``WORKER_REGISTRY`` keys this agent may run.
    parsl_config : parsl.Config | None
        Optional Parsl config.  When ``None`` a default
        ``HighThroughputExecutor`` is created for local testing.
    """

    def __init__(
        self,
        tool_names: Optional[List[str]] = None,
        parsl_config: Any = None,
    ) -> None:
        self.tool_names = tool_names or list(WORKER_REGISTRY.keys())
        self._parsl_config = parsl_config
        self._dfk = None
        self._worker_handles: Dict[str, Handle] = {}
        self._manager = None
        self.logger = logging.getLogger(f"{__name__}.ParslAgent")

    async def agent_on_startup(self) -> None:
        """Initialise the Parsl DFK if parsl is available."""
        try:
            import parsl
            from parsl import Config
            from parsl import HighThroughputExecutor

            config = self._parsl_config or Config(
                executors=[HighThroughputExecutor()],
            )
            self._dfk = parsl.load(config)
            self.logger.info("ParslAgent started with Parsl DFK.")
        except ImportError:
            self.logger.info(
                "Parsl not available — ParslAgent running in direct mode."
            )

    async def run(self) -> None:
        """Keep the agent alive to receive submit actions.

        Academy agents exit as soon as ``run()`` returns.  We wait on an
        Event that is never set so the agent stays alive until shutdown.
        """
        await asyncio.Event().wait()

    async def agent_on_shutdown(self) -> None:
        """Clean up the Parsl DFK."""
        if self._dfk is not None:
            self._dfk.cleanup()
            self._dfk = None
            try:
                import parsl

                parsl.clear()
            except ImportError:
                pass
        self.logger.info("ParslAgent shut down.")

    @action
    async def submit(
        self,
        tool_name: str,
        config: Any,
    ) -> Any:
        """Submit a tool to the Parsl DFK (or run directly) and return result.

        Parameters
        ----------
        tool_name : str
            Key in ``WORKER_REGISTRY``.
        config : Any
            Config dict or Pydantic model for the tool.

        Returns
        -------
        Any
            The tool's result.
        """
        if tool_name not in WORKER_REGISTRY:
            raise ValueError(
                f"Tool '{tool_name}' not in WORKER_REGISTRY. "
                f"Available: {sorted(WORKER_REGISTRY.keys())}"
            )

        # For now, delegate to worker agents directly.
        # When Parsl DFK is available and tools expose expand/aggregate,
        # we can fan out across GPU tiles here.
        from .dispatch import AcademyDispatch

        # Use the dispatch mechanism to route to the right worker
        dispatch = AcademyDispatch()
        await dispatch.start()
        try:
            result = await dispatch.dispatch(tool_name, config)
        finally:
            await dispatch.stop()
        return result


# ---------------------------------------------------------------------------
# RoundRobinParslPool — executor-aware pool of ParslAgents
# ---------------------------------------------------------------------------


class RoundRobinParslPool:
    """Executor-aware pool of :class:`ParslAgent` handles.

    Distributes tasks across multiple DFKs via round-robin and tracks
    outstanding tasks per executor label to enable capacity-aware scheduling.

    Parameters
    ----------
    handles : list[Handle[ParslAgent]]
        Academy handles pointing to live ``ParslAgent`` instances.
    max_workers_per_executor : int
        Maximum concurrent tasks per GPU executor label.
    max_ungated : int
        Maximum concurrent tasks for CPU-only tools.
    """

    def __init__(
        self,
        handles: List[Handle],
        max_workers_per_executor: int = 4,
        max_ungated: int = 16,
    ) -> None:
        self.handles = handles
        self.robin_index = 0
        self._max_workers_per_executor = max_workers_per_executor
        self._max_ungated = max_ungated

        # Outstanding task count per executor label
        self._outstanding: Dict[str, int] = {
            label: 0 for label in ALL_EXECUTOR_LABELS
        }
        self._outstanding["_ungated"] = 0
        self._logger = logging.getLogger(f"{__name__}.RoundRobinParslPool")

    # ------------------------------------------------------------------
    # Capacity queries
    # ------------------------------------------------------------------

    def executor_for_tool(self, tool_name: str) -> str:
        """Return the executor label for a tool, or ``'_ungated'``."""
        return TOOL_TO_EXECUTOR.get(tool_name) or "_ungated"

    def executor_has_capacity(self, tool_name: str) -> bool:
        """Return True if the executor for ``tool_name`` has room."""
        label = self.executor_for_tool(tool_name)
        limit = (
            self._max_ungated
            if label == "_ungated"
            else self._max_workers_per_executor
        )
        return self._outstanding.get(label, 0) < limit

    def outstanding_for_executor(self, label: str) -> int:
        """Return in-flight task count for a given executor label."""
        return self._outstanding.get(label, 0)

    def all_outstanding(self) -> Dict[str, int]:
        """Return a snapshot of outstanding tasks per executor label."""
        return dict(self._outstanding)

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    async def submit(self, tool_name: str, config: Any) -> TaskResult:
        """Submit a task to the next DFK in the pool via round robin.

        The caller must check :meth:`executor_has_capacity` before calling.
        """
        label = self.executor_for_tool(tool_name)
        self._outstanding[label] = self._outstanding.get(label, 0) + 1
        self._logger.debug(
            "Submitting '%s' (executor=%s, outstanding=%d)",
            tool_name,
            label,
            self._outstanding[label],
        )

        handle = self.handles[self.robin_index]
        self.robin_index = (self.robin_index + 1) % len(self.handles)

        start = datetime.datetime.now()
        try:
            result = await handle.submit(tool_name, config)
        finally:
            self._outstanding[label] = max(0, self._outstanding[label] - 1)

        duration = (datetime.datetime.now() - start).total_seconds()
        return TaskResult(
            result=result,
            tool_name=tool_name,
            duration_seconds=duration,
        )
