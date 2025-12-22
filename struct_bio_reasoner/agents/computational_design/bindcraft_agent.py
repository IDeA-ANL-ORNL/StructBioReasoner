from academy.exchange import LocalExchangeFactory, RedisExchangeFactory
from academy.manager import Manager
from academy.concurrent import ParslPoolExecutor
from concurrent.futures import ThreadPoolExecutor
import dill as pickle
import asyncio
import logging
import uuid
import numpy as np
import os
from parsl import Config, HighThroughputExecutor
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from jnana.core.model_manager import UnifiedModelManager

from bindcraft.core.coordinators import ParslDesignCoordinator
from bindcraft.core.folding import ChaiBinder
from bindcraft.core.inverse_folding import ProteinMPNN
from bindcraft.analysis.energy import SimpleEnergy
from bindcraft.util.quality_control import SequenceQualityControl
from ...utils.parsl_settings import AuroraSettings

class BindCraftAgent:
    """"""
    def __init__(self, 
                 agent_id: str,
                 config: dict[str, Any],
                 model_manager: UnifiedModelManager,
                 parsl_config: dict[str, Any]):
        """"""
        self.agent_id = agent_id
        self.config = config
        self.model_manager = model_manager
        self.logger = logging.getLogger(__name__)

        self.capabilities = [
            'binder_design',
            'antibody_design',
            'peptide_design'
        ]

        self.fold_backend = config.get('folding', 'chai')
        self.inv_fold_backend = config.get('inverse_folding', 'proteinmpnn')

        self.parsl_config = parsl_config 
        self.manager = None
        self.forward_folder = None
        self.inverse_folder = None
        self.qc_agent = None
        self.analyzer_agent = None

        self.logger.info(f'BindCraft agent using: {self.fold_backend},{self.inv_fold_backend}')

    async def initialize(self):
        """
        Initialize BindCraft components.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            parsl_settings = AuroraSettings(**self.parsl_config).config_factory(Path.cwd())
            local_settings = LocalSettings(**self.parsl_config).config_factory(Path.cwd())

            cwd = Path(self.config.get('cwd', os.getcwd()))
            cwd.mkdir(exist_ok=True)

            self.fasta_dir = cwd / "fastas"
            self.folds_dir = cwd / "folds"
            self.fasta_dir.mkdir(exist_ok=True)
            self.folds_dir.mkdir(exist_ok=True)

            self.target_sequence = self.config['target_sequence']
            self.binder_sequence = self.config.get('binder_sequence', "MKQHKAMIVALIVICITAVVAALVTRKDLCEVHIRTGQTEVAVF")
            self.device = self.config.get('device', 'cuda:0')
            self.num_rounds = self.config.get('num_rounds', 3)

            if_kwargs =  self.config.get('if_kwargs', {
                'num_seq': self.config.get('num_seq', 25),
                'batch_size': self.config.get('batch_size', 250),
                'max_retries': self.config.get('retries', 5),
                'sampling_temp': self.config.get('temp', '0.1'),
                'model_name': self.config.get('mpnn_model', 'v_48_020'),
                'model_weights': self.config.get('mpnn_weights', 'soluble_model_weights'),
                'proteinmpnn_path': self.config.get('proteinmpnn_path', '/eagle/FoundEpidem/avasan/Softwares/ProteinMPNN'),
                'device': device
            })

            if 'device' not in if_kwargs:
                if_kwargs['device'] = device

            qc_kwargs = self.config.get('qc_kwargs', {
                'max_repeat': 4,
                'max_appearance_ratio': 0.33,
                'max_charge': 5,
                'max_charge_ratio': 0.5,
                'max_hydrophobic_ratio': 0.8,
                'min_diversity': 8,
                'bad_motifs': None,
                'bad_n_termini': None # use defaults
            })

            # Initialize algorithm instances with required parameters
            chai = ChaiBinder(
                fasta_dir=self.fasta_dir,
                out=self.folds_dir,
                diffusion_steps=100,
                device=self.device  # or 'cpu' if GPU not available
            )

            proteinmpnn = ProteinMPNN(**if_kwargs)

            qc_alg = SequenceQualityControl(**qc_kwargs)
            energy_alg = SimpleEnergy()

            self.logger.info('Initialized algorithms')

            executor = ParslPoolExecutor(parsl_settings)
            self.manager = await Manager.from_exchange_factory(
                factory=RedisExchangeFactory('localhost', 6379),
                executors=executor,
            )

            await self.manager.__aenter__()

            self.logger.info('Launching bindcraft handles')

            try:
                # Launch coordinator with handles to other agents
                self.coordinator = await self.manager.launch(
                    ParslDesignCoordinator,
                    args=(chai,
                          proteinmpnn,
                          energy_alg,
                          qc_alg,
                          local_settings,
                          if_kwargs['num_seq'], 
                          if_kwargs['max_retries'],
                          -10.,
                         ),
                )

            except Exception as e:
                self.logger.exception("An error occurred with the ParslDesignCoordinator")
        except ImportError as e:
            self.logger.error(f'Cannot import BindCraft components: {e}')
            self.logger.info('Make sure BindCraft is installed and in PYTHONPATH')
            self.logger.info('Install from: https://github.com/msinclair-py/bindcraft/tree/agent_acad')
            return False

        self.logger.info(f'Successfully imported BindCraft components.')
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

            self.logger.info('BindCraft agent cleanup completed')

        except Exception as e:
            self.logger.error(f'BindCraft agent cleanup failed: {e}')

    def write_checkpoint(self, results: dict[str, Any]):
        #Use timestemp tom get unique name
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        checkpoint_file = f'bindcraft_checkpoint_{timestamp}.pkl'
        with open(checkpoint_file, 'wb') as pkl:
            pickle.dump(results, pkl)

        return checkpoint_file

    def get_capabilities(self) -> list[str]:
        return self.capabilities

    async def generate_binders(self) -> dict:
        """"""
        # Run the workflow
        results = await self.coordinator.run_full_workflow(
            target_sequence=self.target_sequence,
            binder_sequence=self.binder_sequence,
            fasta_base_path=self.fasta_dir,
            pdb_base_path=self.folds_dir,
            remodel_indices=None,  # Interface indices to redesign, else measure
            num_rounds=self.num_rounds,
        )

        await self.cleanup()

        return results

    async def get_top_binders(self,
                              cycles: list[dict[str, Any]],
                              n: int=5) -> dict[int, dict[str, Any]]:
        top_binders = []
        for cycle in cycles:
            evaluated = cycle['evaluated_structures']
            for val in evaluated.values():
                if val['energy'] is not None:
                    top_binders.append(val)

                if len(top_binders) > n:
                    worst_energy = -10000
                    worst_binder = None
                    for i, binder in enumerate(top_binders):
                        if binder['energy'] is None:
                            worst_binder = i
                        elif binder['energy'] > worst_energy:
                            worst_energy = binder['energy']
                            worst_binder = i

                    _ = top_binders.pop(i)

        energies = [binder['energy'] for binder in top_binders]
        order = np.argsort(energies)

        top_dict = {i: top_binders[idx] for i, idx in enumerate(order)}

        return top_dict

    async def run(self) -> dict:
        if not await self.initialize():
            return {}
        else:
            result = await self.generate_binders()

            # Write result to file
            all_cycles = result['all_cycles']
            passing_structures = sum(
                [len(all_cycles[i]['passing_structures']) for i in range(len(all_cycles))]
            )
            
            total_sequences = result['total_sequences_generated']

            top_n_binders = await self.get_top_binders(all_cycles, n=5)

            analysis = {
                'protein_id': self.protein_id,
                'num_rounds': result['rounds_completed'],
                'total_sequences': total_sequences,
                'passing_sequences': result['total_sequences_filtered'],
                'top_binders': top_n_binders,
                'success_rate': passing_structures  / total_sequences if total_sequences > 0 else 0.0

            }

            analysis['checkpoint_file'] = self.write_checkpoint(result) 
            analysis['confidence_score'] = self._calculate_confidence(result)
            analysis['tools_used'] = self._get_tools_used()

            return analysis

    def _calculate_confidence(self,
                              analysis: dict) -> float:
        return 0.75

    def _get_tools_used(self) -> list[str]:
        return ['chai', 'proteinmpnn']
