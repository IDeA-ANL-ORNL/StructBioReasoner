"""
Executive Agent for Hierarchical Multi-Agent Workflow

This agent is the top-level decision maker that:
1. Queries HiPerRAG for literature-guided strategy
2. Allocates computational resources to Manager agents
3. Evaluates Manager performance
4. Decides Manager lifecycle (continue/terminate)
5. Selects best binder for next round
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from academy.agent import Agent, action
from academy.handle import Handle
from academy.exchange import LocalExchangeFactory
from academy.manager import Manager
from concurrent.futures import ThreadPoolExecutor
from struct_bio_reasoner.prompts.prompts import get_prompt_manager, config_master
from struct_bio_reasoner.utils.uniprot_api import fetch_uniprot_sequence

logger = logging.getLogger(__name__)


class ExecutiveAgent(Agent):
    """
    Executive Agent for hierarchical workflow coordination.
    
    This agent makes strategic decisions about resource allocation
    and Manager lifecycle based on performance metrics and literature guidance.
    """
    
    def __init__(self, 
                 research_goal: str,
                 target_name: str,
                 target_seq: str,
                 rag_handle: Handle,
                 fold_handle: Handle,
                 sim_handle: Handle,
                 llm_interface,
                 total_compute_nodes: int,
                 config: Dict[str, Any]):
        """
        Initialize Executive Agent.
        
        Args:
            rag_handle: Handle to HiPerRAG agent
            llm_interface: LLM interface for decision making
            total_compute_nodes: Total computational nodes available
            config: Executive configuration
        """
        self.rag_handle = rag_handle
        self.fold_handle = fold_handle
        self.sim_handle = sim_handle
        self.llm = llm_interface
        self.total_nodes = total_compute_nodes
        self.config = config
        self.target_name = target_name
        self.target_seq = target_seq
        self.rag_prompt_manager = get_prompt_manager('rag', research_goal, {}, target_prot = self.target_name, prompt_type = 'interactome', history = [], num_history = 3) 
        
        self.folding_prompt_manager = get_prompt_manager('structure_prediction', research_goal, {}, target_prot = self.target_seq, prompt_type = 'running', history = [], num_history = 3)

        self.md_prompt_manager = get_prompt_manager('molecular_dynamics', research_goal, {}, target_prot = self.target_seq, prompt_type = 'interactome_simulation', history = [], num_history = 3)
        # Track managers and their allocations
        self.managers: Dict[str, Dict[str, Any]] = {}
        self.round_history: List[Dict[str, Any]] = []
        
        logger.info(f"Executive Agent initialized with {total_compute_nodes} compute nodes")
    
    @action
    async def query_hiper_rag(self, research_goal: str) -> Dict[str, Any]:
        """
        Query HiPerRAG for literature-guided strategy.
        
        Args:
            research_goal: Research objective
            
        Returns:
            RAG response with strategy recommendations
        """
        logger.info("Querying HiPerRAG for initial strategy...")
        
        # Construct RAG prompt for strategic guidance
        self.rag_prompt_manager.running_prompt()
        rag_prompt = self.llm.generate(prompt = self.rag_prompt_manager.prompt_r,
                                    temperature = 0.3,
                                    max_tokens = 32678)

        rag_response = await self.rag_handle.generate_rag_hypothesis({'prompt': rag_prompt})
        logger.info(f"RAG strategy received: {rag_response}")
        self.rag_prompt_manager.input_json = rag_response
        rag_conclusion = self.rag_prompt_manager.conclusion_prompt()
        rag_result_json = self.llm.generate_with_json_output(
                            prompt = rag_conclusion,
                            json_schema = config_master['rag_output'],
                            temperature = 0.3,
                            max_tokens = 32678)
        sequences = [await fetch_uniprot_sequence(id) for id in rag_result_json['interacting_protein_uniprot_ids']]
        rag_result_json['sequences'] = [s['sequence'] for s in sequences]
        self.folding_prompt_manager.input_json = rag_result_json 
        self.folding_prompt_manager.running_prompt()
        return {
            "research_goal": research_goal,
            "rag_strategy": rag_result_json,
            "timestamp": datetime.now().isoformat()
        }
    
    @action
    async def fold_interactome(self):
        folding_input = self.llm.generate_with_json_output(
                            prompt = self.folding_prompt_manager.prompt_r,
                            json_schema = config_master['structure_prediction'],
                            temperature = 0.3,
                            max_tokens = 32678) [0]
        folding_output = await self.fold_handle.analyze_hypothesis({}, folding_input) 
        self.folding_prompt_manager.input_json = folding_output
        self.folding_prompt_manager.conclusion_prompt()
        return folding_output
    @action
    async def sim_interactome(self):
        mdinput = self.llm.generate_with_json_output(
                        prompt = self.folding_prompt_manager.prompt_c,
                        json_schema = config_master['molecular_dynamics'],
                        temperature = 0.3,
                        max_tokens = 32678)[0]
        if True:
            md_output = await self.fold_handle.analyze_hypothesis({}, mdinput)
        self.md_prompt_manager.input_json = md_output
        self.md_prompt_manager.conclusion_prompt()
        self.logger.info(self.md_prompt_manager.prompt_c)
        return md_output
    @action
    async def allocate_resources(self, 
                                 manager_ids: List[str],
                                 round_num: int,
                                 previous_performance: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
        """
        Allocate computational nodes to Managers.
        
        Args:
            manager_ids: List of Manager IDs
            round_num: Current round number
            previous_performance: Performance metrics from previous round
            
        Returns:
            Dictionary mapping manager_id to number of nodes
        """
        logger.info(f"Allocating resources for round {round_num}...")
        
        if round_num == 1 or previous_performance is None:
            # Equal allocation for first round
            nodes_per_manager = self.total_nodes // len(manager_ids)
            allocation = {mid: nodes_per_manager for mid in manager_ids}
            logger.info(f"Round 1: Equal allocation of {nodes_per_manager} nodes per manager")
        else:
            # Performance-based allocation for subsequent rounds
            allocation = await self._performance_based_allocation(
                manager_ids, previous_performance
            )
        
        # Store allocation
        for manager_id, nodes in allocation.items():
            if manager_id not in self.managers:
                self.managers[manager_id] = {}
            self.managers[manager_id]['allocated_nodes'] = nodes
            self.managers[manager_id]['round'] = round_num
        
        return allocation
    
    @action
    async def evaluate_managers(self, manager_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Evaluate Manager performance.

        Args:
            manager_results: Results from each Manager

        Returns:
            Performance evaluation for each Manager
        """
        logger.info(f"Evaluating {len(manager_results)} managers...")

        evaluations = {}

        for manager_id, results in manager_results.items():
            # Extract key metrics
            best_binder = results.get('best_binder', {})
            tasks_executed = results.get('tasks_executed', [])

            # Calculate performance score
            score = self._calculate_performance_score(results)

            evaluations[manager_id] = {
                'score': score,
                'best_binder_affinity': best_binder.get('affinity', 0.0),
                'num_tasks': len(tasks_executed),
                'efficiency': score / len(tasks_executed) if tasks_executed else 0.0,
                'recommendation': 'continue' if score > 0.5 else 'terminate'
            }

        return evaluations

    @action
    async def decide_manager_lifecycle(self,
                                       evaluations: Dict[str, Any],
                                       round_num: int) -> Dict[str, Any]:
        """
        Decide which Managers continue and which get terminated.

        Args:
            evaluations: Manager performance evaluations
            round_num: Current round number

        Returns:
            Lifecycle decisions for each Manager
        """
        logger.info("Deciding Manager lifecycle...")

        # Sort managers by performance
        sorted_managers = sorted(
            evaluations.items(),
            key=lambda x: x[1]['score'],
            reverse=True
        )

        # Keep top performers, terminate bottom performers
        num_to_keep = max(2, len(sorted_managers) // 2)  # Keep at least 2, or half

        decisions = {
            'continue': [m[0] for m in sorted_managers[:num_to_keep]],
            'terminate': [m[0] for m in sorted_managers[num_to_keep:]],
            'round': round_num
        }

        logger.info(f"Continuing {len(decisions['continue'])} managers, "
                   f"terminating {len(decisions['terminate'])} managers")

        return decisions

    @action
    async def select_best_binder(self, manager_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Select the best binder across all Managers for next round.

        Args:
            manager_results: Results from each Manager

        Returns:
            Best binder information
        """
        logger.info("Selecting best binder for next round...")

        best_binder = None
        best_score = float('-inf')
        best_manager = None

        for manager_id, results in manager_results.items():
            binder = results.get('best_binder', {})
            score = binder.get('affinity', float('-inf'))

            if score > best_score:
                best_score = score
                best_binder = binder
                best_manager = manager_id

        logger.info(f"Best binder from {best_manager} with score {best_score}")

        return {
            'binder': best_binder,
            'score': best_score,
            'source_manager': best_manager,
            'timestamp': datetime.now().isoformat()
        }

    async def _performance_based_allocation(self,
                                           manager_ids: List[str],
                                           performance: Dict[str, Any]) -> Dict[str, int]:
        """
        Allocate resources based on Manager performance.

        Higher performing Managers get more resources.
        """
        # Calculate performance scores
        scores = {mid: performance.get(mid, {}).get('score', 0.5) for mid in manager_ids}
        total_score = sum(scores.values())

        # Allocate proportionally to performance
        allocation = {}
        allocated = 0

        for mid in manager_ids[:-1]:
            nodes = int((scores[mid] / total_score) * self.total_nodes)
            allocation[mid] = max(1, nodes)  # At least 1 node
            allocated += allocation[mid]

        # Give remaining to last manager
        allocation[manager_ids[-1]] = max(1, self.total_nodes - allocated)

        return allocation

    def _calculate_performance_score(self, results: Dict[str, Any]) -> float:
        """
        Calculate performance score for a Manager.

        Considers:
        - Best binder affinity
        - Number of successful tasks
        - Efficiency (results per task)
        """
        best_binder = results.get('best_binder', {})
        affinity = best_binder.get('affinity', 0.0)
        tasks = results.get('tasks_executed', [])

        # Normalize affinity (assuming range -20 to 0)
        affinity_score = min(1.0, max(0.0, (affinity + 20) / 20))

        # Task completion score
        task_score = min(1.0, len(tasks) / 10.0)

        # Combined score (weighted)
        score = 0.7 * affinity_score + 0.3 * task_score

        return score

