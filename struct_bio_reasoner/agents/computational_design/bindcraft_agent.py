try:
    from academy.exchange import LocalExchangeFactory
    from academy.manager import Manager
except ImportError:
    raise ImportError(
        "The 'academy' package is required for BindCraftAgent. "
        "Install Jnana with: pip install git+https://github.com/acadev/Jnana.git --no-deps"
    )
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

from jnana.core.model_manager import UnifiedModelManager

from ...data.protein_hypothesis import BinderAnalysis, ProteinHypothesis
from ...core.base_agent import BaseAgent

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

        self.parsl_config = parsl_config #self.config.get('parsl', {})
        self.manager = None
        self.forward_folder = None
        self.inverse_folder = None
        self.qc_agent = None
        self.analyzer_agent = None

        self.logger.info(f'BindCraft agent using: {self.fold_backend},{self.inv_fold_backend}')

        # NOTE: look at bindcraft for this
        #self.bindcraft_config = config['bindcraft_config']

        #if 'target_sequence' not in self.bindcraft_config:
        #    raise AttributeError('`target_sequence` not defined in config!')

    async def initialize(self,
                         parsl: Optional[dict] = None):
        """
        Initialize BindCraft components.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            import platform
            from bindcraft.core.coordinators import ParslDesignCoordinator
            from bindcraft.core.folding import ChaiBinder
            from bindcraft.core.inverse_folding import ProteinMPNN
            from bindcraft.analysis.energy import SimpleEnergy
            from bindcraft.util.quality_control import SequenceQualityControl
            from parsl import Config
            if platform.system() == 'Darwin':
                from ...utils.parsl_settings import MacLocalSettings as _ParslSettings
            else:
                from ...utils.parsl_settings import LocalSettings as _ParslSettings

            parsl_config = self.parsl_config

            if parsl is not None:
                for k, v in parsl.values():
                    parsl_config[k] = v

            self.logger.info(parsl_config)
            self.logger.info(Path.cwd())
            parsl_settings = _ParslSettings(**parsl_config).config_factory(Path.cwd())

            cwd = Path(self.config.get('cwd', os.getcwd()))
            cwd.mkdir(exist_ok=True, parents=True)

            fasta_dir = cwd / "fastas"
            folds_dir = cwd / "folds"
            fasta_dir.mkdir(exist_ok=True)
            folds_dir.mkdir(exist_ok=True)

            target_sequence = self.config.get('target_sequence', '')
            binder_sequence = self.config.get('binder_sequence', "MKQHKAMIVALIVICITAVVAALVTRKDLCEVHIRTGQTEVAVF")
            device = self.config.get('device', 'cpu')
            num_rounds = self.config.get('num_rounds', 3)

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
                fasta_dir=fasta_dir,
                out=folds_dir,
                diffusion_steps=100,
                device=device  # or 'cpu' if GPU not available
            )

            proteinmpnn = ProteinMPNN(**if_kwargs)

            qc_alg = SequenceQualityControl(**qc_kwargs)
            energy_alg = SimpleEnergy()

            self.logger.info('Initialized algorithms')

            self.manager = await Manager.from_exchange_factory(
                factory=LocalExchangeFactory(),
                executors=ThreadPoolExecutor(),
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
                          parsl_settings,
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
            self.initialized = False
            return False

        self.logger.info(f'Successfully imported BindCraft components.')
        self.initialized = True
        
        return True

    async def is_ready(self,
                       parsl: Optional[dict] = None) -> bool:
        if not hasattr(self, 'initialized'):
            await self.initialize(parsl)
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

    async def generate_hypotheses(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """"""
        pass

    def get_capabilities(self) -> list[str]:
        return self.capabilities

    async def generate_binder_hypothesis(self, 
                                         data: dict[str, Any]) -> Optional[ProteinHypothesis]:
        """"""
        if 'parsl' in data:
            parsl = data.pop('parsl')
        else:
            parsl = None

        if not await self.is_ready(parsl):
            self.logger.error('BindCraft agent not ready')
            return None

        return await self._generate_binder_hypothesis(data)

    async def _generate_binder_hypothesis(self,
                                          data: dict[str, Any]) -> Optional[ProteinHypothesis]:
        """"""
        # prepare output paths
        cwd = Path(data.get('cwd', self.config.get('cwd', os.getcwd())))
        cwd.mkdir(exist_ok=True, parents=True)

        fasta_dir = cwd / "fastas"
        folds_dir = cwd / "folds"
        fasta_dir.mkdir(exist_ok=True)
        folds_dir.mkdir(exist_ok=True)
            
        target_sequence = data['target_sequence']
        print(f"\n{'='*80}")
        print(f"BindCraft _generate_binder_hypothesis - SEQUENCES BEING USED:")
        print(f"  target_sequence: {target_sequence[:50]}... ({len(target_sequence)} residues)")
        binder_sequence = data.get('binder_sequence', "MKQHKAMIVALIVICITAVVAALVTRKDLCEVHIRTGQTEVAVF")
        constraints = data.get('constraints', None)
        num_rounds = data.get('num_rounds', 3)

        # Run the workflow
        results = await self.coordinator.run_full_workflow(
            target_sequence=target_sequence,
            binder_sequence=binder_sequence,
            fasta_base_path=fasta_dir,
            pdb_base_path=folds_dir,
            constraints=constraints,
            remodel_indices=None,  # Interface indices to redesign, else measure
            num_rounds=num_rounds
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

    async def analyze_hypothesis(self,
                                 hypothesis: ProteinHypothesis,
                                 task_params: dict[str, Any]) -> BinderAnalysis:
        result = await self.generate_binder_hypothesis(task_params)
        if result is None:
            raise RuntimeError(
                "BindCraft agent failed to initialize — ensure that the "
                "BindCraft package and its dependencies (Chai, ProteinMPNN, "
                "Parsl) are installed and available in your environment. "
                "Install from: https://github.com/msinclair-py/bindcraft/tree/agent_acad"
            )
        # Write result to file
        all_cycles = result['all_cycles']
        passing_structures = sum(
            [len(all_cycles[i]['passing_structures']) for i in range(len(all_cycles))]
        )
        
        total_sequences = result['total_sequences_generated']

        top_n_binders = await self.get_top_binders(all_cycles, n=5)

        analysis = BinderAnalysis(
            protein_id='',
            num_rounds = result['rounds_completed'],
            total_sequences = total_sequences,
            passing_sequences = result['total_sequences_filtered'],
            passing_structures = passing_structures,
            top_binders = top_n_binders,
            success_rate = passing_structures  / total_sequences if total_sequences > 0 else 0.0
        )

        analysis.checkpoint_file = self.write_checkpoint(result) 
        analysis.confidence_score = self._calculate_confidence(analysis)
        analysis.tools_used = self._get_tools_used()

        return analysis

    def _calculate_confidence(self,
                              analysis: BinderAnalysis) -> float:
        return 0.75

    def _get_tools_used(self) -> list[str]:
        return ['chai', 'proteinmpnn']
