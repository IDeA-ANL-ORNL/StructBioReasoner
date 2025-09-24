"""
MCP-Enhanced Protein Analysis Agent

This agent integrates with MCP servers to provide comprehensive protein analysis
combining structure prediction, literature search, clinical trials, and variants.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from ...mcp import ProteinAnalysisMCPClient

logger = logging.getLogger(__name__)


class MCPProteinAgent:
    """Agent that uses MCP servers for comprehensive protein analysis."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.mcp_client = ProteinAnalysisMCPClient()
        self.servers_started = False
    
    async def initialize(self) -> bool:
        """Initialize the MCP client and start servers."""
        try:
            logger.info("Initializing MCP-Enhanced Protein Agent...")
            
            # Start MCP servers
            server_results = await self.mcp_client.start_all_servers()
            
            # Check if at least one server started successfully
            self.servers_started = any(server_results.values())
            
            if self.servers_started:
                logger.info(f"MCP servers started: {server_results}")
                return True
            else:
                logger.warning("No MCP servers could be started")
                return False
                
        except Exception as e:
            logger.error(f"Failed to initialize MCP agent: {e}")
            return False
    
    async def analyze_protein_comprehensive(self, protein_name: str, uniprot_id: str) -> Dict[str, Any]:
        """
        Perform comprehensive protein analysis using MCP servers.
        
        Args:
            protein_name: Name of the protein (e.g., "BRAF")
            uniprot_id: UniProt ID (e.g., "P15056")
            
        Returns:
            Comprehensive analysis results from multiple MCP servers
        """
        if not self.servers_started:
            logger.error("MCP servers not initialized")
            return {"error": "MCP servers not available"}
        
        logger.info(f"Starting comprehensive analysis for {protein_name} ({uniprot_id})")
        
        try:
            results = await self.mcp_client.comprehensive_protein_analysis(
                protein_name, uniprot_id
            )
            
            # Add analysis summary
            results["analysis_summary"] = self._generate_analysis_summary(results)
            
            return results
            
        except Exception as e:
            logger.error(f"Comprehensive analysis failed: {e}")
            return {"error": str(e)}
    
    async def get_structure_prediction(self, uniprot_id: str) -> Optional[Dict[str, Any]]:
        """Get AlphaFold structure prediction for a protein."""
        if not self.servers_started:
            return None
        
        try:
            return await self.mcp_client.get_alphafold_structure(uniprot_id)
        except Exception as e:
            logger.error(f"Structure prediction failed: {e}")
            return None
    
    async def search_protein_literature(self, protein_name: str, limit: int = 20) -> Optional[Dict[str, Any]]:
        """Search biomedical literature for a protein."""
        if not self.servers_started:
            return None
        
        try:
            return await self.mcp_client.search_literature(protein_name, limit)
        except Exception as e:
            logger.error(f"Literature search failed: {e}")
            return None
    
    async def find_clinical_trials(self, protein_name: str, limit: int = 20) -> Optional[Dict[str, Any]]:
        """Find clinical trials related to a protein."""
        if not self.servers_started:
            return None
        
        try:
            return await self.mcp_client.search_clinical_trials(protein_name, limit)
        except Exception as e:
            logger.error(f"Clinical trials search failed: {e}")
            return None
    
    async def get_genetic_variants(self, protein_name: str, limit: int = 20) -> Optional[Dict[str, Any]]:
        """Get genetic variants for a protein."""
        if not self.servers_started:
            return None
        
        try:
            return await self.mcp_client.search_variants(protein_name, limit)
        except Exception as e:
            logger.error(f"Variants search failed: {e}")
            return None
    
    def _generate_analysis_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a summary of the analysis results."""
        summary = {
            "protein_name": results.get("protein_name"),
            "uniprot_id": results.get("uniprot_id"),
            "data_sources_available": [],
            "key_findings": {},
            "recommendations": []
        }
        
        # Check available data sources
        status = results.get("analysis_status", {})
        for source, result in status.items():
            if result == "success":
                summary["data_sources_available"].append(source)
        
        # Extract key findings
        if results.get("alphafold_structure"):
            summary["key_findings"]["structure"] = "AlphaFold structure prediction available"
        
        if results.get("literature"):
            articles = results["literature"].get("articles", [])
            summary["key_findings"]["literature"] = f"{len(articles)} research articles found"
        
        if results.get("clinical_trials"):
            trials = results["clinical_trials"].get("trials", [])
            summary["key_findings"]["clinical_trials"] = f"{len(trials)} clinical trials identified"
        
        if results.get("variants"):
            variants = results["variants"].get("variants", [])
            summary["key_findings"]["variants"] = f"{len(variants)} genetic variants cataloged"
        
        # Generate recommendations
        if "alphafold" in summary["data_sources_available"]:
            summary["recommendations"].append("Use AlphaFold structure for molecular dynamics simulations")
        
        if "literature" in summary["data_sources_available"]:
            summary["recommendations"].append("Review recent literature for design insights")
        
        if "variants" in summary["data_sources_available"]:
            summary["recommendations"].append("Consider pathogenic variants for stability analysis")
        
        return summary
    
    async def generate_protein_engineering_strategy(self, protein_name: str, uniprot_id: str, 
                                                  engineering_goal: str) -> Dict[str, Any]:
        """
        Generate a protein engineering strategy based on MCP data.
        
        Args:
            protein_name: Name of the protein
            uniprot_id: UniProt ID
            engineering_goal: Goal (e.g., "improve thermostability", "enhance activity")
            
        Returns:
            Engineering strategy with recommendations
        """
        # Get comprehensive analysis
        analysis = await self.analyze_protein_comprehensive(protein_name, uniprot_id)
        
        if "error" in analysis:
            return analysis
        
        strategy = {
            "protein": protein_name,
            "goal": engineering_goal,
            "data_foundation": analysis["analysis_summary"],
            "engineering_approach": [],
            "experimental_validation": [],
            "literature_support": []
        }
        
        # Generate strategy based on available data
        if analysis.get("alphafold_structure"):
            strategy["engineering_approach"].append({
                "method": "Structure-based design",
                "description": "Use AlphaFold structure for rational mutagenesis",
                "tools": ["Rosetta", "FoldX", "Molecular dynamics"]
            })
        
        if analysis.get("variants"):
            strategy["engineering_approach"].append({
                "method": "Variant analysis",
                "description": "Analyze natural variants for stability insights",
                "tools": ["Variant effect prediction", "Conservation analysis"]
            })
        
        if analysis.get("literature"):
            strategy["literature_support"] = [
                "Review recent publications for engineering precedents",
                "Identify successful mutation strategies",
                "Understand structure-function relationships"
            ]
        
        # Add experimental validation steps
        strategy["experimental_validation"] = [
            "Computational screening of mutations",
            "Molecular dynamics simulations",
            "Experimental validation of top candidates",
            "Biochemical characterization"
        ]
        
        return strategy
    
    async def cleanup(self):
        """Clean up resources."""
        try:
            await self.mcp_client.stop_all_servers()
            logger.info("MCP servers stopped")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def __del__(self):
        """Cleanup when agent is destroyed."""
        try:
            # Run cleanup in event loop if available
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.cleanup())
            else:
                asyncio.run(self.cleanup())
        except:
            pass
