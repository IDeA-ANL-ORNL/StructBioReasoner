"""
Mutation data models for protein engineering.

This module provides data structures for representing protein mutations,
mutation sets, and their predicted effects.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from enum import Enum


class MutationType(Enum):
    """Types of protein mutations."""
    SUBSTITUTION = "substitution"  # Single amino acid substitution
    INSERTION = "insertion"        # Amino acid insertion
    DELETION = "deletion"          # Amino acid deletion
    INDEL = "indel"               # Insertion-deletion
    SILENT = "silent"             # No amino acid change
    NONSENSE = "nonsense"         # Stop codon introduction
    FRAMESHIFT = "frameshift"     # Frame-shifting mutation


class MutationEffect(Enum):
    """Predicted effects of mutations."""
    STABILIZING = "stabilizing"
    DESTABILIZING = "destabilizing"
    NEUTRAL = "neutral"
    ACTIVATING = "activating"
    DEACTIVATING = "deactivating"
    BINDING_ENHANCING = "binding_enhancing"
    BINDING_REDUCING = "binding_reducing"
    UNKNOWN = "unknown"


@dataclass
class Mutation:
    """
    Represents a single protein mutation.
    """
    mutation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Position and sequence information
    position: int = 0  # 1-based position in protein sequence
    wild_type: str = ""  # Original amino acid (single letter code)
    mutant: str = ""     # Mutant amino acid (single letter code)
    
    # Mutation classification
    mutation_type: MutationType = MutationType.SUBSTITUTION
    
    # Structural context
    secondary_structure: str = ""  # "helix", "sheet", "loop", "unknown"
    solvent_accessibility: Optional[float] = None  # 0.0 to 1.0
    domain: str = ""  # Protein domain containing the mutation
    
    # Functional context
    functional_site: str = ""  # "active_site", "binding_site", "allosteric", "surface"
    conservation_score: Optional[float] = None  # 0.0 to 1.0
    
    # Predicted effects
    predicted_effect: MutationEffect = MutationEffect.UNKNOWN
    stability_change: Optional[float] = None  # ΔΔG in kcal/mol
    activity_change: Optional[float] = None   # Fold change in activity
    binding_change: Optional[float] = None    # Change in binding affinity
    
    # Confidence and validation
    prediction_confidence: float = 0.0  # 0.0 to 1.0
    experimental_validation: bool = False
    
    # Metadata
    rationale: str = ""  # Reason for proposing this mutation
    tools_used: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def __str__(self) -> str:
        """String representation of mutation."""
        return f"{self.wild_type}{self.position}{self.mutant}"
    
    def __repr__(self) -> str:
        """Detailed string representation."""
        return f"Mutation({self.wild_type}{self.position}{self.mutant}, effect={self.predicted_effect.value})"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert mutation to dictionary."""
        return {
            "mutation_id": self.mutation_id,
            "position": self.position,
            "wild_type": self.wild_type,
            "mutant": self.mutant,
            "mutation_type": self.mutation_type.value,
            "secondary_structure": self.secondary_structure,
            "solvent_accessibility": self.solvent_accessibility,
            "domain": self.domain,
            "functional_site": self.functional_site,
            "conservation_score": self.conservation_score,
            "predicted_effect": self.predicted_effect.value,
            "stability_change": self.stability_change,
            "activity_change": self.activity_change,
            "binding_change": self.binding_change,
            "prediction_confidence": self.prediction_confidence,
            "experimental_validation": self.experimental_validation,
            "rationale": self.rationale,
            "tools_used": self.tools_used,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Mutation':
        """Create mutation from dictionary."""
        mutation = cls()
        mutation.mutation_id = data.get("mutation_id", str(uuid.uuid4()))
        mutation.position = data.get("position", 0)
        mutation.wild_type = data.get("wild_type", "")
        mutation.mutant = data.get("mutant", "")
        mutation.mutation_type = MutationType(data.get("mutation_type", "substitution"))
        mutation.secondary_structure = data.get("secondary_structure", "")
        mutation.solvent_accessibility = data.get("solvent_accessibility")
        mutation.domain = data.get("domain", "")
        mutation.functional_site = data.get("functional_site", "")
        mutation.conservation_score = data.get("conservation_score")
        mutation.predicted_effect = MutationEffect(data.get("predicted_effect", "unknown"))
        mutation.stability_change = data.get("stability_change")
        mutation.activity_change = data.get("activity_change")
        mutation.binding_change = data.get("binding_change")
        mutation.prediction_confidence = data.get("prediction_confidence", 0.0)
        mutation.experimental_validation = data.get("experimental_validation", False)
        mutation.rationale = data.get("rationale", "")
        mutation.tools_used = data.get("tools_used", [])
        mutation.created_at = data.get("created_at", datetime.now().isoformat())
        return mutation
    
    def is_conservative(self) -> bool:
        """Check if mutation is conservative (similar amino acids)."""
        # Define amino acid groups
        hydrophobic = set("AILMFWYV")
        polar = set("NQST")
        charged_positive = set("KRH")
        charged_negative = set("DE")
        special = set("CGP")
        
        groups = [hydrophobic, polar, charged_positive, charged_negative, special]
        
        for group in groups:
            if self.wild_type in group and self.mutant in group:
                return True
        return False
    
    def get_chemical_change(self) -> str:
        """Get description of chemical change."""
        # Amino acid properties
        properties = {
            'A': 'small_hydrophobic', 'I': 'hydrophobic', 'L': 'hydrophobic', 'M': 'hydrophobic',
            'F': 'aromatic_hydrophobic', 'W': 'aromatic_hydrophobic', 'Y': 'aromatic_polar',
            'V': 'hydrophobic', 'N': 'polar', 'Q': 'polar', 'S': 'small_polar', 'T': 'polar',
            'K': 'positive', 'R': 'positive', 'H': 'positive', 'D': 'negative', 'E': 'negative',
            'C': 'sulfur', 'G': 'small', 'P': 'rigid'
        }
        
        wt_prop = properties.get(self.wild_type, 'unknown')
        mut_prop = properties.get(self.mutant, 'unknown')
        
        if wt_prop == mut_prop:
            return "conservative"
        elif 'hydrophobic' in wt_prop and 'polar' in mut_prop:
            return "hydrophobic_to_polar"
        elif 'polar' in wt_prop and 'hydrophobic' in mut_prop:
            return "polar_to_hydrophobic"
        elif 'positive' in wt_prop and 'negative' in mut_prop:
            return "charge_reversal"
        elif 'negative' in wt_prop and 'positive' in mut_prop:
            return "charge_reversal"
        else:
            return "moderate"


@dataclass
class MutationSet:
    """
    Represents a set of mutations that work together.
    """
    set_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    
    # Mutations in the set
    mutations: List[Mutation] = field(default_factory=list)
    
    # Set properties
    set_type: str = ""  # "single", "double", "triple", "combinatorial", "saturation"
    design_strategy: str = ""  # "rational", "random", "evolutionary", "computational"
    
    # Predicted combined effects
    combined_stability_change: Optional[float] = None
    combined_activity_change: Optional[float] = None
    epistatic_interactions: List[Dict[str, Any]] = field(default_factory=list)
    
    # Validation
    experimental_validation: bool = False
    validation_results: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    rationale: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def add_mutation(self, mutation: Mutation):
        """Add a mutation to the set."""
        self.mutations.append(mutation)
    
    def remove_mutation(self, mutation_id: str):
        """Remove a mutation from the set."""
        self.mutations = [m for m in self.mutations if m.mutation_id != mutation_id]
    
    def get_mutation_count(self) -> int:
        """Get number of mutations in the set."""
        return len(self.mutations)
    
    def get_positions(self) -> List[int]:
        """Get all positions involved in mutations."""
        return [m.position for m in self.mutations]
    
    def has_overlapping_positions(self) -> bool:
        """Check if any mutations affect the same position."""
        positions = self.get_positions()
        return len(positions) != len(set(positions))
    
    def get_mutation_string(self) -> str:
        """Get string representation of all mutations."""
        return "/".join([str(m) for m in self.mutations])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert mutation set to dictionary."""
        return {
            "set_id": self.set_id,
            "name": self.name,
            "description": self.description,
            "mutations": [m.to_dict() for m in self.mutations],
            "set_type": self.set_type,
            "design_strategy": self.design_strategy,
            "combined_stability_change": self.combined_stability_change,
            "combined_activity_change": self.combined_activity_change,
            "epistatic_interactions": self.epistatic_interactions,
            "experimental_validation": self.experimental_validation,
            "validation_results": self.validation_results,
            "rationale": self.rationale,
            "created_at": self.created_at
        }


@dataclass
class MutationLibrary:
    """
    Represents a library of mutation sets for systematic exploration.
    """
    library_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    
    # Library contents
    mutation_sets: List[MutationSet] = field(default_factory=list)
    
    # Library design
    library_type: str = ""  # "saturation", "combinatorial", "focused", "random"
    target_positions: List[int] = field(default_factory=list)
    allowed_amino_acids: Dict[int, List[str]] = field(default_factory=dict)
    
    # Library statistics
    theoretical_size: int = 0
    actual_size: int = 0
    coverage: float = 0.0
    
    # Metadata
    design_rationale: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def add_mutation_set(self, mutation_set: MutationSet):
        """Add a mutation set to the library."""
        self.mutation_sets.append(mutation_set)
        self.actual_size = len(self.mutation_sets)
    
    def calculate_theoretical_size(self) -> int:
        """Calculate theoretical library size."""
        if not self.allowed_amino_acids:
            return 0
        
        size = 1
        for position, amino_acids in self.allowed_amino_acids.items():
            size *= len(amino_acids)
        
        self.theoretical_size = size
        return size
    
    def calculate_coverage(self) -> float:
        """Calculate library coverage."""
        if self.theoretical_size == 0:
            self.calculate_theoretical_size()
        
        if self.theoretical_size > 0:
            self.coverage = self.actual_size / self.theoretical_size
        else:
            self.coverage = 0.0
        
        return self.coverage
    
    def get_library_summary(self) -> Dict[str, Any]:
        """Get summary of library properties."""
        return {
            "library_id": self.library_id,
            "name": self.name,
            "library_type": self.library_type,
            "target_positions": self.target_positions,
            "theoretical_size": self.theoretical_size,
            "actual_size": self.actual_size,
            "coverage": self.coverage,
            "mutation_sets_count": len(self.mutation_sets)
        }
