#!/usr/bin/env python3
"""
Comprehensive Multi-Tool Protein Engineering Analysis

This example demonstrates the integration of all major tools in StructBioReasoner:
- RFDiffusion for generative design
- Rosetta for computational design
- AlphaFold for structure prediction
- ESM for sequence analysis
- OpenMM for molecular dynamics
- PyMOL for visualization

The example shows how these tools work together to provide comprehensive
protein engineering insights and validation.
"""

import asyncio
import logging
import json
from pathlib import Path
from typing import Dict, List, Any

# StructBioReasoner imports
from struct_bio_reasoner.core.protein_system import ProteinEngineeringSystem
from struct_bio_reasoner.agents import (
    RFDiffusionAgent,
    RosettaAgent,
    AlphaFoldAgent,
    ESMAgent,
    MolecularDynamicsAgent
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ComprehensiveProteinAnalysis:
    """
    Comprehensive protein analysis using all available tools.
    
    This class orchestrates multiple agents and tools to provide
    complete protein engineering analysis and design recommendations.
    """
    
    def __init__(self, config_path: str = "config/protein_config.yaml"):
        """Initialize the comprehensive analysis system."""
        self.config_path = config_path
        self.protein_system = None
        self.agents = {}
        self.results = {}
        
        # Analysis parameters
        self.target_protein = "ubiquitin"
        self.target_sequence = "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG"
        self.analysis_goals = [
            "thermostability_enhancement",
            "structure_optimization", 
            "functional_site_identification",
            "mutation_design"
        ]
        
        logger.info("Comprehensive protein analysis system initialized")
    
    async def initialize_system(self) -> bool:
        """Initialize the protein system and all agents."""
        try:
            logger.info("Initializing protein system and agents...")
            
            # Initialize protein system
            self.protein_system = ProteinEngineeringSystem(self.config_path)
            await self.protein_system.initialize()
            
            # Initialize all agents
            config = self.protein_system.config
            
            # RFDiffusion Agent
            if config.get("agents", {}).get("rfdiffusion_agent", {}).get("enabled", False):
                self.agents["rfdiffusion"] = RFDiffusionAgent(config)
                await self.agents["rfdiffusion"].initialize()
                logger.info("RFDiffusion agent initialized")
            else:
                logger.info("RFDiffusion agent disabled - using mock mode")
            
            # Rosetta Agent
            if config.get("agents", {}).get("rosetta_agent", {}).get("enabled", False):
                self.agents["rosetta"] = RosettaAgent(config)
                await self.agents["rosetta"].initialize()
                logger.info("Rosetta agent initialized")
            else:
                logger.info("Rosetta agent disabled - using mock mode")
            
            # AlphaFold Agent
            if config.get("agents", {}).get("alphafold_agent", {}).get("enabled", False):
                self.agents["alphafold"] = AlphaFoldAgent(config)
                await self.agents["alphafold"].initialize()
                logger.info("AlphaFold agent initialized")
            else:
                logger.info("AlphaFold agent disabled - using mock mode")
            
            # ESM Agent
            if config.get("agents", {}).get("esm_agent", {}).get("enabled", True):
                self.agents["esm"] = ESMAgent(config)
                await self.agents["esm"].initialize()
                logger.info("ESM agent initialized")
            else:
                logger.info("ESM agent disabled")
            
            # Molecular Dynamics Agent
            if config.get("agents", {}).get("molecular_dynamics", {}).get("enabled", True):
                self.agents["md"] = MolecularDynamicsAgent(config)
                await self.agents["md"].initialize()
                logger.info("Molecular dynamics agent initialized")
            else:
                logger.info("MD agent disabled")
            
            logger.info(f"Initialized {len(self.agents)} agents successfully")
            return True
            
        except Exception as e:
            logger.error(f"System initialization failed: {e}")
            return False
    
    async def run_comprehensive_analysis(self) -> Dict[str, Any]:
        """Run comprehensive analysis using all available tools."""
        try:
            logger.info("Starting comprehensive multi-tool protein analysis")
            
            # Prepare analysis context
            context = {
                "target_protein": self.target_protein,
                "protein_sequence": self.target_sequence,
                "analysis_goals": self.analysis_goals,
                "design_objectives": ["stability", "function", "expressibility"],
                "experimental_constraints": {
                    "expression_system": "E. coli",
                    "temperature_range": [25, 85],  # °C
                    "pH_range": [6.0, 8.0]
                }
            }
            
            # Phase 1: Sequence and Structure Analysis
            logger.info("Phase 1: Sequence and structure analysis")
            await self._phase1_sequence_structure_analysis(context)
            
            # Phase 2: Generative and Computational Design
            logger.info("Phase 2: Generative and computational design")
            await self._phase2_design_generation(context)
            
            # Phase 3: Structure Prediction and Validation
            logger.info("Phase 3: Structure prediction and validation")
            await self._phase3_structure_prediction(context)
            
            # Phase 4: Molecular Dynamics Validation
            logger.info("Phase 4: Molecular dynamics validation")
            await self._phase4_dynamics_validation(context)
            
            # Phase 5: Integration and Consensus
            logger.info("Phase 5: Integration and consensus analysis")
            await self._phase5_integration_consensus(context)
            
            # Generate comprehensive report
            report = await self._generate_comprehensive_report()
            
            logger.info("Comprehensive analysis completed successfully")
            return report
            
        except Exception as e:
            logger.error(f"Comprehensive analysis failed: {e}")
            return {"status": "failed", "error": str(e)}
    
    async def _phase1_sequence_structure_analysis(self, context: Dict[str, Any]) -> None:
        """Phase 1: Analyze sequence and predict structure."""
        phase_results = {}
        
        # ESM sequence analysis
        if "esm" in self.agents:
            logger.info("Running ESM sequence analysis...")
            esm_hypotheses = await self.agents["esm"].generate_hypotheses(context)
            phase_results["esm_analysis"] = {
                "hypotheses": esm_hypotheses,
                "num_hypotheses": len(esm_hypotheses),
                "top_insights": [h["title"] for h in esm_hypotheses[:3]]
            }
        
        # AlphaFold structure prediction
        if "alphafold" in self.agents:
            logger.info("Running AlphaFold structure prediction...")
            alphafold_hypotheses = await self.agents["alphafold"].generate_hypotheses(context)
            phase_results["alphafold_prediction"] = {
                "hypotheses": alphafold_hypotheses,
                "num_hypotheses": len(alphafold_hypotheses),
                "prediction_confidence": "high" if len(self.target_sequence) < 200 else "medium"
            }
        
        self.results["phase1_sequence_structure"] = phase_results
        logger.info(f"Phase 1 completed: {len(phase_results)} analysis types")
    
    async def _phase2_design_generation(self, context: Dict[str, Any]) -> None:
        """Phase 2: Generate design hypotheses."""
        phase_results = {}
        
        # RFDiffusion generative design
        if "rfdiffusion" in self.agents:
            logger.info("Running RFDiffusion generative design...")
            rfdiffusion_hypotheses = await self.agents["rfdiffusion"].generate_hypotheses(context)
            phase_results["rfdiffusion_design"] = {
                "hypotheses": rfdiffusion_hypotheses,
                "num_hypotheses": len(rfdiffusion_hypotheses),
                "design_strategies": [h["strategy"] for h in rfdiffusion_hypotheses]
            }
        
        # Rosetta computational design
        if "rosetta" in self.agents:
            logger.info("Running Rosetta computational design...")
            # Add PDB context for Rosetta (would normally be provided)
            rosetta_context = context.copy()
            rosetta_context["pdb_file"] = "mock_structure.pdb"  # Mock for demonstration
            
            rosetta_hypotheses = await self.agents["rosetta"].generate_hypotheses(rosetta_context)
            phase_results["rosetta_design"] = {
                "hypotheses": rosetta_hypotheses,
                "num_hypotheses": len(rosetta_hypotheses),
                "design_approaches": [h["approach"] for h in rosetta_hypotheses]
            }
        
        self.results["phase2_design_generation"] = phase_results
        logger.info(f"Phase 2 completed: {len(phase_results)} design approaches")
    
    async def _phase3_structure_prediction(self, context: Dict[str, Any]) -> None:
        """Phase 3: Predict and validate structures."""
        phase_results = {}
        
        # Structure prediction for designed variants
        if "alphafold" in self.agents:
            logger.info("Predicting structures for designed variants...")
            
            # Mock designed sequences (would come from Phase 2)
            designed_variants = [
                self.target_sequence,  # Wild-type
                self.target_sequence.replace("K", "R", 1),  # Conservative mutation
                self.target_sequence.replace("L", "I", 1)   # Conservative mutation
            ]
            
            structure_predictions = []
            for i, variant in enumerate(designed_variants):
                variant_context = context.copy()
                variant_context["protein_sequence"] = variant
                variant_context["variant_name"] = f"variant_{i+1}"
                
                predictions = await self.agents["alphafold"].generate_hypotheses(variant_context)
                structure_predictions.append({
                    "variant": f"variant_{i+1}",
                    "sequence": variant,
                    "predictions": predictions
                })
            
            phase_results["structure_predictions"] = structure_predictions
        
        self.results["phase3_structure_prediction"] = phase_results
        logger.info(f"Phase 3 completed: {len(phase_results.get('structure_predictions', []))} variants analyzed")
    
    async def _phase4_dynamics_validation(self, context: Dict[str, Any]) -> None:
        """Phase 4: Validate designs with molecular dynamics."""
        phase_results = {}
        
        # Molecular dynamics validation
        if "md" in self.agents:
            logger.info("Running molecular dynamics validation...")
            
            # Add thermostability analysis context
            md_context = context.copy()
            md_context["analysis_type"] = "thermostability"
            md_context["temperature_range"] = [300, 400]  # K
            
            md_hypotheses = await self.agents["md"].generate_hypotheses(md_context)
            phase_results["md_validation"] = {
                "hypotheses": md_hypotheses,
                "num_hypotheses": len(md_hypotheses),
                "validation_approaches": [h["approach"] for h in md_hypotheses]
            }
        
        self.results["phase4_dynamics_validation"] = phase_results
        logger.info(f"Phase 4 completed: {len(phase_results)} validation approaches")
    
    async def _phase5_integration_consensus(self, context: Dict[str, Any]) -> None:
        """Phase 5: Integrate results and build consensus."""
        phase_results = {}
        
        # Collect all hypotheses
        all_hypotheses = []
        for phase_name, phase_data in self.results.items():
            for analysis_type, analysis_data in phase_data.items():
                if "hypotheses" in analysis_data:
                    for hypothesis in analysis_data["hypotheses"]:
                        hypothesis["source_phase"] = phase_name
                        hypothesis["source_analysis"] = analysis_type
                        all_hypotheses.append(hypothesis)
        
        # Rank hypotheses by consensus and feasibility
        ranked_hypotheses = self._rank_hypotheses_by_consensus(all_hypotheses)
        
        # Generate consensus recommendations
        consensus_recommendations = self._generate_consensus_recommendations(ranked_hypotheses)
        
        phase_results["integration_summary"] = {
            "total_hypotheses": len(all_hypotheses),
            "top_ranked_hypotheses": ranked_hypotheses[:5],
            "consensus_recommendations": consensus_recommendations,
            "tool_coverage": list(self.agents.keys())
        }
        
        self.results["phase5_integration_consensus"] = phase_results
        logger.info(f"Phase 5 completed: {len(all_hypotheses)} hypotheses integrated")
    
    def _rank_hypotheses_by_consensus(self, hypotheses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rank hypotheses by consensus across tools."""
        # Simple consensus scoring based on multiple factors
        for hypothesis in hypotheses:
            score = 0.0
            
            # Base feasibility score
            score += hypothesis.get("feasibility_score", 50.0)
            
            # Confidence bonus
            confidence = hypothesis.get("confidence", 0.5)
            score += confidence * 20
            
            # Multi-tool validation bonus
            if hypothesis.get("source_analysis") in ["esm_analysis", "md_validation"]:
                score += 10  # Bonus for experimentally validatable approaches
            
            # Strategy preference
            strategy = hypothesis.get("strategy", "")
            if "stability" in strategy or "optimization" in strategy:
                score += 15  # Bonus for stability-focused approaches
            
            hypothesis["consensus_score"] = score
        
        # Sort by consensus score
        return sorted(hypotheses, key=lambda h: h.get("consensus_score", 0), reverse=True)
    
    def _generate_consensus_recommendations(self, ranked_hypotheses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate consensus recommendations from ranked hypotheses."""
        recommendations = {
            "primary_strategy": "multi_tool_validation",
            "recommended_experiments": [],
            "computational_validation": [],
            "design_priorities": []
        }
        
        # Extract top recommendations
        for hypothesis in ranked_hypotheses[:3]:
            if "experimental_validation" in hypothesis:
                exp_val = hypothesis["experimental_validation"]
                recommendations["recommended_experiments"].extend([
                    f"{hypothesis['title']}: {method}" 
                    for method in exp_val.values() if isinstance(method, str)
                ])
            
            if "computational_validation" in hypothesis:
                comp_val = hypothesis["computational_validation"]
                recommendations["computational_validation"].extend([
                    f"{hypothesis['title']}: {method}"
                    for method in comp_val.values() if isinstance(method, str)
                ])
            
            # Extract design priorities
            strategy = hypothesis.get("strategy", "")
            if strategy not in recommendations["design_priorities"]:
                recommendations["design_priorities"].append(strategy)
        
        return recommendations
    
    async def _generate_comprehensive_report(self) -> Dict[str, Any]:
        """Generate comprehensive analysis report."""
        report = {
            "analysis_summary": {
                "target_protein": self.target_protein,
                "sequence_length": len(self.target_sequence),
                "tools_used": list(self.agents.keys()),
                "analysis_phases": len(self.results),
                "total_hypotheses": sum(
                    len(phase_data.get(analysis_type, {}).get("hypotheses", []))
                    for phase_data in self.results.values()
                    for analysis_type in phase_data.keys()
                    if "hypotheses" in phase_data.get(analysis_type, {})
                )
            },
            "phase_results": self.results,
            "recommendations": self.results.get("phase5_integration_consensus", {}).get("integration_summary", {}),
            "next_steps": {
                "immediate": [
                    "Validate top-ranked computational predictions",
                    "Design experimental validation protocols",
                    "Prioritize mutations for synthesis"
                ],
                "medium_term": [
                    "Synthesize and test top variants",
                    "Refine computational models based on results",
                    "Expand analysis to additional targets"
                ],
                "long_term": [
                    "Develop automated design-test-learn cycles",
                    "Integrate additional experimental data",
                    "Scale to protein family analysis"
                ]
            },
            "tool_performance": {
                agent_name: {
                    "status": "active" if agent_name in self.agents else "disabled",
                    "capabilities": self.agents[agent_name].get_capabilities() if agent_name in self.agents else None
                }
                for agent_name in ["rfdiffusion", "rosetta", "alphafold", "esm", "md"]
            }
        }
        
        return report
    
    async def save_results(self, output_dir: str = "comprehensive_analysis_results") -> None:
        """Save analysis results to files."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Save comprehensive report
        report = await self._generate_comprehensive_report()
        with open(output_path / "comprehensive_report.json", "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        # Save individual phase results
        for phase_name, phase_data in self.results.items():
            with open(output_path / f"{phase_name}.json", "w") as f:
                json.dump(phase_data, f, indent=2, default=str)
        
        logger.info(f"Results saved to {output_path}")
    
    async def cleanup(self) -> None:
        """Clean up all agents and resources."""
        for agent_name, agent in self.agents.items():
            try:
                await agent.cleanup()
                logger.info(f"Cleaned up {agent_name} agent")
            except Exception as e:
                logger.warning(f"Cleanup failed for {agent_name}: {e}")


async def main():
    """Main function to run comprehensive analysis."""
    analysis = ComprehensiveProteinAnalysis()
    
    try:
        # Initialize system
        if not await analysis.initialize_system():
            logger.error("System initialization failed")
            return
        
        # Run comprehensive analysis
        logger.info("Starting comprehensive multi-tool protein analysis...")
        results = await analysis.run_comprehensive_analysis()
        
        # Save results
        await analysis.save_results()
        
        # Print summary
        print("\n" + "="*80)
        print("COMPREHENSIVE MULTI-TOOL ANALYSIS COMPLETED")
        print("="*80)
        print(f"Target Protein: {analysis.target_protein}")
        print(f"Tools Used: {', '.join(analysis.agents.keys())}")
        print(f"Total Hypotheses Generated: {results['analysis_summary']['total_hypotheses']}")
        print(f"Analysis Phases: {results['analysis_summary']['analysis_phases']}")
        
        if "recommendations" in results:
            print("\nTop Recommendations:")
            for i, rec in enumerate(results["recommendations"].get("design_priorities", [])[:3], 1):
                print(f"  {i}. {rec}")
        
        print(f"\nDetailed results saved to: comprehensive_analysis_results/")
        print("="*80)
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
    
    finally:
        # Cleanup
        await analysis.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
