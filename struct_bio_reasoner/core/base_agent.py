"""
Base Agent for StructBioReasoner

This module provides the base agent class that all specialized agents inherit from.
It provides common functionality for hypothesis generation, validation, and resource management.
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all StructBioReasoner agents.
    
    This class provides common functionality that all agents need:
    - Initialization and configuration management
    - Hypothesis generation interface
    - Validation and cleanup methods
    - Resource management
    - Logging and error handling
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize base agent.
        
        Args:
            config: Agent configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Agent identification
        self.agent_id = config.get("agent_id", f"{self.__class__.__name__.lower()}_{uuid.uuid4().hex[:8]}")
        self.agent_type = "base"  # Override in subclasses
        self.specialization = "general"  # Override in subclasses
        
        # Agent state
        self.initialized = False
        self.active_tasks = {}
        self.resource_usage = {}
        
        # Configuration
        self.max_concurrent_tasks = config.get("max_concurrent_tasks", 5)
        self.timeout_seconds = config.get("timeout_seconds", 300)
        self.enable_caching = config.get("enable_caching", True)
        
        self.logger.info(f"Base agent {self.agent_id} initialized")
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the agent and its resources.
        
        This method should be implemented by subclasses to perform
        any necessary initialization (loading models, connecting to services, etc.).
        
        Returns:
            True if initialization successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def generate_hypotheses(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate hypotheses based on the given context.
        
        This is the main method that agents implement to generate
        protein engineering hypotheses.
        
        Args:
            context: Context information for hypothesis generation
            
        Returns:
            List of generated hypotheses
        """
        pass
    
    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get agent capabilities and metadata.
        
        Returns:
            Dictionary describing agent capabilities
        """
        pass
    
    async def validate_hypothesis(self, hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a hypothesis using agent-specific methods.
        
        Args:
            hypothesis: Hypothesis to validate
            
        Returns:
            Validation results
        """
        try:
            self.logger.info(f"Validating hypothesis: {hypothesis.get('id', 'unknown')}")
            
            # Basic validation
            validation_results = {
                "hypothesis_id": hypothesis.get("id"),
                "validation_status": "completed",
                "agent_id": self.agent_id,
                "timestamp": datetime.now().isoformat(),
                "basic_validation": {
                    "has_title": "title" in hypothesis,
                    "has_description": "description" in hypothesis,
                    "has_strategy": "strategy" in hypothesis,
                    "has_rationale": "rationale" in hypothesis
                },
                "recommendations": []
            }
            
            # Check for required fields
            required_fields = ["title", "description", "strategy", "rationale"]
            missing_fields = [field for field in required_fields if field not in hypothesis]
            
            if missing_fields:
                validation_results["basic_validation"]["missing_fields"] = missing_fields
                validation_results["recommendations"].append(f"Missing required fields: {', '.join(missing_fields)}")
            
            # Agent-specific validation can be added by subclasses
            agent_validation = await self._agent_specific_validation(hypothesis)
            validation_results["agent_validation"] = agent_validation
            
            return validation_results
            
        except Exception as e:
            self.logger.error(f"Hypothesis validation failed: {e}")
            return {
                "validation_status": "failed",
                "error": str(e),
                "agent_id": self.agent_id,
                "timestamp": datetime.now().isoformat()
            }
    
    async def _agent_specific_validation(self, hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform agent-specific validation.
        
        This method can be overridden by subclasses to add specific validation logic.
        
        Args:
            hypothesis: Hypothesis to validate
            
        Returns:
            Agent-specific validation results
        """
        return {"status": "no_specific_validation"}
    
    async def cleanup(self) -> None:
        """
        Clean up agent resources.
        
        This method should be called when the agent is no longer needed.
        Subclasses should override this to clean up specific resources.
        """
        try:
            # Cancel active tasks
            for task_id, task in self.active_tasks.items():
                if not task.done():
                    task.cancel()
                    self.logger.info(f"Cancelled task {task_id}")
            
            self.active_tasks.clear()
            self.initialized = False
            
            self.logger.info(f"Agent {self.agent_id} cleanup completed")
            
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")
    
    def is_ready(self) -> bool:
        """
        Check if agent is ready for operation.
        
        Returns:
            True if agent is initialized and ready
        """
        return self.initialized
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current agent status.
        
        Returns:
            Dictionary with agent status information
        """
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "specialization": self.specialization,
            "initialized": self.initialized,
            "active_tasks": len(self.active_tasks),
            "resource_usage": self.resource_usage
        }
    
    async def _execute_with_timeout(self, coro, timeout: Optional[float] = None) -> Any:
        """
        Execute a coroutine with timeout.
        
        Args:
            coro: Coroutine to execute
            timeout: Timeout in seconds (uses agent default if None)
            
        Returns:
            Coroutine result
            
        Raises:
            asyncio.TimeoutError: If operation times out
        """
        timeout = timeout or self.timeout_seconds
        return await asyncio.wait_for(coro, timeout=timeout)
    
    def _generate_task_id(self) -> str:
        """Generate unique task ID."""
        return f"{self.agent_id}_{uuid.uuid4().hex[:8]}"
    
    async def _track_task(self, task_id: str, coro) -> Any:
        """
        Track a task execution.
        
        Args:
            task_id: Unique task identifier
            coro: Coroutine to execute
            
        Returns:
            Task result
        """
        try:
            task = asyncio.create_task(coro)
            self.active_tasks[task_id] = task
            
            result = await task
            return result
            
        finally:
            # Clean up completed task
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]
    
    def _validate_context(self, context: Dict[str, Any]) -> bool:
        """
        Validate input context.
        
        Args:
            context: Context to validate
            
        Returns:
            True if context is valid
        """
        if not isinstance(context, dict):
            self.logger.error("Context must be a dictionary")
            return False
        
        # Basic context validation
        required_keys = ["target_protein", "protein_sequence"]
        for key in required_keys:
            if key not in context:
                self.logger.warning(f"Missing recommended context key: {key}")
        
        return True
    
    def _log_hypothesis_generation(self, context: Dict[str, Any], hypotheses: List[Dict[str, Any]]) -> None:
        """
        Log hypothesis generation results.
        
        Args:
            context: Generation context
            hypotheses: Generated hypotheses
        """
        target_protein = context.get("target_protein", "unknown")
        num_hypotheses = len(hypotheses)
        
        self.logger.info(f"Generated {num_hypotheses} hypotheses for {target_protein}")
        
        if hypotheses:
            strategies = [h.get("strategy", "unknown") for h in hypotheses]
            unique_strategies = len(set(strategies))
            self.logger.info(f"Unique strategies: {unique_strategies}")
    
    def __repr__(self) -> str:
        """String representation of agent."""
        return f"{self.__class__.__name__}(id={self.agent_id}, type={self.agent_type}, ready={self.initialized})"


class MockAgent(BaseAgent):
    """
    Mock agent for testing purposes.
    
    This agent provides mock functionality when real agents are not available
    or for testing scenarios.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize mock agent."""
        super().__init__(config)
        self.agent_type = "mock"
        self.specialization = "testing"
    
    async def initialize(self) -> bool:
        """Initialize mock agent."""
        self.initialized = True
        self.logger.info("Mock agent initialized")
        return True
    
    async def generate_hypotheses(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate mock hypotheses."""
        if not self._validate_context(context):
            return []
        
        target_protein = context.get("target_protein", "unknown_protein")
        
        # Generate mock hypotheses
        hypotheses = [
            {
                "id": f"mock_hypothesis_1_{uuid.uuid4().hex[:8]}",
                "title": f"Mock Stability Enhancement for {target_protein}",
                "description": "Mock hypothesis for testing agent functionality",
                "strategy": "mock_strategy",
                "approach": "computational_mock",
                "rationale": "Generated by mock agent for testing purposes",
                "confidence": 0.8,
                "feasibility_score": 75.0,
                "predicted_outcomes": {
                    "stability_improvement": "moderate",
                    "validation_methods": ["mock_validation"]
                },
                "experimental_validation": {
                    "recommended_experiments": "mock_experiments"
                },
                "computational_validation": {
                    "mock_analysis": "feasible"
                }
            },
            {
                "id": f"mock_hypothesis_2_{uuid.uuid4().hex[:8]}",
                "title": f"Mock Functional Enhancement for {target_protein}",
                "description": "Second mock hypothesis for comprehensive testing",
                "strategy": "mock_functional_strategy",
                "approach": "experimental_mock",
                "rationale": "Alternative mock approach for testing",
                "confidence": 0.7,
                "feasibility_score": 65.0,
                "predicted_outcomes": {
                    "functional_improvement": "significant",
                    "validation_methods": ["mock_functional_validation"]
                }
            }
        ]
        
        self._log_hypothesis_generation(context, hypotheses)
        return hypotheses
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get mock agent capabilities."""
        return {
            "agent_type": self.agent_type,
            "specialization": self.specialization,
            "supported_functions": ["mock_analysis", "testing"],
            "output_formats": ["mock_hypotheses"],
            "validation_methods": ["mock_validation"],
            "integration_tools": ["mock_tools"]
        }
