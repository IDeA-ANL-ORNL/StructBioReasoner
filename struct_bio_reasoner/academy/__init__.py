"""Academy execution fabric (Layer 4).

Distributed agent lifecycle management, Handle-based RPC, and HPC-scale
parallelism via Parsl.  This module wraps Academy's primitives into
StructBioReasoner's Executive/Manager/Worker hierarchy and exposes an
``AcademyDispatch`` bridge so the MCP server can route skill invocations
to Academy worker agents.
"""

from .config import AcademyConfig, create_exchange_factory, create_parsl_executor
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

__all__ = [
    "AcademyConfig",
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
    "create_exchange_factory",
    "create_parsl_executor",
]
