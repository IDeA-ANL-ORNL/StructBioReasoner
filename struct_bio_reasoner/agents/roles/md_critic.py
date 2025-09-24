"""
MD Simulation Critic Role

This module implements the MD Simulation Critic role, which evaluates and provides
feedback on MD simulation expert performance and outputs.
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime

from .base_role import CriticRole

logger = logging.getLogger(__name__)


class MDSimulationCritic(CriticRole):
    """
    Critic role specializing in evaluating MD simulation expert performance.
    
    This critic is responsible for:
    - Evaluating simulation quality and methodology
    - Assessing result reliability and statistical significance
    - Providing feedback on parameter choices and protocols
    - Identifying areas for improvement in simulation workflows
    - Monitoring consistency and reproducibility
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize MD Simulation Critic."""
        super().__init__("MD Simulation Critic", config)
        
        # Critic-specific configuration
        self.specialization = "md_simulation_evaluation"
        self.evaluation_criteria = [
            "simulation_convergence",
            "parameter_appropriateness",
            "statistical_significance",
            "result_reliability",
            "methodology_soundness",
            "reproducibility"
        ]
        
        # Quality thresholds for evaluation
        self.quality_thresholds = {
            "minimum_simulation_time": 5.0,  # ns
            "rmsd_stability_threshold": 0.5,  # Å (for convergence)
            "energy_drift_threshold": 0.1,  # kcal/mol/ns
            "temperature_stability": 5.0,  # K deviation
            "confidence_threshold": 0.7,
            "statistical_samples": 100  # minimum frames for analysis
        }
        
        # Feedback style configuration
        self.feedback_style = config.get("feedback_style", "constructive")
        self.criticism_severity = config.get("criticism_severity", "moderate")
        
        # Performance tracking
        self.evaluations_performed = 0
        self.average_expert_score = 0.0
        self.improvement_suggestions_given = 0
        self.expert_improvement_rate = 0.0
        
        logger.info("MD Simulation Critic initialized")
    
    async def initialize(self) -> bool:
        """Initialize the MD critic."""
        try:
            self.initialized = True
            logger.info("MD Simulation Critic initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize MD critic: {e}")
            return False
    
    async def evaluate_performance(self, 
                                 expert_output: Dict[str, Any], 
                                 context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate MD simulation expert performance and provide feedback.
        
        Args:
            expert_output: Output from MD simulation expert
            context: Context information including task requirements and expectations
            
        Returns:
            Evaluation results with scores, feedback, and improvement suggestions
        """
        evaluation_start = datetime.now()
        
        try:
            # Extract key information
            task_type = expert_output.get("expert_role", "unknown")
            simulation_successful = expert_output.get("simulation_successful", False)
            execution_time = expert_output.get("execution_time", 0)
            
            # Perform comprehensive evaluation
            evaluation_results = {
                "critic_role": "md_simulation_critic",
                "expert_evaluated": "md_simulation_expert",
                "evaluation_timestamp": datetime.now().isoformat(),
                "task_context": context.get("task_type", "unknown")
            }
            
            # Evaluate different aspects
            methodology_score = self._evaluate_methodology(expert_output, context)
            quality_score = self._evaluate_simulation_quality(expert_output, context)
            reliability_score = self._evaluate_result_reliability(expert_output, context)
            efficiency_score = self._evaluate_efficiency(expert_output, context)
            
            # Calculate overall performance score
            overall_score = self._calculate_overall_score(
                methodology_score, quality_score, reliability_score, efficiency_score
            )
            
            evaluation_results.update({
                "performance_scores": {
                    "methodology": methodology_score,
                    "simulation_quality": quality_score,
                    "result_reliability": reliability_score,
                    "efficiency": efficiency_score,
                    "overall": overall_score
                },
                "detailed_feedback": self._generate_detailed_feedback(expert_output, context),
                "improvement_suggestions": self._generate_improvement_suggestions(expert_output, context),
                "strengths_identified": self._identify_strengths(expert_output, context),
                "areas_for_improvement": self._identify_improvement_areas(expert_output, context),
                "recommendation_priority": self._prioritize_recommendations(expert_output, context)
            })
            
            # Update performance tracking
            self.evaluations_performed += 1
            self.average_expert_score = (
                (self.average_expert_score * (self.evaluations_performed - 1) + overall_score)
                / self.evaluations_performed
            )
            
            evaluation_time = (datetime.now() - evaluation_start).total_seconds()
            evaluation_results["evaluation_time"] = evaluation_time
            
            logger.info(f"MD expert evaluation completed - Overall score: {overall_score:.2f}")
            
            return evaluation_results
            
        except Exception as e:
            logger.error(f"MD expert evaluation failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "critic_role": "md_simulation_critic",
                "timestamp": datetime.now().isoformat()
            }
    
    def _evaluate_methodology(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> float:
        """Evaluate the methodology used by the MD expert."""
        score = 0.8  # Base score
        
        # Check if simulation was successful
        if not expert_output.get("simulation_successful", False):
            score -= 0.4
            return max(0.0, score)
        
        # Evaluate parameter choices
        if "simulation_time" in expert_output:
            sim_time = expert_output["simulation_time"]
            if sim_time < self.quality_thresholds["minimum_simulation_time"]:
                score -= 0.2
            elif sim_time > 20.0:  # Good simulation time
                score += 0.1
        
        # Evaluate temperature choice
        if "temperature" in expert_output:
            temp = expert_output["temperature"]
            task_objectives = context.get("objectives", [])
            if "thermostability" in task_objectives and temp > 340:
                score += 0.1  # Good choice for thermostability
            elif temp < 280 or temp > 400:
                score -= 0.1  # Unusual temperature range
        
        # Check for appropriate analysis methods
        if "expert_analysis" in expert_output:
            score += 0.1
        
        return max(0.0, min(1.0, score))
    
    def _evaluate_simulation_quality(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> float:
        """Evaluate the quality of the simulation results."""
        score = 0.7  # Base score
        
        if not expert_output.get("simulation_successful", False):
            return 0.0
        
        # Evaluate RMSD stability
        if "rmsd_average" in expert_output:
            rmsd = expert_output["rmsd_average"]
            if rmsd < 2.0:
                score += 0.2  # Very stable
            elif rmsd < 4.0:
                score += 0.1  # Reasonably stable
            elif rmsd > 6.0:
                score -= 0.2  # Potentially unstable
        
        # Evaluate RMSF values
        if "rmsf_average" in expert_output:
            rmsf = expert_output["rmsf_average"]
            if rmsf < 1.5:
                score += 0.1  # Good flexibility profile
            elif rmsf > 3.0:
                score -= 0.1  # High flexibility
        
        # Check for trajectory file generation
        if "trajectory_file" in expert_output:
            score += 0.1
        
        # Evaluate stability score if available
        if "stability_score" in expert_output:
            stability = expert_output["stability_score"]
            if stability > 0.8:
                score += 0.1
            elif stability < 0.3:
                score -= 0.1
        
        return max(0.0, min(1.0, score))
    
    def _evaluate_result_reliability(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> float:
        """Evaluate the reliability and statistical significance of results."""
        score = 0.6  # Base score
        
        # Check confidence score
        confidence = expert_output.get("confidence_score", 0.0)
        if confidence > 0.8:
            score += 0.2
        elif confidence > 0.6:
            score += 0.1
        elif confidence < 0.4:
            score -= 0.2
        
        # Evaluate quality assessment
        quality_assessment = expert_output.get("quality_assessment", {})
        if quality_assessment:
            if quality_assessment.get("simulation_convergence") == "good":
                score += 0.1
            if quality_assessment.get("expert_confidence") == "high":
                score += 0.1
        
        # Check for appropriate error handling
        if "error" in expert_output and expert_output.get("simulation_successful", False):
            score -= 0.1  # Inconsistent error reporting
        
        # Evaluate recommendation quality
        recommendations = expert_output.get("recommendations", [])
        if len(recommendations) >= 2:
            score += 0.1  # Good number of recommendations
        
        return max(0.0, min(1.0, score))
    
    def _evaluate_efficiency(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> float:
        """Evaluate the efficiency of the expert's performance."""
        score = 0.7  # Base score
        
        # Evaluate execution time
        execution_time = expert_output.get("execution_time", 0)
        if execution_time > 0:
            if execution_time < 5.0:  # Very fast
                score += 0.2
            elif execution_time < 30.0:  # Reasonable time
                score += 0.1
            elif execution_time > 120.0:  # Slow
                score -= 0.2
        
        # Check for successful completion
        if expert_output.get("simulation_successful", False):
            score += 0.1
        else:
            score -= 0.3
        
        # Evaluate resource utilization (if available)
        # This would require more detailed resource monitoring
        
        return max(0.0, min(1.0, score))
    
    def _calculate_overall_score(self, methodology: float, quality: float, 
                               reliability: float, efficiency: float) -> float:
        """Calculate weighted overall performance score."""
        weights = {
            "methodology": 0.3,
            "quality": 0.3,
            "reliability": 0.25,
            "efficiency": 0.15
        }
        
        overall = (
            weights["methodology"] * methodology +
            weights["quality"] * quality +
            weights["reliability"] * reliability +
            weights["efficiency"] * efficiency
        )
        
        return round(overall, 3)
    
    def _generate_detailed_feedback(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate detailed feedback for the expert."""
        feedback = {
            "overall_assessment": "",
            "methodology_feedback": "",
            "quality_feedback": "",
            "reliability_feedback": "",
            "efficiency_feedback": ""
        }
        
        # Overall assessment
        overall_score = self._calculate_overall_score(
            self._evaluate_methodology(expert_output, context),
            self._evaluate_simulation_quality(expert_output, context),
            self._evaluate_result_reliability(expert_output, context),
            self._evaluate_efficiency(expert_output, context)
        )
        
        if overall_score > 0.8:
            feedback["overall_assessment"] = "Excellent performance with high-quality simulation and analysis"
        elif overall_score > 0.6:
            feedback["overall_assessment"] = "Good performance with room for improvement in some areas"
        elif overall_score > 0.4:
            feedback["overall_assessment"] = "Adequate performance but significant improvements needed"
        else:
            feedback["overall_assessment"] = "Poor performance requiring major improvements"
        
        # Methodology feedback
        if expert_output.get("simulation_successful", False):
            feedback["methodology_feedback"] = "Simulation methodology appears sound"
            
            sim_time = expert_output.get("simulation_time", 0)
            if sim_time < self.quality_thresholds["minimum_simulation_time"]:
                feedback["methodology_feedback"] += ", but simulation time may be insufficient for convergence"
        else:
            feedback["methodology_feedback"] = "Simulation failed - review methodology and parameters"
        
        # Quality feedback
        rmsd = expert_output.get("rmsd_average", 0)
        if rmsd > 0:
            if rmsd < 3.0:
                feedback["quality_feedback"] = "Good structural stability observed"
            else:
                feedback["quality_feedback"] = "High RMSD suggests potential stability issues"
        else:
            feedback["quality_feedback"] = "Quality metrics not available for assessment"
        
        # Reliability feedback
        confidence = expert_output.get("confidence_score", 0)
        if confidence > 0.7:
            feedback["reliability_feedback"] = "High confidence in results"
        elif confidence > 0.5:
            feedback["reliability_feedback"] = "Moderate confidence - consider additional validation"
        else:
            feedback["reliability_feedback"] = "Low confidence - results may be unreliable"
        
        # Efficiency feedback
        execution_time = expert_output.get("execution_time", 0)
        if execution_time > 0 and execution_time < 30:
            feedback["efficiency_feedback"] = "Good execution efficiency"
        elif execution_time > 60:
            feedback["efficiency_feedback"] = "Execution time could be optimized"
        else:
            feedback["efficiency_feedback"] = "Execution efficiency within acceptable range"
        
        return feedback
    
    def _generate_improvement_suggestions(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> List[str]:
        """Generate specific improvement suggestions."""
        suggestions = []
        
        # Simulation-specific suggestions
        if not expert_output.get("simulation_successful", False):
            suggestions.append("Review simulation setup and parameter validation")
            suggestions.append("Implement better error handling and recovery mechanisms")
        
        sim_time = expert_output.get("simulation_time", 0)
        if sim_time < self.quality_thresholds["minimum_simulation_time"]:
            suggestions.append(f"Increase simulation time to at least {self.quality_thresholds['minimum_simulation_time']} ns for better convergence")
        
        # Quality improvement suggestions
        rmsd = expert_output.get("rmsd_average", 0)
        if rmsd > 5.0:
            suggestions.append("High RMSD indicates potential issues - consider longer equilibration or different force field")
        
        # Analysis improvement suggestions
        if "expert_analysis" not in expert_output:
            suggestions.append("Include more detailed expert analysis and interpretation")
        
        confidence = expert_output.get("confidence_score", 0)
        if confidence < 0.6:
            suggestions.append("Improve confidence assessment methodology")
            suggestions.append("Consider ensemble simulations for better statistics")
        
        # Efficiency suggestions
        execution_time = expert_output.get("execution_time", 0)
        if execution_time > 60:
            suggestions.append("Optimize simulation protocols for better performance")
        
        # General suggestions
        suggestions.append("Implement more rigorous quality control checks")
        suggestions.append("Consider adding uncertainty quantification to results")
        
        self.improvement_suggestions_given += len(suggestions)
        
        return suggestions
    
    def _identify_strengths(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> List[str]:
        """Identify strengths in the expert's performance."""
        strengths = []
        
        if expert_output.get("simulation_successful", False):
            strengths.append("Successfully completed simulation task")
        
        if expert_output.get("confidence_score", 0) > 0.7:
            strengths.append("High confidence in results")
        
        if "expert_analysis" in expert_output:
            strengths.append("Provided expert analysis and interpretation")
        
        if "recommendations" in expert_output and len(expert_output["recommendations"]) > 0:
            strengths.append("Generated actionable recommendations")
        
        rmsd = expert_output.get("rmsd_average", 0)
        if rmsd > 0 and rmsd < 3.0:
            strengths.append("Achieved good structural stability")
        
        execution_time = expert_output.get("execution_time", 0)
        if execution_time > 0 and execution_time < 30:
            strengths.append("Efficient execution time")
        
        if not strengths:
            strengths.append("Completed task attempt despite challenges")
        
        return strengths
    
    def _identify_improvement_areas(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> List[str]:
        """Identify specific areas needing improvement."""
        areas = []
        
        if not expert_output.get("simulation_successful", False):
            areas.append("Simulation success rate")
        
        confidence = expert_output.get("confidence_score", 0)
        if confidence < 0.6:
            areas.append("Result confidence and reliability")
        
        rmsd = expert_output.get("rmsd_average", 0)
        if rmsd > 4.0:
            areas.append("Structural stability and convergence")
        
        if "quality_assessment" not in expert_output:
            areas.append("Quality assessment and validation")
        
        execution_time = expert_output.get("execution_time", 0)
        if execution_time > 60:
            areas.append("Execution efficiency")
        
        if len(expert_output.get("recommendations", [])) < 2:
            areas.append("Recommendation generation and insights")
        
        return areas
    
    def _prioritize_recommendations(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, List[str]]:
        """Prioritize improvement recommendations by urgency."""
        priorities = {
            "critical": [],
            "important": [],
            "nice_to_have": []
        }
        
        # Critical issues
        if not expert_output.get("simulation_successful", False):
            priorities["critical"].append("Fix simulation failure issues")
        
        confidence = expert_output.get("confidence_score", 0)
        if confidence < 0.4:
            priorities["critical"].append("Improve result reliability")
        
        # Important improvements
        rmsd = expert_output.get("rmsd_average", 0)
        if rmsd > 5.0:
            priorities["important"].append("Address structural stability issues")
        
        if confidence < 0.7:
            priorities["important"].append("Enhance confidence assessment")
        
        # Nice to have
        execution_time = expert_output.get("execution_time", 0)
        if execution_time > 30:
            priorities["nice_to_have"].append("Optimize execution efficiency")
        
        if len(expert_output.get("recommendations", [])) < 3:
            priorities["nice_to_have"].append("Expand recommendation generation")
        
        return priorities
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get MD critic capabilities."""
        return {
            "role_type": "critic",
            "specialization": self.specialization,
            "evaluation_criteria": self.evaluation_criteria,
            "quality_thresholds": self.quality_thresholds,
            "feedback_capabilities": [
                "methodology_evaluation",
                "quality_assessment",
                "reliability_analysis",
                "efficiency_evaluation",
                "improvement_suggestions"
            ],
            "performance_metrics": {
                "evaluations_performed": self.evaluations_performed,
                "average_expert_score": self.average_expert_score,
                "improvement_suggestions_given": self.improvement_suggestions_given
            }
        }
