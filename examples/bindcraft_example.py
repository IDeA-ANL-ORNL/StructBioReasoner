"""
MDAgent Integration Example for StructBioReasoner

This example demonstrates how to use the MDAgent integration in StructBioReasoner
for molecular dynamics simulations with both OpenMM and MDAgent backends.

Usage:
    python examples/mdagent_integration_example.py --backend openmm
    python examples/mdagent_integration_example.py --backend mdagent
"""

import asyncio
import argparse
import logging
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from struct_bio_reasoner.agents.computational_design.bindcraft_agent import BindCraftAgent
from struct_bio_reasoner.agents.roles.mdagent_expert import MDAgentExpert

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def example_basic_md_agent(backend: str = "openmm"):
    """
    Example 1: Basic MD agent usage with backend selection.
    
    Args:
        backend: MD backend to use ('openmm' or 'mdagent')
    """
    logger.info(f"=== Example 1: Basic MD Agent with {backend} backend ===")
    
    # Configure MD agent
    config = {
        "agent_id": "md_agent_example",
        "md_backend": backend,
        "simulation": {
            "temperature": 300,
            "pressure": 1.0,
            "equilibration_steps": 10000,
            "production_steps": 500000,
            "force_field": "amber14-all.xml",
            "water_model": "amber14/tip3pfb.xml"
        },
        "analysis": {
            "rmsd_threshold": 0.3,
            "rmsf_threshold": 0.2,
            "stability_score_threshold": 70.0,
            "confidence_threshold": 0.6
        }
    }
    
    # Add MDAgent-specific config if using MDAgent backend
    if backend == "mdagent":
        config["mdagent"] = {
            "solvent_model": "explicit",
            "force_field": "amber14",
            "water_model": "tip3p",
            "equil_steps": 10_000,
            "prod_steps": 1_000_000
        }
    
    # Create and initialize MD agent
    md_agent = MolecularDynamicsAgent(config)
    await md_agent.initialize()
    
    # Check if agent is ready
    if not md_agent.is_ready():
        logger.error(f"MD agent with {backend} backend not ready")
        return
    
    # Get agent status
    status = md_agent.get_agent_status()
    logger.info(f"MD Agent Status: {status}")

    # Example: Generate hypotheses (requires PDB file)
    # Check if PDB file exists
    pdb_path = Path("data/1ubq.pdb")
    if pdb_path.exists():
        logger.info(f"\n🧬 Running simulation with {pdb_path}")
        logger.info("💡 TIP: Run 'nvidia-smi' in another terminal to see GPU usage!")

        context = {
            'protein_sequence': 'MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG',
            'target_protein': 'ubiquitin',
            'pdb_path': str(pdb_path),
            'analysis_goals': ['thermostability']
        }

        hypotheses = await md_agent.generate_hypotheses(context)
        logger.info(f"\n✅ Generated {len(hypotheses)} hypotheses")
        for i, hyp in enumerate(hypotheses, 1):
            logger.info(f"Hypothesis {i}: {hyp.get('title', 'Untitled')}")
            print(hyp)
    else:
        logger.info(f"\n⚠️  PDB file not found: {pdb_path}")
        logger.info("   To run simulation, download 1ubq.pdb to data/ directory")

    logger.info(f"\nExample 1 completed with {backend} backend")


async def example_mdagent_expert_role():
    """
    Example 2: Using MDAgent Expert role in orchestrated workflow.
    """
    logger.info("=== Example 2: MDAgent Expert Role ===")
    
    # Configure MDAgent expert
    config = {
        "role_id": "mdagent_expert_1",
        "mdagent": {
            "solvent_model": "explicit",
            "force_field": "amber14",
            "water_model": "tip3p",
            "equil_steps": 10_000,
            "prod_steps": 1_000_000
        }
    }
    
    # Create and initialize expert
    expert = MDAgentExpert(config)

    # Note: MDAgent expert requires MDAgent to be installed
    # If not available, this will fail gracefully
    try:
        await expert.initialize()

        if expert.initialized:
            # Get expert capabilities
            capabilities = expert.get_capabilities()
            logger.info(f"Expert Capabilities: {capabilities}")

            # Example task (requires PDB file)
            # Uncomment and modify with your PDB file path
            
            task = {
                "task_type": "thermostability_analysis",
                "protein_data": {
                    "pdb_path": "/eagle/FoundEpidem/avasan/IDEAL/Agents/StructBioReasoner/data/1ubq.pdb",
                    "name": "ubiquitin"
                }
            }

            result = await expert.execute_task(task)
            logger.info(f"Task Result: {result.get('status')}")
            if result.get('status') == 'success':
                logger.info(f"Expert Assessment: {result.get('expert_assessment')}")
                logger.info(f"Recommendations: {result.get('recommendations')}")
            
        else:
            logger.warning("MDAgent expert not initialized (MDAgent may not be installed)")

    except Exception as e:
        logger.error(f"MDAgent expert initialization failed: {e}")
        logger.info("This is expected if MDAgent is not installed")
    finally:
        # Always clean up the expert to properly shut down Academy manager
        try:
            await expert.cleanup()
            logger.info("Expert cleaned up successfully")
        except Exception as e:
            logger.warning(f"Expert cleanup warning: {e}")

    logger.info("Example 2 completed")


async def example_backend_comparison():
    """
    Example 3: Compare OpenMM and MDAgent backends.
    """
    logger.info("=== Example 3: Backend Comparison ===")
    
    backends = ["openmm", "mdagent"]
    
    for backend in backends:
        logger.info(f"\n--- Testing {backend} backend ---")
        
        config = {
            "agent_id": f"md_agent_{backend}",
            "md_backend": backend,
            "simulation": {
                "temperature": 300,
                "equilibration_steps": 10000,
                "production_steps": 500000
            }
        }
        
        if backend == "mdagent":
            config["mdagent"] = {
                "solvent_model": "explicit",
                "equil_steps": 10_000,
                "prod_steps": 1_000_000
            }
        
        agent = MolecularDynamicsAgent(config)
        await agent.initialize()
        
        status = agent.get_agent_status()
        logger.info(f"{backend} Backend Status:")
        logger.info(f"  - Initialized: {status['initialized']}")
        logger.info(f"  - Backend: {status['backend']}")
        
        if backend == "mdagent":
            logger.info(f"  - MDAgent Ready: {status.get('mdagent_ready', False)}")
        else:
            logger.info(f"  - OpenMM Ready: {status.get('openmm_ready', False)}")
    
    logger.info("\nExample 3 completed")


async def example_with_real_protein():
    """
    Example 4: Complete workflow with a real protein structure.
    
    This example requires a PDB file to be present.
    """
    logger.info("=== Example 4: Complete Workflow with Real Protein ===")
    
    # Check if example PDB exists
    pdb_path = Path("data/1ubq.pdb")
    
    if not pdb_path.exists():
        logger.warning(f"PDB file not found: {pdb_path}")
        logger.info("To run this example:")
        logger.info("1. Create a 'data' directory")
        logger.info("2. Download a PDB file (e.g., 1ubq.pdb from RCSB PDB)")
        logger.info("3. Place it in the data directory")
        return
    
    logger.info(f"Using PDB file: {pdb_path}")
    
    # Configure MD agent with MDAgent backend
    config = {
        "agent_id": "md_agent_ubiquitin",
        "md_backend": "mdagent",  # Try MDAgent first
        "mdagent": {
            "solvent_model": "explicit",
            "force_field": "amber14",
            "water_model": "tip3p",
            "equil_steps": 10_000,
            "prod_steps": 100_000  # Shorter for example
        }
    }
    
    # Create and initialize agent
    agent = MolecularDynamicsAgent(config)
    await agent.initialize()
    
    if not agent.is_ready():
        logger.error("MD agent not ready")
        return
    
    # Prepare context
    context = {
        'protein_sequence': 'MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG',
        'target_protein': 'ubiquitin',
        'pdb_path': str(pdb_path),
        'analysis_goals': ['thermostability', 'stability']
    }
    
    # Generate hypotheses
    logger.info("Generating hypotheses...")
    hypotheses = await agent.generate_hypotheses(context)
    
    logger.info(f"\nGenerated {len(hypotheses)} hypotheses:")
    for i, hyp in enumerate(hypotheses, 1):
        logger.info(f"\nHypothesis {i}:")
        logger.info(f"  Title: {hyp.get('title', 'Untitled')}")
        logger.info(f"  Strategy: {hyp.get('strategy', 'Unknown')}")
        logger.info(f"  Confidence: {hyp.get('confidence', 0.0):.2f}")
    
    logger.info("\nExample 4 completed")


def main():
    """Main entry point for examples."""
    parser = argparse.ArgumentParser(
        description="MDAgent Integration Examples for StructBioReasoner"
    )
    parser.add_argument(
        "--backend",
        choices=["openmm", "mdagent"],
        default="openmm",
        help="MD backend to use (default: openmm)"
    )
    parser.add_argument(
        "--example",
        type=int,
        choices=[1, 2, 3, 4],
        help="Run specific example (1-4), or run all if not specified"
    )
    
    args = parser.parse_args()
    
    # Run examples
    if args.example == 1:
        asyncio.run(example_basic_md_agent(args.backend))
    elif args.example == 2:
        asyncio.run(example_mdagent_expert_role())
    elif args.example == 3:
        asyncio.run(example_backend_comparison())
    elif args.example == 4:
        asyncio.run(example_with_real_protein())
    else:
        # Run all examples
        logger.info("Running all examples...\n")
        asyncio.run(example_basic_md_agent(args.backend))
        print("\n" + "="*80 + "\n")
        asyncio.run(example_mdagent_expert_role())
        print("\n" + "="*80 + "\n")
        asyncio.run(example_backend_comparison())
        print("\n" + "="*80 + "\n")
        asyncio.run(example_with_real_protein())


if __name__ == "__main__":
    main()

