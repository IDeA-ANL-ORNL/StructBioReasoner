"""
Agentic Binder Design Pipeline

A cleaned-up, class-based implementation of the agentic workflow for designing
biologic binders using LLM-guided decision-making.

Workflow:
1. Initialize system and set research goal
2. Agentic loop:
   - LLM reasoner recommends next task (BindCraft/MD/Stop)
   - Generate recommended configuration
   - Execute task
   - Evaluate results
3. Generate final report with best binders

Author: StructBioReasoner Team
Date: 2025-12-24
"""

import sys
import asyncio
import logging
import json
import argparse
import dill as pickle
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from types import SimpleNamespace

from jnana.protognosis.core.llm_interface import alcfLLM
from ..core.binder_design_system import BinderDesignSystem
from ..data.protein_hypothesis import ProteinHypothesis
from ..prompts.prompts import get_prompt_manager, config_master
from ..utils.uniprot_api import fetch_uniprot_sequence
from ..utils.hotspot import get_hotspot_resids_from_simulations


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logging.getLogger('parsl').propagate = False

logger = logging.getLogger(__name__)


class AgenticBinderPipeline:
    """
    Agentic pipeline for iterative binder design using LLM-guided decision-making.
    """
    
    def __init__(
        self,
        config_path: str = "config/binder_config.yaml",
        jnana_config_path: str = "config/jnana_config.yaml",
        max_iterations: int = 1_000_000_000,
        enable_agents: Optional[List[str]] = None
    ):
        """
        Initialize the agentic binder design pipeline.
        
        Args:
            config_path: Path to binder configuration file
            jnana_config_path: Path to Jnana configuration file
            max_iterations: Maximum number of design iterations
            enable_agents: List of agents to enable
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
        
        self.system: Optional[BinderDesignSystem] = None
        self.session_id: Optional[str] = None
        self.target_sequence: Optional[str] = None
        self.global_cwd: Optional[str] = None
        
        # Tracking variables
        self.all_binders = []
        self.best_binders = []
        self.iteration_count = 0
        self.comp_design_it = 0
    
    async def initialize(self, research_goal: str) -> None:
        """
        Initialize the binder design system and set research goal.
        
        Args:
            research_goal: The research goal describing the binder design task
        """
        logger.info("="*80)
        logger.info("AGENTIC BINDER DESIGN PIPELINE")
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
                'task': '',
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
        if next_task == 'molecular_dynamics':
            current_config = self._prepare_md_config(current_config, hypothesis, iteration)

        if next_task == 'analysis':
            current_config = self._prepare_analysis_config(current_config, hypothesis, iteration)
        # Execute the task
        results = await self._execute_task(
            task_name=next_task,
            config=current_config,
            hypothesis=hypothesis,
            iteration=iteration
        )

        return {
            'task': next_task,
            'config': current_config,
            'results': results
        }

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
        config['steps'] = 1000
        return config

    def _prepare_analysis_config(
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
        config['steps'] = 1000
        return config

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
            self.comp_design_it +=1
            # Set up constraints if specified
            if 'constraint' in config and 'residues_bind' in config['constraint']:
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
        Run the complete agentic binder design pipeline.

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
                hotspot_residues = [45, 67, 89, 102, 134, 156, 178, 199, 211, 234]

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

        # Run first iteration (hardcoded computational_design)
        iteration_result = await self.run_first_iteration(hypothesis)

        previous_task = iteration_result['task']
        previous_config = iteration_result['config']
        try:
            previous_results = iteration_result['results'].__dict__
        except:
            prvious_results = iteration_result['results']
        # Update hypothesis and track binders
        best_binders_this_iter = self._update_hypothesis(
            hypothesis,
            previous_task,
            iteration_result['results']
        )

        if best_binders_this_iter:
            self.best_binders.append(best_binders_this_iter)

        # Append to history
        self.system.append_history(
            key_items=best_binders_this_iter,
            decision=previous_task,
            configuration=previous_config,
            results=iteration_result['results']
        )

        self.iteration_count = 1

        self.comp_design_it = 1
        # Run subsequent iterations
        while self.iteration_count < self.max_iterations:
            iteration_result = await self.run_iteration(
                hypothesis=hypothesis,
                previous_task=previous_task,
                previous_config=previous_config,
                previous_results=previous_results,
                iteration=self.iteration_count
            )

            # Check if we should stop
            if iteration_result['task'] == 'stop':
                logger.info("Pipeline stopping as recommended by reasoner.")
                break

            # Update for next iteration
            previous_task = iteration_result['task']
            previous_config = iteration_result['config']
            #if iteration_result['results'] is not dict:
            #    previous_results = iteration_result['results'].__dict__
            #else:
            try:
                previous_results = iteration_result['results'].__dict__
            except:
                previous_results = iteration_result['results']

            # Update hypothesis and track binders
            best_binders_this_iter = self._update_hypothesis(
                hypothesis,
                previous_task,
                iteration_result['results']
            )

            if best_binders_this_iter:
                self.best_binders.append(best_binders_this_iter)

            # Append to history
            self.system.append_history(
                key_items=best_binders_this_iter,
                decision=previous_task,
                configuration=previous_config,
                results=iteration_result['results']
            )

            self.iteration_count += 1

        # Generate final report
        final_report = self._generate_final_report(research_goal)

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
            'timestamp': datetime.now().isoformat()
        }

        logger.info(f"\n{'='*80}")
        logger.info("PIPELINE COMPLETED")
        logger.info(f"{'='*80}")
        logger.info(f"Total iterations: {self.iteration_count}")
        logger.info(f"Total binders generated: {len(self.all_binders)}")
        logger.info(f"Best binders tracked: {len(self.best_binders)}")

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
    """Main entry point for the agentic binder pipeline."""
    parser = argparse.ArgumentParser(
        description='Agentic Binder Design Pipeline - LLM-guided iterative binder optimization',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default NMNAT-2 research goal and default hotspots
  python -m struct_bio_reasoner.workflows.agentic_binder_pipeline

  # Run with hotspot discovery (RAG→Folding→MD→Hotspot pipeline)
  python -m struct_bio_reasoner.workflows.agentic_binder_pipeline --discover-hotspots

  # Run with hotspot discovery using actual MD trajectory analysis
  python -m struct_bio_reasoner.workflows.agentic_binder_pipeline --discover-hotspots --use-actual-hotspot-analysis

  # Run with custom hotspot residues
  python -m struct_bio_reasoner.workflows.agentic_binder_pipeline --hotspot-residues "45,67,89,102,134"

  # Run with custom research goal
  python -m struct_bio_reasoner.workflows.agentic_binder_pipeline --research-goal "Design binders for protein X"

  # Run with custom configuration and max iterations
  python -m struct_bio_reasoner.workflows.agentic_binder_pipeline --config custom_config.yaml --max-iterations 20

  # Full example with all options
  python -m struct_bio_reasoner.workflows.agentic_binder_pipeline \\
      --discover-hotspots \\
      --target-prot-name "MyProtein" \\
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
             'Only used if --hotspot-residues is not provided.'
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
        pipeline = AgenticBinderPipeline(
            config_path=args.config,
            jnana_config_path=args.jnana_config,
            max_iterations=args.max_iterations
        )

        # Run pipeline
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

