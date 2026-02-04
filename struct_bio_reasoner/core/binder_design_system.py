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
import json
# Import Jnana components
import sys
sys.path.append(str(Path(__file__).parent.parent.parent.parent / "Jnana"))

from jnana.core.jnana_system import JnanaSystem
from jnana.protognosis.core.agent_core import ContextMemory 
from struct_bio_reasoner.utils.llm_interface import alcfLLM
# Import protein-specific components
from ..data.protein_hypothesis import ProteinHypothesis
from ..agents.analysis.trajectory_analysis import TrajectoryAnalysisAgent
from ..agents.computational_design.bindcraft_agent import BindCraftAgent
from ..agents.molecular_dynamics.mdagent_adapter import MDAgentAdapter
from ..agents.molecular_dynamics.free_energy_agent import FEAgent
from ..agents.structure_prediction.chai_agent import ChaiAgent
from ..agents.analysis.trajectory_analysis import TrajectoryAnalysisAgent
from ..agents.language_model.jnana_agent import JnanaWrapper
from ..prompts.prompts import get_prompt_manager
try:
    from ..agents.hiper_rag.rag_agent import RAGWrapper 
    RAG_EXISTS=True
except Exception as e:
    print("RAG not working because:")
    print(e)
    import traceback
    traceback.print_exc()
    RAG_EXISTS=False

from ..utils.config_loader import load_binder_config
from .knowledge_foundation import ProteinKnowledgeFoundation
import os

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
    memory: ContextMemory=field(default_factory=lambda: ContextMemory())

class BinderDesignSystem():
    """
    Main binder design system extending Jnana.
    
    This system combines Jnana's hypothesis generation and multi-agent
    capabilities with protein-specific tools, agents, and knowledge systems.
    """
    
    def __init__(self, 
                 config_path: Union[str, Path] = "config/binder_config.yaml",
                 research_goal: str = "Design a binder for SARS-CoV-2 spike protein RBD.",
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
        self.memory_binder = ContextMemory()
        self.memory_binder.set_research_goal(research_goal, research_plan='')
        self.research_goal = research_goal
        self.binder_config = load_binder_config(config_path)
        self.global_cwd = self.binder_config.get("agents").get("computational_design").get("bindcraft").get("cwd")
        self.parsl_config = self.binder_config['parsl']
        
        # Determine Jnana config path
        if not jnana_config_path:
            jnana_config_path = self.binder_config.get("jnana", {}).get("config_path", "./config/jnana.yaml")
        
        # Handle Biomni configuration by modifying the Jnana config if needed
        self._prepare_jnana_config(jnana_config_path)

        # Initialize base Jnana system
        #super().__init__(
        #    config_path=jnana_config_path,
        #    **kwargs
        #)
        
        # Protein-specific configuration
        self.enable_tools = enable_tools or []
        self.enable_agents = enable_agents or ['computational_design', 'molecular_dynamics', 'analysis', 'structure_prediction', 'rag', 'free_energy']
        self.knowledge_graph_enabled = knowledge_graph
        self.literature_processing_enabled = literature_processing
        
        # Initialize design-specific components
        self.design_tools = {}
        self.design_agents = {}
        self.knowledge_foundation = None

        # System state
        self.design_system_ready = False
        self.history = {}
        self.history['key_items'] = []
        self.history['decisions'] = []
        self.history['configurations'] = []
        self.history['results'] = []
        self.history['recommendations'] = []
        self.num_history = self.binder_config['history']['num_history']
        #self.start()
        self.logger.info("BinderDesignSystem initialized")

    def append_history(self, key_items: object| None = None,
                             decision: str|None = None,
                             configuration: dict[str, Any] | None = None, 
                             results: dict[str, Any]|None = None,
                             recommendations: dict[str, Any]|object|None = None):
        if key_items is not None:
            self.history['key_items'].append(key_items)
        if recommendations is not None:
            self.history['recommendations'].append(recommendations)
        elif recommendations is None:
            self.history['recommendations'].append('No recommendation')
        if decision is not None:
            self.history['decisions'].append(decision)
        elif decision is None:
            self.history['decisions'].append('No decision')
        if configuration is not None:
            try:
                configuration = json.dumps(configuration)
            except Exception as e:
                self.logger.debug(e)
                configuration = configuration.__dict__
                configuration = json.dumps(configuration)

            max_length = 500
            configuration = configuration[:max_length]
            self.history['configurations'].append(configuration)
        elif configuration is None:
            self.history['configurations'].append('No configuration')
        if results is not None:
            try:
                results = json.dumps(results)
            except Exception as e:
                self.logger.debug(e)
                results = results.__dict__
                results = json.dumps(results)
            max_length = 500
            results = results[:max_length]
            self.history['results'].append(results)
        elif results is None:
            self.history['results'].append('No results')

        if len(self.history['decisions']) > self.num_history:
            self.history['decisions'].pop(0)
        if len(self.history['configurations']) > self.num_history:
            self.history['configurations'].pop(0)
        if len(self.history['results']) > self.num_history:
            self.history['results'].pop(0)

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
        #await super().start()

        # Initialize design-specific components
        
        self._extract_target_sequence(self.research_goal)
        await self._initialize_design_agents()
        await self._initialize_jnana_agent()
        await self._initialize_knowledge_foundation()

        self.design_system_ready = True
        self.logger.info("BinderDesignSystem started successfully")
    
    async def _initialize_jnana_agent(self):
        self.logger.info("Initializing LLM agent")
        jnana_ag_config = self.binder_config.get('jnana', {})
        self.jnana_agent = JnanaWrapper(
                            agent_id = 'jnana',
                            config = jnana_ag_config,
                            research_goal = self.research_goal,
                            enabled_agents = self.enable_agents,
                            target_prot = self.target_prot)

    async def _initialize_design_agents(self):
        """Initialize protein-specific agents."""
        self.logger.info("Initializing protein agents...")
        
        # Get agent configurations
        agent_configs = self.binder_config.get("agents", {})
        
        # Initialize structural analysis agent
        if 'computational_design' in self.enable_agents:
            try:

                os.makedirs(f'{self.global_cwd}/computational_design', exist_ok = True)
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
                                                                model_manager=self.model_manager,
                                                                parsl_config = self.parsl_config
                                                                )
                #print(self.design_agents)
                self.logger.info("BindCraft agent initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize BindCraft agent: {e}")
        
        # Initialize molecular dynamics agent
        if "molecular_dynamics" in self.enable_agents:
            try:
                md_config = agent_configs.get("molecular_dynamics", {})
                os.makedirs(f'{self.global_cwd}/molecular_dynamics', exist_ok = True)

                self.design_agents['molecular_dynamics'] = MDAgentAdapter(
                    agent_id="molecular_dynamics",
                    config=md_config,
                    parsl_config = self.parsl_config
                )
                self.logger.info("MD agent initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize MD agent: {e}")

            if 'free_energy' in self.enable_agents:
                try:
                    os.makedirs(f'{self.global_cwd}/free_energy', exist_ok = True)
                    self.design_agents['free_energy'] = FEAgent(
                        agent_id='free_energy',
                        config=md_config,
                        parsl_config = self.parsl_config,
                    )

                except Exception as e:
                    self.logger.warning(f'Failed to initialize FE agent: {e}')

        # Initialize molecular dynamics agent
        if "rag" in self.enable_agents:
            if RAG_EXISTS:
                try:
                    rag_config = agent_configs["rag"]#.get("rag", {})
                    os.makedirs(f'{self.global_cwd}/rag', exist_ok = True)
                    self.logger.info(rag_config)
                    self.design_agents['rag'] = RAGWrapper(
                        agent_id="rag",
                        config=rag_config,
                        model_manager = self.model_manager
                    )
                    #await self.design_agents['rag'].initialize()
                    self.logger.info("RAG agent initialized")
                except Exception as e:
                    self.logger.warning(f"Failed to initialize RAG agent: {e}")

            else:
                self.logger.warning("distllm is not installed, not using RAG")

        if 'structure_prediction' in self.enable_agents:
            try:
                pred_config = agent_configs.get('structure_prediction', {})
                os.makedirs(f'{self.global_cwd}/structure_prediction', exist_ok = True)
                self.design_agents['structure_prediction'] = ChaiAgent(
                    agent_id='structure_prediction',
                    config=pred_config,
                    parsl_config=self.parsl_config,
                )
            except Exception as e:
                self.logger.warning(f'Failed to initialize structure prediction agent: {e}')

        if 'analysis' in self.enable_agents:
            try:
                os.makedirs(f'{self.global_cwd}/analysis', exist_ok = True)
                self.design_agents['analysis'] = TrajectoryAnalysisAgent(
                    agent_id='analysis',
                    config={}, # no global config
                    parsl_config=self.parsl_config,
                )
            except Exception as e:
                self.logger.warning(f'Failed to initialize analysis agent: {e}')
        
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
            self.target_prot=seq
            return seq

        # Pattern 2: Just "target:" followed by sequence
        pattern2 = r'[Tt]arget:\s*([A-Z]{20,})'
        match = re.search(pattern2, research_goal)
        if match:
            seq = match.group(1).strip()
            self.logger.info(f"Extracted target sequence (pattern 2): {seq[:50]}... ({len(seq)} residues)")
            self.target_prot=seq
            return seq

        # Pattern 3: Any long amino acid sequence (20+ residues)
        # Only use standard amino acid letters
        pattern3 = r'\b([ACDEFGHIKLMNPQRSTVWY]{20,})\b'
        match = re.search(pattern3, research_goal)
        if match:
            seq = match.group(1).strip()
            self.logger.info(f"Extracted target sequence (pattern 3): {seq[:50]}... ({len(seq)} residues)")
            self.target_prot=seq
            return seq

        # If no sequence found, log warning
        self.logger.warning("No target sequence found in research goal")
        self.target_prot=""
        return ""

    def _extract_target_name(self, research_goal: str) -> str:
        """
        Extract target name from research goal text.

        Looks for patterns like:
        - "Target name: NMNAT-2"
        - "target: MKTAYIAK..."
        - Amino acid sequences in the text

        Args:
            research_goal: The research goal text

        Returns:
            Extracted target name or empty string if not found
        """
        import re

        # Pattern 1: Explicit "Target sequence:" or "target sequence:"
        pattern1 = r'[Tt]arget\s+[Nn]ame:\s*([A-Z]{26,})'
        match = re.search(pattern1, research_goal)
        if match:
            seq = match.group(1).strip()
            self.logger.info(f"Extracted target name (pattern 1): {seq[:50]}...")
            self.target_prot_name=seq
            return seq

        # Pattern 2: Just "target:" followed by sequence
        pattern2 = r'[Tt]arget:\s*([A-Z]{20,})'
        match = re.search(pattern2, research_goal)
        if match:
            seq = match.group(1).strip()
            self.logger.info(f"Extracted target sequence (pattern 2): {seq[:50]}... ({len(seq)} residues)")
            self.target_prot_name=seq
            return seq

        # Pattern 3: Any long amino acid sequence (20+ residues)
        # Only use standard amino acid letters
        pattern3 = r'\b([ABCDEFGHIJKLMNOPQRSTUVWXYZ]{20,})\b'
        match = re.search(pattern3, research_goal)
        if match:
            seq = match.group(1).strip()
            self.logger.info(f"Extracted target sequence (pattern 3): {seq[:50]}... ({len(seq)} residues)")
            self.target_prot_name=seq
            return seq

        # If no sequence found, log warning
        self.logger.warning("No target name found in research goal")
        self.target_prot_name=""
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
                    design_config['target_sequence'] = binder_data['target_sequence']
                    self.logger.info(f"Adding target sequence \
                                        from hypothesis to design_config:\
                                        {binder_data['target_sequence'][:50]}...")

                # Get binder sequence from proposed peptides
                if binder_data['proposed_peptides'] and len(binder_data['proposed_peptides']) > 0:
                    first_peptide = binder_data['proposed_peptides'][0]
                    if isinstance(first_peptide, dict) and 'sequence' in first_peptide:
                        design_config['binder_sequence'] = first_peptide['sequence']
                        self.logger.info(f"Adding binder sequence"+\
                                        f"from hypothesis to design_config:"+\
                                        f"{first_peptide['sequence'][:50]}...")
            else:
                self.logger.warning("Hypothesis doesnt have binder_data! config default seqs.")

            task_params['computational_design'].update(design_config)

        
        return protein_hypothesis
    
    async def generate_recommendation(self,
                                      results,
                                      runtype='bindcraft'
                                        ):
        """
        Generate a protein-specific hypothesis.

        Args:
            results
        Returns:
            Generated recommendation
        """
        #self.logger.info(f"Generating protein hypothesis with strategy: {strategy}")
        if runtype == 'molecular_dynamics':
            prompt_type = 'binder_design'
        else:
            prompt_type = 'conclusion'

        prompt_manager = get_prompt_manager(
                agent_type=runtype,
                research_goal=self.research_goal,
                input_json=results,
                target_prot=self.target_prot,
                prompt_type=prompt_type,
                history=self.history,
                num_history=self.num_history
                )
        prompt_manager.conclusion_prompt()
        #conclusion = f"After running bindcraft {results.num_rounds} rounds and generating {results.total_sequences} sequences total, {results.passing_structures} structures pass sequence and structure quality control. I want at least 200 passing structures before going to md simulations"
        self.logger.info(f"Conclusion after running {runtype}: {prompt_manager.prompt_c}")
        results_pass = {'run_type': runtype,
                        'run_conc': prompt_manager.prompt_c}
        recommendation = await self.generate_single_recommendation(results_pass)
        self.logger.info(f"Here is the protein recommendation: \n {[rec.to_dict() for rec in recommendation]}")
        self.append_history(recommendations=recommendation)
        recommendation[0].metadata['history'] = self.history
        recommendation[0].metadata['num_history'] = self.num_history
        #protein_recommendation = ProteinHypothesis.from_unified_hypothesis(
        #    recommendation,
        #    #biological_context=biological_context # this goes into `protein_metadata`
        #)
        
        return [rec.to_dict() for rec in recommendation] #protein_recommendation

    async def generate_recommendedconfig(self,
                                      previous_run_type,
                                      previous_run_config,
                                      recommendation,
                                        ):
        """
        Generate a protein-specific hypothesis.

        Args:
            results
        Returns:
            Generated recommendation
        """
        previous_run = {'run_type': previous_run_type,
                        'config': previous_run_config}
        recommended_configs = await self.generate_single_recommend_config(previous_run,
                        recommendation)
        self.logger.info(f"Here is the recommended config: \n {[rec.to_dict() for rec in recommended_configs]}")
        
        return [rec.to_dict() for rec in recommended_configs] #protein_recommendation


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
