#!/usr/bin/env python3
"""
Example: LLM Tool Calling with BindCraft

This script demonstrates how the LLM can call BindCraft as a tool during
hypothesis generation, allowing it to decide when and how to use computational
design.

This is different from example_full_pipeline.py which explicitly calls BindCraft.
Here, the LLM decides whether to call it or not.
"""

import sys
import asyncio
import logging
from pathlib import Path

# Add Jnana to path
sys.path.insert(0, str(Path(__file__).parent / '../Jnana'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def tool_calling_example():
    """
    Demonstrate LLM calling BindCraft as a tool during hypothesis generation.
    
    Workflow:
    1. Initialize BinderDesignSystem (tool registry is auto-created)
    2. Set research goal
    3. Generate hypothesis - LLM may call bindcraft_design tool
    4. Inspect results to see if tool was called
    5. Compare with explicit BindCraft call
    """
    
    print("\n" + "="*80)
    print("LLM TOOL CALLING EXAMPLE")
    print("="*80)
    
    # =========================================================================
    # STEP 1: Initialize BinderDesignSystem
    # =========================================================================
    print("\n[STEP 1] Initializing BinderDesignSystem...")
    
    from struct_bio_reasoner.core.binder_design_system import BinderDesignSystem
    
    system = BinderDesignSystem(
        config_path="config/binder_config.yaml",
        jnana_config_path="config/test_jnana_config.yaml",
        enable_agents=['computational_design']  # Enable BindCraft
    )
    
    await system.start()
    print("✓ System initialized")
    
    # Verify tool registry was created
    if hasattr(system, 'tool_registry'):
        tools = system.tool_registry.list_tools()
        print(f"✓ Tool registry created with {len(tools)} tools: {tools}")
    else:
        print("❌ Tool registry not found!")
        return
    
    # =========================================================================
    # STEP 2: Set Research Goal
    # =========================================================================
    print("\n[STEP 2] Setting research goal...")
    
    research_goal = """
    Design novel peptide binders for the SARS-CoV-2 spike protein receptor binding domain (RBD).
    
    Target sequence: 
    NITNLCPFGEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFKCYGVSPTKLNDLCFTNVYADSFVIRGDEVRQIAPGQTGKIADYNYKLPDDFTGCVIAWNSNNLDSKVGGNYNYLYRLFRKSNLKPFERDISTEIYQAGSTPCNGVEGFNCYFPLQSYGFQPTNGVGYQPYRVVVLSFELLHAPATVCGPKKSTNLVKNKCVNF
    
    Goals:
    - High binding affinity (< 10 nM)
    - Peptide length: 60-70 amino acids
    - Stable structure
    
    You have access to computational design tools. Consider using them to generate
    novel binder sequences in addition to literature-based proposals.
    """
    
    session_id = await system.set_research_goal(research_goal)
    print(f"✓ Research goal set (session: {session_id})")
    
    # =========================================================================
    # STEP 3: Generate Hypothesis with Tool Calling
    # =========================================================================
    print("\n[STEP 3] Generating hypothesis (LLM may call tools)...")
    print("Note: The LLM will decide whether to call bindcraft_design tool")
    print("      based on the research goal and its reasoning.\n")
    
    hypothesis = await system.generate_protein_hypothesis(
        research_goal=research_goal,
        strategy="binder_gen"
    )
    
    print(f"\n✓ Hypothesis generated: {hypothesis.hypothesis_id}")
    print(f"  Title: {hypothesis.title}")
    
    # =========================================================================
    # STEP 4: Inspect Results
    # =========================================================================
    print("\n[STEP 4] Inspecting hypothesis results...")
    
    # Check if hypothesis has binder data
    if hypothesis.has_binder_data():
        binder_data = hypothesis.binder_data
        print(f"\n✓ Binder data found:")
        print(f"  - Target: {binder_data.target_name}")
        print(f"  - Target sequence: {binder_data.target_sequence[:50]}... ({len(binder_data.target_sequence)} residues)")
        print(f"  - Proposed peptides: {len(binder_data.proposed_peptides)}")
        
        # Analyze peptide sources to see if tool was called
        print(f"\n📊 Peptide Sources:")
        tool_called = False
        for i, peptide in enumerate(binder_data.proposed_peptides, 1):
            source = peptide.get('source', 'unknown')
            sequence = peptide.get('sequence', '')
            peptide_id = peptide.get('peptide_id', f'pep_{i}')
            
            print(f"\n  Peptide {i} ({peptide_id}):")
            print(f"    - Source: {source}")
            print(f"    - Sequence: {sequence[:50]}{'...' if len(sequence) > 50 else ''}")
            print(f"    - Length: {len(sequence)} residues")
            print(f"    - Rationale: {peptide.get('rationale', 'N/A')[:100]}...")
            
            # Check if this came from tool
            if 'computational' in source.lower() or 'bindcraft' in source.lower():
                tool_called = True
                print(f"    ⚙️  This peptide was generated by the BindCraft tool!")
        
        # Summary
        print(f"\n{'='*60}")
        if tool_called:
            print("✅ LLM CALLED THE BINDCRAFT TOOL!")
            print("   The hypothesis includes computationally designed sequences.")
        else:
            print("📚 LLM DID NOT CALL THE TOOL")
            print("   The hypothesis includes only literature-based sequences.")
        print(f"{'='*60}")
        
    else:
        print("❌ No binder data found in hypothesis!")
    
    # =========================================================================
    # STEP 5: Compare with Explicit BindCraft Call
    # =========================================================================
    print("\n[STEP 5] Comparing with explicit BindCraft call...")
    print("This shows the difference between tool calling and explicit invocation.\n")
    
    if hypothesis.has_binder_data():
        binder_data = hypothesis.binder_data
        
        # Prepare config for explicit BindCraft call
        bindcraft_config = {
            "target_sequence": binder_data.target_sequence,
            "binder_sequence": binder_data.proposed_peptides[0]["sequence"] if binder_data.proposed_peptides else "",
            "num_rounds": 1,
            "num_seqs": 10,
            "sampling_temp": 0.1
        }
        
        print("Running explicit BindCraft call (as in example_full_pipeline.py)...")
        bindcraft_agent = system.design_agents['computational_design']
        bindcraft_results = await bindcraft_agent.analyze_hypothesis(
            hypothesis,
            bindcraft_config
        )
        
        print(f"\n✓ Explicit BindCraft call completed:")
        print(f"  - Total sequences: {bindcraft_results.total_sequences}")
        print(f"  - Passing sequences: {bindcraft_results.passing_sequences}")
        print(f"  - Success rate: {bindcraft_results.success_rate:.1%}")
        
        print(f"\n{'='*60}")
        print("COMPARISON:")
        print(f"{'='*60}")
        print("Tool Calling (STEP 3):")
        print("  - LLM decides when to call BindCraft")
        print("  - Happens during hypothesis generation")
        print("  - Results integrated into hypothesis automatically")
        print("  - Optional - LLM may choose not to call")
        print()
        print("Explicit Call (STEP 5):")
        print("  - You explicitly call BindCraft")
        print("  - Happens after hypothesis generation")
        print("  - You control parameters directly")
        print("  - Always runs when you call it")
        print(f"{'='*60}")
    
    # =========================================================================
    # STEP 6: Show Hypothesis Metadata
    # =========================================================================
    print("\n[STEP 6] Hypothesis metadata...")
    
    if hypothesis.metadata:
        print(f"\nMetadata keys: {list(hypothesis.metadata.keys())}")
        
        # Check for tool call history (if implemented)
        if 'tool_calls' in hypothesis.metadata:
            print(f"\n🔧 Tool calls made during generation:")
            for tool_call in hypothesis.metadata['tool_calls']:
                print(f"  - {tool_call.get('tool_name')}: {tool_call.get('status')}")
        
        # Show generation strategy
        if 'generation_strategy' in hypothesis.metadata:
            print(f"\nGeneration strategy: {hypothesis.metadata['generation_strategy']}")
    
    # Cleanup
    await system.stop()
    
    return hypothesis


async def minimal_tool_example():
    """
    Minimal example showing just the tool calling part.
    """
    print("\n" + "="*80)
    print("MINIMAL TOOL CALLING EXAMPLE")
    print("="*80)
    
    from struct_bio_reasoner.core.binder_design_system import BinderDesignSystem
    
    # Initialize system
    system = BinderDesignSystem(
        config_path="config/binder_config.yaml",
        jnana_config_path="config/test_jnana_config.yaml",
        enable_agents=['computational_design']
    )
    await system.start()
    
    # Set research goal
    research_goal = """
    Design peptide binders for SARS-CoV-2 spike RBD.
    Target: NITNLCPFGEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFKCYGVSPTKLNDLCFTNVYADSFVIRGDEVRQIAPGQTGKIADYNYKLPDDFTGCVIAWNSNNLDSKVGGNYNYLYRLFRKSNLKPFERDISTEIYQAGSTPCNGVEGFNCYFPLQSYGFQPTNGVGYQPYRVVVLSFELLHAPATVCGPKKSTNLVKNKCVNF
    
    Use computational design tools to generate novel binders.
    """
    
    await system.set_research_goal(research_goal)
    
    # Generate hypothesis - LLM may call tools
    hypothesis = await system.generate_protein_hypothesis(
        research_goal=research_goal,
        strategy="binder_gen"
    )
    
    # Check results
    if hypothesis.has_binder_data():
        print(f"\n✓ Generated {len(hypothesis.binder_data.proposed_peptides)} peptides")
        for i, pep in enumerate(hypothesis.binder_data.proposed_peptides, 1):
            print(f"  {i}. {pep['sequence'][:30]}... (source: {pep['source']})")
    
    await system.stop()
    return hypothesis


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="LLM Tool Calling Example")
    parser.add_argument(
        '--minimal',
        action='store_true',
        help='Run minimal example instead of full example'
    )
    args = parser.parse_args()
    
    try:
        if args.minimal:
            hypothesis = await minimal_tool_example()
        else:
            hypothesis = await tool_calling_example()
        
        if hypothesis:
            print("\n🎉 Example completed successfully!")
            return True
        else:
            print("\n❌ Example failed!")
            return False
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

