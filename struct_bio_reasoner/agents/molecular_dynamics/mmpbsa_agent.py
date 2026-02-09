from academy.agent import Agent, action
import asyncio
import logging
from parsl import python_app, Config
from pathlib import Path
from typing import Any

from .distributed import parsl_mmpbsa, prepare_mmpbsa

logger = logging.getLogger(__name__)

class FEAgent(Agent):
    """Coordinator that orchestrates Parsl tasks."""
    def __init__(
        self, 
        n_cpus: int,
        amberhome: str,
    ) -> None:
        super().__init__()

        self.n_cpus = n_cpus
        self.amberhome = amberhome

    @action
    async def run(
        self,
        paths: list[Path],
    ) -> list[dict[str, Any]]:
        """Deploy full MD workflow using Parsl.
        fe_kwargs is a list of kwargs dicts which have the following
        structure: {
            'top': Path,
            'dcd': Path,
            'selections': [':1-n_target', ':n_target-n_binder'],
            'out': Path,
            'n_cpus': int,
            'amberhome': str
        }
        """
        logger.info('Computing free energy with MM-PBSA!')
        
        kwarg_futures = [
            asyncio.wrap_future(prepare_mmpbsa(path)) for path in paths
        ]

        fe_kwargs = await asyncio.gather(*kwarg_futures)
        
        for kwargs in fe_kwargs:
            kwargs.update({
                'n_cpus': self.n_cpus,
                'amberhome': self.amberhome
            })

            fe_futures.append(asyncio.wrap_future(parsl_mmpbsa(kwargs)))

        return await asyncio.gather(*fe_futures)
