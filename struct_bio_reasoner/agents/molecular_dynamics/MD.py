from academy.agent import Agent, action
import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

class MDCoordinator(Agent):
    """Coordinator that orchestrates Parsl tasks."""
    def __init__(
        self, 
    ) -> None:
        super().__init__()

    @action
    async def build_system(
        self,
        paths: list[Path],
        structural_inputs: list[Path],
        build_kwargss: list[dict[str, Any]]
    ) -> list[Path]:
        """Submit build tasks to Parsl and wait for completion."""
        futures = []
        for path, pdb, build_kwargs in zip(paths, structural_inputs, build_kwargss):
            print(path, pdb, build_kwargs)
            # Call the Parsl app directly, not through the Agent
            app_future = parsl_build(path, pdb, build_kwargs)
            futures.append(app_future)

        # Convert Parsl futures to async futures and wait
        async_futures = [asyncio.wrap_future(f) for f in futures]
        paths = await asyncio.gather(*async_futures)
        return [path for path in paths if path]

    @action
    async def run_simulation(
        self,
        simulation_paths: list[Path],
        sim_kwargss: list[dict[str, Any]]
    ) -> list[Path]:
        """Submit simulation tasks to Parsl and wait for completion."""
        futures = []
        for path, sim_kwargs in zip(simulation_paths, sim_kwargss):
            # Call the Parsl app directly
            app_future = parsl_simulate(path, sim_kwargs)
            futures.append(app_future)
        
        # Convert and wait
        async_futures = [asyncio.wrap_future(f) for f in futures]
        paths = await asyncio.gather(*async_futures)
        return [path for path in paths if path]

    @action
    async def run(
        self,
        paths: list[Path],
        initial_pdbs: list[Path],
        build_kwargss: list[dict[str, Any]],
        sim_kwargss: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Deploy full MD workflow using Parsl."""
        logger.info(f'Building systems at: {paths}')
        built_paths = await self.build_system(paths, initial_pdbs, build_kwargss)
        
        logger.info(f'Successfully built systems. Simulating at: {built_paths}')
        sim_paths = await self.run_simulation(built_paths, sim_kwargss)

        return sim_paths
