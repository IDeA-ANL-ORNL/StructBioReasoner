#!/usr/bin/env python3
"""
Phase 3 Paper2Agent Demonstration

This example demonstrates the complete Phase 3 Paper2Agent system:
1. Processing scientific papers to extract methodologies
2. Generating MCP tools from paper methodologies
3. Auto-generating code for missing functionality
4. Deploying tools as callable MCP services
5. Integration with existing agentic systems

This represents the next evolution of the StructBioReasoner framework.
"""

import asyncio
import logging
from pathlib import Path
from datetime import datetime
import json

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from struct_bio_reasoner.paper2agent.paper2agent_orchestrator import (
    Paper2AgentOrchestrator, Paper2AgentConfig, PaperSource
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Phase3Demo:
    """Demonstration of Phase 3 Paper2Agent system."""
    
    def __init__(self):
        # Setup configuration
        self.base_dir = Path(__file__).parent.parent
        self.config = Paper2AgentConfig(
            papers_directory=self.base_dir / "paper2agent_papers",
            tools_output_directory=self.base_dir / "paper2agent_tools",
            generated_code_directory=self.base_dir / "paper2agent_generated_code",
            enable_code_generation=True,
            enable_github_integration=True,
            confidence_threshold=0.4,  # Lower threshold for demo
            max_tools_per_paper=5
        )
        
        # Initialize orchestrator
        self.orchestrator = Paper2AgentOrchestrator(self.config)
        
        # Demo papers (simulated paper content)
        self.demo_papers = self._create_demo_papers()
        
        logger.info("Initialized Phase 3 Paper2Agent Demo")
    
    def _create_demo_papers(self) -> list[PaperSource]:
        """Create demo papers for testing."""
        papers = []
        
        # Paper 1: Structural Analysis
        papers.append(PaperSource(
            title="Advanced Protein Structure Prediction Using Deep Learning",
            authors=["Smith, J.", "Johnson, A.", "Williams, B."],
            doi="10.1038/nature.2024.001",
            abstract="We present a novel deep learning approach for protein structure prediction that achieves state-of-the-art accuracy. Our method combines evolutionary information with structural constraints to predict 3D protein structures from sequence alone.",
            content="""
            Abstract: We present a novel deep learning approach for protein structure prediction.
            
            Introduction: Protein structure prediction remains one of the most challenging problems in computational biology.
            
            Methods: Our approach uses a transformer-based architecture to predict protein structures. The method involves:
            1. Sequence preprocessing and feature extraction
            2. Multiple sequence alignment generation
            3. Deep learning model training with structural constraints
            4. Structure refinement using energy minimization
            5. Quality assessment using Ramachandran plot analysis
            
            The structure prediction algorithm follows these steps:
            - Parse input protein sequence
            - Generate evolutionary features from MSA
            - Apply transformer model for distance prediction
            - Reconstruct 3D coordinates from predicted distances
            - Refine structure using molecular dynamics
            
            Results: Our method achieves 95% accuracy on CASP14 targets.
            
            Discussion: The integration of evolutionary and structural information is key to success.
            """,
            github_repo="https://github.com/example/protein-structure-prediction",
            publication_year=2024,
            journal="Nature",
            keywords=["protein structure", "deep learning", "structure prediction"]
        ))
        
        # Paper 2: Evolutionary Analysis
        papers.append(PaperSource(
            title="Phylogenetic Analysis of Protein Families Using Maximum Likelihood",
            authors=["Brown, C.", "Davis, E.", "Miller, F."],
            doi="10.1093/molbev/2024.002",
            abstract="We describe a comprehensive framework for phylogenetic analysis of protein families using maximum likelihood methods with bootstrap support.",
            content="""
            Abstract: We describe a comprehensive framework for phylogenetic analysis.
            
            Introduction: Understanding evolutionary relationships is crucial for protein function prediction.
            
            Methods: Our phylogenetic analysis pipeline includes:
            1. Homologous sequence collection and filtering
            2. Multiple sequence alignment using MUSCLE
            3. Phylogenetic tree construction using maximum likelihood
            4. Bootstrap analysis for statistical support
            5. Conservation analysis across the phylogeny
            
            The conservation analysis method:
            - Align homologous protein sequences
            - Calculate position-specific conservation scores
            - Identify conserved functional domains
            - Map conservation to protein structure
            - Generate evolutionary pressure maps
            
            The phylogenetic tree construction follows:
            - Distance matrix calculation from aligned sequences
            - Maximum likelihood tree estimation
            - Bootstrap resampling for confidence assessment
            - Tree visualization and annotation
            
            Results: We analyzed 500 protein families with high bootstrap support.
            
            Discussion: Conservation patterns correlate with functional importance.
            """,
            publication_year=2024,
            journal="Molecular Biology and Evolution",
            keywords=["phylogenetics", "evolution", "conservation", "maximum likelihood"]
        ))
        
        # Paper 3: Mutation Design
        papers.append(PaperSource(
            title="Rational Design of Thermostable Proteins Using Machine Learning",
            authors=["Wilson, G.", "Taylor, H.", "Anderson, I."],
            doi="10.1016/j.jmb.2024.003",
            abstract="We present a machine learning approach for designing thermostable protein variants through rational mutation selection.",
            content="""
            Abstract: We present a machine learning approach for designing thermostable proteins.
            
            Introduction: Protein thermostability is crucial for industrial applications.
            
            Methods: Our rational design approach includes:
            1. Structural analysis of target protein
            2. Identification of mutation hotspots
            3. Machine learning prediction of stability effects
            4. Combinatorial optimization of mutation sets
            5. Experimental validation of designed variants
            
            The stability prediction method:
            - Parse protein structure from PDB format
            - Extract structural and energetic features
            - Apply trained machine learning models
            - Predict ΔΔG values for mutations
            - Rank mutations by predicted stability improvement
            
            The rational mutation design algorithm:
            - Identify structurally important positions
            - Generate mutation candidates based on physicochemical properties
            - Evaluate predicted effects using multiple scoring functions
            - Select optimal mutation combinations
            - Validate designs through molecular dynamics simulations
            
            Results: We achieved 15°C increase in melting temperature for target proteins.
            
            Discussion: Machine learning enables accurate prediction of mutation effects.
            """,
            github_repo="https://github.com/example/thermostable-design",
            publication_year=2024,
            journal="Journal of Molecular Biology",
            keywords=["protein design", "thermostability", "machine learning", "mutations"]
        ))
        
        return papers
    
    async def run_complete_demo(self):
        """Run the complete Phase 3 demonstration."""
        print("🚀 Starting Phase 3 Paper2Agent Demonstration")
        print("=" * 80)
        
        # Step 1: Process paper collection
        print("\n📚 Step 1: Processing Paper Collection")
        print("-" * 50)
        
        processing_results = await self.orchestrator.process_paper_collection(self.demo_papers)
        
        print(f"✅ Processed {processing_results['summary']['successful_papers']} papers successfully")
        print(f"🔧 Generated {processing_results['summary']['total_tools_generated']} MCP tools")
        print(f"📊 Success rate: {processing_results['summary']['success_rate']:.1%}")
        
        # Step 2: Display generated tools
        print("\n🛠️ Step 2: Generated MCP Tools")
        print("-" * 50)
        
        mcp_info = await self.orchestrator.mcp_server.list_tools()
        
        for i, tool in enumerate(mcp_info["tools"], 1):
            print(f"{i}. {tool['name']}")
            print(f"   Description: {tool['description']}")
            print(f"   Paper: {tool['paper_source']}")
            print(f"   Confidence: {tool['confidence_score']:.2f}")
            print(f"   Usage: {tool['usage_count']} calls, {tool['success_rate']:.1%} success")
            print()
        
        # Step 3: Demonstrate tool usage
        print("\n🎯 Step 3: Demonstrating Tool Usage")
        print("-" * 50)
        
        # Test structural analysis tool
        if any("structure" in tool["name"] for tool in mcp_info["tools"]):
            print("Testing structural analysis tool...")
            
            structure_result = await self.orchestrator.search_and_call_tool(
                "structure prediction",
                {
                    "sequence": "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG",
                    "template_pdb": "1UBQ"
                }
            )
            
            print(f"✅ Structure prediction result: {structure_result.get('tool_result', {}).get('status', 'unknown')}")
            if structure_result.get('tool_result', {}).get('status') == 'success':
                print(f"   Selected tool: {structure_result.get('selected_tool', 'unknown')}")
                print(f"   Execution time: {structure_result.get('tool_result', {}).get('execution_time', 'N/A')}s")
            else:
                print(f"   Result: {structure_result}")
        
        # Test evolutionary analysis tool
        if any("conservation" in tool["name"] or "phylo" in tool["name"] for tool in mcp_info["tools"]):
            print("\nTesting evolutionary analysis tool...")
            
            evolution_result = await self.orchestrator.search_and_call_tool(
                "conservation analysis",
                {
                    "sequences": [
                        "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG",
                        "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG",
                        "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG"
                    ]
                }
            )
            
            print(f"✅ Conservation analysis result: {evolution_result.get('tool_result', {}).get('status', 'unknown')}")
            if evolution_result.get('tool_result', {}).get('status') == 'success':
                print(f"   Selected tool: {evolution_result.get('selected_tool', 'unknown')}")
            else:
                print(f"   Result: {evolution_result}")
        
        # Test mutation design tool
        if any("mutation" in tool["name"] or "design" in tool["name"] for tool in mcp_info["tools"]):
            print("\nTesting mutation design tool...")
            
            mutation_result = await self.orchestrator.search_and_call_tool(
                "stability prediction",
                {
                    "structure": "PDB_STRUCTURE_DATA",
                    "mutations": ["I44V", "F45Y", "D52N"]
                }
            )
            
            print(f"✅ Mutation design result: {mutation_result.get('tool_result', {}).get('status', 'unknown')}")
            if mutation_result.get('tool_result', {}).get('status') == 'success':
                print(f"   Selected tool: {mutation_result.get('selected_tool', 'unknown')}")
            else:
                print(f"   Result: {mutation_result}")
        
        # Step 4: System validation
        print("\n🔍 Step 4: System Validation")
        print("-" * 50)
        
        validation_results = await self.orchestrator.validate_all_tools()
        
        print(f"✅ Validated {validation_results['validation_summary']['passed']} tools")
        print(f"❌ Failed validation: {validation_results['validation_summary']['failed']} tools")
        print(f"📊 Validation success rate: {validation_results['validation_summary']['success_rate']:.1%}")
        
        # Step 5: System status
        print("\n📊 Step 5: System Status")
        print("-" * 50)
        
        status = await self.orchestrator.get_system_status()
        
        print(f"🏗️ Orchestrator Status: {status['orchestrator_status']}")
        print(f"📈 Papers Processed: {status['statistics']['papers_processed']}")
        print(f"🔧 Tools Generated: {status['statistics']['tools_generated']}")
        print(f"💻 Code Generated: {status['statistics']['code_generated']}")
        print(f"🚀 Tools Deployed: {status['statistics']['tools_deployed']}")
        
        # Step 6: Save results
        print("\n💾 Step 6: Saving Results")
        print("-" * 50)
        
        results_file = self.base_dir / "phase3_demo_results.json"
        
        demo_results = {
            "timestamp": datetime.now().isoformat(),
            "processing_results": processing_results,
            "system_status": status,
            "validation_results": validation_results,
            "demo_summary": {
                "papers_processed": len(self.demo_papers),
                "tools_generated": len(mcp_info["tools"]),
                "categories_covered": list(mcp_info.get("categories", [])),
                "success": True
            }
        }
        
        with open(results_file, 'w') as f:
            json.dump(demo_results, f, indent=2, default=str)
        
        print(f"✅ Results saved to: {results_file}")
        
        print("\n🎉 Phase 3 Paper2Agent Demonstration Complete!")
        print("=" * 80)
        
        return demo_results
    
    async def demonstrate_integration_with_existing_system(self):
        """Demonstrate integration with existing multi-community system."""
        print("\n🔗 Integration with Existing Multi-Community System")
        print("-" * 60)
        
        # This would integrate with the existing paper2agent enhanced community system
        print("🤖 Paper2Agent tools can now be called by:")
        print("   • MD Expert agents for structural analysis")
        print("   • Bioinformatics Expert agents for evolutionary analysis")
        print("   • Structure Expert agents for mutation design")
        print("   • Critic agents for validation and assessment")
        
        print("\n📋 Integration Benefits:")
        print("   ✅ Literature-validated tool recommendations")
        print("   ✅ Automatic code generation for missing functionality")
        print("   ✅ Dynamic tool discovery and deployment")
        print("   ✅ Verifiable rewards based on published methods")
        print("   ✅ Scalable framework for any protein engineering challenge")
        
        return True


async def main():
    """Main demonstration function."""
    demo = Phase3Demo()
    
    try:
        # Run complete demonstration
        results = await demo.run_complete_demo()
        
        # Demonstrate integration
        await demo.demonstrate_integration_with_existing_system()
        
        print(f"\n🌟 Phase 3 Paper2Agent system successfully demonstrated!")
        print(f"📊 Generated {results['demo_summary']['tools_generated']} tools from {results['demo_summary']['papers_processed']} papers")
        
        return results
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
