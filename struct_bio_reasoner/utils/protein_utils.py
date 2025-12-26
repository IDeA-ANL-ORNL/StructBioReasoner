"""
Protein utility functions for StructBioReasoner.

This module provides common utility functions for protein analysis
and manipulation.
"""

import logging
import MDAnalysis as mda
import numpy as np
from pathlib import Path
import string
from typing import Dict, List, Optional, Any, Union

try:
    import Bio
    from Bio import SeqIO, PDB
    BIOPYTHON_AVAILABLE = True
except ImportError:
    BIOPYTHON_AVAILABLE = False
    Bio = None


def load_protein_structure(structure_id: str, source: str = "pdb") -> Optional[Dict[str, Any]]:
    """
    Load protein structure from various sources.
    
    Args:
        structure_id: Structure identifier (PDB ID, file path, etc.)
        source: Source type ("pdb", "local", "alphafold")
        
    Returns:
        Structure data dictionary or None if failed
    """
    if not BIOPYTHON_AVAILABLE:
        logging.warning("BioPython not available - structure loading disabled")
        return None
    
    try:
        if source == "pdb":
            return _load_from_pdb(structure_id)
        elif source == "local":
            return _load_from_local(structure_id)
        elif source == "alphafold":
            return _load_from_alphafold(structure_id)
        else:
            logging.error(f"Unknown structure source: {source}")
            return None
            
    except Exception as e:
        logging.error(f"Failed to load structure {structure_id}: {e}")
        return None


def _load_from_pdb(pdb_id: str) -> Dict[str, Any]:
    """Load structure from PDB database."""
    # Placeholder implementation
    return {
        "structure_id": pdb_id,
        "source": "pdb",
        "chains": ["A"],
        "resolution": 2.0,
        "method": "X-RAY DIFFRACTION"
    }


def _load_from_local(file_path: str) -> Dict[str, Any]:
    """Load structure from local file."""
    # Placeholder implementation
    return {
        "structure_id": Path(file_path).stem,
        "source": "local",
        "file_path": file_path,
        "chains": ["A"]
    }


def _load_from_alphafold(uniprot_id: str) -> Dict[str, Any]:
    """Load structure from AlphaFold database."""
    # Placeholder implementation
    return {
        "structure_id": uniprot_id,
        "source": "alphafold",
        "confidence": "high",
        "chains": ["A"]
    }


def analyze_sequence(sequence: str) -> Dict[str, Any]:
    """
    Analyze protein sequence properties.
    
    Args:
        sequence: Protein sequence string
        
    Returns:
        Dictionary with sequence analysis results
    """
    if not sequence:
        return {}
    
    try:
        analysis = {
            "length": len(sequence),
            "molecular_weight": _calculate_molecular_weight(sequence),
            "composition": _calculate_composition(sequence),
            "hydrophobicity": _calculate_hydrophobicity(sequence),
            "charge": _calculate_charge(sequence)
        }
        
        return analysis
        
    except Exception as e:
        logging.error(f"Sequence analysis failed: {e}")
        return {}


def _calculate_molecular_weight(sequence: str) -> float:
    """Calculate approximate molecular weight."""
    # Simplified calculation - average amino acid weight
    return len(sequence) * 110.0  # Average MW of amino acid


def _calculate_composition(sequence: str) -> Dict[str, float]:
    """Calculate amino acid composition."""
    if not sequence:
        return {}
    
    composition = {}
    for aa in "ACDEFGHIKLMNPQRSTVWY":
        count = sequence.count(aa)
        composition[aa] = count / len(sequence) * 100
    
    return composition


def _calculate_hydrophobicity(sequence: str) -> float:
    """Calculate average hydrophobicity."""
    # Simplified hydrophobicity scale
    hydrophobicity_scale = {
        'A': 1.8, 'R': -4.5, 'N': -3.5, 'D': -3.5, 'C': 2.5,
        'Q': -3.5, 'E': -3.5, 'G': -0.4, 'H': -3.2, 'I': 4.5,
        'L': 3.8, 'K': -3.9, 'M': 1.9, 'F': 2.8, 'P': -1.6,
        'S': -0.8, 'T': -0.7, 'W': -0.9, 'Y': -1.3, 'V': 4.2
    }
    
    if not sequence:
        return 0.0
    
    total = sum(hydrophobicity_scale.get(aa, 0) for aa in sequence)
    return total / len(sequence)


def _calculate_charge(sequence: str, ph: float = 7.0) -> float:
    """Calculate net charge at given pH."""
    # Simplified charge calculation
    positive = sequence.count('K') + sequence.count('R') + sequence.count('H')
    negative = sequence.count('D') + sequence.count('E')
    
    return positive - negative


def validate_protein_sequence(sequence: str) -> bool:
    """
    Validate protein sequence.
    
    Args:
        sequence: Protein sequence to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not sequence:
        return False
    
    # Check for valid amino acid characters
    valid_aa = set("ACDEFGHIKLMNPQRSTVWY")
    sequence_set = set(sequence.upper())
    
    return sequence_set.issubset(valid_aa)


def get_sequence_info(sequence: str) -> Dict[str, Any]:
    """
    Get comprehensive sequence information.
    
    Args:
        sequence: Protein sequence
        
    Returns:
        Dictionary with sequence information
    """
    if not validate_protein_sequence(sequence):
        return {"valid": False, "error": "Invalid sequence"}
    
    info = {
        "valid": True,
        "sequence": sequence,
        "length": len(sequence),
        "analysis": analyze_sequence(sequence)
    }
    
    return info


def format_sequence_fasta(sequence: str, header: str = "protein") -> str:
    """
    Format sequence as FASTA.
    
    Args:
        sequence: Protein sequence
        header: FASTA header
        
    Returns:
        FASTA formatted string
    """
    if not sequence:
        return ""
    
    return f">{header}\n{sequence}\n"


def parse_fasta_sequences(fasta_content: str) -> List[Dict[str, str]]:
    """
    Parse FASTA content into sequences.
    
    Args:
        fasta_content: FASTA formatted content
        
    Returns:
        List of dictionaries with header and sequence
    """
    sequences = []
    current_header = ""
    current_sequence = ""
    
    for line in fasta_content.strip().split('\n'):
        if line.startswith('>'):
            if current_header and current_sequence:
                sequences.append({
                    "header": current_header,
                    "sequence": current_sequence
                })
            current_header = line[1:].strip()
            current_sequence = ""
        else:
            current_sequence += line.strip()
    
    # Add the last sequence
    if current_header and current_sequence:
        sequences.append({
            "header": current_header,
            "sequence": current_sequence
        })
    
    return sequences

def add_chainids(u: mda.Universe,
                 terminus_selection: str='name OXT') -> mda.Universe:
    if not hasattr(u.atoms, 'chainIDs'):
        u.add_TopologyAttr('chainIDs')

    u.atoms.chainIDs = np.full(u.atoms.chainIDs.shape, 'A', dtype=object)
    
    term_atoms = u.select_atoms(terminus_selection)
    term_resindices = set(term_atoms.resindices)

    def get_chain_label(index):
        if index < 26:
            return string.ascii_uppercase[index]
        first = string.ascii_uppercase[(index // 26) - 1]
        second = string.ascii_uppercase[index % 26]
        return first + second

    chain_index = 0
    for residue in u.residues:
        residue.atoms.chainIDs = get_chain_label(chain_index)

        if residue.resindex in term_resindices:
            chain_index += 1

    return u

def pdb2seq(pdbf):
    u = mda.Universe(pdbf)
    
    # Chain A only
    chain_a = u.select_atoms('protein and chainID A')
    seq_a = ''.join([aa_dict.get(res.resname, 'X') for res in chain_a.residues])
    
    # Or by chainID
    chain_b = u.select_atoms('protein and chainID B')
    seq_b = ''.join([aa_dict.get(res.resname, 'X') for res in chain_b.residues])
    return [seq_a, seq_b] 
