"""
NMNAT-2 Agentic Binder Design Workflow

This script implements an LLM-guided agentic workflow for designing biologic binders
(affibody, affitin, nanobody, or other scaffolds) for NMNAT-2 that disrupt cancer pathway interactions.

Workflow:
1. Research Goal → Recommender Agent (Jnana) → Optimized HiPerRAG prompt
2. HiPerRAG → Interacting protein names → UniProt API → Sequences
3. Chai Agent → Folded structures
4. Reasoner → Which systems to simulate?
5. MD Analysis Agent → MD results → Top interacting residues
6. WHILE LOOP (Agentic decision-making):
   - Reasoner → Task recommendation (BindCraft/MD/FreeEnergy/Stop)
   - Execute recommended task
   - Reasoner evaluates results
7. Final output: Best binders + rationale

Author: StructBioReasoner Team
Date: 2025-12-08
"""

import dill as pickle
import sys
import asyncio
import logging
import json
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from struct_bio_reasoner.utils.cleanup_queue import cleanup_all_queues
from struct_bio_reasoner.utils.uniprot_api import fetch_uniprot_sequence
from jnana.protognosis.core.llm_interface import alcfLLM
from struct_bio_reasoner.prompts.prompts import get_prompt_manager, config_master
from struct_bio_reasoner.data.protein_hypothesis import ProteinHypothesis
from struct_bio_reasoner.utils.hotspot import get_hotspot_resids_from_simulations

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logging.getLogger('parsl').propagate = False

logger = logging.getLogger(__name__)

# ============================================================================
# MAIN WORKFLOW
# ============================================================================

async def nmnat2_agentic_workflow(research_goal):
    """
    Main agentic workflow for NMNAT-2 binder design.
    """
    
    logger.info("="*80)
    logger.info("NMNAT-2 AGENTIC BINDER DESIGN WORKFLOW")
    logger.info("="*80)
    
    # ========================================================================
    # STEP 1: Initialize System & Set Research Goal
    # ========================================================================
    logger.info("\n[STEP 1] Initializing BinderDesignSystem...")
    
    from struct_bio_reasoner.core.binder_design_system import BinderDesignSystem
    
    system = BinderDesignSystem(
        config_path="config/binder_config_default.yaml",
        jnana_config_path="config/jnana_config.yaml",
        enable_agents=['computational_design', 'molecular_dynamics', 'rag', 'structure_prediction']
    )

    system.prompt_gen_llm = alcfLLM()
    
    await system.start()
    logger.info("✓ System initialized")

    # Define research goal


    session_id = await system.set_research_goal(research_goal)
    target_sequence = system._extract_target_sequence(research_goal)
    logger.info(f"✓ Research goal set (session: {session_id})")

    if False:
        # ========================================================================
        # STEP 2: Recommender Agent → Optimize HiPerRAG Prompt
        # ========================================================================
        logger.info("\n[STEP 2] Using Recommender Agent to optimize HiPerRAG prompt...")

        interactome_rag_prompt_manager = get_prompt_manager('rag', research_goal, {}, target_prot = 'NMNAT-2', prompt_type = 'interactome', history = [], num_history = 3) 
        rag_prompt = system.prompt_gen_llm.generate(prompt = interactome_rag_prompt_manager.prompt_r,
                                            temperature = 0.3,
                                            max_tokens = 32678
                                            ) 
        mdinput = {}
        mdinput['simulation_paths'] = []

        rag_hypothesis = await system.design_agents['rag'].generate_rag_hypothesis({'prompt': rag_prompt})
        system.append_history(key_items = rag_hypothesis, decision = 'rag')

        logger.info(f"{rag_hypothesis=}")
        interactome_rag_prompt_manager.input_json = rag_hypothesis
        conclusion_prompt = interactome_rag_prompt_manager.conclusion_prompt()

        while mdinput['simulation_paths'] == []:
            rag_result_json = system.prompt_gen_llm.generate_with_json_output(prompt = conclusion_prompt,
                                                json_schema = config_master['rag_output'],
                                                temperature = 0.3,
                                                max_tokens = 32678
                                                )[0]

            sequences = [await fetch_uniprot_sequence(id) for id in rag_result_json['interacting_protein_uniprot_ids']] 
            logger.info(sequences)
            rag_result_json['sequences'] = [s['sequence'] for s in sequences]
            
            folding_prompt_manager = get_prompt_manager('chai', research_goal, rag_result_json, target_prot = target_sequence, prompt_type = 'running', history = [], num_history = 3)
            logger.info(f"{folding_prompt_manager.prompt_r=}")

            folding_input = system.prompt_gen_llm.generate_with_json_output(prompt = folding_prompt_manager.prompt_r,
                                                json_schema = config_master['structure_prediction'],
                                                temperature = 0.3,
                                                max_tokens = 32678
                                                )[0]

            with open('rag_hypothesis.pkl', 'wb') as f:
                pickle.dump(rag_hypothesis, f)

            with open('folding_input.pkl', 'wb') as f:
                pickle.dump(folding_input, f)

            #rag_hypothesis = pickle.load(open('rag_hypothesis.pkl', 'rb'))
            #folding_input = pickle.load(open('folding_input.pkl', 'rb'))

            """
            Execute Chai folding with sequences from folding_result
            """
            folding_output = await system.design_agents['structure_prediction'].analyze_hypothesis(rag_hypothesis, folding_input)

            folding_prompt_manager.input_json = folding_output
            folding_conclusion = folding_prompt_manager.conclusion_prompt()
            mdinput = system.prompt_gen_llm.generate_with_json_output(prompt = folding_conclusion,
                                                json_schema = config_master['molecular_dynamics'],
                                                temperature = 0.3,
                                                max_tokens = 32678
                                                )[0]

        logger.info(f'{mdinput=}')
        with open('mdinput.pkl', 'wb') as f:
            pickle.dump(mdinput, f)

        if True:
            md_output = await system.design_agents['molecular_dynamics'].analyze_hypothesis(rag_hypothesis, mdinput)
        
        md_prompt_manager = get_prompt_manager('mdagent', research_goal, md_output, target_prot = target_sequence, prompt_type = 'interactome_simulation', history = system.history, num_history = 3) 
        md_conclusion = md_prompt_manager.prompt_c
        hotspot_input = system.prompt_gen_llm.generate_with_json_output(prompt = md_conclusion,
                                            json_schema = config_master['hotspot'],
                                            temperature = 0.3,
                                            max_tokens = 32678
                                            )[0]
        logger.info(f"Hotspot input: {hotspot_input}")
        if False:
            hotspot_output = get_hotspot_resids_from_simulations(
                sim_directories,
                top_n=10,
                selection1="protein and segid A",
                selection2="protein and segid B"
            )
    if True:
        hotspot_output = {'hotspot_residues': [45, 67, 89, 102, 134, 156, 178, 199, 211, 234]}

    system.append_history(key_items = hotspot_output)

    # ========================================================================
    # STEP 6: AGENTIC WHILE LOOP - Iterative Binder Optimization
    # ========================================================================
    logger.info("\n[STEP 6] Starting agentic optimization loop...")

    design_it = 0
    next_task = None
    max_iterations = 10  # Safety limit

    # Initialize tracking variables
    all_binders = []
    best_binders = []

    while next_task != 'stop' and design_it < max_iterations:
        logger.info(f"\n{'='*80}")
        logger.info(f"ITERATION {design_it + 1}")
        logger.info(f"{'='*80}")

        # ====================================================================
        # ITERATION 0: Hardcoded to use computational_design (BindCraft)
        # ====================================================================
        if design_it == 0:
            logger.info("\n[Iteration 0] Hardcoded: Starting with computational_design (BindCraft)")

            # Hardcode task
            next_task = 'computational_design'

            # Use HiPerRAG to decide which binder scaffold to use
            logger.info("Using HiPerRAG to select optimal binder scaffold...")

            #RAG Results: {json.dumps(rag_result_json, indent=2, default=str)}
            scaffold_selection_prompt = f"""
            Based on the research goal and RAG results, which binder scaffold should we use for NMNAT-2?

            Research Goal: {research_goal}


            Available scaffolds:
            - affibody: VDNKFNKEQQNAFYEILHLPNLNEEQRNAFIQSLKDDPSQSANLLAEAKKLNDAQAPK
            - affitin: MGSWAEFKQRLAAIKTRLQALGGSEAELAAFEKEIAAFESELQAYKGKGNPEVEALRKEAAAIRDELQAYRHN
            - nanobody: QVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEWVSAISGSGGSTYYADSVKGRFTISRDNSKNTLYLQMNSLRAEDTAVYYCAA

            Please provide your recommendation in JSON format:
            {{
                "scaffold_type": "affibody|affitin|nanobody",
                "scaffold_sequence": "full sequence",
                "rationale": "explanation"
            }}"""

            scaffold_schema = {
                'scaffold_type': 'string',
                'scaffold_sequence': 'string',
                'rationale': 'string'
            }

            scaffold_selection = system.prompt_gen_llm.generate_with_json_output(
                prompt=scaffold_selection_prompt,
                json_schema=scaffold_schema,
                temperature=0.3,
                max_tokens=32678
            )[0]
            logger.info(scaffold_selection)
            starting_binder = scaffold_selection['scaffold_sequence']
            logger.info(f"Selected {scaffold_selection['scaffold_type']} scaffold")
            logger.info(f"Rationale: {scaffold_selection['rationale']}")
            logger.info(f"Starting binder: {starting_binder[:50]}...")

            # Default configuration for first iteration
            current_config = system.binder_config.get("agents", {}).get("computational_design", {})
            current_config['target_sequence'] = target_sequence 
            logger.info(f"Using default configuration: {json.dumps(current_config, indent=2)}")

            # Create mock recommendation for iteration 0
            recommendation = {
                'next_task': 'computational_design',
                'rationale': f"Initial iteration - starting with BindCraft using {scaffold_selection['scaffold_type']} scaffold",
                'confidence': 1.0
            }

        # ====================================================================
        # ITERATION 1+: Use LLM reasoner to decide next task and config
        # ====================================================================
        else:
            logger.info(f"\n[Iteration {design_it}] Using LLM reasoner for decision-making...")

            # Step 1: Generate recommendation based on previous results
            logger.info("Step 1: Generating task recommendation...")
            recommendation_list = await system.generate_recommendation(
                results=previous_results,
                runtype=previous_task
            )
            recommendation = recommendation_list[0] if recommendation_list else {}

            next_task = recommendation.get('next_task', 'stop')
            logger.info(f"✓ Recommended next task: {next_task}")
            logger.info(f"  Rationale: {recommendation.get('rationale', 'N/A')}")

            # If stop, break the loop
            if next_task == 'stop':
                logger.info("Reasoner recommends stopping. Finalizing results...")
                break

            # Step 2: Generate recommended configuration
            logger.info("Step 2: Generating recommended configuration...")
            recommended_config_list = await system.generate_recommendedconfig(
                previous_run_type=previous_task,
                previous_run_config=previous_config,
                recommendation=recommendation
            )
            current_config = recommended_config_list[0] if recommended_config_list else {}

            logger.info(f"✓ Recommended configuration: {json.dumps(current_config, indent=2)}")

        # ====================================================================
        # EXECUTE THE RECOMMENDED TASK
        # ====================================================================
        logger.info(f"\nExecuting task: {next_task}")

        # Store current task and config for next iteration
        previous_task = next_task
        previous_config = current_config

        # Create hypothesis for this iteration
        hypothesis_loop = ProteinHypothesis(
            content=f"{next_task} for iteration {design_it}",
            summary=f"Iteration {design_it}: {next_task}",
            metadata={
                'iteration': design_it,
                'task': next_task,
                'target_sequence': target_sequence,
                'hotspot_residues': hotspot_output['hotspot_residues']
            }
        )

        logger.info(f'{next_task=}')
        with open('hypothesis.pkl', 'wb') as f:
            pickle.dump(hypothesis_loop, f)

        with open('current_config.pkl', 'wb') as f:
            pickle.dump(current_config, f)

        # Execute task using unified interface
        logger.info(f"Running {next_task}...")
        results = await system.design_agents[next_task].analyze_hypothesis(
            hypothesis_loop,
            current_config
        )

        previous_results = results
        logger.info(f"✓ {next_task} completed")

        # Extract best binder from this iteration for key_items
        best_binder_this_iteration = None

        if next_task == 'computational_design':
            # Extract best binder from BindCraft results
            logger.info(f"  Sequences generated: {results.get('total_sequences_generated', 0)}")

            # Track all binders
            if 'all_cycles' in results:
                for cycle_data in results['all_cycles'].values():
                    all_binders.extend(cycle_data.keys())

                # Get best binder (lowest energy) from last cycle
                last_cycle = max(results['all_cycles'].keys())
                cycle_data = results['all_cycles'][last_cycle]
                if cycle_data:
                    best_binder_seq = min(cycle_data.items(), key=lambda x: x[1].get('energy', float('inf')))
                    best_binder_this_iteration = {
                        'iteration': design_it,
                        'task': next_task,
                        'sequence': best_binder_seq[0],
                        'energy': best_binder_seq[1].get('energy'),
                        'metrics': best_binder_seq[1]
                    }
                    logger.info(f"  Best binder energy: {best_binder_seq[1].get('energy')}")

        # Append to history with best binder as key_items
        system.append_history(
            key_items=best_binder_this_iteration if best_binder_this_iteration else None,
            decision=next_task,
            configuration=current_config,
            results=results
        )

        # Track best binders
        if best_binder_this_iteration:
            best_binders.append(best_binder_this_iteration)

        # Increment iteration counter
        design_it += 1
        logger.info(f"Iteration {design_it} completed")

    # ========================================================================
    # STEP 7: Generate Final Report
    # ========================================================================
    logger.info("\n[STEP 7] Generating final report...")

    final_report = {
        'research_goal': research_goal,
        'total_iterations': design_it,
        'all_binders': all_binders,
        'best_binders': best_binders[:5] if best_binders else [],
        'final_recommendation': recommendation,
        'history': system.history,
        'timestamp': datetime.now().isoformat()
    }

    logger.info(f"\n{'='*80}")
    logger.info("WORKFLOW COMPLETED")
    logger.info(f"{'='*80}")
    logger.info(f"Total iterations: {design_it}")
    logger.info(f"Total binders generated: {len(all_binders)}")
    logger.info(f"Final task: {next_task}")

    return final_report


# Note: analyze_binding_hotspots function removed - now using
# struct_bio_reasoner.utils.hotspot.get_hotspot_resids_from_simulations
# directly in the workflow (see line ~390)


async def main():

    research_goal = """Design biologic binders for NMNAT-2 (Nicotinamide/nicotinic acid mononucleotide adenylyltransferase 2, Q9BZQ4)
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

    try:
        final_report = await nmnat2_agentic_workflow(research_goal)

        if final_report:
            print("\n✅ Workflow completed successfully!")
            return True
        else:
            print("\n❌ Workflow failed")
            return False

    except Exception as e:
        logger.error(f"Workflow error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

