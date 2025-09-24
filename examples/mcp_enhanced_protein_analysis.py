#!/usr/bin/env python3
"""
MCP-Enhanced Protein Analysis Example

This example demonstrates how to use StructBioReasoner with MCP servers
for comprehensive protein engineering analysis.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from struct_bio_reasoner.agents.mcp_enhanced import MCPProteinAgent


async def demonstrate_mcp_protein_analysis():
    """Demonstrate MCP-enhanced protein analysis."""
    
    print("🧬 MCP-Enhanced Protein Analysis Demonstration")
    print("=" * 80)
    
    # Initialize MCP agent
    agent = MCPProteinAgent()
    
    try:
        # Initialize MCP servers
        print("🚀 Initializing MCP servers...")
        if not await agent.initialize():
            print("❌ Failed to initialize MCP servers")
            return
        
        print("✅ MCP servers initialized successfully")
        
        # Test proteins for analysis
        test_proteins = [
            ("BRAF", "P15056", "Improve thermostability for therapeutic applications"),
            ("TP53", "P04637", "Enhance DNA binding activity"),
            ("EGFR", "P00533", "Design selective inhibitor binding sites")
        ]
        
        results = {}
        
        for protein_name, uniprot_id, goal in test_proteins:
            print(f"\n🔬 Analyzing {protein_name} ({uniprot_id})")
            print("-" * 60)
            
            # Comprehensive analysis
            analysis = await agent.analyze_protein_comprehensive(protein_name, uniprot_id)
            
            if "error" not in analysis:
                # Display summary
                summary = analysis.get("analysis_summary", {})
                print(f"📊 Analysis Summary:")
                print(f"  • Data sources: {', '.join(summary.get('data_sources_available', []))}")
                
                for finding_type, finding in summary.get("key_findings", {}).items():
                    print(f"  • {finding_type.title()}: {finding}")
                
                # Generate engineering strategy
                print(f"\n🎯 Generating engineering strategy for: {goal}")
                strategy = await agent.generate_protein_engineering_strategy(
                    protein_name, uniprot_id, goal
                )
                
                if "error" not in strategy:
                    print(f"📋 Engineering Approach:")
                    for approach in strategy.get("engineering_approach", []):
                        print(f"  • {approach['method']}: {approach['description']}")
                
                results[protein_name] = {
                    "analysis": analysis,
                    "strategy": strategy
                }
                
                print("✅ Analysis complete")
            else:
                print(f"❌ Analysis failed: {analysis['error']}")
        
        # Save comprehensive results
        output_file = Path("mcp_enhanced_analysis_results.json")
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Results saved to: {output_file}")
        
        # Display overall summary
        print("\n" + "=" * 80)
        print("🎉 MCP-ENHANCED ANALYSIS COMPLETE!")
        print("=" * 80)
        
        successful_analyses = len([r for r in results.values() if "error" not in r.get("analysis", {})])
        print(f"✅ Successfully analyzed {successful_analyses}/{len(test_proteins)} proteins")
        
        print("\n🔍 Key Capabilities Demonstrated:")
        print("• AlphaFold structure prediction integration")
        print("• Biomedical literature search and analysis")
        print("• Clinical trials identification")
        print("• Genetic variants cataloging")
        print("• Automated engineering strategy generation")
        
        print("\n🚀 Next Steps:")
        print("• Integrate MCP results with existing StructBioReasoner tools")
        print("• Use structure data for molecular dynamics simulations")
        print("• Incorporate literature insights into design decisions")
        print("• Validate engineering strategies experimentally")
        
        return results
        
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        return None
        
    finally:
        # Cleanup
        print("\n🧹 Cleaning up...")
        await agent.cleanup()
        print("✅ Cleanup complete")


async def test_individual_mcp_functions():
    """Test individual MCP functions."""
    
    print("\n🧪 Testing Individual MCP Functions")
    print("=" * 60)
    
    agent = MCPProteinAgent()
    
    try:
        if not await agent.initialize():
            print("❌ Failed to initialize MCP servers")
            return
        
        protein_name = "BRAF"
        uniprot_id = "P15056"
        
        # Test structure prediction
        print("📐 Testing AlphaFold structure prediction...")
        structure = await agent.get_structure_prediction(uniprot_id)
        if structure:
            print("  ✅ Structure prediction successful")
        else:
            print("  ⚠️  Structure prediction not available")
        
        # Test literature search
        print("📚 Testing literature search...")
        literature = await agent.search_protein_literature(protein_name, limit=5)
        if literature and literature.get("articles"):
            print(f"  ✅ Found {len(literature['articles'])} articles")
        else:
            print("  ⚠️  Literature search not available")
        
        # Test clinical trials
        print("🏥 Testing clinical trials search...")
        trials = await agent.find_clinical_trials(protein_name, limit=5)
        if trials:
            print("  ✅ Clinical trials search successful")
        else:
            print("  ⚠️  Clinical trials search not available")
        
        # Test variants
        print("🧬 Testing variants search...")
        variants = await agent.get_genetic_variants(protein_name, limit=5)
        if variants and variants.get("variants"):
            print(f"  ✅ Found {len(variants['variants'])} variants")
        else:
            print("  ⚠️  Variants search not available")
        
    finally:
        await agent.cleanup()


async def main():
    """Main demonstration function."""
    
    print("🧬 StructBioReasoner MCP Integration Test")
    print("=" * 80)
    
    # Run comprehensive analysis
    results = await demonstrate_mcp_protein_analysis()
    
    # Run individual function tests
    await test_individual_mcp_functions()
    
    print("\n" + "=" * 80)
    print("🎉 MCP INTEGRATION DEMONSTRATION COMPLETE!")
    print("=" * 80)
    
    if results:
        print("\n✅ MCP integration is working successfully!")
        print("🔗 StructBioReasoner can now leverage:")
        print("  • AlphaFold structure predictions")
        print("  • Comprehensive biomedical literature")
        print("  • Clinical trials databases")
        print("  • Genetic variant catalogs")
        print("  • Automated analysis workflows")
        
        print("\n💡 This enables:")
        print("  • Evidence-based protein engineering")
        print("  • Literature-informed design decisions")
        print("  • Clinical relevance assessment")
        print("  • Comprehensive variant analysis")
    else:
        print("\n⚠️  Some MCP functions may not be available")
        print("Please ensure MCP servers are properly installed")


if __name__ == "__main__":
    asyncio.run(main())
