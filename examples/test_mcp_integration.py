#!/usr/bin/env python3
"""
Test MCP Integration with StructBioReasoner

This script demonstrates how to integrate AlphaFold and BioMCP servers
with StructBioReasoner for enhanced protein engineering capabilities.
"""

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

print("🚀 MCP Integration Test Starting...")
print("="*60)

def test_alphafold_server():
    """Test AlphaFold MCP server availability."""
    print("🧪 Testing AlphaFold MCP Server...")
    
    alphafold_path = Path("/tmp/AlphaFold-MCP-Server/build/index.js")
    if alphafold_path.exists():
        print("  ✅ AlphaFold MCP server found")
        return True
    else:
        print("  ❌ AlphaFold MCP server not found")
        return False

def test_biomcp_server():
    """Test BioMCP server availability."""
    print("🧪 Testing BioMCP Server...")
    
    try:
        result = subprocess.run(
            ["biomcp", "--version"], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        if result.returncode == 0:
            print(f"  ✅ BioMCP server found: {result.stdout.strip()}")
            return True
        else:
            print("  ❌ BioMCP server not working")
            return False
    except Exception as e:
        print(f"  ❌ BioMCP server error: {e}")
        return False

def test_biomcp_cli():
    """Test BioMCP CLI functionality."""
    print("🧪 Testing BioMCP CLI functionality...")
    
    try:
        # Test article search
        print("  📚 Testing article search...")
        result = subprocess.run(
            ["biomcp", "article", "search", "--gene", "BRAF", "--limit", "2"], 
            capture_output=True, 
            text=True, 
            timeout=30
        )
        
        if result.returncode == 0:
            print("    ✅ Article search successful")
            # Parse and display results
            try:
                output_lines = result.stdout.strip().split('\n')
                for line in output_lines[-5:]:  # Show last 5 lines
                    if line.strip():
                        print(f"      {line}")
            except:
                pass
        else:
            print(f"    ❌ Article search failed: {result.stderr}")
        
        # Test variant search
        print("  🧬 Testing variant search...")
        result = subprocess.run(
            ["biomcp", "variant", "search", "--gene", "BRAF", "--limit", "2"], 
            capture_output=True, 
            text=True, 
            timeout=30
        )
        
        if result.returncode == 0:
            print("    ✅ Variant search successful")
        else:
            print(f"    ❌ Variant search failed: {result.stderr}")
            
        return True
        
    except Exception as e:
        print(f"  ❌ BioMCP CLI test error: {e}")
        return False

def demonstrate_mcp_capabilities():
    """Demonstrate MCP server capabilities."""
    print("\n🎯 MCP Server Capabilities Demonstration")
    print("="*60)
    
    # Test AlphaFold capabilities
    print("\n📐 AlphaFold MCP Server Capabilities:")
    alphafold_tools = [
        "get_structure - Retrieve protein structure predictions",
        "get_confidence_scores - Get per-residue confidence scores", 
        "search_structures - Search for available structures",
        "batch_structure_info - Process multiple proteins",
        "export_for_pymol - Export for visualization"
    ]
    
    for tool in alphafold_tools:
        print(f"  • {tool}")
    
    # Test BioMCP capabilities  
    print("\n🔬 BioMCP Server Capabilities:")
    biomcp_tools = [
        "search - Unified search across articles, trials, variants",
        "article_searcher - Search PubMed/bioRxiv literature",
        "trial_searcher - Search clinical trials",
        "variant_searcher - Search genetic variants",
        "gene_getter - Get gene information"
    ]
    
    for tool in biomcp_tools:
        print(f"  • {tool}")

def create_integration_example():
    """Create an example of how to integrate MCP servers."""
    print("\n🔗 Integration Example")
    print("="*60)
    
    integration_code = '''
# Example: Comprehensive protein analysis using MCP servers

async def analyze_protein_comprehensive(protein_name: str, uniprot_id: str):
    """Analyze protein using multiple MCP servers."""
    
    # 1. Get AlphaFold structure
    alphafold_data = await mcp_client.call_tool(
        server="alphafold",
        tool="get_structure", 
        params={"uniprotId": uniprot_id, "format": "json"}
    )
    
    # 2. Search biomedical literature
    literature_data = await mcp_client.call_tool(
        server="biomcp",
        tool="search",
        params={"query": f"gene:{protein_name}", "domain": "article"}
    )
    
    # 3. Find clinical trials
    trials_data = await mcp_client.call_tool(
        server="biomcp", 
        tool="search",
        params={"query": f"gene:{protein_name}", "domain": "trial"}
    )
    
    # 4. Get genetic variants
    variants_data = await mcp_client.call_tool(
        server="biomcp",
        tool="search", 
        params={"query": f"gene:{protein_name}", "domain": "variant"}
    )
    
    return {
        "structure": alphafold_data,
        "literature": literature_data,
        "trials": trials_data,
        "variants": variants_data
    }
'''
    
    print(integration_code)

def main():
    """Main test function."""
    print("🧬 MCP Integration Test for StructBioReasoner")
    print("="*60)
    
    # Test server availability
    alphafold_ok = test_alphafold_server()
    biomcp_ok = test_biomcp_server()
    
    if not (alphafold_ok or biomcp_ok):
        print("\n❌ No MCP servers available. Please install them first.")
        return
    
    # Test BioMCP CLI if available
    if biomcp_ok:
        test_biomcp_cli()
    
    # Demonstrate capabilities
    demonstrate_mcp_capabilities()
    
    # Show integration example
    create_integration_example()
    
    # Summary
    print("\n🎉 MCP Integration Test Results")
    print("="*60)
    print(f"✅ AlphaFold MCP Server: {'Available' if alphafold_ok else 'Not Available'}")
    print(f"✅ BioMCP Server: {'Available' if biomcp_ok else 'Not Available'}")
    
    if alphafold_ok or biomcp_ok:
        print("\n🚀 Next Steps for StructBioReasoner Integration:")
        print("1. Create MCP client wrapper classes")
        print("2. Integrate MCP servers into existing agents")
        print("3. Develop orchestration layer for multi-server workflows")
        print("4. Convert existing tools (ESM, RFDiffusion, OpenMM) to MCP servers")
        
        print("\n💡 Benefits of MCP Architecture:")
        print("• Modular and scalable tool integration")
        print("• Language-agnostic server implementations") 
        print("• Standardized protocol for AI-tool communication")
        print("• Easy addition/removal of capabilities")
        print("• Distributed computing possibilities")
    
    print("\n✅ Test Complete!")

if __name__ == "__main__":
    main()
