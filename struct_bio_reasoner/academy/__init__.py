"""Academy execution fabric (Layer 4).

Distributed agent lifecycle management, Handle-based RPC, and HPC-scale
parallelism via Parsl.  This module wraps Academy's primitives into
StructBioReasoner's Executive/Manager/Worker hierarchy and exposes an
``AcademyDispatch`` bridge so the MCP server can route skill invocations
to Academy worker agents.

The orchestration sub-layer adds:
* **CoordinatingAgent** — precondition checks + config hydration
* **ExecutionAgent** — priority queue + async dispatch + retry
* **ParslAgent** — single Parsl DFK wrapper
* **RoundRobinParslPool** — executor-aware round-robin distribution
* **PriorityFrontier** — per-executor backlogs + drain() generator
"""

from .config import AcademyConfig, create_exchange_factory, create_parsl_executor

# Always-available (no academy dependency)
from .executors import (
    ALL_EXECUTOR_LABELS,
    DEFAULT_TOOL_PRIORITIES,
    EXECUTOR_GPU,
    PRIORITY_CRITICAL,
    PRIORITY_DEFAULT,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    TOOL_GROUP_BETA,
    TOOL_PRECONDITIONS,
    TOOL_TO_EXECUTOR,
    QueueItem,
    TaskNode,
    TaskResult,
)

__all__ = [
    "AcademyConfig",
    "create_exchange_factory",
    "create_parsl_executor",
    # Executors / data model (always available)
    "ALL_EXECUTOR_LABELS",
    "DEFAULT_TOOL_PRIORITIES",
    "EXECUTOR_GPU",
    "PRIORITY_CRITICAL",
    "PRIORITY_DEFAULT",
    "PRIORITY_HIGH",
    "PRIORITY_LOW",
    "TOOL_GROUP_BETA",
    "TOOL_PRECONDITIONS",
    "TOOL_TO_EXECUTOR",
    "QueueItem",
    "TaskNode",
    "TaskResult",
]

try:
    from .dispatch import AcademyDispatch
    from .executive import ExecutiveAgent
    from .frontier import PriorityFrontier
    from .manager_agent import ManagerAgent
    from .orchestration import (
        CoordinatingAgent,
        ExecutionAgent,
        ParslAgent,
        RoundRobinParslPool,
    )
    from .worker_agents import (
        BindCraftWorker,
        ConservationWorker,
        FoldingWorker,
        MDWorker,
        ProteinLMWorker,
        RAGWorker,
        TrajectoryAnalysisWorker,
        WORKER_REGISTRY,
    )

    _ACADEMY_AVAILABLE = True
except ImportError:
    _ACADEMY_AVAILABLE = False

if _ACADEMY_AVAILABLE:
    __all__ += [
        "AcademyDispatch",
        "ExecutiveAgent",
        "ManagerAgent",
        "PriorityFrontier",
        "CoordinatingAgent",
        "ExecutionAgent",
        "ParslAgent",
        "RoundRobinParslPool",
        "BindCraftWorker",
        "FoldingWorker",
        "MDWorker",
        "RAGWorker",
        "ConservationWorker",
        "ProteinLMWorker",
        "TrajectoryAnalysisWorker",
        "WORKER_REGISTRY",
    ]
