#!/usr/bin/env python3
"""
Example: Full Binder Design Pipeline

This script demonstrates how the complete integration will work once all phases are implemented.

Current Status:
- ✅ Phase 1: Data structures (complete)
- ✅ Phase 2: CoScientist integration (complete)
- ⏳ Phase 3: ProtoGnosis adapter (TODO)
- ⏳ Phase 4-6: BindCraft, MDAgent, orchestration (TODO)

This is a REFERENCE IMPLEMENTATION showing the intended workflow.
Some parts are marked as TODO and will be implemented in future phases.
"""

import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Add Jnana to path
sys.path.insert(0, str(Path(__file__).parent / '../Jnana'))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from struct_bio_reasoner.utils.cleanup_queue import cleanup_all_queues

async def full_binder_design_pipeline():
    """
    Complete binder design pipeline integrating Jnana + StructBioReasoner.
    
    Workflow:
    1. Initialize BinderDesignSystem
    2. Generate initial hypothesis with CoScientist
    3. Run iterative optimization loop:
       a. BindCraft optimization
       b. MD simulation
       c. Evaluate results with improve_hypothesis()
       d. Decide: continue or complete
       e. If continue, adjust parameters and repeat
    4. Return final optimized hypothesis
    """
    
    logger.info("\n" + "="*80)
    logger.info("FULL BINDER DESIGN PIPELINE")
    logger.info("="*80)
    
    # =========================================================================
    # STEP 1: Initialize BinderDesignSystem
    # =========================================================================
    logger.info("\n[STEP 1] Initializing BinderDesignSystem...")
    
    from struct_bio_reasoner.core.binder_design_system import BinderDesignSystem
    
    system = BinderDesignSystem(
        config_path="config/binder_config.yaml",
        jnana_config_path="config/test_jnana_config.yaml",
        enable_agents=['computational_design', 'molecular_dynamics']
    )
    
    await system.start()
    logger.info("✓ System initialized")
    
    # =========================================================================
    # STEP 2: Set Research Goal
    # =========================================================================
    logger.info("\n[STEP 2] Setting research goal...")
    
    research_goal = """
    Design affibody and only affibody for Q9BZQ4|NMNA2_HUMAN Nicotinamide/nicotinic acid mononucleotide adenylyltransferase 2 OS=Homo sapiens OX=9606 GN=NMNAT2 PE=1 SV=1 
    to optimize binding affinity and stability. Target sequence: 
    MTETTKTHVILLACGSFNPITKGHIQMFERARDYLHKTGRFIVIGGIVSPVHDSYGKQGLVSSRHRLIMCQLAVQNSDWIRVDPWECYQDTWQTTCSVLEHHRDLMKRVTGCILSNVNTPSMTPVIGQPQNETPQPIYQNSNVATKPTAAKILGKVGESLSRICCVRPPVERFTFVDENANLGTVMRYEEIELRILLLCGSDLLESFCIPGLWNEADMEVIVGDFGIVVVPRDAADTDRIMNHSSILRKYKNNIMVVKDDINHPMSVVSSTKSRLALQHGDGHVVDYLSQPVIDYILKSQLYINASG
    
    Goals:
    - Binding affinity < 10 nM
    - Stable complex in MD simulation (RMSD < 3 Å)
    - High success rate (>5% of generated sequences)
    """
    
    session_id = await system.set_research_goal(research_goal)
    logger.info(f"✓ Research goal set (session: {session_id})")
    
    # =========================================================================
    # STEP 3: Generate Initial Hypothesis with CoScientist
    # =========================================================================
    logger.info("\n[STEP 3] Generating initial hypothesis with CoScientist...")
    
    # TODO (Phase 3): Implement this in ProtoGnosisAdapter
    # For now, this shows the intended interface
    
    # This will call:
    # 1. Jnana's CoScientist to generate hypothesis
    # 2. Extract binder data from metadata
    # 3. Convert to ProteinHypothesis
    hyp_count=0
    while hyp_count<1:
        try:
            initial_hypothesis = await system.generate_protein_hypothesis(
                research_goal=research_goal,
                strategy="binder_gen"#"coscientist_binder_design"  # New strategy for binder design
            )
            if initial_hypothesis!=None:
                hyp_count+=1
        except:
            continue
    logger.info(f"✓ Initial hypothesis generated: {initial_hypothesis.hypothesis_id}")
    logger.info(f"  - Title: {initial_hypothesis.title}")
    logger.info(initial_hypothesis.binder_data)
    # Verify binder data
    #if initial_hypothesis.has_binder_data():
    binder_data = initial_hypothesis.binder_data
    #print(f"  - Target: {binder_data.target_name}")
    #print(f"  - Proposed peptides: {len(binder_data.proposed_peptides)}")
    #else:
    #    print("  ❌ No binder data found!")
    #    return None
    
    # =========================================================================
    # STEP 4: Iterative Optimization Loop
    # =========================================================================
    logger.info("\n[STEP 4] Starting iterative optimization loop...")
    
    max_iterations = 5
    current_hypothesis = initial_hypothesis
    iteration = 0
    
    # Initial parameters
    parameters = {
        "num_seq": 5,
        "sampling_temp": 0.2,
        "qc_filters": {
            "multiplicity": 0.5,
            "diversity": 0.7,
            "repeat": 0.3,
            "charge_ratio": 0.5,
            "check_bad_motifs": True,
            "net_charge": 0.4,
            "bad_terminus": True,
            "hydrophobicity": 0.6,
            "passing": 0.8
        },
        "structure_filters": {
            "energy": -10.0,
            "rmsd": 2.0,
            "rmsf": 1.5,
            "passing": 0.7
        },
        "simulation_time": 10  # ns
    }
    
    if False:
        await cleanup_all_queues()
    
    while iteration < 1:#max_iterations:
        iteration += 1
        logger.info(f"\n{'='*60}")
        logger.info(f"ITERATION {iteration}/{max_iterations}")
        logger.info(f"{'='*60}")
        
        # ---------------------------------------------------------------------
        # STEP 4a: Run BindCraft Optimization
        # ---------------------------------------------------------------------
        logger.info(f"\n[{iteration}.a] Running BindCraft optimization...")
        logger.info(f"  Parameters:")
        logger.info(f"    - sampling_temp: {parameters['sampling_temp']}")
        logger.info(f"    - simulation_time: {parameters['simulation_time']} ns")
        
        # Get binder data for BindCraft
        # NOTE: Use direct attribute access instead of get_binder_data()
        if not current_hypothesis.has_binder_data():
            logger.info("  ❌ No binder data found in hypothesis!")
            break

        binder_data = current_hypothesis.binder_data

        logger.info("\n📊 Binder Information:")
        #print(f"  - Target sequence: {binder_data.target_sequence[:50]}... ({len(binder_data.target_sequence)} residues)")
        logger.info(f"  - Proposed peptides: {len(binder_data['proposed_peptides'])}")
        #if binder_data.proposed_peptides:
        #    print(f"  - First peptide: {binder_data.proposed_peptides[0]['sequence'][:50]}...")

        target_sequence = system._extract_target_sequence(research_goal)
        # Prepare BindCraft config
        # NOTE: The BindCraft agent will automatically extract sequences from hypothesis.binder_data
        # We can also pass them explicitly in the config (they will override if present)
        parsl_config = {
            'available_accelerators': [i for i in range(12)],
            'nodes': 1
        }
        bindcraft_config = {
            # These will be extracted from hypothesis.binder_data by BindCraft agent
            # but we include them here for clarity and as fallback
            "target_sequence": target_sequence,
            "binder_sequence": binder_data['proposed_peptides'][0]["sequence"] if binder_data['proposed_peptides'] else None,
            "num_rounds": 1,
            "num_seq": parameters["num_seq"],
            "sampling_temp": parameters["sampling_temp"],
            "qc_filters": parameters["qc_filters"],
            "structure_filters": parameters["structure_filters"]
        }
        
        logger.info(f"{bindcraft_config=}")
        # Run BindCraft
        logger.info(system.design_agents)
        bindcraft_agent = system.design_agents['computational_design']
        
        if False: # placing False since this is under heavy maintenance
            #cosci.stop()
            bindcraft_results = await bindcraft_agent.analyze_hypothesis(
                current_hypothesis,
                bindcraft_config
            )
        
            logger.info(f"  ✓ BindCraft complete:")
            logger.info(f"    - Total sequences: {bindcraft_results.total_sequences}")
            logger.info(f"    - Passing sequences: {bindcraft_results.passing_sequences}")
            logger.info(f"    - Passing structures: {bindcraft_results.passing_structures}")
            logger.info(f"    - Success rate: {bindcraft_results.success_rate:.1%}")
            
            # Add results to hypothesis
            current_hypothesis.add_binder_analysis(bindcraft_results)
        
        if True:
            from struct_bio_reasoner.data.protein_hypothesis import BinderAnalysis
            bindcraft_results = BinderAnalysis(protein_id="X",
                                    num_rounds = 1,
                                    total_sequences = 1000,
                                    passing_sequences = 800,
                                    passing_structures = 50,
                                    success_rate = 0.05,
                                    checkpoint_file = '')
            recommendation = await system.generate_recommendation(bindcraft_results)
            logger.info(f"Recommendation: {recommendation}")
        
        if True:
            previous_run_config ={
                "target_sequence": target_sequence,
                "binder_sequence": binder_data['proposed_peptides'][0]["sequence"] if binder_data['proposed_peptides'] else None,
                "num_rounds": 1,
                "num_seq": parameters["num_seq"],
                "sampling_temp": parameters["sampling_temp"],
                "qc_filters": parameters["qc_filters"],
                "structure_filters": parameters["structure_filters"]
            }
            previous_run_type = 'bindcraft'    
            
            await system.generate_recommendedconfig(previous_run_type,
                                previous_run_config,
                                recommendation)

        import sys
        sys.exit()
        # ---------------------------------------------------------------------
        # STEP 4b: Run MD Simulations
        # ---------------------------------------------------------------------
        logger.info(f"\n[{iteration}.b] Running MD simulations...")
        
        md_agent = system.design_agents['molecular_dynamics']
        md_results = await md_agent.analyze_hypothesis(
            current_hypothesis,
            {"simulation_time": parameters["simulation_time"]}
        )
        
        # Extract MD metrics
        stable_complexes = md_results.get('stable_complexes', 0)
        total_simulations = md_results.get('total_simulations', 0)
        avg_rmsd = md_results.get('avg_rmsd', 0.0)
        avg_energy = md_results.get('avg_binding_energy', 0.0)
        
        logger.info(f"  ✓ MD simulations complete:")
        logger.info(f"    - Stable complexes: {stable_complexes}/{total_simulations}")
        logger.info(f"    - Average RMSD: {avg_rmsd:.2f} Å")
        logger.info(f"    - Average binding energy: {avg_energy:.2f} kcal/mol")
        
        # Add MD results to hypothesis
        current_hypothesis.add_md_analysis(md_results)
        
        # ---------------------------------------------------------------------
        # STEP 4c: Evaluate Results with CoScientist
        # ---------------------------------------------------------------------
        logger.info(f"\n[{iteration}.c] Evaluating results with CoScientist...")
        
        # Prepare experimental results for improve_hypothesis()
        experimental_results = {
            "bindcraft": {
                "num_rounds": bindcraft_results.num_rounds,
                "total_sequences": bindcraft_results.total_sequences,
                "passing_sequences": bindcraft_results.passing_sequences,
                "success_rate": bindcraft_results.success_rate,
                "sequences_per_round": bindcraft_results.sequences_per_round,
                "passing_per_round": bindcraft_results.passing_per_round,
                "parameters_used": parameters
            },
            "md": {
                "stable_complexes": stable_complexes,
                "total_simulations": total_simulations,
                "avg_rmsd": avg_rmsd,
                "avg_binding_energy": avg_energy,
                "simulation_time": parameters["simulation_time"]
            }
        }
        
        # Call improve_hypothesis through Jnana's CoScientist
        # TODO (Phase 3): This should be called through ProtoGnosisAdapter
        from jnana.protognosis.core.coscientist import CoScientist
        
        coscientist = system.coscientist  # Assuming system has coscientist instance
        improvement_result = coscientist.improve_hypothesis(
            current_hypothesis.hypothesis_id,
            experimental_results
        )
        
        decision = improvement_result['decision']
        evaluation = improvement_result['evaluation']
        
        logger.info(f"  ✓ Evaluation complete:")
        logger.info(f"    - Status: {decision['status']}")
        logger.info(f"    - Success rate: {evaluation['success_rate']:.2%}")
        logger.info(f"    - Meets threshold: {evaluation['meets_threshold']}")
        logger.info(f"    - Reasoning: {decision['reasoning'][:100]}...")
        
        # ---------------------------------------------------------------------
        # STEP 4d: Decide Next Action
        # ---------------------------------------------------------------------
        logger.info(f"\n[{iteration}.d] Decision: {decision['status'].upper()}")
        
        if decision['status'] == 'complete':
            logger.info(f"\n✅ Optimization complete!")
            logger.info(f"   Final success rate: {evaluation['success_rate']:.2%}")
            logger.info(f"   Confidence: {decision['confidence']:.2f}")
            break
        
        elif decision['status'] == 'continue':
            logger.info(f"\n⏭️  Continuing optimization...")
            
            # Update parameters based on CoScientist's suggestions
            new_parameters = improvement_result['new_parameters']
            parameter_reasoning = improvement_result['parameter_reasoning']
            
            logger.info(f"   Parameter adjustments:")
            for param, value in new_parameters.items():
                if param in parameters and parameters[param] != value:
                    old_val = parameters[param]
                    logger.info(f"     - {param}: {old_val} → {value}")
                    if param in parameter_reasoning:
                        logger.info(f"       Reason: {parameter_reasoning[param][:80]}...")
            
            # Update parameters for next iteration
            parameters.update(new_parameters)
            
            # Create child hypothesis for next iteration
            # TODO (Phase 1): Use parent-child tracking
            child_hypothesis = current_hypothesis.create_child_hypothesis(
                title=f"Binder Design Iteration {iteration + 1}",
                content=f"Optimized parameters based on iteration {iteration} results",
                metadata={"iteration": iteration + 1, "parameters": parameters}
            )
            
            current_hypothesis = child_hypothesis
            logger.info(f"   Created child hypothesis: {child_hypothesis.hypothesis_id}")
        
        else:
            logger.info(f"\n❌ Unknown decision status: {decision['status']}")
            break
    
    # =========================================================================
    # STEP 5: Return Final Results
    # =========================================================================
    logger.info("\n" + "="*80)
    logger.info("FINAL RESULTS")
    logger.info("="*80)
    
    logger.info(f"\nFinal hypothesis: {current_hypothesis.hypothesis_id}")
    logger.info(f"Total iterations: {iteration}")
    logger.info(f"Lineage depth: {current_hypothesis.get_lineage_depth()}")
    
    # Get lineage info
    lineage = current_hypothesis.get_lineage_info()
    logger.info(f"\nHypothesis lineage:")
    logger.info(f"  - Root: {lineage['root_id']}")
    logger.info(f"  - Parent: {lineage['parent_id']}")
    logger.info(f"  - Depth: {lineage['depth']}")
    logger.info(f"  - Children: {len(lineage['children_ids'])}")
    
    # Get final binder analysis
    if current_hypothesis.binder_analysis:
        analysis = current_hypothesis.binder_analysis
        logger.info(f"\nFinal binder analysis:")
        logger.info(f"  - Total sequences: {analysis.total_sequences}")
        logger.info(f"  - Passing sequences: {analysis.passing_sequences}")
        logger.info(f"  - Success rate: {analysis.success_rate:.2%}")
        logger.info(f"  - Confidence: {analysis.confidence_score:.2f}")
    
    # Cleanup
    await system.stop()
    
    return current_hypothesis


async def main():
    """Main entry point"""
    try:
        final_hypothesis = await full_binder_design_pipeline()
        
        if final_hypothesis:
            print("\n🎉 Pipeline completed successfully!")
            return True
        else:
            print("\n❌ Pipeline failed!")
            return False
            
    except Exception as e:
        print(f"\n❌ Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

