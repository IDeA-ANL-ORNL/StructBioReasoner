"""
Parsl-based Hierarchical Multi-Agent Workflow for Adaptive Binder Design

This workflow implements a three-tier architecture using Parsl for HPC execution
and Academy for agent coordination:

1. Executive Agent: Strategic oversight, manager lifecycle, and guidance
2. Manager Agents: One per RAG hit, running indefinitely on their target
3. Worker Agents: Operational execution (folding, simulation, design)

Flow:
1. Spin up executor
2. Run RAG to identify targets (interacting proteins)
3. Spin up N managers, one for each RAG hit
4. Run managers indefinitely in parallel:
   - Managers periodically report progress to Executive
   - Executive can advise, kill, replace, or duplicate managers
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from parsl import Config, HighThroughputExecutor
from parsl.concurrent import ParslPoolExecutor
from parsl.providers import LocalProvider

from academy.exchange import LocalExchangeFactory, RedisExchangeFactory
from academy.logging import init_logging
from academy.manager import Manager

from ..agents.executive.executive_agent import ExecutiveAgent
from ..agents.manager.manager_agent import ManagerAgent
from ..core.binder_design_system import BinderDesignSystem
from ..utils.llm_interface import alcfLLM

logger = logging.getLogger(__name__)


class ManagerStatus(Enum):
    """Status of a manager agent."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    KILLED = "killed"
    COMPLETED = "completed"


class ExecutiveAction(Enum):
    """Actions the executive can take on managers."""
    CONTINUE = "continue"
    ADVISE = "advise"
    KILL = "kill"
    REPLACE = "replace"
    DUPLICATE = "duplicate"


@dataclass
class WorkflowConfig:
    """Configuration for the hierarchical workflow."""

    # Paths
    config_path: str = "config/binder_config.yaml"
    jnana_config_path: Optional[str] = None
    output_dir: str = "workflow_outputs"

    # Research
    research_goal: str = ""

    # Compute resources
    total_compute_nodes: int = 50
    max_workers_per_node: int = 2
    nodes_per_manager: int = 10

    # Workflow parameters
    max_managers: int = 10
    progress_report_interval: float = 60.0  # seconds
    executive_review_interval: float = 300.0  # seconds (5 min)

    # Stopping criteria
    max_runtime_hours: Optional[float] = None
    target_affinity: float = -15.0  # Stop if any binder reaches this

    # Manager parameters
    max_tasks_per_campaign: int = 100
    min_binder_affinity: float = -10.0

    # Exchange configuration
    use_redis: bool = False
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Parsl configuration
    worker_init_cmd: str = ""
    conda_env: Optional[str] = None


@dataclass
class RAGHit:
    """A single RAG hit representing a target for binder design."""

    target_id: str
    target_name: str
    target_sequence: str
    uniprot_id: Optional[str] = None
    confidence_score: float = 0.0
    rationale: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ManagerState:
    """State tracking for a single Manager agent."""

    manager_id: str
    target: RAGHit
    status: ManagerStatus = ManagerStatus.PENDING
    allocated_nodes: int = 0

    # Progress tracking
    tasks_completed: int = 0
    designs_generated: int = 0
    best_binder: Optional[Dict[str, Any]] = None
    best_score: float = float('-inf')

    # History
    task_history: List[Dict[str, Any]] = field(default_factory=list)
    executive_advice: List[Dict[str, Any]] = field(default_factory=list)

    # Timing
    start_time: Optional[datetime] = None
    last_report_time: Optional[datetime] = None

    # Lineage (for duplicated managers)
    parent_manager_id: Optional[str] = None
    generation: int = 0

    def update_best_binder(self, binder: Dict[str, Any], score: float) -> bool:
        """Update best binder if this one is better."""
        if score > self.best_score:
            self.best_score = score
            self.best_binder = binder
            return True
        return False

    def get_progress_report(self) -> Dict[str, Any]:
        """Generate a progress report for the executive."""
        runtime = None
        if self.start_time:
            runtime = (datetime.now() - self.start_time).total_seconds()

        return {
            'manager_id': self.manager_id,
            'target_id': self.target.target_id,
            'target_name': self.target.target_name,
            'status': self.status.value,
            'tasks_completed': self.tasks_completed,
            'designs_generated': self.designs_generated,
            'best_score': self.best_score,
            'best_binder': self.best_binder,
            'runtime_seconds': runtime,
            'generation': self.generation,
            'recent_advice': self.executive_advice[-3:] if self.executive_advice else [],
        }


@dataclass
class ExecutiveDecision:
    """A decision made by the executive about a manager."""

    manager_id: str
    action: ExecutiveAction
    advice: Optional[str] = None
    new_target: Optional[RAGHit] = None
    source_manager_id: Optional[str] = None  # For duplication
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class WorkflowState:
    """Global workflow state."""

    # RAG results
    rag_strategy: Optional[Dict[str, Any]] = None
    rag_hits: List[RAGHit] = field(default_factory=list)

    # Manager tracking
    manager_states: Dict[str, ManagerState] = field(default_factory=dict)
    manager_counter: int = 0

    # Global best
    best_binder_overall: Optional[Dict[str, Any]] = None
    best_score_overall: float = float('-inf')
    best_manager_id: Optional[str] = None

    # Workflow tracking
    start_time: Optional[datetime] = None
    executive_decisions: List[ExecutiveDecision] = field(default_factory=list)

    def get_active_managers(self) -> List[str]:
        """Get list of active manager IDs."""
        return [
            mid for mid, state in self.manager_states.items()
            if state.status == ManagerStatus.RUNNING
        ]

    def get_next_manager_id(self) -> str:
        """Generate the next manager ID."""
        self.manager_counter += 1
        return f"manager_{self.manager_counter}"

    def update_global_best(self, binder: Dict[str, Any], score: float, manager_id: str) -> bool:
        """Update global best binder if this one is better."""
        if score > self.best_score_overall:
            self.best_score_overall = score
            self.best_binder_overall = binder
            self.best_manager_id = manager_id
            return True
        return False


class ParslHierarchicalWorkflow:
    """
    Parsl-based hierarchical workflow orchestrator for adaptive binder design.

    Uses Parsl's HighThroughputExecutor for HPC-scale parallelism and
    Academy for agent coordination and communication.
    """

    def __init__(self, config: WorkflowConfig):
        """
        Initialize the workflow.

        Args:
            config: Workflow configuration
        """
        self.config = config
        self.state = WorkflowState()

        # System components (initialized in start())
        self.binder_system: Optional[BinderDesignSystem] = None
        self.academy_manager: Optional[Manager] = None
        self.parsl_executor: Optional[ParslPoolExecutor] = None

        # Agent handles
        self.executive_handle = None
        self.manager_handles: Dict[str, Any] = {}

        # Control flags
        self._shutdown_requested = False
        self._manager_tasks: Dict[str, asyncio.Task] = {}

        # Create output directory
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)

        logger.info(f"ParslHierarchicalWorkflow initialized")

    def _create_parsl_config(self) -> Config:
        """Create Parsl configuration for HPC execution."""
        worker_init = self.config.worker_init_cmd
        if self.config.conda_env:
            worker_init = f"cd {os.getcwd()}; conda activate {self.config.conda_env}; {worker_init}"

        return Config(
            executors=[
                HighThroughputExecutor(
                    provider=LocalProvider(
                        worker_init=worker_init if worker_init else None,
                    ),
                    max_workers_per_node=self.config.max_workers_per_node,
                ),
            ],
        )

    def _create_exchange_factory(self):
        """Create the appropriate exchange factory."""
        if self.config.use_redis:
            return RedisExchangeFactory(
                self.config.redis_host,
                self.config.redis_port
            )
        return LocalExchangeFactory()

    async def start(self):
        """Start all workflow components."""
        logger.info("=" * 80)
        logger.info("STARTING PARSL HIERARCHICAL WORKFLOW")
        logger.info("=" * 80)

        # Initialize logging
        init_logging(logging.INFO)

        # Step 1: Initialize BinderDesignSystem
        logger.info("Step 1: Initializing BinderDesignSystem...")
        self.binder_system = BinderDesignSystem(
            config_path=self.config.config_path,
            jnana_config_path=self.config.jnana_config_path,
            research_goal=self.config.research_goal,
            enable_agents=[
                'computational_design',
                'molecular_dynamics',
                'rag',
                'structure_prediction'
            ]
        )
        await self.binder_system.start()
        logger.info("BinderDesignSystem initialized")

        # Step 2: Initialize Parsl executor
        logger.info("Step 2: Initializing Parsl executor...")
        parsl_config = self._create_parsl_config()
        self.parsl_executor = ParslPoolExecutor(parsl_config)
        logger.info(f"Parsl executor initialized with {self.config.max_workers_per_node} workers/node")

        # Step 3: Initialize Academy Manager
        logger.info("Step 3: Initializing Academy Manager...")
        exchange_factory = self._create_exchange_factory()
        self.academy_manager = await Manager.from_exchange_factory(
            factory=exchange_factory,
            executors=self.parsl_executor,
        )
        await self.academy_manager.__aenter__()
        logger.info("Academy Manager initialized")

        # Step 4: Launch Executive Agent
        logger.info("Step 4: Launching Executive Agent...")
        await self._launch_executive()
        logger.info("Executive Agent launched")

        self.state.start_time = datetime.now()
        logger.info("Workflow startup complete")

    async def _launch_executive(self):
        """Launch the Executive Agent."""
        rag_agent = self.binder_system.design_agents.get('rag')
        folding_agent = self.binder_system.design_agents.get('structure_prediction')
        md_agent = self.binder_system.design_agents.get('molecular_dynamics')

        target_name = self.binder_system._extract_target_name(self.config.research_goal)
        target_seq = self.binder_system._extract_target_sequence(self.config.research_goal)

        if not rag_agent:
            logger.warning("RAG agent not available - workflow may be limited")

        self.executive_handle = await self.academy_manager.launch(
            ExecutiveAgent,
            args=(
                self.config.research_goal,
                target_name,
                target_seq,
                rag_agent,
                folding_agent,
                md_agent,
                alcfLLM(),
                self.config.total_compute_nodes,
                {
                    'max_tasks_per_campaign': self.config.max_tasks_per_campaign,
                    'min_binder_affinity': self.config.min_binder_affinity,
                }
            )
        )

    async def run(self) -> Dict[str, Any]:
        """
        Run the hierarchical workflow.

        Returns:
            Complete workflow results
        """
        logger.info("=" * 80)
        logger.info("BEGINNING WORKFLOW EXECUTION")
        logger.info(f"Research Goal: {self.config.research_goal}")
        logger.info("=" * 80)

        # Set research goal in binder system
        session_id = await self.binder_system.set_research_goal(
            self.config.research_goal
        )
        logger.info(f"Research goal set (session: {session_id})")

        # Phase 1: Run RAG to get targets
        await self._execute_rag_phase()

        # Phase 2: Spin up managers for each RAG hit
        await self._spawn_initial_managers()

        # Phase 3: Run managers indefinitely with executive oversight
        await self._run_manager_loop()

        # Compile final results
        return self._compile_final_results()

    async def _execute_rag_phase(self):
        """Execute HiPerRAG to identify targets."""
        logger.info("=" * 80)
        logger.info("PHASE 1: RAG TARGET IDENTIFICATION")
        logger.info("=" * 80)

        # Query RAG for strategy and targets
        self.state.rag_strategy = await self.executive_handle.query_hiper_rag(
            self.config.research_goal
        )
        logger.info("HiPerRAG strategy obtained")

        # Parse RAG hits into structured targets
        self.state.rag_hits = self._parse_rag_hits(self.state.rag_strategy)

        logger.info(f"Identified {len(self.state.rag_hits)} targets from RAG:")
        for i, hit in enumerate(self.state.rag_hits):
            logger.info(f"  {i+1}. {hit.target_name} ({hit.target_id}): {hit.rationale[:80]}...")

    def _parse_rag_hits(self, rag_strategy: Dict[str, Any]) -> List[RAGHit]:
        """Parse RAG strategy response into structured hits."""
        hits = []

        # Extract from rag_strategy structure
        strategy_data = rag_strategy.get('rag_strategy', {})

        # Get interacting proteins from RAG response
        uniprot_ids = strategy_data.get('interacting_protein_uniprot_ids', [])
        sequences = strategy_data.get('sequences', [])

        # Also check for protein names if available
        protein_names = strategy_data.get('interacting_protein_names', [])
        rationales = strategy_data.get('interaction_rationales', [])

        for i, uniprot_id in enumerate(uniprot_ids):
            sequence = sequences[i] if i < len(sequences) else ""
            name = protein_names[i] if i < len(protein_names) else f"Protein_{uniprot_id}"
            rationale = rationales[i] if i < len(rationales) else "Identified by RAG analysis"

            hit = RAGHit(
                target_id=f"target_{i}",
                target_name=name,
                target_sequence=sequence,
                uniprot_id=uniprot_id,
                confidence_score=1.0 - (i * 0.1),  # Higher rank = higher confidence
                rationale=rationale,
                metadata={'rag_rank': i}
            )
            hits.append(hit)

        # Limit to max_managers
        return hits[:self.config.max_managers]

    async def _spawn_initial_managers(self):
        """Spawn one manager per RAG hit."""
        logger.info("=" * 80)
        logger.info("PHASE 2: SPAWNING MANAGERS")
        logger.info("=" * 80)

        # Calculate nodes per manager
        num_targets = len(self.state.rag_hits)
        nodes_per_manager = min(
            self.config.nodes_per_manager,
            self.config.total_compute_nodes // max(1, num_targets)
        )

        # Spawn managers in parallel
        spawn_tasks = []
        for hit in self.state.rag_hits:
            task = self._spawn_manager(hit, nodes_per_manager)
            spawn_tasks.append(task)

        await asyncio.gather(*spawn_tasks)

        logger.info(f"Spawned {len(self.state.manager_states)} managers")

    async def _spawn_manager(
        self,
        target: RAGHit,
        allocated_nodes: int,
        parent_id: Optional[str] = None,
        generation: int = 0
    ) -> str:
        """
        Spawn a new manager for a target.

        Args:
            target: The RAG hit to assign to this manager
            allocated_nodes: Compute nodes to allocate
            parent_id: Parent manager ID if this is a duplicate
            generation: Generation number for lineage tracking

        Returns:
            The new manager's ID
        """
        manager_id = self.state.get_next_manager_id()

        # Create manager state
        manager_state = ManagerState(
            manager_id=manager_id,
            target=target,
            allocated_nodes=allocated_nodes,
            parent_manager_id=parent_id,
            generation=generation,
            start_time=datetime.now(),
        )
        self.state.manager_states[manager_id] = manager_state

        # Prepare worker handles
        worker_handles = await self._prepare_worker_handles()

        # Launch manager agent
        manager_handle = await self.academy_manager.launch(
            ManagerAgent,
            args=(
                manager_id,
                allocated_nodes,
                worker_handles,
                alcfLLM(),
                {
                    'max_tasks_per_campaign': self.config.max_tasks_per_campaign,
                    'min_binder_affinity': self.config.min_binder_affinity,
                    'temperature': 0.5,
                    'target': {
                        'id': target.target_id,
                        'name': target.target_name,
                        'sequence': target.target_sequence,
                    }
                }
            )
        )

        self.manager_handles[manager_id] = manager_handle
        manager_state.status = ManagerStatus.RUNNING

        logger.info(
            f"Spawned {manager_id} for target '{target.target_name}' "
            f"with {allocated_nodes} nodes (gen {generation})"
        )

        return manager_id

    async def _prepare_worker_handles(self) -> Dict[str, Any]:
        """Prepare handles to worker agents."""
        return {
            'folding': self.binder_system.design_agents.get('structure_prediction'),
            'simulation': self.binder_system.design_agents.get('molecular_dynamics'),
            'binder_design': self.binder_system.design_agents.get('computational_design'),
            'free_energy': self.binder_system.design_agents.get('free_energy'),
        }

    async def _run_manager_loop(self):
        """
        Main loop: run managers indefinitely with executive oversight.

        Managers run their campaigns continuously. The executive periodically
        reviews progress and can advise, kill, replace, or duplicate managers.
        """
        logger.info("=" * 80)
        logger.info("PHASE 3: CONTINUOUS OPTIMIZATION")
        logger.info("=" * 80)

        # Start all manager campaign tasks
        for manager_id in self.state.get_active_managers():
            self._start_manager_task(manager_id)

        # Main oversight loop
        last_executive_review = datetime.now()

        while not self._should_stop():
            # Wait for next check interval
            await asyncio.sleep(self.config.progress_report_interval)

            # Collect progress reports from all managers
            progress_reports = await self._collect_progress_reports()

            # Log progress
            self._log_progress(progress_reports)

            # Check if it's time for executive review
            time_since_review = (datetime.now() - last_executive_review).total_seconds()
            if time_since_review >= self.config.executive_review_interval:
                await self._executive_review(progress_reports)
                last_executive_review = datetime.now()

            # Handle any completed/failed manager tasks
            await self._handle_completed_tasks()

        logger.info("Manager loop ended")

    def _start_manager_task(self, manager_id: str):
        """Start a manager's campaign as an async task."""
        if manager_id in self._manager_tasks:
            # Already running
            return

        task = asyncio.create_task(
            self._run_manager_campaign(manager_id),
            name=f"campaign_{manager_id}"
        )
        self._manager_tasks[manager_id] = task

    async def _run_manager_campaign(self, manager_id: str):
        """
        Run a single manager's campaign indefinitely.

        The manager continuously decides and executes tasks until
        it's killed by the executive or the workflow stops.
        """
        manager_state = self.state.manager_states[manager_id]
        manager_handle = self.manager_handles[manager_id]

        current_state = {
            'seed_binder': manager_state.best_binder,
            'research_goal': self.config.research_goal,
            'target': {
                'id': manager_state.target.target_id,
                'name': manager_state.target.target_name,
                'sequence': manager_state.target.target_sequence,
            }
        }

        while manager_state.status == ManagerStatus.RUNNING and not self._shutdown_requested:
            try:
                # Check for executive advice
                if manager_state.executive_advice:
                    latest_advice = manager_state.executive_advice[-1]
                    current_state['executive_advice'] = latest_advice.get('advice')

                # Manager decides next task
                next_task = await manager_handle.decide_next_task(current_state)

                if next_task == 'stop':
                    logger.info(f"{manager_id}: Manager decided to stop")
                    manager_state.status = ManagerStatus.COMPLETED
                    break

                # Execute the task
                task_result = await self._execute_task(
                    manager_handle,
                    next_task,
                    current_state,
                    manager_state
                )

                if task_result:
                    current_state[next_task] = task_result
                    manager_state.tasks_completed += 1
                    manager_state.task_history.append({
                        'task': next_task,
                        'timestamp': datetime.now().isoformat(),
                        'success': True,
                    })

                    # Check for binder results
                    if next_task == 'binder_design':
                        await self._process_binder_result(manager_id, task_result)

                manager_state.last_report_time = datetime.now()

            except asyncio.CancelledError:
                logger.info(f"{manager_id}: Campaign cancelled")
                break
            except Exception as e:
                logger.error(f"{manager_id}: Task failed with error: {e}")
                manager_state.task_history.append({
                    'task': next_task if 'next_task' in dir() else 'unknown',
                    'timestamp': datetime.now().isoformat(),
                    'success': False,
                    'error': str(e),
                })
                await asyncio.sleep(5)  # Brief pause before retrying

        logger.info(f"{manager_id}: Campaign ended with status {manager_state.status.value}")

    async def _execute_task(
        self,
        manager_handle,
        task_type: str,
        current_state: Dict[str, Any],
        manager_state: ManagerState
    ) -> Optional[Dict[str, Any]]:
        """Execute a specific task for a Manager."""
        params = self._build_task_params(task_type, current_state, manager_state)

        task_methods = {
            'folding': manager_handle.execute_folding,
            'simulation': manager_handle.execute_simulation,
            'clustering': manager_handle.execute_clustering,
            'hotspot_analysis': manager_handle.execute_hotspot_analysis,
            'binder_design': manager_handle.execute_binder_design,
        }

        method = task_methods.get(task_type)
        if not method:
            logger.warning(f"Unknown task type: {task_type}")
            return None

        return await method(params)

    def _build_task_params(
        self,
        task_type: str,
        current_state: Dict[str, Any],
        manager_state: ManagerState
    ) -> Dict[str, Any]:
        """Build parameters for a task based on current state."""
        target = manager_state.target

        param_builders = {
            'folding': lambda: {
                'sequences': [target.target_sequence],
                'names': [target.target_name],
                'constraints': {},
            },
            'simulation': lambda: {
                'pdb_path': current_state.get('folding', {}).get('pdb_path', ''),
                'timesteps': 1000000,
                'solvent': 'implicit',
            },
            'clustering': lambda: {
                'trajectory_paths': [
                    r.get('trajectory_path')
                    for r in current_state.get('simulation', [])
                    if r
                ],
                'n_clusters': 5
            },
            'hotspot_analysis': lambda: {
                'simulation_results': current_state.get('simulation', []),
                'cluster_results': current_state.get('clustering')
            },
            'binder_design': lambda: {
                'target_sequence': target.target_sequence,
                'hotspot_residues': current_state.get(
                    'hotspot_analysis', {}
                ).get('hotspots', []),
                'num_designs': 25
            },
        }

        builder = param_builders.get(task_type, lambda: {})
        return builder()

    async def _process_binder_result(self, manager_id: str, result: Dict[str, Any]):
        """Process a binder design result."""
        manager_state = self.state.manager_states[manager_id]

        # Update counts
        num_designs = len(result.get('designs', [result]))
        manager_state.designs_generated += num_designs

        # Check for best binder
        affinity = result.get('affinity', float('-inf'))
        if manager_state.update_best_binder(result, affinity):
            logger.info(
                f"{manager_id}: New best binder with affinity {affinity:.2f}"
            )

            # Update global best
            if self.state.update_global_best(result, affinity, manager_id):
                logger.info(
                    f"NEW GLOBAL BEST: {affinity:.2f} from {manager_id}"
                )

    async def _collect_progress_reports(self) -> Dict[str, Dict[str, Any]]:
        """Collect progress reports from all managers."""
        reports = {}
        for manager_id, state in self.state.manager_states.items():
            if state.status in [ManagerStatus.RUNNING, ManagerStatus.COMPLETED]:
                reports[manager_id] = state.get_progress_report()
        return reports

    def _log_progress(self, reports: Dict[str, Dict[str, Any]]):
        """Log progress summary."""
        logger.info("-" * 60)
        logger.info("PROGRESS REPORT")
        logger.info("-" * 60)

        for manager_id, report in reports.items():
            status_icon = "🟢" if report['status'] == 'running' else "⏹️"
            logger.info(
                f"  {status_icon} {manager_id} [{report['target_name']}]: "
                f"tasks={report['tasks_completed']}, "
                f"designs={report.get('designs_generated', 0)}, "
                f"best={report['best_score']:.2f}"
            )

        if self.state.best_binder_overall:
            logger.info(
                f"  🏆 Global best: {self.state.best_score_overall:.2f} "
                f"from {self.state.best_manager_id}"
            )

    async def _executive_review(self, progress_reports: Dict[str, Dict[str, Any]]):
        """
        Executive reviews all managers and makes decisions.

        The executive can:
        - Advise managers (provide guidance)
        - Kill underperforming managers
        - Replace managers with new targets
        - Duplicate successful managers
        """
        logger.info("=" * 60)
        logger.info("EXECUTIVE REVIEW")
        logger.info("=" * 60)

        # Get executive's decisions
        decisions = await self._get_executive_decisions(progress_reports)

        # Execute decisions
        for decision in decisions:
            await self._execute_decision(decision)
            self.state.executive_decisions.append(decision)

    async def _get_executive_decisions(
        self,
        progress_reports: Dict[str, Dict[str, Any]]
    ) -> List[ExecutiveDecision]:
        """
        Get decisions from the executive agent.

        This queries the executive LLM to analyze progress and decide actions.
        """
        decisions = []

        # Build context for executive
        context = {
            'progress_reports': progress_reports,
            'global_best': {
                'score': self.state.best_score_overall,
                'manager_id': self.state.best_manager_id,
            },
            'available_targets': [
                hit for hit in self.state.rag_hits
                if not any(
                    s.target.target_id == hit.target_id
                    for s in self.state.manager_states.values()
                    if s.status == ManagerStatus.RUNNING
                )
            ],
            'runtime_hours': (datetime.now() - self.state.start_time).total_seconds() / 3600
        }

        # Query executive for evaluation
        evaluations = await self.executive_handle.evaluate_managers(progress_reports)

        # Make lifecycle decisions
        lifecycle = await self.executive_handle.decide_manager_lifecycle(
            evaluations,
            round_num=len(self.state.executive_decisions) + 1
        )

        # Convert to structured decisions
        for manager_id in lifecycle.get('terminate', []):
            decisions.append(ExecutiveDecision(
                manager_id=manager_id,
                action=ExecutiveAction.KILL,
            ))

        # Check for duplication opportunities (top performers)
        active_managers = self.state.get_active_managers()
        if len(active_managers) < self.config.max_managers:
            # Find best performer
            best_manager = max(
                progress_reports.items(),
                key=lambda x: x[1].get('best_score', float('-inf')),
                default=(None, None)
            )
            if best_manager[0] and best_manager[1].get('best_score', float('-inf')) > -12.0:
                decisions.append(ExecutiveDecision(
                    manager_id=self.state.get_next_manager_id(),
                    action=ExecutiveAction.DUPLICATE,
                    source_manager_id=best_manager[0],
                ))

        # Provide advice to continuing managers
        for manager_id in lifecycle.get('continue', []):
            if manager_id in progress_reports:
                report = progress_reports[manager_id]
                # Generate advice based on progress
                advice = self._generate_advice(report, evaluations.get(manager_id, {}))
                if advice:
                    decisions.append(ExecutiveDecision(
                        manager_id=manager_id,
                        action=ExecutiveAction.ADVISE,
                        advice=advice,
                    ))

        return decisions

    def _generate_advice(
        self,
        report: Dict[str, Any],
        evaluation: Dict[str, Any]
    ) -> Optional[str]:
        """Generate advice for a manager based on its progress."""
        advice_parts = []

        # Check if stuck (many tasks but no good binders)
        if report['tasks_completed'] > 20 and report['best_score'] < -8.0:
            advice_parts.append("Consider exploring different hotspot regions")

        # Check if making good progress
        if report['best_score'] > -12.0:
            advice_parts.append("Good progress - focus on refining current best design")

        # Check efficiency
        efficiency = evaluation.get('efficiency', 0)
        if efficiency < 0.3:
            advice_parts.append("Try reducing simulation time to iterate faster")

        return "; ".join(advice_parts) if advice_parts else None

    async def _execute_decision(self, decision: ExecutiveDecision):
        """Execute an executive decision."""
        logger.info(f"Executing decision: {decision.action.value} for {decision.manager_id}")

        if decision.action == ExecutiveAction.KILL:
            await self._kill_manager(decision.manager_id)

        elif decision.action == ExecutiveAction.ADVISE:
            self._advise_manager(decision.manager_id, decision.advice)

        elif decision.action == ExecutiveAction.REPLACE:
            await self._replace_manager(decision.manager_id, decision.new_target)

        elif decision.action == ExecutiveAction.DUPLICATE:
            await self._duplicate_manager(decision.source_manager_id)

    async def _kill_manager(self, manager_id: str):
        """Kill a manager."""
        if manager_id not in self.state.manager_states:
            return

        state = self.state.manager_states[manager_id]
        state.status = ManagerStatus.KILLED

        # Cancel the task
        if manager_id in self._manager_tasks:
            self._manager_tasks[manager_id].cancel()
            try:
                await self._manager_tasks[manager_id]
            except asyncio.CancelledError:
                pass
            del self._manager_tasks[manager_id]

        logger.info(f"Killed {manager_id}")

    def _advise_manager(self, manager_id: str, advice: str):
        """Send advice to a manager."""
        if manager_id not in self.state.manager_states:
            return

        state = self.state.manager_states[manager_id]
        state.executive_advice.append({
            'advice': advice,
            'timestamp': datetime.now().isoformat(),
        })

        logger.info(f"Advised {manager_id}: {advice}")

    async def _replace_manager(self, manager_id: str, new_target: RAGHit):
        """Replace a manager with a new one on a different target."""
        # Kill old manager
        await self._kill_manager(manager_id)

        # Get its allocated nodes
        old_state = self.state.manager_states.get(manager_id)
        nodes = old_state.allocated_nodes if old_state else self.config.nodes_per_manager

        # Spawn new manager
        new_id = await self._spawn_manager(new_target, nodes)
        self._start_manager_task(new_id)

        logger.info(f"Replaced {manager_id} with {new_id} on target {new_target.target_name}")

    async def _duplicate_manager(self, source_manager_id: str):
        """Duplicate a successful manager."""
        if source_manager_id not in self.state.manager_states:
            return

        source_state = self.state.manager_states[source_manager_id]

        # Spawn new manager with same target
        new_id = await self._spawn_manager(
            source_state.target,
            source_state.allocated_nodes,
            parent_id=source_manager_id,
            generation=source_state.generation + 1
        )

        # Copy best binder as seed
        new_state = self.state.manager_states[new_id]
        new_state.best_binder = source_state.best_binder
        new_state.best_score = source_state.best_score

        self._start_manager_task(new_id)

        logger.info(
            f"Duplicated {source_manager_id} as {new_id} "
            f"(gen {new_state.generation})"
        )

    async def _handle_completed_tasks(self):
        """Handle any manager tasks that have completed."""
        completed = []
        for manager_id, task in self._manager_tasks.items():
            if task.done():
                completed.append(manager_id)
                try:
                    await task
                except Exception as e:
                    logger.error(f"{manager_id}: Task ended with error: {e}")

        for manager_id in completed:
            del self._manager_tasks[manager_id]

    def _should_stop(self) -> bool:
        """Check if the workflow should stop."""
        if self._shutdown_requested:
            return True

        # Check runtime limit
        if self.config.max_runtime_hours:
            runtime = (datetime.now() - self.state.start_time).total_seconds() / 3600
            if runtime >= self.config.max_runtime_hours:
                logger.info(f"Max runtime ({self.config.max_runtime_hours}h) reached")
                return True

        # Check target affinity
        if self.state.best_score_overall >= self.config.target_affinity:
            logger.info(
                f"Target affinity ({self.config.target_affinity}) reached: "
                f"{self.state.best_score_overall}"
            )
            return True

        # Check if any managers are still running
        if not self.state.get_active_managers() and not self._manager_tasks:
            logger.info("No active managers remaining")
            return True

        return False

    def _compile_final_results(self) -> Dict[str, Any]:
        """Compile final workflow results."""
        logger.info("=" * 80)
        logger.info("WORKFLOW COMPLETE")
        logger.info("=" * 80)

        runtime = (datetime.now() - self.state.start_time).total_seconds() / 3600

        if self.state.best_binder_overall:
            logger.info(f"Best binder score: {self.state.best_score_overall:.2f}")
            logger.info(f"Best manager: {self.state.best_manager_id}")
        else:
            logger.info("No binders generated")

        logger.info(f"Total runtime: {runtime:.2f} hours")

        return {
            'research_goal': self.config.research_goal,
            'rag_strategy': self.state.rag_strategy,
            'rag_hits': [
                {
                    'target_id': h.target_id,
                    'target_name': h.target_name,
                    'uniprot_id': h.uniprot_id,
                }
                for h in self.state.rag_hits
            ],
            'best_binder_overall': self.state.best_binder_overall,
            'best_score_overall': self.state.best_score_overall,
            'best_manager_id': self.state.best_manager_id,
            'manager_final_states': {
                mid: {
                    'target': state.target.target_name,
                    'status': state.status.value,
                    'best_score': state.best_score,
                    'tasks_completed': state.tasks_completed,
                    'designs_generated': state.designs_generated,
                    'generation': state.generation,
                }
                for mid, state in self.state.manager_states.items()
            },
            'executive_decisions': [
                {
                    'manager_id': d.manager_id,
                    'action': d.action.value,
                    'timestamp': d.timestamp.isoformat(),
                }
                for d in self.state.executive_decisions
            ],
            'runtime_hours': runtime,
            'timestamp': datetime.now().isoformat()
        }

    def request_shutdown(self):
        """Request graceful shutdown of the workflow."""
        logger.info("Shutdown requested")
        self._shutdown_requested = True

    async def stop(self):
        """Stop the workflow and cleanup resources."""
        logger.info("Stopping ParslHierarchicalWorkflow...")

        self._shutdown_requested = True

        # Cancel all manager tasks
        for manager_id, task in self._manager_tasks.items():
            task.cancel()

        # Wait for tasks to finish
        if self._manager_tasks:
            await asyncio.gather(*self._manager_tasks.values(), return_exceptions=True)

        if self.academy_manager:
            await self.academy_manager.__aexit__(None, None, None)

        if self.parsl_executor:
            self.parsl_executor.shutdown()

        if self.binder_system:
            await self.binder_system.stop()

        logger.info("ParslHierarchicalWorkflow stopped")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()


async def run_workflow(config: WorkflowConfig) -> Dict[str, Any]:
    """
    Convenience function to run the workflow.

    Args:
        config: Workflow configuration

    Returns:
        Workflow results
    """
    async with ParslHierarchicalWorkflow(config) as workflow:
        return await workflow.run()


# Example usage
if __name__ == '__main__':
    import asyncio

    config = WorkflowConfig(
        research_goal="Design a binder for SARS-CoV-2 spike protein RBD.",
        config_path="config/binder_config.yaml",
        max_managers=5,
        total_compute_nodes=50,
        max_runtime_hours=24.0,
        target_affinity=-15.0,
        progress_report_interval=60.0,
        executive_review_interval=300.0,
    )

    results = asyncio.run(run_workflow(config))
    print(f"Workflow completed. Best score: {results.get('best_score_overall', 'N/A')}")
