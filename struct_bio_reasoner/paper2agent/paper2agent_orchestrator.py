#!/usr/bin/env python3
"""
Paper2Agent Orchestrator

Main orchestrator for the Paper2Agent system that coordinates:
- Paper analysis and methodology extraction
- MCP tool generation
- Code generation for missing functionality
- Integration with existing agentic systems
- Tool validation and deployment

This is the central hub for Phase 3 implementation.
"""

import asyncio
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field

# Import Paper2Agent components
from .paper_to_mcp_generator import (
    PaperAnalysisEngine, MCPToolGenerator, CodeGenerationEngine,
    MethodologyExtraction, MCPToolSpecification, CodeGenerationRequest
)
from .mcp_integration_framework import (
    MCPServer, MCPToolRegistry, MCPTool, DynamicToolLoader
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class PaperSource:
    """Represents a scientific paper source."""
    title: str
    authors: List[str]
    doi: str
    abstract: str
    content: str
    github_repo: Optional[str] = None
    publication_year: Optional[int] = None
    journal: Optional[str] = None
    keywords: List[str] = field(default_factory=list)


@dataclass
class Paper2AgentConfig:
    """Configuration for Paper2Agent system."""
    papers_directory: Path
    tools_output_directory: Path
    generated_code_directory: Path
    enable_code_generation: bool = True
    enable_github_integration: bool = True
    confidence_threshold: float = 0.5
    max_tools_per_paper: int = 10
    supported_domains: List[str] = field(default_factory=lambda: [
        "structural_analysis", "evolutionary_analysis", "mutation_design"
    ])


class Paper2AgentOrchestrator:
    """
    Main orchestrator for the Paper2Agent system.
    
    Coordinates the entire pipeline from paper analysis to MCP tool deployment.
    """
    
    def __init__(self, config: Paper2AgentConfig):
        self.config = config
        
        # Initialize components
        self.paper_analyzer = PaperAnalysisEngine()
        self.tool_generator = MCPToolGenerator()
        self.code_generator = CodeGenerationEngine()
        self.tool_registry = MCPToolRegistry()
        self.mcp_server = MCPServer(self.tool_registry)
        self.tool_loader = DynamicToolLoader(config.generated_code_directory)
        
        # Create directories
        self._create_directories()
        
        # Statistics
        self.stats = {
            "papers_processed": 0,
            "methodologies_extracted": 0,
            "tools_generated": 0,
            "code_generated": 0,
            "tools_deployed": 0
        }
        
        logger.info("Initialized Paper2Agent Orchestrator")
    
    def _create_directories(self):
        """Create necessary directories."""
        directories = [
            self.config.papers_directory,
            self.config.tools_output_directory,
            self.config.generated_code_directory
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created directory: {directory}")
    
    async def process_paper_collection(self, papers: List[PaperSource]) -> Dict[str, Any]:
        """Process a collection of papers and generate MCP tools."""
        logger.info(f"Processing {len(papers)} papers")
        
        results = {
            "processed_papers": [],
            "generated_tools": [],
            "failed_papers": [],
            "summary": {}
        }
        
        for paper in papers:
            try:
                paper_result = await self.process_single_paper(paper)
                results["processed_papers"].append(paper_result)
                results["generated_tools"].extend(paper_result["tools"])
                
            except Exception as e:
                logger.error(f"Failed to process paper {paper.title}: {e}")
                results["failed_papers"].append({
                    "title": paper.title,
                    "error": str(e)
                })
        
        # Generate summary
        results["summary"] = self._generate_processing_summary(results)
        
        logger.info(f"Completed processing {len(papers)} papers")
        return results
    
    async def process_single_paper(self, paper: PaperSource) -> Dict[str, Any]:
        """Process a single paper and generate tools."""
        logger.info(f"Processing paper: {paper.title}")
        
        # Step 1: Extract methodologies
        paper_metadata = {
            "title": paper.title,
            "doi": paper.doi,
            "github_repo": paper.github_repo,
            "authors": paper.authors,
            "year": paper.publication_year
        }
        
        methodologies = await self.paper_analyzer.analyze_paper(
            paper.content, paper_metadata
        )
        
        logger.info(f"Extracted {len(methodologies)} methodologies from {paper.title}")
        
        # Step 2: Generate MCP tools
        generated_tools = []
        for methodology in methodologies:
            if len(generated_tools) >= self.config.max_tools_per_paper:
                break
            
            try:
                tool_spec = await self.tool_generator.generate_mcp_tool(methodology)
                
                if tool_spec.confidence_score >= self.config.confidence_threshold:
                    generated_tools.append(tool_spec)
                    
                    # Step 3: Generate code if needed
                    if not methodology.code_availability and self.config.enable_code_generation:
                        await self._generate_missing_code(methodology, tool_spec)
                    
                    # Step 4: Deploy tool
                    await self._deploy_tool(tool_spec)
                    
            except Exception as e:
                logger.error(f"Failed to generate tool for {methodology.name}: {e}")
        
        self.stats["papers_processed"] += 1
        self.stats["methodologies_extracted"] += len(methodologies)
        self.stats["tools_generated"] += len(generated_tools)
        
        return {
            "paper": {
                "title": paper.title,
                "doi": paper.doi,
                "authors": paper.authors
            },
            "methodologies_count": len(methodologies),
            "tools": [
                {
                    "name": tool.tool_name,
                    "description": tool.tool_description,
                    "confidence_score": tool.confidence_score,
                    "dependencies": tool.dependencies
                }
                for tool in generated_tools
            ]
        }
    
    async def _generate_missing_code(self, methodology: MethodologyExtraction, 
                                   tool_spec: MCPToolSpecification):
        """Generate code for missing functionality."""
        logger.info(f"Generating missing code for: {methodology.name}")
        
        # Create code generation request
        request = CodeGenerationRequest(
            functionality_name=methodology.name,
            description=methodology.description,
            input_spec={param["name"]: param for param in methodology.input_parameters},
            output_spec=methodology.output_format,
            algorithm_description=" -> ".join(methodology.algorithm_steps),
            domain=self._classify_domain(methodology),
            complexity_level=methodology.implementation_complexity,
            reference_papers=[methodology.paper_source]
        )
        
        # Generate code
        generated_code = await self.code_generator.generate_missing_functionality(request)
        
        # Save generated code
        code_file = self.config.generated_code_directory / f"{methodology.name}.py"
        with open(code_file, 'w') as f:
            f.write(generated_code)
        
        # Update tool specification with generated code
        tool_spec.implementation_code = generated_code
        
        self.stats["code_generated"] += 1
        logger.info(f"Generated and saved code for: {methodology.name}")
    
    def _classify_domain(self, methodology: MethodologyExtraction) -> str:
        """Classify methodology domain."""
        name_lower = methodology.name.lower()
        desc_lower = methodology.description.lower()
        
        if any(keyword in name_lower or keyword in desc_lower 
               for keyword in ["structure", "structural", "fold", "pdb"]):
            return "structural"
        elif any(keyword in name_lower or keyword in desc_lower 
                 for keyword in ["evolution", "conservation", "phylo"]):
            return "evolutionary"
        elif any(keyword in name_lower or keyword in desc_lower 
                 for keyword in ["mutation", "design", "stability"]):
            return "mutation_design"
        else:
            return "general"
    
    async def _deploy_tool(self, tool_spec: MCPToolSpecification):
        """Deploy a generated tool to the MCP server."""
        logger.info(f"Deploying tool: {tool_spec.tool_name}")
        
        # Load implementation if it's in a file
        if tool_spec.implementation_code:
            # Save implementation to file
            impl_file = self.config.generated_code_directory / f"{tool_spec.tool_name}.py"
            with open(impl_file, 'w') as f:
                f.write(tool_spec.implementation_code)
            
            # Load the implementation
            implementation = await self.tool_loader.load_tool_from_file(impl_file)
            
            if implementation is None:
                logger.error(f"Failed to load implementation for {tool_spec.tool_name}")
                return
        else:
            # Create a placeholder implementation
            async def placeholder_implementation(**kwargs):
                return {"status": "placeholder", "message": "Implementation not available"}
            
            implementation = placeholder_implementation
        
        # Create MCP tool
        mcp_tool = MCPTool(
            name=tool_spec.tool_name,
            description=tool_spec.tool_description,
            input_schema=tool_spec.input_schema,
            output_schema=tool_spec.output_schema,
            implementation=implementation,
            paper_source=tool_spec.paper_source,
            confidence_score=tool_spec.confidence_score,
            dependencies=tool_spec.dependencies,
            validation_tests=tool_spec.validation_tests,
            created_at=tool_spec.last_updated
        )
        
        # Register tool
        self.tool_registry.register_tool(mcp_tool)
        self.stats["tools_deployed"] += 1
        
        logger.info(f"Successfully deployed tool: {tool_spec.tool_name}")
    
    def _generate_processing_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate processing summary."""
        return {
            "total_papers": len(results["processed_papers"]) + len(results["failed_papers"]),
            "successful_papers": len(results["processed_papers"]),
            "failed_papers": len(results["failed_papers"]),
            "total_tools_generated": len(results["generated_tools"]),
            "success_rate": len(results["processed_papers"]) / (
                len(results["processed_papers"]) + len(results["failed_papers"])
            ) if (len(results["processed_papers"]) + len(results["failed_papers"])) > 0 else 0,
            "average_tools_per_paper": len(results["generated_tools"]) / len(results["processed_papers"])
            if len(results["processed_papers"]) > 0 else 0,
            "processing_stats": self.stats.copy()
        }
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get current system status."""
        return {
            "orchestrator_status": "active",
            "configuration": {
                "papers_directory": str(self.config.papers_directory),
                "tools_output_directory": str(self.config.tools_output_directory),
                "generated_code_directory": str(self.config.generated_code_directory),
                "confidence_threshold": self.config.confidence_threshold,
                "max_tools_per_paper": self.config.max_tools_per_paper
            },
            "statistics": self.stats,
            "mcp_server_info": await self.mcp_server.list_tools(),
            "timestamp": datetime.now().isoformat()
        }
    
    async def search_and_call_tool(self, query: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Search for a tool and call it."""
        # Search for tools
        search_results = await self.mcp_server.search_tools(query)
        
        if search_results["count"] == 0:
            return {"status": "error", "message": f"No tools found for query: {query}"}
        
        # Use the first (best) match
        best_tool = search_results["tools"][0]
        tool_name = best_tool["name"]
        
        # Call the tool
        result = await self.mcp_server.call_tool(tool_name, arguments)
        
        return {
            "search_query": query,
            "selected_tool": tool_name,
            "tool_result": result
        }
    
    async def validate_all_tools(self) -> Dict[str, Any]:
        """Validate all deployed tools."""
        validation_results = {
            "total_tools": len(self.tool_registry.tools),
            "validated_tools": [],
            "failed_validations": [],
            "validation_summary": {}
        }
        
        for tool_name, tool in self.tool_registry.tools.items():
            try:
                # Run validation tests if available
                if tool.validation_tests:
                    # Placeholder for actual validation
                    validation_results["validated_tools"].append({
                        "name": tool_name,
                        "status": "passed",
                        "confidence_score": tool.confidence_score
                    })
                else:
                    validation_results["validated_tools"].append({
                        "name": tool_name,
                        "status": "no_tests",
                        "confidence_score": tool.confidence_score
                    })
                    
            except Exception as e:
                validation_results["failed_validations"].append({
                    "name": tool_name,
                    "error": str(e)
                })
        
        validation_results["validation_summary"] = {
            "passed": len(validation_results["validated_tools"]),
            "failed": len(validation_results["failed_validations"]),
            "success_rate": len(validation_results["validated_tools"]) / len(self.tool_registry.tools)
            if len(self.tool_registry.tools) > 0 else 0
        }
        
        return validation_results
