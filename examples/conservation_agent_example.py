# examples/run_evolutionary_agent.py

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any

# Configure logging to see output from the agent
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

# Import the necessary components from your project
from struct_bio_reasoner.agents.evolutionary.conservation_agent import EvolutionaryConservationAgent
from struct_bio_reasoner.data.protein_hypothesis import ProteinHypothesis

# A mock class to satisfy the agent's __init__ requirements
class MockModelManager:
    pass

async def main():
    """
    Main function to set up and run the EvolutionaryConservationAgent.
    """
    print("--- StructBioReasoner: Evolutionary Agent Example ---")

    # 1. SETUP & CONFIGURATION
    # In a real application, this would be loaded from a YAML file.
    # For this example, we create a simple dictionary.
    print("\n[Step 1] Initializing the EvolutionaryConservationAgent...")

    config: Dict[str, Any] = {
        "agent_id": "evo_agent_001",
        "muscle_executable_path": "struct_bio_reasoner/tools/muscle-linux-x86.v5.3"
    }
    
    tools: Dict[str, Any] = {}
    model_manager = MockModelManager()
    output_directory = Path("./examples/msa_output")

    # Instantiate the agent
    evolutionary_agent = EvolutionaryConservationAgent(
        agent_id=config["agent_id"],
        config=config,
        tools=tools,
        model_manager=model_manager
    )
    print("Agent initialized successfully.")

    # 2. TASK DEFINITION
    # Define the inputs for the agent's task.
    print("\n[Step 2] Defining the protein hypothesis and task parameters...")
    
    # The agent needs a ProteinHypothesis object for context.
    dummy_hypothesis = ProteinHypothesis(
        protein_id="example_protein_001",
        title="Test hypothesis for MSA generation"
    )

    # These are the sequences we want MUSCLE to align.
    sequences_for_alignment = [
        "MTEYKLVVGGGVGKSALTIQLIQNHFDEYDPTIEDSYR",
        "MTEYKLVVVGANGVGKSALTIQLIQNFVDEYDPTIEDSYR",
        "MTEYKLVVVGGVGKSALTIQLIQNHFLDEYDPTIEDSYR",
        "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTEEDSYR",
    ]
    
    # The 'task_params' dictionary is how we pass instructions to the agent.
    # It MUST contain the 'sequences_to_align' key.
    task_params: Dict[str, Any] = {
        "sequences_to_align": sequences_for_alignment,
        "output_dir": str(output_directory) # Optional: specify where to save the file
    }
    print(f"Task defined: Align {len(sequences_for_alignment)} sequences for protein '{dummy_hypothesis.protein_id}'.")

    # 3. EXECUTION
    # Call the agent's main analysis method.
    print(f"\n[Step 3] Executing the analysis task...")
    print(f"MUSCLE path: {evolutionary_agent.muscle_path}")
    print(f"MUSCLE exists: {Path(evolutionary_agent.muscle_path).exists()}")
    print(f"Output directory: {output_directory}")

    # TO:
    try:
        analysis_result = await evolutionary_agent.analyze_hypothesis(
            hypothesis=dummy_hypothesis,
            task_params=task_params
        )
        print("Analysis task finished.")
    except Exception as e:
        print(f"❌ EXCEPTION during analysis: {e}")
        import traceback
        traceback.print_exc()
        analysis_result = None

    # 4. HANDLING RESULTS
    # Check the results returned by the agent.
    print("\n[Step 4] Reviewing the analysis results...")
    if analysis_result:
        print("✅ Analysis successful!")
        print(f"   - Protein ID: {analysis_result.protein_id}")
        print(f"   - Number of sequences aligned (MSA size): {analysis_result.msa_size}")
        print(f"   - Tools used: {analysis_result.tools_used}")

        expected_msa_file = output_directory / f"{dummy_hypothesis.protein_id}_alignment.fasta"
        print(f"\n➡️ The MSA file has been generated at: {expected_msa_file}")

    else:
        print("❌ Analysis failed. Check the logs for errors.")


if __name__ == "__main__":
    asyncio.run(main())