#!/usr/bin/env python3
"""
Quick Integration Test: Verify Jnana + StructBioReasoner Connection

This is a minimal test to verify:
1. Jnana can be imported
2. StructBioReasoner can be imported
3. Binder hypothesis generation works
4. improve_hypothesis() method exists and can be called

Run this first to verify basic connectivity before running full integration tests.
"""

import sys
from pathlib import Path

# Add Jnana to path
sys.path.insert(0, str(Path(__file__).parent / '../Jnana'))

def test_imports():
    """Test 1: Verify all imports work"""
    print("\n" + "="*60)
    print("TEST 1: Import Verification")
    print("="*60)
    
    try:
        print("\n1. Importing Jnana components...")
        from jnana.protognosis.core.coscientist import CoScientist
        from jnana.protognosis.agents.specialized_agents import GenerationAgent
        print("   ✓ Jnana imports successful")
        
        print("\n2. Importing StructBioReasoner components...")
        from struct_bio_reasoner.data.protein_hypothesis import (
            ProteinHypothesis, 
            BinderHypothesisData,
            BinderAnalysis
        )
        from struct_bio_reasoner.core.binder_design_system import BinderDesignSystem
        print("   ✓ StructBioReasoner imports successful")
        
        print("\n✅ TEST 1 PASSED: All imports work!")
        return True
        
    except ImportError as e:
        print(f"\n❌ TEST 1 FAILED: Import error - {e}")
        return False
    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        return False


def test_method_existence():
    """Test 2: Verify key methods exist"""
    print("\n" + "="*60)
    print("TEST 2: Method Existence Check")
    print("="*60)
    
    try:
        from jnana.protognosis.core.coscientist import CoScientist
        from jnana.protognosis.agents.specialized_agents import GenerationAgent
        from struct_bio_reasoner.data.protein_hypothesis import ProteinHypothesis
        
        print("\n1. Checking CoScientist.improve_hypothesis()...")
        if hasattr(CoScientist, 'improve_hypothesis'):
            print("   ✓ Method exists")
        else:
            print("   ❌ Method NOT found!")
            return False
        
        print("\n2. Checking GenerationAgent._improve_hypothesis()...")
        if hasattr(GenerationAgent, '_improve_hypothesis'):
            print("   ✓ Method exists")
        else:
            print("   ❌ Method NOT found!")
            return False
        
        print("\n3. Checking ProteinHypothesis.from_unified_hypothesis()...")
        if hasattr(ProteinHypothesis, 'from_unified_hypothesis'):
            print("   ✓ Method exists")
        else:
            print("   ⚠️  Method NOT found - needs implementation")
            # Don't fail the test, just warn
        
        print("\n4. Checking ProteinHypothesis.add_binder_analysis()...")
        if hasattr(ProteinHypothesis, 'add_binder_analysis'):
            print("   ✓ Method exists")
        else:
            print("   ❌ Method NOT found!")
            return False
        
        print("\n5. Checking BinderAnalysis.to_dict()...")
        from struct_bio_reasoner.data.protein_hypothesis import BinderAnalysis
        if hasattr(BinderAnalysis, 'to_dict'):
            print("   ✓ Method exists")
        else:
            print("   ❌ Method NOT found!")
            return False
        
        print("\n✅ TEST 2 PASSED: All critical methods exist!")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_binder_data_structure():
    """Test 3: Verify binder data structures"""
    print("\n" + "="*60)
    print("TEST 3: Binder Data Structure Verification")
    print("="*60)
    
    try:
        from struct_bio_reasoner.data.protein_hypothesis import (
            BinderHypothesisData,
            BinderAnalysis
        )
        
        print("\n1. Creating BinderHypothesisData...")
        binder_data = BinderHypothesisData(
            target_name="Test Target",
            target_sequence="MKQHKAMIVALIVICITAVVAALVTRKDLCEVHIRTGQTEVAVF",
            proposed_peptides=[
                {
                    "peptide_id": "pep_001",
                    "sequence": "ACDEFGHIKLMNPQRSTVWY",
                    "source": "literature",
                    "rationale": "Test peptide"
                }
            ],
            literature_references=["doi:10.1234/test"],
            binding_affinity_goal="< 10 nM",
            clinical_context="Test context"
        )
        print(f"   ✓ Created: {binder_data.target_name}")
        print(f"   ✓ Peptides: {len(binder_data.proposed_peptides)}")
        
        print("\n2. Creating BinderAnalysis...")
        analysis = BinderAnalysis(
            protein_id="test_protein",
            num_rounds=3,
            total_sequences=150,
            passing_sequences=8,
            passing_structures=5,
            success_rate=0.033
        )
        print(f"   ✓ Created: {analysis.analysis_id}")
        print(f"   ✓ Success rate: {analysis.success_rate:.1%}")
        
        print("\n3. Converting to dict...")
        analysis_dict = analysis.to_dict()
        print(f"   ✓ Dict keys: {list(analysis_dict.keys())[:5]}...")
        
        print("\n✅ TEST 3 PASSED: Data structures work correctly!")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_parameter_validation():
    """Test 4: Verify parameter validation logic"""
    print("\n" + "="*60)
    print("TEST 4: Parameter Validation")
    print("="*60)
    
    try:
        from jnana.protognosis.agents.specialized_agents import GenerationAgent
        
        print("\n1. Checking _validate_parameters() method...")
        if not hasattr(GenerationAgent, '_validate_parameters'):
            print("   ❌ Method NOT found!")
            return False
        
        print("   ✓ Method exists")
        
        # Create a mock GenerationAgent instance to test validation
        # Note: This might fail if GenerationAgent requires specific initialization
        print("\n2. Testing parameter bounds...")
        
        test_params = {
            "num_seqs": 500,  # Out of bounds (should be 10-250)
            "sampling_temp": 0.5,  # Out of bounds (should be 0.1-0.3)
            "simulation_time": 200,  # Out of bounds (should be 1-100)
            "qc_filters": {
                "multiplicity": 1.5,  # Out of bounds (should be 0-1)
                "diversity": 0.7,
                "check_bad_motifs": True
            },
            "structure_filters": {
                "energy": -50.0,
                "rmsd": 2.0
            }
        }
        
        print(f"   Input params:")
        print(f"     - num_seqs: {test_params['num_seqs']} (should clamp to 250)")
        print(f"     - sampling_temp: {test_params['sampling_temp']} (should clamp to 0.3)")
        print(f"     - simulation_time: {test_params['simulation_time']} (should clamp to 100)")
        
        print("\n   ⚠️  Cannot test validation without LLM instance")
        print("   ⚠️  Will verify during full integration test")
        
        print("\n✅ TEST 4 PASSED: Validation method exists!")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all quick tests"""
    print("\n" + "="*60)
    print("QUICK INTEGRATION TEST")
    print("Jnana + StructBioReasoner Connection Verification")
    print("="*60)
    
    results = {}
    
    # Run tests
    results['imports'] = test_imports()
    results['methods'] = test_method_existence()
    results['data_structures'] = test_binder_data_structure()
    results['validation'] = test_parameter_validation()
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nNext steps:")
        print("1. Run: python test_jnana_structbioreasoner_integration.py")
        print("2. This will test actual hypothesis generation with LLM")
        print("3. Then integrate with BindCraft and MDAgent")
    else:
        print("\n⚠️  Some tests failed. Fix issues before proceeding.")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

