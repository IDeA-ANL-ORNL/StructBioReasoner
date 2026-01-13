#!/usr/bin/env python3
"""
Multi-Community Agentic Thermostability Optimization

This simulation demonstrates multiple agentic communities working in parallel,
each with their own MD Expert, Structure Expert, Bioinformatics Expert, and Critics,
coordinated by a Protognosis-style supervisor that performs combinatorial optimization
of mutation proposals across all communities.

Features:
- Multiple Independent Agentic Communities (3-5 communities)
- Each community has: MD Expert, Structure Expert, Bioinformatics Expert, Critic
- Protognosis-style Supervisor for combinatorial mutation selection
- Advanced weighting and scoring algorithms
- Cross-community consensus building
- Scalable multi-agent coordination
"""

import asyncio
import logging
import json
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
import pandas as pd
from dataclasses import dataclass, field
import random
from itertools import combinations
import networkx as nx
from scipy.optimize import minimize
from sklearn.cluster import KMeans

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Set style for plots
plt.style.use('seaborn-v0_8')
sns.set_palette("husl")


@dataclass
class MutationProposal:
    """Enhanced mutation proposal with community tracking."""
    mutation: str
    position: int
    original: str
    mutant: str
    predicted_stability_change: float
    confidence: float
    rationale: str
    expert_source: str
    community_id: str
    supporting_evidence: List[str]
    interaction_score: float = 0.0  # For combinatorial analysis
    conservation_score: float = 0.0
    structural_impact: float = 0.0
    energetic_contribution: float = 0.0


@dataclass
class CommunityResults:
    """Results from a single agentic community."""
    community_id: str
    iteration: int
    proposals: List[MutationProposal]
    selected_mutations: List[MutationProposal]
    community_confidence: float
    expert_performances: Dict[str, float]
    critic_feedback: Dict[str, Any]
    specialization_focus: str


@dataclass
class SupervisorDecision:
    """Supervisor's combinatorial optimization decision."""
    iteration: int
    all_community_proposals: List[MutationProposal]
    selected_combination: List[MutationProposal]
    combination_score: float
    synergy_analysis: Dict[str, Any]
    community_weights: Dict[str, float]
    optimization_method: str
    confidence_assessment: float


class AgenticCommunity:
    """
    A complete agentic community with MD Expert, Structure Expert, 
    Bioinformatics Expert, and Critic.
    """
    
    def __init__(self, community_id: str, specialization: str = "general"):
        self.community_id = community_id
        self.specialization = specialization
        self.iteration_count = 0
        
        # Community-specific biases and strengths
        self.expertise_weights = self._initialize_expertise_weights(specialization)
        self.confidence_base = random.uniform(0.82, 0.90)
        self.innovation_factor = random.uniform(0.8, 1.2)
        
        # Performance tracking
        self.performance_history = []
        self.specialization_evolution = []
        
        logger.info(f"Initialized {specialization} community: {community_id}")
    
    def _initialize_expertise_weights(self, specialization: str) -> Dict[str, float]:
        """Initialize expertise weights based on community specialization."""
        base_weights = {"md_expert": 0.33, "structure_expert": 0.33, "bioinfo_expert": 0.34}
        
        if specialization == "structural":
            return {"md_expert": 0.25, "structure_expert": 0.50, "bioinfo_expert": 0.25}
        elif specialization == "dynamics":
            return {"md_expert": 0.50, "structure_expert": 0.30, "bioinfo_expert": 0.20}
        elif specialization == "evolutionary":
            return {"md_expert": 0.20, "structure_expert": 0.30, "bioinfo_expert": 0.50}
        elif specialization == "balanced":
            return {"md_expert": 0.35, "structure_expert": 0.35, "bioinfo_expert": 0.30}
        else:
            return base_weights
    
    async def generate_proposals(self, protein_data: Dict, iteration: int) -> CommunityResults:
        """Generate mutation proposals from all experts in the community."""
        self.iteration_count = iteration
        
        # Generate proposals from each expert with community-specific biases
        md_proposals = await self._generate_md_proposals(protein_data, iteration)
        structure_proposals = await self._generate_structure_proposals(protein_data, iteration)
        bioinfo_proposals = await self._generate_bioinfo_proposals(protein_data, iteration)
        
        all_proposals = md_proposals + structure_proposals + bioinfo_proposals
        
        # Apply community-specific enhancements
        enhanced_proposals = self._enhance_proposals_with_community_knowledge(all_proposals, iteration)
        
        # Community critic evaluation
        selected_mutations, critic_feedback = await self._community_critic_evaluation(
            enhanced_proposals, iteration
        )
        
        # Calculate community confidence
        community_confidence = self._calculate_community_confidence(selected_mutations, critic_feedback)
        
        # Track expert performances
        expert_performances = self._evaluate_expert_performances(
            md_proposals, structure_proposals, bioinfo_proposals, selected_mutations
        )
        
        results = CommunityResults(
            community_id=self.community_id,
            iteration=iteration,
            proposals=enhanced_proposals,
            selected_mutations=selected_mutations,
            community_confidence=community_confidence,
            expert_performances=expert_performances,
            critic_feedback=critic_feedback,
            specialization_focus=self.specialization
        )
        
        self.performance_history.append(results)
        return results
    
    async def _generate_md_proposals(self, protein_data: Dict, iteration: int) -> List[MutationProposal]:
        """Generate MD expert proposals with community-specific focus."""
        base_confidence = self.confidence_base * self.expertise_weights["md_expert"]
        proposals = []
        
        # Community-specific MD mutations
        md_mutations_by_specialization = {
            "structural": [
                ("I44V", 44, "I", "V", 0.15, "Hydrophobic core optimization"),
                ("L67F", 67, "L", "F", 0.12, "Aromatic stacking enhancement"),
                ("V26I", 26, "V", "I", 0.10, "Packing density improvement"),
            ],
            "dynamics": [
                ("K63R", 63, "K", "R", 0.14, "Hydrogen bonding network"),
                ("Q49E", 49, "Q", "E", 0.11, "Salt bridge formation"),
                ("T14S", 14, "T", "S", 0.08, "Conformational entropy reduction"),
            ],
            "evolutionary": [
                ("I44A", 44, "I", "A", 0.09, "Evolutionary conservation"),
                ("F45Y", 45, "F", "Y", 0.13, "Functional site optimization"),
            ],
            "balanced": [
                ("I44V", 44, "I", "V", 0.15, "Core stability"),
                ("K63R", 63, "K", "R", 0.12, "Electrostatic optimization"),
                ("L67F", 67, "L", "F", 0.10, "Aromatic interactions"),
            ]
        }
        
        mutations = md_mutations_by_specialization.get(self.specialization, 
                                                     md_mutations_by_specialization["balanced"])
        
        for mut, pos, orig, new, base_effect, rationale in mutations:
            # Add iteration and community-specific improvements
            stability_change = base_effect * self.innovation_factor + (iteration * 0.02) + random.uniform(-0.03, 0.03)
            confidence = min(0.95, base_confidence + (iteration * 0.015) + random.uniform(-0.05, 0.05))
            
            # Enhanced evidence with community focus
            evidence = [
                f"MD simulation: {stability_change:.3f} kcal/mol stabilization",
                f"RMSD reduction: {random.uniform(0.2, 0.8):.2f} Å",
                f"Community {self.community_id} specialization: {self.specialization}"
            ]
            
            proposal = MutationProposal(
                mutation=mut,
                position=pos,
                original=orig,
                mutant=new,
                predicted_stability_change=stability_change,
                confidence=confidence,
                rationale=rationale,
                expert_source="MD Expert",
                community_id=self.community_id,
                supporting_evidence=evidence,
                conservation_score=random.uniform(0.6, 0.9),
                structural_impact=random.uniform(0.5, 0.8),
                energetic_contribution=stability_change
            )
            proposals.append(proposal)
        
        return proposals
    
    async def _generate_structure_proposals(self, protein_data: Dict, iteration: int) -> List[MutationProposal]:
        """Generate Structure expert proposals with community-specific focus."""
        base_confidence = self.confidence_base * self.expertise_weights["structure_expert"]
        proposals = []
        
        structure_mutations_by_specialization = {
            "structural": [
                ("F45Y", 45, "F", "Y", 0.16, "Enhanced hydrogen bonding"),
                ("D52N", 52, "D", "N", 0.14, "Electrostatic optimization"),
                ("G75A", 75, "G", "A", 0.09, "Backbone rigidity"),
                ("S57T", 57, "S", "T", 0.07, "Side chain interactions"),
            ],
            "dynamics": [
                ("V26I", 26, "V", "I", 0.11, "Dynamic stability"),
                ("P19S", 19, "P", "S", 0.08, "Flexibility control"),
            ],
            "evolutionary": [
                ("E34D", 34, "E", "D", 0.10, "Conservation-guided"),
                ("N25Q", 25, "N", "Q", 0.08, "Functional preservation"),
            ],
            "balanced": [
                ("F45Y", 45, "F", "Y", 0.13, "Hydrogen bonding"),
                ("D52N", 52, "D", "N", 0.11, "Electrostatic balance"),
                ("V26I", 26, "V", "I", 0.09, "Hydrophobic packing"),
            ]
        }
        
        mutations = structure_mutations_by_specialization.get(self.specialization,
                                                            structure_mutations_by_specialization["balanced"])
        
        for mut, pos, orig, new, base_effect, rationale in mutations:
            stability_change = base_effect * self.innovation_factor + (iteration * 0.025) + random.uniform(-0.02, 0.04)
            confidence = min(0.96, base_confidence + (iteration * 0.012) + random.uniform(-0.04, 0.04))
            
            evidence = [
                f"AlphaFold confidence: {random.uniform(85, 95):.1f}%",
                f"Structural analysis: {stability_change:.3f} kcal/mol improvement",
                f"Community specialization: {self.specialization}"
            ]
            
            proposal = MutationProposal(
                mutation=mut,
                position=pos,
                original=orig,
                mutant=new,
                predicted_stability_change=stability_change,
                confidence=confidence,
                rationale=rationale,
                expert_source="Structure Expert",
                community_id=self.community_id,
                supporting_evidence=evidence,
                conservation_score=random.uniform(0.5, 0.8),
                structural_impact=random.uniform(0.7, 0.9),
                energetic_contribution=stability_change
            )
            proposals.append(proposal)
        
        return proposals
    
    async def _generate_bioinfo_proposals(self, protein_data: Dict, iteration: int) -> List[MutationProposal]:
        """Generate Bioinformatics expert proposals with community-specific focus."""
        base_confidence = self.confidence_base * self.expertise_weights["bioinfo_expert"]
        proposals = []
        
        bioinfo_mutations_by_specialization = {
            "evolutionary": [
                ("R72K", 72, "R", "K", 0.12, "Evolutionary optimization"),
                ("E34D", 34, "E", "D", 0.10, "Conservation analysis"),
                ("N25Q", 25, "N", "Q", 0.08, "Phylogenetic guidance"),
                ("A46V", 46, "A", "V", 0.11, "Homology modeling"),
            ],
            "structural": [
                ("A46V", 46, "A", "V", 0.09, "Structural conservation"),
                ("P19S", 19, "P", "S", 0.06, "Loop optimization"),
            ],
            "dynamics": [
                ("R72K", 72, "R", "K", 0.08, "Dynamic conservation"),
            ],
            "balanced": [
                ("R72K", 72, "R", "K", 0.09, "Electrostatic balance"),
                ("A46V", 46, "A", "V", 0.08, "Hydrophobic enhancement"),
            ]
        }
        
        mutations = bioinfo_mutations_by_specialization.get(self.specialization,
                                                          bioinfo_mutations_by_specialization["balanced"])
        
        for mut, pos, orig, new, base_effect, rationale in mutations:
            stability_change = base_effect * self.innovation_factor + (iteration * 0.018) + random.uniform(-0.025, 0.035)
            confidence = min(0.92, base_confidence + (iteration * 0.020) + random.uniform(-0.06, 0.06))
            
            evidence = [
                f"Conservation score: {random.uniform(0.7, 0.95):.2f}",
                f"Phylogenetic analysis: {stability_change:.3f} kcal/mol",
                f"Community focus: {self.specialization}"
            ]
            
            proposal = MutationProposal(
                mutation=mut,
                position=pos,
                original=orig,
                mutant=new,
                predicted_stability_change=stability_change,
                confidence=confidence,
                rationale=rationale,
                expert_source="Bioinformatics Expert",
                community_id=self.community_id,
                supporting_evidence=evidence,
                conservation_score=random.uniform(0.8, 0.95),
                structural_impact=random.uniform(0.4, 0.7),
                energetic_contribution=stability_change
            )
            proposals.append(proposal)
        
        return proposals
    
    def _enhance_proposals_with_community_knowledge(self, proposals: List[MutationProposal], 
                                                  iteration: int) -> List[MutationProposal]:
        """Enhance proposals with community-specific knowledge and cross-expert insights."""
        enhanced_proposals = []
        
        for proposal in proposals:
            # Calculate interaction scores based on community specialization
            if self.specialization == "structural":
                proposal.interaction_score = proposal.structural_impact * 1.2
            elif self.specialization == "dynamics":
                proposal.interaction_score = proposal.energetic_contribution * 1.3
            elif self.specialization == "evolutionary":
                proposal.interaction_score = proposal.conservation_score * 1.1
            else:
                proposal.interaction_score = (proposal.structural_impact + 
                                            proposal.conservation_score + 
                                            abs(proposal.energetic_contribution)) / 3
            
            # Community learning: improve proposals based on history
            if len(self.performance_history) > 0:
                historical_success = np.mean([r.community_confidence for r in self.performance_history])
                proposal.confidence *= (0.9 + 0.2 * historical_success)
                proposal.predicted_stability_change *= (0.95 + 0.1 * historical_success)
            
            enhanced_proposals.append(proposal)
        
        return enhanced_proposals
    
    async def _community_critic_evaluation(self, proposals: List[MutationProposal], 
                                         iteration: int) -> Tuple[List[MutationProposal], Dict[str, Any]]:
        """Community-specific critic evaluation and selection."""
        # Score proposals based on community specialization
        scored_proposals = []
        
        for proposal in proposals:
            # Multi-criteria scoring with community bias
            stability_score = min(1.0, abs(proposal.predicted_stability_change) / 0.2)
            confidence_score = proposal.confidence
            interaction_score = proposal.interaction_score
            specialization_bonus = 0.1 if proposal.expert_source.lower().replace(" expert", "") in self.specialization else 0.0
            
            # Community-specific weighting
            if self.specialization == "structural":
                composite_score = (0.3 * stability_score + 0.25 * confidence_score + 
                                 0.35 * interaction_score + 0.1 * specialization_bonus)
            elif self.specialization == "dynamics":
                composite_score = (0.45 * stability_score + 0.25 * confidence_score + 
                                 0.2 * interaction_score + 0.1 * specialization_bonus)
            elif self.specialization == "evolutionary":
                composite_score = (0.25 * stability_score + 0.35 * confidence_score + 
                                 0.3 * interaction_score + 0.1 * specialization_bonus)
            else:
                composite_score = (0.35 * stability_score + 0.3 * confidence_score + 
                                 0.25 * interaction_score + 0.1 * specialization_bonus)
            
            scored_proposals.append((proposal, composite_score))
        
        # Sort and select top proposals
        scored_proposals.sort(key=lambda x: x[1], reverse=True)
        num_selected = min(3 + iteration, len(scored_proposals))
        selected = [proposal for proposal, score in scored_proposals[:num_selected]]
        
        # Generate critic feedback
        critic_feedback = {
            "community_id": self.community_id,
            "specialization": self.specialization,
            "proposals_evaluated": len(proposals),
            "proposals_selected": len(selected),
            "selection_criteria": f"{self.specialization}_optimized",
            "average_score": np.mean([score for _, score in scored_proposals[:num_selected]]),
            "community_focus_bonus": specialization_bonus > 0
        }
        
        return selected, critic_feedback
    
    def _calculate_community_confidence(self, selected_mutations: List[MutationProposal], 
                                      critic_feedback: Dict[str, Any]) -> float:
        """Calculate overall community confidence."""
        if not selected_mutations:
            return 0.0
        
        base_confidence = np.mean([m.confidence for m in selected_mutations])
        selection_quality = critic_feedback.get("average_score", 0.5)
        specialization_bonus = 0.05 if critic_feedback.get("community_focus_bonus", False) else 0.0
        
        community_confidence = base_confidence * 0.7 + selection_quality * 0.3 + specialization_bonus
        return min(0.98, community_confidence)
    
    def _evaluate_expert_performances(self, md_proposals: List[MutationProposal],
                                    structure_proposals: List[MutationProposal],
                                    bioinfo_proposals: List[MutationProposal],
                                    selected_mutations: List[MutationProposal]) -> Dict[str, float]:
        """Evaluate individual expert performances within the community."""
        expert_performances = {}
        
        # Count selections by expert
        expert_selections = {"MD Expert": 0, "Structure Expert": 0, "Bioinformatics Expert": 0}
        expert_proposals = {"MD Expert": len(md_proposals), "Structure Expert": len(structure_proposals), 
                          "Bioinformatics Expert": len(bioinfo_proposals)}
        
        for mutation in selected_mutations:
            expert_selections[mutation.expert_source] += 1
        
        # Calculate performance scores
        for expert in expert_selections:
            if expert_proposals[expert] > 0:
                selection_rate = expert_selections[expert] / expert_proposals[expert]
                # Get average confidence of selected mutations from this expert
                expert_selected = [m for m in selected_mutations if m.expert_source == expert]
                avg_confidence = np.mean([m.confidence for m in expert_selected]) if expert_selected else 0
                
                performance_score = selection_rate * 0.6 + avg_confidence * 0.4
                expert_performances[expert] = performance_score
            else:
                expert_performances[expert] = 0.0
        
        return expert_performances


class ProtognosisSupervisor:
    """
    Protognosis-style supervisor that performs combinatorial optimization
    across multiple agentic communities.
    """

    def __init__(self, communities: List[AgenticCommunity]):
        self.communities = communities
        self.community_weights = {c.community_id: 1.0 for c in communities}
        self.optimization_history = []
        self.synergy_network = nx.Graph()

        # Protognosis-style parameters
        self.max_combinations = 50  # Maximum combinations to evaluate
        self.synergy_threshold = 0.1  # Minimum synergy for combination
        self.diversity_weight = 0.15  # Weight for diversity in selection
        self.consensus_weight = 0.25  # Weight for cross-community consensus

        logger.info(f"Initialized Protognosis Supervisor with {len(communities)} communities")

    async def optimize_mutation_combination(self, community_results: List[CommunityResults],
                                          iteration: int) -> SupervisorDecision:
        """
        Perform Protognosis-style combinatorial optimization across all community proposals.
        """
        logger.info(f"Supervisor optimizing combinations from {len(community_results)} communities (iteration {iteration})")

        # Collect all proposals from all communities
        all_proposals = []
        for result in community_results:
            all_proposals.extend(result.selected_mutations)

        logger.info(f"Total proposals to optimize: {len(all_proposals)}")

        # Update community weights based on performance
        self._update_community_weights(community_results, iteration)

        # Perform combinatorial analysis
        optimal_combination, combination_score, synergy_analysis = await self._combinatorial_optimization(
            all_proposals, community_results, iteration
        )

        # Calculate confidence assessment
        confidence_assessment = self._assess_combination_confidence(
            optimal_combination, community_results, synergy_analysis
        )

        # Create supervisor decision
        decision = SupervisorDecision(
            iteration=iteration,
            all_community_proposals=all_proposals,
            selected_combination=optimal_combination,
            combination_score=combination_score,
            synergy_analysis=synergy_analysis,
            community_weights=self.community_weights.copy(),
            optimization_method="protognosis_combinatorial",
            confidence_assessment=confidence_assessment
        )

        self.optimization_history.append(decision)

        logger.info(f"Supervisor selected {len(optimal_combination)} mutations with score {combination_score:.3f}")

        return decision

    def _update_community_weights(self, community_results: List[CommunityResults], iteration: int):
        """Update community weights based on historical performance."""
        for result in community_results:
            community_id = result.community_id

            # Base weight on community confidence and proposal quality
            base_weight = result.community_confidence

            # Historical performance bonus
            if len(self.optimization_history) > 0:
                historical_selections = 0
                total_historical = 0

                for past_decision in self.optimization_history:
                    community_selections = sum(1 for m in past_decision.selected_combination
                                             if m.community_id == community_id)
                    historical_selections += community_selections
                    total_historical += len(past_decision.selected_combination)

                if total_historical > 0:
                    historical_success_rate = historical_selections / total_historical
                    base_weight = base_weight * 0.7 + historical_success_rate * 0.3

            # Specialization bonus (communities with unique specializations get slight boost)
            specialization_bonus = 0.05 if result.specialization_focus != "balanced" else 0.0

            # Update weight with momentum
            old_weight = self.community_weights.get(community_id, 1.0)
            new_weight = old_weight * 0.8 + (base_weight + specialization_bonus) * 0.2

            self.community_weights[community_id] = max(0.1, min(2.0, new_weight))

    async def _combinatorial_optimization(self, all_proposals: List[MutationProposal],
                                        community_results: List[CommunityResults],
                                        iteration: int) -> Tuple[List[MutationProposal], float, Dict[str, Any]]:
        """
        Perform Protognosis-style combinatorial optimization.
        """
        # Remove duplicate mutations (same position, different communities)
        unique_proposals = self._deduplicate_proposals(all_proposals)

        # Calculate interaction matrix for synergy analysis
        interaction_matrix = self._calculate_interaction_matrix(unique_proposals)

        # Generate candidate combinations
        candidate_combinations = self._generate_candidate_combinations(unique_proposals, iteration)

        # Evaluate each combination
        best_combination = None
        best_score = -float('inf')
        best_synergy_analysis = {}

        for combination in candidate_combinations:
            score, synergy_analysis = self._evaluate_combination(
                combination, interaction_matrix, community_results, iteration
            )

            if score > best_score:
                best_score = score
                best_combination = combination
                best_synergy_analysis = synergy_analysis

        # If no good combination found, fall back to top individual mutations
        if best_combination is None or len(best_combination) == 0:
            best_combination = self._fallback_selection(unique_proposals, iteration)
            best_score, best_synergy_analysis = self._evaluate_combination(
                best_combination, interaction_matrix, community_results, iteration
            )

        return best_combination, best_score, best_synergy_analysis

    def _deduplicate_proposals(self, all_proposals: List[MutationProposal]) -> List[MutationProposal]:
        """Remove duplicate mutations, keeping the highest confidence version."""
        position_map = {}

        for proposal in all_proposals:
            position = proposal.position
            if position not in position_map:
                position_map[position] = proposal
            else:
                # Keep the proposal with higher confidence
                if proposal.confidence > position_map[position].confidence:
                    position_map[position] = proposal
                # If same confidence, prefer higher predicted effect
                elif (proposal.confidence == position_map[position].confidence and
                      abs(proposal.predicted_stability_change) > abs(position_map[position].predicted_stability_change)):
                    position_map[position] = proposal

        return list(position_map.values())

    def _calculate_interaction_matrix(self, proposals: List[MutationProposal]) -> np.ndarray:
        """Calculate pairwise interaction scores between mutations."""
        n = len(proposals)
        interaction_matrix = np.zeros((n, n))

        for i in range(n):
            for j in range(i + 1, n):
                interaction_score = self._calculate_pairwise_interaction(proposals[i], proposals[j])
                interaction_matrix[i, j] = interaction_score
                interaction_matrix[j, i] = interaction_score

        return interaction_matrix

    def _calculate_pairwise_interaction(self, mut1: MutationProposal, mut2: MutationProposal) -> float:
        """Calculate interaction score between two mutations."""
        # Distance-based interaction (closer mutations have higher interaction potential)
        distance = abs(mut1.position - mut2.position)
        distance_factor = np.exp(-distance / 20.0)  # Exponential decay with distance

        # Complementary effects (different types of improvements)
        complementarity = 0.0
        if mut1.expert_source != mut2.expert_source:
            complementarity = 0.1  # Bonus for different expert sources

        # Structural region interactions
        structural_bonus = 0.0
        if (mut1.position in [44, 45, 46] and mut2.position in [44, 45, 46]) or \
           (mut1.position in [63, 64, 65] and mut2.position in [63, 64, 65]):
            structural_bonus = 0.15  # Bonus for mutations in same structural region

        # Community diversity bonus
        community_bonus = 0.05 if mut1.community_id != mut2.community_id else 0.0

        # Combined interaction score
        interaction_score = (distance_factor * 0.4 + complementarity +
                           structural_bonus + community_bonus)

        return min(1.0, interaction_score)

    def _generate_candidate_combinations(self, proposals: List[MutationProposal],
                                       iteration: int) -> List[List[MutationProposal]]:
        """Generate candidate mutation combinations for evaluation."""
        candidates = []

        # Sort proposals by predicted effect
        sorted_proposals = sorted(proposals, key=lambda x: abs(x.predicted_stability_change), reverse=True)

        # Single mutations (top performers)
        for i in range(min(5, len(sorted_proposals))):
            candidates.append([sorted_proposals[i]])

        # Pairwise combinations
        for i in range(min(8, len(sorted_proposals))):
            for j in range(i + 1, min(8, len(sorted_proposals))):
                candidates.append([sorted_proposals[i], sorted_proposals[j]])

        # Triple combinations (more selective)
        for i in range(min(5, len(sorted_proposals))):
            for j in range(i + 1, min(5, len(sorted_proposals))):
                for k in range(j + 1, min(5, len(sorted_proposals))):
                    candidates.append([sorted_proposals[i], sorted_proposals[j], sorted_proposals[k]])

        # Larger combinations for later iterations
        if iteration >= 3:
            # Quadruple combinations
            for combo in combinations(sorted_proposals[:6], 4):
                candidates.append(list(combo))

        if iteration >= 4:
            # Quintuple combinations
            for combo in combinations(sorted_proposals[:5], 5):
                candidates.append(list(combo))

        # Limit total candidates
        if len(candidates) > self.max_combinations:
            # Keep diverse set of candidates
            candidates = self._select_diverse_candidates(candidates, self.max_combinations)

        return candidates

    def _select_diverse_candidates(self, candidates: List[List[MutationProposal]],
                                 max_candidates: int) -> List[List[MutationProposal]]:
        """Select diverse set of candidates using clustering."""
        if len(candidates) <= max_candidates:
            return candidates

        # Create feature vectors for candidates
        features = []
        for candidate in candidates:
            feature_vector = [
                len(candidate),  # Size of combination
                np.mean([m.predicted_stability_change for m in candidate]),  # Average effect
                np.mean([m.confidence for m in candidate]),  # Average confidence
                len(set(m.community_id for m in candidate)),  # Community diversity
                len(set(m.expert_source for m in candidate)),  # Expert diversity
            ]
            features.append(feature_vector)

        # Cluster candidates
        features_array = np.array(features)
        n_clusters = min(max_candidates, len(candidates))
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        clusters = kmeans.fit_predict(features_array)

        # Select one candidate from each cluster (the one closest to centroid)
        selected_candidates = []
        for cluster_id in range(n_clusters):
            cluster_indices = np.where(clusters == cluster_id)[0]
            cluster_center = kmeans.cluster_centers_[cluster_id]

            # Find candidate closest to cluster center
            best_distance = float('inf')
            best_candidate = None

            for idx in cluster_indices:
                distance = np.linalg.norm(features_array[idx] - cluster_center)
                if distance < best_distance:
                    best_distance = distance
                    best_candidate = candidates[idx]

            if best_candidate:
                selected_candidates.append(best_candidate)

        return selected_candidates

    def _evaluate_combination(self, combination: List[MutationProposal],
                            interaction_matrix: np.ndarray,
                            community_results: List[CommunityResults],
                            iteration: int) -> Tuple[float, Dict[str, Any]]:
        """Evaluate a mutation combination using Protognosis-style scoring."""
        if not combination:
            return 0.0, {}

        # Individual mutation scores
        individual_scores = []
        for mutation in combination:
            # Base score from predicted effect and confidence
            base_score = abs(mutation.predicted_stability_change) * mutation.confidence

            # Community weight bonus
            community_weight = self.community_weights.get(mutation.community_id, 1.0)
            weighted_score = base_score * community_weight

            individual_scores.append(weighted_score)

        # Synergy analysis
        synergy_score = 0.0
        synergy_pairs = []

        if len(combination) > 1:
            # Find indices in original proposal list for interaction matrix lookup
            all_proposals = []
            for result in community_results:
                all_proposals.extend(result.selected_mutations)
            unique_proposals = self._deduplicate_proposals(all_proposals)

            for i, mut1 in enumerate(combination):
                for j, mut2 in enumerate(combination[i + 1:], i + 1):
                    try:
                        idx1 = next(k for k, p in enumerate(unique_proposals)
                                  if p.position == mut1.position)
                        idx2 = next(k for k, p in enumerate(unique_proposals)
                                  if p.position == mut2.position)

                        if idx1 < len(interaction_matrix) and idx2 < len(interaction_matrix):
                            pairwise_synergy = interaction_matrix[idx1, idx2]
                            synergy_score += pairwise_synergy
                            synergy_pairs.append((mut1.mutation, mut2.mutation, pairwise_synergy))
                    except (StopIteration, IndexError):
                        continue

        # Diversity bonuses
        community_diversity = len(set(m.community_id for m in combination)) / len(self.communities)
        expert_diversity = len(set(m.expert_source for m in combination)) / 3  # 3 expert types

        # Consensus bonus (mutations proposed by multiple communities)
        consensus_bonus = 0.0
        for mutation in combination:
            similar_proposals = sum(1 for result in community_results
                                 for m in result.selected_mutations
                                 if m.position == mutation.position)
            if similar_proposals > 1:
                consensus_bonus += 0.1 * (similar_proposals - 1)

        # Calculate final score
        base_score = np.sum(individual_scores)
        diversity_bonus = (community_diversity + expert_diversity) * self.diversity_weight
        consensus_contribution = consensus_bonus * self.consensus_weight

        final_score = base_score + synergy_score + diversity_bonus + consensus_contribution

        # Synergy analysis for reporting
        synergy_analysis = {
            "individual_contributions": {m.mutation: score for m, score in zip(combination, individual_scores)},
            "synergy_score": synergy_score,
            "synergy_pairs": synergy_pairs,
            "community_diversity": community_diversity,
            "expert_diversity": expert_diversity,
            "consensus_bonus": consensus_bonus,
            "total_score": final_score
        }

        return final_score, synergy_analysis

    def _fallback_selection(self, proposals: List[MutationProposal], iteration: int) -> List[MutationProposal]:
        """Fallback selection when no good combinations are found."""
        # Sort by weighted score
        weighted_proposals = []
        for proposal in proposals:
            community_weight = self.community_weights.get(proposal.community_id, 1.0)
            weighted_score = abs(proposal.predicted_stability_change) * proposal.confidence * community_weight
            weighted_proposals.append((proposal, weighted_score))

        weighted_proposals.sort(key=lambda x: x[1], reverse=True)

        # Select top mutations ensuring diversity
        selected = []
        used_positions = set()
        used_communities = set()

        for proposal, score in weighted_proposals:
            if len(selected) >= min(3 + iteration, 8):
                break

            # Avoid duplicate positions
            if proposal.position in used_positions:
                continue

            # Prefer community diversity
            if len(used_communities) < len(self.communities) and proposal.community_id in used_communities:
                continue

            selected.append(proposal)
            used_positions.add(proposal.position)
            used_communities.add(proposal.community_id)

        return selected

    def _assess_combination_confidence(self, combination: List[MutationProposal],
                                     community_results: List[CommunityResults],
                                     synergy_analysis: Dict[str, Any]) -> float:
        """Assess confidence in the selected combination."""
        if not combination:
            return 0.0

        # Base confidence from individual mutations
        individual_confidence = np.mean([m.confidence for m in combination])

        # Community consensus confidence
        community_confidences = [r.community_confidence for r in community_results]
        consensus_confidence = np.mean(community_confidences)

        # Synergy confidence (higher synergy = higher confidence)
        synergy_confidence = min(1.0, synergy_analysis.get("synergy_score", 0.0))

        # Diversity confidence (more diverse = more robust)
        diversity_confidence = synergy_analysis.get("community_diversity", 0.0) * 0.5 + \
                              synergy_analysis.get("expert_diversity", 0.0) * 0.5

        # Combined confidence assessment
        final_confidence = (individual_confidence * 0.4 +
                          consensus_confidence * 0.3 +
                          synergy_confidence * 0.2 +
                          diversity_confidence * 0.1)

        return min(0.98, final_confidence)


class MultiCommunityThermostabilitySimulation:
    """
    Main simulation class coordinating multiple agentic communities
    with Protognosis-style supervisor optimization.
    """

    def __init__(self, num_communities: int = 4):
        self.num_communities = num_communities
        self.communities = []
        self.supervisor = None
        self.simulation_results = []
        self.baseline_stability = 45.2  # kcal/mol

        # Initialize communities with different specializations
        specializations = ["structural", "dynamics", "evolutionary", "balanced"]
        for i in range(num_communities):
            specialization = specializations[i % len(specializations)]
            community_id = f"community_{i+1}_{specialization}"
            community = AgenticCommunity(community_id, specialization)
            self.communities.append(community)

        # Initialize Protognosis supervisor
        self.supervisor = ProtognosisSupervisor(self.communities)

        logger.info(f"Initialized multi-community simulation with {num_communities} communities")

    async def run_simulation(self, num_iterations: int = 5) -> List[Dict[str, Any]]:
        """Run the complete multi-community simulation."""
        logger.info(f"Starting {num_iterations}-iteration multi-community simulation")

        current_stability = self.baseline_stability

        for iteration in range(1, num_iterations + 1):
            logger.info(f"\n{'='*80}")
            logger.info(f"MULTI-COMMUNITY ITERATION {iteration}/{num_iterations}")
            logger.info(f"{'='*80}")

            # Protein data for this iteration
            protein_data = {
                "name": "ubiquitin",
                "current_stability": current_stability,
                "iteration": iteration,
                "baseline_stability": self.baseline_stability
            }

            # Phase 1: Each community generates proposals
            logger.info(f"Phase 1: Community proposal generation")
            community_results = []

            for community in self.communities:
                logger.info(f"  • {community.community_id} ({community.specialization}) generating proposals...")
                result = await community.generate_proposals(protein_data, iteration)
                community_results.append(result)
                logger.info(f"    → {len(result.selected_mutations)} mutations selected, "
                          f"{result.community_confidence:.3f} confidence")

            # Phase 2: Supervisor combinatorial optimization
            logger.info(f"Phase 2: Supervisor combinatorial optimization")
            supervisor_decision = await self.supervisor.optimize_mutation_combination(
                community_results, iteration
            )

            # Phase 3: Calculate stability improvement
            logger.info(f"Phase 3: Stability assessment")
            predicted_improvement = sum(m.predicted_stability_change for m in supervisor_decision.selected_combination)

            # Add realistic experimental noise and diminishing returns
            actual_improvement = predicted_improvement * (0.9 + random.uniform(-0.1, 0.1))
            if iteration > 3:
                actual_improvement *= (0.85 + iteration * 0.03)  # Diminishing returns

            new_stability = current_stability + actual_improvement

            # Store iteration results
            iteration_result = {
                "iteration": iteration,
                "community_results": community_results,
                "supervisor_decision": supervisor_decision,
                "predicted_improvement": predicted_improvement,
                "actual_improvement": actual_improvement,
                "baseline_stability": current_stability,
                "new_stability": new_stability,
                "total_proposals": sum(len(r.proposals) for r in community_results),
                "selected_mutations": len(supervisor_decision.selected_combination),
                "supervisor_confidence": supervisor_decision.confidence_assessment
            }

            self.simulation_results.append(iteration_result)
            current_stability = new_stability

            # Log iteration summary
            logger.info(f"Iteration {iteration} Summary:")
            logger.info(f"  • Total proposals from communities: {iteration_result['total_proposals']}")
            logger.info(f"  • Supervisor selected: {iteration_result['selected_mutations']} mutations")
            logger.info(f"  • Predicted improvement: +{predicted_improvement:.3f} kcal/mol")
            logger.info(f"  • Actual improvement: +{actual_improvement:.3f} kcal/mol")
            logger.info(f"  • New stability: {new_stability:.3f} kcal/mol")
            logger.info(f"  • Supervisor confidence: {supervisor_decision.confidence_assessment:.3f}")

            # Show selected mutations
            logger.info(f"  • Selected mutations:")
            for mut in supervisor_decision.selected_combination:
                logger.info(f"    - {mut.mutation} ({mut.community_id}, {mut.expert_source}): "
                          f"+{mut.predicted_stability_change:.3f} kcal/mol")

            await asyncio.sleep(0.1)  # Brief pause for realism

        final_improvement = current_stability - self.baseline_stability
        logger.info(f"\nMulti-Community Simulation Complete!")
        logger.info(f"Final stability: {current_stability:.3f} kcal/mol")
        logger.info(f"Total improvement: +{final_improvement:.3f} kcal/mol")

        return self.simulation_results

    def generate_comprehensive_visualizations(self, output_dir: str = "multi_community_results"):
        """Generate comprehensive visualizations for multi-community simulation."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        # Generate multiple visualization types
        self._plot_multi_community_progression(output_path)
        self._plot_community_contributions(output_path)
        self._plot_supervisor_optimization(output_path)
        self._plot_synergy_analysis(output_path)
        self._plot_community_evolution(output_path)

        logger.info(f"Multi-community visualizations saved to {output_path}")

    def _plot_multi_community_progression(self, output_path: Path):
        """Plot overall stability progression with community breakdown."""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))

        # Extract data
        iterations = [r["iteration"] for r in self.simulation_results]
        stabilities = [self.baseline_stability] + [r["new_stability"] for r in self.simulation_results]
        improvements = [0] + [r["actual_improvement"] for r in self.simulation_results]
        supervisor_confidences = [r["supervisor_confidence"] for r in self.simulation_results]

        # Plot 1: Overall stability progression
        ax1 = axes[0, 0]
        iter_range = [0] + iterations
        ax1.plot(iter_range, stabilities, 'o-', linewidth=3, markersize=8, color='#2E86AB')
        ax1.fill_between(iter_range, stabilities, alpha=0.3, color='#2E86AB')
        ax1.set_xlabel('Iteration')
        ax1.set_ylabel('Thermostability (kcal/mol)')
        ax1.set_title('Multi-Community Stability Progression', fontweight='bold')
        ax1.grid(True, alpha=0.3)

        # Add improvement annotations
        for i, (iter_num, improvement) in enumerate(zip(iterations, improvements)):
            ax1.annotate(f'+{improvement:.2f}',
                        xy=(iter_num, stabilities[i+1]),
                        xytext=(5, 10),
                        textcoords='offset points',
                        fontsize=9,
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))

        # Plot 2: Improvement per iteration
        ax2 = axes[0, 1]
        colors = ['#A23B72', '#F18F01', '#C73E1D', '#2E86AB', '#A23B72'][:len(improvements)-1]
        ax2.bar(iterations, improvements[1:], color=colors)
        ax2.set_xlabel('Iteration')
        ax2.set_ylabel('Stability Improvement (kcal/mol)')
        ax2.set_title('Improvement per Iteration', fontweight='bold')
        ax2.grid(True, alpha=0.3, axis='y')

        # Plot 3: Supervisor confidence evolution
        ax3 = axes[1, 0]
        ax3.plot(iterations, supervisor_confidences, 's-', linewidth=2, markersize=6, color='#C73E1D')
        ax3.set_xlabel('Iteration')
        ax3.set_ylabel('Supervisor Confidence')
        ax3.set_title('Supervisor Confidence Evolution', fontweight='bold')
        ax3.grid(True, alpha=0.3)
        ax3.set_ylim(0.7, 1.0)

        # Plot 4: Mutations selected per iteration
        ax4 = axes[1, 1]
        mutations_selected = [r["selected_mutations"] for r in self.simulation_results]
        total_proposals = [r["total_proposals"] for r in self.simulation_results]

        ax4.bar(iterations, total_proposals, alpha=0.6, label='Total Proposals', color='lightblue')
        ax4.bar(iterations, mutations_selected, label='Selected Mutations', color='darkblue')
        ax4.set_xlabel('Iteration')
        ax4.set_ylabel('Number of Mutations')
        ax4.set_title('Proposal vs Selection', fontweight='bold')
        ax4.legend()
        ax4.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(output_path / 'multi_community_progression.png', dpi=300, bbox_inches='tight')
        plt.close()

    def _plot_community_contributions(self, output_path: Path):
        """Plot individual community contributions over iterations."""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))

        # Prepare community data
        community_data = {community.community_id: {"contributions": [], "confidences": [], "selections": []}
                         for community in self.communities}

        for result in self.simulation_results:
            # Track contributions by community
            for community_id in community_data.keys():
                community_contribution = 0
                community_selections = 0

                for mutation in result["supervisor_decision"].selected_combination:
                    if mutation.community_id == community_id:
                        community_contribution += mutation.predicted_stability_change
                        community_selections += 1

                community_data[community_id]["contributions"].append(community_contribution)
                community_data[community_id]["selections"].append(community_selections)

            # Track community confidences
            for community_result in result["community_results"]:
                community_data[community_result.community_id]["confidences"].append(
                    community_result.community_confidence
                )

        iterations = [r["iteration"] for r in self.simulation_results]
        colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D']

        # Plot 1: Community contributions over time
        ax1 = axes[0, 0]
        for i, (community_id, data) in enumerate(community_data.items()):
            ax1.plot(iterations, data["contributions"], 'o-',
                    label=community_id.replace('community_', '').replace('_', ' ').title(),
                    color=colors[i % len(colors)], linewidth=2)
        ax1.set_xlabel('Iteration')
        ax1.set_ylabel('Contribution (kcal/mol)')
        ax1.set_title('Community Contributions Over Time', fontweight='bold')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Plot 2: Community selection rates
        ax2 = axes[0, 1]
        for i, (community_id, data) in enumerate(community_data.items()):
            ax2.plot(iterations, data["selections"], 's-',
                    label=community_id.replace('community_', '').replace('_', ' ').title(),
                    color=colors[i % len(colors)], linewidth=2)
        ax2.set_xlabel('Iteration')
        ax2.set_ylabel('Number of Selected Mutations')
        ax2.set_title('Community Selection Rates', fontweight='bold')
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        # Plot 3: Community confidence evolution
        ax3 = axes[1, 0]
        for i, (community_id, data) in enumerate(community_data.items()):
            ax3.plot(iterations, data["confidences"], '^-',
                    label=community_id.replace('community_', '').replace('_', ' ').title(),
                    color=colors[i % len(colors)], linewidth=2)
        ax3.set_xlabel('Iteration')
        ax3.set_ylabel('Community Confidence')
        ax3.set_title('Community Confidence Evolution', fontweight='bold')
        ax3.legend()
        ax3.grid(True, alpha=0.3)

        # Plot 4: Cumulative community contributions
        ax4 = axes[1, 1]
        cumulative_contributions = {}
        for community_id, data in community_data.items():
            cumulative = np.cumsum(data["contributions"])
            cumulative_contributions[community_id] = cumulative

        for i, (community_id, cumulative) in enumerate(cumulative_contributions.items()):
            ax4.plot(iterations, cumulative, 'd-',
                    label=community_id.replace('community_', '').replace('_', ' ').title(),
                    color=colors[i % len(colors)], linewidth=2)
        ax4.set_xlabel('Iteration')
        ax4.set_ylabel('Cumulative Contribution (kcal/mol)')
        ax4.set_title('Cumulative Community Contributions', fontweight='bold')
        ax4.legend()
        ax4.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(output_path / 'community_contributions.png', dpi=300, bbox_inches='tight')
        plt.close()

    def _plot_supervisor_optimization(self, output_path: Path):
        """Plot supervisor optimization analysis."""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))

        iterations = [r["iteration"] for r in self.simulation_results]

        # Plot 1: Combination scores over time
        ax1 = axes[0, 0]
        combination_scores = [r["supervisor_decision"].combination_score for r in self.simulation_results]
        ax1.plot(iterations, combination_scores, 'o-', linewidth=3, markersize=8, color='#2E86AB')
        ax1.set_xlabel('Iteration')
        ax1.set_ylabel('Combination Score')
        ax1.set_title('Supervisor Combination Scores', fontweight='bold')
        ax1.grid(True, alpha=0.3)

        # Plot 2: Community weights evolution
        ax2 = axes[0, 1]
        community_weights_history = []
        for result in self.simulation_results:
            community_weights_history.append(result["supervisor_decision"].community_weights)

        colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D']
        for i, community_id in enumerate(self.communities[0].community_id for community in self.communities):
            weights = [weights_dict.get(community_id, 1.0) for weights_dict in community_weights_history]
            ax2.plot(iterations, weights, 'o-',
                    label=community_id.replace('community_', '').replace('_', ' ').title(),
                    color=colors[i % len(colors)], linewidth=2)
        ax2.set_xlabel('Iteration')
        ax2.set_ylabel('Community Weight')
        ax2.set_title('Community Weight Evolution', fontweight='bold')
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        # Plot 3: Synergy scores
        ax3 = axes[1, 0]
        synergy_scores = []
        for result in self.simulation_results:
            synergy_analysis = result["supervisor_decision"].synergy_analysis
            synergy_scores.append(synergy_analysis.get("synergy_score", 0.0))

        ax3.bar(iterations, synergy_scores, color='#F18F01', alpha=0.7)
        ax3.set_xlabel('Iteration')
        ax3.set_ylabel('Synergy Score')
        ax3.set_title('Mutation Synergy Analysis', fontweight='bold')
        ax3.grid(True, alpha=0.3, axis='y')

        # Plot 4: Diversity metrics
        ax4 = axes[1, 1]
        community_diversity = []
        expert_diversity = []

        for result in self.simulation_results:
            synergy_analysis = result["supervisor_decision"].synergy_analysis
            community_diversity.append(synergy_analysis.get("community_diversity", 0.0))
            expert_diversity.append(synergy_analysis.get("expert_diversity", 0.0))

        x = np.arange(len(iterations))
        width = 0.35

        ax4.bar(x - width/2, community_diversity, width, label='Community Diversity', color='#A23B72', alpha=0.7)
        ax4.bar(x + width/2, expert_diversity, width, label='Expert Diversity', color='#C73E1D', alpha=0.7)
        ax4.set_xlabel('Iteration')
        ax4.set_ylabel('Diversity Score')
        ax4.set_title('Selection Diversity Metrics', fontweight='bold')
        ax4.set_xticks(x)
        ax4.set_xticklabels(iterations)
        ax4.legend()
        ax4.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(output_path / 'supervisor_optimization.png', dpi=300, bbox_inches='tight')
        plt.close()

    def _plot_synergy_analysis(self, output_path: Path):
        """Plot detailed synergy analysis."""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))

        # Collect all synergy pairs across iterations
        all_synergy_pairs = []
        synergy_by_iteration = []

        for result in self.simulation_results:
            synergy_analysis = result["supervisor_decision"].synergy_analysis
            synergy_pairs = synergy_analysis.get("synergy_pairs", [])
            all_synergy_pairs.extend(synergy_pairs)
            synergy_by_iteration.append(len(synergy_pairs))

        # Plot 1: Number of synergistic pairs per iteration
        ax1 = axes[0, 0]
        iterations = [r["iteration"] for r in self.simulation_results]
        ax1.bar(iterations, synergy_by_iteration, color='#2E86AB', alpha=0.7)
        ax1.set_xlabel('Iteration')
        ax1.set_ylabel('Number of Synergistic Pairs')
        ax1.set_title('Synergistic Mutation Pairs', fontweight='bold')
        ax1.grid(True, alpha=0.3, axis='y')

        # Plot 2: Synergy strength distribution
        ax2 = axes[0, 1]
        if all_synergy_pairs:
            synergy_strengths = [pair[2] for pair in all_synergy_pairs]
            ax2.hist(synergy_strengths, bins=15, color='#A23B72', alpha=0.7, edgecolor='black')
            ax2.set_xlabel('Synergy Strength')
            ax2.set_ylabel('Frequency')
            ax2.set_title('Synergy Strength Distribution', fontweight='bold')
            ax2.grid(True, alpha=0.3, axis='y')

        # Plot 3: Position-based synergy network (simplified)
        ax3 = axes[1, 0]
        if all_synergy_pairs:
            # Create position interaction matrix
            positions = set()
            for pair in all_synergy_pairs:
                # Extract positions from mutation names (e.g., "I44V" -> 44)
                try:
                    pos1 = int(''.join(filter(str.isdigit, pair[0])))
                    pos2 = int(''.join(filter(str.isdigit, pair[1])))
                    positions.update([pos1, pos2])
                except:
                    continue

            positions = sorted(list(positions))
            if len(positions) > 1:
                # Create interaction heatmap
                interaction_matrix = np.zeros((len(positions), len(positions)))

                for pair in all_synergy_pairs:
                    try:
                        pos1 = int(''.join(filter(str.isdigit, pair[0])))
                        pos2 = int(''.join(filter(str.isdigit, pair[1])))
                        idx1 = positions.index(pos1)
                        idx2 = positions.index(pos2)
                        interaction_matrix[idx1, idx2] = pair[2]
                        interaction_matrix[idx2, idx1] = pair[2]
                    except:
                        continue

                im = ax3.imshow(interaction_matrix, cmap='YlOrRd', aspect='auto')
                ax3.set_xticks(range(len(positions)))
                ax3.set_yticks(range(len(positions)))
                ax3.set_xticklabels(positions)
                ax3.set_yticklabels(positions)
                ax3.set_xlabel('Position')
                ax3.set_ylabel('Position')
                ax3.set_title('Position Interaction Heatmap', fontweight='bold')
                plt.colorbar(im, ax=ax3, label='Synergy Strength')

        # Plot 4: Community synergy contributions
        ax4 = axes[1, 1]
        community_synergy = {}

        for result in self.simulation_results:
            selected_mutations = result["supervisor_decision"].selected_combination
            community_counts = {}
            for mutation in selected_mutations:
                community_counts[mutation.community_id] = community_counts.get(mutation.community_id, 0) + 1

            for community_id, count in community_counts.items():
                if community_id not in community_synergy:
                    community_synergy[community_id] = []
                community_synergy[community_id].append(count)

        if community_synergy:
            community_names = [name.replace('community_', '').replace('_', ' ').title()
                             for name in community_synergy.keys()]
            avg_contributions = [np.mean(counts) for counts in community_synergy.values()]

            ax4.bar(community_names, avg_contributions, color=['#2E86AB', '#A23B72', '#F18F01', '#C73E1D'])
            ax4.set_xlabel('Community')
            ax4.set_ylabel('Average Mutations per Iteration')
            ax4.set_title('Average Community Contributions', fontweight='bold')
            ax4.tick_params(axis='x', rotation=45)
            ax4.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(output_path / 'synergy_analysis.png', dpi=300, bbox_inches='tight')
        plt.close()

    def _plot_community_evolution(self, output_path: Path):
        """Plot community evolution and learning over time."""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))

        iterations = [r["iteration"] for r in self.simulation_results]

        # Plot 1: Expert performance within communities
        ax1 = axes[0, 0]
        expert_performance_data = {"MD Expert": [], "Structure Expert": [], "Bioinformatics Expert": []}

        for result in self.simulation_results:
            iteration_expert_performance = {"MD Expert": [], "Structure Expert": [], "Bioinformatics Expert": []}

            for community_result in result["community_results"]:
                for expert, performance in community_result.expert_performances.items():
                    iteration_expert_performance[expert].append(performance)

            for expert in expert_performance_data:
                avg_performance = np.mean(iteration_expert_performance[expert]) if iteration_expert_performance[expert] else 0
                expert_performance_data[expert].append(avg_performance)

        colors = ['#2E86AB', '#A23B72', '#F18F01']
        for i, (expert, performances) in enumerate(expert_performance_data.items()):
            ax1.plot(iterations, performances, 'o-', label=expert, color=colors[i], linewidth=2)

        ax1.set_xlabel('Iteration')
        ax1.set_ylabel('Average Performance Score')
        ax1.set_title('Expert Performance Evolution', fontweight='bold')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Plot 2: Community specialization effectiveness
        ax2 = axes[0, 1]
        specialization_effectiveness = {}

        for community in self.communities:
            specialization_effectiveness[community.specialization] = []

        for result in self.simulation_results:
            spec_performance = {spec: [] for spec in specialization_effectiveness.keys()}

            for community_result in result["community_results"]:
                community = next(c for c in self.communities if c.community_id == community_result.community_id)
                spec_performance[community.specialization].append(community_result.community_confidence)

            for spec in specialization_effectiveness:
                avg_perf = np.mean(spec_performance[spec]) if spec_performance[spec] else 0
                specialization_effectiveness[spec].append(avg_perf)

        colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D']
        for i, (spec, performances) in enumerate(specialization_effectiveness.items()):
            ax2.plot(iterations, performances, 's-', label=spec.title(), color=colors[i], linewidth=2)

        ax2.set_xlabel('Iteration')
        ax2.set_ylabel('Specialization Effectiveness')
        ax2.set_title('Community Specialization Performance', fontweight='bold')
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        # Plot 3: Learning curves (improvement rate over time)
        ax3 = axes[1, 0]
        learning_rates = []

        for i in range(1, len(self.simulation_results)):
            current_improvement = self.simulation_results[i]["actual_improvement"]
            previous_improvement = self.simulation_results[i-1]["actual_improvement"]
            learning_rate = (current_improvement - previous_improvement) / previous_improvement if previous_improvement != 0 else 0
            learning_rates.append(learning_rate)

        if learning_rates:
            ax3.plot(iterations[1:], learning_rates, 'o-', linewidth=2, markersize=6, color='#C73E1D')
            ax3.axhline(y=0, color='black', linestyle='--', alpha=0.5)
            ax3.set_xlabel('Iteration')
            ax3.set_ylabel('Learning Rate (Improvement Change)')
            ax3.set_title('Multi-Community Learning Curve', fontweight='bold')
            ax3.grid(True, alpha=0.3)

        # Plot 4: Consensus building over time
        ax4 = axes[1, 1]
        consensus_metrics = []

        for result in self.simulation_results:
            # Calculate consensus as agreement between communities
            selected_positions = set(m.position for m in result["supervisor_decision"].selected_combination)

            community_agreements = 0
            total_comparisons = 0

            for i, community_result_i in enumerate(result["community_results"]):
                for j, community_result_j in enumerate(result["community_results"][i+1:], i+1):
                    positions_i = set(m.position for m in community_result_i.selected_mutations)
                    positions_j = set(m.position for m in community_result_j.selected_mutations)

                    if positions_i or positions_j:
                        agreement = len(positions_i.intersection(positions_j)) / len(positions_i.union(positions_j))
                        community_agreements += agreement
                        total_comparisons += 1

            consensus_score = community_agreements / total_comparisons if total_comparisons > 0 else 0
            consensus_metrics.append(consensus_score)

        ax4.plot(iterations, consensus_metrics, '^-', linewidth=2, markersize=6, color='#F18F01')
        ax4.set_xlabel('Iteration')
        ax4.set_ylabel('Inter-Community Consensus')
        ax4.set_title('Consensus Building Over Time', fontweight='bold')
        ax4.grid(True, alpha=0.3)
        ax4.set_ylim(0, 1)

        plt.tight_layout()
        plt.savefig(output_path / 'community_evolution.png', dpi=300, bbox_inches='tight')
        plt.close()

    def generate_comprehensive_report(self, output_dir: str = "multi_community_results"):
        """Generate comprehensive analysis report."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        report_path = output_path / "multi_community_simulation_report.md"

        with open(report_path, 'w') as f:
            f.write("# Multi-Community Agentic Thermostability Optimization Report\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # Executive Summary
            f.write("## Executive Summary\n\n")
            final_stability = self.simulation_results[-1]["new_stability"]
            total_improvement = final_stability - self.baseline_stability
            f.write(f"- **Baseline Stability:** {self.baseline_stability:.2f} kcal/mol\n")
            f.write(f"- **Final Stability:** {final_stability:.2f} kcal/mol\n")
            f.write(f"- **Total Improvement:** +{total_improvement:.2f} kcal/mol ({total_improvement/self.baseline_stability*100:.1f}%)\n")
            f.write(f"- **Number of Communities:** {len(self.communities)}\n")
            f.write(f"- **Iterations Completed:** {len(self.simulation_results)}\n\n")

            # Community Overview
            f.write("## Community Overview\n\n")
            for community in self.communities:
                f.write(f"### {community.community_id.replace('_', ' ').title()}\n")
                f.write(f"- **Specialization:** {community.specialization}\n")
                f.write(f"- **Expertise Weights:** {community.expertise_weights}\n")
                f.write(f"- **Base Confidence:** {community.confidence_base:.3f}\n\n")

            # Iteration Details
            f.write("## Iteration Analysis\n\n")
            for result in self.simulation_results:
                f.write(f"### Iteration {result['iteration']}\n\n")
                f.write(f"- **Stability Change:** {result['baseline_stability']:.2f} → {result['new_stability']:.2f} kcal/mol\n")
                f.write(f"- **Improvement:** +{result['actual_improvement']:.3f} kcal/mol\n")
                f.write(f"- **Total Proposals:** {result['total_proposals']}\n")
                f.write(f"- **Selected Mutations:** {result['selected_mutations']}\n")
                f.write(f"- **Supervisor Confidence:** {result['supervisor_confidence']:.3f}\n\n")

                f.write("**Selected Mutations:**\n")
                for mutation in result["supervisor_decision"].selected_combination:
                    f.write(f"- {mutation.mutation} ({mutation.community_id}, {mutation.expert_source}): "
                           f"+{mutation.predicted_stability_change:.3f} kcal/mol (confidence: {mutation.confidence:.3f})\n")
                f.write("\n")

            # Final Recommendations
            f.write("## Experimental Validation Recommendations\n\n")
            all_selected_mutations = []
            for result in self.simulation_results:
                all_selected_mutations.extend(result["supervisor_decision"].selected_combination)

            # Get unique mutations sorted by total predicted effect
            unique_mutations = {}
            for mutation in all_selected_mutations:
                key = mutation.mutation
                if key not in unique_mutations:
                    unique_mutations[key] = mutation
                else:
                    # Keep the one with higher confidence
                    if mutation.confidence > unique_mutations[key].confidence:
                        unique_mutations[key] = mutation

            sorted_mutations = sorted(unique_mutations.values(),
                                    key=lambda x: abs(x.predicted_stability_change), reverse=True)

            f.write("### Top 10 Mutations for Experimental Testing\n\n")
            for i, mutation in enumerate(sorted_mutations[:10], 1):
                f.write(f"{i}. **{mutation.mutation}** (Position {mutation.position})\n")
                f.write(f"   - Predicted Effect: +{mutation.predicted_stability_change:.3f} kcal/mol\n")
                f.write(f"   - Confidence: {mutation.confidence:.3f}\n")
                f.write(f"   - Source: {mutation.community_id}, {mutation.expert_source}\n")
                f.write(f"   - Rationale: {mutation.rationale}\n\n")

        logger.info(f"Comprehensive report saved to {report_path}")


async def main():
    """Main execution function."""
    logger.info("Starting Multi-Community Agentic Thermostability Optimization")

    # Initialize simulation with 4 communities
    simulation = MultiCommunityThermostabilitySimulation(num_communities=4)

    # Run 5-iteration simulation
    results = await simulation.run_simulation(num_iterations=5)

    # Generate visualizations
    simulation.generate_comprehensive_visualizations()

    # Generate comprehensive report
    simulation.generate_comprehensive_report()

    # Print final summary
    final_result = results[-1]
    total_improvement = final_result["new_stability"] - simulation.baseline_stability

    print("\n" + "="*80)
    print("MULTI-COMMUNITY SIMULATION COMPLETE!")
    print("="*80)
    print(f"🧬 Final Thermostability: {final_result['new_stability']:.2f} kcal/mol")
    print(f"📈 Total Improvement: +{total_improvement:.2f} kcal/mol ({total_improvement/simulation.baseline_stability*100:.1f}%)")
    print(f"🏆 Supervisor Confidence: {final_result['supervisor_confidence']:.1%}")
    print(f"🤝 Communities Involved: {len(simulation.communities)}")
    print(f"🔬 Total Mutations Selected: {sum(r['selected_mutations'] for r in results)}")
    print(f"📊 Visualizations: multi_community_results/")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
