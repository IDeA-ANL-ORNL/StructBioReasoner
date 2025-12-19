"""
Manager Agent for Hierarchical Multi-Agent Workflow

This agent coordinates a single binder design campaign:
1. Decides task sequence (folding → simulation → clustering → design)
2. Executes tasks using worker agents
3. Determines stopping criteria
4. Summarizes campaign results
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from academy.agent import Agent, action
from academy.handle import Handle

logger = logging.getLogger(__name__)


class ManagerAgent(Agent):
    """
    Manager Agent for coordinating binder design campaigns.
    
    This agent makes tactical decisions about task sequencing and
    coordinates worker agents (folding, simulation, clustering, design).
    """
    
    def __init__(self,
                 manager_id: str,
                 allocated_nodes: int,
                 worker_handles: Dict[str, Handle],
                 llm_interface,
                 config: Dict[str, Any]):
        """
        Initialize Manager Agent.
        
        Args:
            manager_id: Unique identifier for this Manager
            allocated_nodes: Number of compute nodes allocated
            worker_handles: Handles to worker agents (folding, simulation, etc.)
            llm_interface: LLM interface for decision making
            config: Manager configuration
        """
        self.manager_id = manager_id
        self.allocated_nodes = allocated_nodes
        self.workers = worker_handles
        self.llm = llm_interface
        self.config = config
        
        # Campaign state
        self.task_history: List[Dict[str, Any]] = []
        self.current_structures: List[Dict[str, Any]] = []
        self.simulation_results: List[Dict[str, Any]] = []
        self.cluster_results: Optional[Dict[str, Any]] = None
        self.hotspot_results: Optional[Dict[str, Any]] = None
        self.binder_designs: List[Dict[str, Any]] = []
        
        # Performance tracking
        self.start_time = datetime.now()
        self.tasks_completed = 0
        
        logger.info(f"Manager {manager_id} initialized with {allocated_nodes} nodes")
    
    @action
    async def decide_next_task(self, current_state: Dict[str, Any]) -> str:
        """
        Decide the next task to execute based on current state.
        
        Args:
            current_state: Current campaign state
            
        Returns:
            Next task type: 'folding', 'simulation', 'clustering', 
                           'hotspot_analysis', 'binder_design', or 'stop'
        """
        logger.info(f"Manager {self.manager_id}: Deciding next task...")
        
        # Build decision prompt
        prompt = self._build_task_decision_prompt(current_state)
        
        # Query LLM for decision
        response = self.llm.generate(
            prompt=prompt,
            temperature=self.config.get('temperature', 0.5),
            max_tokens=500
        )
        
        # Parse response to extract task
        task = self._parse_task_decision(response)
        
        logger.info(f"Manager {self.manager_id}: Next task = {task}")
        return task
    
    @action
    async def execute_folding(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute protein folding task.
        
        Args:
            params: Folding parameters (sequence, etc.)
            
        Returns:
            Folding results with structures
        """
        logger.info(f"Manager {self.manager_id}: Executing folding...")
        
        # Call Chai agent through handle
        folding_handle = self.workers.get('folding')
        if not folding_handle:
            raise ValueError("Folding worker not available")
        
        # Execute folding (assuming Chai agent has a fold_protein action)
        # TODO: what agent is this going to? ForwardFoldingAgent? 
        result = await folding_handle.fold_sequences(
            sequences=params['sequences'],
            names=params['names']
            constraints=params['constraints']
            #target_sequence=params.get('target_sequence'),
            #device=params.get('device', 'cuda:0')
        )
        
        # Store results
        self.current_structures.append(result)
        self._record_task('folding', params, result)
        
        return result
    
    @action
    async def execute_simulation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute MD simulation task.
        
        Args:
            params: Simulation parameters (structure, timesteps, etc.)
            
        Returns:
            Simulation results with trajectory
        """
        logger.info(f"Manager {self.manager_id}: Executing simulation...")
        
        # Call MD agent through handle
        md_handle = self.workers.get('simulation')
        if not md_handle:
            raise ValueError("Simulation worker not available")
        
        # Execute simulation
        result = await md_handle.analyze_hypothesis(
            None,
            params
            # params should contain these keys:
            #   simulation_time: int
            #   solvent: 'implicit' or 'explicit'
            #   steps: int (number of prod steps)
            #   simulation_paths: list[str]
            #   root_output_path: str

            #pdb_path=params['pdb_path'],
            #timesteps=params.get('timesteps', 1000000),
            #temperature=params.get('temperature', 300),
            #solvent=params.get('solvent', 'implicit')
        )
        
        # Store results
        self.simulation_results.append(result)
        self._record_task('simulation', params, result)

        return result

    @action
    async def execute_clustering(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute trajectory clustering task.

        Args:
            params: Clustering parameters (trajectories, n_clusters, etc.)

        Returns:
            Clustering results with representative structures
        """
        logger.info(f"Manager {self.manager_id}: Executing clustering...")

        # Call clustering agent through handle
        cluster_handle = self.workers.get('clustering')
        if not cluster_handle:
            raise ValueError("Clustering worker not available")

        # Execute clustering
        result = await cluster_handle.analyze_hypothesis(
            None,
            params
            # params should contain these keys:
            #   TODO: agent in dev
        )

        # Store results
        self.cluster_results = result
        self._record_task('clustering', params, result)

        return result

    @action
    async def execute_hotspot_analysis(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute hotspot analysis task.

        Args:
            params: Hotspot analysis parameters

        Returns:
            Hotspot analysis results
        """
        logger.info(f"Manager {self.manager_id}: Executing hotspot analysis...")

        # Call hotspot analyzer through handle
        hotspot_handle = self.workers.get('hotspot')
        if not hotspot_handle:
            raise ValueError("Hotspot worker not available")

        # Execute hotspot analysis
        result = await hotspot_handle.analyze_hypothesis(
            None,
            params
            # params should contain these keys:
            #   TODO: agent in dev
            #   
        )

        # Store results
        self.hotspot_results = result
        self._record_task('hotspot_analysis', params, result)

        return result

    @action
    async def execute_binder_design(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute binder design task.

        Args:
            params: Binder design parameters

        Returns:
            Binder design results
        """
        logger.info(f"Manager {self.manager_id}: Executing binder design...")

        # Call BindCraft agent through handle
        design_handle = self.workers.get('binder_design')
        if not design_handle:
            raise ValueError("Binder design worker not available")

        # Execute binder design
        result = await design_handle.analyze_hypothesis(
            None, # no hypothesis
            params
            # params should contain these keys:
            #   cwd,
            #   target_sequence,
            #   binder_sequence,
            #   num_rounds
        )

        # Store results
        self.binder_designs.append(result)
        self._record_task('binder_design', params, result)

        return result

    @action
    async def should_stop(self, history: List[Dict[str, Any]]) -> bool:
        """
        Decide if the campaign should stop.

        Args:
            history: Task execution history

        Returns:
            True if campaign should stop, False otherwise
        """
        logger.info(f"Manager {self.manager_id}: Evaluating stopping criteria...")

        # Check stopping criteria
        max_tasks = self.config.get('max_tasks_per_campaign', 10)
        min_affinity = self.config.get('min_binder_affinity', -10.0)

        # Stop if max tasks reached
        if len(history) >= max_tasks:
            logger.info(f"Manager {self.manager_id}: Max tasks reached")
            return True

        # Stop if good binder found
        if self.binder_designs:
            best_affinity = max(
                d.get('affinity', float('-inf'))
                for d in self.binder_designs
            )
            if best_affinity <= min_affinity:  # More negative = better
                logger.info(f"Manager {self.manager_id}: Good binder found (affinity={best_affinity})")
                return True

        # Continue otherwise
        return False

    @action
    async def summarize_campaign(self) -> Dict[str, Any]:
        """
        Summarize the campaign results.

        Returns:
            Campaign summary with all results and decisions
        """
        logger.info(f"Manager {self.manager_id}: Summarizing campaign...")

        # Find best binder
        best_binder = None
        best_affinity = float('-inf')

        for design in self.binder_designs:
            affinity = design.get('affinity', float('-inf'))
            if affinity > best_affinity:
                best_affinity = affinity
                best_binder = design

        # Calculate campaign duration
        duration = (datetime.now() - self.start_time).total_seconds()

        summary = {
            'manager_id': self.manager_id,
            'allocated_nodes': self.allocated_nodes,
            'tasks_executed': self.task_history,
            'num_tasks': len(self.task_history),
            'duration_seconds': duration,
            'best_binder': best_binder,
            'all_binders': self.binder_designs,
            'structures_generated': len(self.current_structures),
            'simulations_run': len(self.simulation_results),
            'hotspots_identified': self.hotspot_results,
            'timestamp': datetime.now().isoformat()
        }

        return summary

    def _record_task(self, task_type: str, params: Dict[str, Any], result: Dict[str, Any]):
        """Record task execution in history."""
        self.task_history.append({
            'task_type': task_type,
            'params': params,
            'result': result,
            'timestamp': datetime.now().isoformat()
        })
        self.tasks_completed += 1

    def _build_task_decision_prompt(self, current_state: Dict[str, Any]) -> str:
        """Build prompt for LLM to decide next task."""
        prompt = f"""
You are a Manager agent coordinating a binder design campaign.

Current State:
- Structures generated: {len(self.current_structures)}
- Simulations completed: {len(self.simulation_results)}
- Clustering done: {self.cluster_results is not None}
- Hotspots identified: {self.hotspot_results is not None}
- Binders designed: {len(self.binder_designs)}
- Tasks completed: {self.tasks_completed}

Task History:
{self._format_task_history()}

Based on the current state, what should be the next task?

Options:
1. 'folding' - Fold protein structures
2. 'simulation' - Run MD simulations
3. 'clustering' - Cluster simulation trajectories
4. 'hotspot_analysis' - Identify binding hotspots
5. 'binder_design' - Design binder molecules
6. 'stop' - Campaign complete

Respond with ONLY the task name (e.g., 'folding', 'simulation', etc.).
"""
        return prompt

    def _format_task_history(self) -> str:
        """Format task history for prompt."""
        if not self.task_history:
            return "No tasks completed yet"

        history_str = ""
        for i, task in enumerate(self.task_history[-5:], 1):  # Last 5 tasks
            history_str += f"{i}. {task['task_type']}\n"
        return history_str

    def _parse_task_decision(self, llm_response: str) -> str:
        """Parse LLM response to extract task decision."""
        response_lower = llm_response.lower().strip()

        valid_tasks = ['folding', 'simulation', 'clustering',
                      'hotspot_analysis', 'binder_design', 'stop']

        for task in valid_tasks:
            if task in response_lower:
                return task

        # Default to stop if unclear
        logger.warning(f"Could not parse task decision from: {llm_response}")
        return 'stop'
