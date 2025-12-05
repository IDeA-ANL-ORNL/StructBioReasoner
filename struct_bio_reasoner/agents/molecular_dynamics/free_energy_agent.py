"""
FEAgent Adapter for StructBioReasoner

This module provides an adapter that wraps FEAgent components (Builder, MDSimulator, MDCoordinator)
to work seamlessly within StructBioReasoner's agent framework.

The adapter translates between:
- Academy's @action pattern → StructBioReasoner's async methods
- FEAgent's Handle communication → Direct method calls  
- MD simulation results → ProteinHypothesis objects
"""

from dataclasses import asdict, dataclass
import dill as pickle
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

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

from ...data.protein_hypothesis import SimAnalysis, ProteinHypothesis

@dataclass
class FEConfig:
    selections: list=field(default_factory=lambda: ['chain A', 'not chain A'])
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
                 config: Dict[str, Any]):
        """
        Initialize FEAgent adapter.
        
        Args:
            config: Configuration dictionary with FEAgent settings
        """
        super().__init__(config)
        
        self.agent_id = agent_id
        self.agent_type = "free_energy"
        self.specialization = "mmpbsa"
        
        # FEAgent configuration
        self.fe_config = config.get("free_energy", FEConfig())
        
        # FEAgent components (initialized in initialize())
        self.manager = None
        self.fe_handle = None
        
        # State tracking
        self.active_calculations = {}
        self.completed_calculations = {}
        
        self.logger.info(f"FEAgent initialized")

    def __del__(self):
        """Destructor to ensure manager is cleaned up."""
        # Note: This is a safety net. Proper cleanup should use async cleanup() method
        if hasattr(self, 'manager') and self.manager is not None:
            self.logger.warning("FEAgent deleted without proper cleanup - manager still active")
            # We can't call async cleanup from __del__, so just log a warning

    async def initialize(self) -> bool:
        """
        Initialize FEAgent components.

        Returns:
            True if initialization successful, False otherwise
        """
        if not MDAGENT_AVAILABLE:
            self.logger.error("FEAgent not available - cannot initialize adapter")
            self.initialized = False
            return False

        try:
            # Import FEAgent components
            # Note: FEAgent should be installed and available in Python path
            # The agents are defined in agents.py at the root of FEAgent repo
            try:
                # Try importing from mdagent package (if installed as package)
                from MDAgent.core.mmpbsa_agent import FreeEnergy, FECoordinator
            except ImportError:
                try:
                    # Try importing from agents module (if MDAgent is in PYTHONPATH)
                    from agents import FreeEnergy, FECoordinator
                except ImportError as e:
                    self.logger.error(f"Cannot import MDAgent components: {e}")
                    self.logger.info("Make sure MDAgent is installed and in PYTHONPATH")
                    self.logger.info("Install from: https://github.com/msinclair-py/MDAgent")
                    self.initialized = False
                    return False

            # Create Academy manager using async context manager pattern
            # This ensures the exchange client is properly initialized
            self.manager = await Manager.from_exchange_factory(
                factory=LocalExchangeFactory(),
                executors=ThreadPoolExecutor(),
            )

            # Enter the manager context to initialize exchange client
            await self.manager.__aenter__()

            # Launch FEAgent components
            self.fe_handle = await self.manager.launch(FreeEnergy)
            self.coordinator_handle = await self.manager.launch(
                FECoordinator,
                args=(self.fe_handle, self.parsl_config)
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
    
    async def generate_hypotheses(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate MD-based hypotheses using FEAgent backend.
        
        Args:
            context: Analysis context containing protein information
            
        Returns:
            List of hypothesis dictionaries
        """
        if not self.is_ready():
            self.logger.error("FEAgent adapter not ready")
            return []
        
        hypotheses = []
        
        try:
            # Extract context
            target_protein = context.get('target_protein', 'unknown')
            sim_path = context.get('sim_root_path')
            
            if not pdb_path:
                self.logger.error("No PDB path provided in context")
                return []
            
            # Run MD simulation using FEAgent
            self.logger.info("Running {self.free_energy.calculator.__name__}")
            calculation_result = await self.run_calculations(
                sim_path=Path(sim_path),
                protein_name=target_protein
            )
            
            if calculation_result:
                # Convert to hypothesis format
                hypothesis = {
                    'title': f'FEAgent Simulation Analysis for {target_protein}',
                    'strategy': 'free_energy_calculation',
                    'approach': f'{self.free_energy.calculator.__name__} method',
                    'description': f'FEAgent',
                    'confidence': calculation_result.get('confidence', 0.75),
                    'source': 'FEAgent',
                    'calculation_results': calculation_result,
                    'execution_plan': {
                        'solvent_model': self.solvent_model,
                        'equilibration_steps': self.equil_steps,
                        'production_steps': self.prod_steps,
                        'force_field': self.force_field
                    }
                }
                hypotheses.append(hypothesis)
            
            self.logger.info(f"Generated {len(hypotheses)} FEAgent-based hypotheses")
            
        except Exception as e:
            self.logger.error(f"Error generating FEAgent hypotheses: {e}")
        
        return hypotheses
    
    async def run_calculations(self,
                               sim_path: Union[Path, list[Path]],
                               protein_name: str = "unknown",
                               custom_sim_kwargs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        if not self.is_ready():
            self.logger.error("FEAgent adapter not ready")
            return {}
        
        try:
            # Run FEAgent workflow
            self.logger.info(f"Starting FEAgent simulation: {sim_id}")
            
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
                path=paths,
                fe_kwargss=fe_kwargss,
            ) # list of dicts with `path`, `success` and `fe`
            
            # Store results
            analysis = {
                'results': results,
                'timestamp': datetime.now().isoformat()
            }
            
            return analysis

        except Exception as e:
            self.logger.error(f"FEAgent simulation failed: {e}")
            return {}

    async def _unpack_dataclass_config(self,
                                       paths: list[Path]) -> list[dict[str, Any]]:
        """"""
        dict_config = asdict(self.fe_config)
        sels = dict_config['selections']
        fe_kwargss = []
        for path in paths:
            dict_copy = dict_config.copy()
            u = mda.Universe(str(path / 'system.prmtop'), str(path / 'prod.dcd'))
            sel1 = u.select_atoms(sels[0])
            sel2 = u.select_atoms(sels[1])

            s1 = self.format_for_cpptraj(sel1.residues.resids)
            s2 = self.format_for_cpptraj(sel2.residues.resids)

            dict_copy['selections'] = [s1, s2]
            fe_kwargss.append(dict_copy)

        return fe_kwargss

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
            'free_energy': {0: {'path': None, 'mean': 0.0, 'std': 0.0, 'unit': 'kcal/mol'}},
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
                    self.builder_handle = None
                    self.simulator_handle = None
                    self.coordinator_handle = None

            # Call parent cleanup
            await super().cleanup()

            self.logger.info("FEAgent adapter cleanup completed")

        except Exception as e:
            self.logger.error(f"FEAgent adapter cleanup failed: {e}")

    async def analyze_hypothesis(self,
                                 hypothesis: ProteinHypothesis,
                                 task_params: dict[str, Any]) -> SimAnalysis:
        paths = task_params['simulation_paths']
        energies = await self.run_calculations( 
                               sim_path = paths,
                               protein_name = "unknown",
                            )

        analysis = SimAnalysis(
            protein_id='',
            simulation_time_in_ns=sim_results['simulation_time'],
            rmsd=sim_results['rmsd'],
            rmsf=sim_results['rmsf']
        )

        analysis.confidence_score = self._calculate_confidence(analysis)
        analysis.tools_used = self._get_tools_used()

        return analysis

    def _calculate_confidence(self,
                              analysis: SimAnalysis) -> float:
        # TODO: compute this based on RMSD/RMSF threshholds
        return 0.75

    def _get_tools_used(self) -> list[str]:
        return ['cpptraj', 'ambertools']
