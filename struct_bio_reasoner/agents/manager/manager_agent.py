"""
Manager Agent for Hierarchical Multi-Agent Workflow

This agent coordinates a single binder design campaign:
1. Decides task sequence (folding → simulation → clustering → design)
2. Executes tasks using worker agents
3. Receives and acts on executive advice
4. Determines stopping criteria
5. Summarizes campaign results
"""

import asyncio
import logging
from enum import Enum
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from academy.agent import Agent, action
from academy.handle import Handle

logger = logging.getLogger(__name__)


class AdviceType(Enum):
    """Types of executive advice."""
    EXPLORE_HOTSPOTS = "explore_hotspots"
    REFINE_DESIGNS = "refine_designs"
    REDUCE_SIMULATION = "reduce_simulation"
    INCREASE_SIMULATION = "increase_simulation"
    CHANGE_STRATEGY = "change_strategy"
    GENERAL = "general"


class ManagerAgent(Agent):
    """
    Manager Agent for coordinating binder design campaigns.

    This agent makes tactical decisions about task sequencing and
    coordinates worker agents (folding, simulation, clustering, design).
    It also receives and incorporates advice from the Executive agent.
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

        # Target information (from config)
        self.target_info = config.get('target', {})

        # Campaign state
        self.task_history: List[Dict[str, Any]] = []
        self.current_structures: List[Dict[str, Any]] = []
        self.simulation_results: List[Dict[str, Any]] = []
        self.cluster_results: Optional[Dict[str, Any]] = None
        self.hotspot_results: Optional[Dict[str, Any]] = None
        self.binder_designs: List[Dict[str, Any]] = []

        # Executive advice tracking
        self.executive_advice: List[Dict[str, Any]] = []
        self.current_advice: Optional[str] = None
        self.advice_applied: List[Dict[str, Any]] = []

        # Strategy modifiers (adjusted based on advice)
        self.strategy_modifiers = {
            'simulation_timesteps_multiplier': 1.0,
            'num_designs_multiplier': 1.0,
            'exploration_mode': False,  # True = explore new hotspots
            'refinement_mode': False,   # True = refine existing designs
        }

        # Performance tracking
        self.start_time = datetime.now()
        self.tasks_completed = 0
        self.best_affinity = float('-inf')

        logger.info(f"Manager {manager_id} initialized with {allocated_nodes} nodes")
    
    @action
    async def decide_next_task(self, current_state: Dict[str, Any]) -> str:
        """
        Decide the next task to execute based on current state.

        Args:
            current_state: Current campaign state (may include executive_advice)

        Returns:
            Next task type: 'folding', 'simulation', 'clustering',
                           'hotspot_analysis', 'binder_design', or 'stop'
        """
        logger.info(f"Manager {self.manager_id}: Deciding next task...")

        # Check for new executive advice in current_state
        if 'executive_advice' in current_state and current_state['executive_advice']:
            await self.receive_advice(current_state['executive_advice'])

        # Build decision prompt (now includes executive advice)
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
    async def receive_advice(self, advice: str) -> Dict[str, Any]:
        """
        Receive and process advice from the Executive agent.

        Args:
            advice: Advice string from the Executive

        Returns:
            Acknowledgment with any strategy adjustments made
        """
        logger.info(f"Manager {self.manager_id}: Received executive advice: {advice}")

        # Store the advice
        advice_record = {
            'advice': advice,
            'received_at': datetime.now().isoformat(),
            'tasks_at_receipt': self.tasks_completed,
        }
        self.executive_advice.append(advice_record)
        self.current_advice = advice

        # Parse and apply the advice
        adjustments = self._parse_and_apply_advice(advice)
        advice_record['adjustments'] = adjustments

        logger.info(f"Manager {self.manager_id}: Applied adjustments: {adjustments}")
        return {
            'acknowledged': True,
            'manager_id': self.manager_id,
            'adjustments': adjustments,
            'timestamp': datetime.now().isoformat()
        }

    def _parse_and_apply_advice(self, advice: str) -> Dict[str, Any]:
        """
        Parse executive advice and apply relevant strategy adjustments.

        Args:
            advice: The advice string

        Returns:
            Dictionary of adjustments made
        """
        adjustments = {}
        advice_lower = advice.lower()

        # Check for hotspot exploration advice
        if any(kw in advice_lower for kw in ['hotspot', 'explore', 'different region', 'new region']):
            self.strategy_modifiers['exploration_mode'] = True
            self.strategy_modifiers['refinement_mode'] = False
            adjustments['exploration_mode'] = True
            logger.info(f"Manager {self.manager_id}: Switching to exploration mode")

        # Check for refinement advice
        if any(kw in advice_lower for kw in ['refin', 'focus', 'current design', 'best design']):
            self.strategy_modifiers['refinement_mode'] = True
            self.strategy_modifiers['exploration_mode'] = False
            adjustments['refinement_mode'] = True
            logger.info(f"Manager {self.manager_id}: Switching to refinement mode")

        # Check for simulation time adjustments
        if any(kw in advice_lower for kw in ['reduce simulation', 'shorter simulation', 'faster', 'iterate faster']):
            self.strategy_modifiers['simulation_timesteps_multiplier'] = 0.5
            adjustments['simulation_multiplier'] = 0.5
            logger.info(f"Manager {self.manager_id}: Reducing simulation time by 50%")

        if any(kw in advice_lower for kw in ['increase simulation', 'longer simulation', 'more sampling']):
            self.strategy_modifiers['simulation_timesteps_multiplier'] = 2.0
            adjustments['simulation_multiplier'] = 2.0
            logger.info(f"Manager {self.manager_id}: Increasing simulation time by 2x")

        # Check for design quantity adjustments
        if any(kw in advice_lower for kw in ['more design', 'more binder', 'increase design']):
            self.strategy_modifiers['num_designs_multiplier'] = 1.5
            adjustments['designs_multiplier'] = 1.5
            logger.info(f"Manager {self.manager_id}: Increasing design count by 50%")

        # Record that advice was applied
        self.advice_applied.append({
            'advice': advice,
            'adjustments': adjustments,
            'applied_at': datetime.now().isoformat()
        })

        return adjustments

    @action
    async def get_advice_status(self) -> Dict[str, Any]:
        """
        Get the current status of executive advice.

        Returns:
            Status of advice received and applied
        """
        return {
            'manager_id': self.manager_id,
            'total_advice_received': len(self.executive_advice),
            'current_advice': self.current_advice,
            'advice_applied': len(self.advice_applied),
            'strategy_modifiers': self.strategy_modifiers.copy(),
            'recent_advice': self.executive_advice[-3:] if self.executive_advice else []
        }

    @action
    async def clear_advice(self) -> Dict[str, Any]:
        """
        Clear current advice (e.g., after it has been fully acted upon).

        Returns:
            Confirmation of advice cleared
        """
        old_advice = self.current_advice
        self.current_advice = None

        # Reset strategy modifiers to defaults
        self.strategy_modifiers = {
            'simulation_timesteps_multiplier': 1.0,
            'num_designs_multiplier': 1.0,
            'exploration_mode': False,
            'refinement_mode': False,
        }

        logger.info(f"Manager {self.manager_id}: Cleared advice and reset strategy modifiers")
        return {
            'cleared_advice': old_advice,
            'timestamp': datetime.now().isoformat()
        }
    
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
            names=params['names'],
            constraints=params['constraints'],
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

        # Apply strategy modifiers to simulation parameters
        modified_params = params.copy()
        timestep_multiplier = self.strategy_modifiers.get('simulation_timesteps_multiplier', 1.0)

        if 'timesteps' in modified_params:
            original_timesteps = modified_params['timesteps']
            modified_params['timesteps'] = int(original_timesteps * timestep_multiplier)
            logger.info(
                f"Manager {self.manager_id}: Adjusted timesteps from {original_timesteps} "
                f"to {modified_params['timesteps']} (multiplier: {timestep_multiplier})"
            )

        if 'steps' in modified_params:
            original_steps = modified_params['steps']
            modified_params['steps'] = int(original_steps * timestep_multiplier)
            logger.info(
                f"Manager {self.manager_id}: Adjusted steps from {original_steps} "
                f"to {modified_params['steps']} (multiplier: {timestep_multiplier})"
            )

        # Execute simulation
        result = await md_handle.analyze_hypothesis(
            None,
            modified_params
            # params should contain these keys:
            #   simulation_time: int
            #   solvent: 'implicit' or 'explicit'
            #   steps: int (number of prod steps)
            #   simulation_paths: list[str]
            #   root_output_path: str
        )

        # Store results
        self.simulation_results.append(result)
        self._record_task('simulation', modified_params, result)

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

        # Apply strategy modifiers to design parameters
        modified_params = params.copy()
        designs_multiplier = self.strategy_modifiers.get('num_designs_multiplier', 1.0)

        if 'num_designs' in modified_params:
            original_designs = modified_params['num_designs']
            modified_params['num_designs'] = int(original_designs * designs_multiplier)
            logger.info(
                f"Manager {self.manager_id}: Adjusted num_designs from {original_designs} "
                f"to {modified_params['num_designs']} (multiplier: {designs_multiplier})"
            )

        if 'num_rounds' in modified_params:
            original_rounds = modified_params['num_rounds']
            modified_params['num_rounds'] = int(original_rounds * designs_multiplier)
            logger.info(
                f"Manager {self.manager_id}: Adjusted num_rounds from {original_rounds} "
                f"to {modified_params['num_rounds']} (multiplier: {designs_multiplier})"
            )

        # If in refinement mode, add seed binder to improve upon
        if self.strategy_modifiers.get('refinement_mode') and self.binder_designs:
            # Use best existing design as seed
            best_existing = max(
                self.binder_designs,
                key=lambda d: d.get('affinity', float('-inf'))
            )
            if 'seed_binder' not in modified_params:
                modified_params['seed_binder'] = best_existing
                logger.info(
                    f"Manager {self.manager_id}: Refinement mode - using best design "
                    f"(affinity={best_existing.get('affinity', 'N/A')}) as seed"
                )

        # Execute binder design
        result = await design_handle.analyze_hypothesis(
            None,  # no hypothesis
            modified_params
            # params should contain these keys:
            #   cwd,
            #   target_sequence,
            #   binder_sequence,
            #   num_rounds
        )

        # Store results and update best affinity
        self.binder_designs.append(result)
        affinity = result.get('affinity', float('-inf'))
        if affinity > self.best_affinity:
            self.best_affinity = affinity
            logger.info(f"Manager {self.manager_id}: New best affinity: {affinity}")

        self._record_task('binder_design', modified_params, result)

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
            'target': self.target_info,
            'allocated_nodes': self.allocated_nodes,
            'tasks_executed': self.task_history,
            'num_tasks': len(self.task_history),
            'duration_seconds': duration,
            'best_binder': best_binder,
            'best_affinity': best_affinity if best_affinity > float('-inf') else None,
            'all_binders': self.binder_designs,
            'structures_generated': len(self.current_structures),
            'simulations_run': len(self.simulation_results),
            'hotspots_identified': self.hotspot_results,
            # Executive advice tracking
            'advice_received': len(self.executive_advice),
            'advice_applied': len(self.advice_applied),
            'advice_history': self.executive_advice,
            'final_strategy_modifiers': self.strategy_modifiers.copy(),
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
        # Get target info
        target_name = self.target_info.get('name', current_state.get('target', {}).get('name', 'Unknown'))

        # Build base prompt
        prompt = f"""You are a Manager agent coordinating a binder design campaign for target: {target_name}

Current State:
- Structures generated: {len(self.current_structures)}
- Simulations completed: {len(self.simulation_results)}
- Hotspots identified: {self.hotspot_results is not None}
- Binders designed: {len(self.binder_designs)}
- Tasks completed: {self.tasks_completed}
- Best affinity achieved: {self.best_affinity if self.best_affinity > float('-inf') else 'None yet'}

Task History:
{self._format_task_history()}
"""

        # Add executive advice section if we have advice
        if self.current_advice:
            prompt += f"""
EXECUTIVE GUIDANCE (IMPORTANT - incorporate this into your decision):
"{self.current_advice}"

Current Strategy Modifiers:
- Exploration mode: {self.strategy_modifiers['exploration_mode']}
- Refinement mode: {self.strategy_modifiers['refinement_mode']}
- Simulation time multiplier: {self.strategy_modifiers['simulation_timesteps_multiplier']}x
- Design count multiplier: {self.strategy_modifiers['num_designs_multiplier']}x
"""

        # Add strategy guidance based on modifiers
        if self.strategy_modifiers['exploration_mode']:
            prompt += """
NOTE: You are in EXPLORATION mode. Prioritize hotspot_analysis to find new binding regions.
"""
        elif self.strategy_modifiers['refinement_mode']:
            prompt += """
NOTE: You are in REFINEMENT mode. Prioritize binder_design to improve existing designs.
"""

        prompt += """
Based on the current state and any executive guidance, what should be the next task?

Options:
1. 'folding' - Fold protein structures (do this first if no structures)
2. 'simulation' - Run MD simulations (after folding)
3. 'clustering' - Cluster simulation trajectories
4. 'hotspot_analysis' - Identify binding hotspots (prioritize if in exploration mode)
5. 'binder_design' - Design binder molecules (prioritize if in refinement mode)
6. 'stop' - Campaign complete (only if good results achieved or resources exhausted)

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
