#!/usr/bin/env python3
"""
Run the Parsl Hierarchical Workflow for NMNAT2 binder design.

NMNAT2 (Nicotinamide mononucleotide adenylyltransferase 2) is a key enzyme
in NAD+ biosynthesis that plays important roles in neuronal health and
axon maintenance.

This script executes the full hierarchical multi-agent workflow:
1. RAG identifies relevant protein targets/interactors
2. Manager agents are spawned for each target
3. Executive agent oversees the campaign and makes strategic decisions
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from struct_bio_reasoner.workflows import (
    ParslHierarchicalWorkflow,
    WorkflowConfig,
    run_workflow,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'nmnat2_workflow_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)


def main():
    """Run the NMNAT2 binder design workflow."""
    logger.info("Starting NMNAT2 hierarchical workflow")

    # Create workflow configuration for NMNAT2
    config = WorkflowConfig(
        # Research goal focused on NMNAT2
        research_goal=(
            "Design a binder for NMNAT2 (Nicotinamide mononucleotide adenylyltransferase 2). "
            "NMNAT2 is critical for NAD+ biosynthesis and neuronal axon maintenance. "
            "The goal is to develop binders that can modulate NMNAT2 activity or stabilize "
            "the protein to support neuroprotection."
        ),

        # Configuration paths
        config_path="config/binder_config.yaml",
        output_dir=f"workflow_outputs/nmnat2_{datetime.now().strftime('%Y%m%d_%H%M%S')}",

        # Compute resources - adjust based on available resources
        total_compute_nodes=50,
        max_workers_per_node=2,
        nodes_per_manager=10,

        # Workflow parameters
        max_managers=5,
        progress_report_interval=60.0,      # Report every 1 minute
        executive_review_interval=300.0,    # Executive reviews every 5 minutes

        # Stopping criteria
        max_runtime_hours=24.0,             # Maximum 24 hours runtime
        target_affinity=-15.0,              # Stop if affinity reaches -15 kcal/mol

        # Manager parameters
        max_tasks_per_campaign=100,
        min_binder_affinity=-10.0,
    )

    logger.info(f"Configuration:")
    logger.info(f"  Research goal: {config.research_goal[:80]}...")
    logger.info(f"  Output directory: {config.output_dir}")
    logger.info(f"  Max managers: {config.max_managers}")
    logger.info(f"  Max runtime: {config.max_runtime_hours} hours")
    logger.info(f"  Target affinity: {config.target_affinity} kcal/mol")

    # Run the workflow
    try:
        results = asyncio.run(run_workflow(config))

        # Log results
        logger.info("=" * 60)
        logger.info("WORKFLOW COMPLETED")
        logger.info("=" * 60)
        logger.info(f"Best score overall: {results.get('best_score_overall', 'N/A')}")
        logger.info(f"Best manager: {results.get('best_manager_id', 'N/A')}")
        logger.info(f"Runtime: {results.get('runtime_hours', 'N/A'):.2f} hours")

        if results.get('best_binder_overall'):
            logger.info(f"Best binder: {results['best_binder_overall']}")

        # Print summary
        print("\n" + "=" * 60)
        print("NMNAT2 WORKFLOW RESULTS")
        print("=" * 60)
        print(f"Best affinity score: {results.get('best_score_overall', 'N/A')}")
        print(f"Best manager ID: {results.get('best_manager_id', 'N/A')}")
        print(f"Total runtime: {results.get('runtime_hours', 0):.2f} hours")
        print(f"RAG hits processed: {len(results.get('rag_hits', []))}")
        print(f"Executive decisions made: {len(results.get('executive_decisions', []))}")
        print("=" * 60)

        return results

    except KeyboardInterrupt:
        logger.info("Workflow interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Workflow failed with error: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    main()
