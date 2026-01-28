from abc import ABC, abstractmethod
from pathlib import Path
import subprocess
import sys
from typing import Union
import numpy as np

class EnergyCalculation(ABC):
    """Abstract base class for energy calculation methods."""
    
    def __init__(self):
        pass
    
    @abstractmethod
    def __call__(self, structure: Path) -> float:
        """Calculate energy for a given structure."""
        pass


class RosettaEnergy(EnergyCalculation):
    """Calculate energy using Rosetta energy function."""
    
    def __init__(self, 
                 rosetta_path: Path,
                 score_function: str = 'ref2015'):
        self.rosetta_path = rosetta_path
        self.score_function = score_function
        self.score_app = rosetta_path / 'score_jd2'
    
    def __call__(self, structure: Path) -> float:
        """
        Calculate Rosetta energy score for a structure.
        
        Args:
            structure: Path to PDB file
            
        Returns:
            Total Rosetta energy score
        """
        cmd = [
            str(self.score_app),
            '-in:file:s', str(structure),
            '-score:weights', self.score_function,
            '-out:file:scorefile', str(structure.parent / 'score.sc')
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Parse score file
        score_file = structure.parent / 'score.sc'
        if score_file.exists():
            with open(score_file) as f:
                lines = f.readlines()
                # Get last line with scores
                for line in reversed(lines):
                    if line.startswith('SCORE:') and 'total_score' not in line:
                        parts = line.split()
                        return float(parts[1])
        
        return np.nan


class SimpleEnergy(EnergyCalculation):
    """Simplified energy calculation based on interface metrics."""
    
    def __init__(self):
        pass
    
    def __call__(self, structure: Path) -> float:
        """
        Calculate simplified energy based on geometric complementarity.
        
        Args:
            structure: Path to PDB file
            
        Returns:
            Simplified energy score
        """
        import MDAnalysis as mda
        
        u = mda.Universe(str(structure))
        
        # Get interface residues
        chainA = u.select_atoms('chainID A')
        chainB = u.select_atoms('chainID B')
        
        interface_A = u.select_atoms('chainID A and around 5.0 chainID B')
        interface_B = u.select_atoms('chainID B and around 5.0 chainID A')
        
        # Calculate basic metrics
        n_contacts = len(interface_A.residues) + len(interface_B.residues)
        
        # Simple energy approximation (negative = favorable)
        energy = -1.0 * n_contacts
        
        del u
        return energy
