"""
MCP Integration Module for StructBioReasoner

Provides both:
- An MCP **server** that exposes StructBioReasoner tools (skills, reasoning,
  directives) to any MCP client over stdio transport.
- An MCP **client** for calling external MCP servers (AlphaFold, BioMCP, etc.).
"""

from .mcp_client import MCPClient, MCPServerConfig, ProteinAnalysisMCPClient
from .server import create_server

__all__ = [
    "MCPClient",
    "ProteinAnalysisMCPClient",
    "MCPServerConfig",
    "create_server",
]
