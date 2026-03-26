"""Academy configuration — Exchange factory and Parsl executor setup.

Provides helpers to instantiate Academy's ``LocalExchangeFactory`` or
``RedisExchangeFactory``, and optionally a Parsl ``ParslPoolExecutor``
for HPC-scale parallelism.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AcademyConfig:
    """Unified configuration for the Academy execution fabric."""

    # Exchange mode: "local" or "redis"
    exchange_mode: str = "local"
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Parsl / executor settings
    use_parsl: bool = False
    parsl_config_path: Optional[str] = None
    parsl_settings: dict[str, Any] = field(default_factory=dict)

    # Thread pool fallback
    thread_pool_workers: int = 4

    # Compute budget
    total_compute_nodes: int = 4
    nodes_per_manager: int = 2

    # Agent hierarchy
    max_managers: int = 10
    max_tasks_per_campaign: int = 100
    min_binder_affinity: float = -10.0

    # Workflow timing
    progress_report_interval: float = 60.0
    executive_review_interval: float = 300.0
    max_runtime_hours: Optional[float] = None
    target_affinity: float = -15.0


def create_exchange_factory(config: AcademyConfig) -> Any:
    """Create an Academy exchange factory based on *config*.

    Returns either a ``LocalExchangeFactory`` (in-process, laptop mode)
    or a ``RedisExchangeFactory`` (distributed, HPC mode).
    """
    from academy.exchange import LocalExchangeFactory, RedisExchangeFactory

    if config.exchange_mode == "redis":
        logger.info(
            "Creating RedisExchangeFactory (%s:%d)",
            config.redis_host,
            config.redis_port,
        )
        return RedisExchangeFactory(config.redis_host, config.redis_port)

    logger.info("Creating LocalExchangeFactory (in-process)")
    return LocalExchangeFactory()


def create_parsl_executor(config: AcademyConfig) -> Any:
    """Create either a Parsl pool executor or a plain ``ThreadPoolExecutor``.

    When ``config.use_parsl`` is *True* and a ``parsl_config_path`` is given,
    this builds a full ``ParslPoolExecutor`` with the Parsl configuration.
    Otherwise falls back to a ``ThreadPoolExecutor``.
    """
    if config.use_parsl:
        try:
            from pathlib import Path

            import yaml
            from parsl import Config
            from parsl.concurrent import ParslPoolExecutor

            from struct_bio_reasoner.utils.parsl_settings import (
                AuroraSettings,
                LocalSettings,
            )

            if config.parsl_config_path:
                with open(config.parsl_config_path) as f:
                    raw = yaml.safe_load(f)
                settings = config.parsl_settings or raw
            else:
                settings = config.parsl_settings

            # Decide settings class based on exchange mode
            if config.exchange_mode == "redis":
                parsl_cfg = AuroraSettings(**settings).config_factory(Path.cwd())
            else:
                parsl_cfg = LocalSettings(**settings).config_factory(Path.cwd())

            logger.info("Created ParslPoolExecutor")
            return ParslPoolExecutor(parsl_cfg)

        except ImportError:
            logger.warning("Parsl not installed — falling back to ThreadPoolExecutor")

    logger.info(
        "Using ThreadPoolExecutor with %d workers", config.thread_pool_workers
    )
    return ThreadPoolExecutor(max_workers=config.thread_pool_workers)
