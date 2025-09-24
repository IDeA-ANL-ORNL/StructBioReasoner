#!/usr/bin/env python3
"""
Role-Based Protein Engineering Workflow Example

This example demonstrates the sophisticated role-based agentic workflow system
with expert and critic roles for comprehensive protein engineering analysis.

Features:
- MD Simulation Expert with specialized thermostability analysis
- Structure Prediction Expert with AlphaFold MCP integration
- MD Simulation Critic providing performance feedback and improvement suggestions
- Structure Prediction Critic evaluating prediction quality and methodology
- Role Orchestrator managing multi-agent workflows with continuous improvement
"""

import asyncio
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

# StructBioReasoner imports
from struct_bio_reasoner.agents.roles import RoleOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RoleBasedProteinEngineering:
    """
    Comprehensive role-based protein engineering analysis system.
    
    This system demonstrates advanced multi-agent collaboration with:
    - Expert roles performing specialized tasks
    - Critic roles providing continuous feedback and improvement
    - Orchestrated workflows with consensus analysis
    - Performance tracking and iterative improvement
    """
    
    def __init__(self):
        """Initialize the role-based protein engineering system."""
        self.orchestrator = None
        self.analysis_results = {}
        self.performance_history = []
        
        # Configuration for roles
        self.config = {
            "orchestrator_id": "protein_engineering_orchestrator_v1",
            "max_concurrent_workflows": 2,
            "enable_critic_feedback": True,
            "feedback_frequency": "per_task",
            
            # Expert role configurations
            "expert_roles": {
                "md_expert": {
                    "enabled": True,
                    "default_temperature": 350.0,
                    "default_simulation_time": 10.0,
                    "quality_thresholds": {
                        "rmsd_stability": 3.0,
                        "rmsf_flexibility": 2.0,
                        "energy_convergence": 0.1,
                        "sampling_efficiency": 0.8
                    }
                },
                "structure_expert": {
                    "enabled": True,
                    "structure_databases": ["alphafold", "pdb"],
                    "analysis_methods": [
                        "secondary_structure",
                        "surface_analysis",
                        "cavity_detection",
                        "interface_analysis"
                    ],
                    "quality_thresholds": {
                        "confidence_score": 70.0,
                        "resolution_equivalent": 3.0,
                        "coverage": 0.9,
                        "clash_score": 10.0
                    }
                }
            },
            
            # Critic role configurations
            "critic_roles": {
                "md_critic": {
                    "enabled": True,
                    "feedback_style": "constructive",
                    "criticism_severity": "moderate",
                    "quality_thresholds": {
                        "minimum_simulation_time": 5.0,
                        "rmsd_stability_threshold": 0.5,
                        "energy_drift_threshold": 0.1,
                        "temperature_stability": 5.0,
                        "confidence_threshold": 0.7,
                        "statistical_samples": 100
                    }
                },
                "structure_critic": {
                    "enabled": True,
                    "feedback_style": "constructive",
                    "evaluation_criteria": [
                        "prediction_success_rate",
                        "confidence_assessment",
                        "analysis_completeness",
                        "methodology_appropriateness",
                        "result_interpretation",
                        "limitation_awareness"
                    ],
                    "quality_thresholds": {
                        "minimum_confidence": 60.0,
                        "high_confidence": 80.0,
                        "analysis_completeness": 0.8,
                        "interpretation_quality": 0.7,
                        "recommendation_relevance": 0.8,
                        "limitation_awareness": 0.6
                    }
                }
            }
        }
        
        logger.info("Role-Based Protein Engineering system initialized")
    
    async def initialize(self) -> bool:
        """Initialize the orchestrator and all roles."""
        try:
            logger.info("Initializing role-based system...")
            
            # Create and initialize orchestrator
            self.orchestrator = RoleOrchestrator(self.config)
            
            if not await self.orchestrator.initialize():
                logger.error("Failed to initialize orchestrator")
                return False
            
            logger.info("Role-based system initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"System initialization failed: {e}")
            return False
    
    async def analyze_protein_thermostability(self, 
                                            protein_data: Dict[str, Any],
                                            mutations: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Perform comprehensive thermostability analysis using role-based workflow.
        
        Args:
            protein_data: Protein information (sequence, UniProt ID, etc.)
            mutations: Optional list of mutations to analyze
            
        Returns:
            Comprehensive analysis results with expert outputs and critic feedback
        """
        logger.info(f"Starting thermostability analysis for {protein_data.get('name', 'unknown protein')}")
        
        try:
            # Define analysis objectives
            objectives = ["thermostability", "structure_analysis", "mutation_validation"]
            
            # Configure workflow for thermostability analysis
            workflow_config = {
                "analysis_type": "thermostability",
                "include_mutations": mutations is not None,
                "validation_level": "comprehensive"
            }
            
            # Execute workflow
            workflow_results = await self.orchestrator.execute_protein_engineering_workflow(
                protein_data=protein_data,
                objectives=objectives,
                workflow_config=workflow_config
            )
            
            # Process mutations if provided
            if mutations:
                mutation_results = await self._analyze_mutations(mutations, workflow_results)
                workflow_results["mutation_analysis"] = mutation_results
            
            # Store results
            analysis_id = f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.analysis_results[analysis_id] = workflow_results
            
            # Update performance history
            self._update_performance_history(workflow_results)
            
            logger.info(f"Thermostability analysis completed: {analysis_id}")
            return workflow_results
            
        except Exception as e:
            logger.error(f"Thermostability analysis failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def _analyze_mutations(self, 
                               mutations: List[Dict[str, Any]], 
                               base_results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze specific mutations using the role-based system."""
        logger.info(f"Analyzing {len(mutations)} mutations...")
        
        mutation_results = {
            "total_mutations": len(mutations),
            "mutation_analyses": [],
            "comparative_analysis": {},
            "recommendations": []
        }
        
        # Get wild-type baseline from base results
        wt_stability = None
        if "expert_outputs" in base_results and "md_expert" in base_results["expert_outputs"]:
            wt_stability = base_results["expert_outputs"]["md_expert"].get("stability_score", 0.75)
        
        # Analyze each mutation
        for i, mutation in enumerate(mutations):
            logger.info(f"Analyzing mutation {i+1}/{len(mutations)}: {mutation.get('mutation', 'unknown')}")
            
            # Create mutation-specific protein data
            mutant_protein_data = base_results["protein_data"].copy()
            mutant_protein_data.update({
                "mutation": mutation,
                "variant_type": "single_point_mutation"
            })
            
            # Run workflow for mutant
            mutant_workflow = await self.orchestrator.execute_protein_engineering_workflow(
                protein_data=mutant_protein_data,
                objectives=["thermostability", "mutation_validation"],
                workflow_config={"mutation_analysis": True}
            )
            
            # Compare with wild-type
            mutant_stability = 0.75  # Default
            if ("expert_outputs" in mutant_workflow and 
                "md_expert" in mutant_workflow["expert_outputs"]):
                mutant_stability = mutant_workflow["expert_outputs"]["md_expert"].get("stability_score", 0.75)
            
            stability_change = mutant_stability - (wt_stability or 0.75)
            
            mutation_analysis = {
                "mutation": mutation,
                "workflow_results": mutant_workflow,
                "stability_comparison": {
                    "wild_type_stability": wt_stability,
                    "mutant_stability": mutant_stability,
                    "stability_change": stability_change,
                    "effect": "stabilizing" if stability_change > 0 else "destabilizing"
                }
            }
            
            mutation_results["mutation_analyses"].append(mutation_analysis)
        
        # Generate comparative analysis
        mutation_results["comparative_analysis"] = self._generate_mutation_comparison(
            mutation_results["mutation_analyses"]
        )
        
        # Generate mutation-specific recommendations
        mutation_results["recommendations"] = self._generate_mutation_recommendations(
            mutation_results["mutation_analyses"]
        )
        
        return mutation_results
    
    def _generate_mutation_comparison(self, mutation_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate comparative analysis of mutations."""
        if not mutation_analyses:
            return {}
        
        stability_changes = [
            analysis["stability_comparison"]["stability_change"] 
            for analysis in mutation_analyses
        ]
        
        comparison = {
            "best_mutation": None,
            "worst_mutation": None,
            "average_stability_change": sum(stability_changes) / len(stability_changes),
            "stabilizing_mutations": 0,
            "destabilizing_mutations": 0,
            "neutral_mutations": 0
        }
        
        # Find best and worst mutations
        best_idx = stability_changes.index(max(stability_changes))
        worst_idx = stability_changes.index(min(stability_changes))
        
        comparison["best_mutation"] = {
            "mutation": mutation_analyses[best_idx]["mutation"],
            "stability_change": stability_changes[best_idx]
        }
        
        comparison["worst_mutation"] = {
            "mutation": mutation_analyses[worst_idx]["mutation"],
            "stability_change": stability_changes[worst_idx]
        }
        
        # Count mutation effects
        for change in stability_changes:
            if change > 0.01:
                comparison["stabilizing_mutations"] += 1
            elif change < -0.01:
                comparison["destabilizing_mutations"] += 1
            else:
                comparison["neutral_mutations"] += 1
        
        return comparison
    
    def _generate_mutation_recommendations(self, mutation_analyses: List[Dict[str, Any]]) -> List[str]:
        """Generate recommendations based on mutation analysis."""
        recommendations = []
        
        if not mutation_analyses:
            return recommendations
        
        # Find stabilizing mutations
        stabilizing = [
            analysis for analysis in mutation_analyses
            if analysis["stability_comparison"]["stability_change"] > 0.01
        ]
        
        if stabilizing:
            best_stabilizing = max(stabilizing, 
                                 key=lambda x: x["stability_comparison"]["stability_change"])
            mutation_name = best_stabilizing["mutation"].get("mutation", "unknown")
            recommendations.append(f"Prioritize {mutation_name} for experimental validation (best stabilizing effect)")
        
        # General recommendations
        recommendations.extend([
            "Validate computational predictions with experimental thermostability assays",
            "Consider combining multiple stabilizing mutations for additive effects",
            "Monitor critic feedback to improve prediction accuracy over time"
        ])
        
        return recommendations
    
    def _update_performance_history(self, workflow_results: Dict[str, Any]):
        """Update system performance history."""
        performance_entry = {
            "timestamp": datetime.now().isoformat(),
            "workflow_id": workflow_results.get("workflow_id"),
            "execution_time": workflow_results.get("total_execution_time", 0),
            "overall_confidence": workflow_results.get("consensus_analysis", {}).get("confidence_scores", {}).get("overall_workflow", 0),
            "expert_performance": {},
            "critic_feedback_summary": {}
        }
        
        # Extract expert performance
        expert_outputs = workflow_results.get("expert_outputs", {})
        for expert_name, output in expert_outputs.items():
            performance_entry["expert_performance"][expert_name] = {
                "success": output.get("prediction_successful", False) or output.get("simulation_successful", False),
                "confidence": output.get("confidence_score", 0),
                "execution_time": output.get("execution_time", 0)
            }
        
        # Extract critic feedback summary
        critic_evaluations = workflow_results.get("critic_evaluations", {})
        for critic_name, evaluation in critic_evaluations.items():
            performance_entry["critic_feedback_summary"][critic_name] = {
                "overall_score": evaluation.get("performance_scores", {}).get("overall", 0),
                "improvement_suggestions_count": len(evaluation.get("improvement_suggestions", [])),
                "critical_issues_count": len(evaluation.get("recommendation_priority", {}).get("critical", []))
            }
        
        self.performance_history.append(performance_entry)
    
    def get_system_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive system performance report."""
        if not self.orchestrator:
            return {"error": "System not initialized"}
        
        orchestrator_status = self.orchestrator.get_orchestrator_status()
        
        report = {
            "system_overview": {
                "total_analyses": len(self.analysis_results),
                "performance_history_entries": len(self.performance_history),
                "active_roles": orchestrator_status["active_roles"],
                "system_uptime": "N/A"  # Would need startup time tracking
            },
            "orchestrator_metrics": orchestrator_status["workflow_metrics"],
            "role_performance": orchestrator_status["role_performance"],
            "recent_performance": self.performance_history[-5:] if self.performance_history else [],
            "improvement_trends": self._analyze_improvement_trends()
        }
        
        return report
    
    def _analyze_improvement_trends(self) -> Dict[str, Any]:
        """Analyze improvement trends over time."""
        if len(self.performance_history) < 2:
            return {"insufficient_data": True}
        
        # Analyze confidence trends
        confidences = [entry["overall_confidence"] for entry in self.performance_history]
        execution_times = [entry["execution_time"] for entry in self.performance_history]
        
        trends = {
            "confidence_trend": "improving" if confidences[-1] > confidences[0] else "declining",
            "efficiency_trend": "improving" if execution_times[-1] < execution_times[0] else "declining",
            "average_confidence": sum(confidences) / len(confidences),
            "average_execution_time": sum(execution_times) / len(execution_times)
        }
        
        return trends
    
    async def cleanup(self):
        """Clean up the role-based system."""
        if self.orchestrator:
            await self.orchestrator.cleanup()
        logger.info("Role-based system cleanup completed")


async def main():
    """Main execution function demonstrating role-based protein engineering."""
    print("🧬 Role-Based Protein Engineering Workflow")
    print("=" * 80)
    
    # Initialize system
    system = RoleBasedProteinEngineering()
    
    try:
        # Initialize the role-based system
        if not await system.initialize():
            print("❌ Failed to initialize role-based system")
            return
        
        print("✅ Role-based system initialized successfully")
        print(f"   • Experts: MD Simulation, Structure Prediction")
        print(f"   • Critics: MD Critic, Structure Critic")
        print(f"   • Orchestrator: Multi-agent workflow management")
        
        # Define protein for analysis
        protein_data = {
            "name": "ubiquitin",
            "uniprot_id": "P0CG48",
            "sequence": "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG",
            "organism": "Homo sapiens",
            "function": "protein_degradation_regulation"
        }
        
        # Define mutations to analyze
        mutations = [
            {
                "mutation": "I44A",
                "position": 44,
                "original": "I",
                "mutant": "A",
                "rationale": "Reduce steric clashes in hydrophobic core"
            },
            {
                "mutation": "K63R",
                "position": 63,
                "original": "K",
                "mutant": "R",
                "rationale": "Enhance hydrogen bonding capacity"
            }
        ]
        
        print(f"\n🔬 Starting comprehensive analysis...")
        print(f"   • Protein: {protein_data['name']} ({protein_data['uniprot_id']})")
        print(f"   • Mutations: {len(mutations)} variants to analyze")
        print(f"   • Workflow: Structure prediction → MD simulation → Critic evaluation → Consensus")
        
        # Run comprehensive analysis
        results = await system.analyze_protein_thermostability(protein_data, mutations)
        
        if results.get("status") == "error":
            print(f"❌ Analysis failed: {results.get('error')}")
            return
        
        # Display results
        print("\n" + "=" * 80)
        print("🎉 ROLE-BASED ANALYSIS COMPLETE!")
        print("=" * 80)
        
        # Workflow summary
        print(f"\n📊 Workflow Summary:")
        print(f"   • Workflow ID: {results.get('workflow_id')}")
        print(f"   • Execution Time: {results.get('total_execution_time', 0):.2f} seconds")
        print(f"   • Status: {results.get('status', 'unknown')}")
        
        # Expert performance
        expert_outputs = results.get("expert_outputs", {})
        print(f"\n🔬 Expert Performance:")
        for expert_name, output in expert_outputs.items():
            success = output.get("prediction_successful", False) or output.get("simulation_successful", False)
            confidence = output.get("confidence_score", 0)
            print(f"   • {expert_name}: {'✅' if success else '❌'} Success, {confidence:.3f} Confidence")
        
        # Critic evaluations
        critic_evaluations = results.get("critic_evaluations", {})
        print(f"\n🎯 Critic Evaluations:")
        for critic_name, evaluation in critic_evaluations.items():
            overall_score = evaluation.get("performance_scores", {}).get("overall", 0)
            suggestions_count = len(evaluation.get("improvement_suggestions", []))
            print(f"   • {critic_name}: {overall_score:.3f} Overall Score, {suggestions_count} Suggestions")
        
        # Consensus analysis
        consensus = results.get("consensus_analysis", {})
        confidence_scores = consensus.get("confidence_scores", {})
        print(f"\n🤝 Consensus Analysis:")
        print(f"   • Overall Workflow Confidence: {confidence_scores.get('overall_workflow', 0):.3f}")
        print(f"   • Structure Prediction Confidence: {confidence_scores.get('structure_prediction', 0):.3f}")
        print(f"   • MD Simulation Confidence: {confidence_scores.get('md_simulation', 0):.3f}")
        
        # Mutation analysis results
        if "mutation_analysis" in results:
            mutation_analysis = results["mutation_analysis"]
            comparative = mutation_analysis.get("comparative_analysis", {})
            print(f"\n🧬 Mutation Analysis:")
            print(f"   • Total Mutations: {mutation_analysis.get('total_mutations', 0)}")
            print(f"   • Stabilizing: {comparative.get('stabilizing_mutations', 0)}")
            print(f"   • Destabilizing: {comparative.get('destabilizing_mutations', 0)}")
            
            best_mutation = comparative.get("best_mutation", {})
            if best_mutation:
                print(f"   • Best Mutation: {best_mutation.get('mutation', {}).get('mutation', 'unknown')} "
                      f"(+{best_mutation.get('stability_change', 0):.3f} stability)")
        
        # Final recommendations
        final_recommendations = results.get("final_recommendations", [])
        print(f"\n💡 Final Recommendations:")
        for i, rec in enumerate(final_recommendations[:5], 1):
            print(f"   {i}. {rec}")
        
        # System performance report
        performance_report = system.get_system_performance_report()
        print(f"\n📈 System Performance:")
        system_overview = performance_report.get("system_overview", {})
        print(f"   • Total Analyses: {system_overview.get('total_analyses', 0)}")
        
        improvement_trends = performance_report.get("improvement_trends", {})
        if not improvement_trends.get("insufficient_data", False):
            print(f"   • Confidence Trend: {improvement_trends.get('confidence_trend', 'unknown')}")
            print(f"   • Efficiency Trend: {improvement_trends.get('efficiency_trend', 'unknown')}")
        
        print(f"\n📁 Results saved in system memory")
        print(f"   • Analysis ID: {list(system.analysis_results.keys())[-1] if system.analysis_results else 'none'}")
        print(f"   • Performance History: {len(system.performance_history)} entries")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        await system.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
