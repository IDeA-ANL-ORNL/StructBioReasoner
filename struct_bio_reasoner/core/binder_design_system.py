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

# Import protein-specific components
from ..data.protein_hypothesis import ProteinHypothesis
from ..agents.computational_design.bindcraft_agent import BindCraftAgent
from ..agents.molecular_dynamics.mdagent_adapter import MDAgentAdapter
from ..agents.energetic.energy_agent import EnergeticAnalysisAgent
from ..tools.pymol_wrapper import PyMOLWrapper
from ..tools.biopython_utils import BioPythonUtils
from ..utils.config_loader import load_binder_config
from .knowledge_foundation import ProteinKnowledgeFoundation


class BinderDesignSystem(JnanaSystem):
    """
    Main binder design system extending Jnana.
    
    This system combines Jnana's hypothesis generation and multi-agent
    capabilities with protein-specific tools, agents, and knowledge systems.
    """
    
    def __init__(self, 
                 config_path: Union[str, Path] = "config/binder_config.yaml",
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
        self.binder_config = load_binder_config(config_path)
        
        print('loaded binder config')
        # Determine Jnana config path
        if not jnana_config_path:
            jnana_config_path = self.binder_config.get("jnana", {}).get("config_path", 
                                                                        "../Jnana/config/models.yaml")
        
        # Handle Biomni configuration by modifying the Jnana config if needed
        self._prepare_jnana_config(jnana_config_path)

        # Initialize base Jnana system
        super().__init__(
            config_path=jnana_config_path,
            **kwargs
        )
        
        # Protein-specific configuration
        self.enable_tools = enable_tools or []
        self.enable_agents = enable_agents or ['computational_design', 'molecular_dynamics']
        self.knowledge_graph_enabled = knowledge_graph
        self.literature_processing_enabled = literature_processing
        
        # Initialize design-specific components
        self.design_tools = {}
        self.design_agents = {}
        self.knowledge_foundation = None

        # System state
        self.design_system_ready = False
        
        self.logger.info("BinderDesignSystem initialized")

    def _prepare_jnana_config(self, jnana_config_path: str):
        """
        Prepare Jnana configuration, modifying Biomni settings if needed.

        Args:
            jnana_config_path: Path to Jnana configuration file
        """
        try:
            # Check if we need to modify Biomni settings
            biomni_enabled = self.binder_config.get('jnana', {}).get('enable_biomni', True)

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
        
        # Initialize design-specific components
        #await self._initialize_design_tools()
        await self._initialize_design_agents()
        await self._initialize_knowledge_foundation()

        self.design_system_ready = True
        self.logger.info("BinderDesignSystem started successfully")
    
    async def _initialize_design_tools(self):
        """Initialize design-specific tools."""
        self.logger.info("Initializing design tools...")

        # Initialize PyMOL wrapper
        if "pymol" in self.enable_tools:
            try:
                pymol_config = self.binder_config.get("tools", {}).get("pymol", {})
                self.design_tools["pymol"] = PyMOLWrapper(pymol_config)
                await self.design_tools["pymol"].initialize()
                self.logger.info("PyMOL wrapper initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize PyMOL: {e}")

        # Initialize BioPython utilities
        if "biopython" in self.enable_tools:
            try:
                biopython_config = self.binder_config.get("tools", {}).get("biopython", {})
                self.design_tools["biopython"] = BioPythonUtils(biopython_config)
                await self.design_tools["biopython"].initialize()
                self.logger.info("BioPython utilities initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize BioPython: {e}")

        # Initialize OpenMM wrapper
        if "openmm" in self.enable_tools:
            try:
                from ..tools.openmm_wrapper import OpenMMWrapper
                openmm_config = self.binder_config.get("tools", {}).get("openmm", {})
                self.design_tools["openmm"] = OpenMMWrapper(openmm_config)
                await self.design_tools["openmm"].initialize()
                self.logger.info("OpenMM wrapper initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize OpenMM: {e}")

        # TODO: Initialize other tools (Rosetta, AlphaFold, ESM, etc.)

        self.logger.info(f"Initialized {len(self.design_tools)} design tools")
    
    async def _initialize_design_agents(self):
        """Initialize protein-specific agents."""
        self.logger.info("Initializing protein agents...")
        
        # Get agent configurations
        agent_configs = self.binder_config.get("agents", {})
        
        # Initialize structural analysis agent
        if 'computational_design' in self.enable_agents:
            try:
                design_config = agent_configs.get('computational_design', {})
                self.design_agents['computational_design'] = BindCraftAgent(
                                                                agent_id='binder_design',
                                                                config=design_config,
                                                                model_manager=self.model_manager
                                                                )
                self.logger.info("BindCraft agent initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize BindCraft agent: {e}")
        
        # Initialize molecular dynamics agent
        if "molecular_dynamics" in self.enable_agents:
            try:
                md_config = agent_configs.get("molecular_dynamics", {})
                self.design_agents['molecular_dynamics'] = MDAgentAdapter(
                    agent_id="molecular_dynamics",
                    config=md_config
                )
                self.logger.info("MD agent initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize MD agent: {e}")
        
        self.logger.info(f"Initialized {len(self.design_agents)} protein agents")
    
    async def _initialize_knowledge_foundation(self):
        """Initialize protein knowledge foundation."""
        if not (self.knowledge_graph_enabled or self.literature_processing_enabled):
            return
        
        self.logger.info("Initializing protein knowledge foundation...")
        
        try:
            knowledge_config = self.binder_config.get("knowledge_sources", {})
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
                                        biological_context: Optional[Dict] = None,
                                        strategy: str = "comprehensive") -> ProteinHypothesis:
        """
        Generate a protein-specific hypothesis.
        
        Args:
            research_goal: The research objective
            protein_id: Target protein identifier (PDB ID, UniProt ID, etc.)
            biological_context: Context for interactome or residues of interest
            strategy: Generation strategy
            
        Returns:
            Generated protein hypothesis
        """
        self.logger.info(f"Generating protein hypothesis with strategy: {strategy}")
        
        # Create protein-specific task parameters
        task_params = {
            "research_goal": research_goal,
            "protein_id": protein_id,
            "biological_context": biological_context,
            "strategy": strategy,
            "enable_bindcraft_design": "computational_design" in self.design_agents,
            "enable_md_simulation": 'molecular_dynamics' in self.design_agents,
            "computational_design": {}  # Empty dict for design config
        }
        
        # Generate base hypothesis using Jnana
        base_hypothesis = await self.generate_single_hypothesis(strategy)
        
        # Convert to protein-specific hypothesis
        protein_hypothesis = ProteinHypothesis.from_unified_hypothesis(
            base_hypothesis,
            protein_id=protein_id,
            biological_context=biological_context # this goes into `protein_metadata`
        )
        if "computational_design" in self.enable_agents:
            #I want to append design_config to the task_params
            #design_config = self.binder_config.get("agents", {}).get("computational_design", {})
            #For now design config is hardcoded
            design_config = {
                'cwd': '/eagle/FoundEpidem/avasan/Work/StructBioReasoner/data',
                'target_sequence': 'MSTGEELQK',
                'binder_sequence': 'MKQHKAMIVALIVICITAVVAALVTRKDLCEVHIRTGQTEVAVF',
                'device': 'cuda:0',
                'n_rounds': 3,
                'if_kwargs': {
                    'num_seqs': 25,
                    'batch_size': 250,
                    'max_retries': 5,
                    'sampling_temp': '0.1',
                    'model_name': 'v_48_020',
                    'model_weights': 'soluble_model_weights',
                    'proteinmpnn_path': '/eagle/FoundEpidem/avasan/Softwares/ProteinMPNN',
                },
                'qc_kwargs': {
                    'max_repeat': 4,
                    'max_appearance_ratio': 0.33,
                    'max_charge': 5,
                    'max_charge_ratio': 0.5,
                    'max_hydrophobic_ratio': 0.8,
                    'min_diversity': 8,
                    'bad_motifs': None,
                    'bad_n_termini': None
                }
                #'fold_backend': 'chai',
                #'inv_fold_backend': 'proteinmpnn'
            }

            print(design_config)

            task_params['computational_design'].update(design_config)
            
            bindcraft_analysis = await self.design_agents["computational_design"].analyze_hypothesis(
                protein_hypothesis, task_params
            )
            protein_hypothesis.add_binder_analysis(bindcraft_analysis)

        if "molecular_dynamics" in self.enable_agents:
            md_analysis = await self.design_agents['molecular_dynamics'].analyze_hypothesis(
                protein_hypothesis, task_params
            )
            protein_hypothesis.add_md_analysis(md_analysis)
        # Enhance with protein-specific analysis
        #await self._enhance_protein_hypothesis(protein_hypothesis, task_params)
        
        return protein_hypothesis
    
    async def _enhance_protein_hypothesis(self, 
                                        hypothesis: ProteinHypothesis, 
                                        task_params: Dict):
        """Enhance hypothesis with protein-specific analysis."""
        
        # Binder analysis
        if "computational_design" in self.design_agents:
            try:
                bindcraft_analysis = await self.design_agents["computational_design"].analyze_hypothesis(
                    hypothesis, task_params
                )
                hypothesis.add_binder_analysis(bindcraft_analysis)
            except Exception as e:
                self.logger.warning(f"Binder analysis failed: {e}")
        
        # MD analysis
        if "molecular_dynamics" in self.design_agents:
            try:
                md_analysis = await self.design_agents['molecular_dynamics'].analyze_hypothesis(
                    hypothesis, task_params
                )
                hypothesis.add_md_analysis(md_analysis)
            except Exception as e:
                self.logger.warning(f"MD analysis failed: {e}")
        
    def get_protein_system_status(self) -> Dict[str, Any]:
        """Get protein system status."""
        base_status = self.get_system_status()
        
        design_status = {
            "protein_system_ready": self.design_system_ready,
            "enabled_tools": list(self.design_tools.keys()),
            "enabled_agents": list(self.design_agents.keys()),
            "knowledge_graph_enabled": self.knowledge_graph_enabled,
            "literature_processing_enabled": self.literature_processing_enabled,
            "knowledge_foundation_ready": self.knowledge_foundation is not None,
            "tool_status": {name: tool.is_ready() for name, tool in self.design_tools.items()},
            "agent_status": {name: agent.is_ready() for name, agent in self.design_agents.items()}
        }
        
        return {**base_status, "computational_design": design_status}

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

        self.design_system_ready = False
        self.logger.info("BinderDesignSystem stopped")

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
