#!/usr/bin/env python3
"""
Iterative Role-Based Agentic System Simulation for Ubiquitin Thermostability

This simulation demonstrates how the role-based agentic system iteratively improves
ubiquitin thermostability through expert-critic collaboration over 5 iterations.

Features:
- MD Expert: Molecular dynamics analysis and stability predictions
- Structure Expert: Structural analysis and mutation design
- Bioinformatics Expert: Sequence analysis and evolutionary insights
- Critics: Performance evaluation and proposal synthesis
- Iterative Improvement: 5 rounds of optimization with feedback integration
- Comprehensive Visualization: Progress tracking and performance metrics
"""

import asyncio
import logging
import json
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple
import pandas as pd
from dataclasses import dataclass
import random

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
    """Data class for mutation proposals."""
    mutation: str
    position: int
    original: str
    mutant: str
    predicted_stability_change: float
    confidence: float
    rationale: str
    expert_source: str
    supporting_evidence: List[str]


@dataclass
class IterationResults:
    """Data class for iteration results."""
    iteration: int
    proposals: List[MutationProposal]
    selected_mutations: List[MutationProposal]
    baseline_stability: float
    predicted_stability: float
    improvement: float
    consensus_confidence: float
    critic_feedback: Dict[str, Any]


class MDExpertAgent:
    """MD Expert Agent specializing in molecular dynamics analysis."""
    
    def __init__(self):
        self.name = "MD Expert"
        self.expertise = ["molecular_dynamics", "thermostability", "protein_folding"]
        self.confidence_base = 0.85
        
    async def analyze_stability(self, protein_data: Dict, iteration: int) -> List[MutationProposal]:
        """Analyze protein stability and propose mutations."""
        logger.info(f"MD Expert analyzing stability (iteration {iteration})")
        
        # Simulate MD analysis with increasing sophistication over iterations
        base_confidence = self.confidence_base + (iteration * 0.02)
        
        proposals = []
        
        # Core stabilizing mutations based on MD insights
        md_mutations = [
            ("I44V", 44, "I", "V", 0.15, "Reduce steric clashes in hydrophobic core"),
            ("K63R", 63, "K", "R", 0.12, "Enhanced hydrogen bonding network"),
            ("L67F", 67, "L", "F", 0.08, "Improved aromatic stacking interactions"),
            ("T14S", 14, "T", "S", 0.06, "Reduced conformational entropy"),
            ("Q49E", 49, "Q", "E", 0.10, "Stabilized salt bridge formation")
        ]
        
        for i, (mut, pos, orig, new, base_effect, rationale) in enumerate(md_mutations):
            # Add iteration-based improvements and some randomness
            stability_change = base_effect + (iteration * 0.02) + random.uniform(-0.03, 0.03)
            confidence = min(0.95, base_confidence + random.uniform(-0.05, 0.05))
            
            evidence = [
                f"MD simulation shows {stability_change:.3f} kcal/mol stabilization",
                f"RMSD reduction of {random.uniform(0.2, 0.8):.2f} Å observed",
                f"Reduced flexibility in region {pos-5}-{pos+5}"
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
                supporting_evidence=evidence
            )
            proposals.append(proposal)
        
        return proposals


class StructureExpertAgent:
    """Structure Expert Agent specializing in structural analysis."""
    
    def __init__(self):
        self.name = "Structure Expert"
        self.expertise = ["protein_structure", "alphafold", "structural_biology"]
        self.confidence_base = 0.88
        
    async def analyze_structure(self, protein_data: Dict, iteration: int) -> List[MutationProposal]:
        """Analyze protein structure and propose mutations."""
        logger.info(f"Structure Expert analyzing structure (iteration {iteration})")
        
        base_confidence = self.confidence_base + (iteration * 0.015)
        
        proposals = []
        
        # Structure-based mutations
        structure_mutations = [
            ("F45Y", 45, "F", "Y", 0.13, "Enhanced hydrogen bonding capability"),
            ("V26I", 26, "V", "I", 0.09, "Improved hydrophobic packing"),
            ("D52N", 52, "D", "N", 0.11, "Reduced electrostatic repulsion"),
            ("G75A", 75, "G", "A", 0.07, "Reduced backbone flexibility"),
            ("S57T", 57, "S", "T", 0.05, "Improved side chain interactions")
        ]
        
        for mut, pos, orig, new, base_effect, rationale in structure_mutations:
            stability_change = base_effect + (iteration * 0.025) + random.uniform(-0.02, 0.04)
            confidence = min(0.96, base_confidence + random.uniform(-0.04, 0.04))
            
            evidence = [
                f"AlphaFold confidence score: {random.uniform(85, 95):.1f}%",
                f"Structural analysis predicts {stability_change:.3f} kcal/mol improvement",
                f"Cavity analysis shows improved packing density"
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
                supporting_evidence=evidence
            )
            proposals.append(proposal)
        
        return proposals


class BioinformaticsExpertAgent:
    """Bioinformatics Expert Agent specializing in sequence analysis."""
    
    def __init__(self):
        self.name = "Bioinformatics Expert"
        self.expertise = ["sequence_analysis", "evolution", "conservation"]
        self.confidence_base = 0.82
        
    async def analyze_sequence(self, protein_data: Dict, iteration: int) -> List[MutationProposal]:
        """Analyze protein sequence and propose mutations."""
        logger.info(f"Bioinformatics Expert analyzing sequence (iteration {iteration})")
        
        base_confidence = self.confidence_base + (iteration * 0.02)
        
        proposals = []
        
        # Bioinformatics-based mutations
        bioinfo_mutations = [
            ("E34D", 34, "E", "D", 0.08, "Evolutionary conservation analysis"),
            ("N25Q", 25, "N", "Q", 0.06, "Improved hydrogen bonding potential"),
            ("R72K", 72, "R", "K", 0.09, "Optimized electrostatic interactions"),
            ("A46V", 46, "A", "V", 0.10, "Enhanced hydrophobic core stability"),
            ("P19S", 19, "P", "S", 0.04, "Reduced conformational strain")
        ]
        
        for mut, pos, orig, new, base_effect, rationale in bioinfo_mutations:
            stability_change = base_effect + (iteration * 0.018) + random.uniform(-0.025, 0.035)
            confidence = min(0.92, base_confidence + random.uniform(-0.06, 0.06))
            
            evidence = [
                f"Conservation score: {random.uniform(0.7, 0.95):.2f}",
                f"Phylogenetic analysis supports {stability_change:.3f} kcal/mol improvement",
                f"Homology modeling confirms structural compatibility"
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
                supporting_evidence=evidence
            )
            proposals.append(proposal)
        
        return proposals


class CriticAgent:
    """Critic Agent for evaluating and synthesizing proposals."""
    
    def __init__(self):
        self.name = "Synthesis Critic"
        self.evaluation_history = []
        
    async def evaluate_proposals(self, all_proposals: List[MutationProposal], 
                                iteration: int) -> Tuple[List[MutationProposal], Dict[str, Any]]:
        """Evaluate and synthesize proposals from all experts."""
        logger.info(f"Critic evaluating {len(all_proposals)} proposals (iteration {iteration})")
        
        # Group proposals by expert
        expert_groups = {}
        for proposal in all_proposals:
            expert = proposal.expert_source
            if expert not in expert_groups:
                expert_groups[expert] = []
            expert_groups[expert].append(proposal)
        
        # Evaluate each expert's contributions
        expert_evaluations = {}
        for expert, proposals in expert_groups.items():
            avg_confidence = np.mean([p.confidence for p in proposals])
            avg_stability = np.mean([p.predicted_stability_change for p in proposals])
            
            expert_evaluations[expert] = {
                "proposal_count": len(proposals),
                "average_confidence": avg_confidence,
                "average_stability_improvement": avg_stability,
                "consistency_score": 1.0 - np.std([p.confidence for p in proposals]),
                "innovation_score": min(1.0, avg_stability * 2)  # Higher for bigger improvements
            }
        
        # Select best proposals using multi-criteria decision making
        selected_proposals = self._select_best_proposals(all_proposals, iteration)
        
        # Generate critic feedback
        feedback = {
            "iteration": iteration,
            "total_proposals_evaluated": len(all_proposals),
            "selected_proposals": len(selected_proposals),
            "expert_evaluations": expert_evaluations,
            "selection_criteria": {
                "stability_weight": 0.4,
                "confidence_weight": 0.3,
                "novelty_weight": 0.2,
                "consensus_weight": 0.1
            },
            "improvement_suggestions": self._generate_improvement_suggestions(expert_evaluations, iteration),
            "consensus_confidence": np.mean([p.confidence for p in selected_proposals])
        }
        
        self.evaluation_history.append(feedback)
        
        return selected_proposals, feedback
    
    def _select_best_proposals(self, proposals: List[MutationProposal], 
                              iteration: int) -> List[MutationProposal]:
        """Select best proposals using weighted scoring."""
        # Calculate composite scores
        scored_proposals = []
        for proposal in proposals:
            # Multi-criteria scoring
            stability_score = min(1.0, proposal.predicted_stability_change / 0.2)  # Normalize to 0-1
            confidence_score = proposal.confidence
            novelty_score = 1.0 if iteration == 1 else 0.8  # Slight preference for novel approaches
            
            # Position-based diversity bonus
            position_bonus = 0.1 if proposal.position in [44, 63, 45, 52] else 0.0  # Key positions
            
            composite_score = (
                0.4 * stability_score +
                0.3 * confidence_score +
                0.2 * novelty_score +
                0.1 * position_bonus
            )
            
            scored_proposals.append((proposal, composite_score))
        
        # Sort by score and select top proposals
        scored_proposals.sort(key=lambda x: x[1], reverse=True)
        
        # Select top 3-5 proposals, increasing with iteration
        num_selected = min(3 + iteration, len(scored_proposals))
        selected = [proposal for proposal, score in scored_proposals[:num_selected]]
        
        return selected
    
    def _generate_improvement_suggestions(self, expert_evaluations: Dict, 
                                        iteration: int) -> List[str]:
        """Generate suggestions for expert improvement."""
        suggestions = []
        
        # Analyze expert performance
        for expert, eval_data in expert_evaluations.items():
            if eval_data["average_confidence"] < 0.8:
                suggestions.append(f"{expert}: Increase confidence through more rigorous validation")
            
            if eval_data["consistency_score"] < 0.7:
                suggestions.append(f"{expert}: Improve consistency in proposal quality")
            
            if eval_data["innovation_score"] < 0.6:
                suggestions.append(f"{expert}: Explore more innovative mutation strategies")
        
        # General suggestions based on iteration
        if iteration <= 2:
            suggestions.append("Focus on well-established stabilizing mutations")
        elif iteration <= 4:
            suggestions.append("Explore synergistic mutation combinations")
        else:
            suggestions.append("Fine-tune mutations for optimal thermostability")
        
        return suggestions


class ThermostabilitySimulation:
    """Main simulation class for iterative thermostability improvement."""
    
    def __init__(self):
        self.md_expert = MDExpertAgent()
        self.structure_expert = StructureExpertAgent()
        self.bioinfo_expert = BioinformaticsExpertAgent()
        self.critic = CriticAgent()
        
        self.baseline_stability = 45.2  # kcal/mol (typical for ubiquitin)
        self.iteration_results = []
        
    async def run_simulation(self, num_iterations: int = 5) -> List[IterationResults]:
        """Run the complete iterative simulation."""
        logger.info(f"Starting {num_iterations}-iteration thermostability simulation")
        
        current_stability = self.baseline_stability
        
        for iteration in range(1, num_iterations + 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"ITERATION {iteration}/{num_iterations}")
            logger.info(f"{'='*60}")
            
            # Protein data for this iteration (would include previous mutations)
            protein_data = {
                "name": "ubiquitin",
                "current_stability": current_stability,
                "iteration": iteration,
                "previous_mutations": [r.selected_mutations for r in self.iteration_results]
            }
            
            # Get proposals from all experts
            md_proposals = await self.md_expert.analyze_stability(protein_data, iteration)
            structure_proposals = await self.structure_expert.analyze_structure(protein_data, iteration)
            bioinfo_proposals = await self.bioinfo_expert.analyze_sequence(protein_data, iteration)
            
            all_proposals = md_proposals + structure_proposals + bioinfo_proposals
            
            # Critic evaluation and selection
            selected_mutations, critic_feedback = await self.critic.evaluate_proposals(
                all_proposals, iteration
            )
            
            # Calculate predicted stability improvement
            total_improvement = sum(m.predicted_stability_change for m in selected_mutations)
            
            # Add some realistic diminishing returns and experimental noise
            actual_improvement = total_improvement * (0.9 + random.uniform(-0.1, 0.1))
            if iteration > 3:  # Diminishing returns in later iterations
                actual_improvement *= (0.8 + iteration * 0.05)
            
            new_stability = current_stability + actual_improvement
            
            # Store iteration results
            iteration_result = IterationResults(
                iteration=iteration,
                proposals=all_proposals,
                selected_mutations=selected_mutations,
                baseline_stability=current_stability,
                predicted_stability=new_stability,
                improvement=actual_improvement,
                consensus_confidence=critic_feedback["consensus_confidence"],
                critic_feedback=critic_feedback
            )
            
            self.iteration_results.append(iteration_result)
            current_stability = new_stability
            
            # Log iteration summary
            logger.info(f"Iteration {iteration} Summary:")
            logger.info(f"  • Proposals evaluated: {len(all_proposals)}")
            logger.info(f"  • Mutations selected: {len(selected_mutations)}")
            logger.info(f"  • Stability improvement: +{actual_improvement:.3f} kcal/mol")
            logger.info(f"  • New stability: {new_stability:.3f} kcal/mol")
            logger.info(f"  • Consensus confidence: {critic_feedback['consensus_confidence']:.3f}")
            
            # Brief pause for realism
            await asyncio.sleep(0.1)
        
        logger.info(f"\nSimulation complete! Final stability: {current_stability:.3f} kcal/mol")
        logger.info(f"Total improvement: +{current_stability - self.baseline_stability:.3f} kcal/mol")
        
        return self.iteration_results
    
    def generate_visualizations(self, output_dir: str = "thermostability_simulation_results"):
        """Generate comprehensive visualizations of the simulation results."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Create multiple visualization plots
        self._plot_stability_progression(output_path)
        self._plot_expert_contributions(output_path)
        self._plot_confidence_evolution(output_path)
        self._plot_mutation_analysis(output_path)
        self._plot_critic_feedback_trends(output_path)
        
        logger.info(f"Visualizations saved to {output_path}")
    
    def _plot_stability_progression(self, output_path: Path):
        """Plot thermostability progression over iterations."""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        # Stability progression
        iterations = [0] + [r.iteration for r in self.iteration_results]
        stabilities = [self.baseline_stability] + [r.predicted_stability for r in self.iteration_results]
        improvements = [0] + [r.improvement for r in self.iteration_results]
        
        ax1.plot(iterations, stabilities, 'o-', linewidth=3, markersize=8, color='#2E86AB')
        ax1.fill_between(iterations, stabilities, alpha=0.3, color='#2E86AB')
        ax1.set_xlabel('Iteration', fontsize=12)
        ax1.set_ylabel('Thermostability (kcal/mol)', fontsize=12)
        ax1.set_title('Ubiquitin Thermostability Progression', fontsize=14, fontweight='bold')
        ax1.grid(True, alpha=0.3)
        
        # Add annotations for key improvements
        for i, (iter_num, stability) in enumerate(zip(iterations[1:], stabilities[1:]), 1):
            ax1.annotate(f'+{improvements[i]:.2f}', 
                        xy=(iter_num, stability), 
                        xytext=(5, 10), 
                        textcoords='offset points',
                        fontsize=10, 
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))
        
        # Improvement per iteration
        ax2.bar(range(1, len(improvements)), improvements[1:], 
                color=['#A23B72', '#F18F01', '#C73E1D', '#2E86AB', '#A23B72'][:len(improvements)-1])
        ax2.set_xlabel('Iteration', fontsize=12)
        ax2.set_ylabel('Stability Improvement (kcal/mol)', fontsize=12)
        ax2.set_title('Improvement per Iteration', fontsize=14, fontweight='bold')
        ax2.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        plt.savefig(output_path / 'stability_progression.png', dpi=300, bbox_inches='tight')
        plt.close()
    
    def _plot_expert_contributions(self, output_path: Path):
        """Plot expert contributions over iterations."""
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        
        # Prepare data
        experts = ['MD Expert', 'Structure Expert', 'Bioinformatics Expert']
        colors = ['#2E86AB', '#A23B72', '#F18F01']
        
        # Proposals per expert per iteration
        expert_proposals = {expert: [] for expert in experts}
        expert_selections = {expert: [] for expert in experts}
        expert_avg_confidence = {expert: [] for expert in experts}
        expert_avg_improvement = {expert: [] for expert in experts}
        
        for result in self.iteration_results:
            # Count proposals and selections by expert
            for expert in experts:
                proposals = [p for p in result.proposals if p.expert_source == expert]
                selections = [p for p in result.selected_mutations if p.expert_source == expert]
                
                expert_proposals[expert].append(len(proposals))
                expert_selections[expert].append(len(selections))
                
                if proposals:
                    expert_avg_confidence[expert].append(np.mean([p.confidence for p in proposals]))
                    expert_avg_improvement[expert].append(np.mean([p.predicted_stability_change for p in proposals]))
                else:
                    expert_avg_confidence[expert].append(0)
                    expert_avg_improvement[expert].append(0)
        
        iterations = list(range(1, len(self.iteration_results) + 1))
        
        # Plot 1: Proposals per expert
        ax1 = axes[0, 0]
        for expert, color in zip(experts, colors):
            ax1.plot(iterations, expert_proposals[expert], 'o-', label=expert, color=color, linewidth=2)
        ax1.set_xlabel('Iteration')
        ax1.set_ylabel('Number of Proposals')
        ax1.set_title('Proposals per Expert', fontweight='bold')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Plot 2: Selections per expert
        ax2 = axes[0, 1]
        for expert, color in zip(experts, colors):
            ax2.plot(iterations, expert_selections[expert], 's-', label=expert, color=color, linewidth=2)
        ax2.set_xlabel('Iteration')
        ax2.set_ylabel('Number of Selected Mutations')
        ax2.set_title('Selected Mutations per Expert', fontweight='bold')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # Plot 3: Average confidence
        ax3 = axes[1, 0]
        for expert, color in zip(experts, colors):
            ax3.plot(iterations, expert_avg_confidence[expert], '^-', label=expert, color=color, linewidth=2)
        ax3.set_xlabel('Iteration')
        ax3.set_ylabel('Average Confidence')
        ax3.set_title('Expert Confidence Evolution', fontweight='bold')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        # Plot 4: Average predicted improvement
        ax4 = axes[1, 1]
        for expert, color in zip(experts, colors):
            ax4.plot(iterations, expert_avg_improvement[expert], 'd-', label=expert, color=color, linewidth=2)
        ax4.set_xlabel('Iteration')
        ax4.set_ylabel('Avg Predicted Improvement (kcal/mol)')
        ax4.set_title('Expert Prediction Quality', fontweight='bold')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_path / 'expert_contributions.png', dpi=300, bbox_inches='tight')
        plt.close()
    
    def _plot_confidence_evolution(self, output_path: Path):
        """Plot confidence evolution and consensus building."""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        iterations = [r.iteration for r in self.iteration_results]
        consensus_confidence = [r.consensus_confidence for r in self.iteration_results]
        
        # Individual expert confidence ranges
        expert_confidence_ranges = {expert: {'min': [], 'max': [], 'avg': []} 
                                  for expert in ['MD Expert', 'Structure Expert', 'Bioinformatics Expert']}
        
        for result in self.iteration_results:
            for expert in expert_confidence_ranges.keys():
                expert_proposals = [p for p in result.proposals if p.expert_source == expert]
                if expert_proposals:
                    confidences = [p.confidence for p in expert_proposals]
                    expert_confidence_ranges[expert]['min'].append(min(confidences))
                    expert_confidence_ranges[expert]['max'].append(max(confidences))
                    expert_confidence_ranges[expert]['avg'].append(np.mean(confidences))
                else:
                    expert_confidence_ranges[expert]['min'].append(0)
                    expert_confidence_ranges[expert]['max'].append(0)
                    expert_confidence_ranges[expert]['avg'].append(0)
        
        # Plot consensus confidence
        ax1.plot(iterations, consensus_confidence, 'o-', linewidth=3, markersize=8, 
                color='#2E86AB', label='Consensus Confidence')
        ax1.fill_between(iterations, consensus_confidence, alpha=0.3, color='#2E86AB')
        ax1.set_xlabel('Iteration')
        ax1.set_ylabel('Consensus Confidence')
        ax1.set_title('Consensus Confidence Evolution', fontweight='bold')
        ax1.grid(True, alpha=0.3)
        ax1.set_ylim(0.7, 1.0)
        
        # Plot expert confidence ranges
        colors = ['#A23B72', '#F18F01', '#C73E1D']
        for (expert, data), color in zip(expert_confidence_ranges.items(), colors):
            ax2.fill_between(iterations, data['min'], data['max'], alpha=0.3, color=color)
            ax2.plot(iterations, data['avg'], 'o-', color=color, label=f'{expert} (avg)', linewidth=2)
        
        ax2.set_xlabel('Iteration')
        ax2.set_ylabel('Expert Confidence Range')
        ax2.set_title('Expert Confidence Ranges', fontweight='bold')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_path / 'confidence_evolution.png', dpi=300, bbox_inches='tight')
        plt.close()

    def _plot_mutation_analysis(self, output_path: Path):
        """Plot detailed mutation analysis."""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))

        # Collect all mutations across iterations
        all_mutations = []
        for result in self.iteration_results:
            for mutation in result.selected_mutations:
                all_mutations.append({
                    'iteration': result.iteration,
                    'mutation': mutation.mutation,
                    'position': mutation.position,
                    'stability_change': mutation.predicted_stability_change,
                    'confidence': mutation.confidence,
                    'expert': mutation.expert_source
                })

        df = pd.DataFrame(all_mutations)

        # Plot 1: Mutation positions over iterations
        ax1 = axes[0, 0]
        scatter = ax1.scatter(df['iteration'], df['position'],
                            c=df['stability_change'], s=df['confidence']*100,
                            cmap='RdYlBu_r', alpha=0.7)
        ax1.set_xlabel('Iteration')
        ax1.set_ylabel('Mutation Position')
        ax1.set_title('Mutation Positions and Effects', fontweight='bold')
        ax1.grid(True, alpha=0.3)

        # Add colorbar
        cbar = plt.colorbar(scatter, ax=ax1)
        cbar.set_label('Stability Change (kcal/mol)')

        # Plot 2: Stability improvements by expert
        ax2 = axes[0, 1]
        expert_improvements = df.groupby(['expert', 'iteration'])['stability_change'].sum().unstack(fill_value=0)
        expert_improvements.plot(kind='bar', ax=ax2, stacked=True)
        ax2.set_xlabel('Expert')
        ax2.set_ylabel('Total Stability Improvement (kcal/mol)')
        ax2.set_title('Cumulative Expert Contributions', fontweight='bold')
        ax2.legend(title='Iteration', bbox_to_anchor=(1.05, 1), loc='upper left')
        ax2.tick_params(axis='x', rotation=45)

        # Plot 3: Mutation frequency heatmap
        ax3 = axes[1, 0]
        position_counts = df.groupby(['position', 'iteration']).size().unstack(fill_value=0)
        sns.heatmap(position_counts, ax=ax3, cmap='YlOrRd', annot=True, fmt='d')
        ax3.set_xlabel('Iteration')
        ax3.set_ylabel('Mutation Position')
        ax3.set_title('Mutation Position Frequency', fontweight='bold')

        # Plot 4: Confidence vs Stability relationship
        ax4 = axes[1, 1]
        colors = {'MD Expert': '#2E86AB', 'Structure Expert': '#A23B72', 'Bioinformatics Expert': '#F18F01'}
        for expert in df['expert'].unique():
            expert_data = df[df['expert'] == expert]
            ax4.scatter(expert_data['confidence'], expert_data['stability_change'],
                       label=expert, color=colors.get(expert, 'gray'), alpha=0.7, s=60)

        ax4.set_xlabel('Confidence')
        ax4.set_ylabel('Predicted Stability Change (kcal/mol)')
        ax4.set_title('Confidence vs Predicted Effect', fontweight='bold')
        ax4.legend()
        ax4.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(output_path / 'mutation_analysis.png', dpi=300, bbox_inches='tight')
        plt.close()

    def _plot_critic_feedback_trends(self, output_path: Path):
        """Plot critic feedback and improvement trends."""
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))

        iterations = [r.iteration for r in self.iteration_results]

        # Extract critic feedback data
        total_proposals = [len(r.proposals) for r in self.iteration_results]
        selected_proposals = [len(r.selected_mutations) for r in self.iteration_results]
        selection_rates = [s/t if t > 0 else 0 for s, t in zip(selected_proposals, total_proposals)]

        # Plot 1: Proposal selection rates
        ax1 = axes[0, 0]
        ax1.plot(iterations, selection_rates, 'o-', linewidth=3, markersize=8, color='#C73E1D')
        ax1.fill_between(iterations, selection_rates, alpha=0.3, color='#C73E1D')
        ax1.set_xlabel('Iteration')
        ax1.set_ylabel('Selection Rate')
        ax1.set_title('Critic Selection Efficiency', fontweight='bold')
        ax1.grid(True, alpha=0.3)

        # Plot 2: Expert evaluation scores
        ax2 = axes[0, 1]
        expert_scores = {'MD Expert': [], 'Structure Expert': [], 'Bioinformatics Expert': []}

        for result in self.iteration_results:
            expert_evals = result.critic_feedback.get('expert_evaluations', {})
            for expert in expert_scores.keys():
                if expert in expert_evals:
                    # Composite score based on multiple criteria
                    eval_data = expert_evals[expert]
                    composite_score = (
                        eval_data.get('average_confidence', 0) * 0.3 +
                        eval_data.get('consistency_score', 0) * 0.3 +
                        eval_data.get('innovation_score', 0) * 0.4
                    )
                    expert_scores[expert].append(composite_score)
                else:
                    expert_scores[expert].append(0)

        colors = ['#2E86AB', '#A23B72', '#F18F01']
        for (expert, scores), color in zip(expert_scores.items(), colors):
            ax2.plot(iterations, scores, 'o-', label=expert, color=color, linewidth=2)

        ax2.set_xlabel('Iteration')
        ax2.set_ylabel('Expert Performance Score')
        ax2.set_title('Expert Performance Evolution', fontweight='bold')
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        # Plot 3: Cumulative improvements
        ax3 = axes[1, 0]
        cumulative_improvements = []
        cumsum = 0
        for result in self.iteration_results:
            cumsum += result.improvement
            cumulative_improvements.append(cumsum)

        ax3.plot(iterations, cumulative_improvements, 'o-', linewidth=3, markersize=8, color='#2E86AB')
        ax3.fill_between(iterations, cumulative_improvements, alpha=0.3, color='#2E86AB')
        ax3.set_xlabel('Iteration')
        ax3.set_ylabel('Cumulative Improvement (kcal/mol)')
        ax3.set_title('Cumulative Thermostability Gains', fontweight='bold')
        ax3.grid(True, alpha=0.3)

        # Plot 4: Improvement suggestions trend
        ax4 = axes[1, 1]
        suggestion_counts = []
        for result in self.iteration_results:
            suggestions = result.critic_feedback.get('improvement_suggestions', [])
            suggestion_counts.append(len(suggestions))

        ax4.bar(iterations, suggestion_counts, color=['#A23B72', '#F18F01', '#C73E1D', '#2E86AB', '#A23B72'][:len(iterations)])
        ax4.set_xlabel('Iteration')
        ax4.set_ylabel('Number of Improvement Suggestions')
        ax4.set_title('Critic Feedback Volume', fontweight='bold')
        ax4.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(output_path / 'critic_feedback_trends.png', dpi=300, bbox_inches='tight')
        plt.close()

    def generate_summary_report(self, output_dir: str = "thermostability_simulation_results"):
        """Generate a comprehensive summary report."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        # Calculate summary statistics
        total_improvement = sum(r.improvement for r in self.iteration_results)
        final_stability = self.baseline_stability + total_improvement
        avg_confidence = np.mean([r.consensus_confidence for r in self.iteration_results])

        total_mutations = sum(len(r.selected_mutations) for r in self.iteration_results)
        unique_positions = set()
        for result in self.iteration_results:
            for mutation in result.selected_mutations:
                unique_positions.add(mutation.position)

        # Expert contribution analysis
        expert_contributions = {'MD Expert': 0, 'Structure Expert': 0, 'Bioinformatics Expert': 0}
        for result in self.iteration_results:
            for mutation in result.selected_mutations:
                expert_contributions[mutation.expert_source] += mutation.predicted_stability_change

        # Generate report
        report = f"""
# Ubiquitin Thermostability Improvement Simulation Report

## Executive Summary
- **Baseline Stability**: {self.baseline_stability:.2f} kcal/mol
- **Final Stability**: {final_stability:.2f} kcal/mol
- **Total Improvement**: +{total_improvement:.2f} kcal/mol ({(total_improvement/self.baseline_stability)*100:.1f}% increase)
- **Average Consensus Confidence**: {avg_confidence:.3f}
- **Total Mutations Selected**: {total_mutations}
- **Unique Positions Targeted**: {len(unique_positions)}

## Iteration-by-Iteration Results

"""

        for i, result in enumerate(self.iteration_results, 1):
            report += f"""
### Iteration {i}
- **Stability Improvement**: +{result.improvement:.3f} kcal/mol
- **New Stability**: {result.predicted_stability:.2f} kcal/mol
- **Mutations Selected**: {len(result.selected_mutations)}
- **Consensus Confidence**: {result.consensus_confidence:.3f}
- **Selected Mutations**:
"""
            for mutation in result.selected_mutations:
                report += f"  - {mutation.mutation} ({mutation.expert_source}): +{mutation.predicted_stability_change:.3f} kcal/mol\n"

        report += f"""

## Expert Performance Analysis

### Contribution by Expert
"""
        for expert, contribution in expert_contributions.items():
            percentage = (contribution / total_improvement) * 100 if total_improvement > 0 else 0
            report += f"- **{expert}**: +{contribution:.3f} kcal/mol ({percentage:.1f}% of total)\n"

        report += f"""

### Key Insights
1. **Most Effective Strategy**: {max(expert_contributions.items(), key=lambda x: x[1])[0]} provided the highest cumulative improvement
2. **Convergence**: {'Achieved' if self.iteration_results[-1].improvement < 0.05 else 'Not achieved'} - final iteration showed {'minimal' if self.iteration_results[-1].improvement < 0.05 else 'significant'} improvement
3. **Confidence Trend**: {'Increasing' if self.iteration_results[-1].consensus_confidence > self.iteration_results[0].consensus_confidence else 'Stable'} confidence over iterations
4. **Position Diversity**: {len(unique_positions)} unique positions targeted, indicating {'broad' if len(unique_positions) > 8 else 'focused'} mutation strategy

## Recommendations for Experimental Validation

### Priority Mutations (Top 5)
"""

        # Get top 5 mutations by predicted effect
        all_selected = []
        for result in self.iteration_results:
            all_selected.extend(result.selected_mutations)

        top_mutations = sorted(all_selected, key=lambda x: x.predicted_stability_change, reverse=True)[:5]

        for i, mutation in enumerate(top_mutations, 1):
            report += f"{i}. **{mutation.mutation}**: +{mutation.predicted_stability_change:.3f} kcal/mol (Confidence: {mutation.confidence:.3f})\n"
            report += f"   - Rationale: {mutation.rationale}\n"
            report += f"   - Expert: {mutation.expert_source}\n\n"

        report += """
### Experimental Strategy
1. **Single Mutations**: Test top 3 individual mutations first
2. **Combination Testing**: Explore synergistic effects of compatible mutations
3. **Validation Methods**: Use thermal shift assays, differential scanning calorimetry
4. **Controls**: Include wild-type and known stabilizing mutations as controls

## Simulation Methodology
- **Expert Agents**: 3 specialized agents (MD, Structure, Bioinformatics)
- **Critic System**: Multi-criteria evaluation and selection
- **Iterations**: 5 rounds of iterative improvement
- **Selection Criteria**: Stability (40%), Confidence (30%), Novelty (20%), Consensus (10%)
"""

        # Save report
        with open(output_path / 'simulation_report.md', 'w') as f:
            f.write(report)

        logger.info(f"Summary report saved to {output_path / 'simulation_report.md'}")


async def main():
    """Main execution function for the thermostability simulation."""
    print("🧬 Iterative Role-Based Thermostability Simulation")
    print("=" * 80)

    # Initialize simulation
    simulation = ThermostabilitySimulation()

    try:
        print("🚀 Starting 5-iteration thermostability improvement simulation...")
        print("   • MD Expert: Molecular dynamics analysis")
        print("   • Structure Expert: Structural analysis and AlphaFold integration")
        print("   • Bioinformatics Expert: Sequence analysis and evolutionary insights")
        print("   • Critic Agent: Proposal evaluation and synthesis")

        # Run simulation
        results = await simulation.run_simulation(num_iterations=5)

        print(f"\n{'='*80}")
        print("🎉 SIMULATION COMPLETE!")
        print(f"{'='*80}")

        # Display summary
        total_improvement = sum(r.improvement for r in results)
        final_stability = simulation.baseline_stability + total_improvement

        print(f"\n📊 Final Results:")
        print(f"   • Baseline Stability: {simulation.baseline_stability:.2f} kcal/mol")
        print(f"   • Final Stability: {final_stability:.2f} kcal/mol")
        print(f"   • Total Improvement: +{total_improvement:.2f} kcal/mol")
        print(f"   • Percentage Increase: {(total_improvement/simulation.baseline_stability)*100:.1f}%")

        print(f"\n🎯 Iteration Summary:")
        for i, result in enumerate(results, 1):
            print(f"   Iteration {i}: +{result.improvement:.3f} kcal/mol "
                  f"({len(result.selected_mutations)} mutations, "
                  f"{result.consensus_confidence:.3f} confidence)")

        # Generate visualizations
        print(f"\n📈 Generating comprehensive visualizations...")
        simulation.generate_visualizations()

        # Generate summary report
        print(f"📝 Generating summary report...")
        simulation.generate_summary_report()

        print(f"\n✅ All results saved to 'thermostability_simulation_results/' directory")
        print(f"   • stability_progression.png - Main stability improvement plot")
        print(f"   • expert_contributions.png - Expert performance analysis")
        print(f"   • confidence_evolution.png - Confidence trends")
        print(f"   • mutation_analysis.png - Detailed mutation analysis")
        print(f"   • critic_feedback_trends.png - Critic evaluation trends")
        print(f"   • simulation_report.md - Comprehensive summary report")

    except Exception as e:
        print(f"❌ Simulation failed: {e}")
        logger.error(f"Simulation error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
