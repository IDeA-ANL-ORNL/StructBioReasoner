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

from dataclasses import dataclass, asdict, field

@dataclass
class BinderConfig:
    cwd: Path=Path('/lus/flare/projects/FoundEpidem/msinclair/github/StructBioReasoner/data'),
    target_sequence: str='MMKMEGIALKKRLSWISVCLLVLVSAAGMLFSTAAKTETSSHKAHTEAQVINTFDGVADYLQTYHKLPDNYITKSEAQALGWVASKGNLADVAPGKSIGGDIFSNREGKLPGKSGRTWREADINYTSGFRNSDRILYSSDWLIYKTTDHYQTFTKIR',
    binder_sequence: str='MKKAVINGEQIRSISDLHQTLKKELALPEYYGENLDALWDCLTGWVEYPLVLEWRQFEQSKQLTENGAESVLQVFREAKAEGCDITIILS',
    device: str='xpu',
    num_rounds: int=1,
    if_kwargs: dict[str, Any]=field(default_factory=lambda: {
        'num_seq': 10,
        'batch_size': 10,
        'max_retries': 5,
        'sampling_temp': '0.1',
        'model_name': 'v_48_020',
        'model_weights': 'soluble_model_weights',
        'proteinmpnn_path': Path('/lus/flare/projects/FoundEpidem/msinclair/pkgs/ProteinMPNN'),
    })
    qc_kwargs: dict[str, Any]=field(default_factory=lambda: {
        'max_repeat': 4,
        'max_appearance_ratio': 0.33,
        'max_charge': 10,
        'max_charge_ratio': 0.5,
        'max_hydrophobic_ratio': 0.8,
        'min_diversity': 8,
        'bad_motifs': None,
        'bad_n_termini': None
    })
    
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
        
        #self.start()
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
        
        await self._initialize_design_tools()
        await self._initialize_design_agents()

        ### If we want the llm to directly use tool calling then initialize the tool registry.
        ### Otherwise keep it false
        if False:
            await self._initialize_tool_registry()  # NEW: Initialize tool registry
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
                design_config = self.binder_config.get("agents", {}).get("computational_design", asdict(BinderConfig()))

                if 'bindcraft' in design_config:
                    kwargs = design_config['bindcraft']
                    if_kwargs = design_config['inverse_folding']
                    qc_kwargs = design_config['quality_control']
                    
                    kwargs['if_kwargs'] = if_kwargs
                    kwargs['qc_kwargs'] = qc_kwargs

                    design_config = kwargs

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

    async def _initialize_tool_registry(self):
        """
        Initialize tool registry and register BindCraft tool.

        This makes BindCraft available as a tool that LLM agents can call
        during hypothesis generation.
        """
        try:
            from jnana.tools import ToolRegistry, BindCraftTool

            # Create tool registry
            self.tool_registry = ToolRegistry()
            self.logger.info("Tool registry created")

            # Register BindCraft tool if agent is available
            if 'computational_design' in self.design_agents:
                bindcraft_agent = self.design_agents['computational_design']
                bindcraft_tool = BindCraftTool(bindcraft_agent)
                self.tool_registry.register_tool(bindcraft_tool)
                self.logger.info("✓ BindCraft tool registered for LLM use")

                # Inject tool registry into ProtoGnosis agents
                if hasattr(self, 'protognosis_adapter') and self.protognosis_adapter:
                    if hasattr(self.protognosis_adapter, 'coscientist'):
                        coscientist = self.protognosis_adapter.coscientist
                        # Agents are stored in supervisor.agents, not coscientist.agents
                        if hasattr(coscientist, 'supervisor') and hasattr(coscientist.supervisor, 'agents'):
                            # Inject into all generation agents
                            for agent_id, agent in coscientist.supervisor.agents.items():
                                if agent_id.startswith('generation'):
                                    agent.tool_registry = self.tool_registry
                                    self.logger.info(f"  - Injected tool registry into {agent_id}")

                            self.logger.info("✓ Tool registry injected into CoScientist generation agents")
            else:
                self.logger.info("BindCraft agent not available, skipping tool registration")

        except Exception as e:
            self.logger.warning(f"Failed to initialize tool registry: {e}")
            import traceback
            traceback.print_exc()

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

    def _extract_target_sequence(self, research_goal: str) -> str:
        """
        Extract target sequence from research goal text.

        Looks for patterns like:
        - "Target sequence: MKTAYIAK..."
        - "target: MKTAYIAK..."
        - Amino acid sequences in the text

        Args:
            research_goal: The research goal text

        Returns:
            Extracted target sequence or empty string if not found
        """
        import re

        # Pattern 1: Explicit "Target sequence:" or "target sequence:"
        pattern1 = r'[Tt]arget\s+[Ss]equence:\s*([A-Z]{20,})'
        match = re.search(pattern1, research_goal)
        if match:
            seq = match.group(1).strip()
            self.logger.info(f"Extracted target sequence (pattern 1): {seq[:50]}... ({len(seq)} residues)")
            return seq

        # Pattern 2: Just "target:" followed by sequence
        pattern2 = r'[Tt]arget:\s*([A-Z]{20,})'
        match = re.search(pattern2, research_goal)
        if match:
            seq = match.group(1).strip()
            self.logger.info(f"Extracted target sequence (pattern 2): {seq[:50]}... ({len(seq)} residues)")
            return seq

        # Pattern 3: Any long amino acid sequence (20+ residues)
        # Only use standard amino acid letters
        pattern3 = r'\b([ACDEFGHIKLMNPQRSTVWY]{20,})\b'
        match = re.search(pattern3, research_goal)
        if match:
            seq = match.group(1).strip()
            self.logger.info(f"Extracted target sequence (pattern 3): {seq[:50]}... ({len(seq)} residues)")
            return seq

        # If no sequence found, log warning
        self.logger.warning("No target sequence found in research goal")
        return ""

    def _extract_binder_sequence(self, research_goal: str) -> str:
        """
        Extract binder sequence from research goal text (optional).

        Looks for patterns like:
        - "Binder sequence: MKTAYIAK..."
        - "binder: MKTAYIAK..."

        Args:
            research_goal: The research goal text

        Returns:
            Extracted binder sequence or empty string if not found
        """
        import re

        # Pattern 1: Explicit "Binder sequence:" or "binder sequence:"
        pattern1 = r'[Bb]inder\s+[Ss]equence:\s*([A-Z]{10,})'
        match = re.search(pattern1, research_goal)
        if match:
            seq = match.group(1).strip()
            self.logger.info(f"Extracted binder sequence: {seq[:50]}... ({len(seq)} residues)")
            return seq

        # Pattern 2: Just "binder:" followed by sequence
        pattern2 = r'[Bb]inder:\s*([A-Z]{10,})'
        match = re.search(pattern2, research_goal)
        if match:
            seq = match.group(1).strip()
            self.logger.info(f"Extracted binder sequence: {seq[:50]}... ({len(seq)} residues)")
            return seq

        # No binder sequence found (this is optional)
        return ""

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

        # STEP 1: Extract target and binder sequences from research goal
        target_sequence = self._extract_target_sequence(research_goal)
        binder_sequence = self._extract_binder_sequence(research_goal)

        # STEP 1b: Fallback to config defaults if extraction failed
        if not target_sequence:
            # Try to get from binder_config
            config_defaults = self.binder_config.get("agents", {}).get("computational_design", {})
            if isinstance(config_defaults, dict):
                target_sequence = config_defaults.get("target_sequence", "")
            if not target_sequence and hasattr(BinderConfig, 'target_sequence'):
                # Use BinderConfig dataclass default
                default_config = BinderConfig()
                target_sequence = default_config.target_sequence
                self.logger.info(f"Using default target sequence from BinderConfig ({len(target_sequence)} residues)")

        if not binder_sequence:
            # Try to get from binder_config
            config_defaults = self.binder_config.get("agents", {}).get("computational_design", {})
            if isinstance(config_defaults, dict):
                binder_sequence = config_defaults.get("binder_sequence", "")
            if not binder_sequence and hasattr(BinderConfig, 'binder_sequence'):
                # Use BinderConfig dataclass default
                default_config = BinderConfig()
                binder_sequence = default_config.binder_sequence
                self.logger.info(f"Using default binder sequence from BinderConfig ({len(binder_sequence)} residues)")

        # STEP 2: Set research_plan_config in GenerationAgent's memory
        # This ensures the LLM receives the target sequence in its prompt
        if hasattr(self, 'protognosis_adapter') and self.protognosis_adapter:
            if hasattr(self.protognosis_adapter, 'coscientist') and self.protognosis_adapter.coscientist:
                coscientist = self.protognosis_adapter.coscientist
                # Agents are stored in supervisor.agents, not coscientist.agents
                if hasattr(coscientist, 'supervisor') and hasattr(coscientist.supervisor, 'agents'):
                    # Get all generation agents from supervisor
                    generation_agents = [agent for agent_id, agent in coscientist.supervisor.agents.items()
                                       if agent_id.startswith('generation')]
                    if generation_agents:
                        # Set research_plan_config in ALL generation agents' memory
                        research_plan_config = {
                            'target_sequence': target_sequence,
                            'binder_sequence': binder_sequence,
                            'task_type': 'binder_design'
                        }
                        for gen_agent in generation_agents:
                            if hasattr(gen_agent, 'memory') and gen_agent.memory:
                                gen_agent.memory.metadata['research_plan_config'] = research_plan_config
                        self.logger.info(f"✓ Set research_plan_config in {len(generation_agents)} generation agents with target sequence ({len(target_sequence)} residues)")
                    else:
                        self.logger.warning("No generation agents found in supervisor")
                else:
                    self.logger.warning("CoScientist does not have supervisor.agents")
            else:
                self.logger.warning("ProtoGnosis adapter does not have coscientist")
        else:
            self.logger.warning("Could not access protognosis_adapter to set research_plan_config")

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

        # STEP 3: Generate base hypothesis using Jnana (now with target sequence in config)
        base_hypothesis = await self.generate_single_hypothesis(strategy)

        # Convert to protein-specific hypothesis
        protein_hypothesis = ProteinHypothesis.from_unified_hypothesis(
            base_hypothesis,
            biological_context=biological_context # this goes into `protein_metadata`
        )
        if "computational_design" in self.enable_agents:
            #I want to append design_config to the task_params
            design_config = self.binder_config.get("agents", {}).get("computational_design", asdict(BinderConfig()))

            if 'bindcraft' in design_config:
                kwargs = design_config['bindcraft']
                if_kwargs = design_config['inverse_folding']
                qc_kwargs = design_config['quality_control']

                kwargs['if_kwargs'] = if_kwargs
                kwargs['qc_kwargs'] = qc_kwargs

                design_config = kwargs

            # CRITICAL FIX: Extract sequences from the hypothesis and add to design_config
            # This ensures BindCraft uses the LLM-generated sequences, not config defaults
            if protein_hypothesis.has_binder_data() and protein_hypothesis.binder_data:
                binder_data = protein_hypothesis.binder_data

                # Override design_config with sequences from hypothesis
                if binder_data['target_sequence'] and binder_data['target_sequence'] != "UNKNOWN":
                    design_config['target_sequence'] = binder_data.target_sequence
                    self.logger.info(f"Adding target sequence from hypothesis to design_config: {binder_data.target_sequence[:50]}...")

                # Get binder sequence from proposed peptides
                if binder_data['proposed_peptides'] and len(binder_data['proposed_peptides']) > 0:
                    first_peptide = binder_data['proposed_peptides'][0]
                    if isinstance(first_peptide, dict) and 'sequence' in first_peptide:
                        design_config['binder_sequence'] = first_peptide['sequence']
                        self.logger.info(f"Adding binder sequence from hypothesis to design_config: {first_peptide['sequence'][:50]}...")
            else:
                self.logger.warning("Hypothesis does not have binder_data! Using config defaults for sequences.")

            task_params['computational_design'].update(design_config)

            print("Running BINDDDDCRAFFFFFTTTTTT DIREEECCCTTTLLLY")
            if False:
                bindcraft_analysis = await self.design_agents["computational_design"].analyze_hypothesis(
                    protein_hypothesis, design_config
                )
                protein_hypothesis.add_binder_analysis(bindcraft_analysis)

        if False:
            if "molecular_dynamics" in self.enable_agents:
                md_analysis = await self.design_agents['molecular_dynamics'].analyze_hypothesis(
                    protein_hypothesis, task_params
                )
                protein_hypothesis.add_md_analysis(md_analysis)
        
        return protein_hypothesis
    
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
