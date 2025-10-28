"""
Structural Analysis Agent for protein engineering.

This agent performs structural analysis of proteins and mutations,
including active site identification, cavity analysis, and stability predictions.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

# Import base agent functionality
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent.parent.parent / "Jnana"))

from jnana.core.model_manager import UnifiedModelManager

# Import protein-specific components
from ...data.protein_hypothesis import ProteinHypothesis, StructuralAnalysis
from ...data.mutation_model import Mutation, MutationSet
from ...tools.pymol_wrapper import PyMOLWrapper
from ...tools.biopython_utils import BioPythonUtils


class StructuralAnalysisAgent:
    """
    Agent specialized in protein structural analysis.
    
    This agent can:
    - Analyze protein structures from PDB or AlphaFold
    - Identify active sites and binding sites
    - Predict mutation effects on structure
    - Assess protein stability and flexibility
    """
    
    def __init__(self, 
                 agent_id: str,
                 config: Dict[str, Any],
                 tools: Dict[str, Any],
                 model_manager: UnifiedModelManager):
        """
        Initialize the structural analysis agent.
        
        Args:
            agent_id: Unique identifier for this agent
            config: Agent configuration
            tools: Available tools (PyMOL, BioPython, etc.)
            model_manager: LLM model manager
        """
        self.agent_id = agent_id
        self.config = config
        self.tools = tools
        self.model_manager = model_manager
        self.logger = logging.getLogger(__name__)
        
        # Agent capabilities
        self.capabilities = config.get("capabilities", [
            "active_site_identification",
            "cavity_analysis",
            "interface_prediction",
            "conformational_sampling"
        ])
        
        # Tool references
        self.pymol = tools.get("pymol")
        self.biopython = tools.get("biopython")
        
        # Analysis parameters
        self.confidence_threshold = config.get("confidence_threshold", 0.7)
        
        self.logger.info(f"StructuralAnalysisAgent {agent_id} initialized")
    
    def is_ready(self) -> bool:
        """Check if agent is ready for analysis."""
        return (self.pymol is not None and self.pymol.is_ready()) or \
               (self.biopython is not None and self.biopython.is_ready())
    
    async def analyze_hypothesis(self, 
                                hypothesis: ProteinHypothesis, 
                                task_params: Dict[str, Any]) -> StructuralAnalysis:
        """
        Perform structural analysis of a protein hypothesis.
        
        Args:
            hypothesis: Protein hypothesis to analyze
            task_params: Analysis parameters
            
        Returns:
            StructuralAnalysis results
        """
        self.logger.info(f"Starting structural analysis for hypothesis {hypothesis.hypothesis_id}")
        
        # Create analysis object
        analysis = StructuralAnalysis(
            protein_id=hypothesis.protein_id,
            structure_source=hypothesis.structure_source or "unknown"
        )
        
        try:
            # Load protein structure
            structure_data = await self._load_protein_structure(hypothesis)
            if not structure_data:
                self.logger.warning("Could not load protein structure")
                analysis.confidence_score = 0.0
                return analysis
            
            # Perform structural analyses
            if "active_site_identification" in self.capabilities:
                await self._identify_active_sites(analysis, structure_data, hypothesis)
            
            if "cavity_analysis" in self.capabilities:
                await self._analyze_cavities(analysis, structure_data, hypothesis)
            
            if "interface_prediction" in self.capabilities:
                await self._predict_interfaces(analysis, structure_data, hypothesis)
            
            # Analyze mutations if present
            if hypothesis.target_mutations:
                await self._analyze_mutations(analysis, structure_data, hypothesis)
            
            # Calculate overall confidence
            analysis.confidence_score = self._calculate_confidence(analysis)
            analysis.tools_used = self._get_tools_used()
            
            self.logger.info(f"Structural analysis completed with confidence {analysis.confidence_score:.2f}")
            
        except Exception as e:
            self.logger.error(f"Structural analysis failed: {e}")
            analysis.confidence_score = 0.0
        
        return analysis
    
    async def _load_protein_structure(self, hypothesis: ProteinHypothesis) -> Optional[Dict[str, Any]]:
        """Load protein structure from various sources."""
        protein_id = hypothesis.protein_id
        structure_id = hypothesis.structure_id or protein_id
        
        if not structure_id:
            self.logger.warning("No protein or structure ID provided")
            return None
        
        # Try to load from PDB first
        if self.biopython:
            try:
                structure_data = await self.biopython.load_structure(structure_id, source="pdb")
                if structure_data:
                    hypothesis.structure_source = "pdb"
                    return structure_data
            except Exception as e:
                self.logger.debug(f"Failed to load from PDB: {e}")
        
        # Try AlphaFold database
        if self.biopython:
            try:
                structure_data = await self.biopython.load_structure(structure_id, source="alphafold")
                if structure_data:
                    hypothesis.structure_source = "alphafold"
                    return structure_data
            except Exception as e:
                self.logger.debug(f"Failed to load from AlphaFold: {e}")
        
        # TODO: Add CHAI-1 folding structure prediction
        return None
    
    async def _identify_active_sites(self, 
                                   analysis: StructuralAnalysis, 
                                   structure_data: Dict[str, Any],
                                   hypothesis: ProteinHypothesis):
        """Identify active sites in the protein structure."""
        self.logger.info("Identifying active sites")
        
        try:
            # Use BioPython for basic active site prediction
            if self.biopython:
                active_sites = await self.biopython.predict_active_sites(structure_data)
                analysis.active_site_residues = active_sites.get("residues", [])
                analysis.catalytic_residues = active_sites.get("catalytic", [])
            
            # Use PyMOL for visualization and additional analysis
            if self.pymol:
                binding_sites = await self.pymol.identify_binding_sites(structure_data)
                analysis.binding_sites = binding_sites
            
            # Use LLM for interpretation if available
            if analysis.active_site_residues:
                interpretation = await self._interpret_active_sites(
                    analysis.active_site_residues, hypothesis
                )
                analysis.active_site_residues.extend(interpretation.get("additional_residues", []))
        
        except Exception as e:
            self.logger.warning(f"Active site identification failed: {e}")
    
    async def _analyze_cavities(self, 
                              analysis: StructuralAnalysis, 
                              structure_data: Dict[str, Any],
                              hypothesis: ProteinHypothesis):
        """Analyze protein cavities and pockets."""
        self.logger.info("Analyzing protein cavities")
        
        try:
            if self.biopython:
                cavities = await self.biopython.detect_cavities(structure_data)
                analysis.cavities = cavities
            
            # Additional cavity analysis with PyMOL
            if self.pymol:
                cavity_volumes = await self.pymol.calculate_cavity_volumes(structure_data)
                for i, cavity in enumerate(analysis.cavities):
                    if i < len(cavity_volumes):
                        cavity["volume"] = cavity_volumes[i]
        
        except Exception as e:
            self.logger.warning(f"Cavity analysis failed: {e}")
    
    async def _predict_interfaces(self, 
                                analysis: StructuralAnalysis, 
                                structure_data: Dict[str, Any],
                                hypothesis: ProteinHypothesis):
        """Predict protein-protein interfaces."""
        self.logger.info("Predicting protein interfaces")
        
        try:
            if self.biopython:
                interfaces = await self.biopython.predict_interfaces(structure_data)
                # Store interface information in binding_sites
                for interface in interfaces:
                    analysis.binding_sites.append({
                        "type": "protein_interface",
                        "residues": interface.get("residues", []),
                        "area": interface.get("surface_area", 0),
                        "partner": interface.get("partner", "unknown")
                    })
        
        except Exception as e:
            self.logger.warning(f"Interface prediction failed: {e}")
    
    async def _analyze_mutations(self, 
                               analysis: StructuralAnalysis, 
                               structure_data: Dict[str, Any],
                               hypothesis: ProteinHypothesis):
        """Analyze the structural effects of proposed mutations."""
        self.logger.info("Analyzing mutation effects")
        
        try:
            for mutation in hypothesis.target_mutations:
                # Predict stability change
                if self.biopython:
                    stability_change = await self.biopython.predict_stability_change(
                        structure_data, mutation
                    )
                    mutation.stability_change = stability_change
                
                # Analyze structural context
                structural_context = await self._get_structural_context(
                    structure_data, mutation.position
                )
                mutation.secondary_structure = structural_context.get("secondary_structure", "")
                mutation.solvent_accessibility = structural_context.get("accessibility", None)
                mutation.domain = structural_context.get("domain", "")
            
            # Store overall stability predictions
            stability_changes = [m.stability_change for m in hypothesis.target_mutations 
                               if m.stability_change is not None]
            if stability_changes:
                analysis.stability_predictions["average_ddg"] = sum(stability_changes) / len(stability_changes)
                analysis.stability_predictions["total_ddg"] = sum(stability_changes)
        
        except Exception as e:
            self.logger.warning(f"Mutation analysis failed: {e}")
    
    async def _get_structural_context(self, structure_data: Dict[str, Any], position: int) -> Dict[str, Any]:
        """Get structural context for a specific residue position."""
        context = {}
        
        try:
            if self.biopython:
                context = await self.biopython.get_residue_context(structure_data, position)
        except Exception as e:
            self.logger.debug(f"Failed to get structural context for position {position}: {e}")
        
        return context
    
    async def _interpret_active_sites(self, active_sites: List[str], hypothesis: ProteinHypothesis) -> Dict[str, Any]:
        """Use LLM to interpret active site predictions."""
        if not self.model_manager:
            return {}
        
        try:
            # Create prompt for LLM interpretation
            prompt = f"""
            Analyze the following active site residues for protein {hypothesis.protein_id}:
            Active sites: {', '.join(active_sites)}
            
            Research goal: {hypothesis.metadata.get('research_goal', 'Not specified')}
            
            Please provide:
            1. Additional residues that might be functionally important
            2. Functional classification of the active site
            3. Potential binding partners or substrates
            
            Respond in JSON format with keys: additional_residues, functional_class, binding_partners
            """
            
            # Get model for structural analysis
            model_config = self.model_manager.get_task_model("scientific_evaluation")
            
            # TODO: Implement actual LLM call
            # For now, return empty interpretation
            return {"additional_residues": [], "functional_class": "unknown", "binding_partners": []}
        
        except Exception as e:
            self.logger.warning(f"LLM interpretation failed: {e}")
            return {}
    
    def _calculate_confidence(self, analysis: StructuralAnalysis) -> float:
        """Calculate overall confidence score for the analysis."""
        confidence_factors = []
        
        # Structure quality factor
        if analysis.structure_source == "pdb":
            confidence_factors.append(0.9)
        elif analysis.structure_source == "alphafold":
            confidence_factors.append(0.7)
        else:
            confidence_factors.append(0.3)
        
        # Analysis completeness factor
        completeness = 0.0
        if analysis.active_site_residues:
            completeness += 0.3
        if analysis.binding_sites:
            completeness += 0.3
        if analysis.cavities:
            completeness += 0.2
        if analysis.stability_predictions:
            completeness += 0.2
        
        confidence_factors.append(completeness)
        
        # Tool availability factor
        tool_factor = 0.5  # Base factor
        if self.pymol and self.pymol.is_ready():
            tool_factor += 0.25
        if self.biopython and self.biopython.is_ready():
            tool_factor += 0.25
        
        confidence_factors.append(tool_factor)
        
        # Calculate weighted average
        return sum(confidence_factors) / len(confidence_factors)
    
    def _get_tools_used(self) -> List[str]:
        """Get list of tools used in the analysis."""
        tools_used = []
        
        if self.pymol and self.pymol.is_ready():
            tools_used.append("pymol")
        if self.biopython and self.biopython.is_ready():
            tools_used.append("biopython")
        
        return tools_used
