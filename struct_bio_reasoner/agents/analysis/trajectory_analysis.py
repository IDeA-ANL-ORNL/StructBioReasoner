"""
Analysis agent for StructBioReasoner
"""

import dill as pickle
import asyncio
import logging
from ...utils.parsl_settings import AuroraSettings, LocalSettings
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import numpy as np
from datetime import datetime

from academy.exchange import LocalExchangeFactory
from academy.manager import Manager
from concurrent.futures import ThreadPoolExecutor
    
from ...core.base_agent import BaseAgent
from ...data.protein_hypothesis import SimAnalysis, ProteinHypothesis


class TrajectoryAnalysisAgent:
    """
    """
    
    def __init__(self, 
                 agent_id: str,
                 config: Dict[str, Any],
                 parsl_config: Dict[str, Any]):
        """
        Initialize Trajectory Analysis Agent.
        
        Args:
            config: Configuration dictionary with MDAgent analyzer settings
        """
        self.agent_id = agent_id
        self.config = config.get('analysis', {})

        self.agent_type = "analysis"
        self.specialization = ""
        self.logger = logging.getLogger(__name__)
        
        # MDAgent components (initialized in initialize())
        self.manager = None

        # Load parsl kwargs
        self.parsl_config = parsl_config
        
    async def initialize(self,
                         parsl: Optional[dict] = None) -> bool:
        """
        Initialize MDAgent components.

        Returns:
            True if initialization successful, False otherwise
        """
        from MDAgent.analysis.analyzer_agent import AnalysisCoordinator

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

        self.parsl_settings = LocalSettings(**parsl_config).config_factory(Path.cwd())

        self.coordinator_handle = await self.manager.launch(
            AnalysisCoordinator,
            args=(self.parsl_settings,),
        )

        self.initialized = True
        self.logger.info("MDAgent components initialized successfully")

        return True
    
    async def perform_analysis(self,
                               analysis_schedule: dict[str, Any]) -> dict[str, Any]:
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
        if 'parsl' in analysis_schedule:
            parsl = analysis_schedule.pop('parsl')
        else:
            parsl = None

        if not await self.is_ready(parsl):
            self.logger.error("Analysis agent not ready")
            return {}
        
        try:
            self.logger.info('Analyzing simulation results')
            # Analyze results and create structured output
            analysis = await self.coordinator_handle.analyze(analysis_schedule)
            
            # Clean up agent/parsl
            await self.cleanup()
            
            self.logger.info(f"Analysis completed")

            return analysis

        except Exception as e:
            import traceback
            self.logger.info(traceback.format_exc())
            self.logger.error(f"Analysis failed: {e}")
            return {}

    def _calculate_confidence(self, trajectory_analysis: Dict[str, Any]) -> float:
        """
        Calculate confidence score based on trajectory analysis quality.

        Args:
            trajectory_analysis: Trajectory analysis results

        Returns:
            Confidence score (0.0 to 1.0)
        """
        if not trajectory_analysis: # analysis failed
            return 0.5

        confidence = 0.8  # Base confidence
        
        basic = trajectory_analysis.get('dynamic', {}).get('basic_simulation_analysis', {})
        # Adjust based on RMSD stability
        rmsd_std = basic.get('rmsd', {}).get('std', 0.0)
        if rmsd_std < 0.1:
            confidence += 0.1  # Very stable
        elif rmsd_std > 0.3:
            confidence -= 0.1  # Less stable

        # Adjust based on trajectory length
        traj_info = basic.get('trajectory_info', {})
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
            "capabilities": [
                "analysis"
            ],
            "integration_features": [
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
                    self.coordinator_handle = None
                    delattr(self, 'initialized')

            self.logger.info("Analysis agent cleanup completed")

        except Exception as e:
            self.logger.error(f"Analysis agent cleanup failed: {e}")

    async def analyze_hypothesis(self,
                                 hypothesis: ProteinHypothesis,
                                 task_params: dict[str, Any]) -> SimAnalysis:
        sim_results = await self.perform_analysis(
            task_params
        )

        confidence_score = self._calculate_confidence(sim_results)
        tools_used = self._get_tools_used()
        protein_id = task_params.get('protein_id', '')
        
        static_results = sim_results.get('static', None)
        if static_results is not None:
            analysis = StructureAnalysis()

        dynamic_results = sim_results.get('dynamic', None)
        if dynamic_results is not None:
            if 'basic_simulation_analysis' in sim_results['dynamic'].keys():
                summary = sim_results['dynamic']['basic_simulation_analysis']['summary']
                analysis = SimAnalysis(
                    protein_id=protein_id,
                    simulation_time_in_ns=self.prod_steps * 4 / 1000000,
                    rmsd=summary['rmsd'],
                    rmsf=summary['rmsf'],
                    rog=summary['rog']
                )
            if 'advanced_simulation_analysis' in sim_results['dynamic'].keys():
                analysis = StructuralAnalysis(
                    protein_id=protein_id,
                    binding_sites=[],
                )

        return analysis

    async def is_ready(self,
                       parsl: Optional[dict[str, Any]]=None) -> bool:
        if not hasattr(self, 'initialized'):
            await self.initialize(parsl)
        return self.initialized

    def _calculate_confidence(self,
                              analysis: SimAnalysis) -> float:
        # TODO: compute this based on RMSD/RMSF threshholds
        return 0.75

    def _get_tools_used(self) -> list[str]:
        return ['mdtraj', 'mdanalysis', 'rust-simulation-tools']
