"""
FEAgent (Free Energy) Adapter for StructBioReasoner

This module provides an adapter for MM-PBSA free energy calculations
using the SharedParslMixin to avoid nested Parsl configuration collisions.
"""

from dataclasses import asdict, dataclass, field
import dill as pickle
import asyncio
import logging
import MDAnalysis as mda
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, TYPE_CHECKING
from datetime import datetime

from ...utils.parsl_settings import LocalCPUSettings

# FEAgent imports
try:
    from academy.exchange import LocalExchangeFactory
    from academy.manager import Manager
    from concurrent.futures import ThreadPoolExecutor

    MDAGENT_AVAILABLE = True
except ImportError:
    MDAGENT_AVAILABLE = False
    logging.warning("FEAgent not available. Install from https://github.com/msinclair-py/MDAgent")

from ...data.protein_hypothesis import EnergeticAnalysis, ProteinHypothesis
from ..shared_parsl_mixin import SharedParslMixin

if TYPE_CHECKING:
    from ...workflows.advanced_workflow import SharedParslContext


@dataclass
class FEConfig:
    """Configuration for free energy calculations."""
    selections: List = field(default_factory=lambda: ['chain A', 'not chain A'])
    out: Path = Path('.')
    n_cpus: int = 200
    amberhome: str = ''


class FEAgent(SharedParslMixin):
    """
    Free energy calculation agent using MM-PBSA.

    This agent uses SharedParslMixin to support:
    1. Shared Parsl context from workflow (prevents nested config collisions)
    2. Standalone mode for testing (original behavior)
    """

    def __init__(
        self,
        agent_id: str,
        config: Dict[str, Any],
        parsl_config: Dict[str, Any]
    ):
        """
        Initialize FEAgent adapter.

        Args:
            agent_id: Unique identifier for this agent
            config: Configuration dictionary with FEAgent settings
            parsl_config: Parsl configuration dictionary
        """
        # Initialize the mixin
        super().__init__()

        self.agent_id = agent_id
        self.agent_type = "free_energy"
        self.specialization = "mmpbsa"

        # FEAgent configuration
        self.fe_config = config.get("free_energy", asdict(FEConfig()))

        if 'amberhome' not in self.fe_config:
            self.fe_config['amberhome'] = ''

        if not self.fe_config['amberhome']:
            self.fe_config['amberhome'] = config.get('mdagent', {}).get('amberhome', {})

        parsl_config['cores_per_worker'] = self.fe_config['cpus']
        parsl_config['max_workers_per_node'] = self.fe_config['cpus_per_node'] // self.fe_config['cpus']
        # Set thread limits to avoid numpy interference
        parsl_config['worker_init'] += '; export OPENBLAS_NUM_THREADS=1'
        parsl_config['worker_init'] += '; export MKL_NUM_THREADS=1'
        parsl_config['worker_init'] += '; export OMP_NUM_THREADS=1'

        self.parsl_config = parsl_config

        # FEAgent components (initialized in initialize())
        self.fe_handle = None
        self.coordinator_handle = None

        # State tracking
        self.active_calculations = {}
        self.completed_calculations = {}

        self.logger = logging.getLogger(__name__)
        self.logger.info(f"FEAgent initialized")

    async def initialize(
        self,
        parsl: Optional[Dict[str, Any]] = None,
        shared_context: Optional['SharedParslContext'] = None
    ) -> bool:
        """
        Initialize FEAgent components.

        Args:
            parsl: Optional parsl config overrides (for backwards compatibility)
            shared_context: Optional shared Parsl context from workflow

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            from MDAgent.core.mmpbsa_agent import FECoordinator

            # Initialize Academy manager using mixin
            self.manager = await self._initialize_manager()

            # Prepare data dict for mixin
            data = {}
            if parsl is not None:
                data['parsl'] = parsl
            if shared_context is not None:
                data['_shared_parsl_context'] = shared_context

            # Get Parsl settings using the mixin (key fix!)
            parsl_settings = await self._get_parsl_settings(
                data=data,
                shared_context=shared_context,
                settings_class=LocalCPUSettings,
                parsl_config=self.parsl_config,
                agent_id=self.agent_id,
            )

            self.logger.info(f'Parsl settings obtained (shared: {self.is_using_shared_parsl})')
            self.logger.info('Attempting to launch FEAgent')

            self.coordinator_handle = await self.manager.launch(
                FECoordinator,
                args=(parsl_settings,)
            )

            self.initialized = True
            self.logger.info("FEAgent components initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize FEAgent: {e}")
            self.initialized = False

            # Clean up manager if it was created
            await self._cleanup_manager()
            return False

    async def run_calculations(
        self,
        sim_path: Union[Path, List[Path]],
        protein_name: str = "unknown",
        custom_sim_kwargs: Optional[Dict[str, Any]] = None,
        parsl: Optional[Dict[str, Any]] = None,
        shared_context: Optional['SharedParslContext'] = None
    ) -> Dict[str, Any]:
        """
        Run MM-PBSA free energy calculations.

        Args:
            sim_path: Path(s) to simulation directories
            protein_name: Name of the protein
            custom_sim_kwargs: Custom simulation parameters (optional)
            parsl: Optional parsl config overrides
            shared_context: Optional shared Parsl context

        Returns:
            Free energy calculation results
        """
        if not await self.is_ready(parsl, shared_context):
            self.logger.error("FEAgent adapter not ready")
            return {}

        try:
            # Find directories with completed simulations
            if isinstance(sim_path, list):
                paths = []
                for path in sim_path:
                    paths += [p.parent for p in path.glob('*/prod.dcd')]
            else:
                paths = [path.parent for path in sim_path.glob('*/prod.dcd')]

            # Build configuration for each system
            fe_kwargss = await self._unpack_dataclass_config(paths)

            results = await self.coordinator_handle.deploy(
                paths=paths,
                fe_kwargss=fe_kwargss,
            )

            analysis = {}
            for result in results:
                if result['success']:
                    path = str(result['path'])
                    mean, std = result['fe']

                    analysis[path] = {
                        'mean': mean,
                        'std': std,
                        'unit': 'kcal/mol'
                    }

            await self.cleanup()
            return analysis

        except Exception as e:
            import traceback
            self.logger.error(f"FEAgent simulation failed: {e}")
            self.logger.error(traceback.format_exc())
            return {}

    async def _unpack_dataclass_config(
        self,
        paths: List[Path]
    ) -> List[Dict[str, Any]]:
        """Build configuration for each simulation path."""
        fe_kwargss = []
        for path in paths:
            dict_copy = self.fe_config.copy()
            u = mda.Universe(str(path / 'system.prmtop'), str(path / 'prod.dcd'))

            protein = u.select_atoms('protein').residues.resids
            oxts = u.select_atoms('name OXT').residues.resids

            last_protein_resid = oxts[-2]
            sel1 = [resid for resid in protein if resid <= last_protein_resid]
            sel2 = [resid for resid in protein if resid > last_protein_resid]

            s1 = self.format_for_cpptraj(sel1)
            s2 = self.format_for_cpptraj(sel2)

            dict_copy['selections'] = [s1, s2]
            dict_copy['out'] = str(path)
            dict_copy['n_cpus'] = self.fe_config['cpus']

            fe_kwargss.append(dict_copy)

        return fe_kwargss

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

    def format_for_cpptraj(self, resids: List[int]) -> str:
        """Format residue IDs for cpptraj selection."""
        string = ':'
        cur = resids[0] - 1
        start = resids[0]
        end = None

        for resid in resids:
            if resid - cur > 1:
                end = cur
                string += f'{start}-{end},'
                start = resid

            cur = resid

        end = resids[-1]
        string += f'{start}-{end}'

        return string

    def _create_placeholder_analysis(self) -> Dict[str, Any]:
        """Create placeholder analysis when detailed analysis is not available."""
        return {
            'status': 'placeholder',
            'message': 'Detailed trajectory analysis not available (MDAgent not installed)',
            'free_energy': {'': {'mean': 0.0, 'std': 0.0, 'unit': 'kcal/mol'}},
        }

    def get_capabilities(self) -> Dict[str, Any]:
        """Get FEAgent adapter capabilities."""
        return {
            "agent_type": self.agent_type,
            "specialization": self.specialization,
            "mdagent_available": MDAGENT_AVAILABLE,
            "capabilities": ["mmpbsa"],
            "integration_features": [
                "hypothesis_generation",
                "result_analysis",
                "trajectory_processing"
            ]
        }

    async def cleanup(self) -> None:
        """Clean up FEAgent resources."""
        try:
            # Release accelerators if using shared context
            await self._release_accelerators(self.agent_id)

            # Clean up Academy manager using mixin
            await self._cleanup_manager()

            self.fe_handle = None
            self.coordinator_handle = None

            self.logger.info("FEAgent adapter cleanup completed")

        except Exception as e:
            self.logger.error(f"FEAgent adapter cleanup failed: {e}")

    async def analyze_hypothesis(
        self,
        hypothesis: ProteinHypothesis,
        task_params: Dict[str, Any]
    ) -> EnergeticAnalysis:
        """
        Analyze hypothesis by calculating binding free energy.

        Args:
            hypothesis: Input protein hypothesis
            task_params: Task parameters including simulation paths

        Returns:
            Energetic analysis results
        """
        paths = task_params['simulation_paths']

        # Extract shared context if present
        shared_context = task_params.pop('_shared_parsl_context', None)
        parsl = task_params.pop('parsl', None)

        energies = await self.run_calculations(
            sim_path=paths,
            protein_name="unknown",
            parsl=parsl,
            shared_context=shared_context
        )

        analysis = EnergeticAnalysis(
            protein_id='',
            binding_affinities=energies,
            force_field='amber19',
        )

        analysis.confidence_score = self._calculate_confidence(analysis)
        analysis.tools_used = self._get_tools_used()

        return analysis

    def _calculate_confidence(self, analysis: EnergeticAnalysis) -> float:
        """Calculate confidence score for analysis."""
        return 0.75

    def _get_tools_used(self) -> List[str]:
        """Get list of tools used."""
        return ['cpptraj', 'ambertools']
