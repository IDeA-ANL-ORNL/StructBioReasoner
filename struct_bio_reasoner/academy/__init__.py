"""Academy execution fabric (Layer 4).

Distributed agent lifecycle management, Handle-based RPC, and HPC-scale
parallelism via Parsl.  This module wraps Academy's primitives into
StructBioReasoner's Executive/Manager/Worker hierarchy and exposes an
``AcademyDispatch`` bridge so the MCP server can route skill invocations
to Academy worker agents.
"""

from .config import AcademyConfig, create_exchange_factory, create_parsl_executor

try:
    from .dispatch import AcademyDispatch
    from .executive import ExecutiveAgent
    from .manager_agent import ManagerAgent
    from .worker_agents import (
        BindCraftWorker,
        FoldingWorker,
        MDWorker,
        RAGWorker,
        ConservationWorker,
        ProteinLMWorker,
        TrajectoryAnalysisWorker,
        WORKER_REGISTRY,
    )
    _ACADEMY_AVAILABLE = True
except ImportError:
    _ACADEMY_AVAILABLE = False

__all__ = [
    "AcademyConfig",
    "create_exchange_factory",
    "create_parsl_executor",
]

if _ACADEMY_AVAILABLE:
    __all__ += [
        "AcademyDispatch",
        "ExecutiveAgent",
        "ManagerAgent",
        "BindCraftWorker",
        "FoldingWorker",
        "MDWorker",
        "RAGWorker",
        "ConservationWorker",
        "ProteinLMWorker",
        "TrajectoryAnalysisWorker",
        "WORKER_REGISTRY",
    ]
