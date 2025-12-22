"""
MDAgent Adapter for StructBioReasoner

This module provides an adapter that wraps MDAgent components (Builder, MDSimulator, MDCoordinator)
to work seamlessly within StructBioReasoner's agent framework.

The adapter translates between:
- Academy's @action pattern → StructBioReasoner's async methods
- MDAgent's Handle communication → Direct method calls  
- MD simulation results → ProteinHypothesis objects
"""

import dill as pickle
import asyncio
import logging
from ...utils.parsl_settings import AuroraSettings
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import numpy as np
from datetime import datetime
from MDAgent.core.agents_no_FE import Builder, MDSimulator, MDCoordinator
from molecular_simulations.build import ImplicitSolvent, ExplicitSolvent
from molecular_simulations.simulate import ImplicitSimulator, Simulator

from academy.exchange import LocalExchangeFactory, RedisExchangeFactory
from academy.manager import Manager
from academy.concurrent import ParslPoolExecutor
from concurrent.futures import ThreadPoolExecutor
    

class MDAgentAdapter:
    """
    Adapter that wraps MDAgent components to work within StructBioReasoner.
    
    This adapter enables StructBioReasoner to use MDAgent's proven MD simulation
    workflow while maintaining compatibility with the hypothesis-centric design.
    
    Key Features:
    - Wraps MDAgent's Builder, MDSimulator, and MDCoordinator
    - Converts MD results to ProteinHypothesis objects
    - Supports both implicit and explicit solvent models
    - Integrates with StructBioReasoner's role-based orchestration
    """
    
    def __init__(self, 
                 agent_id: str,
                 paths: list[Path],
                 out: Path,
                 config: Dict[str, Any],
                 parsl_config: Dict[str, Any],
                 steps: int=12500000):
        """
        Initialize MDAgent adapter.
        
        Args:
            config: Configuration dictionary with MDAgent settings
        """
        self.agent_id = agent_id
        self.config = config

        self.agent_type = "md_simulation"
        self.specialization = "mdagent_backend"
        self.logger = logging.getLogger(__name__)
        
        self.paths = paths
        self.root_out = out
        self.steps = steps

        # MDAgent configuration
        self.mdagent_config = self.config.get("mdagent", {})
        self.solvent_model = self.mdagent_config.get("solvent_model", "explicit")
        self.amberhome = self.mdagent_config.get('amberhome', None)
        self.build_kwargs = self.mdagent_config.get('build_kwargs', {})
        self.sim_kwargs = self.mdagent_config.get('sim_kwargs', {})
        
        # Simulation parameters
        self.equil_steps = self.mdagent_config.get("equil_steps", 10_000)
        self.prod_steps = self.mdagent_config.get("prod_steps", 1_000_000)
        
        p_steps = self.prod_steps * 4 / 1000000
        self.logger.info(f'Will run MD for {p_steps} ns')
        
        # MDAgent components (initialized in initialize())
        self.manager = None
        self.builder_handle = None
        self.simulator_handle = None
        self.coordinator_handle = None

        # Load parsl kwargs
        self.parsl_config = parsl_config

    async def initialize(self,
                         parsl: Optional[dict] = None) -> bool:
        """
        Initialize MDAgent components.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            parsl_settings = AuroraSettings(**self.parsl_config).config_factory(Path.cwd())
            local_settings = LocalSettings(**self.parsl_config).config_factory(Path.cwd())

            executor = ParslPoolExecutor(parsl_settings)
            # Create Academy manager using async context manager pattern
            # This ensures the exchange client is properly initialized
            self.manager = await Manager.from_exchange_factory(
                factory=RedisExchangeFactory('localhost', 6379),
                executors=executor,
            )

            # Enter the manager context to initialize exchange client
            await self.manager.__aenter__()
            
            # Launch MDAgent components
            self.builder_handle = await self.manager.launch(
                Builder, args=(
                    ImplicitSolvent, ExplicitSolvent
                )
            )
            self.simulator_handle = await self.manager.launch(
                MDSimulator, args=(
                    ImplicitSimulator, Simulator
                )
            )

            self.coordinator_handle = await self.manager.launch(
                MDCoordinator,
                args=(self.builder_handle, self.simulator_handle, local_settings)
            )

            self.initialized = True
            self.logger.info("MDAgent components initialized successfully")
            return True

        except Exception as e:
            self.logger.exception('An error occurred with the MDAgentAdapter')

            self.initialized = False
            return False
    
    async def run_md_simulation(self) -> dict:
        """
        Run complete MD simulation using MDAgent coordinator.

        Args:
            pdb_path: Path to input PDB file or list of PDB files
            protein_name: Name of the protein
            custom_build_kwargs: Custom build parameters (optional)
            custom_sim_kwargs: Custom simulation parameters (optional)

        Returns:
            Simulation results dictionary
        """
        try:
            # Create simulation directory
            sim_id = f"mdagent_{protein_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            for path in self.paths:
                self.logger.info(f'Running simulations at: {pdb}')

            # Prepare build kwargs
            build_kwargs = self.build_kwargs or {
                'solvent': self.solvent_model,
                'protein': True,
                'out': 'system.pdb',
            }
            
            if 'amberhome' not in build_kwargs:
                build_kwargs['amberhome'] = self.amberhome

            # Prepare simulation kwargs
            sim_kwargs = self.sim_kwargs or {
                'solvent': self.solvent_model,
                'equil_steps': self.equil_steps,
                'prod_steps': self.prod_steps,
            }

            pdbs = [path.glob('*.pdb')[0] for path in self.paths]
            sim_paths = [Path(self.root_path) / f'mdagent_{i}' for i in range(len(self.paths))]
            for sim_path in sim_paths:
                sim_path.mkdir(parents=True, exist_ok=True)
            
            build_kwargs = [build_kwargs.copy() for _ in range(len(sim_paths))]
            sim_kwargs = [sim_kwargs.copy() for _ in range(len(sim_paths))]
            
            results = await self.coordinator_handle.deploy_md(
                paths=sim_paths,
                initial_pdbs=pdbs,
                build_kwargss=build_kwargs,
                sim_kwargss=sim_kwargs,
            )

            # Clean up agent/parsl
            await self.cleanup()
            
            self.logger.info(f"MDAgent simulation completed")

            return results

        except Exception as e:
            import traceback
            self.logger.info(traceback.format_exc())
            self.logger.error(f"MDAgent simulation failed: {e}")
            return {}
    
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get MDAgent adapter capabilities.
        
        Returns:
            Dictionary describing adapter capabilities
        """
        return {
            "agent_type": self.agent_type,
            "specialization": self.specialization,
            "mdagent_available": MDAGENT_AVAILABLE,
            "supported_solvent_models": ["implicit", "explicit"],
            "supported_force_fields": ["amber14", "charmm36"],
            "supported_water_models": ["tip3p", "tip4p", "spce"],
            "capabilities": [
                "system_building",
                "md_simulation",
                "implicit_solvent",
                "explicit_solvent",
                "equilibration",
                "production_runs"
            ],
            "integration_features": [
                "hypothesis_generation",
                "result_analysis",
                "trajectory_processing"
            ]
        }
    
    async def cleanup(self) -> None:
        """Clean up MDAgent resources."""
        try:
            # Exit and close Academy manager context
            if self.manager:
                try:
                    await self.manager.__aexit__(None, None, None)
                    self.logger.info("Academy manager context exited successfully")
                except Exception as e:
                    self.logger.warning(f"Error exiting manager context: {e}")
                finally:
                    self.manager = None
                    self.builder_handle = None
                    self.simulator_handle = None
                    self.coordinator_handle = None
                    delattr(self, 'initialized')

            self.logger.info("MDAgent adapter cleanup completed")

        except Exception as e:
            self.logger.error(f"MDAgent adapter cleanup failed: {e}")

    async def run(self) -> dict:
        if not await self.initialize():
            return {}
        else:
            sim_results = await self.run_md_simulation()
            return sim_results

    def _calculate_confidence(self,
                              analysis: SimAnalysis) -> float:
        # TODO: compute this based on RMSD/RMSF threshholds
        return 0.75

    def _get_tools_used(self) -> list[str]:
        return ['openmm', 'mdanalysis']
