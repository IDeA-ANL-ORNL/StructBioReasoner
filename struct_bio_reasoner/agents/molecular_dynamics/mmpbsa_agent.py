from academy.agent import Agent, action
import asyncio
import logging
from parsl import python_app, Config
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

class FECoordinator(Agent):
    """Coordinator that orchestrates Parsl tasks."""
    def __init__(
        self, 
    ) -> None:
        super().__init__()

    @action
    async def run_mmpbsa(
        self,
        fe_kwargss: list[dict[str, Any]]
    ) -> list[float]:
        """Submit MMPBSA tasks to Parsl and wait for completion."""
        futures = []
        for fe_kwargs in fe_kwargss:
            # Call the Parsl app directly
            app_future = parsl_mmpbsa(fe_kwargs)
            futures.append(asyncio.wrap_future(app_future))

        return await asyncio.gather(*futures)

    @action
    async def deploy(
        self,
        paths: list[Path],
        fe_kwargss: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Deploy full MD workflow using Parsl."""
        logger.info('Computing free energy with MM-PBSA!')
        futures = []
        # Update fe_kwargs with paths from simulations
        for path, fe_kwargs in zip(paths, fe_kwargss):
            logger.info(f'Will run at: {path}')
            fe_kwargs.update({
                'top': path / 'system.prmtop',
                'dcd': path / 'prod.dcd'
            })

            futures.append(asyncio.wrap_future(parsl_mmpbsa(fe_kwargs)))

        return await asyncio.gather(*futures)
