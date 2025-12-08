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
from ...utils.parsl_settings import AuroraSettings, LocalSettings
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import numpy as np
from datetime import datetime

# MDAgent imports (from https://github.com/msinclair-py/MDAgent)
try:
    from academy.exchange import LocalExchangeFactory
    from academy.manager import Manager
    from concurrent.futures import ThreadPoolExecutor
    
    # Import MDAgent components
    # Note: These would need to be installed from the MDAgent repository
    # For now, we'll create a compatibility layer
    MDAGENT_AVAILABLE = True
except ImportError:
    MDAGENT_AVAILABLE = False
    logging.warning("MDAgent not available. Install from https://github.com/msinclair-py/MDAgent")

from ...core.base_agent import BaseAgent
from ...data.protein_hypothesis import SimAnalysis, ProteinHypothesis


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
                 config: Dict[str, Any],
                 parsl_config: Dict[str, Any]):
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
        
        # MDAgent configuration
        self.mdagent_config = self.config.get("mdagent", {})
        self.solvent_model = self.mdagent_config.get("solvent_model", "explicit")
        self.force_field = self.mdagent_config.get("force_field", "amber14")
        self.water_model = self.mdagent_config.get("water_model", "tip3p")
        self.amberhome = self.mdagent_config.get('amberhome', None)
        
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
        
        # State tracking
        self.active_simulations = {}
        self.completed_simulations = {}

        self.logger.info(f"MDAgentAdapter initialized with {self.solvent_model} solvent")

    def __del__(self):
        """Destructor to ensure manager is cleaned up."""
        # Note: This is a safety net. Proper cleanup should use async cleanup() method
        if hasattr(self, 'manager') and self.manager is not None:
            self.logger.warning("MDAgentAdapter deleted without proper cleanup - manager still active")
            # We can't call async cleanup from __del__, so just log a warning

    async def initialize(self) -> bool:
        """
        Initialize MDAgent components.

        Returns:
            True if initialization successful, False otherwise
        """
        if not MDAGENT_AVAILABLE:
            self.logger.error("MDAgent not available - cannot initialize adapter")
            self.initialized = False
            return False

        try:
            self.logger.info('trying to import MDAgent package')
            # Import MDAgent components
            # Note: MDAgent should be installed and available in Python path
            # The agents are defined in agents.py at the root of MDAgent repo
            try:
                # Try importing from mdagent package (if installed as package)
                from MDAgent.core.agents_no_FE import Builder, MDSimulator, MDCoordinator
                from molecular_simulations.build import ImplicitSolvent, ExplicitSolvent
                from molecular_simulations.simulate import ImplicitSimulator, Simulator
            except ImportError as e:
                self.logger.error(f"Cannot import MDAgent components: {e}")
                self.logger.info("Make sure MDAgent is installed and in PYTHONPATH")
                self.logger.info("Install from: https://github.com/msinclair-py/MDAgent")
                self.initialized = False
                return False

            self.logger.info('survived import')
            # Create Academy manager using async context manager pattern
            # This ensures the exchange client is properly initialized
            self.manager = await Manager.from_exchange_factory(
                factory=LocalExchangeFactory(),
                executors=ThreadPoolExecutor(),
            )

            # Enter the manager context to initialize exchange client
            await self.manager.__aenter__()

            self.logger.info('launching handles')

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
            self.parsl_settings = LocalSettings(**self.parsl_config).config_factory(Path.cwd())

            self.logger.info('launching coordinator')
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
            if self.manager:
                try:
                    await self.manager.__aexit__(None, None, None)
                    self.logger.info('Academy manager context exited successfully')
                except Exception as e:
                    self.logger.warning(f'Error exiting manager context: {e}')
                finally: 
                    self.manager = None

            return False
    
    async def generate_hypotheses(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate MD-based hypotheses using MDAgent backend.
        
        Args:
            context: Analysis context containing protein information
            
        Returns:
            List of hypothesis dictionaries
        """
        if not self.initialized:
            self.logger.error("MDAgent adapter not ready")
            return []
        
        hypotheses = []
        
        try:
            # Extract context
            protein_sequence = context.get('protein_sequence', '')
            target_protein = context.get('target_protein', 'unknown')
            pdb_path = context.get('pdb_path')
            
            if not pdb_path:
                self.logger.error("No PDB path provided in context")
                return []
            
            # Run MD simulation using MDAgent
            self.logger.info("RUNNNNINNNNG MDDDD")
            simulation_result = await self.run_md_simulation(
                pdb_path=Path(pdb_path),
                protein_name=target_protein
            )
            
            if simulation_result:
                # Convert to hypothesis format
                hypothesis = {
                    'title': f'MDAgent Simulation Analysis for {target_protein}',
                    'strategy': 'mdagent_simulation',
                    'approach': f'{self.solvent_model}_solvent_md',
                    'description': f'MD simulation using MDAgent with {self.solvent_model} solvent',
                    'confidence': simulation_result.get('confidence', 0.75),
                    'source': 'MDAgentAdapter',
                    'simulation_results': simulation_result,
                    'execution_plan': {
                        'solvent_model': self.solvent_model,
                        'equilibration_steps': self.equil_steps,
                        'production_steps': self.prod_steps,
                        'force_field': self.force_field
                    }
                }
                hypotheses.append(hypothesis)
            
            self.logger.info(f"Generated {len(hypotheses)} MDAgent-based hypotheses")
            
        except Exception as e:
            self.logger.error(f"Error generating MDAgent hypotheses: {e}")
        
        return hypotheses
    
    async def run_md_simulation(self,
                                root_path: Path,
                               pdb_path: Union[Path, List[Path]],
                               protein_name: str = "unknown",
                               custom_build_kwargs: Optional[Dict[str, Any]] = None,
                               custom_sim_kwargs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        if not await self.is_ready():
            self.logger.error("MDAgent adapter not ready")
            return {}
        
        try:
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

            self.logger.info(f'{sim_kwargs=}')
            
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
           
            for sim_id, result in enumerate(results):
                # Store results
                self.completed_simulations[sim_id] = {
                    'results': result,
                    'build_kwargs': build_kwargs,
                    'sim_kwargs': sim_kwargs,
                    'timestamp': datetime.now().isoformat()
                }
            
            self.logger.info('Analyzing simulation results')
            # Analyze results and create structured output
            analysis = await self._analyze_mdagent_results(results)
            
            # Clean up agent/parsl
            await self.cleanup()
            
            self.logger.info(f"MDAgent simulation completed")

            return analysis

        except Exception as e:
            self.logger.error(f"MDAgent simulation failed: {e}")
            return {}
    
    async def _analyze_mdagent_results(self, results: Dict[int, Any]) -> Dict[str, Any]:
        """
        Analyze MDAgent simulation results.

        Args:
            sim_id: Simulation identifier
            results: Raw results from MDAgent

        Returns:
            Structured analysis results
        """
        analyses = {sim_id: {} for sim_id in range(len(results))}
        for sim_id, result in enumerate(results):
            build_path = result.get('build')
            sim_status = result.get('sim')

            # Basic analysis structure
            analysis = {
                'simulation_id': sim_id,
                'build_path': str(build_path) if build_path else None,
                'simulation_status': sim_status,
                'solvent_model': self.solvent_model,
                'success': 'unknown',
                'confidence': 0.8 if sim_status == 'success' else 0.0,
                'timestamp': datetime.now().isoformat()
            }

            # Perform trajectory analysis if simulation succeeded
            if sim_status == 'success' and build_path:
                try:
                    self.logger.info(f'Analyzing {build_path}!')
                    trajectory_analysis = await self._analyze_trajectory(build_path)
                    analysis['trajectory_analysis'] = trajectory_analysis


                    # Update confidence based on trajectory quality
                    if trajectory_analysis:
                        analysis['confidence'] = self._calculate_confidence(trajectory_analysis)

                    analysis['success'] = True

                except Exception as e:
                    self.logger.warning(f"Trajectory analysis failed: {e}")
                    analysis['trajectory_analysis_error'] = str(e)

                analyses[sim_id] = analysis

        return analyses

    async def _analyze_trajectory(self, build_path: Path) -> Optional[Dict[str, Any]]:
        """
        Analyze MD trajectory to extract structural and dynamic properties.

        Args:
            build_path: Path to simulation directory

        Returns:
            Trajectory analysis results or None if failed
        """
        try:
            # Try to import MDTraj for trajectory analysis
            try:
                import mdtraj as md
                import numpy as np
            except ImportError:
                self.logger.warning("MDTraj not available - skipping detailed trajectory analysis")
                return self._create_placeholder_analysis()

            # Look for trajectory files
            build_path = Path(build_path)
            trajectory = build_path / self.mdagent_config['output_dcd']

            if not trajectory.exists():
                self.logger.warning("No trajectory files found")
                return self._create_placeholder_analysis()

            # Load topology
            pdb_file = build_path / self.mdagent_config['topology']
            if not pdb_file.exists():
                self.logger.warning("No PDB topology file found")
                return self._create_placeholder_analysis()

            # Load trajectory
            traj = md.load(str(trajectory), top=str(pdb_file))

            self.logger.info('Loaded trajectory')

            # Compute structural metrics
            analysis = {}

            # RMSD (Root Mean Square Deviation)
            rmsd = md.rmsd(traj, traj[0])
            analysis['rmsd'] = {
                'mean': float(np.mean(rmsd)),
                'std': float(np.std(rmsd)),
                'min': float(np.min(rmsd)),
                'max': float(np.max(rmsd)),
                'unit': 'nm'
            }

            # RMSF (Root Mean Square Fluctuation)
            rmsf = md.rmsf(traj, traj[0])
            analysis['rmsf'] = {
                'mean': float(np.mean(rmsf)),
                'std': float(np.std(rmsf)),
                'per_residue': rmsf.tolist(),
                'unit': 'nm'
            }

            # Radius of gyration
            rg = md.compute_rg(traj)
            analysis['radius_of_gyration'] = {
                'mean': float(np.mean(rg)),
                'std': float(np.std(rg)),
                'min': float(np.min(rg)),
                'max': float(np.max(rg)),
                'unit': 'nm'
            }

            # Secondary structure (DSSP)
            try:
                dssp = md.compute_dssp(traj)
                # Count secondary structure elements
                helix_content = np.mean(np.isin(dssp, ['H', 'G', 'I']))
                sheet_content = np.mean(np.isin(dssp, ['E', 'B']))
                coil_content = np.mean(np.isin(dssp, ['C', 'T', 'S']))

                analysis['secondary_structure'] = {
                    'helix_content': float(helix_content * 100),
                    'sheet_content': float(sheet_content * 100),
                    'coil_content': float(coil_content * 100),
                    'unit': 'percent'
                }
            except Exception as e:
                self.logger.warning(f"DSSP calculation failed: {e}")

            # Identify flexible residues (high RMSF)
            rmsf_threshold = np.mean(rmsf) + np.std(rmsf)
            flexible_residues = np.where(rmsf > rmsf_threshold)[0].tolist()

            # Identify stable residues (low RMSF)
            stable_threshold = np.mean(rmsf) - 0.5 * np.std(rmsf)
            stable_residues = np.where(rmsf < stable_threshold)[0].tolist()

            analysis['flexibility_analysis'] = {
                'flexible_residues': flexible_residues[:20],  # Top 20
                'stable_residues': stable_residues[:20],  # Top 20
                'rmsf_threshold': float(rmsf_threshold),
                'stable_threshold': float(stable_threshold)
            }

            # Trajectory quality metrics
            analysis['trajectory_info'] = {
                'n_frames': int(traj.n_frames),
                'n_atoms': int(traj.n_atoms),
                'n_residues': int(traj.n_residues),
                'time_ns': float(traj.time[-1] / 1000) if len(traj.time) > 0 else 0.0
            }

            return analysis

        except Exception as e:
            self.logger.error(f"Trajectory analysis failed: {e}")
            return None

    def _create_placeholder_analysis(self) -> Dict[str, Any]:
        """
        Create placeholder analysis when detailed analysis is not available.

        Returns:
            Placeholder analysis dictionary
        """
        return {
            'status': 'placeholder',
            'message': 'Detailed trajectory analysis not available (MDTraj not installed)',
            'rmsd': {'mean': 0.0, 'std': 0.0, 'unit': 'nm'},
            'rmsf': {'mean': 0.0, 'std': 0.0, 'unit': 'nm'},
            'radius_of_gyration': {'mean': 0.0, 'std': 0.0, 'unit': 'nm'}
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

    async def analyze_hypothesis(self,
                                 hypothesis: ProteinHypothesis,
                                 task_params: dict[str, Any]) -> SimAnalysis:
        #### Rewrite this according to how binder analysis adds to hypothesis
        self.logger.info('We are about to run MD')
        structures = task_params['simulation_paths']
        out = task_params['root_output_path']
        prod_steps = task_params.get('steps', self.prod_steps)

        # TODO: get kwargs for build/sim from task_params
        sim_results = await self.run_md_simulation( 
            root_path=out,
            pdb_path=structures,
            protein_name = "unknown",
            custom_build_kwargs = {'protein': True,},
            custom_sim_kwargs = {'equil_steps': self.equil_steps,
                                 'prod_steps': prod_steps,
                                 'n_equil_cycles': 2,
                                 'platform': 'OpenCL'},
        )
        
        summary_stats = self.summarize(sim_results)
        
        analysis = SimAnalysis(
            protein_id='',
            simulation_time_in_ns=self.prod_steps * 4 / 1000000,
            rmsd=summary_stats['rmsd'],
            rmsf=summary_stats['rmsf'],
            rog=summary_stats['rog']
        )

        analysis.confidence_score = self._calculate_confidence(analysis)
        analysis.tools_used = self._get_tools_used()

        return analysis

    async def is_ready(self) -> bool:
        if not hasattr(self, 'initialized'):
            await self.initialize()
        return self.initialized

    def summarize(self,
                  results: dict[str, Any]) -> dict[str, Any]:
        N = len(results)
        rmsds = np.zeros((N, 3))
        rmsfs = np.zeros((N, 3))
        rogs = np.zeros((N, 3))

        for i, v in results.items():
            analysis = v['trajectory_analysis']
            n_frames = analysis['trajectory_info']['n_frames']
            rmsds[i, 0] = analysis['rmsd']['mean']
            rmsds[i, 1] = analysis['rmsd']['std']
            rmsds[i, 2] = n_frames

            rmsfs[i, 0] = analysis['rmsf']['mean']
            rmsfs[i, 1] = analysis['rmsf']['std']
            rmsfs[i, 2] = n_frames
            
            rogs[i, 0] = analysis['radius_of_gyration']['mean']
            rogs[i, 1] = analysis['radius_of_gyration']['std']
            rogs[i, 2] = n_frames

        return {
            'rmsd': self.population_stats(rmsds),
            'rmsf': self.population_stats(rmsfs),
            'rog': self.population_stats(rogs)
        }

    def population_stats(self,
                         data: np.ndarray) -> np.ndarray:
        means = data[:, 0]
        stds = data[:, 1]
        ns = data[:, 2].astype(float)

        N_total = ns.sum()
        mean_combined = (ns * means).sum() / N_total
        
        # Formula: sigma^2 = ( Σ n_i (s_i^2 + (m_i - μ)^2) ) / N
        var_combined = (ns * (stds**2 + (means - mean_combined)**2)).sum() / N_total
        std_combined = np.sqrt(var_combined)
        
        return np.array([mean_combined, std_combined])

    def _calculate_confidence(self,
                              analysis: SimAnalysis) -> float:
        # TODO: compute this based on RMSD/RMSF threshholds
        return 0.75

    def _get_tools_used(self) -> list[str]:
        return ['openmm', 'mdanalysis']
