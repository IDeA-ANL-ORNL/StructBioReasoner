# structur_bio_reasoner/tools/muscle_wrapper.py

import subprocess
from pathlib import Path
from typing import List, Optional


def MUSCLEWrapper(input_sequences: List[str], 
               output_msa_path: Path,
               muscle_executable: Path) -> bool:
    """
    Runs MUSCLE to align sequences.

    Args:
        input_sequences: A list of protein sequences as strings.
        output_msa_path: Path to save the aligned MSA file (in FASTA format).
        muscle_executable: Path to the MUSCLE v5 executable.

    Returns:
        True if successful, False otherwise.
    """

    temp_input_file = output_msa_path.with_suffix(".temp.fasta")
    with open(temp_input_file, "w") as f:
        for i, seq in enumerate(input_sequences):
            f.write(f">seq_{i}\n")
            f.write(f"{seq}\n")
            
    # muscle -align <input> -output <output>
    command = [
        str(muscle_executable),
        "-align", str(temp_input_file),
        "-output", str(output_msa_path)
    ]
    
    try:
        print(f"Running MUSCLE: {' '.join(command)}")
        subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"MUSCLE alignment saved to {output_msa_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"MUSCLE failed!")
        print(f"Stderr: {e.stderr}")
        return False
    finally:
        if temp_input_file.exists():
            temp_input_file.unlink()