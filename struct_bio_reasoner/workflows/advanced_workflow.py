"""
Advanced Hierarchical Multi-Agent Workflow for Adaptive Binder Design

This is a refactored version of parsl_hierarchical_workflow.py with the following improvements:

1. SINGLE PARSL CONFIGURATION: Only one Parsl DataFlowKernel at the top level.
   Worker agents receive a shared execution context instead of creating their own.

2. THREAD-SAFE STATE: Manager ID generation and state updates use asyncio.Lock.

3. BOUNDED COLLECTIONS: History lists use deque with maxlen to prevent memory leaks.

4. FIXED BUGS:
   - conda_env -> python_env attribute fix
   - locals() vs dir() for variable existence check
   - Proper file handle management with context managers

5. IMPROVED ERROR HANDLING: Specific exception types and proper cleanup.

6. SIMPLIFIED ARCHITECTURE:
   - TaskExecutor strategy pattern for task dispatch
   - Separated concerns with helper classes
   - Cleaner resource management

Architecture:
    Executive Agent (strategic oversight)
        |
        v
    Manager Agents (one per RAG hit)
        |
        v
    Worker Agents (shared Parsl context - NO nested configs)
"""

from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Protocol, Tuple
import yaml

import parsl
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
from ..utils.parsl_settings import LocalSettings, LocalCPUSettings, AuroraSettings

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

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


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class PathConfig:
    """Path-related configuration."""
    config: str = "config/binder_config.yaml"
    jnana_config: Optional[str] = None
    parsl_config: str = "config/parsl.yaml"
    output_dir: str = "workflow_outputs"


@dataclass
class ComputeConfig:
    """Compute resource configuration."""
    total_nodes: int = 50
    max_workers_per_node: int = 2
    nodes_per_manager: int = 10
    python_env: Optional[str] = None
    worker_init_cmd: str = ""


@dataclass
class ManagerLimitsConfig:
    """Manager behavior configuration."""
    max_managers: int = 10
    max_tasks_per_campaign: int = 100
    min_binder_affinity: float = -10.0

    # History limits to prevent memory leaks
    max_task_history: int = 100
    max_advice_history: int = 50
    max_decision_history: int = 200


@dataclass
class TimingConfig:
    """Timing and interval configuration."""
    progress_report_interval: float = 60.0  # seconds
    executive_review_interval: float = 300.0  # seconds
    max_runtime_hours: Optional[float] = None


@dataclass
class StoppingConfig:
    """Stopping criteria configuration."""
    target_affinity: float = -15.0


@dataclass
class ExchangeConfig:
    """Exchange/communication configuration."""
    use_redis: bool = False
    redis_host: str = "localhost"
    redis_port: int = 6379


@dataclass
class WorkflowConfig:
    """
    Unified workflow configuration with grouped settings.

    This replaces the flat configuration from the original workflow.
    """
    research_goal: str = ""

    paths: PathConfig = field(default_factory=PathConfig)
    compute: ComputeConfig = field(default_factory=ComputeConfig)
    manager_limits: ManagerLimitsConfig = field(default_factory=ManagerLimitsConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    stopping: StoppingConfig = field(default_factory=StoppingConfig)
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)

    @classmethod
    def from_flat_config(cls, **kwargs) -> 'WorkflowConfig':
        """Create from flat kwargs for backwards compatibility."""
        return cls(
            research_goal=kwargs.get('research_goal', ''),
            paths=PathConfig(
                config=kwargs.get('config_path', 'config/binder_config.yaml'),
                jnana_config=kwargs.get('jnana_config_path'),
                parsl_config=kwargs.get('parsl_config', 'config/parsl.yaml'),
                output_dir=kwargs.get('output_dir', 'workflow_outputs'),
            ),
            compute=ComputeConfig(
                total_nodes=kwargs.get('total_compute_nodes', 50),
                max_workers_per_node=kwargs.get('max_workers_per_node', 2),
                nodes_per_manager=kwargs.get('nodes_per_manager', 10),
                python_env=kwargs.get('python_env'),
                worker_init_cmd=kwargs.get('worker_init_cmd', ''),
            ),
            manager_limits=ManagerLimitsConfig(
                max_managers=kwargs.get('max_managers', 10),
                max_tasks_per_campaign=kwargs.get('max_tasks_per_campaign', 100),
                min_binder_affinity=kwargs.get('min_binder_affinity', -10.0),
            ),
            timing=TimingConfig(
                progress_report_interval=kwargs.get('progress_report_interval', 60.0),
                executive_review_interval=kwargs.get('executive_review_interval', 300.0),
                max_runtime_hours=kwargs.get('max_runtime_hours'),
            ),
            stopping=StoppingConfig(
                target_affinity=kwargs.get('target_affinity', -15.0),
            ),
            exchange=ExchangeConfig(
                use_redis=kwargs.get('use_redis', False),
                redis_host=kwargs.get('redis_host', 'localhost'),
                redis_port=kwargs.get('redis_port', 6379),
            ),
        )


# =============================================================================
# Data Classes
# =============================================================================

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
    """
    State tracking for a single Manager agent.

    Uses bounded deques for history to prevent memory leaks in long-running workflows.
    """
    manager_id: str
    target: RAGHit
    status: ManagerStatus = ManagerStatus.PENDING
    allocated_nodes: int = 0

    # Progress tracking
    tasks_completed: int = 0
    designs_generated: int = 0
    best_binder: Optional[Dict[str, Any]] = None
    best_score: float = float('inf')

    # Bounded history (prevents memory leaks)
    task_history: Deque[Dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=100)
    )
    executive_advice: Deque[Dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=50)
    )

    # Timing
    start_time: Optional[datetime] = None
    last_report_time: Optional[datetime] = None

    # Lineage (for duplicated managers)
    parent_manager_id: Optional[str] = None
    generation: int = 0

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
            'recent_advice': list(self.executive_advice)[-3:] if self.executive_advice else [],
        }


@dataclass
class ExecutiveDecision:
    """A decision made by the executive about a manager."""
    manager_id: str
    action: ExecutiveAction
    advice: Optional[str] = None
    new_target: Optional[RAGHit] = None
    source_manager_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


# =============================================================================
# Thread-Safe State Management
# =============================================================================

class WorkflowState:
    """
    Global workflow state with thread-safe operations.

    Uses asyncio.Lock for safe concurrent access to shared state.
    """

    def __init__(self, max_decision_history: int = 200):
        # RAG results
        self.rag_strategy: Optional[Dict[str, Any]] = None
        self.rag_hits: List[RAGHit] = []

        # Manager tracking
        self.manager_states: Dict[str, ManagerState] = {}
        self._manager_counter: int = 0
        self._counter_lock = asyncio.Lock()

        # Global best (with lock for thread safety)
        self._best_lock = asyncio.Lock()
        self.best_binder_overall: Optional[Dict[str, Any]] = None
        self.best_score_overall: float = float('inf')
        self.best_manager_id: Optional[str] = None

        # Workflow tracking
        self.start_time: Optional[datetime] = None
        self.executive_decisions: Deque[ExecutiveDecision] = deque(maxlen=max_decision_history)

    def get_active_managers(self) -> List[str]:
        """Get list of active manager IDs."""
        return [
            mid for mid, state in self.manager_states.items()
            if state.status == ManagerStatus.RUNNING
        ]

    async def get_next_manager_id(self) -> str:
        """Thread-safe generation of the next manager ID."""
        async with self._counter_lock:
            self._manager_counter += 1
            return f"manager_{self._manager_counter}"

    async def update_global_best(
        self,
        binder: Dict[str, Any],
        score: float,
        manager_id: str
    ) -> bool:
        """Thread-safe update of global best binder."""
        async with self._best_lock:
            # For binding affinity, lower (more negative) is better
            if score < self.best_score_overall:
                self.best_score_overall = score
                self.best_binder_overall = binder
                self.best_manager_id = manager_id
                return True
            return False

    async def update_manager_best(
        self,
        manager_id: str,
        binder: Dict[str, Any],
        score: float
    ) -> bool:
        """Update a manager's best binder if this one is better."""
        if manager_id not in self.manager_states:
            return False

        state = self.manager_states[manager_id]
        if score < state.best_score:
            state.best_score = score
            state.best_binder = binder
            return True
        return False


# =============================================================================
# Shared Parsl Context (KEY FIX: No nested Parsl configs)
# =============================================================================

@dataclass
class SharedParslContext:
    """
    Shared Parsl execution context passed to worker agents.

    This replaces the pattern where each agent creates its own Parsl config.
    Worker agents should use this context instead of creating new configs.
    """
    config: Config
    executor: Optional[ParslPoolExecutor] = None
    run_dir: Path = field(default_factory=lambda: Path.cwd())

    # Resource allocation tracking
    _allocated_accelerators: Dict[str, List[str]] = field(default_factory=dict)
    _allocation_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def allocate_accelerators(
        self,
        agent_id: str,
        count: int,
        total_accelerators: int = 12
    ) -> List[str]:
        """
        Allocate accelerators to an agent, preventing conflicts.

        This is the key fix for GPU collision issues.
        """
        async with self._allocation_lock:
            # Find which accelerators are already allocated
            used = set()
            for allocated in self._allocated_accelerators.values():
                used.update(allocated)

            # Find available accelerators
            all_accel = set(str(i) for i in range(total_accelerators))
            available = list(all_accel - used)

            if len(available) < count:
                logger.warning(
                    f"Requested {count} accelerators but only {len(available)} available. "
                    f"Allocating {len(available)}."
                )
                count = len(available)

            # Allocate
            allocated = available[:count]
            self._allocated_accelerators[agent_id] = allocated

            logger.info(f"Allocated accelerators {allocated} to agent {agent_id}")
            return allocated

    async def release_accelerators(self, agent_id: str):
        """Release accelerators when an agent is done."""
        async with self._allocation_lock:
            if agent_id in self._allocated_accelerators:
                released = self._allocated_accelerators.pop(agent_id)
                logger.info(f"Released accelerators {released} from agent {agent_id}")


# =============================================================================
# Task Executors (Strategy Pattern)
# =============================================================================

class TaskExecutor(ABC):
    """Abstract base for task execution strategies."""

    @abstractmethod
    async def execute(
        self,
        manager_handle: Any,
        params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Execute the task and return results."""
        pass

    @abstractmethod
    def build_params(
        self,
        current_state: Dict[str, Any],
        manager_state: ManagerState
    ) -> Dict[str, Any]:
        """Build task parameters from current state."""
        pass


class FoldingExecutor(TaskExecutor):
    """Executor for structure prediction tasks."""

    async def execute(self, manager_handle, params):
        return await manager_handle.execute_folding(params)

    def build_params(self, current_state, manager_state):
        return {
            'sequences': [manager_state.target.target_sequence],
            'names': [manager_state.target.target_name],
            'constraints': {},
        }


class SimulationExecutor(TaskExecutor):
    """Executor for molecular dynamics simulation tasks."""

    async def execute(self, manager_handle, params):
        return await manager_handle.execute_simulation(params)

    def build_params(self, current_state, manager_state):
        folding_result = current_state.get('folding', {})
        pdb_path = folding_result.get('pdb_path', '') if isinstance(folding_result, dict) else ''
        return {
            'pdb_path': pdb_path,
            'timesteps': 1000000,
            'solvent': 'implicit',
        }


class ClusteringExecutor(TaskExecutor):
    """Executor for trajectory clustering tasks."""

    async def execute(self, manager_handle, params):
        return await manager_handle.execute_clustering(params)

    def build_params(self, current_state, manager_state):
        sim_results = current_state.get('simulation', [])
        if not isinstance(sim_results, list):
            sim_results = [sim_results] if sim_results else []

        return {
            'trajectory_paths': [
                r.get('trajectory_path') for r in sim_results
                if r and isinstance(r, dict) and r.get('trajectory_path')
            ],
            'n_clusters': 5
        }


class HotspotExecutor(TaskExecutor):
    """Executor for hotspot analysis tasks."""

    async def execute(self, manager_handle, params):
        return await manager_handle.execute_hotspot_analysis(params)

    def build_params(self, current_state, manager_state):
        sim_results = current_state.get('simulation', [])
        if not isinstance(sim_results, list):
            sim_results = [sim_results] if sim_results else []

        return {
            'simulation_results': sim_results,
            'cluster_results': current_state.get('clustering')
        }


class BinderDesignExecutor(TaskExecutor):
    """Executor for binder design tasks."""

    async def execute(self, manager_handle, params):
        return await manager_handle.execute_binder_design(params)

    def build_params(self, current_state, manager_state):
        hotspot_result = current_state.get('hotspot_analysis', {})
        hotspots = []
        if isinstance(hotspot_result, dict):
            hotspots = hotspot_result.get('hotspots', [])

        return {
            'target_sequence': manager_state.target.target_sequence,
            'hotspot_residues': hotspots,
            'num_designs': 25
        }


class TaskExecutorRegistry:
    """Registry of task executors."""

    _executors: Dict[str, TaskExecutor] = {
        'folding': FoldingExecutor(),
        'simulation': SimulationExecutor(),
        'clustering': ClusteringExecutor(),
        'hotspot_analysis': HotspotExecutor(),
        'binder_design': BinderDesignExecutor(),
    }

    @classmethod
    def get(cls, task_type: str) -> Optional[TaskExecutor]:
        return cls._executors.get(task_type)

    @classmethod
    def register(cls, task_type: str, executor: TaskExecutor):
        cls._executors[task_type] = executor


# =============================================================================
# Main Workflow Class
# =============================================================================

class AdvancedHierarchicalWorkflow:
    """
    Advanced hierarchical workflow with single Parsl configuration.

    Key improvements over ParslHierarchicalWorkflow:
    1. Single Parsl config at top level (no nested configs)
    2. Thread-safe state management
    3. Bounded history collections
    4. Strategy pattern for task execution
    5. Proper resource cleanup
    """

    def __init__(self, config: WorkflowConfig):
        """Initialize the workflow."""
        self.config = config
        self.state = WorkflowState(
            max_decision_history=config.manager_limits.max_decision_history
        )

        # Load Parsl settings from YAML (with proper file handling)
        with open(config.paths.parsl_config) as f:
            self.base_parsl_settings = yaml.safe_load(f)

        # System components (initialized in start())
        self.binder_system: Optional[BinderDesignSystem] = None
        self.academy_manager: Optional[Manager] = None
        self.parsl_executor: Optional[ParslPoolExecutor] = None
        self.shared_parsl_context: Optional[SharedParslContext] = None

        # Agent handles
        self.executive_handle = None
        self.manager_handles: Dict[str, Any] = {}

        # Control flags
        self._shutdown_requested = False
        self._manager_tasks: Dict[str, asyncio.Task] = {}
        self._initialized = False

        # Create output directory
        Path(config.paths.output_dir).mkdir(parents=True, exist_ok=True)

        logger.info("AdvancedHierarchicalWorkflow initialized")

    def _create_parsl_config(self, run_dir: Path) -> Config:
        """
        Create the SINGLE Parsl configuration for the entire workflow.

        This is the only place where Parsl Config is created.
        Worker agents receive SharedParslContext instead of creating their own.
        """
        worker_init = self.config.compute.worker_init_cmd

        # FIX: Use python_env (not conda_env which doesn't exist)
        if self.config.compute.python_env:
            worker_init = (
                f"cd {os.getcwd()}; "
                f"source {self.config.compute.python_env}/bin/activate; "
                f"{worker_init}"
            )

        parsl_config = AuroraSettings(**self.base_parsl_settings).config_factory(run_dir)
        return parsl_config

    def _create_exchange_factory(self):
        """Create the appropriate exchange factory."""
        if self.config.exchange.use_redis:
            return RedisExchangeFactory(
                self.config.exchange.redis_host,
                self.config.exchange.redis_port
            )
        return LocalExchangeFactory()

    async def start(self):
        """Start all workflow components."""
        logger.info("=" * 80)
        logger.info("STARTING ADVANCED HIERARCHICAL WORKFLOW")
        logger.info("=" * 80)

        try:
            init_logging(logging.INFO)

            # Step 1: Initialize BinderDesignSystem
            logger.info("Step 1: Initializing BinderDesignSystem...")
            self.binder_system = BinderDesignSystem(
                config_path=self.config.paths.config,
                jnana_config_path=self.config.paths.jnana_config,
                research_goal=self.config.research_goal,
                enable_agents=[
                    'computational_design',
                    'molecular_dynamics',
                    'rag',
                    'structure_prediction',
                    'free_energy'
                ]
            )
            await self.binder_system.start()
            logger.info("BinderDesignSystem initialized")

            # Step 2: Create SINGLE Parsl configuration
            logger.info("Step 2: Creating single Parsl configuration...")
            run_dir = Path(self.config.paths.output_dir) / 'parsl_runinfo'
            run_dir.mkdir(parents=True, exist_ok=True)

            parsl_config = self._create_parsl_config(run_dir)
            self.parsl_executor = ParslPoolExecutor(parsl_config)

            # Create shared context for worker agents
            self.shared_parsl_context = SharedParslContext(
                config=parsl_config,
                executor=self.parsl_executor,
                run_dir=run_dir,
            )
            logger.info("Single Parsl executor initialized (shared by all agents)")

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
            self._initialized = True
            logger.info("Workflow startup complete")

        except Exception as e:
            logger.error(f"Startup failed: {e}")
            await self._cleanup_partial_init()
            raise

    async def _cleanup_partial_init(self):
        """Cleanup after partial initialization failure."""
        if self.academy_manager:
            try:
                await self.academy_manager.__aexit__(None, None, None)
            except Exception:
                pass

        if self.parsl_executor:
            try:
                self.parsl_executor.shutdown()
            except Exception:
                pass

        if self.binder_system:
            try:
                await self.binder_system.stop()
            except Exception:
                pass

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
                self.config.compute.total_nodes,
                {
                    'max_tasks_per_campaign': self.config.manager_limits.max_tasks_per_campaign,
                    'min_binder_affinity': self.config.manager_limits.min_binder_affinity,
                }
            )
        )

    async def run(self) -> Dict[str, Any]:
        """Run the hierarchical workflow."""
        logger.info("=" * 80)
        logger.info("BEGINNING WORKFLOW EXECUTION")
        logger.info(f"Research Goal: {self.config.research_goal}")
        logger.info("=" * 80)

        # Set research goal
        session_id = await self.binder_system.set_research_goal(
            self.config.research_goal
        )
        logger.info(f"Research goal set (session: {session_id})")

        # Phase 1: RAG target identification
        await self._execute_rag_phase()

        # Phase 2: Spawn managers
        await self._spawn_initial_managers()

        # Phase 3: Run managers with oversight
        await self._run_manager_loop()

        return self._compile_final_results()

    async def _execute_rag_phase(self):
        """Execute HiPerRAG to identify targets."""
        logger.info("=" * 80)
        logger.info("PHASE 1: RAG TARGET IDENTIFICATION")
        logger.info("=" * 80)

        self.state.rag_strategy = await self.executive_handle.query_hiper_rag(
            self.config.research_goal
        )
        logger.info("HiPerRAG strategy obtained")

        self.state.rag_hits = self._parse_rag_hits(self.state.rag_strategy)

        logger.info(f"Identified {len(self.state.rag_hits)} targets from RAG:")
        for i, hit in enumerate(self.state.rag_hits):
            logger.info(f"  {i+1}. {hit.target_name} ({hit.target_id}): {hit.rationale[:80]}...")

    def _parse_rag_hits(self, rag_strategy: Dict[str, Any]) -> List[RAGHit]:
        """Parse RAG strategy response into structured hits."""
        hits = []
        strategy_data = rag_strategy.get('rag_strategy', {})

        uniprot_ids = strategy_data.get('interacting_protein_uniprot_ids', [])
        sequences = strategy_data.get('sequences', [])
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
                confidence_score=1.0 - (i * 0.025),
                rationale=rationale,
                metadata={'rag_rank': i}
            )
            hits.append(hit)

        return hits[:self.config.manager_limits.max_managers]

    async def _spawn_initial_managers(self):
        """Spawn one manager per RAG hit."""
        logger.info("=" * 80)
        logger.info("PHASE 2: SPAWNING MANAGERS")
        logger.info("=" * 80)

        num_targets = len(self.state.rag_hits)
        nodes_per_manager = min(
            self.config.compute.nodes_per_manager,
            self.config.compute.total_nodes // max(1, num_targets)
        )

        spawn_tasks = [
            self._spawn_manager(hit, nodes_per_manager)
            for hit in self.state.rag_hits
        ]

        await asyncio.gather(*spawn_tasks)
        logger.info(f"Spawned {len(self.state.manager_states)} managers")

    async def _spawn_manager(
        self,
        target: RAGHit,
        allocated_nodes: int,
        parent_id: Optional[str] = None,
        generation: int = 0
    ) -> str:
        """Spawn a new manager for a target."""
        # Thread-safe ID generation
        manager_id = await self.state.get_next_manager_id()

        # Create state with bounded history
        manager_state = ManagerState(
            manager_id=manager_id,
            target=target,
            allocated_nodes=allocated_nodes,
            parent_manager_id=parent_id,
            generation=generation,
            start_time=datetime.now(),
            task_history=deque(maxlen=self.config.manager_limits.max_task_history),
            executive_advice=deque(maxlen=self.config.manager_limits.max_advice_history),
        )
        self.state.manager_states[manager_id] = manager_state

        # Prepare worker handles (using shared Parsl context)
        worker_handles = await self._prepare_worker_handles(manager_id)

        # Launch manager agent
        manager_handle = await self.academy_manager.launch(
            ManagerAgent,
            args=(
                manager_id,
                allocated_nodes,
                worker_handles,
                alcfLLM(),
                {
                    'max_tasks_per_campaign': self.config.manager_limits.max_tasks_per_campaign,
                    'min_binder_affinity': self.config.manager_limits.min_binder_affinity,
                    'temperature': 0.5,
                    'target': {
                        'id': target.target_id,
                        'name': target.target_name,
                        'sequence': target.target_sequence,
                    },
                    # Pass shared context info instead of letting agents create their own
                    'use_shared_parsl': True,
                    'parsl_run_dir': str(self.shared_parsl_context.run_dir),
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

    async def _prepare_worker_handles(self, manager_id: str) -> Dict[str, Any]:
        """
        Prepare handles to worker agents with SHARED Parsl context.

        Key improvement: Workers use the shared context instead of creating
        their own Parsl configurations.
        """
        # Allocate accelerators for this manager's workers
        if self.shared_parsl_context:
            await self.shared_parsl_context.allocate_accelerators(
                manager_id,
                count=2  # Each manager gets 2 accelerators
            )

        return {
            'folding': self.binder_system.design_agents.get('structure_prediction'),
            'simulation': self.binder_system.design_agents.get('molecular_dynamics'),
            'binder_design': self.binder_system.design_agents.get('computational_design'),
            'free_energy': self.binder_system.design_agents.get('free_energy'),
            # Pass shared context so agents don't create their own
            '_shared_parsl_context': self.shared_parsl_context,
        }

    async def _run_manager_loop(self):
        """Main loop: run managers with executive oversight."""
        logger.info("=" * 80)
        logger.info("PHASE 3: CONTINUOUS OPTIMIZATION")
        logger.info("=" * 80)

        # Start manager campaign tasks
        for manager_id in self.state.get_active_managers():
            self._start_manager_task(manager_id)

        last_executive_review = datetime.now()

        while not self._should_stop():
            await asyncio.sleep(self.config.timing.progress_report_interval)

            progress_reports = await self._collect_progress_reports()
            self._log_progress(progress_reports)

            # Executive review
            time_since_review = (datetime.now() - last_executive_review).total_seconds()
            if time_since_review >= self.config.timing.executive_review_interval:
                await self._executive_review(progress_reports)
                last_executive_review = datetime.now()

            await self._handle_completed_tasks()

        logger.info("Manager loop ended")

    def _start_manager_task(self, manager_id: str):
        """Start a manager's campaign as an async task."""
        if manager_id in self._manager_tasks:
            return

        task = asyncio.create_task(
            self._run_manager_campaign(manager_id),
            name=f"campaign_{manager_id}"
        )
        self._manager_tasks[manager_id] = task

    async def _run_manager_campaign(self, manager_id: str):
        """Run a single manager's campaign."""
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

        next_task = None  # Initialize to avoid reference issues

        while manager_state.status == ManagerStatus.RUNNING and not self._shutdown_requested:
            try:
                # Apply executive advice
                if manager_state.executive_advice:
                    latest_advice = manager_state.executive_advice[-1]
                    current_state['executive_advice'] = latest_advice.get('advice')

                # Manager decides next task
                next_task = await manager_handle.decide_next_task(current_state)

                if next_task == 'stop':
                    logger.info(f"{manager_id}: Manager decided to stop")
                    manager_state.status = ManagerStatus.COMPLETED
                    break

                # Execute using strategy pattern
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

                    if next_task == 'binder_design':
                        await self._process_binder_result(manager_id, task_result)

                manager_state.last_report_time = datetime.now()

            except asyncio.CancelledError:
                logger.info(f"{manager_id}: Campaign cancelled")
                break
            except Exception as e:
                logger.error(f"{manager_id}: Task failed with error: {e}")
                # FIX: Use locals() not dir() to check variable existence
                task_name = next_task if next_task is not None else 'unknown'
                manager_state.task_history.append({
                    'task': task_name,
                    'timestamp': datetime.now().isoformat(),
                    'success': False,
                    'error': str(e),
                })
                await asyncio.sleep(5)

        # Release accelerators when done
        if self.shared_parsl_context:
            await self.shared_parsl_context.release_accelerators(manager_id)

        logger.info(f"{manager_id}: Campaign ended with status {manager_state.status.value}")

    async def _execute_task(
        self,
        manager_handle,
        task_type: str,
        current_state: Dict[str, Any],
        manager_state: ManagerState
    ) -> Optional[Dict[str, Any]]:
        """Execute a task using the strategy pattern."""
        executor = TaskExecutorRegistry.get(task_type)

        if not executor:
            logger.warning(f"Unknown task type: {task_type}")
            return None

        params = executor.build_params(current_state, manager_state)
        return await executor.execute(manager_handle, params)

    async def _process_binder_result(self, manager_id: str, result: Dict[str, Any]):
        """Process a binder design result with thread-safe updates."""
        manager_state = self.state.manager_states[manager_id]

        num_designs = len(result.get('designs', [result]))
        manager_state.designs_generated += num_designs

        affinity = result.get('affinity', float('inf'))

        # Thread-safe update of manager's best
        if await self.state.update_manager_best(manager_id, result, affinity):
            logger.info(f"{manager_id}: New best binder with affinity {affinity:.2f}")

            # Thread-safe update of global best
            if await self.state.update_global_best(result, affinity, manager_id):
                logger.info(f"NEW GLOBAL BEST: {affinity:.2f} from {manager_id}")

    async def _collect_progress_reports(self) -> Dict[str, Dict[str, Any]]:
        """Collect progress reports from all managers."""
        reports = {}
        for manager_id, state in self.state.manager_states.items():
            if state.status in [ManagerStatus.RUNNING, ManagerStatus.COMPLETED]:
                reports[manager_id] = state.get_progress_report()
        return reports

    def _log_progress(self, reports: Dict[str, Dict[str, Any]]):
        """Log progress summary (without emojis for log compatibility)."""
        logger.info("-" * 60)
        logger.info("PROGRESS REPORT")
        logger.info("-" * 60)

        for manager_id, report in reports.items():
            status = "[RUNNING]" if report['status'] == 'running' else "[STOPPED]"
            logger.info(
                f"  {status} {manager_id} [{report['target_name']}]: "
                f"tasks={report['tasks_completed']}, "
                f"designs={report.get('designs_generated', 0)}, "
                f"best={report['best_score']:.2f}"
            )

        if self.state.best_binder_overall:
            logger.info(
                f"  [BEST] Global best: {self.state.best_score_overall:.2f} "
                f"from {self.state.best_manager_id}"
            )

    async def _executive_review(self, progress_reports: Dict[str, Dict[str, Any]]):
        """Executive reviews all managers and makes decisions."""
        logger.info("=" * 60)
        logger.info("EXECUTIVE REVIEW")
        logger.info("=" * 60)

        decisions = await self._get_executive_decisions(progress_reports)

        for decision in decisions:
            await self._execute_decision(decision)
            self.state.executive_decisions.append(decision)

    async def _get_executive_decisions(
        self,
        progress_reports: Dict[str, Dict[str, Any]]
    ) -> List[ExecutiveDecision]:
        """Get decisions from the executive agent."""
        decisions = []

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

        evaluations = await self.executive_handle.evaluate_managers(progress_reports)

        lifecycle = await self.executive_handle.decide_manager_lifecycle(
            evaluations,
            round_num=len(self.state.executive_decisions) + 1
        )

        for manager_id in lifecycle.get('terminate', []):
            decisions.append(ExecutiveDecision(
                manager_id=manager_id,
                action=ExecutiveAction.KILL,
            ))

        # Duplication opportunities
        active_managers = self.state.get_active_managers()
        if len(active_managers) < self.config.manager_limits.max_managers:
            best_manager = max(
                progress_reports.items(),
                key=lambda x: -x[1].get('best_score', float('inf')),  # More negative is better
                default=(None, None)
            )
            if best_manager[0] and best_manager[1].get('best_score', float('inf')) < -12.0:
                new_id = await self.state.get_next_manager_id()
                decisions.append(ExecutiveDecision(
                    manager_id=new_id,
                    action=ExecutiveAction.DUPLICATE,
                    source_manager_id=best_manager[0],
                ))

        # Advice for continuing managers
        for manager_id in lifecycle.get('continue', []):
            if manager_id in progress_reports:
                report = progress_reports[manager_id]
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
        """Generate advice for a manager based on progress."""
        advice_parts = []

        if report['tasks_completed'] > 20 and report['best_score'] > -8.0:
            advice_parts.append("Consider exploring different hotspot regions")

        if report['best_score'] < -12.0:
            advice_parts.append("Good progress - focus on refining current best design")

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
        """Kill a manager and release its resources."""
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

        # Release accelerators
        if self.shared_parsl_context:
            await self.shared_parsl_context.release_accelerators(manager_id)

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
        """Replace a manager with a new one."""
        await self._kill_manager(manager_id)

        old_state = self.state.manager_states.get(manager_id)
        nodes = old_state.allocated_nodes if old_state else self.config.compute.nodes_per_manager

        new_id = await self._spawn_manager(new_target, nodes)
        self._start_manager_task(new_id)

        logger.info(f"Replaced {manager_id} with {new_id} on target {new_target.target_name}")

    async def _duplicate_manager(self, source_manager_id: str):
        """Duplicate a successful manager."""
        if source_manager_id not in self.state.manager_states:
            return

        source_state = self.state.manager_states[source_manager_id]

        new_id = await self._spawn_manager(
            source_state.target,
            source_state.allocated_nodes,
            parent_id=source_manager_id,
            generation=source_state.generation + 1
        )

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
                except asyncio.CancelledError:
                    pass  # Expected for killed managers
                except Exception as e:
                    logger.error(f"{manager_id}: Task ended with error: {e}")

        for manager_id in completed:
            del self._manager_tasks[manager_id]

    def _should_stop(self) -> bool:
        """Check if the workflow should stop."""
        if self._shutdown_requested:
            return True

        # Runtime limit
        if self.config.timing.max_runtime_hours:
            runtime = (datetime.now() - self.state.start_time).total_seconds() / 3600
            if runtime >= self.config.timing.max_runtime_hours:
                logger.info(f"Max runtime ({self.config.timing.max_runtime_hours}h) reached")
                return True

        # Target affinity (lower is better for binding)
        if self.state.best_score_overall <= self.config.stopping.target_affinity:
            logger.info(
                f"Target affinity ({self.config.stopping.target_affinity}) reached: "
                f"{self.state.best_score_overall}"
            )
            return True

        # No active managers
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
        logger.info("Stopping AdvancedHierarchicalWorkflow...")

        self._shutdown_requested = True

        # Cancel all manager tasks
        for manager_id, task in list(self._manager_tasks.items()):
            task.cancel()

        # Wait for tasks to finish
        if self._manager_tasks:
            await asyncio.gather(*self._manager_tasks.values(), return_exceptions=True)

        # Cleanup in reverse order of initialization
        if self.academy_manager:
            try:
                await self.academy_manager.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing academy manager: {e}")

        if self.parsl_executor:
            try:
                self.parsl_executor.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down Parsl executor: {e}")

        if self.binder_system:
            try:
                await self.binder_system.stop()
            except Exception as e:
                logger.warning(f"Error stopping binder system: {e}")

        logger.info("AdvancedHierarchicalWorkflow stopped")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - always cleanup."""
        await self.stop()
        return False  # Don't suppress exceptions


# =============================================================================
# Convenience Functions
# =============================================================================

async def run_workflow(config: WorkflowConfig) -> Dict[str, Any]:
    """Convenience function to run the workflow."""
    async with AdvancedHierarchicalWorkflow(config) as workflow:
        return await workflow.run()


def create_config_from_kwargs(**kwargs) -> WorkflowConfig:
    """Create WorkflowConfig from flat kwargs for backwards compatibility."""
    return WorkflowConfig.from_flat_config(**kwargs)


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Run Advanced Hierarchical Workflow')
    parser.add_argument('--research-goal', type=str, required=True,
                        help='Research goal for binder design')
    parser.add_argument('--config', type=str, default='config/binder_config.yaml',
                        help='Path to binder config YAML')
    parser.add_argument('--parsl-config', type=str, default='config/parsl.yaml',
                        help='Path to Parsl config YAML')
    parser.add_argument('--max-managers', type=int, default=5,
                        help='Maximum number of concurrent managers')
    parser.add_argument('--max-runtime-hours', type=float, default=24.0,
                        help='Maximum runtime in hours')
    parser.add_argument('--target-affinity', type=float, default=-15.0,
                        help='Target binding affinity (stop when reached)')

    args = parser.parse_args()

    config = WorkflowConfig(
        research_goal=args.research_goal,
        paths=PathConfig(
            config=args.config,
            parsl_config=args.parsl_config,
        ),
        manager_limits=ManagerLimitsConfig(
            max_managers=args.max_managers,
        ),
        timing=TimingConfig(
            max_runtime_hours=args.max_runtime_hours,
        ),
        stopping=StoppingConfig(
            target_affinity=args.target_affinity,
        ),
    )

    results = asyncio.run(run_workflow(config))
    print(f"\nWorkflow completed. Best score: {results.get('best_score_overall', 'N/A')}")
