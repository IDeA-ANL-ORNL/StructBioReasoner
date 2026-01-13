"""
Hierarchical Multi-Agent Workflow for Adaptive Binder Design

This workflow implements a three-tier architecture:
1. Executive Agent: Strategic resource allocation and Manager lifecycle
2. Manager Agents: Tactical task sequencing for binder campaigns
3. Worker Agents: Operational execution (folding, simulation, design)

Flow:
Executive → HiPerRAG → Resource Allocation → Managers → Workers → Results → 
Executive Evaluation → Resource Reallocation → Next Round
"""

import asyncio
import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from academy.exchange import LocalExchangeFactory
from academy.manager import Manager
from concurrent.futures import ThreadPoolExecutor

from ..agents.executive.executive_agent import ExecutiveAgent
from ..agents.manager.manager_agent import ManagerAgent
from ..core.binder_design_system import BinderDesignSystem
from ..utils.llm_interface import alcfLLM

logger = logging.getLogger(__name__)


class HierarchicalBinderWorkflow:
    """
    Hierarchical workflow orchestrator for adaptive binder design.
    
    This orchestrator coordinates:
    - Executive agent for strategic decisions
    - Multiple Manager agents for parallel campaigns
    - Worker agents for task execution
    """
    
    def __init__(self,
                 config_path: str,
                 jnana_config_path: str,
                 research_goal: str,
                 total_compute_nodes: int = 50,
                 num_managers: int = 5,
                 max_rounds: int = 3):
        """
        Initialize hierarchical workflow.
        
        Args:
            config_path: Path to binder config
            jnana_config_path: Path to Jnana config
            total_compute_nodes: Total computational nodes available
            num_managers: Number of Manager agents to create
            max_rounds: Maximum number of rounds to execute
        """
        self.config_path = config_path
        self.jnana_config_path = jnana_config_path
        self.total_nodes = total_compute_nodes
        self.num_managers = num_managers
        self.max_rounds = max_rounds
        self.research_goal = research_goal
        # System components
        self.binder_system: Optional[BinderDesignSystem] = None
        self.academy_manager: Optional[Manager] = None
        self.executive_handle = None
        self.manager_handles: Dict[str, Any] = {}
        
        # Workflow state
        self.round_history: List[Dict[str, Any]] = []
        self.current_round = 0
        self.best_binder_overall = None
        
        logger.info(f"Hierarchical workflow initialized: {num_managers} managers, "
                   f"{total_compute_nodes} nodes, {max_rounds} max rounds")
    
    async def initialize(self):
        """Initialize all workflow components."""
        logger.info("Initializing hierarchical workflow...")
        
        # Initialize BinderDesignSystem
        self.binder_system = BinderDesignSystem(
            config_path=self.config_path,
            jnana_config_path=self.jnana_config_path,
            enable_agents=['computational_design', 'molecular_dynamics', 
                          'rag', 'structure_prediction']
        )
        await self.binder_system.start()
        logger.info("✓ BinderDesignSystem initialized")
        
        # Initialize Academy Manager for agent coordination
        self.academy_manager = await Manager.from_exchange_factory(
            factory=LocalExchangeFactory(),
            executors=ThreadPoolExecutor(),
        )
        await self.academy_manager.__aenter__()
        logger.info("✓ Academy Manager initialized")
        
        # Launch Executive Agent
        await self._launch_executive()
        logger.info("✓ Executive Agent launched")
        
        logger.info("Hierarchical workflow initialization complete")
    
    async def run(self, research_goal: str) -> Dict[str, Any]:
        """
        Run the hierarchical workflow.
        
        Args:
            research_goal: Research objective for binder design
            
        Returns:
            Complete workflow results with all rounds
        """
        logger.info("="*80)
        logger.info("STARTING HIERARCHICAL MULTI-AGENT WORKFLOW")
        logger.info("="*80)
        
        # Set research goal in binder system
        self.research_goal = research_goal
        session_id = await self.binder_system.set_research_goal(research_goal)
        logger.info(f"Research goal set (session: {session_id})")
        
        # Query HiPerRAG for initial strategy
        rag_strategy = await self.executive_handle.query_hiper_rag(research_goal)
        logger.info("✓ HiPerRAG strategy obtained")
        
        fold_results = await self.executive_handle.fold_interactome()
        logger.info(f'Interactome Folding obtained')
        sim_results = await self.executive_handle.sim_interactome()
        logger.info(f'Interactome Simulations obtained')
        # Initialize workflow state
        #seed_binder = None
        '''
        We want an initial run for all managers to fold + simulate the interactome results from hiper-rag
        '''
        active_managers = [f"manager_{i}" for i in range(self.num_managers)]
        # I want a seed binder for each manager in a dictionry
        seed_binders = {f"manager_{i}": None for i in range(self.num_managers)}
        # Execute rounds
        for round_num in range(1, self.max_rounds + 1):
            self.current_round = round_num
            logger.info(f"\n{'='*80}")
            logger.info(f"ROUND {round_num}/{self.max_rounds}")
            logger.info(f"{'='*80}")
            
            # Execute round
            round_results = await self.execute_round(
                round_num=round_num,
                active_managers=active_managers,
                seed_binder=seed_binder,
                research_goal=research_goal
            )
            
            # Store round results
            self.round_history.append(round_results)
            
            # Executive evaluates and decides lifecycle
            evaluations = round_results['evaluations']
            lifecycle_decisions = await self.executive_handle.decide_manager_lifecycle(
                evaluations, round_num
            )
            
            # Update active managers for next round
            active_managers = lifecycle_decisions['continue']
            
            # Select best binder for next round
            # Need a separate seed binder for each manager, dont want a global best binder
            best_binder_result = await self.executive_handle.select_best_binder(
                round_results['manager_results']
            )
            # update this!!!!!
            seed_binder = best_binder_result['binder']
            
            # Update overall best
            if (self.best_binder_overall is None or 
                best_binder_result['score'] > self.best_binder_overall.get('score', float('-inf'))):
                self.best_binder_overall = best_binder_result
            
            logger.info(f"Round {round_num} complete. Active managers: {len(active_managers)}")
            
            # Stop if no managers left
            if not active_managers:
                logger.info("No active managers remaining. Stopping workflow.")
                break
        
        # Compile final results
        final_results = {
            'research_goal': research_goal,
            'rag_strategy': rag_strategy,
            'total_rounds': len(self.round_history),
            'round_history': self.round_history,
            'best_binder_overall': self.best_binder_overall,
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info("="*80)
        logger.info("HIERARCHICAL WORKFLOW COMPLETE")
        logger.info(f"Best binder score: {self.best_binder_overall.get('score', 'N/A')}")
        logger.info("="*80)

        return final_results

    async def execute_round(self,
                           round_num: int,
                           active_managers: List[str],
                           seed_binder: Optional[Dict[str, Any]],
                           research_goal: str) -> Dict[str, Any]:
        """
        Execute a single round of the workflow.

        Args:
            round_num: Current round number
            active_managers: List of active Manager IDs
            seed_binder: Best binder from previous round (None for round 1)
            research_goal: Research objective

        Returns:
            Round results including Manager outputs and evaluations
        """
        logger.info(f"Executing round {round_num}...")

        # Get previous performance (None for round 1)
        previous_performance = None
        if round_num > 1 and self.round_history:
            previous_performance = self.round_history[-1]['evaluations']

        # Executive allocates resources
        resource_allocation = await self.executive_handle.allocate_resources(
            active_managers, round_num, previous_performance
        )
        logger.info(f"Resources allocated: {resource_allocation}")

        # Launch Manager agents
        await self._launch_managers(active_managers, resource_allocation)

        # Execute Manager campaigns in parallel
        manager_tasks = []
        for manager_id in active_managers:
            task = self._execute_manager_campaign(
                manager_id, seed_binder, research_goal
            )
            manager_tasks.append(task)

        # Wait for all Managers to complete
        manager_results_list = await asyncio.gather(*manager_tasks)

        # Organize results by manager_id
        manager_results = {
            result['manager_id']: result
            for result in manager_results_list
        }

        # Executive evaluates Managers
        evaluations = await self.executive_handle.evaluate_managers(manager_results)

        round_results = {
            'round_num': round_num,
            'resource_allocation': resource_allocation,
            'manager_results': manager_results,
            'evaluations': evaluations,
            'timestamp': datetime.now().isoformat()
        }

        return round_results

    async def _execute_manager_campaign(self,
                                       manager_id: str,
                                       seed_binder: Optional[Dict[str, Any]],
                                       research_goal: str) -> Dict[str, Any]:
        """
        Execute a single Manager's campaign.

        Args:
            manager_id: Manager identifier
            seed_binder: Starting binder (if any)
            research_goal: Research objective

        Returns:
            Manager campaign results
        """
        logger.info(f"Starting campaign for {manager_id}...")

        manager_handle = self.manager_handles[manager_id]

        # Manager decides and executes tasks until stopping
        current_state = {
            'seed_binder': seed_binder,
            'research_goal': research_goal
        }

        while True:
            # Manager decides next task
            next_task = await manager_handle.decide_next_task(current_state)

            if next_task == 'stop':
                logger.info(f"{manager_id}: Campaign complete (stop decision)")
                break

            # Execute the task
            task_result = await self._execute_manager_task(
                manager_handle, next_task, current_state
            )

            # Update state
            current_state[next_task] = task_result

            # Check if should stop
            task_history = await self._get_manager_history(manager_handle)
            should_stop = await manager_handle.should_stop(task_history)

            if should_stop:
                logger.info(f"{manager_id}: Campaign complete (stopping criteria met)")
                break

        # Manager summarizes campaign
        summary = await manager_handle.summarize_campaign()

        logger.info(f"{manager_id}: Campaign summary generated")
        return summary

    async def _execute_manager_task(self,
                                    manager_handle,
                                    task_type: str,
                                    current_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a specific task for a Manager.

        Args:
            manager_handle: Handle to Manager agent
            task_type: Type of task to execute
            current_state: Current campaign state

        Returns:
            Task execution results
        """
        logger.info(f"Executing task: {task_type}")

        # Build task parameters based on current state
        params = self._build_task_params(task_type, current_state)

        # Execute appropriate task
        if task_type == 'folding':
            result = await manager_handle.execute_folding(params)
        elif task_type == 'simulation':
            result = await manager_handle.execute_simulation(params)
        elif task_type == 'clustering':
            result = await manager_handle.execute_clustering(params)
        elif task_type == 'hotspot_analysis':
            result = await manager_handle.execute_hotspot_analysis(params)
        elif task_type == 'binder_design':
            result = await manager_handle.execute_binder_design(params)
        else:
            raise ValueError(f"Unknown task type: {task_type}")

        return result

    async def _launch_executive(self):
        """Launch the Executive Agent."""
        # Get RAG handle from binder system
        rag_agent = self.binder_system.design_agents.get('rag')
        folding_agent = self.binder_system.design_agents.get('structure_prediction')
        md_agent = self.binder_system.design_agents.get('molecular_dynamics')
        self.target_name = self.binder_system._extract_target_name(self.research_goal)
        self.target_seq = self.binder_system._extract_target_sequence(self.research_goal)
        if not rag_agent:
            raise ValueError("RAG agent not available in binder system")

        # Launch Executive Agent
        self.executive_handle = await self.academy_manager.launch(
            ExecutiveAgent,
            args=(
                self.research_goal,
                self.target_name,
                self.target_seq,
                rag_agent,#.rag_coord,  # RAG handle
                folding_agent,
                md_agent,
                alcfLLM(),  # LLM interface
                self.total_nodes,  # Total compute nodes
                {}  # Config
            )
        )

    async def _launch_managers(self,
                              manager_ids: List[str],
                              resource_allocation: Dict[str, int]):
        """
        Launch Manager agents with allocated resources.

        Args:
            manager_ids: List of Manager IDs to launch
            resource_allocation: Nodes allocated to each Manager
        """
        for manager_id in manager_ids:
            if manager_id not in self.manager_handles:
                # Prepare worker handles for this Manager
                worker_handles = await self._prepare_worker_handles()

                # Launch Manager
                manager_handle = await self.academy_manager.launch(
                    ManagerAgent,
                    args=(
                        manager_id,
                        resource_allocation[manager_id],
                        worker_handles,
                        alcfLLM(),
                        {}  # Config
                    )
                )

                self.manager_handles[manager_id] = manager_handle
                logger.info(f"Launched {manager_id} with {resource_allocation[manager_id]} nodes")

    async def _prepare_worker_handles(self) -> Dict[str, Any]:
        """
        Prepare handles to worker agents.

        Returns:
            Dictionary of worker handles
        """
        # For now, return references to agents in binder_system
        # In full implementation, these would be Academy handles
        return {
            'folding': self.binder_system.design_agents.get('structure_prediction'),
            'simulation': self.binder_system.design_agents.get('molecular_dynamics'),
            'binder_design': self.binder_system.design_agents.get('computational_design'),
            # Note: clustering and hotspot would need to be added
        }

    def _build_task_params(self, task_type: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Build parameters for a task based on current state."""
        # Extract target sequence from research goal
        target_sequence = self.binder_system._extract_target_sequence(
            current_state.get('research_goal', '')
        )

        if task_type == 'folding':
            return {
                'sequence': current_state.get('seed_binder', {}).get('sequence', 'MKQHKAMIVALIVICITAVVAALVTRKDLCEVHIRTGQTEVAVF'),
                'target_sequence': target_sequence
            }
        elif task_type == 'simulation':
            return {
                'pdb_path': current_state.get('folding', {}).get('pdb_path', ''),
                'timesteps': 1000000
            }
        elif task_type == 'clustering':
            return {
                'trajectory_paths': [r.get('trajectory_path') for r in current_state.get('simulation', [])],
                'n_clusters': 5
            }
        elif task_type == 'hotspot_analysis':
            return {
                'simulation_results': current_state.get('simulation', []),
                'cluster_results': current_state.get('clustering')
            }
        elif task_type == 'binder_design':
            return {
                'target_sequence': target_sequence,
                'hotspot_residues': current_state.get('hotspot_analysis', {}).get('hotspots', []),
                'num_designs': 25
            }
        else:
            return {}

    async def _get_manager_history(self, manager_handle) -> List[Dict[str, Any]]:
        """Get task history from a Manager."""
        # This would access the Manager's task_history attribute
        # For now, return empty list (would need proper implementation)
        return []

    async def cleanup(self):
        """Cleanup workflow resources."""
        logger.info("Cleaning up hierarchical workflow...")

        if self.academy_manager:
            await self.academy_manager.__aexit__(None, None, None)

        if self.binder_system:
            await self.binder_system.cleanup()

        logger.info("Cleanup complete")
