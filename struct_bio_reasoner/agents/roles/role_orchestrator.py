"""
Role Orchestrator for Multi-Agent Protein Engineering Workflows

This module implements the Role Orchestrator that manages complex multi-agent
workflows with expert and critic roles for protein engineering tasks.
"""

import asyncio
import logging
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path

from .base_role import BaseRole, RoleType
from .md_expert import MDSimulationExpert
from .structure_expert import StructurePredictionExpert
from .md_critic import MDSimulationCritic
from .structure_critic import StructurePredictionCritic

logger = logging.getLogger(__name__)


class WorkflowStage(str):
    """Workflow stage identifiers."""
    INITIALIZATION = "initialization"
    STRUCTURE_PREDICTION = "structure_prediction"
    STRUCTURE_EVALUATION = "structure_evaluation"
    MD_SIMULATION = "md_simulation"
    MD_EVALUATION = "md_evaluation"
    CONSENSUS_ANALYSIS = "consensus_analysis"
    FINAL_RECOMMENDATIONS = "final_recommendations"


class RoleOrchestrator:
    """
    Orchestrator for managing multi-agent protein engineering workflows.
    
    This orchestrator coordinates expert and critic roles to perform
    comprehensive protein engineering analysis with continuous feedback
    and improvement.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the role orchestrator.
        
        Args:
            config: Orchestrator configuration including role settings
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Orchestrator identification
        self.orchestrator_id = config.get("orchestrator_id", "protein_engineering_orchestrator")
        
        # Role management
        self.expert_roles: Dict[str, BaseRole] = {}
        self.critic_roles: Dict[str, BaseRole] = {}
        self.role_registry: Dict[str, BaseRole] = {}
        
        # Workflow management
        self.current_workflow = None
        self.workflow_history = []
        self.active_tasks = {}
        
        # Performance tracking
        self.workflow_metrics = {
            "workflows_completed": 0,
            "average_workflow_time": 0.0,
            "expert_performance_trends": {},
            "improvement_over_time": []
        }
        
        # Configuration
        self.max_concurrent_workflows = config.get("max_concurrent_workflows", 3)
        self.enable_critic_feedback = config.get("enable_critic_feedback", True)
        self.feedback_frequency = config.get("feedback_frequency", "per_task")
        
        self.logger.info(f"Role Orchestrator {self.orchestrator_id} initialized")
    
    async def initialize(self) -> bool:
        """Initialize the orchestrator and all roles."""
        try:
            self.logger.info("Initializing Role Orchestrator...")
            
            # Initialize expert roles
            await self._initialize_expert_roles()
            
            # Initialize critic roles
            if self.enable_critic_feedback:
                await self._initialize_critic_roles()
            
            # Set up role communication
            self._setup_role_communication()
            
            self.logger.info(f"Role Orchestrator initialized with {len(self.expert_roles)} experts and {len(self.critic_roles)} critics")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Role Orchestrator: {e}")
            return False
    
    async def _initialize_expert_roles(self):
        """Initialize expert roles."""
        expert_config = self.config.get("expert_roles", {})
        
        # Initialize MD Simulation Expert
        if expert_config.get("md_expert", {}).get("enabled", True):
            md_expert = MDSimulationExpert(expert_config.get("md_expert", {}))
            if await md_expert.initialize():
                self.expert_roles["md_expert"] = md_expert
                self.role_registry[md_expert.role_id] = md_expert
                self.logger.info("MD Simulation Expert initialized")
        
        # Initialize Structure Prediction Expert
        if expert_config.get("structure_expert", {}).get("enabled", True):
            structure_expert = StructurePredictionExpert(expert_config.get("structure_expert", {}))
            if await structure_expert.initialize():
                self.expert_roles["structure_expert"] = structure_expert
                self.role_registry[structure_expert.role_id] = structure_expert
                self.logger.info("Structure Prediction Expert initialized")
    
    async def _initialize_critic_roles(self):
        """Initialize critic roles."""
        critic_config = self.config.get("critic_roles", {})
        
        # Initialize MD Simulation Critic
        if critic_config.get("md_critic", {}).get("enabled", True):
            md_critic = MDSimulationCritic(critic_config.get("md_critic", {}))
            if await md_critic.initialize():
                self.critic_roles["md_critic"] = md_critic
                self.role_registry[md_critic.role_id] = md_critic
                self.logger.info("MD Simulation Critic initialized")
        
        # Initialize Structure Prediction Critic
        if critic_config.get("structure_critic", {}).get("enabled", True):
            structure_critic = StructurePredictionCritic(critic_config.get("structure_critic", {}))
            if await structure_critic.initialize():
                self.critic_roles["structure_critic"] = structure_critic
                self.role_registry[structure_critic.role_id] = structure_critic
                self.logger.info("Structure Prediction Critic initialized")
    
    def _setup_role_communication(self):
        """Set up communication channels between roles."""
        # Register all roles with each other for communication
        for role_id, role in self.role_registry.items():
            for peer_id, peer_role in self.role_registry.items():
                if role_id != peer_id:
                    role.register_peer_role(peer_id, peer_role)
        
        self.logger.info("Role communication channels established")
    
    async def execute_protein_engineering_workflow(self, 
                                                 protein_data: Dict[str, Any],
                                                 objectives: List[str],
                                                 workflow_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a comprehensive protein engineering workflow with expert-critic collaboration.
        
        Args:
            protein_data: Protein information (sequence, UniProt ID, etc.)
            objectives: List of engineering objectives (thermostability, activity, etc.)
            workflow_config: Optional workflow-specific configuration
            
        Returns:
            Comprehensive workflow results with expert outputs and critic feedback
        """
        workflow_start = datetime.now()
        workflow_id = f"workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            self.logger.info(f"Starting protein engineering workflow: {workflow_id}")
            
            # Initialize workflow
            workflow_results = {
                "workflow_id": workflow_id,
                "protein_data": protein_data,
                "objectives": objectives,
                "start_time": workflow_start.isoformat(),
                "stages": {},
                "expert_outputs": {},
                "critic_evaluations": {},
                "consensus_analysis": {},
                "final_recommendations": []
            }
            
            self.current_workflow = workflow_results
            
            # Stage 1: Structure Prediction
            if "structure_expert" in self.expert_roles:
                structure_results = await self._execute_structure_prediction_stage(
                    protein_data, objectives, workflow_config
                )
                workflow_results["stages"][WorkflowStage.STRUCTURE_PREDICTION] = structure_results
                workflow_results["expert_outputs"]["structure_expert"] = structure_results
                
                # Get critic feedback on structure prediction
                if "structure_critic" in self.critic_roles:
                    structure_evaluation = await self._get_critic_evaluation(
                        "structure_critic", structure_results, 
                        {"task_type": "structure_prediction", "objectives": objectives}
                    )
                    workflow_results["stages"][WorkflowStage.STRUCTURE_EVALUATION] = structure_evaluation
                    workflow_results["critic_evaluations"]["structure_critic"] = structure_evaluation
            
            # Stage 2: MD Simulation (using structure prediction results)
            if "md_expert" in self.expert_roles:
                md_context = {
                    "protein_data": protein_data,
                    "objectives": objectives,
                    "structure_data": workflow_results["expert_outputs"].get("structure_expert", {})
                }
                
                md_results = await self._execute_md_simulation_stage(
                    md_context, objectives, workflow_config
                )
                workflow_results["stages"][WorkflowStage.MD_SIMULATION] = md_results
                workflow_results["expert_outputs"]["md_expert"] = md_results
                
                # Get critic feedback on MD simulation
                if "md_critic" in self.critic_roles:
                    md_evaluation = await self._get_critic_evaluation(
                        "md_critic", md_results,
                        {"task_type": "thermostability_simulation", "objectives": objectives}
                    )
                    workflow_results["stages"][WorkflowStage.MD_EVALUATION] = md_evaluation
                    workflow_results["critic_evaluations"]["md_critic"] = md_evaluation
            
            # Stage 3: Consensus Analysis
            consensus_results = await self._perform_consensus_analysis(workflow_results)
            workflow_results["stages"][WorkflowStage.CONSENSUS_ANALYSIS] = consensus_results
            workflow_results["consensus_analysis"] = consensus_results
            
            # Stage 4: Final Recommendations
            final_recommendations = await self._generate_final_recommendations(workflow_results)
            workflow_results["stages"][WorkflowStage.FINAL_RECOMMENDATIONS] = final_recommendations
            workflow_results["final_recommendations"] = final_recommendations
            
            # Complete workflow
            workflow_end = datetime.now()
            workflow_results["end_time"] = workflow_end.isoformat()
            workflow_results["total_execution_time"] = (workflow_end - workflow_start).total_seconds()
            workflow_results["status"] = "completed"
            
            # Update performance metrics
            self._update_workflow_metrics(workflow_results)
            
            # Store workflow history
            self.workflow_history.append(workflow_results)
            self.current_workflow = None
            
            self.logger.info(f"Workflow {workflow_id} completed successfully in {workflow_results['total_execution_time']:.2f} seconds")
            
            return workflow_results
            
        except Exception as e:
            self.logger.error(f"Workflow {workflow_id} failed: {e}")
            
            # Create error result
            error_result = {
                "workflow_id": workflow_id,
                "status": "failed",
                "error": str(e),
                "start_time": workflow_start.isoformat(),
                "end_time": datetime.now().isoformat(),
                "partial_results": workflow_results if 'workflow_results' in locals() else {}
            }
            
            self.workflow_history.append(error_result)
            self.current_workflow = None
            
            return error_result
    
    async def _execute_structure_prediction_stage(self, 
                                                protein_data: Dict[str, Any],
                                                objectives: List[str],
                                                workflow_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute structure prediction stage."""
        self.logger.info("Executing structure prediction stage...")
        
        structure_expert = self.expert_roles["structure_expert"]
        
        # Prepare task for structure expert
        task = {
            "task_type": "structure_prediction",
            "protein_data": protein_data,
            "analysis_requirements": ["quality_assessment", "functional_sites"],
            "quality_requirements": {"minimum_confidence": 60.0}
        }
        
        # Execute expert task
        expert_request = {
            "type": "expert_task",
            "task": task
        }
        
        result = await structure_expert.process_request(expert_request)
        
        self.logger.info("Structure prediction stage completed")
        return result
    
    async def _execute_md_simulation_stage(self,
                                         context: Dict[str, Any],
                                         objectives: List[str],
                                         workflow_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute MD simulation stage."""
        self.logger.info("Executing MD simulation stage...")
        
        md_expert = self.expert_roles["md_expert"]
        
        # Prepare task for MD expert
        task = {
            "task_type": "thermostability_simulation",
            "protein_data": context["protein_data"],
            "simulation_params": {
                "temperature": 350.0,  # High temperature for thermostability
                "simulation_time": 10.0
            },
            "analysis_requirements": ["stability_analysis", "trajectory_analysis"]
        }
        
        # Execute expert task
        expert_request = {
            "type": "expert_task",
            "task": task
        }
        
        result = await md_expert.process_request(expert_request)
        
        self.logger.info("MD simulation stage completed")
        return result
    
    async def _get_critic_evaluation(self,
                                   critic_role_name: str,
                                   expert_output: Dict[str, Any],
                                   context: Dict[str, Any]) -> Dict[str, Any]:
        """Get critic evaluation of expert performance."""
        if critic_role_name not in self.critic_roles:
            return {"error": f"Critic role {critic_role_name} not available"}
        
        critic = self.critic_roles[critic_role_name]
        
        # Prepare evaluation request
        evaluation_request = {
            "type": "evaluate",
            "expert_output": expert_output,
            "context": context
        }
        
        evaluation_result = await critic.process_request(evaluation_request)
        
        self.logger.info(f"Critic evaluation completed by {critic_role_name}")
        return evaluation_result

    async def _perform_consensus_analysis(self, workflow_results: Dict[str, Any]) -> Dict[str, Any]:
        """Perform consensus analysis across expert outputs and critic feedback."""
        self.logger.info("Performing consensus analysis...")

        consensus = {
            "analysis_type": "expert_critic_consensus",
            "timestamp": datetime.now().isoformat(),
            "expert_agreement": {},
            "critic_insights": {},
            "integrated_assessment": {},
            "confidence_scores": {}
        }

        # Analyze expert outputs
        expert_outputs = workflow_results.get("expert_outputs", {})

        # Structure prediction consensus
        if "structure_expert" in expert_outputs:
            structure_output = expert_outputs["structure_expert"]
            consensus["expert_agreement"]["structure_prediction"] = {
                "success": structure_output.get("prediction_successful", False),
                "confidence": structure_output.get("structure_confidence", 0),
                "quality": structure_output.get("confidence_score", 0)
            }

        # MD simulation consensus
        if "md_expert" in expert_outputs:
            md_output = expert_outputs["md_expert"]
            consensus["expert_agreement"]["md_simulation"] = {
                "success": md_output.get("simulation_successful", False),
                "stability_score": md_output.get("stability_score", 0),
                "quality": md_output.get("confidence_score", 0)
            }

        # Integrate critic feedback
        critic_evaluations = workflow_results.get("critic_evaluations", {})

        for critic_name, evaluation in critic_evaluations.items():
            if "performance_scores" in evaluation:
                consensus["critic_insights"][critic_name] = {
                    "overall_score": evaluation["performance_scores"].get("overall", 0),
                    "key_strengths": evaluation.get("strengths_identified", []),
                    "improvement_areas": evaluation.get("areas_for_improvement", []),
                    "priority_recommendations": evaluation.get("recommendation_priority", {})
                }

        # Generate integrated assessment
        consensus["integrated_assessment"] = self._generate_integrated_assessment(
            expert_outputs, critic_evaluations
        )

        # Calculate overall confidence scores
        consensus["confidence_scores"] = self._calculate_consensus_confidence(
            expert_outputs, critic_evaluations
        )

        return consensus

    def _generate_integrated_assessment(self,
                                      expert_outputs: Dict[str, Any],
                                      critic_evaluations: Dict[str, Any]) -> Dict[str, Any]:
        """Generate integrated assessment from expert and critic inputs."""
        assessment = {
            "overall_success": True,
            "quality_rating": "good",
            "reliability": "moderate",
            "experimental_readiness": "medium",
            "key_findings": [],
            "critical_issues": [],
            "recommendations": []
        }

        # Assess overall success
        structure_success = expert_outputs.get("structure_expert", {}).get("prediction_successful", False)
        md_success = expert_outputs.get("md_expert", {}).get("simulation_successful", False)

        if not structure_success or not md_success:
            assessment["overall_success"] = False
            assessment["quality_rating"] = "poor"

        # Assess quality based on critic scores
        critic_scores = []
        for critic_eval in critic_evaluations.values():
            if "performance_scores" in critic_eval:
                critic_scores.append(critic_eval["performance_scores"].get("overall", 0))

        if critic_scores:
            avg_critic_score = sum(critic_scores) / len(critic_scores)
            if avg_critic_score > 0.8:
                assessment["quality_rating"] = "excellent"
            elif avg_critic_score > 0.6:
                assessment["quality_rating"] = "good"
            elif avg_critic_score > 0.4:
                assessment["quality_rating"] = "moderate"
            else:
                assessment["quality_rating"] = "poor"

        # Generate key findings
        if structure_success:
            structure_conf = expert_outputs["structure_expert"].get("structure_confidence", 0)
            assessment["key_findings"].append(f"Structure prediction successful with {structure_conf:.1f}% confidence")

        if md_success:
            stability_score = expert_outputs["md_expert"].get("stability_score", 0)
            assessment["key_findings"].append(f"MD simulation completed with stability score {stability_score:.3f}")

        # Identify critical issues from critics
        for critic_eval in critic_evaluations.values():
            critical_issues = critic_eval.get("recommendation_priority", {}).get("critical", [])
            assessment["critical_issues"].extend(critical_issues)

        # Generate integrated recommendations
        assessment["recommendations"] = self._generate_integrated_recommendations(
            expert_outputs, critic_evaluations
        )

        return assessment

    def _generate_integrated_recommendations(self,
                                           expert_outputs: Dict[str, Any],
                                           critic_evaluations: Dict[str, Any]) -> List[str]:
        """Generate integrated recommendations from all sources."""
        recommendations = []

        # Collect expert recommendations
        for expert_output in expert_outputs.values():
            expert_recs = expert_output.get("recommendations", [])
            recommendations.extend(expert_recs)

        # Collect critic improvement suggestions
        for critic_eval in critic_evaluations.values():
            critic_suggestions = critic_eval.get("improvement_suggestions", [])
            recommendations.extend(critic_suggestions)

        # Remove duplicates and prioritize
        unique_recommendations = list(set(recommendations))

        # Add consensus-specific recommendations
        unique_recommendations.append("Validate computational predictions with experimental data")
        unique_recommendations.append("Consider iterative improvement based on critic feedback")

        return unique_recommendations[:10]  # Limit to top 10 recommendations

    def _calculate_consensus_confidence(self,
                                      expert_outputs: Dict[str, Any],
                                      critic_evaluations: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate consensus confidence scores."""
        confidence_scores = {
            "structure_prediction": 0.0,
            "md_simulation": 0.0,
            "overall_workflow": 0.0
        }

        # Structure prediction confidence
        if "structure_expert" in expert_outputs:
            expert_conf = expert_outputs["structure_expert"].get("confidence_score", 0)
            critic_conf = 0.0
            if "structure_critic" in critic_evaluations:
                critic_conf = critic_evaluations["structure_critic"].get("performance_scores", {}).get("overall", 0)

            confidence_scores["structure_prediction"] = (expert_conf + critic_conf) / 2

        # MD simulation confidence
        if "md_expert" in expert_outputs:
            expert_conf = expert_outputs["md_expert"].get("confidence_score", 0)
            critic_conf = 0.0
            if "md_critic" in critic_evaluations:
                critic_conf = critic_evaluations["md_critic"].get("performance_scores", {}).get("overall", 0)

            confidence_scores["md_simulation"] = (expert_conf + critic_conf) / 2

        # Overall workflow confidence
        individual_scores = [score for score in confidence_scores.values() if score > 0]
        if individual_scores:
            confidence_scores["overall_workflow"] = sum(individual_scores) / len(individual_scores)

        return confidence_scores

    async def _generate_final_recommendations(self, workflow_results: Dict[str, Any]) -> List[str]:
        """Generate final recommendations based on complete workflow analysis."""
        self.logger.info("Generating final recommendations...")

        recommendations = []

        # Extract key information
        consensus = workflow_results.get("consensus_analysis", {})
        integrated_assessment = consensus.get("integrated_assessment", {})
        confidence_scores = consensus.get("confidence_scores", {})

        # Overall workflow assessment
        overall_confidence = confidence_scores.get("overall_workflow", 0)
        if overall_confidence > 0.8:
            recommendations.append("High-confidence results - proceed with experimental validation")
        elif overall_confidence > 0.6:
            recommendations.append("Moderate confidence - validate key predictions experimentally")
        else:
            recommendations.append("Low confidence - consider alternative approaches or additional analysis")

        # Specific recommendations based on expert outputs
        expert_outputs = workflow_results.get("expert_outputs", {})

        # Structure-based recommendations
        if "structure_expert" in expert_outputs:
            structure_conf = expert_outputs["structure_expert"].get("structure_confidence", 0)
            if structure_conf > 80:
                recommendations.append("High-quality structure available for detailed analysis")
            else:
                recommendations.append("Structure prediction has limitations - validate experimentally")

        # MD-based recommendations
        if "md_expert" in expert_outputs:
            stability_score = expert_outputs["md_expert"].get("stability_score", 0)
            if stability_score > 0.8:
                recommendations.append("Protein shows excellent stability - suitable for applications")
            elif stability_score > 0.6:
                recommendations.append("Moderate stability - consider stabilizing mutations")
            else:
                recommendations.append("Stability concerns - significant engineering required")

        # Critic-based recommendations
        critic_evaluations = workflow_results.get("critic_evaluations", {})
        for critic_eval in critic_evaluations.values():
            priority_recs = critic_eval.get("recommendation_priority", {})
            critical_issues = priority_recs.get("critical", [])
            if critical_issues:
                recommendations.extend([f"Critical: {issue}" for issue in critical_issues[:2]])

        # General workflow recommendations
        recommendations.extend([
            "Document all computational predictions for experimental validation",
            "Consider ensemble approaches for improved reliability",
            "Implement iterative design based on experimental feedback",
            "Monitor expert performance and adjust workflows accordingly"
        ])

        return recommendations[:15]  # Limit to top 15 recommendations

    def _update_workflow_metrics(self, workflow_results: Dict[str, Any]):
        """Update orchestrator performance metrics."""
        self.workflow_metrics["workflows_completed"] += 1

        # Update average workflow time
        execution_time = workflow_results.get("total_execution_time", 0)
        current_avg = self.workflow_metrics["average_workflow_time"]
        workflow_count = self.workflow_metrics["workflows_completed"]

        self.workflow_metrics["average_workflow_time"] = (
            (current_avg * (workflow_count - 1) + execution_time) / workflow_count
        )

        # Track expert performance trends
        expert_outputs = workflow_results.get("expert_outputs", {})
        for expert_name, output in expert_outputs.items():
            if expert_name not in self.workflow_metrics["expert_performance_trends"]:
                self.workflow_metrics["expert_performance_trends"][expert_name] = []

            confidence = output.get("confidence_score", 0)
            self.workflow_metrics["expert_performance_trends"][expert_name].append({
                "timestamp": datetime.now().isoformat(),
                "confidence": confidence,
                "success": output.get("prediction_successful", False) or output.get("simulation_successful", False)
            })

        # Track improvement over time
        consensus = workflow_results.get("consensus_analysis", {})
        overall_confidence = consensus.get("confidence_scores", {}).get("overall_workflow", 0)

        self.workflow_metrics["improvement_over_time"].append({
            "workflow_id": workflow_results.get("workflow_id"),
            "timestamp": datetime.now().isoformat(),
            "overall_confidence": overall_confidence,
            "execution_time": execution_time
        })

    def get_orchestrator_status(self) -> Dict[str, Any]:
        """Get current orchestrator status and metrics."""
        return {
            "orchestrator_id": self.orchestrator_id,
            "active_roles": {
                "experts": list(self.expert_roles.keys()),
                "critics": list(self.critic_roles.keys())
            },
            "workflow_metrics": self.workflow_metrics,
            "current_workflow": self.current_workflow is not None,
            "workflows_in_history": len(self.workflow_history),
            "role_performance": {
                role_id: role.get_status()
                for role_id, role in self.role_registry.items()
            }
        }

    async def cleanup(self):
        """Clean up orchestrator and all roles."""
        self.logger.info("Cleaning up Role Orchestrator...")

        # Clean up all roles
        for role in self.role_registry.values():
            await role.cleanup()

        # Clear registries
        self.expert_roles.clear()
        self.critic_roles.clear()
        self.role_registry.clear()

        self.logger.info("Role Orchestrator cleanup completed")
