"""
Base Role Classes for Role-based Agentic System

This module defines the base classes for expert and critic roles in the
StructBioReasoner agentic workflow system.
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class RoleType(Enum):
    """Types of roles in the agentic system."""
    EXPERT = "expert"
    CRITIC = "critic"
    ORCHESTRATOR = "orchestrator"


class CommunicationProtocol(Enum):
    """Communication protocols between agents."""
    DIRECT = "direct"
    BROADCAST = "broadcast"
    HIERARCHICAL = "hierarchical"


class BaseRole(ABC):
    """
    Abstract base class for all roles in the agentic system.
    
    This class provides common functionality for both expert and critic roles:
    - Role identification and metadata
    - Communication protocols
    - Performance tracking
    - State management
    """
    
    def __init__(self, 
                 role_name: str,
                 role_type: RoleType,
                 config: Dict[str, Any]):
        """
        Initialize base role.
        
        Args:
            role_name: Human-readable name for this role
            role_type: Type of role (expert, critic, orchestrator)
            config: Role configuration dictionary
        """
        self.role_name = role_name
        self.role_type = role_type
        self.config = config
        self.logger = logging.getLogger(f"{self.__class__.__name__}")
        
        # Role identification
        self.role_id = config.get("role_id", f"{role_name}_{uuid.uuid4().hex[:8]}")
        self.specialization = config.get("specialization", "general")
        self.expertise_level = config.get("expertise_level", "intermediate")
        
        # Communication settings
        self.communication_protocol = CommunicationProtocol(
            config.get("communication_protocol", "direct")
        )
        self.max_concurrent_interactions = config.get("max_concurrent_interactions", 3)
        
        # Performance tracking
        self.performance_history = []
        self.interaction_count = 0
        self.success_rate = 0.0
        self.last_active = None
        
        # State management
        self.initialized = False
        self.active_tasks = {}
        self.peer_roles = {}  # Other roles this role can communicate with
        
        self.logger.info(f"Base role {self.role_id} ({self.role_type.value}) initialized")
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the role and its resources.
        
        Returns:
            True if initialization successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a request from another role or the orchestrator.
        
        Args:
            request: Request data including task type, parameters, and context
            
        Returns:
            Response data with results, status, and metadata
        """
        pass
    
    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get role capabilities and metadata.
        
        Returns:
            Dictionary describing role capabilities, expertise, and limitations
        """
        pass
    
    async def communicate_with_role(self, 
                                  target_role_id: str, 
                                  message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a message to another role.
        
        Args:
            target_role_id: ID of the target role
            message: Message data to send
            
        Returns:
            Response from the target role
        """
        if target_role_id not in self.peer_roles:
            raise ValueError(f"Unknown target role: {target_role_id}")
        
        target_role = self.peer_roles[target_role_id]
        
        # Add communication metadata
        message.update({
            "sender_id": self.role_id,
            "sender_type": self.role_type.value,
            "timestamp": datetime.now().isoformat(),
            "communication_protocol": self.communication_protocol.value
        })
        
        try:
            response = await target_role.process_request(message)
            self.interaction_count += 1
            self.last_active = datetime.now()
            return response
            
        except Exception as e:
            self.logger.error(f"Communication failed with {target_role_id}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def register_peer_role(self, role_id: str, role_instance: 'BaseRole'):
        """
        Register a peer role for communication.
        
        Args:
            role_id: ID of the peer role
            role_instance: Instance of the peer role
        """
        self.peer_roles[role_id] = role_instance
        self.logger.info(f"Registered peer role: {role_id}")
    
    def update_performance(self, task_result: Dict[str, Any]):
        """
        Update performance metrics based on task results.
        
        Args:
            task_result: Results from a completed task
        """
        self.performance_history.append({
            "timestamp": datetime.now().isoformat(),
            "task_type": task_result.get("task_type", "unknown"),
            "success": task_result.get("success", False),
            "execution_time": task_result.get("execution_time", 0),
            "quality_score": task_result.get("quality_score", 0.0)
        })
        
        # Calculate success rate
        if self.performance_history:
            successes = sum(1 for h in self.performance_history if h["success"])
            self.success_rate = successes / len(self.performance_history)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current role status and performance metrics.
        
        Returns:
            Dictionary with role status information
        """
        return {
            "role_id": self.role_id,
            "role_name": self.role_name,
            "role_type": self.role_type.value,
            "specialization": self.specialization,
            "expertise_level": self.expertise_level,
            "initialized": self.initialized,
            "active_tasks": len(self.active_tasks),
            "interaction_count": self.interaction_count,
            "success_rate": self.success_rate,
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "peer_roles": list(self.peer_roles.keys())
        }
    
    async def cleanup(self):
        """Clean up role resources."""
        self.active_tasks.clear()
        self.logger.info(f"Role {self.role_id} cleaned up")


class ExpertRole(BaseRole):
    """
    Base class for expert roles that perform specialized tasks.
    
    Expert roles are responsible for:
    - Executing domain-specific tasks
    - Providing expert analysis and recommendations
    - Maintaining domain knowledge and best practices
    - Collaborating with other experts and responding to critics
    """
    
    def __init__(self, role_name: str, config: Dict[str, Any]):
        """Initialize expert role."""
        super().__init__(role_name, RoleType.EXPERT, config)
        
        # Expert-specific attributes
        self.domain_expertise = config.get("domain_expertise", [])
        self.confidence_threshold = config.get("confidence_threshold", 0.7)
        self.quality_standards = config.get("quality_standards", {})
        
        # Task execution settings
        self.max_retry_attempts = config.get("max_retry_attempts", 3)
        self.timeout_seconds = config.get("timeout_seconds", 300)
    
    @abstractmethod
    async def execute_expert_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a domain-specific expert task.
        
        Args:
            task: Task specification with parameters and requirements
            
        Returns:
            Task results with analysis, recommendations, and confidence scores
        """
        pass
    
    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process request from another role or orchestrator."""
        request_type = request.get("type", "unknown")
        
        if request_type == "expert_task":
            return await self.execute_expert_task(request.get("task", {}))
        elif request_type == "status_check":
            return self.get_status()
        elif request_type == "capability_query":
            return self.get_capabilities()
        else:
            return {
                "status": "error",
                "error": f"Unknown request type: {request_type}",
                "timestamp": datetime.now().isoformat()
            }


class CriticRole(BaseRole):
    """
    Base class for critic roles that evaluate and provide feedback.
    
    Critic roles are responsible for:
    - Evaluating expert performance and outputs
    - Providing constructive feedback and improvement suggestions
    - Monitoring quality standards and best practices
    - Facilitating continuous improvement in the agentic system
    """
    
    def __init__(self, role_name: str, config: Dict[str, Any]):
        """Initialize critic role."""
        super().__init__(role_name, RoleType.CRITIC, config)
        
        # Critic-specific attributes
        self.evaluation_criteria = config.get("evaluation_criteria", [])
        self.feedback_style = config.get("feedback_style", "constructive")
        self.monitoring_frequency = config.get("monitoring_frequency", "per_task")
        
        # Evaluation settings
        self.quality_thresholds = config.get("quality_thresholds", {})
        self.improvement_tracking = config.get("improvement_tracking", True)
    
    @abstractmethod
    async def evaluate_performance(self, 
                                 expert_output: Dict[str, Any], 
                                 context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate expert performance and provide feedback.
        
        Args:
            expert_output: Output from an expert role
            context: Context information for evaluation
            
        Returns:
            Evaluation results with scores, feedback, and improvement suggestions
        """
        pass
    
    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process request from another role or orchestrator."""
        request_type = request.get("type", "unknown")
        
        if request_type == "evaluate":
            expert_output = request.get("expert_output", {})
            context = request.get("context", {})
            return await self.evaluate_performance(expert_output, context)
        elif request_type == "status_check":
            return self.get_status()
        elif request_type == "capability_query":
            return self.get_capabilities()
        else:
            return {
                "status": "error",
                "error": f"Unknown request type: {request_type}",
                "timestamp": datetime.now().isoformat()
            }

    async def cleanup(self):
        """Clean up critic resources."""
        self.active_tasks.clear()
        self.logger.info(f"Critic role {self.role_id} cleaned up")
