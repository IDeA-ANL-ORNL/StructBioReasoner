"""Data models for StructBioReasoner."""

from .protein_hypothesis import (
    ProteinHypothesis, 
    MutationHypothesis,
    StructuralAnalysis,
    EvolutionaryAnalysis,
    EnergeticAnalysis,
    ExperimentalValidation
)
from .mutation_model import (
    Mutation,
    MutationSet,
    MutationLibrary,
    MutationType,
    MutationEffect
)

__all__ = [
    "ProteinHypothesis",
    "MutationHypothesis", 
    "StructuralAnalysis",
    "EvolutionaryAnalysis",
    "EnergeticAnalysis",
    "ExperimentalValidation",
    "Mutation",
    "MutationSet",
    "MutationLibrary",
    "MutationType",
    "MutationEffect"
]
