"""
MCP Client for StructBioReasoner

This module provides a client interface for communicating with MCP servers
including AlphaFold and BioMCP servers for enhanced protein engineering capabilities.
"""

import asyncio
import json
import subprocess
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    name: str
    command: List[str]
    description: str
    capabilities: List[str]


class MCPClient:
    """Client for communicating with MCP servers."""
    
    def __init__(self):
        self.servers = {}
        self.processes = {}
        self.server_configs = {
            "alphafold": MCPServerConfig(
                name="alphafold",
                command=["node", "/tmp/AlphaFold-MCP-Server/build/index.js"],
                description="AlphaFold protein structure prediction server",
                capabilities=[
                    "get_structure",
                    "get_confidence_scores", 
                    "search_structures",
                    "batch_structure_info",
                    "export_for_pymol"
                ]
            ),
            "biomcp": MCPServerConfig(
                name="biomcp",
                command=["biomcp", "run"],
                description="Biomedical research MCP server",
                capabilities=[
                    "search",
                    "fetch",
                    "article_searcher",
                    "trial_searcher",
                    "variant_searcher",
                    "gene_getter"
                ]
            )
        }
    
    async def start_server(self, server_name: str) -> bool:
        """Start an MCP server."""
        if server_name not in self.server_configs:
            logger.error(f"Unknown server: {server_name}")
            return False
        
        config = self.server_configs[server_name]
        
        try:
            # Check if AlphaFold server exists
            if server_name == "alphafold":
                alphafold_path = Path("/tmp/AlphaFold-MCP-Server/build/index.js")
                if not alphafold_path.exists():
                    logger.error("AlphaFold MCP server not found. Please install it first.")
                    return False
            
            process = subprocess.Popen(
                config.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.processes[server_name] = process
            logger.info(f"Started {server_name} MCP server")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start {server_name} server: {e}")
            return False
    
    async def stop_server(self, server_name: str):
        """Stop an MCP server."""
        if server_name in self.processes:
            try:
                process = self.processes[server_name]
                process.terminate()
                process.wait(timeout=5)
                del self.processes[server_name]
                logger.info(f"Stopped {server_name} server")
            except Exception as e:
                logger.error(f"Error stopping {server_name} server: {e}")
    
    async def call_tool(self, server_name: str, tool_name: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Call a tool on an MCP server."""
        if server_name not in self.processes:
            logger.error(f"Server {server_name} not running")
            return None
        
        process = self.processes[server_name]
        
        # Create MCP request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": params
            }
        }
        
        try:
            # Send request
            request_json = json.dumps(request) + "\n"
            process.stdin.write(request_json)
            process.stdin.flush()
            
            # Read response
            response_line = process.stdout.readline()
            if response_line:
                response = json.loads(response_line)
                if "result" in response:
                    return response["result"]
                elif "error" in response:
                    logger.error(f"MCP error: {response['error']}")
                    return None
            
        except Exception as e:
            logger.error(f"Error calling {tool_name} on {server_name}: {e}")
        
        return None
    
    async def get_server_capabilities(self, server_name: str) -> List[str]:
        """Get the capabilities of an MCP server."""
        if server_name in self.server_configs:
            return self.server_configs[server_name].capabilities
        return []
    
    async def list_available_servers(self) -> Dict[str, MCPServerConfig]:
        """List all available MCP servers."""
        return self.server_configs
    
    async def start_all_servers(self) -> Dict[str, bool]:
        """Start all available MCP servers."""
        results = {}
        for server_name in self.server_configs:
            results[server_name] = await self.start_server(server_name)
        return results
    
    async def stop_all_servers(self):
        """Stop all running MCP servers."""
        for server_name in list(self.processes.keys()):
            await self.stop_server(server_name)
    
    def __del__(self):
        """Cleanup when client is destroyed."""
        # Stop all servers synchronously
        for server_name, process in self.processes.items():
            try:
                process.terminate()
                process.wait(timeout=2)
            except:
                pass


class ProteinAnalysisMCPClient(MCPClient):
    """Specialized MCP client for protein analysis workflows."""
    
    async def get_alphafold_structure(self, uniprot_id: str, format: str = "json") -> Optional[Dict[str, Any]]:
        """Get AlphaFold structure prediction."""
        return await self.call_tool(
            "alphafold",
            "get_structure",
            {"uniprotId": uniprot_id, "format": format}
        )
    
    async def search_literature(self, gene: str, limit: int = 20) -> Optional[Dict[str, Any]]:
        """Search biomedical literature."""
        return await self.call_tool(
            "biomcp",
            "search",
            {"query": f"gene:{gene}", "domain": "article"}
        )
    
    async def search_clinical_trials(self, gene: str, limit: int = 20) -> Optional[Dict[str, Any]]:
        """Search clinical trials."""
        return await self.call_tool(
            "biomcp", 
            "search",
            {"query": f"gene:{gene}", "domain": "trial"}
        )
    
    async def search_variants(self, gene: str, limit: int = 20) -> Optional[Dict[str, Any]]:
        """Search genetic variants."""
        return await self.call_tool(
            "biomcp",
            "search", 
            {"query": f"gene:{gene}", "domain": "variant"}
        )
    
    async def comprehensive_protein_analysis(self, protein_name: str, uniprot_id: str) -> Dict[str, Any]:
        """Perform comprehensive protein analysis using multiple MCP servers."""
        results = {
            "protein_name": protein_name,
            "uniprot_id": uniprot_id,
            "alphafold_structure": None,
            "literature": None,
            "clinical_trials": None,
            "variants": None,
            "analysis_status": {}
        }
        
        # Get AlphaFold structure
        try:
            results["alphafold_structure"] = await self.get_alphafold_structure(uniprot_id)
            results["analysis_status"]["alphafold"] = "success" if results["alphafold_structure"] else "failed"
        except Exception as e:
            logger.error(f"AlphaFold analysis failed: {e}")
            results["analysis_status"]["alphafold"] = "error"
        
        # Search literature
        try:
            results["literature"] = await self.search_literature(protein_name)
            results["analysis_status"]["literature"] = "success" if results["literature"] else "failed"
        except Exception as e:
            logger.error(f"Literature search failed: {e}")
            results["analysis_status"]["literature"] = "error"
        
        # Search clinical trials
        try:
            results["clinical_trials"] = await self.search_clinical_trials(protein_name)
            results["analysis_status"]["clinical_trials"] = "success" if results["clinical_trials"] else "failed"
        except Exception as e:
            logger.error(f"Clinical trials search failed: {e}")
            results["analysis_status"]["clinical_trials"] = "error"
        
        # Search variants
        try:
            results["variants"] = await self.search_variants(protein_name)
            results["analysis_status"]["variants"] = "success" if results["variants"] else "failed"
        except Exception as e:
            logger.error(f"Variants search failed: {e}")
            results["analysis_status"]["variants"] = "error"
        
        return results
