#!/usr/bin/env python3
"""
StructBioReasoner: Main entry point for the protein engineering system.

This script provides command-line interface for running the Jnana-based
structural biology reasoning model.
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

# Add the current directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent))

from struct_bio_reasoner import ProteinEngineeringSystem, print_package_info, get_package_status


def setup_logging(level: str = "INFO", log_file: Optional[str] = None):
    """Setup logging configuration."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Setup console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    
    # Setup file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


async def run_interactive_mode(system: ProteinEngineeringSystem, args):
    """Run the system in interactive mode."""
    print("🧬 Starting StructBioReasoner in Interactive Mode")
    print("=" * 60)
    
    # Set research goal
    if args.goal:
        research_goal = args.goal
    else:
        research_goal = input("Enter your protein engineering research goal: ")
    
    session_id = await system.set_research_goal(research_goal)
    print(f"Session created: {session_id}")
    
    # Run interactive mode
    await system.run_interactive_mode()


async def run_batch_mode(system: ProteinEngineeringSystem, args):
    """Run the system in batch mode."""
    print("🧬 Starting StructBioReasoner in Batch Mode")
    print("=" * 60)
    
    # Set research goal
    if not args.goal:
        print("Error: Research goal is required for batch mode")
        return
    
    session_id = await system.set_research_goal(args.goal)
    print(f"Session created: {session_id}")
    
    # Determine strategies
    strategies = args.strategies or ["structural_analysis", "evolutionary_conservation", "energetic_analysis"]
    
    print(f"Generating {args.count} hypotheses using strategies: {', '.join(strategies)}")
    
    # Run batch mode
    await system.run_batch_mode(
        hypothesis_count=args.count,
        strategies=strategies,
        tournament_matches=args.tournament_matches
    )
    
    print("Batch processing completed!")


async def run_hybrid_mode(system: ProteinEngineeringSystem, args):
    """Run the system in hybrid mode."""
    print("🧬 Starting StructBioReasoner in Hybrid Mode")
    print("=" * 60)
    
    # Set research goal
    if not args.goal:
        print("Error: Research goal is required for hybrid mode")
        return
    
    session_id = await system.set_research_goal(args.goal)
    print(f"Session created: {session_id}")
    
    # Determine strategies
    strategies = args.strategies or ["structural_analysis", "evolutionary_conservation", "energetic_analysis"]
    
    print(f"Phase 1: Generating {args.count} hypotheses using strategies: {', '.join(strategies)}")
    print("Phase 2: Interactive refinement (if enabled)")
    print("Phase 3: Tournament evaluation")
    
    # Run hybrid mode
    await system.run_hybrid_mode(
        hypothesis_count=args.count,
        strategies=strategies,
        interactive_refinement=args.interactive_refinement,
        tournament_matches=args.tournament_matches
    )
    
    print("Hybrid processing completed!")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="StructBioReasoner: Jnana-based Structural Biology Reasoning Model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python struct_bio_reasoner.py --mode interactive --goal "Improve enzyme thermostability"
  
  # Batch mode
  python struct_bio_reasoner.py --mode batch --goal "Design mutations for TEM-1 β-lactamase" --count 10
  
  # Hybrid mode with custom strategies
  python struct_bio_reasoner.py --mode hybrid --goal "Enhance binding affinity" \\
    --strategies structural_analysis evolutionary_conservation --count 5
        """
    )
    
    # Mode selection
    parser.add_argument(
        "--mode", 
        choices=["interactive", "batch", "hybrid", "status"],
        default="interactive",
        help="Operation mode (default: interactive)"
    )
    
    # Research goal
    parser.add_argument(
        "--goal", 
        type=str,
        help="Research goal or question"
    )
    
    # Protein specification
    parser.add_argument(
        "--protein",
        type=str,
        help="Target protein ID (PDB ID, UniProt ID, etc.)"
    )
    
    # Batch/Hybrid mode options
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of hypotheses to generate (default: 5)"
    )
    
    parser.add_argument(
        "--strategies",
        nargs="+",
        choices=["structural_analysis", "evolutionary_conservation", "energetic_analysis", 
                "mutation_design", "literature_analysis"],
        help="Generation strategies to use"
    )
    
    parser.add_argument(
        "--tournament-matches",
        type=int,
        default=25,
        help="Number of tournament matches for ranking (default: 25)"
    )
    
    # Hybrid mode options
    parser.add_argument(
        "--interactive-refinement",
        action="store_true",
        help="Enable interactive refinement in hybrid mode"
    )
    
    # Configuration
    parser.add_argument(
        "--config",
        type=str,
        default="config/protein_config.yaml",
        help="Configuration file path (default: config/protein_config.yaml)"
    )
    
    parser.add_argument(
        "--jnana-config",
        type=str,
        help="Jnana configuration file path (optional)"
    )
    
    # Tool selection
    parser.add_argument(
        "--enable-tools",
        nargs="+",
        default=["pymol", "biopython"],
        help="Tools to enable (default: pymol biopython)"
    )
    
    parser.add_argument(
        "--enable-agents",
        nargs="+",
        default=["structural", "evolutionary", "energetic", "design"],
        help="Agents to enable (default: structural evolutionary energetic design)"
    )
    
    # System options
    parser.add_argument(
        "--no-knowledge-graph",
        action="store_true",
        help="Disable knowledge graph"
    )
    
    parser.add_argument(
        "--no-literature",
        action="store_true",
        help="Disable literature processing"
    )
    
    parser.add_argument(
        "--enable-visualization",
        action="store_true",
        help="Enable protein visualization"
    )
    
    # Output options
    parser.add_argument(
        "--output",
        type=str,
        help="Output directory for results"
    )
    
    # Logging options
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    parser.add_argument(
        "--log-file",
        type=str,
        help="Log file path"
    )
    
    # System information
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version information"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level, args.log_file)
    
    # Show version information
    if args.version:
        print_package_info()
        return
    
    # Show system status
    if args.mode == "status":
        print_package_info()
        status = get_package_status()
        print("\nSystem Status:")
        print(f"  Jnana Available: {status['jnana_available']}")
        print("  Tool Availability:")
        for tool, available in status['tools_available'].items():
            status_symbol = "✓" if available else "✗"
            print(f"    {status_symbol} {tool}")
        return
    
    try:
        # Initialize the protein engineering system
        print("Initializing StructBioReasoner...")
        
        system = ProteinEngineeringSystem(
            config_path=args.config,
            jnana_config_path=args.jnana_config,
            enable_tools=args.enable_tools,
            enable_agents=args.enable_agents,
            knowledge_graph=not args.no_knowledge_graph,
            literature_processing=not args.no_literature,
            output_path=args.output
        )
        
        # Start the system
        await system.start()
        
        # Check system status
        status = system.get_protein_system_status()
        if not status["protein_engineering"]["protein_system_ready"]:
            print("Warning: Protein system not fully ready - some functionality may be limited")
        
        # Run in selected mode
        if args.mode == "interactive":
            await run_interactive_mode(system, args)
        elif args.mode == "batch":
            await run_batch_mode(system, args)
        elif args.mode == "hybrid":
            await run_hybrid_mode(system, args)
        
        # Stop the system
        await system.stop()
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        logging.error(f"Error running StructBioReasoner: {e}")
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
