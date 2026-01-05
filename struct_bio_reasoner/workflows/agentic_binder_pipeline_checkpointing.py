"""
Agentic Binder Design Pipeline with Checkpointing

A checkpointing-enabled version of the agentic workflow for designing
biologic binders using LLM-guided decision-making.

Features:
- Automatic checkpointing at configurable intervals
- Resume from checkpoint capability
- Saves all relevant state (hypothesis, history, results, configs)

Workflow:
1. Initialize system and set research goal (or load from checkpoint)
2. Agentic loop:
   - LLM reasoner recommends next task (BindCraft/MD/Stop)
   - Generate recommended configuration
   - Execute task
   - Evaluate results
   - Save checkpoint
3. Generate final report with best binders

Author: StructBioReasoner Team
Date: 2025-12-26
"""

import sys
import asyncio
import logging
import json
import argparse
import dill as pickle
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from types import SimpleNamespace
import wandb

from jnana.protognosis.core.llm_interface import alcfLLM
from ..core.binder_design_system import BinderDesignSystem
from ..data.protein_hypothesis import ProteinHypothesis
from ..prompts.prompts import get_prompt_manager, config_master
from ..utils.uniprot_api import fetch_uniprot_sequence
from ..utils.hotspot import get_hotspot_resids_from_simulations
from ..utils.protein_utils import pdb2seq
#from ..utils.metric_eval import MetricEvaluator


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logging.getLogger('parsl').propagate = False

logger = logging.getLogger(__name__)


class PipelineCheckpoint:
    """Container for pipeline checkpoint data."""
    
    def __init__(
        self,
        iteration: int,
        hypothesis: ProteinHypothesis,
        research_goal: str,
        hotspot_residues: List[int],
        target_sequence: str,
        session_id: str,
        all_binders: List[Any],
        best_binders: List[Any],
        comp_design_it: int,
        previous_task: Optional[str],
        previous_config: Optional[Dict[str, Any]],
        previous_results: Optional[Dict[str, Any]],
        history: List[Any],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize checkpoint.
        
        Args:
            iteration: Current iteration number
            hypothesis: ProteinHypothesis object
            research_goal: The research goal
            hotspot_residues: List of hotspot residue indices
            target_sequence: Target protein sequence
            session_id: Session ID
            all_binders: List of all binders generated
            best_binders: List of best binders
            comp_design_it: Computational design iteration count
            previous_task: Previous task name
            previous_config: Previous task configuration
            previous_results: Previous task results
            history: System history
            metadata: Additional metadata
        """
        self.iteration = iteration
        self.hypothesis = hypothesis
        self.research_goal = research_goal
        self.hotspot_residues = hotspot_residues
        self.target_sequence = target_sequence
        self.session_id = session_id
        self.all_binders = all_binders
        self.best_binders = best_binders
        self.comp_design_it = comp_design_it
        self.previous_task = previous_task
        self.previous_config = previous_config
        self.previous_results = previous_results
        self.history = history
        self.metadata = metadata or {}
        self.timestamp = datetime.now().isoformat()
    
    def save(self, filepath: Path) -> None:
        """Save checkpoint to file."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'wb') as f:
            pickle.dump(self, f)
        logger.info(f"💾 Checkpoint saved: {filepath}")
    
    @classmethod
    def load(cls, filepath: Path) -> 'PipelineCheckpoint':
        """Load checkpoint from file."""
        with open(filepath, 'rb') as f:
            checkpoint = pickle.load(f)
        logger.info(f"📂 Checkpoint loaded: {filepath}")
        return checkpoint


class AgenticBinderPipelineWithCheckpointing:
    """
    Agentic pipeline for iterative binder design with checkpointing support.
    """
    
    def __init__(
        self,
        config_path: str = "config/binder_config.yaml",
        jnana_config_path: str = "config/jnana_config.yaml",
        max_iterations: int = 1_000_000_000,
        enable_agents: Optional[List[str]] = None,
        checkpoint_dir: str = "checkpoints",
        checkpoint_interval: int = 1,
        wandb_project ='binder_design',
        wandb_name = 'nmnat2_test'
    ):
        """
        Initialize the agentic binder design pipeline with checkpointing.

        Args:
            config_path: Path to binder configuration file
            jnana_config_path: Path to Jnana configuration file
            max_iterations: Maximum number of design iterations
            enable_agents: List of agents to enable
            checkpoint_dir: Directory to save checkpoints
            checkpoint_interval: Save checkpoint every N iterations (default: 1)
        """
        self.config_path = config_path
        self.jnana_config_path = jnana_config_path
        self.max_iterations = max_iterations
        self.enable_agents = enable_agents or [
            'computational_design',
            'molecular_dynamics',
            'rag',
            'structure_prediction',
            'analysis',
            'free_energy'
        ]
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_interval = checkpoint_interval

        self.system: Optional[BinderDesignSystem] = None
        self.session_id: Optional[str] = None
        self.target_sequence: Optional[str] = None
        self.global_cwd: Optional[str] = None
        self.research_goal: Optional[str] = None

        # Tracking variables
        self.all_binders = []
        self.best_binders = []
        self.iteration_count = 0
        self.comp_design_it = 0
        
        # In __init__():
        #self.metric_evaluator = MetricEvaluator(
        #        project_name=wandb_project,
        #        run_name=f"exp_{wandb_name}{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        #    )
    async def initialize(self, research_goal: str) -> None:
        """
        Initialize the binder design system and set research goal.

        Args:
            research_goal: The research goal describing the binder design task
        """
        logger.info("="*80)
        logger.info("AGENTIC BINDER DESIGN PIPELINE (WITH CHECKPOINTING)")
        logger.info("="*80)
        logger.info("\n[INITIALIZATION] Setting up BinderDesignSystem...")

        # Initialize system
        self.system = BinderDesignSystem(
            config_path=self.config_path,
            jnana_config_path=self.jnana_config_path,
            enable_agents=self.enable_agents
        )

        self.system.prompt_gen_llm = alcfLLM()
        await self.system.start()

        logger.info(f'design agents allowed : {self.system.design_agents}')
        # Set research goal
        self.research_goal = research_goal
        self.session_id = await self.system.set_research_goal(research_goal)
        self.target_sequence = self.system._extract_target_sequence(research_goal)

        # Get global working directory
        self.global_cwd = self.system.binder_config.get("agents", {}).get(
            "computational_design", {}
        ).get("bindcraft", {}).get("cwd")

        logger.info(f"✓ System initialized (session: {self.session_id})")
        logger.info(f"✓ Target sequence extracted ({len(self.target_sequence)} residues)")
        logger.info(f"✓ Checkpoints will be saved to: {self.checkpoint_dir}")
        logger.info(f"✓ Checkpoint interval: every {self.checkpoint_interval} iteration(s)")

    def _create_checkpoint(
        self,
        iteration: int,
        hypothesis: ProteinHypothesis,
        hotspot_residues: List[int],
        previous_task: Optional[str] = None,
        previous_config: Optional[Dict[str, Any]] = None,
        previous_results: Optional[Dict[str, Any]] = None
    ) -> PipelineCheckpoint:
        """
        Create a checkpoint of the current pipeline state.

        Args:
            iteration: Current iteration number
            hypothesis: ProteinHypothesis object
            hotspot_residues: List of hotspot residue indices
            previous_task: Previous task name
            previous_config: Previous task configuration
            previous_results: Previous task results

        Returns:
            PipelineCheckpoint object
        """
        return PipelineCheckpoint(
            iteration=iteration,
            hypothesis=hypothesis,
            research_goal=self.research_goal,
            hotspot_residues=hotspot_residues,
            target_sequence=self.target_sequence,
            session_id=self.session_id,
            all_binders=self.all_binders.copy(),
            best_binders=self.best_binders.copy(),
            comp_design_it=self.comp_design_it,
            previous_task=previous_task,
            previous_config=previous_config,
            previous_results=previous_results,
            history=self.system.history.copy() if self.system else [],
            metadata={
                'global_cwd': self.global_cwd,
                'max_iterations': self.max_iterations
            }
        )

    def _save_checkpoint(
        self,
        checkpoint: PipelineCheckpoint,
        name: Optional[str] = None
    ) -> Path:
        """
        Save checkpoint to disk.

        Args:
            checkpoint: PipelineCheckpoint object
            name: Optional custom name for checkpoint file

        Returns:
            Path to saved checkpoint file
        """
        if name is None:
            name = f"checkpoint_iter_{checkpoint.iteration:04d}.pkl"

        filepath = self.checkpoint_dir / name
        checkpoint.save(filepath)

        # Also save a "latest" checkpoint for easy resuming
        latest_path = self.checkpoint_dir / "checkpoint_latest.pkl"
        checkpoint.save(latest_path)

        return filepath

    async def _restore_from_checkpoint(self, checkpoint: PipelineCheckpoint) -> Tuple[ProteinHypothesis, List[int], Optional[str], Optional[Dict], Optional[Dict]]:
        """
        Restore pipeline state from checkpoint.

        Args:
            checkpoint: PipelineCheckpoint object

        Returns:
            Tuple of (hypothesis, hotspot_residues, previous_task, previous_config, previous_results)
        """
        logger.info("\n" + "="*80)
        logger.info("RESTORING FROM CHECKPOINT")
        logger.info("="*80)
        logger.info(f"Checkpoint iteration: {checkpoint.iteration}")
        logger.info(f"Checkpoint timestamp: {checkpoint.timestamp}")

        # Restore tracking variables
        self.all_binders = checkpoint.all_binders.copy()
        self.best_binders = checkpoint.best_binders.copy()
        self.iteration_count = checkpoint.iteration
        self.comp_design_it = checkpoint.comp_design_it
        self.research_goal = checkpoint.research_goal
        self.target_sequence = checkpoint.target_sequence
        self.session_id = checkpoint.session_id
        self.global_cwd = checkpoint.metadata.get('global_cwd')

        # Initialize system with the research goal
        await self.initialize(checkpoint.research_goal)

        # Restore history
        self.system.history = checkpoint.history.copy()

        logger.info(f"✓ Restored {len(self.all_binders)} binders")
        logger.info(f"✓ Restored {len(self.best_binders)} best binders")
        logger.info(f"✓ Restored {len(self.system.history)} history entries")
        logger.info(f"✓ Resuming from iteration {checkpoint.iteration + 1}")

        return (
            checkpoint.hypothesis,
            checkpoint.hotspot_residues,
            checkpoint.previous_task,
            checkpoint.previous_config,
            checkpoint.previous_results
        )

    async def discover_hotspots(
        self,
        research_goal: str,
        target_prot_name: str = 'NMNAT-2',
        use_actual_hotspot_analysis: bool = False
    ) -> List[int]:
        """
        Discover binding hotspots using RAG → Folding → MD → Hotspot analysis.

        This method implements the full pipeline:
        1. HiPerRAG to find interacting proteins
        2. Fetch sequences from UniProt
        3. Fold structures with Chai
        4. Run MD simulations
        5. Analyze hotspots from MD trajectories

        Args:
            research_goal: The research goal
            target_prot_name: Name of target protein for prompts
            use_actual_hotspot_analysis: If True, use actual hotspot analysis from MD
                                         If False, use LLM to suggest hotspots

        Returns:
            List of hotspot residue indices
        """
        logger.info("\n" + "="*80)
        logger.info("HOTSPOT DISCOVERY PIPELINE")
        logger.info("="*80)

        # Step 1: HiPerRAG to find interacting proteins
        logger.info("\n[STEP 1] Using HiPerRAG to find interacting proteins...")

        interactome_rag_prompt_manager = get_prompt_manager(
            'rag',
            research_goal,
            {},
            target_prot=target_prot_name,
            prompt_type='interactome',
            history_list=[],
            num_history=3
        )

        rag_prompt = self.system.prompt_gen_llm.generate(
            prompt=interactome_rag_prompt_manager.prompt_r,
            temperature=0.3,
            max_tokens=32678
        )

        rag_hypothesis = await self.system.design_agents['rag'].generate_rag_hypothesis(
            {'prompt': rag_prompt}
        )
        self.system.append_history(key_items=rag_hypothesis, decision='rag')

        logger.info(f"RAG hypothesis generated")

        # Step 2: Extract interacting proteins and get sequences
        logger.info("\n[STEP 2] Extracting interacting proteins and sequences...")

        interactome_rag_prompt_manager.input_json = rag_hypothesis
        conclusion_prompt = interactome_rag_prompt_manager.conclusion_prompt()

        mdinput = {}
        mdinput['simulation_paths'] = []

        # Loop until we get valid simulation paths
        while mdinput['simulation_paths'] == []:
            rag_result_json = self.system.prompt_gen_llm.generate_with_json_output(
                prompt=conclusion_prompt,
                json_schema=config_master['rag_output'],
                temperature=0.3,
                max_tokens=32678
            )[0]

            # Fetch sequences from UniProt
            logger.info(f"Fetching sequences for {len(rag_result_json['interacting_protein_uniprot_ids'])} proteins...")
            sequences = [
                await fetch_uniprot_sequence(id)
                for id in rag_result_json['interacting_protein_uniprot_ids']
            ]
            rag_result_json['sequences'] = [s['sequence'] for s in sequences]

            # Step 3: Fold structures with Chai
            logger.info("\n[STEP 3] Folding structures with Chai...")

            folding_prompt_manager = get_prompt_manager(
                'chai',
                research_goal,
                rag_result_json,
                target_prot=self.target_sequence,
                prompt_type='running',
                history_list=[],
                num_history=3
            )

            folding_input = self.system.prompt_gen_llm.generate_with_json_output(
                prompt=folding_prompt_manager.prompt_r,
                json_schema=config_master['structure_prediction'],
                temperature=0.3,
                max_tokens=32678
            )[0]

            # Execute Chai folding
            folding_output = await self.system.design_agents['structure_prediction'].analyze_hypothesis(
                rag_hypothesis,
                folding_input
            )

            logger.info("✓ Folding completed")

            # Step 4: Prepare MD input
            logger.info("\n[STEP 4] Preparing MD simulation input...")

            folding_prompt_manager.input_json = folding_output
            folding_conclusion = folding_prompt_manager.conclusion_prompt()
            mdinput = self.system.prompt_gen_llm.generate_with_json_output(
                prompt=folding_conclusion,
                json_schema=config_master['molecular_dynamics'],
                temperature=0.3,
                max_tokens=32678
            )[0]

        # Step 5: Run MD simulations
        logger.info("\n[STEP 5] Running MD simulations...")
        logger.info(f"MD input: {mdinput}")

        md_output = await self.system.design_agents['molecular_dynamics'].analyze_hypothesis(
            rag_hypothesis,
            mdinput
        )

        logger.info("✓ MD simulations completed")

        # Step 6: Analyze hotspots
        logger.info("\n[STEP 6] Analyzing binding hotspots...")

        md_prompt_manager = get_prompt_manager(
            'mdagent',
            research_goal,
            md_output,
            target_prot=self.target_sequence,
            prompt_type='interactome_simulation',
            history_list=self.system.history,
            num_history=3
        )

        md_conclusion = md_prompt_manager.prompt_c
        hotspot_input = self.system.prompt_gen_llm.generate_with_json_output(
            prompt=md_conclusion,
            json_schema=config_master['hotspot'],
            temperature=0.3,
            max_tokens=32678
        )[0]

        logger.info(f"Hotspot input: {hotspot_input}")

        # Get hotspot residues
        if use_actual_hotspot_analysis and 'simulation_directories' in hotspot_input:
            # Use actual MD trajectory analysis
            logger.info("Using actual hotspot analysis from MD trajectories...")
            hotspot_output = get_hotspot_resids_from_simulations(
                hotspot_input['simulation_directories'],
                top_n=10,
                selection1="protein and segid A",
                selection2="protein and segid B"
            )
        else:
            # Use LLM-suggested hotspots from the analysis
            logger.info("Using LLM-suggested hotspots...")
            hotspot_output = hotspot_input

        hotspot_residues = hotspot_output.get('hotspot_residues', [])

        logger.info(f"✓ Discovered {len(hotspot_residues)} hotspot residues: {hotspot_residues}")

        # Append to history
        self.system.append_history(key_items=hotspot_output)

        return hotspot_residues

    async def run_first_iteration(
        self,
        hypothesis: ProteinHypothesis,
        starting_binder: str = 'VDNKFNKEQQNAFYEILHLPNLNEEQRNAFIQSLKDDPSQSANLLAEAKKLNDAQAPK'
    ) -> Dict[str, Any]:
        """
        Run the first iteration with hardcoded computational_design task.

        Args:
            hypothesis: The protein hypothesis object
            starting_binder: Initial binder scaffold sequence (default: affibody)

        Returns:
            Dictionary containing task results and configuration
        """
        logger.info("\n" + "="*80)
        logger.info("ITERATION 1 (Initial Design)")
        logger.info("="*80)
        logger.info("\n[Iteration 0] Starting with computational_design (BindCraft)")

        # Get default configuration
        current_config = self.system.binder_config.get("agents", {}).get(
            "computational_design", {}
        ).get("bindcraft", {}).copy()

        current_config['binder_sequence'] = starting_binder
        current_config['target_sequence'] = self.target_sequence

        logger.info(f"Using starting binder: {starting_binder[:50]}...")

        # Generate initial recommendation
        previous_task = 'computational_design'
        previous_config = current_config
        previous_results = {'results': 'none'}

        recommendation_list = await self.system.generate_recommendation(
            results=previous_results,
            runtype=previous_task
        )

        recommendation = recommendation_list[0] if recommendation_list else {}
        recommendation_obj = SimpleNamespace(**recommendation)

        # Generate recommended configuration
        recommended_config_list = await self.system.generate_recommendedconfig(
            previous_run_type=previous_task,
            previous_run_config=previous_config,
            recommendation=recommendation_obj
        )

        logger.info(f'Recommended config list: {recommended_config_list}')

        if recommended_config_list:
            current_config = recommended_config_list[-1]['metadata']['new_config']

        current_config['num_rounds'] = 1

        # Execute computational design
        results = await self._execute_task(
            task_name='computational_design',
            config=current_config,
            hypothesis=hypothesis,
            iteration=0
        )

        return {
            'task': 'computational_design',
            'config': current_config,
            'results': results
        }

    async def run_iteration(
        self,
        hypothesis: ProteinHypothesis,
        previous_task: str,
        previous_config: Dict[str, Any],
        previous_results: Dict[str, Any],
        iteration: int
    ) -> Dict[str, Any]:
        """
        Run a single iteration of the agentic loop.

        Args:
            hypothesis: The protein hypothesis object
            previous_task: Name of the previous task executed
            previous_config: Configuration used in previous task
            previous_results: Results from previous task
            iteration: Current iteration number

        Returns:
            Dictionary containing task results, configuration, and next task
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"ITERATION {iteration + 1}")
        logger.info(f"{'='*80}")
        logger.info(f"\n[Iteration {iteration}] Using LLM reasoner for decision-making...")

        # Step 1: Generate task recommendation
        logger.info("Step 1: Generating task recommendation...")
        recommendation_list = await self.system.generate_recommendation(
            results=previous_results,
            runtype=previous_task
        )

        recommendation = recommendation_list[-1] if recommendation_list else {}
        next_task = recommendation.get('metadata', {}).get('next_task', 'computational_design')

        logger.info(f"✓ Recommended next task: {next_task}")

        # Check if we should stop
        if next_task == 'stop':
            logger.info("Reasoner recommends stopping but we will continue anyways.")
            return {
                'task': 'stop',
                'config': None,
                'results': None
            }

        # Step 2: Generate recommended configuration
        logger.info("Step 2: Generating recommended configuration...")
        recommendation_obj = SimpleNamespace(**recommendation)

        recommended_config_list = await self.system.generate_recommendedconfig(
            previous_run_type=previous_task,
            previous_run_config=previous_config,
            recommendation=recommendation_obj
        )

        logger.info(f'Recommended config list: {recommended_config_list}')

        current_config = recommended_config_list[-1]['metadata']['new_config'] if recommended_config_list else {}

        # Handle task-specific configuration
        if next_task == 'computational_design':
            current_config = self._prepare_compdesign_config(current_config, hypothesis, iteration)
        if next_task == 'molecular_dynamics':
            current_config = self._prepare_md_config(current_config, hypothesis, iteration)

        if next_task == 'analysis':
            current_config = self._prepare_analysis_config(current_config, hypothesis, iteration)

        if next_task == 'free_energy':
            current_config = self._prepare_fe_config(current_config, hypothesis, iteration)

        # Execute the task
        results = await self._execute_task(
            task_name=next_task,
            config=current_config,
            hypothesis=hypothesis,
            iteration=iteration
        )

        # After each iteration:
        #self.metric_evaluator.update_metrics(
        #    decision=previous_task,
        #    binder_results=previous_results if previous_task == 'computational_design' else None,
        #    md_results=previous_results if previous_task == 'molecular_dynamics' else None,
        #    fe_results=previous_results if previous_task == 'free_energy' else None
        #    )
        #self.metric_evaluator.log_to_wandb(step=self.iteration_count)

        return {
            'task': next_task,
            'config': current_config,
            'results': results
        }
    def _prepare_compdesign_config(
        self,
        config: Dict[str, Any],
        hypothesis: ProteinHypothesis,
        iteration: int
    ) -> Dict[str, Any]:
        """
        Prepare configuration for computational design task.

        Args:
            config: Base configuration
            hypothesis: The protein hypothesis object
            iteration: Current iteration number

        Returns:
            Updated configuration for analysis task
        """

        if config['batch_size']>200:
            config['batch_size'] = 200

        return config

    def _prepare_md_config(
        self,
        config: Dict[str, Any],
        hypothesis: ProteinHypothesis,
        iteration: int
    ) -> Dict[str, Any]:
        """
        Prepare configuration for molecular dynamics task.

        Args:
            config: Base configuration
            hypothesis: The protein hypothesis object
            iteration: Current iteration number

        Returns:
            Updated configuration for MD task
        """
        checkpoint_file = hypothesis.binder_analysis.checkpoint_file
        checkpoint_data = pickle.load(open(checkpoint_file, 'rb'))
        all_cycles = checkpoint_data['all_cycles']

        passing = [
            all_cycles[i]['passing_structures']
            for i in range(len(all_cycles))
        ]
        passing = [Path(item).resolve() for sublist in passing for item in sublist]

        config['simulation_paths'] = passing
        config['root_output_path'] = f'{self.global_cwd}/molecular_dynamics/{self.comp_design_it}'
        #config['steps'] = 10000

        if config['steps']<10000:
            config['steps'] = 10000

        return config

    def _prepare_analysis_config(
        self,
        config: Dict[str, Any],
        hypothesis: ProteinHypothesis,
        iteration: int
    ) -> Dict[str, Any]:
        """
        Prepare configuration for analysis task.

        Args:
            config: Base configuration
            hypothesis: The protein hypothesis object
            iteration: Current iteration number

        Returns:
            Updated configuration for analysis task
        """
        paths = hypothesis.md_analysis['paths']
        data_type = config['data_type']
        analysis_type = config['analysis_type']

        distance_cutoff = config['distance_cutoff']
        if analysis_type == 'both':
            analysis_type = ['basic', 'advanced']
        else:
            analysis_type = [analysis_type]

        #seqs = [pdb2seq(p/'build/protein.pdb')[1] for p in paths]
        analysis_config = {
            data_type: {
                at: {
                    'paths': paths,
                    'kwargs': {
                        'distance_cutoff': distance_cutoff,
                        'n_top': 10,
                    },
                    #'seqs': seqs
                }
            } for at in analysis_type
        }
        return analysis_config


    def _prepare_fe_config(
        self,
        config: Dict[str, Any],
        hypothesis: ProteinHypothesis,
        iteration: int
    ) -> Dict[str, Any]:
        """
        Prepare configuration for analysis task.

        Args:
            config: Base configuration
            hypothesis: The protein hypothesis object
            iteration: Current iteration number

        Returns:
            Updated configuration for analysis task
        """
        paths = hypothesis.md_analysis['paths']

        fe_config = {'simulation_paths' : Path(f'{self.global_cwd}/molecular_dynamics/{self.comp_design_it}')}

        return fe_config

    async def _execute_task(
        self,
        task_name: str,
        config: Dict[str, Any],
        hypothesis: ProteinHypothesis,
        iteration: int
    ) -> Any:
        """
        Execute a specific task with the given configuration.

        Args:
            task_name: Name of the task to execute
            config: Task configuration
            hypothesis: The protein hypothesis object
            iteration: Current iteration number

        Returns:
            Task results
        """
        logger.info(f"\nExecuting task: {task_name}")

        # Handle computational design specific setup
        if task_name == 'computational_design':
            config['cwd'] = f'{self.global_cwd}/computational_design/{self.comp_design_it}'
            config['target_sequence'] = self.target_sequence
            self.comp_design_it += 1
            # Set up constraints if specified
            if 'constraint' in config and 'residues_bind' in config['constraint']:
                try:
                    config['constraints'] = {
                        i: {
                            'chainA': 'B',
                            'resA': '',
                            'chainB': 'A',
                            'resB': f'{self.target_sequence[entry-1]}{entry}',
                            'const_type': 'pocket',
                            'distance': 5.5
                        }
                        for i, entry in enumerate([
                            int(r) for r in config['constraint']['residues_bind']
                        ])
                    }
                except:
                    config['constraints'] = {}
            self.system.design_agents[task_name].config['cwd'] = config['cwd']
            await self.system.design_agents[task_name].initialize()

        # Execute the task
        logger.info(f'Before running {task_name}, {config=}')
        results = await self.system.design_agents[task_name].analyze_hypothesis(
            hypothesis,
            config
        )

        logger.info(f"✓ {task_name} completed")

        return results

    def _update_hypothesis(
        self,
        hypothesis: ProteinHypothesis,
        task_name: str,
        results: Any
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Update hypothesis with task results and extract best binders.

        Args:
            hypothesis: The protein hypothesis object
            task_name: Name of the task executed
            results: Task results

        Returns:
            List of best binders if available, None otherwise
        """
        best_binders = None

        if task_name == 'computational_design':
            hypothesis.add_binder_analysis(results)
            best_binders = results.top_binders
            logger.info(f'Best binders from this iteration: {best_binders}')

        elif task_name == 'molecular_dynamics':
            hypothesis.add_md_analysis(results)

        elif task_name == 'analysis':
            pass

        return best_binders

    async def run(
        self,
        research_goal: str,
        hotspot_residues: Optional[List[int]] = None,
        discover_hotspots: bool = False,
        target_prot_name: str = 'NMNAT-2',
        use_actual_hotspot_analysis: bool = False
    ) -> Dict[str, Any]:
        """
        Run the complete agentic binder design pipeline with checkpointing.

        Args:
            research_goal: The research goal describing the binder design task
            hotspot_residues: Optional list of hotspot residue indices
            discover_hotspots: If True and hotspot_residues is None, run RAG→Folding→MD→Hotspot pipeline
            target_prot_name: Name of target protein for prompts (used in hotspot discovery)
            use_actual_hotspot_analysis: If True, use actual MD trajectory analysis for hotspots

        Returns:
            Final report dictionary with results and best binders
        """
        # Initialize system
        await self.initialize(research_goal)

        # Determine hotspot residues
        if hotspot_residues is None:
            if discover_hotspots:
                # Run full RAG → Folding → MD → Hotspot pipeline
                logger.info("\n[HOTSPOT DISCOVERY] Running RAG→Folding→MD→Hotspot pipeline...")
                hotspot_residues = await self.discover_hotspots(
                    research_goal=research_goal,
                    target_prot_name=target_prot_name,
                    use_actual_hotspot_analysis=use_actual_hotspot_analysis
                )
            else:
                # Use default hotspot residues
                logger.info("\n[HOTSPOT] Using default hotspot residues...")
                hotspot_residues = None#[]#45, 67, 89, 102, 134, 156, 178, 199, 211, 234]

        # Create hypothesis for tracking
        hypothesis = ProteinHypothesis(
            content="Agentic binder design tasks in order:",
            summary="Agentic binder design tasks in order:",
            metadata={
                'iterations': [],
                'tasks': [],
                'target_sequence': self.target_sequence,
                'hotspot_residues': hotspot_residues
            }
        )

        # Append hotspot info to history
        self.system.append_history(key_items={'hotspot_residues': hotspot_residues})

        logger.info("\n[STARTING] Agentic optimization loop...")

        # Iteration 0: Run first iteration with computational_design
        iteration_result = await self.run_first_iteration(hypothesis)

        previous_task = iteration_result['task']
        previous_config = iteration_result['config']

        ##try:
        #    previous_results = iteration_result['results'].__dict__
        #except:
        previous_results = iteration_result['results']

        # Update hypothesis and track binders
        best_binders_this_iter = self._update_hypothesis(
            hypothesis,
            previous_task,
            previous_results
        )

        if best_binders_this_iter:
            self.all_binders.extend(best_binders_this_iter)
            self.best_binders.append(best_binders_this_iter)

        # Append to history
        self.system.append_history(
            key_items=best_binders_this_iter,
            decision=previous_task,
            configuration=previous_config,
            results=previous_results
        )

        self.iteration_count = 1

        # Save checkpoint after iteration 0
        if self.checkpoint_interval > 0 and self.iteration_count % self.checkpoint_interval == 0:
            checkpoint = self._create_checkpoint(
                iteration=self.iteration_count,
                hypothesis=hypothesis,
                hotspot_residues=hotspot_residues,
                previous_task=previous_task,
                previous_config=previous_config,
                previous_results=previous_results
            )
            self._save_checkpoint(checkpoint)

        # Iterations 1+: LLM-guided agentic loop
        while self.iteration_count < self.max_iterations:
            try:
                iteration_result = await self.run_iteration(
                    hypothesis=hypothesis,
                    previous_task=previous_task,
                    previous_config=previous_config,
                    previous_results=previous_results,
                    iteration=self.iteration_count
                )

                next_task = iteration_result['task']

                # Check if we should stop
                if next_task == 'stop' or next_task == '':
                    logger.info("\n[STOPPING] Reasoner recommends stopping.")
                    next_task = 'computational_design'

                # Update state
                previous_task = next_task
                previous_config = iteration_result['config']
                previous_results = iteration_result['results']

                # Update hypothesis and track binders
                best_binders_this_iter = self._update_hypothesis(
                    hypothesis,
                    previous_task,
                    previous_results
                )

                if best_binders_this_iter:
                    self.all_binders.extend(best_binders_this_iter)
                    self.best_binders.append(best_binders_this_iter)

                # Append to history
                self.system.append_history(
                    key_items=best_binders_this_iter,
                    decision=previous_task,
                    configuration=previous_config,
                    results=previous_results
                )

                self.iteration_count += 1

                # Save checkpoint
                if self.checkpoint_interval > 0 and self.iteration_count % self.checkpoint_interval == 0:
                    checkpoint = self._create_checkpoint(
                        iteration=self.iteration_count,
                        hypothesis=hypothesis,
                        hotspot_residues=hotspot_residues,
                        previous_task=previous_task,
                        previous_config=previous_config,
                        previous_results=previous_results
                    )
                    self._save_checkpoint(checkpoint)

            except Exception as e:
                next_task = 'computational_design'
                logger.error('Exception during while loop: {e}')
                continue

        # Generate final report
        final_report = self._generate_final_report(research_goal)

        #self.metric_evaluator.finish()
        # Save final checkpoint
        final_checkpoint = self._create_checkpoint(
            iteration=self.iteration_count,
            hypothesis=hypothesis,
            hotspot_residues=hotspot_residues,
            previous_task=previous_task,
            previous_config=previous_config,
            previous_results=previous_results
        )
        self._save_checkpoint(final_checkpoint, name="checkpoint_final.pkl")

        return final_report

    async def run_from_checkpoint(
        self,
        checkpoint_path: str
    ) -> Dict[str, Any]:
        """
        Resume pipeline execution from a checkpoint.

        Args:
            checkpoint_path: Path to checkpoint file

        Returns:
            Final report dictionary with results and best binders
        """
        # Load checkpoint
        checkpoint = PipelineCheckpoint.load(Path(checkpoint_path))

        # Restore state
        hypothesis, hotspot_residues, previous_task, previous_config, previous_results = \
            await self._restore_from_checkpoint(checkpoint)

        logger.info("\n[RESUMING] Continuing agentic optimization loop...")

        # Continue from where we left off
        while self.iteration_count < self.max_iterations:
            iteration_result = await self.run_iteration(
                hypothesis=hypothesis,
                previous_task=previous_task,
                previous_config=previous_config,
                previous_results=previous_results,
                iteration=self.iteration_count
            )

            next_task = iteration_result['task']

            # Check if we should stop
            if next_task == 'stop' or next_task == '':
                logger.info("\n[STOPPING] Reasoner recommends stopping.")
                break

            # Update state
            previous_task = next_task
            previous_config = iteration_result['config']
            previous_results = iteration_result['results']

            # Update hypothesis and track binders
            best_binders_this_iter = self._update_hypothesis(
                hypothesis,
                previous_task,
                previous_results
            )

            if best_binders_this_iter:
                self.all_binders.extend(best_binders_this_iter)
                self.best_binders.append(best_binders_this_iter)

            # Append to history
            self.system.append_history(
                key_items=best_binders_this_iter,
                decision=previous_task,
                configuration=previous_config,
                results=previous_results
            )

            self.iteration_count += 1

            # Save checkpoint
            if self.checkpoint_interval > 0 and self.iteration_count % self.checkpoint_interval == 0:
                checkpoint = self._create_checkpoint(
                    iteration=self.iteration_count,
                    hypothesis=hypothesis,
                    hotspot_residues=hotspot_residues,
                    previous_task=previous_task,
                    previous_config=previous_config,
                    previous_results=previous_results
                )
                self._save_checkpoint(checkpoint)

        # Generate final report
        final_report = self._generate_final_report(self.research_goal)

        # Save final checkpoint
        final_checkpoint = self._create_checkpoint(
            iteration=self.iteration_count,
            hypothesis=hypothesis,
            hotspot_residues=hotspot_residues,
            previous_task=previous_task,
            previous_config=previous_config,
            previous_results=previous_results
        )
        self._save_checkpoint(final_checkpoint, name="checkpoint_final.pkl")

        return final_report

    def _generate_final_report(self, research_goal: str) -> Dict[str, Any]:
        """
        Generate final report with results and best binders.

        Args:
            research_goal: The research goal

        Returns:
            Final report dictionary
        """
        logger.info("\n[FINAL REPORT] Generating summary...")

        final_report = {
            'research_goal': research_goal,
            'total_iterations': self.iteration_count,
            'all_binders': self.all_binders,
            'best_binders': self.best_binders[:5] if self.best_binders else [],
            'history': self.system.history if self.system else [],
            'timestamp': datetime.now().isoformat(),
            'checkpoint_dir': str(self.checkpoint_dir)
        }

        logger.info(f"\n{'='*80}")
        logger.info("PIPELINE COMPLETED")
        logger.info(f"{'='*80}")
        logger.info(f"Total iterations: {self.iteration_count}")
        logger.info(f"Total binders generated: {len(self.all_binders)}")
        logger.info(f"Best binders tracked: {len(self.best_binders)}")
        logger.info(f"Checkpoints saved to: {self.checkpoint_dir}")

        return final_report


# Default research goal for NMNAT-2
DEFAULT_RESEARCH_GOAL = """Design biologic binders for NMNAT-2 (Nicotinamide/nicotinic acid mononucleotide adenylyltransferase 2, Q9BZQ4)
using affibody, affitin, or nanobody scaffolds (or other biologic scaffolds if clinical evidence supports it).

Target: Q9BZQ4|NMNA2_HUMAN Nicotinamide/nicotinic acid mononucleotide adenylyltransferase 2
Target Sequence: MTETTKTHVILLACGSFNPITKGHIQMFERARDYLHKTGRFIVIGGIVSPVHDSYGKQGLVSSRHRLIMCQLAVQNSDWIRVDPWECYQDTWQTTCSVLEHHRDLMKRVTGCILSNVNTPSMTPVIGQPQNETPQPIYQNSNVATKPTAAKILGKVGESLSRICCVRPPVERFTFVDENANLGTVMRYEEIELRILLLCGSDLLESFCIPGLWNEADMEVIVGDFGIVVVPRDAADTDRIMNHSSILRKYKNNIMVVKDDINHPMSVVSSTKSRLALQHGDGHVVDYLSQPVIDYILKSQLYINASG

Objective: Disrupt physical interactions between NMNAT-2 and proteins involved in cancer pathways.

Goals:
- High binding affinity (< 10 nM)
- Stable complex in MD simulation (RMSD < 3 Å)
- Mimic binding interface of natural interacting partners
- Prioritize scaffolds with clinical precedent

Default Scaffolds:
- Affibody: VDNKFNKEQQNAFYEILHLPNLNEEQRNAFIQSLKDDPSQSANLLAEAKKLNDAQAPK
- Affitin: MGSWAEFKQRLAAIKTRLQALGGSEAELAAFEKEIAAFESELQAYKGKGNPEVEALRKEAAAIRDELQAYRHN
- Nanobody: QVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEWVSAISGSGGSTYYADSVKGRFTISRDNSKNTLYLQMNSLRAEDTAVYYCAA...WGQGTLVTVSS"""


async def main():
    """Main entry point for the agentic binder pipeline with checkpointing."""
    parser = argparse.ArgumentParser(
        description='Agentic Binder Design Pipeline with Checkpointing - LLM-guided iterative binder optimization',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default NMNAT-2 research goal and default hotspots
  python -m struct_bio_reasoner.workflows.agentic_binder_pipeline_checkpointing

  # Run with checkpointing every 2 iterations
  python -m struct_bio_reasoner.workflows.agentic_binder_pipeline_checkpointing --checkpoint-interval 2

  # Resume from checkpoint
  python -m struct_bio_reasoner.workflows.agentic_binder_pipeline_checkpointing --resume checkpoints/checkpoint_latest.pkl

  # Run with hotspot discovery
  python -m struct_bio_reasoner.workflows.agentic_binder_pipeline_checkpointing --discover-hotspots

  # Run with custom checkpoint directory
  python -m struct_bio_reasoner.workflows.agentic_binder_pipeline_checkpointing --checkpoint-dir my_checkpoints

  # Full example with all options
  python -m struct_bio_reasoner.workflows.agentic_binder_pipeline_checkpointing \\
      --discover-hotspots \\
      --checkpoint-interval 1 \\
      --checkpoint-dir results/checkpoints \\
      --max-iterations 15 \\
      --output results/final_report.json
        """
    )

    parser.add_argument(
        '--research-goal',
        type=str,
        default=DEFAULT_RESEARCH_GOAL,
        help='Research goal describing the binder design task (default: NMNAT-2 binder design)'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='config/binder_config.yaml',
        help='Path to binder configuration file (default: config/binder_config.yaml)'
    )

    parser.add_argument(
        '--jnana-config',
        type=str,
        default='config/jnana_config.yaml',
        help='Path to Jnana configuration file (default: config/jnana_config.yaml)'
    )

    parser.add_argument(
        '--max-iterations',
        type=int,
        default=10,
        help='Maximum number of design iterations (default: 10)'
    )

    parser.add_argument(
        '--checkpoint-dir',
        type=str,
        default='checkpoints',
        help='Directory to save checkpoints (default: checkpoints)'
    )

    parser.add_argument(
        '--checkpoint-interval',
        type=int,
        default=1,
        help='Save checkpoint every N iterations (default: 1, set to 0 to disable)'
    )

    parser.add_argument(
        '--resume',
        type=str,
        default=None,
        help='Path to checkpoint file to resume from (e.g., checkpoints/checkpoint_latest.pkl)'
    )

    parser.add_argument(
        '--hotspot-residues',
        type=str,
        default=None,
        help='Comma-separated list of hotspot residue indices (e.g., "45,67,89"). '
             'If not provided and --discover-hotspots is not set, uses default hotspots.'
    )

    parser.add_argument(
        '--discover-hotspots',
        action='store_true',
        help='Run RAG→Folding→MD→Hotspot pipeline to discover binding hotspots. '
             'Only used if --hotspot-residues is not provided and not resuming from checkpoint.'
    )

    parser.add_argument(
        '--target-prot-name',
        type=str,
        default='NMNAT-2',
        help='Name of target protein for prompts (default: NMNAT-2). '
             'Used in hotspot discovery pipeline.'
    )

    parser.add_argument(
        '--use-actual-hotspot-analysis',
        action='store_true',
        help='Use actual MD trajectory analysis for hotspots instead of LLM suggestions. '
             'Only relevant when --discover-hotspots is set.'
    )

    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Path to save final report JSON (default: no file output)'
    )

    args = parser.parse_args()

    # Parse hotspot residues if provided
    hotspot_residues = None
    if args.hotspot_residues:
        hotspot_residues = [int(x.strip()) for x in args.hotspot_residues.split(',')]

    try:
        # Initialize pipeline
        pipeline = AgenticBinderPipelineWithCheckpointing(
            config_path=args.config,
            jnana_config_path=args.jnana_config,
            max_iterations=args.max_iterations,
            checkpoint_dir=args.checkpoint_dir,
            checkpoint_interval=args.checkpoint_interval
        )

        # Resume from checkpoint or start fresh
        if args.resume:
            logger.info(f"Resuming from checkpoint: {args.resume}")
            final_report = await pipeline.run_from_checkpoint(args.resume)
        else:
            logger.info(f"Starting pipeline with research goal:\n{args.research_goal[:200]}...")

            if args.discover_hotspots and hotspot_residues is None:
                logger.info("Hotspot discovery enabled - will run RAG→Folding→MD→Hotspot pipeline")
            elif hotspot_residues is not None:
                logger.info(f"Using provided hotspot residues: {hotspot_residues}")
            else:
                logger.info("Using default hotspot residues")

            final_report = await pipeline.run(
                research_goal=args.research_goal,
                hotspot_residues=hotspot_residues,
                discover_hotspots=args.discover_hotspots,
                target_prot_name=args.target_prot_name,
                use_actual_hotspot_analysis=args.use_actual_hotspot_analysis
            )

        # Save output if requested
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w') as f:
                json.dump(final_report, f, indent=2, default=str)

            logger.info(f"\n✓ Final report saved to: {output_path}")

        logger.info("\n✅ Pipeline completed successfully!")
        return True

    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

