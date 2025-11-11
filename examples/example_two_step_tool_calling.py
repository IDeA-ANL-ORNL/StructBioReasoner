"""
Example demonstrating the two-step tool calling approach.

This shows how the LLM can actually call BindCraft during hypothesis generation
using the two-step approach:
1. Generate initial hypothesis (structured JSON)
2. Ask LLM if it wants to use tools (function calling)
3. Execute tools and incorporate results

This overcomes the OpenAI API limitation where you can't use both
`tools` and `response_format: json_object` simultaneously.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent / '../Jnana'))

from struct_bio_reasoner.core.binder_design_system import BinderDesignSystem
from struct_bio_reasoner.utils.config_loader import load_binder_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """
    Demonstrate two-step tool calling for binder design.
    """
    print("\n" + "="*80)
    print("TWO-STEP TOOL CALLING DEMONSTRATION")
    print("="*80 + "\n")
    
    # Initialize the system
    print("📦 Step 1: Initializing BinderDesignSystem...")
    system = BinderDesignSystem(
        config_path="config/binder_config.yaml",
        jnana_config_path="../Jnana/config/config.yaml"
    )
    await system.initialize()
    print("✓ System initialized\n")
    
    # Define research goal
    research_goal = """
    Design a peptide binder for SARS-CoV-2 spike protein receptor binding domain (RBD).
    The binder should have high affinity and specificity for the RBD to potentially
    block ACE2 interaction.
    """
    
    print("🎯 Research Goal:")
    print(research_goal)
    print()
    
    # Generate hypothesis with tool calling
    print("🧬 Step 2: Generating hypothesis with LLM tool calling enabled...")
    print("   This will:")
    print("   1. Generate initial hypothesis (literature/homology/de-novo)")
    print("   2. Ask LLM if it wants to use computational tools")
    print("   3. If yes, execute BindCraft and incorporate results")
    print()
    
    hypothesis = await system.generate_protein_hypothesis(
        research_goal=research_goal,
        strategy="binder_gen"
    )
    
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80 + "\n")
    
    # Display hypothesis
    print(f"📋 Hypothesis: {hypothesis.summary}\n")
    
    # Check if tools were called
    if hypothesis.metadata.get("tool_calls_made"):
        print("✅ TOOL CALLING SUCCESSFUL!")
        print(f"   Number of tool calls: {hypothesis.metadata.get('tool_call_count', 0)}")
        print()
    else:
        print("ℹ️  No tools were called (LLM decided not to use them)")
        print()
    
    # Display binder data
    if hasattr(hypothesis, 'binder_data') and hypothesis.binder_data:
        binder_data = hypothesis.binder_data
        print(f"🎯 Target: {binder_data.target_name}")
        print(f"   Sequence: {binder_data.target_sequence[:50]}...")
        print()
        
        print(f"🧬 Proposed Peptides: {len(binder_data.proposed_peptides)}")
        
        # Count by source
        sources = {}
        for peptide in binder_data.proposed_peptides:
            source = peptide.get('source', 'unknown')
            sources[source] = sources.get(source, 0) + 1
        
        print("\n   Sources breakdown:")
        for source, count in sources.items():
            emoji = "🔬" if "computational" in source else "📚"
            print(f"   {emoji} {source}: {count} sequences")
        
        print("\n   Sample sequences:")
        for i, peptide in enumerate(binder_data.proposed_peptides[:5], 1):
            source = peptide.get('source', 'unknown')
            sequence = peptide.get('sequence', '')
            rationale = peptide.get('rationale', '')[:80]
            
            emoji = "🔬" if "computational" in source else "📚"
            print(f"\n   {i}. {emoji} Source: {source}")
            print(f"      Sequence: {sequence[:60]}...")
            print(f"      Rationale: {rationale}...")
            
            # Show tool metadata if available
            if 'tool_metadata' in peptide:
                metadata = peptide['tool_metadata']
                print(f"      Metrics: pLDDT={metadata.get('plddt', 'N/A')}, "
                      f"pAE={metadata.get('pae', 'N/A')}, "
                      f"pTM={metadata.get('ptm', 'N/A')}")
    
    print("\n" + "="*80)
    print("ANALYSIS")
    print("="*80 + "\n")
    
    # Analyze the results
    if hypothesis.metadata.get("tool_calls_made"):
        print("✅ SUCCESS: LLM successfully called BindCraft tool!")
        print()
        print("What happened:")
        print("1. ✓ LLM generated initial hypothesis with literature-based sequences")
        print("2. ✓ LLM was asked if it wanted to use computational tools")
        print("3. ✓ LLM decided to call bindcraft_design tool")
        print("4. ✓ BindCraft executed and generated sequences")
        print("5. ✓ Results were incorporated into hypothesis")
        print()
        print("Result: Hypothesis contains BOTH literature AND computational sequences!")
    else:
        print("ℹ️  LLM chose not to use tools")
        print()
        print("This could mean:")
        print("- LLM was satisfied with literature-based sequences")
        print("- LLM didn't think computational design was necessary")
        print("- Tool calling prompt needs adjustment")
        print()
        print("Note: You can still explicitly call BindCraft after hypothesis generation")
    
    print("\n" + "="*80)
    print("NEXT STEPS")
    print("="*80 + "\n")
    
    print("You can now:")
    print("1. Run MD simulations on the proposed peptides")
    print("2. Evaluate binding affinity")
    print("3. Iterate with CoScientist to improve designs")
    print("4. Export results for experimental validation")
    
    return hypothesis


if __name__ == "__main__":
    asyncio.run(main())

