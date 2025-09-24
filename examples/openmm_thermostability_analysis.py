#!/usr/bin/env python3
"""
OpenMM Thermostability Analysis Example

This script demonstrates how to use StructBioReasoner's OpenMM integration
for thermostability analysis and mutation validation through molecular dynamics simulations.

Example usage:
    python examples/openmm_thermostability_analysis.py
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# Add StructBioReasoner to path
sys.path.append(str(Path(__file__).parent.parent))

from struct_bio_reasoner.tools.openmm_wrapper import OpenMMWrapper
from struct_bio_reasoner.agents.molecular_dynamics.md_agent import MolecularDynamicsAgent
import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def download_protein_structure(pdb_id: str) -> str:
    """Download protein structure from PDB."""
    try:
        url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
        response = requests.get(url)
        response.raise_for_status()
        
        # Save to temporary file
        pdb_file = f"{pdb_id}.pdb"
        with open(pdb_file, 'w') as f:
            f.write(response.text)
        
        logger.info(f"Downloaded {pdb_id} structure")
        return pdb_file
        
    except Exception as e:
        logger.error(f"Failed to download {pdb_id}: {e}")
        return None


async def demonstrate_openmm_wrapper():
    """Demonstrate basic OpenMM wrapper functionality."""
    logger.info("=== OpenMM Wrapper Demonstration ===")
    
    # Initialize OpenMM wrapper
    config = {
        "force_field": "amber14-all.xml",
        "water_model": "amber14/tip3pfb.xml",
        "temperature": 300,
        "pressure": 1.0,
        "equilibration_steps": 1000,  # Reduced for demo
        "production_steps": 5000,     # Reduced for demo
        "report_interval": 100,
        "trajectory_interval": 500
    }
    
    openmm_wrapper = OpenMMWrapper(config)
    await openmm_wrapper.initialize()
    
    if not openmm_wrapper.is_ready():
        logger.warning("OpenMM not available - skipping wrapper demonstration")
        return None
    
    # Download ubiquitin structure
    pdb_file = await download_protein_structure("1UBQ")
    if not pdb_file:
        return None
    
    try:
        # Setup simulation
        structure_data = {"file_path": pdb_file}
        simulation_id = "demo_ubiquitin_md"
        
        logger.info("Setting up MD simulation...")
        if not await openmm_wrapper.setup_simulation(structure_data, simulation_id):
            logger.error("Failed to setup simulation")
            return None
        
        # Run equilibration
        logger.info("Running equilibration...")
        if not await openmm_wrapper.run_equilibration(simulation_id):
            logger.error("Equilibration failed")
            return None
        
        # Run production
        logger.info("Running production simulation...")
        trajectory_file = await openmm_wrapper.run_production(simulation_id)
        if not trajectory_file:
            logger.error("Production simulation failed")
            return None
        
        # Analyze trajectory
        logger.info("Analyzing trajectory...")
        analysis = await openmm_wrapper.analyze_trajectory(simulation_id)
        if not analysis:
            logger.error("Trajectory analysis failed")
            return None
        
        # Predict thermostability
        logger.info("Predicting thermostability...")
        thermo_prediction = await openmm_wrapper.predict_thermostability(simulation_id)
        if not thermo_prediction:
            logger.error("Thermostability prediction failed")
            return None
        
        # Display results
        logger.info("=== MD Analysis Results ===")
        logger.info(f"Simulation length: {analysis['trajectory_length']} frames")
        logger.info(f"Total time: {analysis['total_time']:.2f} ns")
        logger.info(f"RMSD (mean ± std): {analysis['rmsd']['mean']:.3f} ± {analysis['rmsd']['std']:.3f} nm")
        logger.info(f"RMSF (mean): {analysis['rmsf']['mean']:.3f} nm")
        logger.info(f"Radius of gyration: {analysis['radius_of_gyration']['mean']:.3f} ± {analysis['radius_of_gyration']['std']:.3f} nm")
        
        logger.info("=== Thermostability Prediction ===")
        logger.info(f"Stability score: {thermo_prediction['stability_score']:.1f}/100")
        logger.info(f"Predicted ΔTm: {thermo_prediction['predicted_delta_tm']:.1f}°C")
        logger.info(f"Flexible residues: {thermo_prediction['flexible_residues'][:10]}")
        logger.info(f"Stable residues: {thermo_prediction['stable_residues'][:10]}")
        
        # Cleanup
        await openmm_wrapper.cleanup_simulation(simulation_id)
        
        return {
            'analysis': analysis,
            'thermostability': thermo_prediction
        }
        
    finally:
        # Cleanup files
        if os.path.exists(pdb_file):
            os.remove(pdb_file)


async def demonstrate_md_agent():
    """Demonstrate MD agent functionality."""
    logger.info("=== MD Agent Demonstration ===")
    
    # Initialize MD agent
    config = {
        "agent_id": "demo_md_agent",
        "capabilities": [
            "thermostability_prediction",
            "mutation_validation",
            "flexibility_analysis"
        ],
        "simulation": {
            "temperature": 300,
            "equilibration_steps": 1000,  # Reduced for demo
            "production_steps": 5000,     # Reduced for demo
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
    
    md_agent = MolecularDynamicsAgent(config)
    await md_agent.initialize()
    
    if not md_agent.is_ready():
        logger.warning("MD agent not ready - skipping agent demonstration")
        return None
    
    # Download ubiquitin structure
    pdb_file = await download_protein_structure("1UBQ")
    if not pdb_file:
        return None
    
    try:
        structure_data = {"file_path": pdb_file}
        
        # Generate thermostability hypothesis
        logger.info("Generating thermostability hypothesis...")
        thermo_hypothesis = await md_agent.generate_thermostability_hypothesis(
            structure_data, "ubiquitin"
        )
        
        if thermo_hypothesis:
            logger.info("=== Generated Thermostability Hypothesis ===")
            logger.info(f"Title: {thermo_hypothesis.title}")
            logger.info(f"Type: {thermo_hypothesis.hypothesis_type}")
            logger.info(f"Content preview: {thermo_hypothesis.content[:200]}...")
            logger.info(f"Hallmarks: {thermo_hypothesis.hallmarks}")
        
        # Analyze protein dynamics
        logger.info("Analyzing protein dynamics...")
        dynamics_hypothesis = await md_agent.analyze_protein_dynamics(
            structure_data, "ubiquitin"
        )
        
        if dynamics_hypothesis:
            logger.info("=== Generated Dynamics Hypothesis ===")
            logger.info(f"Title: {dynamics_hypothesis.title}")
            logger.info(f"Type: {dynamics_hypothesis.hypothesis_type}")
            logger.info(f"Content preview: {dynamics_hypothesis.content[:200]}...")
        
        # Validate mutations (example mutations)
        example_mutations = [
            {"position": 11, "from": "T", "to": "I", "rationale": "Increase hydrophobic packing"},
            {"position": 27, "from": "Q", "to": "E", "rationale": "Form salt bridge"}
        ]
        
        logger.info("Validating example mutations...")
        validation_hypothesis = await md_agent.validate_mutations(
            structure_data, example_mutations, "ubiquitin"
        )
        
        if validation_hypothesis:
            logger.info("=== Generated Mutation Validation Hypothesis ===")
            logger.info(f"Title: {validation_hypothesis.title}")
            logger.info(f"Type: {validation_hypothesis.hypothesis_type}")
            logger.info(f"Content preview: {validation_hypothesis.content[:200]}...")
        
        # Get agent status
        status = md_agent.get_agent_status()
        logger.info("=== MD Agent Status ===")
        logger.info(f"Agent ID: {status['agent_id']}")
        logger.info(f"Initialized: {status['initialized']}")
        logger.info(f"OpenMM ready: {status['openmm_ready']}")
        logger.info(f"Generated hypotheses: {status['generated_hypotheses']}")
        
        return {
            'thermostability_hypothesis': thermo_hypothesis,
            'dynamics_hypothesis': dynamics_hypothesis,
            'validation_hypothesis': validation_hypothesis,
            'agent_status': status
        }
        
    finally:
        # Cleanup files
        if os.path.exists(pdb_file):
            os.remove(pdb_file)


async def main():
    """Main demonstration function."""
    logger.info("🧬 StructBioReasoner OpenMM Integration Demonstration")
    logger.info("=" * 60)
    
    try:
        # Demonstrate OpenMM wrapper
        wrapper_results = await demonstrate_openmm_wrapper()
        
        # Demonstrate MD agent
        agent_results = await demonstrate_md_agent()
        
        logger.info("=" * 60)
        logger.info("✅ OpenMM integration demonstration completed successfully!")
        
        if wrapper_results:
            logger.info("🔬 OpenMM wrapper: Functional")
        else:
            logger.info("⚠️  OpenMM wrapper: Not available or failed")
        
        if agent_results:
            logger.info("🤖 MD agent: Functional")
            logger.info(f"📊 Generated {len([h for h in [agent_results.get('thermostability_hypothesis'), agent_results.get('dynamics_hypothesis'), agent_results.get('validation_hypothesis')] if h])} hypotheses")
        else:
            logger.info("⚠️  MD agent: Not available or failed")
        
        logger.info("🚀 StructBioReasoner now includes molecular dynamics capabilities!")
        
    except Exception as e:
        logger.error(f"Demonstration failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
