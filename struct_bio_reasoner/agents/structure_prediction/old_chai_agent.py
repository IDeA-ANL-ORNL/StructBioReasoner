"""
Chai Agent for StructBioReasoner

This agent wraps Chai-1 structure prediction components using the
SharedParslMixin to avoid nested Parsl configuration collisions.
"""

from concurrent.futures import ThreadPoolExecutor
import dill as pickle
import asyncio
import logging
import uuid
import numpy as np
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from datetime import datetime

from academy.exchange import LocalExchangeFactory
from academy.manager import Manager

from ...data.protein_hypothesis import ProteinHypothesis, FoldAnalysis
from ...core.base_agent import BaseAgent
from ..shared_parsl_mixin import SharedParslMixin

if TYPE_CHECKING:
    from ...workflows.advanced_workflow import SharedParslContext


class ChaiAgent(SharedParslMixin):
    """
    Chai-1 structure prediction agent.

    This agent uses SharedParslMixin to support:
    1. Shared Parsl context from workflow (prevents nested config collisions)
    2. Standalone mode for testing (original behavior)
    """

    def __init__(
        self,
        agent_id: str,
        config: Dict[str, Any],
        parsl_config: Dict[str, Any]
    ):
        """
        Initialize Chai agent.

        Args:
            agent_id: Unique identifier for this agent
            config: Agent configuration dictionary
            parsl_config: Parsl configuration dictionary
        """
        # Initialize the mixin
        super().__init__()

        self.agent_id = agent_id
        self.config = config
        self.logger = logging.getLogger(__name__)

        self.fasta_dir = Path(self.config.get('fasta_dir', 'fastas'))
        self.fold_dir = Path(self.config.get('fold_dir', 'folds'))

        self.capabilities = [
            'structure_prediction',
            'cofolding'
        ]

        self.parsl_config = parsl_config
        self.coordinator = None

    async def initialize(
        self,
        data: Optional[Dict[str, Any]] = None,
        shared_context: Optional['SharedParslContext'] = None
    ) -> bool:
        """
        Initialize Chai components.

        Args:
            data: Optional initialization data (may contain parsl overrides, cwd, etc.)
            shared_context: Optional shared Parsl context from workflow

        Returns:
            True if initialization successful, False otherwise
        """
        data = data or {}

        try:
            from bindcraft.core.agentic_parsl import ForwardFoldingAgent
            from bindcraft.core.folding import Chai
            from ...utils.parsl_settings import LocalSettings

            # If shared_context provided, add it to data
            if shared_context is not None:
                data['_shared_parsl_context'] = shared_context

            # Get Parsl settings using the mixin (key fix!)
            parsl_settings = await self._get_parsl_settings(
                data=data,
                shared_context=shared_context,
                settings_class=LocalSettings,
                parsl_config=self.parsl_config,
                agent_id=self.agent_id,
            )

            self.logger.info(f'Parsl settings obtained (shared: {self.is_using_shared_parsl})')

            # Determine working directories
            cwd = data.get('cwd', None)
            if cwd is None:
                fasta_dir = self.fasta_dir
                fold_dir = self.fold_dir
            else:
                fasta_dir = Path(cwd) / 'fastas'
                fold_dir = Path(cwd) / 'folds'

            fasta_dir.mkdir(exist_ok=True, parents=True)
            fold_dir.mkdir(exist_ok=True, parents=True)

            device = self.config.get('device', 'cuda:0')

            # Initialize Chai algorithm
            chai = Chai(
                fasta_dir=fasta_dir,
                out=fold_dir,
                diffusion_steps=100,
                device=device
            )

            # Initialize Academy manager using mixin
            self.manager = await self._initialize_manager()

            try:
                # Launch coordinator
                self.coordinator = await self.manager.launch(
                    ForwardFoldingAgent,
                    args=(chai, parsl_settings),
                )

            except Exception as e:
                self.logger.exception("An error occurred with the ForwardFoldingAgent")
                raise

        except ImportError as e:
            self.logger.error(f'Cannot import Chai components: {e}')
            self.logger.info('Make sure Chai is installed and in PYTHONPATH')
            self.logger.info('Install from: https://github.com/msinclair-py/bindcraft/tree/agent_acad')
            self.initialized = False
            return False

        self.logger.info(f'Successfully imported Chai components.')
        self.initialized = True

        return True

    async def is_ready(
        self,
        data: Optional[Dict[str, Any]] = None,
        shared_context: Optional['SharedParslContext'] = None
    ) -> bool:
        """
        Check if agent is ready, initializing if needed.

        Args:
            data: Optional initialization data
            shared_context: Optional shared Parsl context from workflow

        Returns:
            True if agent is ready
        """
        self.logger.info('Checking if we are initialized')
        if not hasattr(self, 'initialized') or not self.initialized:
            await self.initialize(data, shared_context)
        return self.initialized

    async def cleanup(self):
        """Clean up Chai agent resources."""
        try:
            # Release accelerators if using shared context
            await self._release_accelerators(self.agent_id)

            # Clean up Academy manager using mixin
            await self._cleanup_manager()

            self.coordinator = None
            self.logger.info('Chai agent cleanup completed')

        except Exception as e:
            self.logger.error(f'Chai agent cleanup failed: {e}')

    def get_capabilities(self) -> List[str]:
        """Get agent capabilities."""
        return self.capabilities

    async def generate_binder_hypothesis(
        self,
        data: Dict[str, Any]
    ) -> Optional[ProteinHypothesis]:
        """
        Generate structure predictions.

        Args:
            data: Input data including sequences and optional parsl/context

        Returns:
            Generated hypothesis or None on failure
        """
        # Extract shared context if present
        shared_context = data.pop('_shared_parsl_context', None)

        if not await self.is_ready(data, shared_context):
            self.logger.error('Chai agent not ready')
            return None

        return await self._generate_binder_hypothesis(data)

    async def _generate_binder_hypothesis(
        self,
        data: Dict[str, Any]
    ) -> Optional[ProteinHypothesis]:
        """Internal hypothesis generation."""
        constraints = data.get('constraints', [None] * len(data['sequences']))

        # Run the workflow
        results = await self.coordinator.fold_sequences(
            sequences=data['sequences'],
            names=data['names'],
            constraints=constraints,
        )

        analysis = await self.collate_results(results)

        await self.cleanup()

        return analysis

    async def collate_results(
        self,
        results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Collate folding results."""
        analysis = {
            'total_models': len(results),
            'unique_models': len(results[0].keys()) if results else 0,
            'best_models': [],
            'scores': {}
        }

        for result in results:
            best_score = None
            best_model = None
            scores = {}

            for key, val in result.items():
                if best_score is None:
                    best_score = val['scores']['aggregate_score']
                    best_model = val['model']
                elif best_score < val['scores']['aggregate_score']:
                    best_score = val['scores']['aggregate_score']
                    best_model = val['model']

                scores[str(val['model'])] = val['scores']

            analysis['best_models'].append(best_model)
            analysis['scores'] = scores

        return analysis

    async def analyze_hypothesis(
        self,
        hypothesis: ProteinHypothesis,
        task_params: Dict[str, Any]
    ) -> FoldAnalysis:
        """
        Analyze hypothesis by performing structure prediction.

        Args:
            hypothesis: Input protein hypothesis
            task_params: Task parameters including sequences

        Returns:
            Fold analysis results
        """
        result = await self.generate_binder_hypothesis(task_params)

        analysis = FoldAnalysis(
            folding_algorithm='Chai-1',
            unique_models=result['unique_models'],
            total_models=result['total_models'],
            best_models=result['best_models'],
            scores=result['scores']
        )

        analysis.confidence_score = self._calculate_confidence(analysis)
        analysis.tools_used = self._get_tools_used()

        return analysis

    def _calculate_confidence(self, analysis: FoldAnalysis) -> float:
        """Calculate confidence score for analysis."""
        return 0.75

    def _get_tools_used(self) -> List[str]:
        """Get list of tools used."""
        return ['chai']
