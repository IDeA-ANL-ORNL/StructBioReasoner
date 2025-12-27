"""
FEAgent Adapter for StructBioReasoner

This module provides an adapter that wraps FEAgent components (Builder, MDSimulator, MDCoordinator)
to work seamlessly within StructBioReasoner's agent framework.

The adapter translates between:
- Academy's @action pattern → StructBioReasoner's async methods
- FEAgent's Handle communication → Direct method calls  
- MD simulation results → ProteinHypothesis objects
"""

from dataclasses import asdict, dataclass, field
import dill as pickle
import asyncio
import logging
import MDAnalysis as mda
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from ...utils.parsl_settings import LocalCPUSettings

# FEAgent imports (from https://github.com/msinclair-py/MDAgent)
try:
    from academy.exchange import LocalExchangeFactory
    from academy.manager import Manager
    from concurrent.futures import ThreadPoolExecutor
    
    # Import FEAgent components
    # Note: These would need to be installed from the FEAgent repository
    # For now, we'll create a compatibility layer
    MDAGENT_AVAILABLE = True
except ImportError:
    MDAGENT_AVAILABLE = False
    logging.warning("FEAgent not available. Install from https://github.com/msinclair-py/MDAgent")

from ...data.protein_hypothesis import EnergeticAnalysis, ProteinHypothesis

@dataclass
class FEConfig:
    selections: list=field(default_factory=lambda: ['chain A', 'not chain A'])
    out: Path=Path('.')
    n_cpus: int=200,
    amberhome: str=''

class FEAgent:
    """
    Adapter that wraps FEAgent components to work within StructBioReasoner.
    
    This adapter enables StructBioReasoner to use FEAgent's proven MD simulation
    workflow while maintaining compatibility with the hypothesis-centric design.
    
    Key Features:
    - Wraps FEAgent's Builder, MDSimulator, and MDCoordinator
    - Converts MD results to ProteinHypothesis objects
    - Supports both implicit and explicit solvent models
    - Integrates with StructBioReasoner's role-based orchestration
    """
    
    def __init__(self, 
                 agent_id: str,
                 config: Dict[str, Any],
                 parsl_config: dict[str, Any]):
        """
        Initialize FEAgent adapter.
        
        Args:
            config: Configuration dictionary with FEAgent settings
        """
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
        # set these to disallow numpy from screwing up our calculations
        parsl_config['worker_init'] += '; export OPENBLAS_NUM_THREADS=1'
        parsl_config['worker_init'] += '; export MKL_NUM_THREADS=1'
        parsl_config['worker_init'] += '; export OMP_NUM_THREADS=1'

        self.parsl_config = parsl_config
        
        # FEAgent components (initialized in initialize())
        self.manager = None
        self.fe_handle = None
        self.coordinator_handle = None
        
        # State tracking
        self.active_calculations = {}
        self.completed_calculations = {}
        
        self.logger = logging.getLogger(__name__)
        
        self.logger.info(f"FEAgent initialized")

    async def initialize(self,
                         parsl: Optional[dict] = None) -> bool:
        """
        Initialize FEAgent components.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Import FEAgent components
            # Note: FEAgent should be installed and available in Python path
            # The agents are defined in agents.py at the root of FEAgent repo
            # Try importing from mdagent package (if installed as package)
            from MDAgent.core.mmpbsa_agent import FECoordinator

            # Create Academy manager using async context manager pattern
            # This ensures the exchange client is properly initialized
            self.manager = await Manager.from_exchange_factory(
                factory=LocalExchangeFactory(),
                executors=ThreadPoolExecutor(),
            )

            # Enter the manager context to initialize exchange client
            await self.manager.__aenter__()

            parsl_config = self.parsl_config
            if parsl is not None:
                for k, v in parsl.values():
                    parsl_config[k] = v

            # worker_init, nodes, max_workers_per_node, cores_per_worker
            parsl_settings = LocalCPUSettings(**parsl_config).config_factory(Path.cwd())

            self.logger.info('Attempting to launch FEAgent')
            self.coordinator_handle = await self.manager.launch(
                FECoordinator,
                args=(parsl_settings)
            )

            self.initialized = True
            self.logger.info("FEAgent components initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize FEAgent: {e}")
            self.initialized = False
            # Clean up manager if it was created
            if self.manager:
                try:
                    await self.manager.__aexit__(None, None, None)
                except:
                    pass
                self.manager = None
            return False
    
    async def run_calculations(self,
                               sim_path: Union[Path, list[Path]],
                               protein_name: str = "unknown",
                               custom_sim_kwargs: Optional[Dict[str, Any]] = None,
                               parsl: Optional[dict] = None) -> Dict[str, Any]:
        """
        Run complete MD simulation using FEAgent coordinator.

        Args:
            pdb_path: Path to input PDB file or list of PDB files
            protein_name: Name of the protein
            custom_build_kwargs: Custom build parameters (optional)
            custom_sim_kwargs: Custom simulation parameters (optional)

        Returns:
            Simulation results dictionary
        """
        if not await self.is_ready(parsl):
            self.logger.error("FEAgent adapter not ready")
            return {}
        
        try:
            # This looks weird but ensures we only run dirs with simulations
            # in them. Skips over failed runs, or extraneous dirs
            if isinstance(sim_path, list):
                paths = []
                for path in sim_path:
                    paths += [p.parent for p in path.glob('*/prod.dcd')]
            else:
                paths = [path.parent for path in sim_path.glob('*/prod.dcd')]

            # Interpret config for each system
            fe_kwargss = await self._unpack_dataclass_config(paths)

            results = await self.coordinator_handle.deploy(
                paths=paths,
                fe_kwargss=fe_kwargss,
            ) # list of dicts with `path`, `success` and `fe`

            analysis = {}
            for result in results:
                if result['fe'] is None:
                    mean, std = None, None
                else:
                    mean, std = result['fe']

                result['path']: {'mean': mean,
                                 'std': std,
                                 'unit': 'kcal/mol'} 
            
            return analysis

        except Exception as e:
            import traceback
            self.logger.error(f"FEAgent simulation failed: {e}")
            self.logger.error(traceback.format_exc())
            return {}

    async def _unpack_dataclass_config(self,
                                       paths: list[Path]) -> list[dict[str, Any]]:
        """"""
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

    async def is_ready(self,
                       parsl: Optional[dict] = None) -> bool:
        if not hasattr(self, 'initialized'):
            await self.initialize(parsl)
        return self.initialized

    def format_for_cpptraj(self,
                           resids: list[int]) -> str:
        """"""
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
        """
        Create placeholder analysis when detailed analysis is not available.

        Returns:
            Placeholder analysis dictionary
        """
        return {
            'status': 'placeholder',
            'message': 'Detailed trajectory analysis not available (MDAgent not installed)',
            'free_energy': {'': {'mean': 0.0, 'std': 0.0, 'unit': 'kcal/mol'}},
        }

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

        # Clamp to [0, 1]
        return max(0.0, min(1.0, confidence))
    
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get FEAgent adapter capabilities.
        
        Returns:
            Dictionary describing adapter capabilities
        """
        return {
            "agent_type": self.agent_type,
            "specialization": self.specialization,
            "mdagent_available": MDAGENT_AVAILABLE,
            "capabilities": [
                "mmpbsa"
            ],
            "integration_features": [
                "hypothesis_generation",
                "result_analysis",
                "trajectory_processing"
            ]
        }
    
    async def cleanup(self) -> None:
        """Clean up FEAgent resources."""
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
                    self.fe_handle = None
                    delattr(self, 'initialized')

            # Call parent cleanup
            await super().cleanup()

            self.logger.info("FEAgent adapter cleanup completed")

        except Exception as e:
            self.logger.error(f"FEAgent adapter cleanup failed: {e}")

    async def analyze_hypothesis(self,
                                 hypothesis: ProteinHypothesis,
                                 task_params: dict[str, Any]) -> EnergeticAnalysis:
        paths = task_params['simulation_paths']
        if 'parsl' in task_params:
            parsl = task_params.pop('parsl')
        else:
            parsl = None

        energies = await self.run_calculations( 
            sim_path = paths,
            protein_name = "unknown",
            parsl = parsl
        )

        analysis = EnergeticAnalysis(
            protein_id='',
            binding_affinities=energies,
            force_field='amber19',
        )
    
        analysis.confidence_score = self._calculate_confidence(analysis)
        analysis.tools_used = self._get_tools_used()

        return analysis

    def _calculate_confidence(self,
                              analysis: EnergeticAnalysis) -> float:
        # TODO: compute this based on RMSD/RMSF threshholds
        return 0.75

    def _get_tools_used(self) -> list[str]:
        return ['cpptraj', 'ambertools']
