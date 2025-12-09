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
from jnana.protognosis.core.llm_interface import alcfLLM
from struct_bio_reasoner.prompts.prompts import get_prompt_manager, config_master
from struct_bio_reasoner.data.protein_hypothesis import ProteinHypothesis
# Add Jnana to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'Jnana'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def fetch_uniprot_sequence(uniprot_id: str) -> Optional[Dict[str, str]]:
    """
    Fetch protein sequence from UniProt API.
    
    Args:
        uniprot_id: UniProt accession ID
        
    Returns:
        Dictionary with protein name and sequence
    """
    try:
        url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.fasta"
        response = requests.get(url)
        
        if response.status_code == 200:
            lines = response.text.strip().split('\n')
            header = lines[0]
            sequence = ''.join(lines[1:])
            
            # Extract protein name from header
            # Format: >sp|P12345|PROT_HUMAN Protein name OS=...
            parts = header.split('|')
            if len(parts) >= 3:
                name_part = parts[2].split(' OS=')[0]
            else:
                name_part = uniprot_id
            
            logger.info(f"Fetched sequence for {uniprot_id}: {name_part} ({len(sequence)} aa)")
            
            return {
                'uniprot_id': uniprot_id,
                'name': name_part,
                'sequence': sequence
            }
        else:
            logger.error(f"Failed to fetch {uniprot_id}: HTTP {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Error fetching UniProt sequence {uniprot_id}: {e}")
        return None


def parse_hiperrag_response(rag_response: str) -> List[Dict[str, str]]:
    """
    Parse HiPerRAG response to extract interacting proteins.
    
    Args:
        rag_response: RAG response text
        
    Returns:
        List of dicts with protein_name and uniprot_id
    """
    try:
        # Try to parse as JSON first
        if '{' in rag_response and '}' in rag_response:
            # Extract JSON portion
            start = rag_response.find('{')
            end = rag_response.rfind('}') + 1
            json_str = rag_response[start:end]
            
            data = json.loads(json_str)
            
            # Handle different response formats
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                # Single protein or nested structure
                if 'interacting_protein_name' in data:
                    return [data]
                else:
                    # Might be {protein1: {...}, protein2: {...}}
                    return list(data.values())
        
        # Fallback: manual parsing
        logger.warning("Could not parse as JSON, using fallback parsing")
        return []
        
    except Exception as e:
        logger.error(f"Error parsing HiPerRAG response: {e}")
        return []


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
    rag_result_json['sequences'] = [s['sequence'] for s in sequences]
    logger.info(f"{rag_result_json=}")
    #import sys
    #sys.exit()
    #rag_result_formatted = [{'interaction': name, 'uniprot_id': id, 'sequence':await fetch_uniprot_sequence(id), 'cancer_pathway': cancer_pathway, 'interaction_type': interaction_type, 'therapeutic_rationale': therapeutic_rationale} for name, id, cancer_pathway, interaction_type, therapeutic_rationale in zip(rag_result_json['interactions'], rag_result_json['interacting_protein_uniprot_ids'], rag_result_json['cancer_pathways'], rag_result_json['interaction_types'], rag_result_json['therapeutic_rationales'])]
    
    folding_prompt_manager = get_prompt_manager('chai', research_goal, rag_result_json, target_prot = target_sequence, prompt_type = 'folding', history_list = [], num_history = 3)
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
    """
    system.design_agents['structure_prediction'].generate_binder_hypothesis(folding_result)
    """

    import sys
    sys.exit()



    # Extract response from hypothesis
    rag_response_text = rag_hypothesis.content if hasattr(rag_hypothesis, 'content') else str(rag_hypothesis)

    logger.info(f"✓ HiPerRAG response received")
    logger.info(f"Response preview: {rag_response_text[:300]}...")

    # Parse interacting proteins
    interacting_proteins = parse_hiperrag_response(rag_response_text)
    logger.info(f"✓ Identified {len(interacting_proteins)} interacting proteins")

    # ========================================================================
    # STEP 4: UniProt API → Fetch Sequences
    # ========================================================================
    logger.info("\n[STEP 4] Fetching sequences from UniProt...")

    protein_sequences = {}
    for protein_info in interacting_proteins:
        uniprot_id = protein_info.get('interacting_protein_uniprot_id') or protein_info.get('uniprot_id')
        if uniprot_id:
            seq_data = await fetch_uniprot_sequence(uniprot_id)
            if seq_data:
                protein_sequences[uniprot_id] = seq_data

    logger.info(f"✓ Fetched {len(protein_sequences)} protein sequences")

    # Add NMNAT-2 target sequence
    nmnat2_sequence = "MTETTKTHVILLACGSFNPITKGHIQMFERARDYLHKTGRFIVIGGIVSPVHDSYGKQGLVSSRHRLIMCQLAVQNSDWIRVDPWECYQDTWQTTCSVLEHHRDLMKRVTGCILSNVNTPSMTPVIGQPQNETPQPIYQNSNVATKPTAAKILGKVGESLSRICCVRPPVERFTFVDENANLGTVMRYEEIELRILLLCGSDLLESFCIPGLWNEADMEVIVGDFGIVVVPRDAADTDRIMNHSSILRKYKNNIMVVKDDINHPMSVVSSTKSRLALQHGDGHVVDYLSQPVIDYILKSQLYINASG"
    protein_sequences['Q9BZQ4'] = {
        'uniprot_id': 'Q9BZQ4',
        'name': 'NMNAT2_HUMAN',
        'sequence': nmnat2_sequence
    }

    # ========================================================================
    # STEP 5: Chai Agent → Fold Structures
    # ========================================================================
    logger.info("\n[STEP 5] Folding protein structures with Chai...")

    chai_agent = system.design_agents.get('structure_prediction')
    if not chai_agent:
        logger.error("Chai agent not available!")
        return None

    # Prepare structures to fold: NMNAT-2 + interacting partners
    structures_to_fold = {}
    for uniprot_id, seq_data in protein_sequences.items():
        structures_to_fold[seq_data['name']] = seq_data['sequence']

    logger.info(f"Folding {len(structures_to_fold)} structures...")

    # Fold structures using Chai agent
    # add list of sequences to fold [[target, partner1], [target, partner2]...]
    folded_structures = await chai_agent.fold_proteins(structures_to_fold)
    logger.info(f"✓ Folded {len(folded_structures)} structures")

    # ========================================================================
    # STEP 6: Reasoner → Which Systems to Simulate?
    # ========================================================================
    logger.info("\n[STEP 6] Using Reasoner to select systems for MD simulation...")

    system_selection_prompt = f"""
    We have folded the following protein structures:
    {json.dumps([{'name': name, 'confidence': data.get('confidence', 'N/A')}
                 for name, data in folded_structures.items()], indent=2)}

    Interacting proteins identified from literature:
    {json.dumps(interacting_proteins, indent=2)}

    Target: NMNAT-2 (NMNAT2_HUMAN)

    Task: Select which protein-protein complexes should be simulated with MD to identify binding hotspots.

    Criteria:
    1. High confidence structure predictions
    2. Strong literature evidence for interaction
    3. Relevance to cancer pathways
    4. Computational feasibility (prefer smaller complexes first)

    Return a JSON list of systems to simulate:
    [
      {{
        "protein1": "NMNAT2_HUMAN",
        "protein2": "PARTNER_NAME",
        "rationale": "why simulate this complex",
        "priority": 1-5 (5=highest)
      }}
    ]

    Select 2-4 systems maximum. Return ONLY the JSON array."""

    systems_response = await system.model_manager.generate_with_json_output(
        prompt=system_selection_prompt,
        schema={
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "protein1": {"type": "string"},
                    "protein2": {"type": "string"},
                    "rationale": {"type": "string"},
                    "priority": {"type": "integer"}
                }
            }
        },
        temperature=0.3
    )

    selected_systems = systems_response if isinstance(systems_response, list) else []
    logger.info(f"✓ Selected {len(selected_systems)} systems for MD simulation")
    for sys in selected_systems:
        logger.info(f"  - {sys['protein1']} + {sys['protein2']} (priority: {sys['priority']})")

    # ========================================================================
    # STEP 7: MD Analysis Agent → Simulate & Identify Hotspots
    # ========================================================================
    logger.info("\n[STEP 7] Running MD simulations to identify binding hotspots...")

    md_agent = system.design_agents.get('molecular_dynamics')
    if not md_agent:
        logger.error("MD agent not available!")
        return None

    md_results = {}
    hotspot_residues = {}

    for system_info in selected_systems:
        protein1 = system_info['protein1']
        protein2 = system_info['protein2']
        system_name = f"{protein1}_{protein2}"

        logger.info(f"Simulating {system_name}...")

        # Get structure paths
        struct1_path = folded_structures.get(protein1, {}).get('pdb_path')
        struct2_path = folded_structures.get(protein2, {}).get('pdb_path')

        if not struct1_path or not struct2_path:
            logger.warning(f"Missing structures for {system_name}, skipping")
            continue

        # Run MD simulation
        task_params = {
            'simulation_paths': [Path(struct1_path), Path(struct2_path)],
            'root_output_path': Path(f'./data/md_simulations/{system_name}'),
            'steps': 5000000  # 20 ns
        }

        sim_result = await md_agent.analyze_hypothesis(
            hypothesis=None,  # Will be created internally
            task_params=task_params
        )

        md_results[system_name] = sim_result
        logger.info(f"✓ Completed MD simulation for {system_name}")

    # Analyze MD results to identify hotspots
    logger.info("\nAnalyzing MD trajectories for binding hotspots...")

    # Use the hotspot analysis utility
    from struct_bio_reasoner.utils.hotspot import get_hotspot_resids_from_simulations

    # Collect simulation directories
    sim_directories = [
        Path(f'./data/md_simulations/{system_name}')
        for system_name in md_results.keys()
    ]

    # Analyze hotspots using the utility
    hotspot_resids_dict = get_hotspot_resids_from_simulations(
        sim_directories,
        top_n=10,
        selection1="protein and segid A",  # NMNAT-2
        selection2="protein and segid B",  # Partner protein
        contact_cutoff=4.5,
        contact_frequency_threshold=0.3,
        stride=10
    )

    # Convert to the format expected by the workflow
    for system_name, resids in hotspot_resids_dict.items():
        hotspot_residues[system_name] = resids
        logger.info(f"✓ Identified {len(resids)} hotspot residues in {system_name}: {resids}")

    # ========================================================================
    # STEP 8: Agentic While Loop - Iterative Optimization
    # ========================================================================
    logger.info("\n[STEP 8] Starting agentic optimization loop...")

    iteration = 0
    max_iterations = 10
    continue_optimization = True

    # State tracking
    bindcraft_results = None
    current_peptides = None
    md_simulation_results = {}
    free_energy_results = {}
    best_binders = []

    while continue_optimization and iteration < max_iterations:
        iteration += 1
        logger.info(f"\n{'='*80}")
        logger.info(f"ITERATION {iteration}")
        logger.info(f"{'='*80}")

        # ====================================================================
        # Reasoner: Decide Next Task
        # ====================================================================
        if iteration == 1:
            # First iteration: always use BindCraft
            recommended_task = "bindcraft"
            task_rationale = "Initial iteration - generate peptide binders using BindCraft"
            logger.info(f"[Iteration {iteration}] Hardcoded task: {recommended_task}")
        else:
            # Use LLM reasoner to decide next task
            task_decision_prompt = f"""
            Current state of binder design workflow:

            Iteration: {iteration}
            Hotspot residues identified: {json.dumps(hotspot_residues, indent=2)}

            Previous results:
            - BindCraft results: {bindcraft_results is not None}
            - MD simulations completed: {len(md_simulation_results)}
            - Free energy calculations: {len(free_energy_results)}
            - Best binders found: {len(best_binders)}

            Available tasks:
            1. "bindcraft" - Generate/optimize peptide binders using BindCraft
            2. "md_simulation" - Run MD simulations on peptide-target complexes
            3. "free_energy" - Calculate binding free energies with MM-PBSA
            4. "stop" - Stop optimization and return best binders

            Decide the next task based on:
            - What has been completed
            - What information is still needed
            - Whether we have sufficient high-quality binders

            Return JSON:
            {{
              "task": "bindcraft|md_simulation|free_energy|stop",
              "rationale": "explanation of why this task is needed",
              "confidence": 0.0-1.0
            }}"""

            task_decision = await system.model_manager.generate_with_json_output(
                prompt=task_decision_prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "enum": ["bindcraft", "md_simulation", "free_energy", "stop"]},
                        "rationale": {"type": "string"},
                        "confidence": {"type": "number"}
                    }
                },
                temperature=0.3
            )

            recommended_task = task_decision.get('task', 'stop')
            task_rationale = task_decision.get('rationale', 'No rationale provided')
            logger.info(f"[Iteration {iteration}] Reasoner recommends: {recommended_task}")
            logger.info(f"Rationale: {task_rationale}")

        # ====================================================================
        # Execute Recommended Task
        # ====================================================================

        if recommended_task == "bindcraft":
            logger.info("\n[TASK: BindCraft] Generating/optimizing peptide binders...")

            bindcraft_agent = system.design_agents.get('computational_design')
            if not bindcraft_agent:
                logger.error("BindCraft agent not available!")
                continue

            # Prepare BindCraft task
            bindcraft_task = {
                'target_sequence': nmnat2_sequence,
                'hotspot_residues': hotspot_residues.get('NMNAT2_HUMAN_PARTNER1', []),  # Use first partner's hotspots
                'num_rounds': 3,
                'num_sequences': 25,
                'scaffold_type': 'peptide'  # Could also be 'affibody', 'nanobody', etc.
            }

            bindcraft_results = await bindcraft_agent.generate_binders(bindcraft_task)
            current_peptides = bindcraft_results.get('optimized_sequences', [])
            logger.info(f"✓ BindCraft generated {len(current_peptides)} peptide binders")

        elif recommended_task == "md_simulation":
            logger.info("\n[TASK: MD Simulation] Simulating peptide-target complexes...")

            if not current_peptides:
                logger.warning("No peptides available for MD simulation!")
                continue

            # Run MD simulations on top peptides
            for i, peptide in enumerate(current_peptides[:5]):  # Top 5 peptides
                peptide_id = f"peptide_{iteration}_{i+1}"
                logger.info(f"Simulating {peptide_id}...")

                # Create complex structure (would use Chai to fold peptide-target complex)
                # For now, assume we have the structure

                task_params = {
                    'simulation_paths': [Path(f'./data/peptide_complexes/{peptide_id}.pdb')],
                    'root_output_path': Path(f'./data/md_peptides/{peptide_id}'),
                    'steps': 5000000
                }

                sim_result = await md_agent.analyze_hypothesis(None, task_params)
                md_simulation_results[peptide_id] = sim_result
                logger.info(f"✓ Completed MD for {peptide_id}")

        elif recommended_task == "free_energy":
            logger.info("\n[TASK: Free Energy] Calculating binding free energies...")

            fe_agent = system.design_agents.get('free_energy')
            if not fe_agent:
                logger.error("Free energy agent not available!")
                continue

            # Calculate free energies for simulated peptides
            sim_paths = [Path(f'./data/md_peptides/{pid}') for pid in md_simulation_results.keys()]

            task_params = {
                'simulation_paths': sim_paths
            }

            fe_results = await fe_agent.analyze_hypothesis(None, task_params)
            free_energy_results = fe_results.binding_affinities
            logger.info(f"✓ Calculated free energies for {len(free_energy_results)} peptides")

            # Rank peptides by binding affinity
            ranked_peptides = sorted(
                free_energy_results.items(),
                key=lambda x: x[1]['mean']
            )

            best_binders = ranked_peptides[:5]  # Top 5
            logger.info(f"✓ Top 5 binders identified")

        elif recommended_task == "stop":
            logger.info("\n[TASK: Stop] Reasoner decided to stop optimization")
            continue_optimization = False
            break

        else:
            logger.warning(f"Unknown task: {recommended_task}")
            continue

    # ========================================================================
    # STEP 9: Final Reasoner - Generate Report
    # ========================================================================
    logger.info("\n[STEP 9] Generating final report with best binders...")

    final_report_prompt = f"""
    Generate a comprehensive final report for the NMNAT-2 binder design campaign.

    Workflow completed:
    - Iterations: {iteration}
    - Systems simulated: {len(md_results)}
    - Hotspots identified: {sum(len(h) for h in hotspot_residues.values())}
    - Peptides generated: {len(current_peptides) if current_peptides else 0}
    - MD simulations: {len(md_simulation_results)}
    - Free energy calculations: {len(free_energy_results)}

    Best binders (top 5 by binding affinity):
    {json.dumps([{{'peptide_id': pid, 'delta_g': data['mean'], 'std': data['std']}}
                 for pid, data in best_binders], indent=2)}

    Generate a report including:
    1. Executive summary
    2. Top 5 peptide binders with sequences and binding affinities
    3. Rationale for each binder (why it's promising)
    4. Recommended next steps for experimental validation
    5. Limitations and caveats

    Return as JSON with these fields."""

    final_report = await system.model_manager.generate_with_json_output(
        prompt=final_report_prompt,
        schema={
            "type": "object",
            "properties": {
                "executive_summary": {"type": "string"},
                "top_binders": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "rank": {"type": "integer"},
                            "peptide_id": {"type": "string"},
                            "sequence": {"type": "string"},
                            "binding_affinity_kcal_mol": {"type": "number"},
                            "rationale": {"type": "string"}
                        }
                    }
                },
                "experimental_recommendations": {"type": "array", "items": {"type": "string"}},
                "limitations": {"type": "array", "items": {"type": "string"}}
            }
        },
        temperature=0.5
    )

    logger.info("✓ Final report generated")

    # Save report
    output_dir = Path('./data/nmnat2_workflow_results')
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = output_dir / f"nmnat2_binder_report_{timestamp}.json"

    with open(report_file, 'w') as f:
        json.dump(final_report, f, indent=2)

    logger.info(f"✓ Report saved to {report_file}")

    # ========================================================================
    # Print Summary
    # ========================================================================
    print("\n" + "="*80)
    print("WORKFLOW COMPLETE!")
    print("="*80)
    print(f"\nExecutive Summary:")
    print(final_report['executive_summary'])
    print(f"\nTop 5 Binders:")
    for binder in final_report['top_binders'][:5]:
        print(f"  {binder['rank']}. {binder['peptide_id']}: ΔG = {binder['binding_affinity_kcal_mol']:.2f} kcal/mol")
        print(f"     Sequence: {binder['sequence']}")
        print(f"     Rationale: {binder['rationale']}")
    print(f"\nReport saved to: {report_file}")
    print("="*80 + "\n")

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

