"""
Shared Parsl Context Mixin for Worker Agents

This module provides a mixin class that standardizes how worker agents handle
Parsl configuration. The key improvement is that agents can receive a shared
Parsl context from the workflow instead of creating their own, which prevents
the collision issues from nested Parsl configurations.

Usage:
    class MyAgent(SharedParslMixin):
        def __init__(self, ...):
            super().__init__()
            # Your init code

        async def initialize(self, data=None, shared_context=None):
            # Get parsl settings using the mixin
            parsl_settings = await self._get_parsl_settings(
                data=data,
                shared_context=shared_context,
                settings_class=LocalSettings,
                parsl_config=self.parsl_config
            )

            # Use parsl_settings for your coordinator
            self.coordinator = await self.manager.launch(
                MyCoordinator,
                args=(parsl_settings,)
            )
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from academy.exchange import LocalExchangeFactory
from academy.manager import Manager

if TYPE_CHECKING:
    from parsl import Config
    from ..workflows.advanced_workflow import SharedParslContext

logger = logging.getLogger(__name__)


@dataclass
class StandaloneParslContext:
    """
    Lightweight context for agents running standalone (not in workflow).

    This allows agents to work both within the workflow (using SharedParslContext)
    and standalone for testing/development (using their own config).
    """
    config: Optional['Config'] = None
    run_dir: Path = field(default_factory=lambda: Path.cwd())
    allocated_accelerators: List[str] = field(default_factory=list)
    is_standalone: bool = True


class SharedParslMixin:
    """
    Mixin that provides standardized Parsl context handling for worker agents.

    Key features:
    1. Accepts shared context from workflow (no nested Parsl configs)
    2. Falls back to standalone mode for testing/development
    3. Provides consistent Academy manager lifecycle management
    4. Tracks allocated accelerators to prevent GPU conflicts

    When using SharedParslContext from the workflow:
    - Does NOT create a new Parsl Config
    - Uses the workflow's single DataFlowKernel
    - Respects accelerator allocations from the workflow

    When running standalone:
    - Creates its own Parsl Config (original behavior)
    - Useful for testing individual agents
    """

    def __init__(self):
        """Initialize mixin state."""
        self._shared_context: Optional['SharedParslContext'] = None
        self._standalone_context: Optional[StandaloneParslContext] = None
        self._manager: Optional[Manager] = None
        self._manager_initialized: bool = False
        self._using_shared_parsl: bool = False
        self._logger = logging.getLogger(self.__class__.__name__)

    @property
    def parsl_context(self) -> Optional[Any]:
        """Get the current Parsl context (shared or standalone)."""
        return self._shared_context or self._standalone_context

    @property
    def is_using_shared_parsl(self) -> bool:
        """Check if agent is using shared Parsl context."""
        return self._using_shared_parsl

    async def _initialize_manager(
        self,
        executor: Optional[Any] = None
    ) -> Manager:
        """
        Initialize Academy manager with proper lifecycle management.

        Args:
            executor: Optional executor (uses ThreadPoolExecutor if not provided)

        Returns:
            Initialized Manager instance
        """
        if self._manager_initialized and self._manager:
            return self._manager

        self._manager = await Manager.from_exchange_factory(
            factory=LocalExchangeFactory(),
            executors=executor or ThreadPoolExecutor(max_workers=4),
        )
        await self._manager.__aenter__()
        self._manager_initialized = True

        self._logger.info("Academy manager initialized")
        return self._manager

    async def _cleanup_manager(self) -> None:
        """Clean up Academy manager resources."""
        if self._manager_initialized and self._manager:
            try:
                await self._manager.__aexit__(None, None, None)
                self._logger.info("Academy manager context exited successfully")
            except Exception as e:
                self._logger.warning(f"Error exiting manager context: {e}")
            finally:
                self._manager = None
                self._manager_initialized = False

                # Clear initialized flag if it exists
                if hasattr(self, 'initialized'):
                    self.initialized = False

    async def _get_parsl_settings(
        self,
        data: Optional[Dict[str, Any]] = None,
        shared_context: Optional['SharedParslContext'] = None,
        settings_class: type = None,
        parsl_config: Optional[Dict[str, Any]] = None,
        run_dir: Optional[Path] = None,
        agent_id: Optional[str] = None,
    ) -> 'Config':
        """
        Get Parsl settings, preferring shared context if available.

        This is the KEY method that prevents nested Parsl configurations.

        Priority:
        1. If shared_context provided -> use its config (no new Config created)
        2. If data contains '_shared_parsl_context' -> use that
        3. Otherwise -> create standalone config (original behavior)

        Args:
            data: Optional data dict that may contain shared context
            shared_context: Explicit shared context from workflow
            settings_class: Parsl settings class (LocalSettings, etc.)
            parsl_config: Dict of parsl configuration options
            run_dir: Run directory for standalone mode
            agent_id: Agent ID for logging and resource tracking

        Returns:
            Parsl Config object
        """
        agent_id = agent_id or getattr(self, 'agent_id', 'unknown_agent')

        # Check for shared context in multiple places
        context = shared_context
        if context is None and data is not None:
            context = data.get('_shared_parsl_context')

        if context is not None:
            # Using shared context - NO new Parsl config created
            self._shared_context = context
            self._using_shared_parsl = True
            self._logger.info(
                f"Agent {agent_id} using shared Parsl context "
                f"(run_dir: {context.run_dir})"
            )
            return context.config

        # Standalone mode - create our own config
        self._using_shared_parsl = False
        self._logger.info(
            f"Agent {agent_id} creating standalone Parsl config "
            "(not using shared context)"
        )

        if settings_class is None:
            from ..utils.parsl_settings import LocalSettings
            settings_class = LocalSettings

        parsl_config = parsl_config or {}

        # Merge any parsl overrides from data
        if data is not None and 'parsl' in data:
            parsl_overrides = data.get('parsl', {})
            if isinstance(parsl_overrides, dict):
                for k, v in parsl_overrides.items():
                    parsl_config[k] = v

        run_dir = run_dir or Path.cwd()

        # Create standalone context for tracking
        self._standalone_context = StandaloneParslContext(
            run_dir=run_dir,
            is_standalone=True,
        )

        # Create the config
        config = settings_class(**parsl_config).config_factory(run_dir)
        self._standalone_context.config = config

        return config

    async def _get_allocated_accelerators(
        self,
        agent_id: Optional[str] = None,
        requested_count: int = 1
    ) -> List[str]:
        """
        Get allocated accelerators for this agent.

        If using shared context, uses workflow's allocation.
        If standalone, returns default accelerators.

        Args:
            agent_id: Agent ID for allocation tracking
            requested_count: Number of accelerators requested

        Returns:
            List of allocated accelerator IDs
        """
        agent_id = agent_id or getattr(self, 'agent_id', 'unknown_agent')

        if self._shared_context is not None:
            # Request allocation from shared context
            try:
                accelerators = await self._shared_context.allocate_accelerators(
                    agent_id,
                    count=requested_count
                )
                return accelerators
            except Exception as e:
                self._logger.warning(f"Failed to allocate accelerators: {e}")
                return [str(i) for i in range(requested_count)]

        # Standalone mode - use default accelerators
        if self._standalone_context is not None:
            self._standalone_context.allocated_accelerators = [
                str(i) for i in range(requested_count)
            ]
            return self._standalone_context.allocated_accelerators

        return [str(i) for i in range(requested_count)]

    async def _release_accelerators(self, agent_id: Optional[str] = None) -> None:
        """Release accelerators back to the pool."""
        agent_id = agent_id or getattr(self, 'agent_id', 'unknown_agent')

        if self._shared_context is not None:
            try:
                await self._shared_context.release_accelerators(agent_id)
            except Exception as e:
                self._logger.warning(f"Failed to release accelerators: {e}")


class WorkerAgentBase(SharedParslMixin):
    """
    Base class for worker agents that combines SharedParslMixin with
    common agent functionality.

    Provides:
    - Parsl context management (shared or standalone)
    - Academy manager lifecycle
    - Standard cleanup pattern
    - Ready-state tracking
    """

    def __init__(
        self,
        agent_id: str,
        config: Dict[str, Any],
        parsl_config: Dict[str, Any],
    ):
        """
        Initialize worker agent base.

        Args:
            agent_id: Unique identifier for this agent
            config: Agent-specific configuration
            parsl_config: Parsl configuration dict
        """
        super().__init__()

        self.agent_id = agent_id
        self.config = config
        self.parsl_config = parsl_config
        self.initialized = False

        self._logger = logging.getLogger(f"{self.__class__.__name__}.{agent_id}")

    async def is_ready(self, data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Check if agent is ready, initializing if needed.

        Args:
            data: Optional data dict (may contain shared context)

        Returns:
            True if agent is initialized and ready
        """
        if not self.initialized:
            await self.initialize(data)
        return self.initialized

    async def initialize(self, data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Initialize agent. Override in subclasses.

        Args:
            data: Optional initialization data

        Returns:
            True if initialization successful
        """
        raise NotImplementedError("Subclasses must implement initialize()")

    async def cleanup(self) -> None:
        """
        Clean up agent resources.

        Handles:
        - Academy manager cleanup
        - Accelerator release
        - State reset
        """
        try:
            # Release accelerators if using shared context
            await self._release_accelerators(self.agent_id)

            # Clean up Academy manager
            await self._cleanup_manager()

            self.initialized = False
            self._logger.info(f"Agent {self.agent_id} cleanup completed")

        except Exception as e:
            self._logger.error(f"Agent {self.agent_id} cleanup failed: {e}")
