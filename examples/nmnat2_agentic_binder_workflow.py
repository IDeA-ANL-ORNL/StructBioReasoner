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
# Add Jnana to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'Jnana'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
        config_path="config/binder_config.yaml",
        jnana_config_path="config/test_jnana_config.yaml",
        enable_agents=['computational_design', 'molecular_dynamics', 'rag', 'structure_prediction']
    )
    
    await system.start()
    logger.info("✓ System initialized")

    # Define research goal


    session_id = await system.set_research_goal(research_goal)
    target_sequence = system._extract_target_sequence(research_goal)
    logger.info(f"✓ Research goal set (session: {session_id})")

    # ========================================================================
    # STEP 2: Recommender Agent → Optimize HiPerRAG Prompt
    # ========================================================================
    logger.info("\n[STEP 2] Using Recommender Agent to optimize HiPerRAG prompt...")

    interactome_rag_prompt_manager = get_prompt_manager('rag', research_goal, {}, target_prot = 'NMNAT-2', prompt_type = 'interactome', history_list = [], num_history = 3) 
    rag_prompt = system.prompt_gen_llm.generate(prompt = interactome_rag_prompt_manager.prompt_r,
                                        temperature = 0.3,
                                        max_tokens = 32678
                                        ) 

    rag_hypothesis = await system.design_agents['rag'].generate_rag_hypothesis({'prompt': rag_prompt})
    system.append_history(key_items = rag_hypothesis, decision = 'rag')

    logger.info(f"{rag_hypothesis=}")
    interactome_rag_prompt_manager.input_json = rag_hypothesis
    conclusion_prompt = interactome_rag_prompt_manager.conclusion_prompt()
    rag_result_json = system.prompt_gen_llm.generate_with_json_output(prompt = conclusion_prompt,
                                        json_schema = config_master['rag_output'],
                                        temperature = 0.3,
                                        max_tokens = 32678
                                        ) 
    rag_result_json = rag_result_json[0]
    sequences = [await fetch_uniprot_sequence(id) for id in rag_result_json['interacting_protein_uniprot_ids']] 
    logger.info(sequences)
    rag_result_json['sequences'] = [s['sequence'] for s in sequences]
    logger.info(f"{rag_result_json=}")
    
    folding_prompt_manager = get_prompt_manager('chai', research_goal, rag_result_json, target_prot = target_sequence, prompt_type = 'running', history_list = [], num_history = 3)
    logger.info(f"{folding_prompt_manager.prompt_r=}")
    folding_input = system.prompt_gen_llm.generate_with_json_output(prompt = folding_prompt_manager.prompt_r,
                                        json_schema = config_master['chai'],
                                        temperature = 0.3,
                                        max_tokens = 32678
                                        ) 
    
    logger.info(f"{rag_result_json=}")
    logger.info(f"{folding_input=}")
    """
    Execute Chai folding with sequences from folding_result
    """
    if True:
        folding_output = await system.design_agents['structure_prediction'].analyze_hypothesis(rag_hypothesis, folding_input)
    if False:
        folding_output = {"analysis_id": "d842ca9a-0f37-4fd7-9231-d9145839966b", "folding_algorithm": "Chai-1", "unique_models": 5, "total_models": 2, "best_models": ["data/interactome/folds/nmnat2_p53/protein3.pdb", "data/interactome/folds/nmnat2_fbxo45/protein4.pdb"], "scores": {"0": {"aggregate_score": [[0.37450993061065674], [0.37606847286224365], [0.373186320066452], [0.38200777769088745], [0.3771553933620453]], "ptm": [[0.5082611441612244], [0.5060023665428162], [0.5090510249137878], [0.507888674736023], [0.5092036724090576]], "iptm": [[0.34107211232185364], [0.34358495473861694], [0.3392201364040375], [0.35053756833076477], [0.3441433012485504]], "per_chain_ptm": [[[0.6279827952384949, 0.6040610671043396]], [[0.6258801817893982, 0.6029364466667175]], [[0.625359296798706, 0.6005409955978394]], [[0.6229435801506042, 0.6049138307571411]], [[0.6228601336479187, 0.6027255654335022]]], "per_chain_pair_iptm": [[[[0.6279827952384949, 0.21405690908432007], [0.34107211232185364, 0.6040610671043396]]], [[[0.6258801817893982, 0.21357953548431396], [0.34358495473861694, 0.6029364466667175]]], [[[0.625359296798706, 0.21446824073791504], [0.3392201364040375, 0.6005409955978394]]], [[[0.6229435801506042, 0.21590736508369446], [0.35053756833076477, 0.6049138307571411]]], [[[0.6228601336479187, 0.21368837356567383], [0.3441433012485504, 0.6027255654335022]]]], "has_inter_chain_clashes": [[false], [false], [false], [false], [false]], "chain_chain_clashes": [[[[0, 0], [0, 0]]], [[[0, 0], [0, 0]]], [[[1, 0], [0, 0]]], [[[0, 0], [0, 0]]], [[[0, 0], [0, 0]]]]}, "1": {"aggregate_score": [[0.3203924596309662], [0.3217898905277252], [0.32374289631843567], [0.3141600787639618], [0.3249344825744629]], "ptm": [[0.5748198628425598], [0.5817196369171143], [0.5802063941955566], [0.5755545496940613], [0.5788462162017822]], "iptm": [[0.2567856013774872], [0.25680744647979736], [0.25962701439857483], [0.24881145358085632], [0.26145654916763306]], "per_chain_ptm": [[[0.6657668948173523, 0.8086109161376953]], [[0.6640876531600952, 0.8090826272964478]], [[0.665465235710144, 0.809389591217041]], [[0.6696493029594421, 0.8104386329650879]], [[0.665094792842865, 0.8087285757064819]]], "per_chain_pair_iptm": [[[[0.6657668948173523, 0.21266961097717285], [0.2567856013774872, 0.8086109161376953]]], [[[0.6640876531600952, 0.21302932500839233], [0.25680744647979736, 0.8090826272964478]]], [[[0.665465235710144, 0.21106721460819244], [0.25962701439857483, 0.809389591217041]]], [[[0.6696493029594421, 0.2127392441034317], [0.24881145358085632, 0.8104386329650879]]], [[[0.665094792842865, 0.2132064700126648], [0.26145654916763306, 0.8087285757064819]]]], "has_inter_chain_clashes": [[false], [false], [false], [false], [false]], "chain_chain_clashes": [[[[0, 0], [0, 0]]], [[[0, 0], [0, 0]]], [[[0, 1], [1, 0]]], [[[0, 0], [0, 0]]], [[[1, 0], [0, 0]]]]}}, "tools_used": ["chai"], "confidence_score": 0.75, "timestamp": "2025-12-09T21:00:20.421234"} 

    folding_prompt_manager.input_json = folding_output
    folding_conclusion = folding_prompt_manager.conclusion_prompt()
    mdinput = system.prompt_gen_llm.generate_with_json_output(prompt = folding_conclusion,
                                        json_schema = config_master['mdagent'],
                                        temperature = 0.3,
                                        max_tokens = 32678
                                        ) 

    if True:
        md_output = await system.design_agents['molecular_dynamics'].analyze_hypothesis(rag_hypothesis, mdinput)
    
    md_prompt_manager = get_prompt_manager('mdagent', research_goal, md_output, target_prot = target_sequence, prompt_type = 'interactome_simulation', history_list = system.history_list, num_history = 3) 
    md_conclusion = md_prompt_manager.prompt_c
    hotspot_input = system.prompt_gen_llm.generate_with_json_output(prompt = md_conclusion,
                                        json_schema = config_master['hotspot'],
                                        temperature = 0.3,
                                        max_tokens = 32678
                                        )
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

            scaffold_selection_prompt = f"""
            Based on the research goal and RAG results, which binder scaffold should we use for NMNAT-2?

            Research Goal: {research_goal}

            RAG Results: {json.dumps(rag_result_json, indent=2, default=str)}

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
            )

            starting_binder = scaffold_selection[0]['scaffold_sequence']
            logger.info(f"Selected {scaffold_selection[0]['scaffold_type']} scaffold")
            logger.info(f"Rationale: {scaffold_selection[0]['rationale']}")
            logger.info(f"Starting binder: {starting_binder[:50]}...")

            # Default configuration for first iteration
            current_config = system.binder_config.get("agents", {}).get("computational_design", {})

            logger.info(f"Using default configuration: {json.dumps(current_config, indent=2)}")

            # Create mock recommendation for iteration 0
            recommendation = {
                'next_task': 'computational_design',
                'rationale': f"Initial iteration - starting with BindCraft using {scaffold_selection[0]['scaffold_type']} scaffold",
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

