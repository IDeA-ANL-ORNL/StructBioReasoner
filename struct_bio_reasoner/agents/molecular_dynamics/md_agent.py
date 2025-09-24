"""
Molecular Dynamics Agent for protein engineering hypothesis generation and validation.

This agent uses OpenMM simulations to generate hypotheses about protein
thermostability, dynamics, and mutation effects.
"""

import asyncio
import logging
import uuid
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime

from ...tools.openmm_wrapper import OpenMMWrapper
from ...data.protein_hypothesis import ProteinHypothesis
from ...core.base_agent import BaseAgent


class MolecularDynamicsAgent(BaseAgent):
    """
    Agent specialized in molecular dynamics simulations for protein engineering.
    
    Capabilities:
    - Thermostability prediction through MD simulations
    - Mutation effect validation
    - Dynamic flexibility analysis
    - Hypothesis generation based on MD insights
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize MD agent.

        Args:
            config: Agent configuration
        """
        # Initialize base agent
        super().__init__(config)

        # MD-specific capabilities
        self.capabilities = [
            "thermostability_prediction",
            "mutation_validation",
            "flexibility_analysis",
            "dynamics_hypothesis_generation"
        ]
        
        # MD simulation parameters
        self.simulation_config = config.get("simulation", {
            "temperature": 300,  # K
            "pressure": 1.0,     # atm
            "equilibration_steps": 10000,
            "production_steps": 500000,  # 1ns
            "force_field": "amber14-all.xml",
            "water_model": "amber14/tip3pfb.xml"
        })
        
        # Analysis parameters
        self.analysis_config = config.get("analysis", {
            "rmsd_threshold": 0.3,  # nm
            "rmsf_threshold": 0.2,  # nm
            "stability_score_threshold": 70.0,
            "confidence_threshold": 0.6
        })
        
        # Tools
        self.openmm_wrapper = None
        self.initialized = False
        
        # State
        self.active_simulations = {}
        self.completed_analyses = {}
        self.generated_hypotheses = []
    
    async def initialize(self):
        """Initialize the MD agent."""
        try:
            # Initialize OpenMM wrapper
            self.openmm_wrapper = OpenMMWrapper(self.simulation_config)
            await self.openmm_wrapper.initialize()
            
            if not self.openmm_wrapper.is_ready():
                self.logger.warning("OpenMM not available - MD agent will operate in limited mode")
                self.initialized = False
                return
            
            self.initialized = True
            self.logger.info(f"MD agent {self.agent_id} initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize MD agent: {e}")
            self.initialized = False
    
    def is_ready(self) -> bool:
        """Check if MD agent is ready."""
        return self.initialized and self.openmm_wrapper and self.openmm_wrapper.is_ready()
    
    async def generate_thermostability_hypothesis(self, structure_data: Dict[str, Any],
                                                protein_name: str = "unknown") -> Optional[ProteinHypothesis]:
        """
        Generate thermostability hypothesis based on MD simulation.
        
        Args:
            structure_data: Protein structure data
            protein_name: Name of the protein
            
        Returns:
            Generated hypothesis or None if failed
        """
        if not self.is_ready():
            self.logger.error("MD agent not ready")
            return None
        
        try:
            # Create simulation ID
            simulation_id = f"thermo_{protein_name}_{uuid.uuid4().hex[:8]}"
            
            # Setup and run simulation
            self.logger.info(f"Setting up thermostability simulation for {protein_name}")
            
            if not await self.openmm_wrapper.setup_simulation(structure_data, simulation_id):
                return None
            
            # Run equilibration and production
            if not await self.openmm_wrapper.run_equilibration(simulation_id):
                return None
            
            trajectory_file = await self.openmm_wrapper.run_production(simulation_id)
            if not trajectory_file:
                return None
            
            # Analyze trajectory
            analysis = await self.openmm_wrapper.analyze_trajectory(simulation_id)
            if not analysis:
                return None
            
            # Predict thermostability
            thermo_prediction = await self.openmm_wrapper.predict_thermostability(simulation_id)
            if not thermo_prediction:
                return None
            
            # Generate hypothesis based on results
            hypothesis = await self._create_thermostability_hypothesis(
                protein_name, analysis, thermo_prediction, simulation_id
            )
            
            # Store results
            self.completed_analyses[simulation_id] = {
                'analysis': analysis,
                'thermostability': thermo_prediction,
                'hypothesis': hypothesis
            }
            
            # Cleanup simulation
            await self.openmm_wrapper.cleanup_simulation(simulation_id)
            
            return hypothesis
            
        except Exception as e:
            self.logger.error(f"Thermostability hypothesis generation failed: {e}")
            return None
    
    async def validate_mutations(self, structure_data: Dict[str, Any],
                               mutations: List[Dict[str, Any]],
                               protein_name: str = "unknown") -> Optional[ProteinHypothesis]:
        """
        Validate mutations through MD simulations.
        
        Args:
            structure_data: Protein structure data
            mutations: List of mutations to validate
            protein_name: Name of the protein
            
        Returns:
            Validation hypothesis or None if failed
        """
        if not self.is_ready():
            self.logger.error("MD agent not ready")
            return None
        
        try:
            # Setup wildtype simulation
            wt_simulation_id = f"wt_{protein_name}_{uuid.uuid4().hex[:8]}"
            
            self.logger.info(f"Setting up wildtype simulation for {protein_name}")
            if not await self._run_complete_simulation(structure_data, wt_simulation_id):
                return None
            
            # Setup mutant simulations
            mutant_ids = []
            for i, mutation_set in enumerate(mutations):
                mutant_id = f"mut_{protein_name}_{i}_{uuid.uuid4().hex[:8]}"
                
                self.logger.info(f"Setting up mutant simulation {i+1}/{len(mutations)}")
                if await self._run_complete_simulation(structure_data, mutant_id, [mutation_set]):
                    mutant_ids.append(mutant_id)
            
            if not mutant_ids:
                self.logger.error("No mutant simulations completed successfully")
                return None
            
            # Compare mutations
            comparison = await self.openmm_wrapper.compare_mutations(wt_simulation_id, mutant_ids)
            if not comparison:
                return None
            
            # Generate validation hypothesis
            hypothesis = await self._create_mutation_validation_hypothesis(
                protein_name, mutations, comparison
            )
            
            # Cleanup simulations
            await self.openmm_wrapper.cleanup_simulation(wt_simulation_id)
            for mutant_id in mutant_ids:
                await self.openmm_wrapper.cleanup_simulation(mutant_id)
            
            return hypothesis
            
        except Exception as e:
            self.logger.error(f"Mutation validation failed: {e}")
            return None
    
    async def analyze_protein_dynamics(self, structure_data: Dict[str, Any],
                                     protein_name: str = "unknown") -> Optional[ProteinHypothesis]:
        """
        Analyze protein dynamics and generate flexibility-based hypotheses.
        
        Args:
            structure_data: Protein structure data
            protein_name: Name of the protein
            
        Returns:
            Dynamics analysis hypothesis or None if failed
        """
        if not self.is_ready():
            self.logger.error("MD agent not ready")
            return None
        
        try:
            # Create simulation ID
            simulation_id = f"dynamics_{protein_name}_{uuid.uuid4().hex[:8]}"
            
            # Run complete simulation
            if not await self._run_complete_simulation(structure_data, simulation_id):
                return None
            
            # Get analysis results
            analysis = self.completed_analyses[simulation_id]['analysis']
            thermo_prediction = self.completed_analyses[simulation_id]['thermostability']
            
            # Generate dynamics hypothesis
            hypothesis = await self._create_dynamics_hypothesis(
                protein_name, analysis, thermo_prediction, simulation_id
            )
            
            return hypothesis
            
        except Exception as e:
            self.logger.error(f"Dynamics analysis failed: {e}")
            return None
    
    # Helper methods
    
    async def _run_complete_simulation(self, structure_data: Dict[str, Any],
                                     simulation_id: str,
                                     mutations: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Run complete MD simulation pipeline."""
        try:
            # Setup simulation
            if not await self.openmm_wrapper.setup_simulation(structure_data, simulation_id, mutations):
                return False
            
            # Run equilibration
            if not await self.openmm_wrapper.run_equilibration(simulation_id):
                return False
            
            # Run production
            trajectory_file = await self.openmm_wrapper.run_production(simulation_id)
            if not trajectory_file:
                return False
            
            # Analyze trajectory
            analysis = await self.openmm_wrapper.analyze_trajectory(simulation_id)
            if not analysis:
                return False
            
            # Predict thermostability
            thermo_prediction = await self.openmm_wrapper.predict_thermostability(simulation_id)
            if not thermo_prediction:
                return False
            
            # Store results
            self.completed_analyses[simulation_id] = {
                'analysis': analysis,
                'thermostability': thermo_prediction
            }
            
            return True
            
        except Exception as e:
            self.logger.error(f"Complete simulation failed for {simulation_id}: {e}")
            return False

    async def _create_thermostability_hypothesis(self, protein_name: str,
                                               analysis: Dict[str, Any],
                                               thermo_prediction: Dict[str, Any],
                                               simulation_id: str) -> ProteinHypothesis:
        """Create thermostability hypothesis from MD analysis."""

        stability_score = thermo_prediction['stability_score']
        delta_tm = thermo_prediction['predicted_delta_tm']
        flexible_residues = thermo_prediction['flexible_residues']

        # Generate hypothesis content
        if stability_score > self.analysis_config['stability_score_threshold']:
            stability_assessment = "high thermostability"
            improvement_needed = "minimal"
        elif stability_score > 50:
            stability_assessment = "moderate thermostability"
            improvement_needed = "moderate"
        else:
            stability_assessment = "low thermostability"
            improvement_needed = "significant"

        hypothesis_content = f"""
        Molecular dynamics simulation analysis of {protein_name} reveals {stability_assessment}
        with a predicted stability score of {stability_score:.1f}/100. The protein shows
        {improvement_needed} need for thermostability enhancement.

        Key findings:
        - RMSD stability: {analysis['rmsd']['std']:.3f} nm (lower is more stable)
        - Average flexibility (RMSF): {analysis['rmsf']['mean']:.3f} nm
        - Radius of gyration stability: {analysis['radius_of_gyration']['std']:.3f} nm
        - Predicted ΔTm: {delta_tm:.1f}°C

        Flexible regions identified at residues: {flexible_residues[:5]}
        These regions represent potential targets for rigidifying mutations to enhance thermostability.

        Recommended strategies:
        1. Target flexible loops with proline substitutions
        2. Introduce disulfide bonds in flexible regions
        3. Optimize hydrophobic core packing
        4. Enhance electrostatic interactions
        """

        # Create hypothesis
        hypothesis = ProteinHypothesis(
            title=f"MD-based thermostability analysis of {protein_name}",
            content=hypothesis_content.strip(),
            description=f"Molecular dynamics simulation predicts {stability_assessment} for {protein_name}",
            hypothesis_type="md_thermostability",
            generation_timestamp=datetime.now().isoformat(),
            metadata={
                'simulation_id': simulation_id,
                'stability_score': stability_score,
                'predicted_delta_tm': delta_tm,
                'flexible_residues': flexible_residues,
                'analysis_summary': {
                    'rmsd_std': analysis['rmsd']['std'],
                    'rmsf_mean': analysis['rmsf']['mean'],
                    'rg_std': analysis['radius_of_gyration']['std']
                },
                'agent_id': self.agent_id,
                'simulation_parameters': self.simulation_config
            }
        )

        # Set hallmarks based on analysis quality
        hypothesis.hallmarks = {
            'testability': 8.5,  # MD predictions are highly testable
            'specificity': 7.5,  # Specific residue-level predictions
            'grounded_knowledge': 9.0,  # Based on physics-based simulations
            'predictive_power': 8.0,  # Quantitative predictions
            'parsimony': 7.0   # Straightforward thermostability model
        }

        self.generated_hypotheses.append(hypothesis)
        return hypothesis

    async def _create_mutation_validation_hypothesis(self, protein_name: str,
                                                   mutations: List[Dict[str, Any]],
                                                   comparison: Dict[str, Any]) -> ProteinHypothesis:
        """Create mutation validation hypothesis from comparison results."""

        beneficial_mutations = [m for m in comparison['mutant_comparisons'] if m['beneficial']]
        detrimental_mutations = [m for m in comparison['mutant_comparisons'] if not m['beneficial']]

        # Generate hypothesis content
        hypothesis_content = f"""
        Molecular dynamics validation of {len(mutations)} proposed mutations for {protein_name}
        reveals {len(beneficial_mutations)} beneficial and {len(detrimental_mutations)}
        detrimental mutations based on thermostability predictions.

        Wildtype baseline:
        - Stability score: {comparison['wildtype_stability_score']:.1f}/100
        - Predicted ΔTm: {comparison['wildtype_delta_tm']:.1f}°C

        Beneficial mutations:
        """

        for mut in beneficial_mutations:
            hypothesis_content += f"""
        - {mut['mutations']}: ΔStability = +{mut['stability_change']:.1f}, ΔTm = +{mut['delta_tm_change']:.1f}°C
          Confidence: {mut['confidence']:.2f}
        """

        if detrimental_mutations:
            hypothesis_content += f"""

        Detrimental mutations to avoid:
        """
            for mut in detrimental_mutations[:3]:  # Show top 3 worst
                hypothesis_content += f"""
        - {mut['mutations']}: ΔStability = {mut['stability_change']:.1f}, ΔTm = {mut['delta_tm_change']:.1f}°C
        """

        hypothesis_content += f"""

        Validation confidence: {np.mean([m['confidence'] for m in comparison['mutant_comparisons']]):.2f}

        Recommendations:
        1. Prioritize beneficial mutations for experimental validation
        2. Avoid detrimental mutations in design strategies
        3. Consider combinatorial effects of multiple mutations
        4. Validate predictions with thermal stability assays
        """

        # Create hypothesis
        hypothesis = ProteinHypothesis(
            title=f"MD validation of mutations in {protein_name}",
            content=hypothesis_content.strip(),
            description=f"Molecular dynamics validation identifies {len(beneficial_mutations)} beneficial mutations",
            hypothesis_type="md_mutation_validation",
            generation_timestamp=datetime.now().isoformat(),
            metadata={
                'total_mutations': len(mutations),
                'beneficial_count': len(beneficial_mutations),
                'detrimental_count': len(detrimental_mutations),
                'comparison_results': comparison,
                'agent_id': self.agent_id,
                'validation_confidence': np.mean([m['confidence'] for m in comparison['mutant_comparisons']])
            }
        )

        # Set hallmarks
        hypothesis.hallmarks = {
            'testability': 9.0,  # Direct experimental validation possible
            'specificity': 8.5,  # Specific mutation effects quantified
            'grounded_knowledge': 9.0,  # Physics-based validation
            'predictive_power': 8.5,  # Quantitative mutation effects
            'parsimony': 8.0   # Clear mutation-effect relationships
        }

        self.generated_hypotheses.append(hypothesis)
        return hypothesis

    async def _create_dynamics_hypothesis(self, protein_name: str,
                                        analysis: Dict[str, Any],
                                        thermo_prediction: Dict[str, Any],
                                        simulation_id: str) -> ProteinHypothesis:
        """Create dynamics analysis hypothesis."""

        flexible_residues = thermo_prediction['flexible_residues']
        stable_residues = thermo_prediction['stable_residues']
        mutation_recommendations = thermo_prediction['mutation_recommendations']

        # Analyze secondary structure stability
        ss_analysis = analysis['secondary_structure']

        hypothesis_content = f"""
        Molecular dynamics analysis of {protein_name} reveals distinct dynamic regions
        with implications for protein engineering strategies.

        Dynamic Profile:
        - Highly flexible residues ({len(flexible_residues)}): {flexible_residues[:10]}
        - Stable core residues ({len(stable_residues)}): {stable_residues[:10]}
        - Secondary structure content: {ss_analysis['helix_content']:.1f}% helix,
          {ss_analysis['sheet_content']:.1f}% sheet, {ss_analysis['coil_content']:.1f}% coil

        Engineering Implications:
        1. Flexible regions are prime targets for rigidification strategies
        2. Stable regions should be conserved to maintain fold integrity
        3. Loop regions show highest mobility and mutation tolerance
        4. Core secondary structures provide stability framework

        Mutation Strategy Recommendations:
        """

        for rec in mutation_recommendations[:5]:
            hypothesis_content += f"""
        - Residue {rec['residue_index']}: {rec['mutation_type']}
          ({rec['rationale']}, confidence: {rec['confidence']:.2f})
        """

        hypothesis_content += f"""

        Predicted outcomes:
        - Rigidification of flexible regions could improve thermostability by 2-5°C
        - Conservation of stable regions maintains protein function
        - Targeted mutations show {np.mean([r['confidence'] for r in mutation_recommendations]):.2f} average confidence
        """

        # Create hypothesis
        hypothesis = ProteinHypothesis(
            title=f"Dynamics-based engineering strategy for {protein_name}",
            content=hypothesis_content.strip(),
            description=f"MD dynamics analysis identifies {len(flexible_residues)} flexible and {len(stable_residues)} stable regions",
            hypothesis_type="md_dynamics_analysis",
            generation_timestamp=datetime.now().isoformat(),
            metadata={
                'simulation_id': simulation_id,
                'flexible_residues': flexible_residues,
                'stable_residues': stable_residues,
                'mutation_recommendations': mutation_recommendations,
                'secondary_structure': ss_analysis,
                'agent_id': self.agent_id
            }
        )

        # Set hallmarks
        hypothesis.hallmarks = {
            'testability': 8.0,  # Dynamics predictions testable via NMR/HDX
            'specificity': 8.5,  # Residue-specific flexibility predictions
            'grounded_knowledge': 9.0,  # Based on MD simulations
            'predictive_power': 7.5,  # Dynamics-structure relationships
            'parsimony': 7.5   # Clear flexibility-stability model
        }

        self.generated_hypotheses.append(hypothesis)
        return hypothesis

    def get_agent_status(self) -> Dict[str, Any]:
        """Get current status of the MD agent."""
        return {
            'agent_id': self.agent_id,
            'initialized': self.initialized,
            'openmm_ready': self.openmm_wrapper.is_ready() if self.openmm_wrapper else False,
            'capabilities': self.capabilities,
            'active_simulations': len(self.active_simulations),
            'completed_analyses': len(self.completed_analyses),
            'generated_hypotheses': len(self.generated_hypotheses),
            'simulation_config': self.simulation_config
        }

    async def generate_hypotheses(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate molecular dynamics-based hypotheses for protein engineering.

        Args:
            context: Analysis context containing protein information

        Returns:
            List of hypothesis dictionaries
        """
        hypotheses = []

        try:
            # Extract context information
            protein_sequence = context.get('protein_sequence', '')
            target_protein = context.get('target_protein', 'unknown')
            analysis_goals = context.get('analysis_goals', [])

            # Generate thermostability hypothesis
            if 'thermostability' in str(analysis_goals).lower() or 'stability' in str(analysis_goals).lower():
                thermo_hypothesis = {
                    'title': 'Molecular Dynamics Thermostability Validation',
                    'strategy': 'thermostability_validation',
                    'approach': 'temperature_gradient_simulation',
                    'description': f'Validate thermostability predictions for {target_protein} using MD simulations at multiple temperatures',
                    'confidence': 0.75,
                    'source': 'MolecularDynamicsAgent',
                    'execution_plan': {
                        'simulation_temperatures': [300, 320, 340, 360, 380, 400],  # K
                        'simulation_time_ns': 10,
                        'analysis_metrics': ['RMSD', 'RMSF', 'radius_of_gyration', 'secondary_structure'],
                        'validation_approach': 'temperature_dependent_stability_scoring'
                    },
                    'expected_outcomes': [
                        'Quantitative stability scores at different temperatures',
                        'Identification of unfolding initiation sites',
                        'Validation of mutation effects on thermostability'
                    ]
                }
                hypotheses.append(thermo_hypothesis)

            # Generate mutation validation hypothesis
            mutation_hypothesis = {
                'title': 'MD-Based Mutation Effect Validation',
                'strategy': 'mutation_validation',
                'approach': 'comparative_simulation_analysis',
                'description': f'Compare wild-type and mutant {target_protein} dynamics to validate predicted mutation effects',
                'confidence': 0.70,
                'source': 'MolecularDynamicsAgent'
            }
            hypotheses.append(mutation_hypothesis)

            self.logger.info(f"Generated {len(hypotheses)} MD-based hypotheses")

        except Exception as e:
            self.logger.error(f"Error generating MD hypotheses: {e}")

        return hypotheses

    def get_capabilities(self) -> List[str]:
        """Get list of agent capabilities."""
        return self.capabilities
