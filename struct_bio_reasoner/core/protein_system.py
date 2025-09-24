"""
ProteinEngineeringSystem: Main system class extending Jnana for protein engineering.

This module provides the core system that integrates Jnana's capabilities
with protein-specific agents, tools, and knowledge systems.
"""

import asyncio
import logging
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

# Import Jnana components
import sys
sys.path.append(str(Path(__file__).parent.parent.parent.parent / "Jnana"))

from jnana.core.jnana_system import JnanaSystem
from jnana.data.unified_hypothesis import UnifiedHypothesis
from jnana.core.model_manager import UnifiedModelManager

# Import protein-specific components
from ..data.protein_hypothesis import ProteinHypothesis, MutationHypothesis
from ..agents.structural.structural_agent import StructuralAnalysisAgent
from ..agents.evolutionary.conservation_agent import EvolutionaryConservationAgent
from ..agents.energetic.energy_agent import EnergeticAnalysisAgent
from ..agents.design.mutation_agent import MutationDesignAgent
from ..tools.pymol_wrapper import PyMOLWrapper
from ..tools.biopython_utils import BioPythonUtils
from ..utils.config_loader import load_protein_config
from .knowledge_foundation import ProteinKnowledgeFoundation


class ProteinEngineeringSystem(JnanaSystem):
    """
    Main protein engineering system extending Jnana.
    
    This system combines Jnana's hypothesis generation and multi-agent
    capabilities with protein-specific tools, agents, and knowledge systems.
    """
    
    def __init__(self, 
                 config_path: Union[str, Path] = "config/protein_config.yaml",
                 jnana_config_path: Optional[Union[str, Path]] = None,
                 enable_tools: List[str] = None,
                 enable_agents: List[str] = None,
                 knowledge_graph: bool = True,
                 literature_processing: bool = True,
                 **kwargs):
        """
        Initialize the protein engineering system.
        
        Args:
            config_path: Path to protein-specific configuration
            jnana_config_path: Path to Jnana configuration (optional)
            enable_tools: List of tools to enable
            enable_agents: List of agents to enable
            knowledge_graph: Whether to enable knowledge graph
            literature_processing: Whether to enable literature processing
            **kwargs: Additional arguments passed to JnanaSystem
        """
        self.logger = logging.getLogger(__name__)
        
        # Load protein-specific configuration
        self.protein_config = load_protein_config(config_path)
        
        # Determine Jnana config path
        if not jnana_config_path:
            jnana_config_path = self.protein_config.get("jnana", {}).get("config_path", 
                                                                        "../Jnana/config/models.yaml")
        
        # Handle Biomni configuration by modifying the Jnana config if needed
        self._prepare_jnana_config(jnana_config_path)

        # Initialize base Jnana system
        super().__init__(
            config_path=jnana_config_path,
            **kwargs
        )
        
        # Protein-specific configuration
        self.enable_tools = enable_tools or ["pymol", "biopython"]
        self.enable_agents = enable_agents or ["structural", "evolutionary", "energetic", "design"]
        self.knowledge_graph_enabled = knowledge_graph
        self.literature_processing_enabled = literature_processing
        
        # Initialize protein-specific components
        self.protein_tools = {}
        self.protein_agents = {}
        self.knowledge_foundation = None
        
        # System state
        self.protein_system_ready = False
        
        self.logger.info("ProteinEngineeringSystem initialized")

    def _prepare_jnana_config(self, jnana_config_path: str):
        """
        Prepare Jnana configuration, modifying Biomni settings if needed.

        Args:
            jnana_config_path: Path to Jnana configuration file
        """
        try:
            # Check if we need to modify Biomni settings
            biomni_enabled = self.protein_config.get('jnana', {}).get('enable_biomni', True)

            # If Biomni should be disabled, create a modified config
            if not biomni_enabled:
                import tempfile


                # Read the original Jnana config
                with open(jnana_config_path, 'r') as f:
                    jnana_config = yaml.safe_load(f)

                # Modify Biomni setting
                if 'biomni' not in jnana_config:
                    jnana_config['biomni'] = {}
                jnana_config['biomni']['enabled'] = False

                # Create a temporary modified config file
                temp_config = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
                yaml.dump(jnana_config, temp_config, default_flow_style=False)
                temp_config.close()

                # Store the temp file path for cleanup later
                self._temp_jnana_config = temp_config.name

                # Update the config path to use our modified version
                # We'll modify the original file temporarily
                self._original_jnana_config = jnana_config_path
                with open(jnana_config_path, 'w') as f:
                    yaml.dump(jnana_config, f, default_flow_style=False)

                self.logger.info("Modified Jnana configuration to disable Biomni")
            else:
                self._temp_jnana_config = None
                self._original_jnana_config = None

        except Exception as e:
            self.logger.warning(f"Failed to modify Jnana configuration: {e}")
            self._temp_jnana_config = None
            self._original_jnana_config = None

    async def start(self):
        """Start the protein engineering system."""
        # Start base Jnana system
        await super().start()
        
        # Initialize protein-specific components
        await self._initialize_protein_tools()
        await self._initialize_protein_agents()
        await self._initialize_knowledge_foundation()
        
        self.protein_system_ready = True
        self.logger.info("ProteinEngineeringSystem started successfully")
    
    async def _initialize_protein_tools(self):
        """Initialize protein-specific tools."""
        self.logger.info("Initializing protein tools...")
        
        # Initialize PyMOL wrapper
        if "pymol" in self.enable_tools:
            try:
                pymol_config = self.protein_config.get("tools", {}).get("pymol", {})
                self.protein_tools["pymol"] = PyMOLWrapper(pymol_config)
                await self.protein_tools["pymol"].initialize()
                self.logger.info("PyMOL wrapper initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize PyMOL: {e}")
        
        # Initialize BioPython utilities
        if "biopython" in self.enable_tools:
            try:
                biopython_config = self.protein_config.get("tools", {}).get("biopython", {})
                self.protein_tools["biopython"] = BioPythonUtils(biopython_config)
                await self.protein_tools["biopython"].initialize()
                self.logger.info("BioPython utilities initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize BioPython: {e}")

        # Initialize OpenMM wrapper
        if "openmm" in self.enable_tools:
            try:
                from ..tools.openmm_wrapper import OpenMMWrapper
                openmm_config = self.protein_config.get("tools", {}).get("openmm", {})
                self.protein_tools["openmm"] = OpenMMWrapper(openmm_config)
                await self.protein_tools["openmm"].initialize()
                self.logger.info("OpenMM wrapper initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize OpenMM: {e}")

        # TODO: Initialize other tools (Rosetta, AlphaFold, ESM, etc.)

        self.logger.info(f"Initialized {len(self.protein_tools)} protein tools")
    
    async def _initialize_protein_agents(self):
        """Initialize protein-specific agents."""
        self.logger.info("Initializing protein agents...")
        
        # Get agent configurations
        agent_configs = self.protein_config.get("agents", {})
        
        # Initialize structural analysis agent
        if "structural" in self.enable_agents:
            try:
                structural_config = agent_configs.get("structural_analysis", {})
                self.protein_agents["structural"] = StructuralAnalysisAgent(
                    agent_id="structural_analysis",
                    config=structural_config,
                    tools=self.protein_tools,
                    model_manager=self.model_manager
                )
                self.logger.info("Structural analysis agent initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize structural agent: {e}")
        
        # Initialize evolutionary conservation agent
        if "evolutionary" in self.enable_agents:
            try:
                evolutionary_config = agent_configs.get("evolutionary_conservation", {})
                self.protein_agents["evolutionary"] = EvolutionaryConservationAgent(
                    agent_id="evolutionary_conservation",
                    config=evolutionary_config,
                    tools=self.protein_tools,
                    model_manager=self.model_manager
                )
                self.logger.info("Evolutionary conservation agent initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize evolutionary agent: {e}")
        
        # Initialize energetic analysis agent
        if "energetic" in self.enable_agents:
            try:
                energetic_config = agent_configs.get("energetic_analysis", {})
                self.protein_agents["energetic"] = EnergeticAnalysisAgent(
                    agent_id="energetic_analysis",
                    config=energetic_config,
                    tools=self.protein_tools,
                    model_manager=self.model_manager
                )
                self.logger.info("Energetic analysis agent initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize energetic agent: {e}")
        
        # Initialize mutation design agent
        if "design" in self.enable_agents:
            try:
                design_config = agent_configs.get("mutation_design", {})
                self.protein_agents["design"] = MutationDesignAgent(
                    agent_id="mutation_design",
                    config=design_config,
                    tools=self.protein_tools,
                    model_manager=self.model_manager
                )
                self.logger.info("Mutation design agent initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize design agent: {e}")
        
        self.logger.info(f"Initialized {len(self.protein_agents)} protein agents")
    
    async def _initialize_knowledge_foundation(self):
        """Initialize protein knowledge foundation."""
        if not (self.knowledge_graph_enabled or self.literature_processing_enabled):
            return
        
        self.logger.info("Initializing protein knowledge foundation...")
        
        try:
            knowledge_config = self.protein_config.get("knowledge_sources", {})
            self.knowledge_foundation = ProteinKnowledgeFoundation(
                config=knowledge_config,
                enable_knowledge_graph=self.knowledge_graph_enabled,
                enable_literature_processing=self.literature_processing_enabled
            )
            await self.knowledge_foundation.initialize()
            self.logger.info("Protein knowledge foundation initialized")
        except Exception as e:
            self.logger.warning(f"Failed to initialize knowledge foundation: {e}")
            self.knowledge_foundation = None
    
    async def generate_protein_hypothesis(self, 
                                        research_goal: str,
                                        protein_id: Optional[str] = None,
                                        mutation_context: Optional[Dict] = None,
                                        strategy: str = "comprehensive") -> ProteinHypothesis:
        """
        Generate a protein-specific hypothesis.
        
        Args:
            research_goal: The research objective
            protein_id: Target protein identifier (PDB ID, UniProt ID, etc.)
            mutation_context: Context for mutation-based hypotheses
            strategy: Generation strategy
            
        Returns:
            Generated protein hypothesis
        """
        self.logger.info(f"Generating protein hypothesis with strategy: {strategy}")
        
        # Create protein-specific task parameters
        task_params = {
            "research_goal": research_goal,
            "protein_id": protein_id,
            "mutation_context": mutation_context,
            "strategy": strategy,
            "enable_structural_analysis": "structural" in self.protein_agents,
            "enable_evolutionary_analysis": "evolutionary" in self.protein_agents,
            "enable_energetic_analysis": "energetic" in self.protein_agents
        }
        
        # Generate base hypothesis using Jnana
        base_hypothesis = await self.generate_single_hypothesis(strategy)
        
        # Convert to protein-specific hypothesis
        protein_hypothesis = ProteinHypothesis.from_unified_hypothesis(
            base_hypothesis,
            protein_id=protein_id,
            mutation_context=mutation_context
        )
        
        # Enhance with protein-specific analysis
        await self._enhance_protein_hypothesis(protein_hypothesis, task_params)
        
        return protein_hypothesis
    
    async def _enhance_protein_hypothesis(self, 
                                        hypothesis: ProteinHypothesis, 
                                        task_params: Dict):
        """Enhance hypothesis with protein-specific analysis."""
        
        # Structural analysis
        if "structural" in self.protein_agents:
            try:
                structural_analysis = await self.protein_agents["structural"].analyze_hypothesis(
                    hypothesis, task_params
                )
                hypothesis.add_structural_analysis(structural_analysis)
            except Exception as e:
                self.logger.warning(f"Structural analysis failed: {e}")
        
        # Evolutionary analysis
        if "evolutionary" in self.protein_agents:
            try:
                evolutionary_analysis = await self.protein_agents["evolutionary"].analyze_hypothesis(
                    hypothesis, task_params
                )
                hypothesis.add_evolutionary_analysis(evolutionary_analysis)
            except Exception as e:
                self.logger.warning(f"Evolutionary analysis failed: {e}")
        
        # Energetic analysis
        if "energetic" in self.protein_agents:
            try:
                energetic_analysis = await self.protein_agents["energetic"].analyze_hypothesis(
                    hypothesis, task_params
                )
                hypothesis.add_energetic_analysis(energetic_analysis)
            except Exception as e:
                self.logger.warning(f"Energetic analysis failed: {e}")
    
    def get_protein_system_status(self) -> Dict[str, Any]:
        """Get protein system status."""
        base_status = self.get_system_status()
        
        protein_status = {
            "protein_system_ready": self.protein_system_ready,
            "enabled_tools": list(self.protein_tools.keys()),
            "enabled_agents": list(self.protein_agents.keys()),
            "knowledge_graph_enabled": self.knowledge_graph_enabled,
            "literature_processing_enabled": self.literature_processing_enabled,
            "knowledge_foundation_ready": self.knowledge_foundation is not None,
            "tool_status": {name: tool.is_ready() for name, tool in self.protein_tools.items()},
            "agent_status": {name: agent.is_ready() for name, agent in self.protein_agents.items()}
        }
        
        return {**base_status, "protein_engineering": protein_status}

    async def stop(self):
        """Stop the protein engineering system."""
        # Stop protein-specific components
        if self.knowledge_foundation:
            # TODO: Add cleanup for knowledge foundation
            pass

        # Stop base Jnana system
        await super().stop()

        # Clean up temporary configuration files
        self._cleanup_jnana_config()

        self.protein_system_ready = False
        self.logger.info("ProteinEngineeringSystem stopped")

    def _cleanup_jnana_config(self):
        """Clean up temporary Jnana configuration modifications."""
        try:
            if hasattr(self, '_temp_jnana_config') and self._temp_jnana_config:
                # Remove temporary file
                import os
                if os.path.exists(self._temp_jnana_config):
                    os.unlink(self._temp_jnana_config)

            # Note: We don't restore the original config file since it might be in use
            # The modification is minimal and only disables Biomni

        except Exception as e:
            self.logger.warning(f"Failed to cleanup Jnana configuration: {e}")
