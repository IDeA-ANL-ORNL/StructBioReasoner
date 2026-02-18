"""
Test Executive for single-node local testing.

Loads Parsl once at the executive level, then launches N LocalDirector
instances that share the pre-loaded DFK.  This avoids the global-state
conflict that arises when multiple Directors each call ``parsl.load()``.

Usage::

    python -m struct_bio_reasoner.agents.executive.test_executive \
        --config config/binder_config.yaml \
        --num-directors 2 \
        --output-dir test_executive_output \
        --max-runtime 60
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import parsl
import yaml

from academy.exchange import LocalExchangeFactory
from academy.logging import init_logging
from academy.manager import Manager

from struct_bio_reasoner.agents.director.director_agent import Director
from struct_bio_reasoner.utils.parsl_settings import (
    LocalSettings,
    resource_summary_from_config,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def split_list(lst: list, n: int) -> list[list]:
    """Split *lst* into *n* roughly-equal chunks."""
    k, m = divmod(len(lst), n)
    return [lst[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n)]


def build_director_runtime(
    base_config: dict[str, Any],
    accelerator_chunk: list[str],
) -> dict[str, Any]:
    """Return a per-director runtime config with its accelerator slice."""
    runtime = dict(base_config)
    runtime['parsl'] = {
        **base_config.get('parsl', {}),
        'available_accelerators': accelerator_chunk,
    }
    return runtime


# ---------------------------------------------------------------------------
# LocalDirector — shares a pre-loaded Parsl DFK
# ---------------------------------------------------------------------------

class LocalDirector(Director):
    """Director that shares a pre-loaded Parsl DFK (for local testing).

    Instead of calling ``parsl.load()`` / ``parsl.clear()`` itself, it
    grabs the already-loaded global DFK created by :class:`TestExecutive`.
    """

    async def agent_on_startup(self) -> None:
        self.dfk = parsl.dfk()        # grab the already-loaded global DFK
        await self.load_agents()

    async def agent_on_shutdown(self) -> None:
        self.dfk = None                # don't cleanup — executive owns the DFK


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class TestExecutiveConfig:
    """Configuration for the local test executive."""

    config_path: str = "config/binder_config.yaml"
    num_directors: int = 2
    output_dir: str = "test_executive_output"
    max_runtime_minutes: float = 60.0
    review_interval_seconds: float = 120.0


# ---------------------------------------------------------------------------
# TestExecutive
# ---------------------------------------------------------------------------

class TestExecutive:
    """Single-node orchestrator that launches N LocalDirectors.

    Lifecycle:
        1. ``__init__``: parse config, compute accelerator splits.
        2. ``start()``: load Parsl once, create Academy Manager, launch
           LocalDirectors via ``manager.launch()``.
        3. ``run()``: start each director's ``agentic_run`` as an
           ``asyncio.Task`` and enter the review loop.
        4. ``stop()``: cancel director tasks, cleanup Academy Manager,
           cleanup Parsl.
    """

    def __init__(self, config: TestExecutiveConfig) -> None:
        self.config = config

        # Load YAML config
        with open(config.config_path) as fh:
            self.yaml_config: dict[str, Any] = yaml.safe_load(fh)

        # Accelerator splitting
        parsl_section = self.yaml_config.get('parsl', {})
        all_accels: list[str] = parsl_section.get(
            'available_accelerators',
            [str(i) for i in range(12)],
        )
        self.accel_chunks = split_list(all_accels, config.num_directors)

        # Runtime state
        self.academy_manager: Optional[Manager] = None
        self.director_handles: Dict[str, Any] = {}
        self.director_tasks: Dict[str, asyncio.Task] = {}
        self._shutdown_requested = False
        self._start_time: Optional[float] = None

        # Output directory
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)

        logger.info(
            "TestExecutive initialised: %d directors, accelerators split %s",
            config.num_directors,
            [len(c) for c in self.accel_chunks],
        )

    # ----- start -----------------------------------------------------------

    async def start(self) -> None:
        """Load Parsl, create Academy Manager, launch LocalDirectors."""
        init_logging(logging.INFO)

        # --- 1. Load Parsl once at the executive level ---
        run_dir = Path(self.config.output_dir)
        parsl_section = self.yaml_config.get('parsl', {})
        all_accels = parsl_section.get(
            'available_accelerators',
            [str(i) for i in range(12)],
        )
        settings = LocalSettings(
            available_accelerators=all_accels,
            nodes=parsl_section.get('nodes', 1),
            worker_init=parsl_section.get('worker_init', ''),
        )
        parsl_config = settings.config_factory(run_dir)
        parsl.load(parsl_config)
        logger.info("Parsl loaded (executive-level DFK)")

        # --- 2. Academy Manager ---
        factory = LocalExchangeFactory()
        self.academy_manager = await Manager.from_exchange_factory(
            factory=factory,
        )
        await self.academy_manager.__aenter__()
        logger.info("Academy Manager ready")

        # --- 3. Launch LocalDirectors ---
        for i, chunk in enumerate(self.accel_chunks):
            director_id = f"director_{i}"
            runtime = build_director_runtime(self.yaml_config, chunk)
            director_settings = LocalSettings(
                available_accelerators=chunk,
                nodes=1,
            )

            handle = await self.academy_manager.launch(
                LocalDirector,
                args=(runtime, director_settings),
            )
            self.director_handles[director_id] = handle
            logger.info(
                "Launched %s with accelerators %s",
                director_id,
                chunk,
            )

        self._start_time = time.monotonic()
        logger.info("All %d directors launched", len(self.director_handles))

    # ----- run -------------------------------------------------------------

    async def run(self) -> None:
        """Kick off each director's agentic loop and enter the review loop."""
        # Start agentic_run for each director as a background task
        for director_id, handle in self.director_handles.items():
            task = asyncio.create_task(
                handle.agentic_run(),
                name=f"run_{director_id}",
            )
            self.director_tasks[director_id] = task

        logger.info("Director agentic loops started — entering review loop")

        # Review loop
        while not self._should_stop():
            await asyncio.sleep(self.config.review_interval_seconds)

            for director_id, handle in self.director_handles.items():
                task = self.director_tasks.get(director_id)
                if task and task.done():
                    logger.info("%s: agentic_run finished", director_id)
                    try:
                        await task
                    except Exception as exc:
                        logger.error("%s: agentic_run error: %s", director_id, exc)
                    continue

                try:
                    status = await handle.check_status()
                    logger.info("%s status: %s", director_id, status)
                except Exception as exc:
                    logger.warning(
                        "%s: check_status failed: %s", director_id, exc,
                    )

        logger.info("Review loop ended")

    # ----- stop ------------------------------------------------------------

    async def stop(self) -> None:
        """Cancel director tasks and tear down resources."""
        self._shutdown_requested = True

        # Cancel running director tasks
        for director_id, task in self.director_tasks.items():
            if not task.done():
                task.cancel()
                logger.info("Cancelled %s", director_id)

        if self.director_tasks:
            await asyncio.gather(
                *self.director_tasks.values(), return_exceptions=True,
            )

        # Academy Manager cleanup
        if self.academy_manager:
            await self.academy_manager.__aexit__(None, None, None)
            logger.info("Academy Manager shut down")

        # Parsl cleanup
        try:
            dfk = parsl.dfk()
            dfk.cleanup()
        except Exception:
            pass
        parsl.clear()
        logger.info("Parsl cleaned up")

    # ----- main (convenience) ---------------------------------------------

    async def main(self) -> None:
        """Convenience entry point: start → run → stop."""
        try:
            await self.start()
            await self.run()
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received")
        finally:
            await self.stop()

    # ----- internals -------------------------------------------------------

    def _should_stop(self) -> bool:
        if self._shutdown_requested:
            return True

        # Max runtime exceeded
        if self._start_time is not None:
            elapsed_minutes = (time.monotonic() - self._start_time) / 60.0
            if elapsed_minutes >= self.config.max_runtime_minutes:
                logger.info(
                    "Max runtime (%.1f min) reached", self.config.max_runtime_minutes,
                )
                return True

        # All directors finished
        if all(t.done() for t in self.director_tasks.values()):
            logger.info("All directors finished")
            return True

        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local test executive for StructBioReasoner",
    )
    parser.add_argument(
        "--config",
        default="config/binder_config.yaml",
        help="Path to the YAML configuration file (default: config/binder_config.yaml)",
    )
    parser.add_argument(
        "--num-directors",
        type=int,
        default=2,
        help="Number of LocalDirectors to launch (default: 2)",
    )
    parser.add_argument(
        "--output-dir",
        default="test_executive_output",
        help="Output directory for run artifacts (default: test_executive_output)",
    )
    parser.add_argument(
        "--max-runtime",
        type=float,
        default=60.0,
        help="Maximum runtime in minutes (default: 60)",
    )
    parser.add_argument(
        "--review-interval",
        type=float,
        default=120.0,
        help="Seconds between status reviews (default: 120)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    cfg = TestExecutiveConfig(
        config_path=args.config,
        num_directors=args.num_directors,
        output_dir=args.output_dir,
        max_runtime_minutes=args.max_runtime,
        review_interval_seconds=args.review_interval,
    )

    executive = TestExecutive(cfg)
    asyncio.run(executive.main())
