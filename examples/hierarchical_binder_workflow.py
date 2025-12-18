"""
Hierarchical Multi-Agent Binder Design Workflow Example

This example demonstrates the hierarchical workflow with:
- Executive Agent for strategic resource allocation
- Multiple Manager Agents for parallel binder campaigns
- Worker Agents for task execution (folding, simulation, design)

The workflow executes multiple rounds where:
1. Executive queries HiPerRAG for strategy
2. Executive allocates compute nodes to Managers
3. Managers execute parallel binder design campaigns
4. Executive evaluates performance and reallocates resources
5. Best binder seeds next round
6. Poor-performing Managers get "laid off"

Author: StructBioReasoner Team
Date: 2025-12-18
"""

import sys
import asyncio
import logging
import json
from pathlib import Path
from datetime import datetime

# Add Jnana to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'Jnana'))

from struct_bio_reasoner.workflows.hierarchical_workflow import HierarchicalBinderWorkflow

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """
    Run hierarchical multi-agent binder design workflow.
    """
    
    logger.info("="*80)
    logger.info("HIERARCHICAL MULTI-AGENT BINDER DESIGN WORKFLOW")
    logger.info("="*80)
    
    # Define research goal
    research_goal = """
    Design a high-affinity binder for NMNAT-2 (Nicotinamide Mononucleotide 
    Adenylyltransferase 2) that disrupts its interaction with cancer pathway proteins.
    
    Target: NMNAT-2 (UniProt: Q9BZQ4)
    Objective: Block protein-protein interactions involved in cancer metabolism
    Desired properties: High affinity (< -10 kcal/mol), high specificity, stable
    """
    
    # Initialize hierarchical workflow
    workflow = HierarchicalBinderWorkflow(
        config_path="config/binder_config.yaml",
        jnana_config_path="config/jnana_config.yaml",
        total_compute_nodes=50,  # Total nodes available
        num_managers=5,          # Number of parallel campaigns
        max_rounds=3             # Maximum rounds to execute
    )
    
    try:
        # Initialize workflow
        logger.info("\n[INITIALIZATION] Setting up hierarchical workflow...")
        await workflow.initialize()
        logger.info("✓ Workflow initialized")
        
        # Run workflow
        logger.info("\n[EXECUTION] Starting hierarchical workflow...")
        results = await workflow.run(research_goal)
        
        # Display results
        logger.info("\n" + "="*80)
        logger.info("WORKFLOW RESULTS")
        logger.info("="*80)
        
        logger.info(f"\nTotal Rounds Executed: {results['total_rounds']}")
        
        # Display round-by-round summary
        for round_data in results['round_history']:
            round_num = round_data['round_num']
            logger.info(f"\n--- Round {round_num} ---")
            
            # Resource allocation
            allocation = round_data['resource_allocation']
            logger.info(f"Resource Allocation:")
            for manager_id, nodes in allocation.items():
                logger.info(f"  {manager_id}: {nodes} nodes")
            
            # Manager results
            logger.info(f"\nManager Results:")
            for manager_id, result in round_data['manager_results'].items():
                logger.info(f"  {manager_id}:")
                logger.info(f"    Tasks: {result['num_tasks']}")
                logger.info(f"    Best Binder Affinity: {result.get('best_binder', {}).get('affinity', 'N/A')}")
            
            # Evaluations
            logger.info(f"\nManager Evaluations:")
            for manager_id, eval_data in round_data['evaluations'].items():
                logger.info(f"  {manager_id}:")
                logger.info(f"    Score: {eval_data['score']:.3f}")
                logger.info(f"    Recommendation: {eval_data['recommendation']}")
        
        # Best binder overall
        best = results['best_binder_overall']
        logger.info(f"\n{'='*80}")
        logger.info("BEST BINDER OVERALL")
        logger.info(f"{'='*80}")
        logger.info(f"Source Manager: {best['source_manager']}")
        logger.info(f"Affinity Score: {best['score']}")
        logger.info(f"Binder Details: {json.dumps(best['binder'], indent=2)}")
        
        # Save results to file
        output_dir = Path("results/hierarchical_workflow")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"hierarchical_results_{timestamp}.json"
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"\n✓ Results saved to: {output_file}")
        
    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        raise
    
    finally:
        # Cleanup
        logger.info("\n[CLEANUP] Cleaning up workflow resources...")
        await workflow.cleanup()
        logger.info("✓ Cleanup complete")
    
    logger.info("\n" + "="*80)
    logger.info("HIERARCHICAL WORKFLOW COMPLETE")
    logger.info("="*80)


if __name__ == "__main__":
    asyncio.run(main())

