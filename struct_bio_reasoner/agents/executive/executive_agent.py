"""
Executive Agent for Hierarchical Multi-Agent Workflow

This agent is the top-level decision maker that:
1. Queries HiPerRAG for literature-guided strategy
2. Allocates computational resources to Manager agents
3. Evaluates Manager performance
4. Decides Manager lifecycle (continue/terminate/advise/duplicate/replace)
5. Generates strategic advice for managers
6. Identifies candidates for duplication or replacement
"""

import asyncio
import json
import logging
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple
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


class ExecutiveActionType(Enum):
    """Actions the executive can take on managers."""
    CONTINUE = "continue"
    ADVISE = "advise"
    KILL = "kill"
    REPLACE = "replace"
    DUPLICATE = "duplicate"


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
            research_goal: The overall research objective
            target_name: Name of the target protein
            target_seq: Sequence of the target protein
            rag_handle: Handle to HiPerRAG agent
            fold_handle: Handle to folding agent
            sim_handle: Handle to simulation agent
            llm_interface: LLM interface for decision making
            total_compute_nodes: Total computational nodes available
            config: Executive configuration
        """
        self.research_goal = research_goal
        self.rag_handle = rag_handle
        self.fold_handle = fold_handle
        self.sim_handle = sim_handle
        self.llm = llm_interface
        self.total_nodes = total_compute_nodes
        self.config = config
        self.target_name = target_name
        self.target_seq = target_seq

        # Prompt managers for different stages
        self.rag_prompt_manager = get_prompt_manager(
            'rag', research_goal, {},
            target_prot=self.target_name,
            prompt_type='interactome',
            history=[],
            num_history=3
        )
        self.folding_prompt_manager = get_prompt_manager(
            'structure_prediction', research_goal, {},
            target_prot=self.target_seq,
            prompt_type='running',
            history=[],
            num_history=3
        )
        self.md_prompt_manager = get_prompt_manager(
            'molecular_dynamics', research_goal, {},
            target_prot=self.target_seq,
            prompt_type='interactome_simulation',
            history=[],
            num_history=3
        )

        # Track managers and their allocations
        self.managers: Dict[str, Dict[str, Any]] = {}
        self.round_history: List[Dict[str, Any]] = []
        self.action_history: List[Dict[str, Any]] = []

        # Thresholds for decision making (can be overridden via config)
        self.duplication_threshold = config.get('duplication_threshold', -12.0)
        self.termination_threshold = config.get('termination_threshold', 0.3)
        self.stuck_task_threshold = config.get('stuck_task_threshold', 20)
        self.max_managers = config.get('max_managers', 10)

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

        # Handle progress report format (tasks_completed instead of tasks_executed)
        if not tasks:
            tasks_count = results.get('tasks_completed', 0)
        else:
            tasks_count = len(tasks)

        # Also check best_score directly (from progress reports)
        if affinity == 0.0:
            affinity = results.get('best_score', 0.0)

        # Normalize affinity (assuming range -20 to 0)
        affinity_score = min(1.0, max(0.0, (affinity + 20) / 20))

        # Task completion score
        task_score = min(1.0, tasks_count / 10.0)

        # Combined score (weighted)
        score = 0.7 * affinity_score + 0.3 * task_score

        return score

    @action
    async def generate_manager_advice(
        self,
        manager_id: str,
        progress_report: Dict[str, Any],
        evaluation: Dict[str, Any]
    ) -> Optional[str]:
        """
        Generate strategic advice for a manager using LLM.

        Args:
            manager_id: The manager to advise
            progress_report: Current progress report from manager
            evaluation: Performance evaluation

        Returns:
            Advice string or None if no advice needed
        """
        logger.info(f"Generating advice for {manager_id}...")

        # Build context for LLM
        prompt = f"""You are an executive agent overseeing a protein binder design campaign.

Research Goal: {self.research_goal}

Manager {manager_id} Progress Report:
- Target: {progress_report.get('target_name', 'Unknown')}
- Tasks Completed: {progress_report.get('tasks_completed', 0)}
- Designs Generated: {progress_report.get('designs_generated', 0)}
- Best Binding Affinity: {progress_report.get('best_score', 'N/A')}
- Runtime: {progress_report.get('runtime_seconds', 0) / 3600:.2f} hours
- Recent Advice Given: {progress_report.get('recent_advice', [])}

Performance Evaluation:
- Score: {evaluation.get('score', 0):.3f}
- Efficiency: {evaluation.get('efficiency', 0):.3f}
- Recommendation: {evaluation.get('recommendation', 'continue')}

Based on this information, provide brief, actionable advice to help this manager improve.
Focus on:
1. Whether they should try different hotspot regions
2. Whether to increase/decrease simulation time
3. Whether to focus on refining current designs or exploring new ones
4. Any strategic pivots based on progress

If the manager is performing well, you may respond with "NO_ADVICE_NEEDED".
Keep advice concise (1-2 sentences max).

Advice:"""

        try:
            response = self.llm.generate(
                prompt=prompt,
                temperature=0.7,
                max_tokens=200
            )

            advice = response.strip()

            if "NO_ADVICE_NEEDED" in advice.upper():
                return None

            logger.info(f"Generated advice for {manager_id}: {advice}")
            return advice

        except Exception as e:
            logger.error(f"Failed to generate advice: {e}")
            return None

    @action
    async def decide_manager_actions(
        self,
        progress_reports: Dict[str, Dict[str, Any]],
        available_targets: List[Dict[str, Any]],
        current_manager_count: int
    ) -> List[Dict[str, Any]]:
        """
        Decide comprehensive actions for all managers.

        This is the main decision-making method that determines all actions:
        - Which managers to continue
        - Which managers to kill
        - Which managers to advise
        - Which managers to duplicate
        - Which managers to replace

        Args:
            progress_reports: Progress reports from all managers
            available_targets: Targets not currently assigned to managers
            current_manager_count: Current number of active managers

        Returns:
            List of action dictionaries with keys:
            - manager_id: Target manager ID
            - action: ExecutiveActionType value
            - advice: Optional advice string
            - new_target: Optional target for replacement
            - source_manager_id: Optional source for duplication
        """
        logger.info("Deciding comprehensive manager actions...")

        actions = []

        # First, evaluate all managers
        evaluations = await self.evaluate_managers(progress_reports)

        # Sort by performance
        sorted_managers = sorted(
            evaluations.items(),
            key=lambda x: x[1]['score'],
            reverse=True
        )

        # Identify actions for each manager
        for manager_id, evaluation in sorted_managers:
            progress = progress_reports.get(manager_id, {})

            # Check for termination (poor performance)
            if evaluation['score'] < self.termination_threshold:
                actions.append({
                    'manager_id': manager_id,
                    'action': ExecutiveActionType.KILL.value,
                    'reason': f"Low performance score: {evaluation['score']:.3f}"
                })
                continue

            # Check if manager is stuck (many tasks, no good results)
            tasks_completed = progress.get('tasks_completed', 0)
            best_score = progress.get('best_score', float('-inf'))

            if tasks_completed > self.stuck_task_threshold and best_score < -8.0:
                # Consider replacement if there are available targets
                if available_targets:
                    actions.append({
                        'manager_id': manager_id,
                        'action': ExecutiveActionType.REPLACE.value,
                        'new_target': available_targets[0],
                        'reason': f"Stuck after {tasks_completed} tasks with score {best_score:.2f}"
                    })
                    available_targets = available_targets[1:]  # Remove used target
                    continue

            # Generate advice for continuing managers
            advice = await self.generate_manager_advice(manager_id, progress, evaluation)
            if advice:
                actions.append({
                    'manager_id': manager_id,
                    'action': ExecutiveActionType.ADVISE.value,
                    'advice': advice
                })
            else:
                actions.append({
                    'manager_id': manager_id,
                    'action': ExecutiveActionType.CONTINUE.value
                })

        # Check for duplication opportunities
        if current_manager_count < self.max_managers and sorted_managers:
            best_manager_id, best_evaluation = sorted_managers[0]
            best_progress = progress_reports.get(best_manager_id, {})
            best_score = best_progress.get('best_score', float('-inf'))

            # Duplicate if top performer exceeds threshold
            if best_score > self.duplication_threshold:
                actions.append({
                    'manager_id': f"new_duplicate",
                    'action': ExecutiveActionType.DUPLICATE.value,
                    'source_manager_id': best_manager_id,
                    'reason': f"Top performer with score {best_score:.2f}"
                })

        # Record actions in history
        self.action_history.append({
            'timestamp': datetime.now().isoformat(),
            'actions': actions
        })

        logger.info(f"Decided {len(actions)} actions")
        return actions

    @action
    async def identify_duplication_candidates(
        self,
        progress_reports: Dict[str, Dict[str, Any]],
        max_duplicates: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Identify managers that should be duplicated.

        Args:
            progress_reports: Progress reports from all managers
            max_duplicates: Maximum number of duplications to suggest

        Returns:
            List of duplication recommendations
        """
        logger.info("Identifying duplication candidates...")

        candidates = []

        for manager_id, progress in progress_reports.items():
            best_score = progress.get('best_score', float('-inf'))
            tasks_completed = progress.get('tasks_completed', 0)
            designs_generated = progress.get('designs_generated', 0)

            # Good candidate if: high score, productive, generating designs
            if (best_score > self.duplication_threshold and
                tasks_completed > 5 and
                designs_generated > 0):

                candidates.append({
                    'manager_id': manager_id,
                    'score': best_score,
                    'tasks': tasks_completed,
                    'designs': designs_generated,
                    'target_name': progress.get('target_name', 'Unknown')
                })

        # Sort by score and return top candidates
        candidates.sort(key=lambda x: x['score'], reverse=True)

        logger.info(f"Found {len(candidates)} duplication candidates")
        return candidates[:max_duplicates]

    @action
    async def identify_replacement_candidates(
        self,
        progress_reports: Dict[str, Dict[str, Any]],
        available_targets: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Identify managers that should be replaced with new targets.

        Args:
            progress_reports: Progress reports from all managers
            available_targets: Available targets for replacement

        Returns:
            List of replacement recommendations
        """
        logger.info("Identifying replacement candidates...")

        if not available_targets:
            logger.info("No available targets for replacement")
            return []

        candidates = []

        for manager_id, progress in progress_reports.items():
            best_score = progress.get('best_score', float('-inf'))
            tasks_completed = progress.get('tasks_completed', 0)
            runtime_seconds = progress.get('runtime_seconds', 0)

            # Candidate for replacement if:
            # - Many tasks completed but poor results
            # - Running for a while with no improvement
            if tasks_completed > self.stuck_task_threshold and best_score < -8.0:
                candidates.append({
                    'manager_id': manager_id,
                    'score': best_score,
                    'tasks': tasks_completed,
                    'runtime_hours': runtime_seconds / 3600 if runtime_seconds else 0,
                    'current_target': progress.get('target_name', 'Unknown'),
                    'reason': 'stuck_no_progress'
                })

        # Sort by score (worst first) and match with available targets
        candidates.sort(key=lambda x: x['score'])

        recommendations = []
        for i, candidate in enumerate(candidates):
            if i < len(available_targets):
                candidate['new_target'] = available_targets[i]
                recommendations.append(candidate)

        logger.info(f"Found {len(recommendations)} replacement candidates")
        return recommendations

    @action
    async def generate_strategic_summary(
        self,
        progress_reports: Dict[str, Dict[str, Any]],
        global_best: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate a strategic summary of the workflow state.

        Args:
            progress_reports: Progress reports from all managers
            global_best: Information about the global best binder

        Returns:
            Strategic summary with recommendations
        """
        logger.info("Generating strategic summary...")

        # Calculate aggregate statistics
        total_tasks = sum(p.get('tasks_completed', 0) for p in progress_reports.values())
        total_designs = sum(p.get('designs_generated', 0) for p in progress_reports.values())
        scores = [p.get('best_score', float('-inf')) for p in progress_reports.values()]
        avg_score = sum(scores) / len(scores) if scores else 0

        # Build summary prompt
        prompt = f"""You are an executive agent overseeing a protein binder design campaign.

Research Goal: {self.research_goal}

Current Workflow State:
- Active Managers: {len(progress_reports)}
- Total Tasks Completed: {total_tasks}
- Total Designs Generated: {total_designs}
- Average Best Score: {avg_score:.2f}
- Global Best Score: {global_best.get('score', 'N/A')}
- Global Best Manager: {global_best.get('manager_id', 'N/A')}

Manager Summary:
"""
        for mid, progress in progress_reports.items():
            prompt += f"- {mid} ({progress.get('target_name', 'Unknown')}): "
            prompt += f"score={progress.get('best_score', 'N/A'):.2f}, "
            prompt += f"tasks={progress.get('tasks_completed', 0)}, "
            prompt += f"designs={progress.get('designs_generated', 0)}\n"

        prompt += """
Provide a brief strategic assessment including:
1. Overall progress toward research goal
2. Which targets look most promising
3. Recommended strategic adjustments
4. Risk assessment

Keep response concise (3-4 sentences).

Assessment:"""

        try:
            response = self.llm.generate(
                prompt=prompt,
                temperature=0.5,
                max_tokens=300
            )

            summary = {
                'timestamp': datetime.now().isoformat(),
                'active_managers': len(progress_reports),
                'total_tasks': total_tasks,
                'total_designs': total_designs,
                'average_score': avg_score,
                'global_best_score': global_best.get('score'),
                'global_best_manager': global_best.get('manager_id'),
                'strategic_assessment': response.strip()
            }

            logger.info(f"Strategic assessment: {response.strip()}")
            return summary

        except Exception as e:
            logger.error(f"Failed to generate strategic summary: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'active_managers': len(progress_reports),
                'total_tasks': total_tasks,
                'total_designs': total_designs,
                'average_score': avg_score,
                'error': str(e)
            }

    @action
    async def reallocate_resources(
        self,
        progress_reports: Dict[str, Dict[str, Any]],
        current_allocations: Dict[str, int]
    ) -> Dict[str, int]:
        """
        Dynamically reallocate resources based on performance.

        Args:
            progress_reports: Progress reports from all managers
            current_allocations: Current node allocations per manager

        Returns:
            New allocation mapping manager_id to nodes
        """
        logger.info("Reallocating resources based on performance...")

        # Calculate performance scores
        scores = {}
        for manager_id, progress in progress_reports.items():
            scores[manager_id] = self._calculate_performance_score(progress)

        total_score = sum(scores.values())
        if total_score == 0:
            # Equal allocation if no scores
            nodes_per = self.total_nodes // len(progress_reports)
            return {mid: nodes_per for mid in progress_reports}

        # Allocate proportionally to performance
        new_allocations = {}
        allocated = 0

        manager_ids = list(progress_reports.keys())
        for mid in manager_ids[:-1]:
            # Calculate proportional allocation
            proportion = scores[mid] / total_score
            nodes = int(proportion * self.total_nodes)
            nodes = max(1, min(nodes, self.total_nodes // 2))  # Min 1, max half
            new_allocations[mid] = nodes
            allocated += nodes

        # Give remainder to last manager
        new_allocations[manager_ids[-1]] = max(1, self.total_nodes - allocated)

        logger.info(f"Reallocated resources: {new_allocations}")
        return new_allocations

