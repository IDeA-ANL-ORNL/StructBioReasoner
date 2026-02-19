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
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import parsl
import yaml

from academy.exchange import LocalExchangeFactory
from academy.logging import init_logging
from academy.manager import Manager

from struct_bio_reasoner.agents.data.data_agent import DataAgent
from struct_bio_reasoner.agents.data.events import EventType
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

        # Persistence identifiers
        self.experiment_id = str(uuid.uuid4())
        self.data_agent_handle: Optional[Any] = None

        # Map director labels → assigned UUIDs for DB consistency
        self._director_ids: Dict[str, str] = {}

        # Output directory
        self._output_dir = Path(config.output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "TestExecutive initialised: %d directors, accelerators split %s",
            config.num_directors,
            [len(c) for c in self.accel_chunks],
        )

    # ----- start -----------------------------------------------------------

    async def _emit(self, event: dict[str, Any]) -> None:
        """Fire-and-forget an event to the executive-level DataAgent."""
        if self.data_agent_handle is None:
            return
        try:
            await self.data_agent_handle.record_event(event)
        except Exception:
            logger.debug("Executive DataAgent event emission failed", exc_info=True)

    async def start(self) -> None:
        """Load Parsl, create Academy Manager, launch LocalDirectors."""
        init_logging(logging.INFO)

        # --- 1. Load Parsl once at the executive level ---
        run_dir = self._output_dir
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

        # --- 3. Launch executive-level DataAgent ---
        database_url = self.yaml_config.get(
            "database_url",
            f"sqlite+aiosqlite:///{run_dir / 'data.db'}",
        )
        self.data_agent_handle = await self.academy_manager.launch(
            DataAgent,
            kwargs={"database_url": database_url},
        )
        logger.info("Executive DataAgent launched")

        # --- 4. Emit EXPERIMENT_START ---
        await self._emit({
            "event_type": EventType.EXPERIMENT_START.value,
            "director_id": "",
            "experiment_id": self.experiment_id,
            "payload": {
                "experiment_id": self.experiment_id,
                "research_goal": self.yaml_config.get(
                    "reasoner", {}
                ).get("research_goal", ""),
                "config_snapshot": self.yaml_config,
                "num_directors": self.config.num_directors,
            },
        })

        # --- 5. Launch LocalDirectors ---
        for i, chunk in enumerate(self.accel_chunks):
            director_label = f"director_{i}"
            director_id = str(uuid.uuid4())
            self._director_ids[director_label] = director_id

            runtime = build_director_runtime(self.yaml_config, chunk)
            # Inject director_id and shared database_url so the Director's
            # DataAgent writes to the same database.
            runtime['director_id'] = director_id
            runtime['database_url'] = database_url

            director_settings = LocalSettings(
                available_accelerators=chunk,
                nodes=1,
            )

            handle = await self.academy_manager.launch(
                LocalDirector,
                args=(runtime, director_settings),
            )
            self.director_handles[director_label] = handle
            logger.info(
                "Launched %s (id=%s) with accelerators %s",
                director_label,
                director_id,
                chunk,
            )

            # Emit DIRECTOR_START
            await self._emit({
                "event_type": EventType.DIRECTOR_START.value,
                "director_id": director_id,
                "experiment_id": self.experiment_id,
                "payload": {
                    "external_label": director_label,
                    "accelerator_ids": chunk,
                    "target_protein": self.yaml_config.get(
                        "reasoner", {}
                    ).get("target_protein", ""),
                    "config_snapshot": runtime,
                },
            })

        self._start_time = time.monotonic()
        logger.info("All %d directors launched", len(self.director_handles))

    # ----- run -------------------------------------------------------------

    async def run(self) -> None:
        """Kick off each director's agentic loop and enter the review loop."""
        # Start agentic_run for each director as a background task
        for director_label, handle in self.director_handles.items():
            task = asyncio.create_task(
                handle.agentic_run(),
                name=f"run_{director_label}",
            )
            self.director_tasks[director_label] = task

        logger.info("Director agentic loops started — entering review loop")

        # Review loop
        while not self._should_stop():
            await asyncio.sleep(self.config.review_interval_seconds)

            # Aggregate experiment-level stats from DataAgent
            summary: dict = {}
            insights: dict = {}
            if self.data_agent_handle:
                try:
                    summary = await self.data_agent_handle.get_experiment_summary(
                        self.experiment_id
                    )
                    insights = await self.data_agent_handle.get_cross_director_insights(
                        self.experiment_id
                    )
                    logger.info(
                        "Experiment summary: %d tasks completed, %d failed, avg %.0fms",
                        summary.get("completed", 0),
                        summary.get("failed", 0),
                        summary.get("avg_duration_ms") or 0,
                    )
                except Exception:
                    logger.debug("DataAgent summary query failed", exc_info=True)

            for director_label, handle in self.director_handles.items():
                director_id = self._director_ids.get(director_label, director_label)
                task = self.director_tasks.get(director_label)

                if task and task.done():
                    logger.info("%s: agentic_run finished", director_label)
                    snapshot = "completed"
                    try:
                        await task
                    except Exception as exc:
                        logger.error("%s: agentic_run error: %s", director_label, exc)
                        snapshot = str(exc)

                    await self._emit({
                        "event_type": EventType.EXECUTIVE_ACTION.value,
                        "director_id": director_id,
                        "experiment_id": self.experiment_id,
                        "payload": {
                            "action_type": "observed_finished",
                            "status_snapshot": snapshot,
                        },
                    })
                    continue

                try:
                    status = await handle.check_status()
                    logger.info("%s status: %s", director_label, status)

                    action = await self._evaluate_director(
                        director_label, handle, summary, insights,
                    )

                    await self._emit({
                        "event_type": EventType.EXECUTIVE_ACTION.value,
                        "director_id": director_id,
                        "experiment_id": self.experiment_id,
                        "payload": {
                            "action_type": action,
                            "status_snapshot": str(status),
                        },
                    })

                    if action == "advise":
                        advice = (
                            f"High failure rate detected ({summary.get('failed', 0)}"
                            f"/{summary.get('total_tasks', 0)} tasks failed). "
                            f"Consider changing strategy or parameters."
                        )
                        try:
                            await handle.receive_instruction(advice)
                        except Exception:
                            logger.debug(
                                "Failed to send instruction to %s",
                                director_label,
                                exc_info=True,
                            )
                except Exception as exc:
                    logger.warning(
                        "%s: check_status failed: %s", director_label, exc,
                    )

        logger.info("Review loop ended")

    async def _evaluate_director(
        self,
        director_label: str,
        handle: Any,
        summary: dict,
        insights: dict,
    ) -> str:
        """Decide KILL / ADVISE / CONTINUE for a director."""
        director_id = self._director_ids.get(director_label, director_label)

        # Get per-director recovery state as a proxy for recent progress
        if self.data_agent_handle:
            try:
                state = await self.data_agent_handle.get_recovery_state(director_id)
            except Exception:
                state = {}
        else:
            state = {}

        action = "continue"

        # If the summary shows high failure rate, advise
        total = summary.get("total_tasks", 0)
        failed = summary.get("failed", 0)
        if total > 5 and failed / max(total, 1) > 0.5:
            action = "advise"

        return action

    # ----- stop ------------------------------------------------------------

    async def stop(self) -> None:
        """Cancel director tasks and tear down resources."""
        self._shutdown_requested = True

        # Cancel running director tasks
        for director_label, task in self.director_tasks.items():
            if not task.done():
                task.cancel()
                logger.info("Cancelled %s", director_label)

        if self.director_tasks:
            await asyncio.gather(
                *self.director_tasks.values(), return_exceptions=True,
            )

        # Emit DIRECTOR_END for each director
        for director_label in self.director_handles:
            director_id = self._director_ids.get(director_label, director_label)
            task = self.director_tasks.get(director_label)
            reason = "completed" if (task and task.done()) else "shutdown"
            await self._emit({
                "event_type": EventType.DIRECTOR_END.value,
                "director_id": director_id,
                "payload": {"reason": reason},
            })

        # Emit EXPERIMENT_END
        await self._emit({
            "event_type": EventType.EXPERIMENT_END.value,
            "director_id": "",
            "payload": {
                "experiment_id": self.experiment_id,
                "status": "completed",
            },
        })

        # Export data to Parquet
        if self.data_agent_handle:
            try:
                export_dir = str(self._output_dir / "exports")
                paths = await self.data_agent_handle.export_to_parquet(
                    output_dir=export_dir,
                    experiment_id=self.experiment_id,
                )
                logger.info("Exported %d tables to %s", len(paths), export_dir)
            except Exception:
                logger.warning("Parquet export failed", exc_info=True)

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
