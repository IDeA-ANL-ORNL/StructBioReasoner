"""
MCP Integration Module for StructBioReasoner

This module provides Model Context Protocol (MCP) integration capabilities
for enhanced protein engineering workflows using external MCP servers.
"""

from .mcp_client import MCPClient, ProteinAnalysisMCPClient, MCPServerConfig

__all__ = [
    "MCPClient",
    "ProteinAnalysisMCPClient", 
    "MCPServerConfig"
]
