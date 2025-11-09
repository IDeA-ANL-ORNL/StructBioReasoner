"""
Protein-specific hypothesis data models.

This module extends Jnana's UnifiedHypothesis with protein engineering
specific fields and methods.
"""
import inspect
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Union

# Import Jnana components
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent.parent / "Jnana"))

from jnana.data.unified_hypothesis import UnifiedHypothesis, Reference
from .mutation_model import Mutation, MutationSet, MutationEffect


@dataclass
class BinderHypothesisData:
    """Data structure for binder design hypotheses
    """
    hypothesis_text: str
    target_name: str
    target_sequence: str
    proposed_peptides: List[Dict[str, Any]] # Each has seq, source, rationale, peptide_id
    literature_references: List[str]
    binding_affinity_goal: Optional[str] = None
    clinical_context: Optional[str] = None
    # Binder type information
    binder_type: str = "peptide"  # "peptide", "antibody", "nanobody", etc.
    # Metadata
    generated_by: str = "coscientist"  # Which agent generated this
    generation_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'hypothesis_text': self.hypothesis_text,
            'target_name': self.target_name,
            'target_sequence': self.target_sequence,
            'proposed_peptides': self.proposed_peptides,
            'literature_references': self.literature_references,
            'binding_affinity_goal': self.binding_affinity_goal,
            'clinical_context': self.clinical_context,
            'binder_type': self.binder_type,
            'generated_by': self.generated_by,
            'generation_timestamp': self.generation_timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BinderHypothesisData':
        """Create from dictionary (e.g., from CoScientist JSON response)."""
        return cls(
            hypothesis_text=data.get('hypothesis_text', ''),
            target_name=data.get('target_name', ''),
            target_sequence=data.get('target_sequence', ''),
            proposed_peptides=data.get('proposed_peptides', []),
            literature_references=data.get('literature_references', []),
            binding_affinity_goal=data.get('binding_affinity_goal'),
            clinical_context=data.get('clinical_context'),
            binder_type=data.get('binder_type', 'peptide'),
            generated_by=data.get('generated_by', 'coscientist'),
            generation_timestamp=data.get('generation_timestamp', datetime.now().isoformat())
        )



@dataclass
class StructuralAnalysis:
    """Structural analysis results for a protein hypothesis."""
    analysis_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    protein_id: str = ""
    structure_source: str = ""  # "pdb", "alphafold", "predicted"
    
    # Active site analysis
    active_site_residues: List[str] = field(default_factory=list)
    binding_sites: List[Dict[str, Any]] = field(default_factory=list)
    catalytic_residues: List[str] = field(default_factory=list)
    
    # Structural features
    secondary_structure: Dict[str, Any] = field(default_factory=dict)
    domains: List[Dict[str, Any]] = field(default_factory=list)
    cavities: List[Dict[str, Any]] = field(default_factory=list)
    
    # Stability analysis
    stability_predictions: Dict[str, float] = field(default_factory=dict)
    flexibility_regions: List[Dict[str, Any]] = field(default_factory=list)
    
    # Analysis metadata
    tools_used: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class BinderAnalysis:
    """"""
    analysis_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    protein_id: str = ''

    # Binder analysis
    num_rounds: int = 1
    total_sequences: int = 10
    passing_sequences: int = 0
    passing_structures: int = 0
    success_rate: float = 0.0
    checkpoint_file: str = ''
    # Top binder features

    # Analysis metadata
    tools_used: list[str] = field(default_factory=list)
    confidence_score: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SimAnalysis:
    """"""
    analysis_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    protein_id: str = ''

    # Simulation analysis
    simulation_time_in_ns: int = 1
    rmsd: dict = field(default_factory=dict)
    rmsf: dict = field(default_factory=dict)

    # Analysis metadata
    tools_used: list[str] = field(default_factory=list)
    confidence_score: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class EvolutionaryAnalysis:
    """Evolutionary analysis results for a protein hypothesis."""
    analysis_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    protein_id: str = ""
    
    # Sequence analysis
    msa_size: int = 0
    sequence_identity_range: tuple = (0.0, 1.0)
    conservation_scores: Dict[str, float] = field(default_factory=dict)
    
    # Evolutionary features
    conserved_residues: List[str] = field(default_factory=list)
    variable_regions: List[Dict[str, Any]] = field(default_factory=list)
    coevolving_pairs: List[tuple] = field(default_factory=list)
    
    # Phylogenetic analysis
    phylogenetic_tree: Optional[str] = None  # Newick format
    evolutionary_rate: float = 0.0
    selection_pressure: Dict[str, float] = field(default_factory=dict)
    
    # Analysis metadata
    tools_used: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class EnergeticAnalysis:
    """Energetic analysis results for a protein hypothesis."""
    analysis_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    protein_id: str = ""
    
    # Stability predictions
    folding_energy: Optional[float] = None  # kcal/mol
    stability_change: Optional[float] = None  # ΔΔG
    melting_temperature: Optional[float] = None  # °C
    
    # Binding analysis
    binding_affinities: Dict[str, float] = field(default_factory=dict)
    interaction_energies: Dict[str, float] = field(default_factory=dict)
    
    # Mutation effects
    mutation_effects: List[MutationEffect] = field(default_factory=list)
    epistatic_interactions: List[Dict[str, Any]] = field(default_factory=list)
    
    # Analysis metadata
    force_field: str = ""
    temperature: float = 298.15  # Kelvin
    ph: float = 7.0
    tools_used: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ExperimentalValidation:
    """Experimental validation data for protein hypotheses."""
    validation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Experimental design
    experiment_type: str = ""  # "mutagenesis", "binding", "activity", etc.
    methodology: str = ""
    conditions: Dict[str, Any] = field(default_factory=dict)
    
    # Results
    measurements: List[Dict[str, Any]] = field(default_factory=list)
    statistical_analysis: Dict[str, Any] = field(default_factory=dict)
    
    # Validation outcome
    hypothesis_supported: Optional[bool] = None
    confidence_level: float = 0.0
    p_value: Optional[float] = None
    
    # Metadata
    laboratory: str = ""
    researcher: str = ""
    publication: Optional[Reference] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class ProteinHypothesis(UnifiedHypothesis):
    """
    Protein-specific hypothesis extending UnifiedHypothesis.
    
    This class adds protein engineering specific fields and methods
    while maintaining compatibility with Jnana's base system.
    """
    
    def __init__(self, **kwargs):
        """Initialize protein hypothesis."""
        uh_keys = set(inspect.signature(UnifiedHypothesis.__init__).parameters)
        uh_kwargs = {k: kwargs[k] for k in kwargs if k in uh_keys}
        super().__init__(**uh_kwargs)
        
        # Protein-specific fields
        self.protein_id: str = kwargs.get("protein_id", "")
        self.protein_name: str = kwargs.get("protein_name", "")
        self.organism: str = kwargs.get("organism", "")
        self.protein_family: str = kwargs.get("protein_family", "")
        
        # Structural information
        self.structure_id: str = kwargs.get("structure_id", "")
        self.structure_source: str = kwargs.get("structure_source", "")
        self.resolution: Optional[float] = kwargs.get("resolution")
        
        # Mutation context
        self.target_mutations: List[Mutation] = kwargs.get("target_mutations", [])
        self.mutation_sets: List[MutationSet] = kwargs.get("mutation_sets", [])
        
        # Analysis results
        self.structural_analysis: Optional[StructuralAnalysis] = None
        self.evolutionary_analysis: Optional[EvolutionaryAnalysis] = None
        self.energetic_analysis: Optional[EnergeticAnalysis] = None
        self.binder_analysis: Optional[BinderAnalysis] = None
        self.md_analysis: Optional[SimAnalysis] = None
        self.binder_data: Optional[BinderHypothesisData] = kwargs.get("binder_data")
        
        # Experimental validation
        self.experimental_validations: List[ExperimentalValidation] = []

        # Protein-specific metadata
        self.protein_metadata = kwargs.get("protein_metadata", {})
        
        # Update hypothesis type
        if not self.hypothesis_type:
            self.hypothesis_type = "protein_engineering"
    
    @classmethod
    def from_unified_hypothesis(cls,
                              unified_hypothesis: UnifiedHypothesis,
                              protein_id: str = "",
                              protein_name: str = "",
                              biological_context: Optional[Dict] = None) -> 'ProteinHypothesis':
        """
        Create a ProteinHypothesis from a UnifiedHypothesis.

        Args:
            unified_hypothesis: Base hypothesis to extend
            protein_id: Target protein identifier
            protein_name: Protein name
            biological_context: Biological context information

        Returns:
            ProteinHypothesis instance
        """
        # Extract all fields from unified hypothesis
        hypothesis_data = {
            "hypothesis_id": unified_hypothesis.hypothesis_id,
            "title": unified_hypothesis.title,
            "content": unified_hypothesis.content,
            "description": unified_hypothesis.description,
            "experimental_validation": unified_hypothesis.experimental_validation,
            "created_at": unified_hypothesis.created_at,
            "updated_at": unified_hypothesis.updated_at,
            "generation_timestamp": unified_hypothesis.generation_timestamp,
            "version": unified_hypothesis.version,
            "version_string": unified_hypothesis.version_string,
            "hypothesis_type": "protein_engineering",
            "parent_id": unified_hypothesis.parent_id,
            "children_ids": unified_hypothesis.children_ids,
            "hypothesis_number": unified_hypothesis.hypothesis_number,
            "hallmarks": unified_hypothesis.hallmarks,
            "evaluation_scores": unified_hypothesis.evaluation_scores,
            "references": unified_hypothesis.references,
            "feedback_history": unified_hypothesis.feedback_history,
            "notes": unified_hypothesis.notes,
            "improvements_made": unified_hypothesis.improvements_made,
            "user_feedback": unified_hypothesis.user_feedback,
            "tournament_record": unified_hypothesis.tournament_record,
            "agent_contributions": unified_hypothesis.agent_contributions,
            "generation_strategy": unified_hypothesis.generation_strategy,
            "biomni_verification": unified_hypothesis.biomni_verification,
            "is_biomedical": True,  # Protein hypotheses are inherently biomedical
            "biomedical_domains": unified_hypothesis.biomedical_domains + ["protein_engineering"],
            "metadata": unified_hypothesis.metadata,
            "tags": unified_hypothesis.tags + ["protein", "structural_biology"],

            # Protein-specific fields
            "protein_id": protein_id,
            "protein_name": protein_name,
            "protein_metadata": biological_context or {},
            # ADD THIS: Check if this is a binder hypothesis
            "binder_data": cls._extract_binder_data(unified_hypothesis, biological_context)
        }

        return cls(**hypothesis_data)

    @classmethod
    def _extract_binder_data(cls, 
                            unified_hypothesis: UnifiedHypothesis,
                            biological_context: Optional[Dict] = None) -> Optional[BinderHypothesisData]:
        """
        Extract binder-specific data from a unified hypothesis.

        This checks multiple sources:
        1. biological_context dict (if explicitly provided)
        2. unified_hypothesis.metadata (if CoScientist stored it there)
        3. unified_hypothesis.content (if it's structured JSON)

        Args:
            unified_hypothesis: The base hypothesis
            biological_context: Optional context dict

        Returns:
            BinderHypothesisData if binder data found, None otherwise
        """
        binder_data = None

        # Method 1: Check biological_context for explicit binder data
        if biological_context and 'binder_data' in biological_context:
            binder_data = BinderHypothesisData.from_dict(biological_context['binder_data'])

        # Method 2: Check if biological_context itself IS the binder data
        elif biological_context and 'target_sequence' in biological_context:
            # biological_context contains binder fields directly
            binder_data = BinderHypothesisData.from_dict(biological_context)

        # Method 3: Check unified_hypothesis.metadata
        elif unified_hypothesis.metadata and 'binder_data' in unified_hypothesis.metadata:
            binder_data = BinderHypothesisData.from_dict(unified_hypothesis.metadata['binder_data'])

        # Method 4: Try to parse from content if it's JSON
        elif unified_hypothesis.content:
            try:
                import json
                # Check if content is JSON with binder data
                content_data = json.loads(unified_hypothesis.content)
                if 'target_sequence' in content_data and 'proposed_peptides' in content_data:
                    binder_data = BinderHypothesisData.from_dict(content_data)
            except (json.JSONDecodeError, TypeError):
                # Content is not JSON or doesn't contain binder data
                pass
            
        return binder_data

    def add_binder_analysis(self, analysis: BinderAnalysis):
        """"""
        self.binder_analysis = analysis
        self.update_at = time.time()

        # Update metadata
        self.metadata['has_binder_analysis'] = True
        self.metadata['binder_confidence'] = analysis.confidence_score

    def add_md_analysis(self, analysis: SimAnalysis):
        """"""
        self.md_analysis = analysis
        self.update_at = time.time()

        # Update metadata
        self.metadata['has_md_analysis'] = True
        self.metadata['md_confidence'] = analysis.confidence_score

    def add_structural_analysis(self, analysis: StructuralAnalysis):
        """Add structural analysis results."""
        self.structural_analysis = analysis
        self.update_at = time.time()
        
        # Update metadata
        self.metadata["has_structural_analysis"] = True
        self.metadata["structural_confidence"] = analysis.confidence_score
    
    def add_evolutionary_analysis(self, analysis: EvolutionaryAnalysis):
        """Add evolutionary analysis results."""
        self.evolutionary_analysis = analysis
        self.updated_at = time.time()
        
        # Update metadata
        self.metadata["has_evolutionary_analysis"] = True
        self.metadata["evolutionary_confidence"] = analysis.confidence_score
    
    def add_energetic_analysis(self, analysis: EnergeticAnalysis):
        """Add energetic analysis results."""
        self.energetic_analysis = analysis
        self.updated_at = time.time()
        
        # Update metadata
        self.metadata["has_energetic_analysis"] = True
        self.metadata["energetic_confidence"] = analysis.confidence_score
    
    def add_experimental_validation(self, validation: ExperimentalValidation):
        """Add experimental validation data."""
        self.experimental_validations.append(validation)
        self.updated_at = time.time()
        
        # Update metadata
        self.metadata["experimental_validations_count"] = len(self.experimental_validations)
        if validation.hypothesis_supported is not None:
            self.metadata["experimental_support"] = validation.hypothesis_supported
    
    def get_protein_summary(self) -> Dict[str, Any]:
        """Get a summary of protein-specific information."""
        return {
            "protein_id": self.protein_id,
            "protein_name": self.protein_name,
            "organism": self.organism,
            "protein_family": self.protein_family,
            "structure_info": {
                "structure_id": self.structure_id,
                "source": self.structure_source,
                "resolution": self.resolution
            },
            "mutations": {
                "target_mutations_count": len(self.target_mutations),
                "mutation_sets_count": len(self.mutation_sets)
            },
            "analysis_status": {
                "structural": self.structural_analysis is not None,
                "evolutionary": self.evolutionary_analysis is not None,
                "energetic": self.energetic_analysis is not None,
                "computational_design": self.binder_analysis is not None,
                "molecular_dynamics": self.md_analysis is not None
            },
            "experimental_validations": len(self.experimental_validations),
            "overall_confidence": self._calculate_overall_confidence()
        }
    
    def _calculate_overall_confidence(self) -> float:
        """Calculate overall confidence score from all analyses."""
        confidences = []
        
        if self.structural_analysis:
            confidences.append(self.structural_analysis.confidence_score)
        if self.evolutionary_analysis:
            confidences.append(self.evolutionary_analysis.confidence_score)
        if self.energetic_analysis:
            confidences.append(self.energetic_analysis.confidence_score)
        if self.binder_analysis:
            confidences.append(self.binder_analysis.confidence_score)
        if self.md_analysis:
            confidences.append(self.md_analysis.confidence_score)
        
        if confidences:
            return sum(confidences) / len(confidences)
        return 0.0

    def has_binder_data(self) -> bool:
        """Check if this hypothesis contains binder-specific data."""
        return self.binder_data is not None

    def get_target_sequence(self) -> Optional[str]:
        """Get the target sequence from binder data."""
        if self.binder_data:
            return self.binder_data.target_sequence
        return None
    
    def get_proposed_peptides(self) -> List[Dict[str, Any]]:
        """Get the proposed peptides from binder data."""
        if self.binder_data:
            return self.binder_data.proposed_peptides
        return []
    
    def add_binder_data(self, binder_data: Union[BinderHypothesisData, Dict[str, Any]]):
        """
        Add or update binder-specific data.
        
        Args:
            binder_data: Either a BinderHypothesisData object or dict
        """
        if isinstance(binder_data, dict):
            self.binder_data = BinderHypothesisData.from_dict(binder_data)
        else:
            self.binder_data = binder_data
        self.updated_at = time.time()

class MutationHypothesis(ProteinHypothesis):
    """
    Specialized hypothesis for mutation-based protein engineering.
    
    This class focuses specifically on hypotheses involving protein mutations
    and their predicted effects.
    """
    
    def __init__(self, **kwargs):
        """Initialize mutation hypothesis."""
        super().__init__(**kwargs)
        
        # Mutation-specific fields
        self.primary_mutation: Optional[Mutation] = kwargs.get("primary_mutation")
        self.secondary_mutations: List[Mutation] = kwargs.get("secondary_mutations", [])
        self.mutation_rationale: str = kwargs.get("mutation_rationale", "")
        self.expected_effects: List[str] = kwargs.get("expected_effects", [])
        
        # Predicted outcomes
        self.stability_prediction: Optional[float] = kwargs.get("stability_prediction")
        self.activity_prediction: Optional[float] = kwargs.get("activity_prediction")
        self.binding_prediction: Optional[float] = kwargs.get("binding_prediction")
        
        # Update hypothesis type
        self.hypothesis_type = "mutation_design"
    
    def get_mutation_summary(self) -> Dict[str, Any]:
        """Get summary of mutation-specific information."""
        all_mutations = []
        if self.primary_mutation:
            all_mutations.append(self.primary_mutation)
        all_mutations.extend(self.secondary_mutations)
        
        return {
            "total_mutations": len(all_mutations),
            "primary_mutation": str(self.primary_mutation) if self.primary_mutation else None,
            "secondary_mutations_count": len(self.secondary_mutations),
            "mutation_rationale": self.mutation_rationale,
            "expected_effects": self.expected_effects,
            "predictions": {
                "stability": self.stability_prediction,
                "activity": self.activity_prediction,
                "binding": self.binding_prediction
            }
        }
