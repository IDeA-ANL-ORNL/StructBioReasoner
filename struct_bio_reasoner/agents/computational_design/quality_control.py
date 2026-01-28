from collections import Counter
from pathlib import Path
import re
from typing import Union
import MDAnalysis as mda
from MDAnalysis.lib.util import convert_aa_code

class SequenceQualityControl:
    """Quality control filters for designed binder sequences."""
    
    def __init__(self, 
                 max_repeat: int = 4,
                 max_appearance_ratio: float = 0.33,
                 max_charge: int = 5,
                 max_charge_ratio: float = 0.5,
                 max_hydrophobic_ratio: float = 0.6,
                 min_diversity: int = 8,
                 bad_motifs: list[str] = None,
                 bad_n_termini: list[str] = None):
        """
        Initialize QC filters.
        
        Args:
            max_repeat: Maximum number of consecutive identical residues
            max_appearance_ratio: Maximum ratio of any single amino acid
            max_charge: Maximum net charge
            max_charge_ratio: Maximum ratio of charged residues
            max_hydrophobic_ratio: Maximum ratio of hydrophobic residues
            min_diversity: Minimum number of unique amino acid types
            bad_motifs: List of problematic sequence motifs
            bad_n_termini: List of problematic N-terminal residues
        """
        self.max_repeat = max_repeat
        self.max_appearance_ratio = max_appearance_ratio
        self.max_charge = max_charge
        self.max_charge_ratio = max_charge_ratio
        self.max_hydrophobic_ratio = max_hydrophobic_ratio
        self.min_diversity = min_diversity
        self.bad_motifs = bad_motifs if bad_motifs is not None else ['RK', 'DP', 'DG', 'DS']
        self.bad_n_termini = bad_n_termini if bad_n_termini is not None else ['Q', 'N']

        # Residue type definitions
        self.positive = ['K', 'R']
        self.negative = ['D', 'E']
        self.hydrophobic = ['A', 'C', 'F', 'G', 'I', 'L', 'M', 'P', 'V', 'W']
        
    def __call__(self, sequence: Union[Path, str]) -> bool:
        """
        Run all QC checks on a sequence.
        
        Args:
            sequence: Either a PDB file path or sequence string
            
        Returns:
            True if sequence passes all checks, False otherwise
        """
        if isinstance(sequence, Path):
            try:
                sel = mda.Universe(str(sequence)).select_atoms('chainID B')
            except EOFError:
                return False
            self.seq = ''.join([convert_aa_code(aa) for aa in sel.residues.resnames])
        elif isinstance(sequence, str):
            self.seq = sequence
        else:
            raise ValueError("sequence must be Path or str")

        self.length = len(self.seq)
        self.counts = Counter(self.seq)
        self.pairs = [self.seq[i:i+2] for i in range(0, len(self.seq)-1)]

        checks = [
            self.multiplicity, 
            self.diversity, 
            self.repeat, 
            self.charge_ratio,
            self.check_bad_motifs,
            self.net_charge,
            self.bad_terminus,
            self.hydrophobicity,
        ]
        
        for check in checks:
            if not check():
                print(check.__name__)
                return False

        return True

    def multiplicity(self) -> bool:
        """Check if any amino acid appears too frequently."""
        for count in self.counts.values():
            if count / self.length > self.max_appearance_ratio:
                return False
        return True

    def diversity(self) -> bool:
        """Check if sequence has sufficient amino acid diversity."""
        return len(self.counts) >= self.min_diversity

    def repeat(self) -> bool:
        """Check for consecutive repeated residues."""
        pattern = r'(.)\1{' + str(self.max_repeat - 1) + ',}'
        return re.search(pattern, self.seq) is None

    def charge_ratio(self) -> bool:
        """Check ratio of charged residues."""
        charged = sum([v for k, v in self.counts.items() 
                      if k in self.positive + self.negative])
        return charged / self.length <= self.max_charge_ratio

    def check_bad_motifs(self) -> bool:
        """Check for problematic sequence motifs."""
        return not any([motif in ''.join(self.pairs) for motif in self.bad_motifs])

    def net_charge(self) -> bool:
        """Check net charge of sequence."""
        positive = sum([v for k, v in self.counts.items() if k in self.positive])
        negative = sum([v for k, v in self.counts.items() if k in self.negative])
        return abs(positive - negative) <= self.max_charge

    def bad_terminus(self) -> bool:
        """Check for problematic N-terminal residue."""
        return self.seq[0] not in self.bad_n_termini

    def hydrophobicity(self) -> bool:
        """Check hydrophobic residue ratio."""
        hydrophobic = sum([v for k, v in self.counts.items() 
                          if k in self.hydrophobic])
        return hydrophobic / self.length <= self.max_hydrophobic_ratio


def filter_sequences(sequences: list[str], 
                     qc: SequenceQualityControl = None) -> list[str]:
    """
    Filter a list of sequences using QC criteria.
    
    Args:
        sequences: List of sequence strings
        qc: QualityControl instance (uses defaults if None)
        
    Returns:
        List of sequences that pass QC
    """
    if qc is None:
        qc = SequenceQualityControl()
    
    passing = []
    for seq in sequences:
        if qc(seq):
            passing.append(seq)
    
    return passing
