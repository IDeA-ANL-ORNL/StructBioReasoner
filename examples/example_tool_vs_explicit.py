#!/usr/bin/env python3
"""
Example: Tool Calling vs Explicit Invocation

This script demonstrates the TWO ways to use BindCraft:

1. TOOL CALLING: LLM decides to call BindCraft during hypothesis generation
2. EXPLICIT: You explicitly call BindCraft after hypothesis generation

Both approaches work and can be used together!
"""

import sys
import asyncio
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / '../Jnana'))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def approach_1_tool_calling():
    """
    APPROACH 1: LLM Tool Calling
    
    The LLM decides whether to call BindCraft during hypothesis generation.
    This is OPTIONAL - the LLM may choose to use only literature-based sequences.
    """
    print("\n" + "="*80)
    print("APPROACH 1: LLM TOOL CALLING")
    print("="*80)
    print("The LLM will decide whether to call BindCraft as a tool.\n")
    
    from struct_bio_reasoner.core.binder_design_system import BinderDesignSystem
    
    # Initialize system
    system = BinderDesignSystem(
        config_path="config/binder_config.yaml",
        jnana_config_path="config/test_jnana_config.yaml",
        enable_agents=['computational_design']
    )
    await system.start()
    
    # Research goal that encourages tool use
    research_goal = """
    Design novel peptide binders for SARS-CoV-2 spike protein RBD.
    
    Target sequence: NITNLCPFGEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFKCYGVSPTKLNDLCFTNVYADSFVIRGDEVRQIAPGQTGKIADYNYKLPDDFTGCVIAWNSNNLDSKVGGNYNYLYRLFRKSNLKPFERDISTEIYQAGSTPCNGVEGFNCYFPLQSYGFQPTNGVGYQPYRVVVLSFELLHAPATVCGPKKSTNLVKNKCVNF
    
    Please use computational design tools to generate novel binder sequences.
    """
    
    await system.set_research_goal(research_goal)
    
    # Generate hypothesis - LLM may call bindcraft_design tool
    print("Generating hypothesis (LLM may call tools)...")
    hypothesis = await system.generate_protein_hypothesis(
        research_goal=research_goal,
        strategy="binder_gen"
    )
    
    # Check if tool was called
    print(f"\n✓ Hypothesis generated: {hypothesis.hypothesis_id}")
    
    if hypothesis.has_binder_data():
        binder_data = hypothesis.binder_data
        print(f"\nProposed peptides: {len(binder_data.proposed_peptides)}")
        
        tool_used = False
        for i, pep in enumerate(binder_data.proposed_peptides, 1):
            source = pep.get('source', 'unknown')
            print(f"  {i}. Source: {source}")
            if 'computational' in source.lower() or 'bindcraft' in source.lower():
                tool_used = True
        
        if tool_used:
            print("\n✅ LLM CALLED THE BINDCRAFT TOOL!")
            print("   Hypothesis includes computationally designed sequences.")
        else:
            print("\n📚 LLM used literature-based sequences only.")
    
    await system.stop()
    return hypothesis


async def approach_2_explicit_call():
    """
    APPROACH 2: Explicit BindCraft Call
    
    You explicitly call BindCraft after hypothesis generation.
    This is the traditional approach from example_full_pipeline.py.
    """
    print("\n" + "="*80)
    print("APPROACH 2: EXPLICIT BINDCRAFT CALL")
    print("="*80)
    print("You explicitly call BindCraft after hypothesis generation.\n")
    
    from struct_bio_reasoner.core.binder_design_system import BinderDesignSystem
    
    # Initialize system
    system = BinderDesignSystem(
        config_path="config/binder_config.yaml",
        jnana_config_path="config/test_jnana_config.yaml",
        enable_agents=['computational_design']
    )
    await system.start()
    
    # Research goal (doesn't mention tools)
    research_goal = """
    Design peptide binders for SARS-CoV-2 spike protein RBD based on literature.
    
    Target sequence: NITNLCPFGEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFKCYGVSPTKLNDLCFTNVYADSFVIRGDEVRQIAPGQTGKIADYNYKLPDDFTGCVIAWNSNNLDSKVGGNYNYLYRLFRKSNLKPFERDISTEIYQAGSTPCNGVEGFNCYFPLQSYGFQPTNGVGYQPYRVVVLSFELLHAPATVCGPKKSTNLVKNKCVNF
    """
    
    await system.set_research_goal(research_goal)
    
    # Generate hypothesis (LLM likely won't call tools)
    print("Generating hypothesis...")
    hypothesis = await system.generate_protein_hypothesis(
        research_goal=research_goal,
        strategy="binder_gen"
    )
    
    print(f"\n✓ Hypothesis generated: {hypothesis.hypothesis_id}")
    
    # NOW explicitly call BindCraft
    if hypothesis.has_binder_data():
        binder_data = hypothesis.binder_data
        
        print(f"\nLLM proposed {len(binder_data.proposed_peptides)} peptides from literature.")
        print("\nNow explicitly calling BindCraft to optimize them...")
        
        # Prepare BindCraft config
        bindcraft_config = {
            "target_sequence": binder_data.target_sequence,
            "binder_sequence": binder_data.proposed_peptides[0]["sequence"] if binder_data.proposed_peptides else "",
            "num_rounds": 1,
            "num_seqs": 10,
            "sampling_temp": 0.1
        }
        
        # Explicit BindCraft call
        bindcraft_agent = system.design_agents['computational_design']
        results = await bindcraft_agent.analyze_hypothesis(
            hypothesis,
            bindcraft_config
        )
        
        print(f"\n✅ EXPLICIT BINDCRAFT CALL COMPLETED!")
        print(f"   - Total sequences: {results.total_sequences}")
        print(f"   - Passing sequences: {results.passing_sequences}")
        print(f"   - Success rate: {results.success_rate:.1%}")
    
    await system.stop()
    return hypothesis


async def approach_3_hybrid():
    """
    APPROACH 3: Hybrid (Both!)
    
    LLM may call tools during generation, AND you explicitly call BindCraft.
    This gives you the best of both worlds.
    """
    print("\n" + "="*80)
    print("APPROACH 3: HYBRID (TOOL + EXPLICIT)")
    print("="*80)
    print("LLM may call tools, AND you explicitly call BindCraft.\n")
    
    from struct_bio_reasoner.core.binder_design_system import BinderDesignSystem
    
    # Initialize system
    system = BinderDesignSystem(
        config_path="config/binder_config.yaml",
        jnana_config_path="config/test_jnana_config.yaml",
        enable_agents=['computational_design']
    )
    await system.start()
    
    research_goal = """
    Design peptide binders for SARS-CoV-2 spike protein RBD.
    
    Target: NITNLCPFGEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFKCYGVSPTKLNDLCFTNVYADSFVIRGDEVRQIAPGQTGKIADYNYKLPDDFTGCVIAWNSNNLDSKVGGNYNYLYRLFRKSNLKPFERDISTEIYQAGSTPCNGVEGFNCYFPLQSYGFQPTNGVGYQPYRVVVLSFELLHAPATVCGPKKSTNLVKNKCVNF
    
    Consider using computational tools if helpful.
    """
    
    await system.set_research_goal(research_goal)
    
    # STEP 1: Generate hypothesis (LLM may call tools)
    print("STEP 1: Generating hypothesis (LLM may call tools)...")
    hypothesis = await system.generate_protein_hypothesis(
        research_goal=research_goal,
        strategy="binder_gen"
    )
    
    print(f"\n✓ Hypothesis generated")
    
    # STEP 2: Explicitly call BindCraft for optimization
    if hypothesis.has_binder_data():
        binder_data = hypothesis.binder_data
        
        print(f"\nSTEP 2: Explicitly calling BindCraft for optimization...")
        
        bindcraft_config = {
            "target_sequence": binder_data.target_sequence,
            "binder_sequence": binder_data.proposed_peptides[0]["sequence"] if binder_data.proposed_peptides else "",
            "num_rounds": 3,  # More rounds for optimization
            "num_seqs": 50,   # More sequences
            "sampling_temp": 0.2
        }
        
        bindcraft_agent = system.design_agents['computational_design']
        results = await bindcraft_agent.analyze_hypothesis(
            hypothesis,
            bindcraft_config
        )
        
        print(f"\n✅ HYBRID APPROACH COMPLETED!")
        print(f"   - Initial peptides from LLM: {len(binder_data.proposed_peptides)}")
        print(f"   - Optimized sequences from BindCraft: {results.total_sequences}")
        print(f"   - Final passing sequences: {results.passing_sequences}")
        print(f"\n   This combines LLM reasoning with computational optimization!")
    
    await system.stop()
    return hypothesis


async def main():
    """Run all three approaches"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Tool Calling vs Explicit Invocation")
    parser.add_argument(
        '--approach',
        type=int,
        choices=[1, 2, 3],
        help='Which approach to run (1=tool, 2=explicit, 3=hybrid). If not specified, runs all.'
    )
    args = parser.parse_args()
    
    try:
        if args.approach == 1:
            await approach_1_tool_calling()
        elif args.approach == 2:
            await approach_2_explicit_call()
        elif args.approach == 3:
            await approach_3_hybrid()
        else:
            # Run all approaches
            print("\n" + "🔬"*40)
            print("RUNNING ALL THREE APPROACHES")
            print("🔬"*40)
            
            await approach_1_tool_calling()
            await asyncio.sleep(2)
            
            await approach_2_explicit_call()
            await asyncio.sleep(2)
            
            await approach_3_hybrid()
            
            print("\n" + "="*80)
            print("SUMMARY OF APPROACHES")
            print("="*80)
            print("\n1. TOOL CALLING:")
            print("   - LLM decides when to use BindCraft")
            print("   - Happens during hypothesis generation")
            print("   - Optional and automatic")
            print("   - Good for: Letting LLM make design decisions")
            
            print("\n2. EXPLICIT CALL:")
            print("   - You control when BindCraft runs")
            print("   - Happens after hypothesis generation")
            print("   - Always runs when you call it")
            print("   - Good for: Controlled optimization pipelines")
            
            print("\n3. HYBRID:")
            print("   - Best of both worlds")
            print("   - LLM proposes initial sequences (may use tools)")
            print("   - You run optimization with custom parameters")
            print("   - Good for: Complex iterative workflows")
            print("\n" + "="*80)
        
        print("\n🎉 Example completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

