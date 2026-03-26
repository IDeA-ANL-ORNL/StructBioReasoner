"""AcademyDispatch — bridge between MCP skill endpoints and Academy Handle RPC.

When the MCP server receives a skill invocation, it calls
``AcademyDispatch.dispatch(skill_name, params)`` which:

1. Looks up the appropriate Worker Agent class in ``WORKER_REGISTRY``
2. Lazily launches the agent via ``Manager.launch()`` (first call only)
3. Invokes the worker's ``@action`` method through the Handle
4. Returns the result to the MCP caller

This gives every MCP skill invocation transparent access to Academy's
distributed execution fabric — the same call works locally
(``LocalExchangeFactory``) and on HPC clusters
(``RedisExchangeFactory`` + Parsl).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .config import AcademyConfig, create_exchange_factory, create_parsl_executor
from .worker_agents import WORKER_REGISTRY

logger = logging.getLogger(__name__)

# Maps skill name → default @action method name on the worker
_DEFAULT_ACTION: Dict[str, str] = {
    "bindcraft": "run_design",
    "binder_design": "run_design",
    "folding": "fold_sequences",
    "structure_prediction": "fold_sequences",
    "md": "run_simulation",
    "simulation": "run_simulation",
    "molecular_dynamics": "run_simulation",
    "rag": "generate_rag_hypothesis",
    "literature": "generate_rag_hypothesis",
    "hiperrag": "generate_rag_hypothesis",
    "conservation": "run_conservation",
    "protein_lm": "embed_sequence",
    "trajectory_analysis": "cluster_trajectories",
    "clustering": "cluster_trajectories",
}


class AcademyDispatch:
    """Bridge: MCP endpoint → Academy Handle invocation.

    Usage::

        config = AcademyConfig(exchange_mode="local")
        dispatch = AcademyDispatch(config)
        await dispatch.start()

        result = await dispatch.dispatch("bindcraft", {"target_sequence": "MKQH..."})

        await dispatch.stop()
    """

    def __init__(
        self,
        config: Optional[AcademyConfig] = None,
        worker_configs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self.config = config or AcademyConfig()
        self.worker_configs = worker_configs or {}

        # Initialised in start()
        self._manager = None
        self._worker_handles: Dict[str, Any] = {}
        self._started = False

    async def start(self) -> None:
        """Initialise the Academy Manager and exchange transport."""
        if self._started:
            return

        from academy.manager import Manager

        exchange_factory = create_exchange_factory(self.config)
        executor = create_parsl_executor(self.config)

        self._manager = await Manager.from_exchange_factory(
            factory=exchange_factory,
            executors=executor,
        )
        await self._manager.__aenter__()
        self._started = True
        logger.info("AcademyDispatch started (exchange=%s)", self.config.exchange_mode)

    async def stop(self) -> None:
        """Shut down the Academy Manager and all worker agents."""
        if not self._started:
            return
        if self._manager:
            await self._manager.__aexit__(None, None, None)
        self._worker_handles.clear()
        self._started = False
        logger.info("AcademyDispatch stopped")

    async def dispatch(
        self,
        skill_name: str,
        params: Dict[str, Any],
        action_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Route an MCP skill invocation to the matching Academy worker.

        Args:
            skill_name: Canonical skill name (e.g. ``"bindcraft"``, ``"folding"``).
            params: Parameters forwarded to the worker's ``@action`` method.
            action_name: Override the default action method name.

        Returns:
            Result dictionary from the worker agent.

        Raises:
            ValueError: If ``skill_name`` is not in ``WORKER_REGISTRY``.
            RuntimeError: If dispatch has not been started.
        """
        if not self._started:
            raise RuntimeError("AcademyDispatch not started — call start() first")

        handle = await self._get_or_launch(skill_name)
        method_name = action_name or _DEFAULT_ACTION.get(skill_name, "run")

        logger.info("Dispatching %s.%s(…)", skill_name, method_name)
        method = getattr(handle, method_name)
        result = await method(params)
        return result if isinstance(result, dict) else {"result": result}

    async def _get_or_launch(self, skill_name: str) -> Any:
        """Get an existing Handle or lazily launch the worker agent."""
        if skill_name in self._worker_handles:
            return self._worker_handles[skill_name]

        agent_cls = WORKER_REGISTRY.get(skill_name)
        if agent_cls is None:
            raise ValueError(
                f"Unknown skill '{skill_name}'. "
                f"Available: {sorted(WORKER_REGISTRY.keys())}"
            )

        worker_config = self.worker_configs.get(skill_name, {})
        handle = await self._manager.launch(agent_cls, args=(worker_config,))
        self._worker_handles[skill_name] = handle

        logger.info("Launched %s worker (%s)", skill_name, agent_cls.__name__)
        return handle

    def list_available_skills(self) -> list[str]:
        """Return canonical skill names this dispatch can handle."""
        return sorted(WORKER_REGISTRY.keys())

    def list_active_workers(self) -> list[str]:
        """Return skill names that currently have a live Handle."""
        return sorted(self._worker_handles.keys())

    # Async context manager support
    async def __aenter__(self) -> "AcademyDispatch":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()
