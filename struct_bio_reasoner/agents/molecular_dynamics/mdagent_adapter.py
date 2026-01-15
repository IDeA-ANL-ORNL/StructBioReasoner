"""
MDAgent Adapter for StructBioReasoner

This module provides an adapter that wraps MDAgent components (Builder, MDSimulator, MDCoordinator)
to work seamlessly within StructBioReasoner's agent framework.

The adapter uses SharedParslMixin to avoid nested Parsl configuration collisions
when running within the hierarchical workflow.
"""

import dill as pickle
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, TYPE_CHECKING
import numpy as np
from datetime import datetime

from ...utils.parsl_settings import AuroraSettings, LocalSettings

# MDAgent imports (from https://github.com/msinclair-py/MDAgent)
try:
    from academy.exchange import LocalExchangeFactory
    from academy.manager import Manager
    from concurrent.futures import ThreadPoolExecutor

    MDAGENT_AVAILABLE = True
except ImportError:
    MDAGENT_AVAILABLE = False
    logging.warning("MDAgent not available. Install from https://github.com/msinclair-py/MDAgent")

from ...core.base_agent import BaseAgent
from ...data.protein_hypothesis import SimAnalysis, ProteinHypothesis
from ..shared_parsl_mixin import SharedParslMixin

if TYPE_CHECKING:
    from ...workflows.advanced_workflow import SharedParslContext


class MDAgentAdapter(SharedParslMixin):
    """
    Adapter that wraps MDAgent components to work within StructBioReasoner.

    This adapter uses SharedParslMixin to support:
    1. Shared Parsl context from workflow (prevents nested config collisions)
    2. Standalone mode for testing (original behavior)

    Key Features:
    - Wraps MDAgent's Builder, MDSimulator, and MDCoordinator
    - Converts MD results to ProteinHypothesis objects
    - Supports both implicit and explicit solvent models
    - Integrates with StructBioReasoner's role-based orchestration
    """

    def __init__(
        self,
        agent_id: str,
        config: Dict[str, Any],
        parsl_config: Dict[str, Any]
    ):
        """
        Initialize MDAgent adapter.

        Args:
            agent_id: Unique identifier for this agent
            config: Configuration dictionary with MDAgent settings
            parsl_config: Parsl configuration dictionary
        """
        # Initialize the mixin
        super().__init__()

        self.agent_id = agent_id
        self.config = config
        self.agent_type = "md_simulation"
        self.specialization = "mdagent_backend"
        self.logger = logging.getLogger(__name__)

        # MDAgent configuration
        self.mdagent_config = self.config.get("mdagent", {})
        self.solvent_model = self.mdagent_config.get("solvent_model", "explicit")
        self.force_field = self.mdagent_config.get("force_field", "amber14")
        self.water_model = self.mdagent_config.get("water_model", "tip3p")
        self.amberhome = self.mdagent_config.get('amberhome', None)

        # Simulation parameters
        self.equil_steps = self.mdagent_config.get("equil_steps", 10_000)
        self.prod_steps = self.mdagent_config.get("prod_steps", 20_000)

        p_steps = self.prod_steps * 4 / 1000000
        self.logger.info(f'Will run MD for {p_steps} ns')

        # MDAgent components (initialized in initialize())
        self.builder_handle = None
        self.simulator_handle = None
        self.coordinator_handle = None

        # Load parsl kwargs
        self.parsl_config = parsl_config

        # State tracking
        self.active_simulations = {}
        self.completed_simulations = {}

        self.logger.info(f"MDAgentAdapter initialized with {self.solvent_model} solvent")

    def __del__(self):
        """Destructor to ensure manager is cleaned up."""
        if hasattr(self, '_manager') and self._manager is not None:
            self.logger.warning("MDAgentAdapter deleted without proper cleanup - manager still active")

    async def initialize(
        self,
        parsl: Optional[Dict[str, Any]] = None,
        shared_context: Optional['SharedParslContext'] = None
    ) -> bool:
        """
        Initialize MDAgent components.

        Args:
            parsl: Optional parsl config overrides (for backwards compatibility)
            shared_context: Optional shared Parsl context from workflow

        Returns:
            True if initialization successful, False otherwise
        """
        if not MDAGENT_AVAILABLE:
            self.logger.error("MDAgent not available - cannot initialize adapter")
            self.initialized = False
            return False

        try:
            try:
                from MDAgent.core.agents_no_FE import Builder, MDSimulator, MDCoordinator
                from molecular_simulations.build import ImplicitSolvent, ExplicitSolvent
                from molecular_simulations.simulate import ImplicitSimulator, Simulator
            except ImportError as e:
                self.logger.error(f"Cannot import MDAgent components: {e}")
                self.logger.info("Make sure MDAgent is installed and in PYTHONPATH")
                self.logger.info("Install from: https://github.com/msinclair-py/MDAgent")
                self.initialized = False
                return False

            # Initialize Academy manager using mixin
            self.manager = await self._initialize_manager()

            # Prepare data dict for mixin
            data = {}
            if parsl is not None:
                data['parsl'] = parsl
            if shared_context is not None:
                data['_shared_parsl_context'] = shared_context

            # Launch MDAgent components
            self.builder_handle = await self.manager.launch(
                Builder, args=(ImplicitSolvent, ExplicitSolvent)
            )
            self.simulator_handle = await self.manager.launch(
                MDSimulator, args=(ImplicitSimulator, Simulator)
            )

            # Get Parsl settings using the mixin (key fix!)
            self.parsl_settings = await self._get_parsl_settings(
                data=data,
                shared_context=shared_context,
                settings_class=LocalSettings,
                parsl_config=self.parsl_config,
                agent_id=self.agent_id,
            )

            self.logger.info(f'Parsl settings obtained (shared: {self.is_using_shared_parsl})')
            self.logger.info('Launching coordinator')

            self.coordinator_handle = await self.manager.launch(
                MDCoordinator,
                args=(self.builder_handle, self.simulator_handle, self.parsl_settings)
            )

            self.initialized = True
            self.logger.info("MDAgent components initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize MDAgent: {e}")
            self.initialized = False

            # Clean up manager if it was created
            await self._cleanup_manager()
            return False

    async def run_md_simulation(
        self,
        root_path: Path,
        pdb_path: Union[Path, List[Path]],
        protein_name: str = "unknown",
        custom_build_kwargs: Optional[Dict[str, Any]] = None,
        custom_sim_kwargs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run complete MD simulation using MDAgent coordinator.

        Args:
            root_path: Root path for output
            pdb_path: Path to input PDB file or list of PDB files
            protein_name: Name of the protein
            custom_build_kwargs: Custom build parameters (optional)
            custom_sim_kwargs: Custom simulation parameters (optional)

        Returns:
            Simulation results dictionary
        """
        if not await self.is_ready():
            self.logger.error("MDAgent adapter not ready")
            return {}

        # Create simulation directory
        sim_id = f"mdagent_{protein_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        for pdb in pdb_path:
            self.logger.info(f'Running simulations at: {pdb}')

        # Prepare build kwargs
        build_kwargs = custom_build_kwargs or {
            'solvent': self.solvent_model,
            'protein': True,
            'out': 'system.pdb',
        }

        if 'amberhome' not in build_kwargs:
            build_kwargs['amberhome'] = self.amberhome

        # Prepare simulation kwargs
        sim_kwargs = custom_sim_kwargs or {
            'solvent': self.solvent_model,
            'equil_steps': self.equil_steps,
            'prod_steps': self.prod_steps,
        }

        sim_paths = [Path(root_path) / f'mdagent_{i}' for i in range(len(pdb_path))]
        for sim_path in sim_paths:
            sim_path.mkdir(parents=True, exist_ok=True)

        build_kwargs = [build_kwargs.copy() for _ in range(len(sim_paths))]
        sim_kwargs = [sim_kwargs.copy() for _ in range(len(sim_paths))]

        # Run MDAgent workflow
        self.logger.info(f"Starting MDAgent simulation: {sim_id}")

        results = await self.coordinator_handle.deploy_md(
            paths=sim_paths,
            initial_pdbs=pdb_path,
            build_kwargss=build_kwargs,
            sim_kwargss=sim_kwargs,
        )

        # Clean up agent/parsl
        await self.cleanup()

        self.logger.info(f"MDAgent simulation completed")
        self.logger.info(f'MD results: {results}')
        return results

    def _calculate_confidence(self, trajectory_analysis: Dict[str, Any]) -> float:
        """
        Calculate confidence score based on trajectory analysis quality.

        Args:
            trajectory_analysis: Trajectory analysis results

        Returns:
            Confidence score (0.0 to 1.0)
        """
        if trajectory_analysis.get('status') == 'placeholder':
            return 0.5

        confidence = 0.8  # Base confidence

        # Adjust based on RMSD stability
        rmsd_std = trajectory_analysis.get('rmsd', {}).get('std', 0.0)
        if rmsd_std < 0.1:
            confidence += 0.1  # Very stable
        elif rmsd_std > 0.3:
            confidence -= 0.1  # Less stable

        # Adjust based on trajectory length
        traj_info = trajectory_analysis.get('trajectory_info', {})
        n_frames = traj_info.get('n_frames', 0)
        if n_frames > 1000:
            confidence += 0.05  # Good sampling
        elif n_frames < 100:
            confidence -= 0.1  # Poor sampling

        # Clamp to [0, 1]
        return max(0.0, min(1.0, confidence))

    def get_capabilities(self) -> Dict[str, Any]:
        """Get MDAgent adapter capabilities."""
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
            # Release accelerators if using shared context
            await self._release_accelerators(self.agent_id)

            # Clean up Academy manager using mixin
            await self._cleanup_manager()

            self.builder_handle = None
            self.simulator_handle = None
            self.coordinator_handle = None

            self.logger.info("MDAgent adapter cleanup completed")

        except Exception as e:
            self.logger.error(f"MDAgent adapter cleanup failed: {e}")

    async def analyze_hypothesis(
        self,
        hypothesis: ProteinHypothesis,
        task_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze hypothesis by running MD simulation.

        Args:
            hypothesis: Protein hypothesis to analyze
            task_params: Task parameters including simulation paths

        Returns:
            Simulation analysis results
        """
        self.logger.info('We are about to run MD')

        # Extract shared context if present
        shared_context = task_params.pop('_shared_parsl_context', None)
        parsl = task_params.pop('parsl', None)

        # Ensure we're initialized with proper context
        if not await self.is_ready(parsl, shared_context):
            self.logger.error("MDAgent adapter not ready")
            return {}

        structures = [Path(p) for p in task_params['simulation_paths']]
        out = Path(task_params['root_output_path'])
        prod_steps = task_params.get('steps', self.prod_steps)
        solvent = task_params.get('solvent', 'explicit')

        sim_results = await self.run_md_simulation(
            root_path=out,
            pdb_path=structures,
            protein_name="unknown",
            custom_build_kwargs={'protein': True, 'solvent': solvent},
            custom_sim_kwargs={
                'equil_steps': self.equil_steps,
                'prod_steps': prod_steps,
                'n_equil_cycles': 2,
                'platform': 'OpenCL',
                'solvent': solvent
            },
        )

        return {'paths': sim_results}

    async def is_ready(
        self,
        parsl: Optional[Dict[str, Any]] = None,
        shared_context: Optional['SharedParslContext'] = None
    ) -> bool:
        """
        Check if adapter is ready, initializing if needed.

        Args:
            parsl: Optional parsl config overrides
            shared_context: Optional shared Parsl context from workflow

        Returns:
            True if adapter is ready
        """
        if not hasattr(self, 'initialized') or not self.initialized:
            await self.initialize(parsl, shared_context)
        return self.initialized

    def _get_tools_used(self) -> List[str]:
        """Get list of tools used."""
        return ['openmm', 'mdanalysis']
