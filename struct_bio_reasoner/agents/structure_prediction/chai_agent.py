from academy.exchange import LocalExchangeFactory, RedisExchangeFactory
from academy.manager import Manager
from parsl.concurrent import ParslPoolExecutor
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

from bindcraft.core.agentic_parsl import ForwardFoldingAgent
from bindcraft.core.folding import Chai
from parsl import Config
from ...utils.parsl_settings import AuroraSettings, LocalSettings
from ...core.base_agent import BaseAgent

class ChaiAgent:
    """"""
    def __init__(self, 
                 agent_id: str,
                 experiment: dict[str, Any],
                 config: dict[str, Any],
                 parsl_config: dict[str, Any]):
        """"""
        self.agent_id = agent_id
        
        self.sequences = experiment['sequences']
        self.names = experiment['names']
        self.constraints = experiment['constraints']
        
        self.config = config
        self.logger = logging.getLogger(__name__)

        self.cwd = Path(self.config.get('cwd', '.'))
        self.fasta_dir = self.cwd / self.config.get('fasta_dir', 'fastas')
        self.fold_dir = self.cwd / self.config.get('fold_dir', 'folds')

        self.capabilities = [
            'structure_prediction',
            'cofolding'
        ]

        self.parsl_config = parsl_config
        self.manager = None

    async def initialize(self):
        """
        Initialize Chai components.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            parsl_settings = AuroraSettings(**self.parsl_config).config_factory(Path.cwd())
            local_settings = LocalSettings(**self.parsl_config).config_facory(Path.cwd())
            
            self.fasta_dir.mkdir(exist_ok=True, parents=True)
            self.fold_dir.mkdir(exist_ok=True, parents=True)

            device = self.config.get('device', 'cuda:0')

            # Initialize algorithm instances with required parameters
            chai = Chai(
                fasta_dir=self.fasta_dir,
                out=self.fold_dir,
                diffusion_steps=100,
                device=device  # or 'cpu' if GPU not available
            )
            
            executor = ParslPoolExecutor(parsl_settings)
            self.manager = await Manager.from_exchange_factory(
                factory=RedisExchangeFactory('localhost', 6379),
                executors=executor,
            )

            await self.manager.__aenter__()

            try:
                # Launch coordinator with handles to other agents
                self.coordinator = await self.manager.launch(
                    ForwardFoldingAgent,
                    args=(chai,
                          local_settings,
                         ),
                )

            except Exception as e:
                self.logger.exception("An error occurred with the ForwardFoldingAgent")

        except ImportError as e:
            self.logger.error(f'Cannot import Chai components: {e}')
            self.logger.info('Make sure Chai is installed and in PYTHONPATH')
            self.logger.info('Install from: https://github.com/msinclair-py/bindcraft/tree/agent_acad')
            return False

        self.logger.info(f'Successfully imported Chai components.')
        
        return True

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

            self.logger.info('Chai agent cleanup completed')

        except Exception as e:
            self.logger.error(f'Chai agent cleanup failed: {e}')

    def get_capabilities(self) -> list[str]:
        return self.capabilities

    async def generate_binder_hypothesis(self) -> dict:
        """"""
        # Run the workflow
        results = await self.coordinator.fold_sequences(
            sequences=self.sequences,
            names=self.names,
            constraints=self.constraints,
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

    async def run(self) -> dict:
        if not await self.initialize():
            return {}
        else:
            result = await self.generate_binder_hypothesis()

            # Write result to file
            analysis = {
                'folding_algorithm': 'Chai-1',
                'unique_models': result['unique_models'], # integer
                'total_models': result['total_models'],   # integer
                'best_models': result['best_models'],     # list[Path]
                'scores': result['scores']                # dict[int, dict[str, float]]
            }                                             # {0: {'aggregate_score': 0.82, ...},
                                                          #  1: {..., 'ptm': 0.92, ...}}

            analysis['confidence_score'] = self._calculate_confidence(analysis)
            analysis['tools_used'] = self._get_tools_used()

            return analysis

    def _calculate_confidence(self,
                              analysis: dict[str, Any]) -> float:
        return 0.75

    def _get_tools_used(self) -> list[str]:
        return ['chai']
