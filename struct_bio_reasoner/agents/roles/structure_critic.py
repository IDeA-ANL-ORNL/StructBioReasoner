"""
Structure Prediction Critic Role

This module implements the Structure Prediction Critic role, which evaluates and
provides feedback on structure prediction expert performance and outputs.
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime

from .base_role import CriticRole

logger = logging.getLogger(__name__)


class StructurePredictionCritic(CriticRole):
    """
    Critic role specializing in evaluating structure prediction expert performance.
    
    This critic is responsible for:
    - Evaluating structure prediction quality and methodology
    - Assessing prediction confidence and reliability
    - Providing feedback on analysis completeness and accuracy
    - Identifying limitations and areas for improvement
    - Monitoring consistency across different prediction tasks
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize Structure Prediction Critic."""
        super().__init__("Structure Prediction Critic", config)
        
        # Critic-specific configuration
        self.specialization = "structure_prediction_evaluation"
        self.evaluation_criteria = [
            "prediction_success_rate",
            "confidence_assessment",
            "analysis_completeness",
            "methodology_appropriateness",
            "result_interpretation",
            "limitation_awareness"
        ]
        
        # Quality thresholds for evaluation
        self.quality_thresholds = {
            "minimum_confidence": 60.0,  # AlphaFold confidence score
            "high_confidence": 80.0,
            "analysis_completeness": 0.8,  # Fraction of expected analyses
            "interpretation_quality": 0.7,
            "recommendation_relevance": 0.8,
            "limitation_awareness": 0.6
        }
        
        # Evaluation weights
        self.evaluation_weights = {
            "prediction_quality": 0.3,
            "analysis_depth": 0.25,
            "interpretation_accuracy": 0.2,
            "methodology": 0.15,
            "efficiency": 0.1
        }
        
        # Performance tracking
        self.evaluations_performed = 0
        self.average_expert_score = 0.0
        self.prediction_success_rate = 0.0
        self.improvement_tracking = []
        
        logger.info("Structure Prediction Critic initialized")
    
    async def initialize(self) -> bool:
        """Initialize the structure prediction critic."""
        try:
            self.initialized = True
            logger.info("Structure Prediction Critic initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize structure critic: {e}")
            return False
    
    async def evaluate_performance(self, 
                                 expert_output: Dict[str, Any], 
                                 context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate structure prediction expert performance and provide feedback.
        
        Args:
            expert_output: Output from structure prediction expert
            context: Context information including task requirements and expectations
            
        Returns:
            Evaluation results with scores, feedback, and improvement suggestions
        """
        evaluation_start = datetime.now()
        
        try:
            # Extract key information
            task_type = expert_output.get("expert_role", "unknown")
            prediction_successful = expert_output.get("prediction_successful", False)
            execution_time = expert_output.get("execution_time", 0)
            
            # Perform comprehensive evaluation
            evaluation_results = {
                "critic_role": "structure_prediction_critic",
                "expert_evaluated": "structure_prediction_expert",
                "evaluation_timestamp": datetime.now().isoformat(),
                "task_context": context.get("task_type", "unknown")
            }
            
            # Evaluate different aspects
            prediction_quality_score = self._evaluate_prediction_quality(expert_output, context)
            analysis_depth_score = self._evaluate_analysis_depth(expert_output, context)
            interpretation_score = self._evaluate_interpretation_accuracy(expert_output, context)
            methodology_score = self._evaluate_methodology(expert_output, context)
            efficiency_score = self._evaluate_efficiency(expert_output, context)
            
            # Calculate overall performance score
            overall_score = self._calculate_overall_score(
                prediction_quality_score, analysis_depth_score, interpretation_score,
                methodology_score, efficiency_score
            )
            
            evaluation_results.update({
                "performance_scores": {
                    "prediction_quality": prediction_quality_score,
                    "analysis_depth": analysis_depth_score,
                    "interpretation_accuracy": interpretation_score,
                    "methodology": methodology_score,
                    "efficiency": efficiency_score,
                    "overall": overall_score
                },
                "detailed_feedback": self._generate_detailed_feedback(expert_output, context),
                "improvement_suggestions": self._generate_improvement_suggestions(expert_output, context),
                "strengths_identified": self._identify_strengths(expert_output, context),
                "areas_for_improvement": self._identify_improvement_areas(expert_output, context),
                "confidence_assessment": self._assess_expert_confidence(expert_output, context),
                "recommendation_priority": self._prioritize_recommendations(expert_output, context)
            })
            
            # Update performance tracking
            self.evaluations_performed += 1
            self.average_expert_score = (
                (self.average_expert_score * (self.evaluations_performed - 1) + overall_score)
                / self.evaluations_performed
            )
            
            if prediction_successful:
                success_count = sum(1 for eval in self.improvement_tracking if eval.get("prediction_successful", False))
                self.prediction_success_rate = (success_count + 1) / self.evaluations_performed
            
            # Track improvement over time
            self.improvement_tracking.append({
                "timestamp": datetime.now().isoformat(),
                "overall_score": overall_score,
                "prediction_successful": prediction_successful,
                "task_type": context.get("task_type", "unknown")
            })
            
            evaluation_time = (datetime.now() - evaluation_start).total_seconds()
            evaluation_results["evaluation_time"] = evaluation_time
            
            logger.info(f"Structure expert evaluation completed - Overall score: {overall_score:.2f}")
            
            return evaluation_results
            
        except Exception as e:
            logger.error(f"Structure expert evaluation failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "critic_role": "structure_prediction_critic",
                "timestamp": datetime.now().isoformat()
            }
    
    def _evaluate_prediction_quality(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> float:
        """Evaluate the quality of structure predictions."""
        score = 0.5  # Base score
        
        # Check if prediction was successful
        if not expert_output.get("prediction_successful", False):
            return 0.1  # Very low score for failed predictions
        
        # Evaluate confidence score
        structure_confidence = expert_output.get("structure_confidence", 0)
        if structure_confidence > self.quality_thresholds["high_confidence"]:
            score += 0.3  # High confidence prediction
        elif structure_confidence > self.quality_thresholds["minimum_confidence"]:
            score += 0.2  # Acceptable confidence
        else:
            score -= 0.1  # Low confidence
        
        # Check for structure data availability
        if "structure_data" in expert_output:
            score += 0.1
        
        # Evaluate PDB URL availability
        if "pdb_url" in expert_output and expert_output["pdb_url"]:
            score += 0.1
        
        # Check for expert analysis
        if "expert_analysis" in expert_output:
            analysis = expert_output["expert_analysis"]
            if isinstance(analysis, dict) and len(analysis) > 2:
                score += 0.1
        
        return max(0.0, min(1.0, score))
    
    def _evaluate_analysis_depth(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> float:
        """Evaluate the depth and completeness of structural analysis."""
        score = 0.6  # Base score
        
        # Check for different types of analysis
        analysis_components = [
            "expert_analysis",
            "quality_assessment", 
            "recommendations",
            "confidence_score"
        ]
        
        present_components = sum(1 for comp in analysis_components if comp in expert_output)
        completeness = present_components / len(analysis_components)
        
        if completeness > 0.8:
            score += 0.2
        elif completeness > 0.6:
            score += 0.1
        elif completeness < 0.4:
            score -= 0.2
        
        # Evaluate recommendation quality
        recommendations = expert_output.get("recommendations", [])
        if len(recommendations) >= 3:
            score += 0.1
        elif len(recommendations) < 1:
            score -= 0.1
        
        # Check for limitation awareness
        expert_analysis = expert_output.get("expert_analysis", {})
        if isinstance(expert_analysis, dict):
            if "limitations" in expert_analysis or "recommended_use" in expert_analysis:
                score += 0.1
        
        return max(0.0, min(1.0, score))
    
    def _evaluate_interpretation_accuracy(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> float:
        """Evaluate the accuracy and appropriateness of result interpretation."""
        score = 0.7  # Base score
        
        # Check confidence interpretation
        structure_confidence = expert_output.get("structure_confidence", 0)
        expert_analysis = expert_output.get("expert_analysis", {})
        
        if isinstance(expert_analysis, dict):
            confidence_assessment = expert_analysis.get("confidence_assessment", "")
            reliability = expert_analysis.get("reliability", "")
            
            # Check if confidence interpretation matches actual confidence
            if structure_confidence > 80 and "high" in confidence_assessment.lower():
                score += 0.1
            elif structure_confidence < 60 and "low" in confidence_assessment.lower():
                score += 0.1
            elif structure_confidence > 80 and "low" in confidence_assessment.lower():
                score -= 0.2  # Misinterpretation
            
            # Check for appropriate reliability assessment
            if reliability in ["high", "moderate", "low"]:
                score += 0.05
        
        # Evaluate recommendation appropriateness
        recommendations = expert_output.get("recommendations", [])
        if recommendations:
            # Check if recommendations match confidence level
            high_conf_recs = ["detailed structural analysis", "drug design", "mutation effect prediction"]
            low_conf_recs = ["experimental validation", "alternative methods"]
            
            if structure_confidence > 80:
                if any(rec for rec in recommendations if any(hc in rec.lower() for hc in ["detailed", "drug", "mutation"])):
                    score += 0.1
            elif structure_confidence < 60:
                if any(rec for rec in recommendations if any(lc in rec.lower() for lc in ["validation", "alternative", "caution"])):
                    score += 0.1
        
        return max(0.0, min(1.0, score))
    
    def _evaluate_methodology(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> float:
        """Evaluate the methodology and approach used."""
        score = 0.7  # Base score
        
        # Check if appropriate prediction method was used
        prediction_method = expert_output.get("prediction_method", "")
        if "alphafold" in prediction_method.lower():
            score += 0.1  # Good choice for most proteins
        
        # Evaluate error handling
        if not expert_output.get("prediction_successful", False):
            error_msg = expert_output.get("error", "")
            if error_msg and len(error_msg) > 10:
                score += 0.05  # Good error reporting
            
            # Check for fallback recommendations
            if "fallback_recommendation" in expert_output or "alternative_methods" in expert_output:
                score += 0.1
        
        # Check for appropriate quality assessment
        quality_assessment = expert_output.get("quality_assessment", {})
        if isinstance(quality_assessment, dict) and len(quality_assessment) > 1:
            score += 0.1
        
        # Evaluate execution time reasonableness
        execution_time = expert_output.get("execution_time", 0)
        if 0 < execution_time < 10:  # Reasonable time for structure prediction
            score += 0.05
        elif execution_time > 60:  # Too slow
            score -= 0.1
        
        return max(0.0, min(1.0, score))
    
    def _evaluate_efficiency(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> float:
        """Evaluate the efficiency of the expert's performance."""
        score = 0.7  # Base score
        
        # Evaluate execution time
        execution_time = expert_output.get("execution_time", 0)
        if execution_time > 0:
            if execution_time < 5.0:  # Very fast
                score += 0.2
            elif execution_time < 15.0:  # Reasonable time
                score += 0.1
            elif execution_time > 60.0:  # Slow
                score -= 0.2
        
        # Check for successful completion
        if expert_output.get("prediction_successful", False):
            score += 0.1
        else:
            score -= 0.2
        
        # Evaluate resource utilization (based on available data)
        if "structure_data" in expert_output and expert_output.get("prediction_successful", False):
            score += 0.1  # Successfully retrieved data
        
        return max(0.0, min(1.0, score))
    
    def _calculate_overall_score(self, prediction_quality: float, analysis_depth: float,
                               interpretation: float, methodology: float, efficiency: float) -> float:
        """Calculate weighted overall performance score."""
        overall = (
            self.evaluation_weights["prediction_quality"] * prediction_quality +
            self.evaluation_weights["analysis_depth"] * analysis_depth +
            self.evaluation_weights["interpretation_accuracy"] * interpretation +
            self.evaluation_weights["methodology"] * methodology +
            self.evaluation_weights["efficiency"] * efficiency
        )
        
        return round(overall, 3)
    
    def _generate_detailed_feedback(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate detailed feedback for the expert."""
        feedback = {
            "overall_assessment": "",
            "prediction_quality_feedback": "",
            "analysis_feedback": "",
            "interpretation_feedback": "",
            "methodology_feedback": "",
            "efficiency_feedback": ""
        }
        
        # Overall assessment
        overall_score = self._calculate_overall_score(
            self._evaluate_prediction_quality(expert_output, context),
            self._evaluate_analysis_depth(expert_output, context),
            self._evaluate_interpretation_accuracy(expert_output, context),
            self._evaluate_methodology(expert_output, context),
            self._evaluate_efficiency(expert_output, context)
        )
        
        if overall_score > 0.8:
            feedback["overall_assessment"] = "Excellent structure prediction performance with comprehensive analysis"
        elif overall_score > 0.6:
            feedback["overall_assessment"] = "Good performance with some areas for enhancement"
        elif overall_score > 0.4:
            feedback["overall_assessment"] = "Adequate performance but significant improvements needed"
        else:
            feedback["overall_assessment"] = "Poor performance requiring major improvements"
        
        # Prediction quality feedback
        if expert_output.get("prediction_successful", False):
            confidence = expert_output.get("structure_confidence", 0)
            if confidence > 80:
                feedback["prediction_quality_feedback"] = "High-quality prediction with excellent confidence"
            elif confidence > 60:
                feedback["prediction_quality_feedback"] = "Good prediction quality with acceptable confidence"
            else:
                feedback["prediction_quality_feedback"] = "Low confidence prediction - use with caution"
        else:
            feedback["prediction_quality_feedback"] = "Prediction failed - review input parameters and methods"
        
        # Analysis feedback
        recommendations = expert_output.get("recommendations", [])
        if len(recommendations) >= 3:
            feedback["analysis_feedback"] = "Comprehensive analysis with good recommendations"
        elif len(recommendations) >= 1:
            feedback["analysis_feedback"] = "Basic analysis provided - could be more comprehensive"
        else:
            feedback["analysis_feedback"] = "Analysis lacking - need more detailed insights and recommendations"
        
        # Interpretation feedback
        expert_analysis = expert_output.get("expert_analysis", {})
        if isinstance(expert_analysis, dict) and len(expert_analysis) > 2:
            feedback["interpretation_feedback"] = "Good interpretation of results with appropriate context"
        else:
            feedback["interpretation_feedback"] = "Interpretation could be more detailed and contextual"
        
        # Methodology feedback
        if expert_output.get("prediction_successful", False):
            feedback["methodology_feedback"] = "Appropriate methodology for structure prediction"
        else:
            if "alternative_methods" in expert_output:
                feedback["methodology_feedback"] = "Good fallback suggestions despite prediction failure"
            else:
                feedback["methodology_feedback"] = "Need better error handling and alternative approaches"
        
        # Efficiency feedback
        execution_time = expert_output.get("execution_time", 0)
        if execution_time > 0 and execution_time < 15:
            feedback["efficiency_feedback"] = "Good execution efficiency"
        elif execution_time > 30:
            feedback["efficiency_feedback"] = "Execution time could be optimized"
        else:
            feedback["efficiency_feedback"] = "Execution efficiency within acceptable range"
        
        return feedback
    
    def _generate_improvement_suggestions(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> List[str]:
        """Generate specific improvement suggestions."""
        suggestions = []
        
        # Prediction-specific suggestions
        if not expert_output.get("prediction_successful", False):
            suggestions.append("Implement better input validation and error handling")
            suggestions.append("Add fallback prediction methods for failed cases")
        
        confidence = expert_output.get("structure_confidence", 0)
        if confidence < self.quality_thresholds["minimum_confidence"]:
            suggestions.append("Develop better confidence assessment and interpretation methods")
        
        # Analysis improvement suggestions
        recommendations = expert_output.get("recommendations", [])
        if len(recommendations) < 2:
            suggestions.append("Provide more comprehensive recommendations and insights")
        
        if "expert_analysis" not in expert_output:
            suggestions.append("Include detailed expert analysis and interpretation")
        
        # Quality assessment suggestions
        if "quality_assessment" not in expert_output:
            suggestions.append("Implement comprehensive quality assessment metrics")
        
        # Efficiency suggestions
        execution_time = expert_output.get("execution_time", 0)
        if execution_time > 30:
            suggestions.append("Optimize prediction workflow for better performance")
        
        # General suggestions
        suggestions.append("Enhance limitation awareness and uncertainty quantification")
        suggestions.append("Improve integration with experimental validation recommendations")
        
        return suggestions
    
    def _identify_strengths(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> List[str]:
        """Identify strengths in the expert's performance."""
        strengths = []
        
        if expert_output.get("prediction_successful", False):
            strengths.append("Successfully completed structure prediction")
        
        confidence = expert_output.get("structure_confidence", 0)
        if confidence > 80:
            strengths.append("Achieved high-confidence structure prediction")
        
        if "expert_analysis" in expert_output:
            strengths.append("Provided expert analysis and interpretation")
        
        recommendations = expert_output.get("recommendations", [])
        if len(recommendations) >= 3:
            strengths.append("Generated comprehensive recommendations")
        
        if "pdb_url" in expert_output and expert_output["pdb_url"]:
            strengths.append("Successfully retrieved structure data and URLs")
        
        execution_time = expert_output.get("execution_time", 0)
        if execution_time > 0 and execution_time < 15:
            strengths.append("Efficient execution time")
        
        if not strengths:
            strengths.append("Attempted structure prediction task")
        
        return strengths
    
    def _identify_improvement_areas(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> List[str]:
        """Identify specific areas needing improvement."""
        areas = []
        
        if not expert_output.get("prediction_successful", False):
            areas.append("Prediction success rate and error handling")
        
        confidence = expert_output.get("structure_confidence", 0)
        if confidence < 70:
            areas.append("Prediction confidence and reliability")
        
        if len(expert_output.get("recommendations", [])) < 2:
            areas.append("Recommendation generation and analysis depth")
        
        if "quality_assessment" not in expert_output:
            areas.append("Quality assessment and validation")
        
        execution_time = expert_output.get("execution_time", 0)
        if execution_time > 30:
            areas.append("Execution efficiency and optimization")
        
        if "expert_analysis" not in expert_output:
            areas.append("Expert interpretation and insights")
        
        return areas
    
    def _assess_expert_confidence(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Assess how well the expert handles confidence and uncertainty."""
        assessment = {
            "confidence_reporting": "good" if "structure_confidence" in expert_output else "poor",
            "uncertainty_awareness": "moderate",
            "limitation_identification": "basic",
            "recommendation_appropriateness": "good"
        }
        
        # Check if expert appropriately interprets confidence
        confidence = expert_output.get("structure_confidence", 0)
        expert_analysis = expert_output.get("expert_analysis", {})
        
        if isinstance(expert_analysis, dict):
            if "limitations" in expert_analysis:
                assessment["limitation_identification"] = "good"
            if "reliability" in expert_analysis:
                assessment["uncertainty_awareness"] = "good"
        
        # Check recommendation appropriateness
        recommendations = expert_output.get("recommendations", [])
        if confidence < 60 and any("validation" in rec.lower() for rec in recommendations):
            assessment["recommendation_appropriateness"] = "excellent"
        elif confidence > 80 and any("detailed" in rec.lower() for rec in recommendations):
            assessment["recommendation_appropriateness"] = "excellent"
        
        return assessment
    
    def _prioritize_recommendations(self, expert_output: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, List[str]]:
        """Prioritize improvement recommendations by urgency."""
        priorities = {
            "critical": [],
            "important": [],
            "nice_to_have": []
        }
        
        # Critical issues
        if not expert_output.get("prediction_successful", False):
            priorities["critical"].append("Fix prediction failure issues")
        
        confidence = expert_output.get("structure_confidence", 0)
        if confidence < 50:
            priorities["critical"].append("Improve prediction confidence and reliability")
        
        # Important improvements
        if len(expert_output.get("recommendations", [])) < 2:
            priorities["important"].append("Enhance analysis depth and recommendations")
        
        if "quality_assessment" not in expert_output:
            priorities["important"].append("Implement comprehensive quality assessment")
        
        # Nice to have
        execution_time = expert_output.get("execution_time", 0)
        if execution_time > 20:
            priorities["nice_to_have"].append("Optimize execution efficiency")
        
        if "expert_analysis" not in expert_output or len(expert_output.get("expert_analysis", {})) < 3:
            priorities["nice_to_have"].append("Expand expert interpretation and insights")
        
        return priorities
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get structure prediction critic capabilities."""
        return {
            "role_type": "critic",
            "specialization": self.specialization,
            "evaluation_criteria": self.evaluation_criteria,
            "quality_thresholds": self.quality_thresholds,
            "evaluation_weights": self.evaluation_weights,
            "feedback_capabilities": [
                "prediction_quality_assessment",
                "analysis_depth_evaluation",
                "interpretation_accuracy_check",
                "methodology_review",
                "efficiency_analysis"
            ],
            "performance_metrics": {
                "evaluations_performed": self.evaluations_performed,
                "average_expert_score": self.average_expert_score,
                "prediction_success_rate": self.prediction_success_rate
            }
        }
