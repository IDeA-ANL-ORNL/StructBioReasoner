#!/usr/bin/env python3
"""
Test script for the Parsl Hierarchical Multi-Agent Workflow

This script demonstrates and tests the hierarchical workflow with:
1. Executive Agent managing multiple Manager Agents
2. Managers running indefinitely on RAG-identified targets
3. Executive providing advice, killing, duplicating, and replacing managers

For testing purposes, this script uses mock agents and a simplified setup.
"""

import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from struct_bio_reasoner.workflows import (
    ParslHierarchicalWorkflow,
    WorkflowConfig,
    WorkflowState,
    ManagerState,
    ManagerStatus,
    RAGHit,
    ExecutiveAction,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Mock Classes for Testing
# =============================================================================

class MockLLM:
    """Mock LLM interface for testing."""

    def __init__(self):
        self.call_count = 0
        self.task_sequence = ['folding', 'simulation', 'hotspot_analysis', 'binder_design']

    def generate(self, prompt: str, temperature: float = 0.5, max_tokens: int = 500) -> str:
        """Generate a mock response based on the prompt."""
        self.call_count += 1
        prompt_lower = prompt.lower()

        # Task decision prompts
        if 'next task' in prompt_lower or 'what should be' in prompt_lower:
            # Cycle through tasks
            task_idx = self.call_count % len(self.task_sequence)
            return self.task_sequence[task_idx]

        # Advice generation prompts
        if 'advice' in prompt_lower:
            if self.call_count % 3 == 0:
                return "NO_ADVICE_NEEDED"
            elif self.call_count % 3 == 1:
                return "Consider exploring different hotspot regions for better binding sites."
            else:
                return "Good progress - focus on refining current best design."

        # Strategic summary prompts
        if 'strategic assessment' in prompt_lower or 'assessment' in prompt_lower:
            return (
                "The campaign is making steady progress. Target ACE2 shows the most promise "
                "with best scores. Consider focusing resources on top performers. "
                "Risk is moderate - some managers may need replacement if progress stalls."
            )

        return "Mock LLM response"

    def generate_with_json_output(
        self,
        prompt: str,
        json_schema: Dict,
        temperature: float = 0.5,
        max_tokens: int = 500
    ) -> List[Dict[str, Any]]:
        """Generate mock JSON output."""
        return [{
            'interacting_protein_uniprot_ids': ['P12345', 'Q67890', 'R11111'],
            'interacting_protein_names': ['ACE2', 'TMPRSS2', 'Furin'],
            'interaction_rationales': [
                'Primary receptor for viral entry',
                'Primes spike protein for fusion',
                'Cleaves spike at S1/S2 boundary'
            ],
            'sequences': [
                'MSSSSWLLLSLVAVTAA...',  # Truncated for brevity
                'MALNSGSPPAIGPYYENHGY...',
                'MELRPWLLWVVAATGTLVLL...',
            ]
        }]


class MockBinderDesignSystem:
    """Mock BinderDesignSystem for testing."""

    def __init__(self):
        self.design_agents = {
            'rag': MockAgentHandle('rag'),
            'structure_prediction': MockAgentHandle('structure_prediction'),
            'molecular_dynamics': MockAgentHandle('molecular_dynamics'),
            'computational_design': MockAgentHandle('computational_design'),
            'free_energy': MockAgentHandle('free_energy'),
        }

    async def start(self):
        logger.info("MockBinderDesignSystem started")

    async def stop(self):
        logger.info("MockBinderDesignSystem stopped")

    async def set_research_goal(self, goal: str) -> str:
        logger.info(f"Research goal set: {goal}")
        return f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def _extract_target_name(self, goal: str) -> str:
        return "SARS-CoV-2 Spike"

    def _extract_target_sequence(self, goal: str) -> str:
        return "MFVFLVLLPLVSSQCVNLTTRTQLPPAYTNS..."


class MockAgentHandle:
    """Mock agent handle for testing."""

    def __init__(self, agent_type: str):
        self.agent_type = agent_type
        self.call_count = 0

    async def generate_rag_hypothesis(self, params: Dict) -> Dict[str, Any]:
        """Mock RAG hypothesis generation."""
        self.call_count += 1
        return {
            'hypothesis': 'Target ACE2 and TMPRSS2 for binder design',
            'confidence': 0.85,
            'sources': ['PMID:12345678', 'PMID:87654321']
        }

    async def fold_sequences(self, sequences: List[str], names: List[str], constraints: Dict) -> Dict[str, Any]:
        """Mock protein folding."""
        self.call_count += 1
        return {
            'pdb_path': f'/tmp/mock_structure_{self.call_count}.pdb',
            'confidence': 0.92,
            'plddt': 85.5
        }

    async def analyze_hypothesis(self, hypothesis: Any, params: Dict) -> Dict[str, Any]:
        """Mock analysis (simulation, design, etc.)."""
        self.call_count += 1

        if self.agent_type == 'molecular_dynamics':
            return {
                'trajectory_path': f'/tmp/mock_traj_{self.call_count}.xtc',
                'rmsd': 2.5,
                'rmsf': [1.2, 1.5, 0.8, 2.1],
                'energy': -12500.0
            }
        elif self.agent_type == 'computational_design':
            # Simulate varying affinities
            import random
            affinity = -8.0 - random.random() * 10  # Range: -8 to -18
            return {
                'binder_sequence': 'MVLSPADKTNVKAAWGKVGAHAGE...',
                'affinity': affinity,
                'confidence': 0.75 + random.random() * 0.2,
                'designs': [{'id': i, 'affinity': affinity - i * 0.5} for i in range(5)]
            }
        else:
            return {
                'result': 'success',
                'data': {'mock': True}
            }


class MockAcademyManager:
    """Mock Academy Manager for testing."""

    def __init__(self):
        self.launched_agents = {}
        self.agent_counter = 0

    async def launch(self, agent_class, args=None) -> 'MockAgentProxy':
        """Launch a mock agent."""
        self.agent_counter += 1
        agent_id = f"agent_{self.agent_counter}"

        # Create a mock agent instance
        if args:
            agent = agent_class(*args)
        else:
            agent = agent_class()

        proxy = MockAgentProxy(agent_id, agent)
        self.launched_agents[agent_id] = proxy

        logger.info(f"Launched mock agent: {agent_id} ({agent_class.__name__})")
        return proxy

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockAgentProxy:
    """Mock proxy for launched agents."""

    def __init__(self, agent_id: str, agent: Any):
        self.agent_id = agent_id
        self.agent = agent

    def __getattr__(self, name: str):
        """Proxy attribute access to the underlying agent."""
        attr = getattr(self.agent, name)
        if callable(attr):
            # Wrap methods to make them async if needed
            async def async_wrapper(*args, **kwargs):
                result = attr(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    return await result
                return result
            return async_wrapper
        return attr


class MockParslExecutor:
    """Mock Parsl executor for testing."""

    def __init__(self):
        self.tasks = []

    def submit(self, fn, *args, **kwargs):
        """Submit a task."""
        future = asyncio.Future()
        future.set_result(fn(*args, **kwargs))
        self.tasks.append(future)
        return future

    def shutdown(self):
        logger.info("MockParslExecutor shutdown")


# =============================================================================
# Test Workflow Class (with mocks injected)
# =============================================================================

class TestableWorkflow(ParslHierarchicalWorkflow):
    """Workflow subclass that uses mocks for testing."""

    def __init__(self, config: WorkflowConfig):
        super().__init__(config)
        self._use_mocks = True

    async def start(self):
        """Start with mock components."""
        logger.info("=" * 80)
        logger.info("STARTING TESTABLE HIERARCHICAL WORKFLOW")
        logger.info("=" * 80)

        # Use mock components
        self.binder_system = MockBinderDesignSystem()
        await self.binder_system.start()
        logger.info("MockBinderDesignSystem initialized")

        self.parsl_executor = MockParslExecutor()
        logger.info("MockParslExecutor initialized")

        self.academy_manager = MockAcademyManager()
        await self.academy_manager.__aenter__()
        logger.info("MockAcademyManager initialized")

        # Launch mock Executive Agent
        await self._launch_mock_executive()
        logger.info("Mock Executive Agent launched")

        self.state.start_time = datetime.now()
        logger.info("Testable workflow startup complete")

    async def _launch_mock_executive(self):
        """Launch a mock executive agent."""
        self.executive_handle = MockExecutiveAgent(
            research_goal=self.config.research_goal,
            llm=MockLLM(),
            total_nodes=self.config.total_compute_nodes
        )

    def _parse_rag_hits(self, rag_strategy: Dict[str, Any]) -> List[RAGHit]:
        """Parse mock RAG hits."""
        # Return predefined test targets
        return [
            RAGHit(
                target_id="target_0",
                target_name="ACE2",
                target_sequence="MSSSSWLLLSLVAVTAAQSTIEEQAKTFLDKFNHEAEDLFYQS...",
                uniprot_id="Q9BYF1",
                confidence_score=0.95,
                rationale="Primary receptor for SARS-CoV-2 entry"
            ),
            RAGHit(
                target_id="target_1",
                target_name="TMPRSS2",
                target_sequence="MALNSGSPPAIGPYYENHGYQPENPYPAQPTVVPTVYEVHPAQ...",
                uniprot_id="O15393",
                confidence_score=0.85,
                rationale="Primes spike protein for membrane fusion"
            ),
            RAGHit(
                target_id="target_2",
                target_name="Furin",
                target_sequence="MELRPWLLWVVAATGTLVLLAADAQGQKVFTNTWAVRIPGGPA...",
                uniprot_id="P09958",
                confidence_score=0.75,
                rationale="Cleaves spike at S1/S2 boundary"
            ),
        ][:self.config.max_managers]

    async def _spawn_manager(
        self,
        target: RAGHit,
        allocated_nodes: int,
        parent_id: Optional[str] = None,
        generation: int = 0
    ) -> str:
        """Spawn a mock manager."""
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

        # Create mock manager
        mock_manager = MockManagerAgent(
            manager_id=manager_id,
            target=target,
            llm=MockLLM()
        )

        self.manager_handles[manager_id] = mock_manager
        manager_state.status = ManagerStatus.RUNNING

        logger.info(
            f"Spawned mock {manager_id} for target '{target.target_name}' "
            f"with {allocated_nodes} nodes (gen {generation})"
        )

        return manager_id


class MockExecutiveAgent:
    """Mock Executive Agent for testing."""

    def __init__(self, research_goal: str, llm: MockLLM, total_nodes: int):
        self.research_goal = research_goal
        self.llm = llm
        self.total_nodes = total_nodes
        self.call_count = 0

    async def query_hiper_rag(self, research_goal: str) -> Dict[str, Any]:
        """Mock RAG query."""
        self.call_count += 1
        return {
            "research_goal": research_goal,
            "rag_strategy": {
                'interacting_protein_uniprot_ids': ['Q9BYF1', 'O15393', 'P09958'],
                'interacting_protein_names': ['ACE2', 'TMPRSS2', 'Furin'],
                'sequences': [
                    'MSSSSWLLLSLVAVTAAQSTIEEQAKTFLDKFNHEAEDLFYQS...',
                    'MALNSGSPPAIGPYYENHGYQPENPYPAQPTVVPTVYEVHPAQ...',
                    'MELRPWLLWVVAATGTLVLLAADAQGQKVFTNTWAVRIPGGPA...',
                ],
                'interaction_rationales': [
                    'Primary receptor for SARS-CoV-2 entry',
                    'Primes spike protein for membrane fusion',
                    'Cleaves spike at S1/S2 boundary',
                ]
            },
            "timestamp": datetime.now().isoformat()
        }

    async def evaluate_managers(self, manager_results: Dict[str, Dict]) -> Dict[str, Any]:
        """Mock manager evaluation."""
        evaluations = {}
        for manager_id, results in manager_results.items():
            score = 0.5 + (results.get('best_score', -10) + 15) / 20
            evaluations[manager_id] = {
                'score': min(1.0, max(0.0, score)),
                'efficiency': 0.7,
                'recommendation': 'continue' if score > 0.4 else 'terminate'
            }
        return evaluations

    async def decide_manager_lifecycle(
        self,
        evaluations: Dict[str, Any],
        round_num: int
    ) -> Dict[str, Any]:
        """Mock lifecycle decisions."""
        continue_list = []
        terminate_list = []

        for manager_id, eval_data in evaluations.items():
            if eval_data.get('score', 0) > 0.3:
                continue_list.append(manager_id)
            else:
                terminate_list.append(manager_id)

        return {
            'continue': continue_list,
            'terminate': terminate_list,
            'round': round_num
        }

    async def select_best_binder(self, manager_results: Dict[str, Dict]) -> Dict[str, Any]:
        """Mock best binder selection."""
        best_score = float('-inf')
        best_binder = None
        best_manager = None

        for manager_id, results in manager_results.items():
            score = results.get('best_score', float('-inf'))
            if score > best_score:
                best_score = score
                best_binder = results.get('best_binder')
                best_manager = manager_id

        return {
            'binder': best_binder,
            'score': best_score,
            'source_manager': best_manager
        }


class MockManagerAgent:
    """Mock Manager Agent for testing."""

    def __init__(self, manager_id: str, target: RAGHit, llm: MockLLM):
        self.manager_id = manager_id
        self.target = target
        self.llm = llm
        self.task_count = 0
        self.best_score = float('-inf')
        self.advice_received = []

        # Simulate task sequence
        self.task_sequence = [
            'folding', 'simulation', 'clustering',
            'hotspot_analysis', 'binder_design',
            'simulation', 'binder_design',
            'binder_design', 'stop'
        ]

    async def decide_next_task(self, current_state: Dict[str, Any]) -> str:
        """Decide next task."""
        # Check for advice
        if 'executive_advice' in current_state and current_state['executive_advice']:
            self.advice_received.append(current_state['executive_advice'])
            logger.info(f"{self.manager_id}: Received advice: {current_state['executive_advice']}")

        if self.task_count >= len(self.task_sequence):
            return 'stop'

        task = self.task_sequence[self.task_count]
        self.task_count += 1
        return task

    async def execute_folding(self, params: Dict) -> Dict[str, Any]:
        """Mock folding execution."""
        await asyncio.sleep(0.1)  # Simulate work
        return {'pdb_path': f'/tmp/{self.manager_id}_structure.pdb', 'plddt': 85.0}

    async def execute_simulation(self, params: Dict) -> Dict[str, Any]:
        """Mock simulation execution."""
        await asyncio.sleep(0.1)
        return {'trajectory_path': f'/tmp/{self.manager_id}_traj.xtc', 'rmsd': 2.3}

    async def execute_clustering(self, params: Dict) -> Dict[str, Any]:
        """Mock clustering execution."""
        await asyncio.sleep(0.05)
        return {'n_clusters': 5, 'representatives': [1, 15, 30, 45, 60]}

    async def execute_hotspot_analysis(self, params: Dict) -> Dict[str, Any]:
        """Mock hotspot analysis."""
        await asyncio.sleep(0.05)
        return {'hotspots': [42, 79, 105, 200], 'scores': [0.9, 0.85, 0.8, 0.75]}

    async def execute_binder_design(self, params: Dict) -> Dict[str, Any]:
        """Mock binder design."""
        import random
        await asyncio.sleep(0.1)

        # Simulate improving scores over time
        base_score = -15.0 + self.task_count * 0.5
        affinity = base_score + random.uniform(-2, 2)

        if affinity > self.best_score:
            self.best_score = affinity

        return {
            'binder_sequence': 'MVLSPADKTNVKAAWGKVGAHAGE...',
            'affinity': affinity,
            'designs': [{'id': i, 'affinity': affinity - i * 0.3} for i in range(5)]
        }

    async def should_stop(self, history: List[Dict]) -> bool:
        """Check if should stop."""
        return self.task_count >= len(self.task_sequence)

    async def summarize_campaign(self) -> Dict[str, Any]:
        """Summarize the campaign."""
        return {
            'manager_id': self.manager_id,
            'target': self.target.target_name,
            'tasks_completed': self.task_count,
            'best_score': self.best_score,
            'advice_received': len(self.advice_received),
            'best_binder': {'affinity': self.best_score}
        }


# =============================================================================
# Test Functions
# =============================================================================

async def test_workflow_initialization():
    """Test workflow initialization."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Workflow Initialization")
    logger.info("=" * 80)

    config = WorkflowConfig(
        research_goal="Design binders for SARS-CoV-2 spike protein",
        config_path="config/test_config.yaml",
        max_managers=3,
        total_compute_nodes=30,
        max_runtime_hours=0.01,  # Very short for testing
        progress_report_interval=2.0,
        executive_review_interval=5.0,
    )

    workflow = TestableWorkflow(config)
    await workflow.start()

    assert workflow.binder_system is not None, "BinderDesignSystem not initialized"
    assert workflow.parsl_executor is not None, "Parsl executor not initialized"
    assert workflow.academy_manager is not None, "Academy manager not initialized"
    assert workflow.executive_handle is not None, "Executive not launched"

    await workflow.stop()
    logger.info("TEST PASSED: Workflow initialization")


async def test_rag_phase():
    """Test RAG target identification phase."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: RAG Target Identification")
    logger.info("=" * 80)

    config = WorkflowConfig(
        research_goal="Design binders for SARS-CoV-2 spike protein",
        max_managers=3,
        total_compute_nodes=30,
        max_runtime_hours=0.01,
    )

    workflow = TestableWorkflow(config)
    await workflow.start()

    # Execute RAG phase
    await workflow._execute_rag_phase()

    assert workflow.state.rag_strategy is not None, "RAG strategy not set"
    assert len(workflow.state.rag_hits) > 0, "No RAG hits found"
    assert len(workflow.state.rag_hits) <= config.max_managers, "Too many RAG hits"

    logger.info(f"Found {len(workflow.state.rag_hits)} targets:")
    for hit in workflow.state.rag_hits:
        logger.info(f"  - {hit.target_name} ({hit.uniprot_id}): {hit.rationale}")

    await workflow.stop()
    logger.info("TEST PASSED: RAG target identification")


async def test_manager_spawning():
    """Test manager spawning."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Manager Spawning")
    logger.info("=" * 80)

    config = WorkflowConfig(
        research_goal="Design binders for SARS-CoV-2 spike protein",
        max_managers=3,
        total_compute_nodes=30,
        max_runtime_hours=0.01,
    )

    workflow = TestableWorkflow(config)
    await workflow.start()

    # Execute RAG and spawn managers
    await workflow._execute_rag_phase()
    await workflow._spawn_initial_managers()

    assert len(workflow.state.manager_states) == len(workflow.state.rag_hits), \
        "Manager count doesn't match RAG hits"

    for manager_id, state in workflow.state.manager_states.items():
        assert state.status == ManagerStatus.RUNNING, f"{manager_id} not running"
        assert state.allocated_nodes > 0, f"{manager_id} has no nodes"
        logger.info(
            f"  {manager_id}: target={state.target.target_name}, "
            f"nodes={state.allocated_nodes}, status={state.status.value}"
        )

    await workflow.stop()
    logger.info("TEST PASSED: Manager spawning")


async def test_full_workflow():
    """Test full workflow execution."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Full Workflow Execution")
    logger.info("=" * 80)

    config = WorkflowConfig(
        research_goal="Design binders for SARS-CoV-2 spike protein",
        max_managers=2,
        total_compute_nodes=20,
        max_runtime_hours=0.005,  # ~18 seconds
        progress_report_interval=1.0,
        executive_review_interval=3.0,
        target_affinity=-20.0,  # Unreachable, so we rely on time limit
    )

    async with TestableWorkflow(config) as workflow:
        results = await workflow.run()

    assert results is not None, "No results returned"
    assert 'research_goal' in results, "Missing research_goal in results"
    assert 'rag_hits' in results, "Missing rag_hits in results"
    assert 'manager_final_states' in results, "Missing manager states in results"

    logger.info("\nWorkflow Results:")
    logger.info(f"  Research Goal: {results['research_goal']}")
    logger.info(f"  RAG Hits: {len(results['rag_hits'])}")
    logger.info(f"  Best Score: {results.get('best_score_overall', 'N/A')}")
    logger.info(f"  Runtime: {results.get('runtime_hours', 0):.4f} hours")

    logger.info("\nManager Final States:")
    for mid, state in results['manager_final_states'].items():
        logger.info(
            f"  {mid}: target={state['target']}, "
            f"status={state['status']}, "
            f"tasks={state['tasks_completed']}, "
            f"best_score={state['best_score']:.2f}"
        )

    logger.info("TEST PASSED: Full workflow execution")


async def test_manager_advice():
    """Test manager receiving and acting on advice."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Manager Advice Handling")
    logger.info("=" * 80)

    from struct_bio_reasoner.agents.manager import ManagerAgent

    # Create a mock manager
    mock_llm = MockLLM()
    mock_workers = {
        'folding': MockAgentHandle('folding'),
        'simulation': MockAgentHandle('simulation'),
        'binder_design': MockAgentHandle('binder_design'),
    }

    manager = ManagerAgent(
        manager_id="test_manager",
        allocated_nodes=10,
        worker_handles=mock_workers,
        llm_interface=mock_llm,
        config={
            'target': {'id': 'test', 'name': 'TestTarget', 'sequence': 'MVLSPAD...'},
            'max_tasks_per_campaign': 10,
        }
    )

    # Test receiving advice
    result = await manager.receive_advice("Consider exploring different hotspot regions")

    assert result['acknowledged'], "Advice not acknowledged"
    assert 'exploration_mode' in result['adjustments'], "Exploration mode not set"
    assert manager.strategy_modifiers['exploration_mode'], "Exploration mode not enabled"

    logger.info(f"Advice result: {result}")

    # Test refinement advice
    result = await manager.receive_advice("Focus on refining current best design")

    assert manager.strategy_modifiers['refinement_mode'], "Refinement mode not enabled"
    assert not manager.strategy_modifiers['exploration_mode'], "Exploration mode should be off"

    logger.info(f"Refinement advice result: {result}")

    # Test advice status
    status = await manager.get_advice_status()
    assert status['total_advice_received'] == 2, "Wrong advice count"

    logger.info(f"Advice status: {status}")
    logger.info("TEST PASSED: Manager advice handling")


async def test_executive_actions():
    """Test executive action decision making."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Executive Actions")
    logger.info("=" * 80)

    executive = MockExecutiveAgent(
        research_goal="Test goal",
        llm=MockLLM(),
        total_nodes=50
    )

    # Mock progress reports
    progress_reports = {
        'manager_1': {
            'target_name': 'ACE2',
            'tasks_completed': 15,
            'best_score': -14.5,
            'designs_generated': 10,
        },
        'manager_2': {
            'target_name': 'TMPRSS2',
            'tasks_completed': 25,
            'best_score': -7.0,  # Poor performer
            'designs_generated': 5,
        },
        'manager_3': {
            'target_name': 'Furin',
            'tasks_completed': 10,
            'best_score': -12.0,
            'designs_generated': 8,
        },
    }

    # Test evaluation
    evaluations = await executive.evaluate_managers(progress_reports)
    logger.info(f"Evaluations: {evaluations}")

    assert 'manager_1' in evaluations, "Missing manager_1 evaluation"
    assert evaluations['manager_1']['score'] > evaluations['manager_2']['score'], \
        "manager_1 should score higher than manager_2"

    # Test lifecycle decisions
    lifecycle = await executive.decide_manager_lifecycle(evaluations, round_num=1)
    logger.info(f"Lifecycle decisions: {lifecycle}")

    assert 'continue' in lifecycle, "Missing continue list"
    assert 'terminate' in lifecycle, "Missing terminate list"

    # Test best binder selection
    best = await executive.select_best_binder(progress_reports)
    logger.info(f"Best binder: {best}")

    assert best['source_manager'] == 'manager_1', "Wrong best manager selected"

    logger.info("TEST PASSED: Executive actions")


async def run_all_tests():
    """Run all tests."""
    logger.info("=" * 80)
    logger.info("RUNNING ALL WORKFLOW TESTS")
    logger.info("=" * 80)

    tests = [
        ("Workflow Initialization", test_workflow_initialization),
        ("RAG Phase", test_rag_phase),
        ("Manager Spawning", test_manager_spawning),
        ("Manager Advice", test_manager_advice),
        ("Executive Actions", test_executive_actions),
        ("Full Workflow", test_full_workflow),
    ]

    results = []
    for name, test_fn in tests:
        try:
            await test_fn()
            results.append((name, "PASSED", None))
        except Exception as e:
            results.append((name, "FAILED", str(e)))
            logger.error(f"Test '{name}' failed: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)

    passed = sum(1 for _, status, _ in results if status == "PASSED")
    failed = sum(1 for _, status, _ in results if status == "FAILED")

    for name, status, error in results:
        icon = "✓" if status == "PASSED" else "✗"
        logger.info(f"  {icon} {name}: {status}")
        if error:
            logger.info(f"      Error: {error}")

    logger.info("-" * 40)
    logger.info(f"  Total: {len(results)}, Passed: {passed}, Failed: {failed}")

    return failed == 0


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Test the hierarchical workflow")
    parser.add_argument(
        '--test',
        choices=['all', 'init', 'rag', 'spawn', 'advice', 'executive', 'full'],
        default='all',
        help='Which test to run'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    test_map = {
        'init': test_workflow_initialization,
        'rag': test_rag_phase,
        'spawn': test_manager_spawning,
        'advice': test_manager_advice,
        'executive': test_executive_actions,
        'full': test_full_workflow,
    }

    if args.test == 'all':
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1)
    else:
        try:
            asyncio.run(test_map[args.test]())
            logger.info(f"\nTest '{args.test}' completed successfully!")
            sys.exit(0)
        except Exception as e:
            logger.error(f"\nTest '{args.test}' failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
