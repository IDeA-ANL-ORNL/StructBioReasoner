from academy.exchange import LocalExchangeFactory
from academy.manager import Manager
from concurrent.futures import ThreadPoolExecutor
import dill as pickle
import asyncio
import logging
import uuid
import numpy as np
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from ...data.protein_hypothesis import ProteinHypothesis, FoldAnalysis
from ...core.base_agent import BaseAgent

class ChaiAgent:
    """"""
    def __init__(self, 
                 agent_id: str,
                 config: dict[str, Any],
                 parsl_config: dict[str, Any]):
        """"""
        self.agent_id = agent_id
        self.config = config
        self.logger = logging.getLogger(__name__)

        self.fasta_dir = Path(self.config.get('fasta_dir', 'fastas'))
        self.fold_dir = Path(self.config.get('fold_dir', 'folds'))

        self.capabilities = [
            'structure_prediction',
            'cofolding'
        ]

        self.parsl_config = parsl_config #self.config.get('parsl', {})
        self.manager = None

    async def initialize(self,
                         data: dict[str, Any]):
        """
        Initialize Chai components.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            from bindcraft.core.agentic_parsl import ForwardFoldingAgent
            from bindcraft.core.folding import Chai
            from parsl import Config
            from ...utils.parsl_settings import LocalSettings

            self.parsl_settings = LocalSettings(**self.parsl_config).config_factory(Path.cwd())
            
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

            # Initialize algorithm instances with required parameters
            chai = Chai(
                fasta_dir=fasta_dir,
                out=fold_dir,
                diffusion_steps=100,
                device=device  # or 'cpu' if GPU not available
            )

            self.manager = await Manager.from_exchange_factory(
                factory=LocalExchangeFactory(),
                executors=ThreadPoolExecutor(),
            )

            await self.manager.__aenter__()

            try:
                # Launch coordinator with handles to other agents
                self.coordinator = await self.manager.launch(
                    ForwardFoldingAgent,
                    args=(chai,
                          self.parsl_settings,
                         ),
                )

            except Exception as e:
                self.logger.exception("An error occurred with the ForwardFoldingAgent")
        except ImportError as e:
            self.logger.error(f'Cannot import Chai components: {e}')
            self.logger.info('Make sure Chai is installed and in PYTHONPATH')
            self.logger.info('Install from: https://github.com/msinclair-py/bindcraft/tree/agent_acad')
            self.initialized = False
            return False

        self.logger.info(f'Successfully imported Chai components.')
        self.initialized = True
        
        return True

    async def is_ready(self,
                       data: dict[str, Any]) -> bool:
        self.logger.info('Checking if we are initialized')
        if not hasattr(self, 'initialized'):
            await self.initialize(data)
        return self.initialized

    async def cleanup(self):
        try:
            if self.manager:
                try:
                    await self.manager.__aexit__(None, None, None)
                    self.logger.info('Academy manager context exited successfully')
                except Exception as e:
                    self.logger.warning(f'Error exiting manager context: {e}')
                finally:
                    self.manager = None
                    delattr(self, 'initialized')

            self.logger.info('Chai agent cleanup completed')

        except Exception as e:
            self.logger.error(f'Chai agent cleanup failed: {e}')

    def get_capabilities(self) -> list[str]:
        return self.capabilities

    async def generate_binder_hypothesis(self, 
                                         data: dict[str, Any]) -> Optional[ProteinHypothesis]:
        """"""
        if not await self.is_ready(data):
            self.logger.error('Chai agent not ready')
            return None

        return await self._generate_binder_hypothesis(data)

    async def _generate_binder_hypothesis(self,
                                          data: dict[str, Any]) -> Optional[ProteinHypothesis]:
        """"""
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
    
    async def collate_results(self,
                              results: list[dict[str, Any]]) -> dict[str, Any]:
        analysis = {'total_models': len(results),
                    'unique_models': len(results[0].keys()),
                    'best_models': [],
                    'scores': {}}
        for result in results:
            best_score = None
            best_model = None
            scores = {}
            for key, val in result.items():
                if best_score == None:
                    best_score = val['scores']['aggregate_score']
                    best_model = val['model']
                elif best_score < val['scores']['aggregate_score']:
                    best_score = val['scores']['aggregate_score']
                    best_model = val['model']

                scores[str(val['model'])] = val['scores']

            analysis['best_models'].append(best_model)
            analysis['scores'] = scores

        return analysis

    async def analyze_hypothesis(self,
                                 hypothesis: ProteinHypothesis,
                                 task_params: dict[str, Any]) -> FoldAnalysis:
        result = await self.generate_binder_hypothesis(task_params)

        # Write result to file
        analysis = FoldAnalysis(
            folding_algorithm='Chai-1',
            unique_models=result['unique_models'], # integer
            total_models=result['total_models'],   # integer
            best_models=result['best_models'],     # list[Path]
            scores=result['scores']                # dict[int, dict[str, float]]
        )                                          # {0: {'aggregate_score': 0.82, ...},
                                                   #  1: {..., 'ptm': 0.92, ...}}

        analysis.confidence_score = self._calculate_confidence(analysis)
        analysis.tools_used = self._get_tools_used()

        return analysis

    def _calculate_confidence(self,
                              analysis: FoldAnalysis) -> float:
        return 0.75

    def _get_tools_used(self) -> list[str]:
        return ['chai']
