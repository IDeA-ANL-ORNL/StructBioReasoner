#!/usr/bin/env python3
"""
MCP Integration Framework for Paper2Agent

This module provides the Model Context Protocol (MCP) integration framework
for converting Paper2Agent generated tools into callable MCP services.

Key Features:
- MCP server implementation for generated tools
- Tool registration and discovery
- Dynamic tool loading and execution
- Validation and error handling
- Integration with existing agentic systems
"""

import asyncio
import logging
import json
import inspect
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, field
import importlib.util
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """Represents an MCP tool generated from a paper."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    implementation: Callable
    paper_source: str
    confidence_score: float
    dependencies: List[str]
    validation_tests: List[str]
    created_at: datetime
    last_used: Optional[datetime] = None
    usage_count: int = 0
    success_rate: float = 1.0


@dataclass
class MCPToolRegistry:
    """Registry for managing MCP tools."""
    tools: Dict[str, MCPTool] = field(default_factory=dict)
    categories: Dict[str, List[str]] = field(default_factory=dict)
    paper_index: Dict[str, List[str]] = field(default_factory=dict)
    
    def register_tool(self, tool: MCPTool):
        """Register a new MCP tool."""
        self.tools[tool.name] = tool
        
        # Categorize tool
        category = self._determine_category(tool)
        if category not in self.categories:
            self.categories[category] = []
        self.categories[category].append(tool.name)
        
        # Index by paper
        if tool.paper_source not in self.paper_index:
            self.paper_index[tool.paper_source] = []
        self.paper_index[tool.paper_source].append(tool.name)
        
        logger.info(f"Registered MCP tool: {tool.name} (category: {category})")
    
    def _determine_category(self, tool: MCPTool) -> str:
        """Determine tool category based on name and description."""
        name_lower = tool.name.lower()
        desc_lower = tool.description.lower()
        
        if any(keyword in name_lower or keyword in desc_lower 
               for keyword in ["structure", "structural", "fold", "pdb"]):
            return "structural_analysis"
        elif any(keyword in name_lower or keyword in desc_lower 
                 for keyword in ["evolution", "conservation", "phylo"]):
            return "evolutionary_analysis"
        elif any(keyword in name_lower or keyword in desc_lower 
                 for keyword in ["mutation", "design", "stability"]):
            return "mutation_design"
        else:
            return "general"
    
    def get_tools_by_category(self, category: str) -> List[MCPTool]:
        """Get all tools in a specific category."""
        tool_names = self.categories.get(category, [])
        return [self.tools[name] for name in tool_names]
    
    def get_tools_by_paper(self, paper_source: str) -> List[MCPTool]:
        """Get all tools from a specific paper."""
        tool_names = self.paper_index.get(paper_source, [])
        return [self.tools[name] for name in tool_names]
    
    def search_tools(self, query: str) -> List[MCPTool]:
        """Search tools by name or description."""
        query_lower = query.lower()
        matching_tools = []
        
        for tool in self.tools.values():
            if (query_lower in tool.name.lower() or 
                query_lower in tool.description.lower()):
                matching_tools.append(tool)
        
        return matching_tools


class MCPServer:
    """MCP Server for Paper2Agent generated tools."""
    
    def __init__(self, registry: MCPToolRegistry):
        self.registry = registry
        self.server_info = {
            "name": "Paper2Agent MCP Server",
            "version": "1.0.0",
            "description": "MCP server for literature-derived protein engineering tools"
        }
        
        logger.info("Initialized Paper2Agent MCP Server")
    
    async def list_tools(self) -> Dict[str, Any]:
        """List all available tools."""
        tools_info = []
        
        for tool in self.registry.tools.values():
            tools_info.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
                "paper_source": tool.paper_source,
                "confidence_score": tool.confidence_score,
                "usage_count": tool.usage_count,
                "success_rate": tool.success_rate
            })
        
        return {
            "server_info": self.server_info,
            "tools": tools_info,
            "total_tools": len(tools_info),
            "categories": list(self.registry.categories.keys())
        }
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a specific tool with given arguments."""
        if tool_name not in self.registry.tools:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        tool = self.registry.tools[tool_name]
        
        try:
            # Validate inputs
            self._validate_tool_inputs(tool, arguments)
            
            # Execute tool
            start_time = datetime.now()
            result = await tool.implementation(**arguments)
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # Update usage statistics
            tool.last_used = datetime.now()
            tool.usage_count += 1
            
            # Validate outputs
            self._validate_tool_outputs(tool, result)
            
            return {
                "status": "success",
                "tool_name": tool_name,
                "result": result,
                "execution_time": execution_time,
                "paper_source": tool.paper_source,
                "confidence_score": tool.confidence_score
            }
            
        except Exception as e:
            # Update failure statistics
            tool.success_rate = (tool.success_rate * tool.usage_count) / (tool.usage_count + 1)
            tool.usage_count += 1
            
            logger.error(f"Error executing tool {tool_name}: {e}")
            
            return {
                "status": "error",
                "tool_name": tool_name,
                "error": str(e),
                "paper_source": tool.paper_source
            }
    
    def _validate_tool_inputs(self, tool: MCPTool, arguments: Dict[str, Any]):
        """Validate tool inputs against schema."""
        schema = tool.input_schema
        required_fields = schema.get("required", [])
        
        # Check required fields
        for field in required_fields:
            if field not in arguments:
                raise ValueError(f"Required field '{field}' missing")
        
        # Type validation would go here in a full implementation
        logger.debug(f"Input validation passed for tool: {tool.name}")
    
    def _validate_tool_outputs(self, tool: MCPTool, result: Any):
        """Validate tool outputs against schema."""
        # Output validation would go here in a full implementation
        logger.debug(f"Output validation passed for tool: {tool.name}")
    
    async def get_tool_info(self, tool_name: str) -> Dict[str, Any]:
        """Get detailed information about a specific tool."""
        if tool_name not in self.registry.tools:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        tool = self.registry.tools[tool_name]
        
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
            "paper_source": tool.paper_source,
            "confidence_score": tool.confidence_score,
            "dependencies": tool.dependencies,
            "validation_tests": tool.validation_tests,
            "created_at": tool.created_at.isoformat(),
            "last_used": tool.last_used.isoformat() if tool.last_used else None,
            "usage_count": tool.usage_count,
            "success_rate": tool.success_rate
        }
    
    async def get_tools_by_category(self, category: str) -> Dict[str, Any]:
        """Get tools filtered by category."""
        tools = self.registry.get_tools_by_category(category)
        
        return {
            "category": category,
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "confidence_score": tool.confidence_score,
                    "paper_source": tool.paper_source
                }
                for tool in tools
            ],
            "count": len(tools)
        }
    
    async def search_tools(self, query: str) -> Dict[str, Any]:
        """Search tools by query."""
        tools = self.registry.search_tools(query)
        
        return {
            "query": query,
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "confidence_score": tool.confidence_score,
                    "paper_source": tool.paper_source
                }
                for tool in tools
            ],
            "count": len(tools)
        }


class DynamicToolLoader:
    """Loader for dynamically loading generated tools."""
    
    def __init__(self, tools_directory: Path):
        self.tools_directory = Path(tools_directory)
        self.loaded_modules = {}
        
        logger.info(f"Initialized Dynamic Tool Loader for: {tools_directory}")
    
    async def load_tool_from_file(self, file_path: Path) -> Optional[Callable]:
        """Load a tool implementation from a Python file."""
        try:
            # Create module spec
            module_name = file_path.stem
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            
            if spec is None or spec.loader is None:
                logger.error(f"Could not create module spec for {file_path}")
                return None
            
            # Load module
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # Find the main function (assume it's the async function with most parameters)
            functions = [obj for name, obj in inspect.getmembers(module, inspect.iscoroutinefunction)]
            
            if not functions:
                logger.error(f"No async functions found in {file_path}")
                return None
            
            # Select the main function (heuristic: most parameters)
            main_function = max(functions, key=lambda f: len(inspect.signature(f).parameters))
            
            self.loaded_modules[module_name] = module
            logger.info(f"Successfully loaded tool from {file_path}")
            
            return main_function
            
        except Exception as e:
            logger.error(f"Error loading tool from {file_path}: {e}")
            return None
    
    async def scan_and_load_tools(self) -> List[Callable]:
        """Scan directory and load all tool implementations."""
        tools = []
        
        if not self.tools_directory.exists():
            logger.warning(f"Tools directory does not exist: {self.tools_directory}")
            return tools
        
        for file_path in self.tools_directory.glob("*.py"):
            if file_path.name.startswith("__"):
                continue
            
            tool = await self.load_tool_from_file(file_path)
            if tool:
                tools.append(tool)
        
        logger.info(f"Loaded {len(tools)} tools from {self.tools_directory}")
        return tools
    
    def reload_tool(self, module_name: str) -> Optional[Callable]:
        """Reload a specific tool module."""
        if module_name in self.loaded_modules:
            try:
                importlib.reload(self.loaded_modules[module_name])
                logger.info(f"Reloaded tool module: {module_name}")
                return True
            except Exception as e:
                logger.error(f"Error reloading module {module_name}: {e}")
                return False
        else:
            logger.warning(f"Module {module_name} not found in loaded modules")
            return False
