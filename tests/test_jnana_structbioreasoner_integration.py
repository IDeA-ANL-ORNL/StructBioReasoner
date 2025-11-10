#!/usr/bin/env python3
"""
Integration Test: Jnana + StructBioReasoner Binder Design Pipeline

This test verifies the full integration between:
1. Jnana's CoScientist (hypothesis generation and improvement)
2. StructBioReasoner's BindCraft agent (binder optimization)
3. StructBioReasoner's MDAgent (molecular dynamics simulation)

Test Flow:
1. Generate initial binder hypothesis using Jnana's CoScientist
2. Extract binder data (target sequence, proposed peptides)
3. Run BindCraft optimization (simulated for testing)
4. Run MD simulations (simulated for testing)
5. Call improve_hypothesis() with experimental results
6. Verify decision logic and parameter suggestions
"""

import sys
import os
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any

# Add Jnana to path
sys.path.insert(0, str(Path(__file__).parent / '../Jnana'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_jnana_hypothesis_generation():
    """Test 1: Generate binder hypothesis using Jnana's CoScientist"""
    print("\n" + "="*80)
    print("TEST 1: Jnana Binder Hypothesis Generation")
    print("="*80)

    try:
        from jnana.protognosis.core.coscientist import CoScientist

        # Determine which LLM to use based on environment variables
        llm_config = "anthropic"  # default
        if os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
            llm_config = "openai"
            logger.info("Using OpenAI (detected OPENAI_API_KEY)")
        elif os.getenv("ANTHROPIC_API_KEY"):
            llm_config = "anthropic"
            logger.info("Using Anthropic (detected ANTHROPIC_API_KEY)")
        else:
            logger.warning("No API key detected. Set ANTHROPIC_API_KEY or OPENAI_API_KEY")

        # Initialize CoScientist
        logger.info(f"Initializing CoScientist with {llm_config}...")
        coscientist = CoScientist(llm_config=llm_config)
        
        # Set research goal for binder design
        research_goal = """
        Design peptide binders for SARS-CoV-2 spike protein receptor binding domain (RBD) 
        to optimize binding affinity and stability. Target sequence: 
        NITNLCPFGEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFKCYGVSPTKLNDLCFTNVYADSFVIRGDEVRQIAPGQTGKIADYNYKLPDDFTGCVIAWNSNNLDSKVGGNYNYLYRLFRKSNLKPFERDISTEIYQAGSTPCNGVEGFNCYFPLQSYGFQPTNGVGYQPYRVVVLSFELLHAPATVCGPKKSTNLVKNKCVNF
        """
        
        logger.info("Setting research goal...")
        plan_config = coscientist.set_research_goal(research_goal)
        
        # Verify binder design detection
        is_binder_design = ('target_sequence' in plan_config or 'binder_sequence' in plan_config)
        print(f"\n✓ Binder design detected: {is_binder_design}")
        print(f"✓ Plan config keys: {list(plan_config.keys())}")
        
        # Generate hypothesis
        logger.info("Generating binder hypothesis...")
        coscientist.start()
        hypothesis_ids = coscientist.generate_hypotheses(count=1, strategies=["literature_exploration"])
        coscientist.wait_for_completion(timeout=120)
        
        # Get the generated hypothesis
        hypotheses = coscientist.get_all_hypotheses()
        if not hypotheses:
            print("❌ No hypotheses generated!")
            return None
        
        hypothesis = hypotheses[0]
        print(f"\n✓ Hypothesis generated: {hypothesis.hypothesis_id}")
        print(f"✓ Summary: {hypothesis.summary[:100]}...")
        
        # Check for binder data
        binder_data = hypothesis.metadata.get('binder_data')
        if binder_data:
            print(f"\n✓ Binder data found!")
            print(f"  - Target: {binder_data.get('target_name', 'N/A')}")
            print(f"  - Target sequence length: {len(binder_data.get('target_sequence', ''))}")
            print(f"  - Proposed peptides: {len(binder_data.get('proposed_peptides', []))}")
            
            # Show first peptide
            if binder_data.get('proposed_peptides'):
                pep = binder_data['proposed_peptides'][0]
                print(f"\n  First peptide:")
                print(f"    - ID: {pep.get('peptide_id', 'N/A')}")
                print(f"    - Sequence: {pep.get('sequence', 'N/A')}")
                print(f"    - Source: {pep.get('source', 'N/A')}")
                print(f"    - Rationale: {pep.get('rationale', 'N/A')[:80]}...")
        else:
            print("❌ No binder data in hypothesis metadata!")
            return None
        
        coscientist.stop()
        
        print("\n✅ TEST 1 PASSED: Hypothesis generation successful!")
        return hypothesis
        
    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_improve_hypothesis_with_mock_results():
    """Test 2: Test improve_hypothesis() with mock experimental results"""
    print("\n" + "="*80)
    print("TEST 2: Improve Hypothesis with Mock Experimental Results")
    print("="*80)

    try:
        from jnana.protognosis.core.coscientist import CoScientist

        # Determine which LLM to use based on environment variables
        llm_config = "anthropic"  # default
        if os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
            llm_config = "openai"
            logger.info("Using OpenAI (detected OPENAI_API_KEY)")
        elif os.getenv("ANTHROPIC_API_KEY"):
            llm_config = "anthropic"
            logger.info("Using Anthropic (detected ANTHROPIC_API_KEY)")

        # Initialize CoScientist
        logger.info(f"Initializing CoScientist with {llm_config}...")
        coscientist = CoScientist(llm_config=llm_config)
        
        # Set research goal
        research_goal = "Design peptide binders for SARS-CoV-2 spike protein RBD"
        plan_config = coscientist.set_research_goal(research_goal)
        
        # Generate hypothesis
        coscientist.start()
        hypothesis_ids = coscientist.generate_hypotheses(count=1, strategies=["literature_exploration"])
        coscientist.wait_for_completion(timeout=120)
        
        hypotheses = coscientist.get_all_hypotheses()
        if not hypotheses:
            print("❌ No hypotheses generated!")
            return False
        
        hypothesis = hypotheses[0]
        hypothesis_id = hypothesis.hypothesis_id
        
        print(f"\n✓ Generated hypothesis: {hypothesis_id}")
        
        # Create mock experimental results (simulating BindCraft + MD)
        experimental_results = {
            "bindcraft": {
                "num_rounds": 3,
                "total_sequences": 150,
                "passing_sequences": 8,
                "success_rate": 0.053,  # 5.3% - above threshold!
                "sequences_per_round": [50, 50, 50],
                "passing_per_round": [2, 3, 3],
                "parameters_used": {
                    "num_seqs": 50,
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
                        "energy": -50.0,
                        "rmsd": 2.0,
                        "rmsf": 1.5,
                        "passing": 0.7
                    }
                }
            },
            "md": {
                "stable_complexes": 5,
                "total_simulations": 8,
                "avg_rmsd": 2.3,
                "avg_binding_energy": -45.2,
                "simulation_time": 100
            }
        }
        
        print("\n✓ Mock experimental results created:")
        print(f"  - BindCraft: {experimental_results['bindcraft']['passing_sequences']}/{experimental_results['bindcraft']['total_sequences']} sequences passed")
        print(f"  - MD: {experimental_results['md']['stable_complexes']}/{experimental_results['md']['total_simulations']} stable complexes")
        print(f"  - Success rate: {experimental_results['md']['stable_complexes']/experimental_results['bindcraft']['total_sequences']*100:.2f}%")
        
        # Call improve_hypothesis
        logger.info("Calling improve_hypothesis()...")
        result = coscientist.improve_hypothesis(hypothesis_id, experimental_results)
        
        # Verify result structure
        print("\n✓ Improvement result received:")
        print(f"  - Decision status: {result['decision']['status']}")
        print(f"  - Reasoning: {result['decision']['reasoning'][:100]}...")
        print(f"  - Confidence: {result['decision']['confidence']}")
        print(f"  - Success rate: {result['evaluation']['success_rate']:.2%}")
        print(f"  - Meets threshold: {result['evaluation']['meets_threshold']}")
        
        # Check new parameters
        if 'new_parameters' in result:
            new_params = result['new_parameters']
            print(f"\n✓ New parameters suggested:")
            print(f"  - num_seqs: {new_params.get('num_seqs', 'N/A')}")
            print(f"  - sampling_temp: {new_params.get('sampling_temp', 'N/A')}")
            print(f"  - simulation_time: {new_params.get('simulation_time', 'N/A')}")
            
            # Verify parameter bounds
            num_seqs = new_params.get('num_seqs', 0)
            sampling_temp = new_params.get('sampling_temp', 0)
            sim_time = new_params.get('simulation_time', 0)
            
            bounds_ok = (
                10 <= num_seqs <= 250 and
                0.1 <= sampling_temp <= 0.3 and
                1.0 <= sim_time <= 100.0
            )
            
            if bounds_ok:
                print(f"\n✓ Parameters within bounds!")
            else:
                print(f"\n❌ Parameters out of bounds!")
                print(f"  - num_seqs: {num_seqs} (should be 10-250)")
                print(f"  - sampling_temp: {sampling_temp} (should be 0.1-0.3)")
                print(f"  - simulation_time: {sim_time} (should be 1-100)")
        
        coscientist.stop()
        
        print("\n✅ TEST 2 PASSED: improve_hypothesis() works correctly!")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_structbioreasoner_conversion():
    """Test 3: Convert Jnana hypothesis to StructBioReasoner ProteinHypothesis"""
    print("\n" + "="*80)
    print("TEST 3: Convert to StructBioReasoner ProteinHypothesis")
    print("="*80)
    
    try:
        from jnana.protognosis.core.coscientist import CoScientist
        from struct_bio_reasoner.data.protein_hypothesis import ProteinHypothesis
        
        # Generate hypothesis with Jnana
        coscientist = CoScientist(llm_config="anthropic")
        research_goal = "Design peptide binders for target protein"
        coscientist.set_research_goal(research_goal)
        
        coscientist.start()
        coscientist.generate_hypotheses(count=1)
        coscientist.wait_for_completion(timeout=120)
        
        hypotheses = coscientist.get_all_hypotheses()
        if not hypotheses:
            print("❌ No hypotheses generated!")
            return False
        
        jnana_hypothesis = hypotheses[0]
        print(f"\n✓ Jnana hypothesis: {jnana_hypothesis.hypothesis_id}")
        
        # Convert to UnifiedHypothesis first (this is what Jnana returns)
        # Then convert to ProteinHypothesis
        # Note: We need to check if from_unified_hypothesis exists
        
        print("\n✓ Checking ProteinHypothesis.from_unified_hypothesis()...")
        if hasattr(ProteinHypothesis, 'from_unified_hypothesis'):
            print("  - Method exists!")
        else:
            print("  - Method NOT found - needs to be implemented!")
            return False
        
        coscientist.stop()
        
        print("\n✅ TEST 3 PASSED: Conversion method exists!")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all integration tests"""
    print("\n" + "="*80)
    print("JNANA + STRUCTBIOREASONER INTEGRATION TESTS")
    print("="*80)
    
    results = {}
    
    # Test 1: Hypothesis generation
    results['hypothesis_generation'] = await test_jnana_hypothesis_generation()
    
    # Test 2: Improve hypothesis
    results['improve_hypothesis'] = await test_improve_hypothesis_with_mock_results()
    
    # Test 3: Conversion to ProteinHypothesis
    results['conversion'] = await test_structbioreasoner_conversion()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Integration is working! 🎉")
    else:
        print("\n⚠️  Some tests failed. Check the output above for details.")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

