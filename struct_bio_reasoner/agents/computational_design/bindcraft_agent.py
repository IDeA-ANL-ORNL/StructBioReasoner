"""
BindCraft Agent for StructBioReasoner

This agent wraps BindCraft components for binder design using the
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

from jnana.core.model_manager import UnifiedModelManager

from ...data.protein_hypothesis import BinderAnalysis, ProteinHypothesis
from ...core.base_agent import BaseAgent
from ..shared_parsl_mixin import SharedParslMixin

if TYPE_CHECKING:
    from ...workflows.advanced_workflow import SharedParslContext


class BindCraftAgent(SharedParslMixin):
    """
    BindCraft agent for computational binder design.

    This agent now uses SharedParslMixin to support both:
    1. Shared Parsl context from workflow (prevents nested config collisions)
    2. Standalone mode for testing (original behavior)
    """

    def __init__(
        self,
        agent_id: str,
        config: Dict[str, Any],
        model_manager: UnifiedModelManager,
        parsl_config: Dict[str, Any]
    ):
        """
        Initialize BindCraft agent.

        Args:
            agent_id: Unique identifier for this agent
            config: Agent configuration dictionary
            model_manager: Unified model manager for LLM access
            parsl_config: Parsl configuration dictionary
        """
        # Initialize the mixin
        super().__init__()

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
        self.coordinator = None

        self.logger.info(f'BindCraft agent using: {self.fold_backend},{self.inv_fold_backend}')

    async def initialize(
        self,
        parsl: Optional[Dict[str, Any]] = None,
        shared_context: Optional['SharedParslContext'] = None
    ) -> bool:
        """
        Initialize BindCraft components.

        Args:
            parsl: Optional parsl config overrides (for backwards compatibility)
            shared_context: Optional shared Parsl context from workflow

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            from bindcraft.core.coordinators import ParslDesignCoordinator
            from bindcraft.core.folding import ChaiBinder
            from bindcraft.core.inverse_folding import ProteinMPNN
            from bindcraft.analysis.energy import SimpleEnergy
            from bindcraft.util.quality_control import SequenceQualityControl
            from ...utils.parsl_settings import LocalSettings

            # Prepare data dict for mixin (may contain parsl overrides)
            data = {}
            if parsl is not None:
                data['parsl'] = parsl

            # If shared_context provided, add it to data
            if shared_context is not None:
                data['_shared_parsl_context'] = shared_context

            # Get Parsl settings using the mixin (key fix!)
            # This will use shared context if available, otherwise create standalone
            parsl_settings = await self._get_parsl_settings(
                data=data,
                shared_context=shared_context,
                settings_class=LocalSettings,
                parsl_config=self.parsl_config,
                agent_id=self.agent_id,
            )

            self.logger.info(f"Parsl settings obtained (shared: {self.is_using_shared_parsl})")

            cwd = Path(self.config.get('cwd', os.getcwd()))
            cwd.mkdir(exist_ok=True, parents=True)

            fasta_dir = cwd / "fastas"
            folds_dir = cwd / "folds"
            fasta_dir.mkdir(exist_ok=True)
            folds_dir.mkdir(exist_ok=True)

            target_sequence = self.config['target_sequence']
            binder_sequence = self.config.get('binder_sequence', "MKQHKAMIVALIVICITAVVAALVTRKDLCEVHIRTGQTEVAVF")
            device = self.config.get('device', 'cuda:0')
            num_rounds = self.config.get('num_rounds', 3)

            if_kwargs = self.config.get('if_kwargs', {
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
                'bad_n_termini': None
            })

            # Initialize algorithm instances
            chai = ChaiBinder(
                fasta_dir=fasta_dir,
                out=folds_dir,
                diffusion_steps=100,
                device=device
            )

            proteinmpnn = ProteinMPNN(**if_kwargs)
            qc_alg = SequenceQualityControl(**qc_kwargs)
            energy_alg = SimpleEnergy()

            self.logger.info('Initialized algorithms')

            # Initialize Academy manager using mixin
            self.manager = await self._initialize_manager()

            self.logger.info('Launching bindcraft handles')

            try:
                # Launch coordinator with handles to other agents
                self.coordinator = await self.manager.launch(
                    ParslDesignCoordinator,
                    args=(
                        chai,
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
                raise

        except ImportError as e:
            self.logger.error(f'Cannot import BindCraft components: {e}')
            self.logger.info('Make sure BindCraft is installed and in PYTHONPATH')
            self.logger.info('Install from: https://github.com/msinclair-py/bindcraft/tree/agent_acad')
            self.initialized = False
            return False

        self.logger.info(f'Successfully imported BindCraft components.')
        self.initialized = True

        return True

    async def is_ready(
        self,
        parsl: Optional[Dict[str, Any]] = None,
        shared_context: Optional['SharedParslContext'] = None
    ) -> bool:
        """
        Check if agent is ready, initializing if needed.

        Args:
            parsl: Optional parsl config overrides
            shared_context: Optional shared Parsl context from workflow

        Returns:
            True if agent is ready
        """
        if not hasattr(self, 'initialized') or not self.initialized:
            await self.initialize(parsl, shared_context)
        return self.initialized

    async def cleanup(self):
        """Clean up BindCraft agent resources."""
        try:
            # Release accelerators if using shared context
            await self._release_accelerators(self.agent_id)

            # Clean up manager using mixin
            await self._cleanup_manager()

            self.coordinator = None
            self.logger.info('BindCraft agent cleanup completed')

        except Exception as e:
            self.logger.error(f'BindCraft agent cleanup failed: {e}')

    def write_checkpoint(self, results: Dict[str, Any]) -> str:
        """Write results checkpoint to file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        checkpoint_file = f'bindcraft_checkpoint_{timestamp}.pkl'
        with open(checkpoint_file, 'wb') as pkl:
            pickle.dump(results, pkl)
        return checkpoint_file

    async def generate_hypotheses(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate hypotheses (not implemented)."""
        pass

    def get_capabilities(self) -> List[str]:
        """Get agent capabilities."""
        return self.capabilities

    async def generate_binder_hypothesis(
        self,
        data: Dict[str, Any]
    ) -> Optional[ProteinHypothesis]:
        """
        Generate binder hypothesis.

        Args:
            data: Input data including target sequence and optional parsl/context

        Returns:
            Generated hypothesis or None on failure
        """
        # Extract shared context if present
        shared_context = data.pop('_shared_parsl_context', None)
        parsl = data.pop('parsl', None)

        if not await self.is_ready(parsl, shared_context):
            self.logger.error('BindCraft agent not ready')
            return None

        return await self._generate_binder_hypothesis(data)

    async def _generate_binder_hypothesis(
        self,
        data: Dict[str, Any]
    ) -> Optional[ProteinHypothesis]:
        """Internal hypothesis generation."""
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
            remodel_indices=None,
            num_rounds=num_rounds
        )

        await self.cleanup()

        return results

    async def get_top_binders(
        self,
        cycles: List[Dict[str, Any]],
        n: int = 5
    ) -> Dict[int, Dict[str, Any]]:
        """Get top N binders from design cycles."""
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

                    _ = top_binders.pop(worst_binder)

        energies = [binder['energy'] for binder in top_binders]
        order = np.argsort(energies)

        top_dict = {i: top_binders[idx] for i, idx in enumerate(order)}

        return top_dict

    async def analyze_hypothesis(
        self,
        hypothesis: ProteinHypothesis,
        task_params: Dict[str, Any]
    ) -> BinderAnalysis:
        """
        Analyze hypothesis and generate binders.

        Args:
            hypothesis: Input protein hypothesis
            task_params: Task parameters including target sequence

        Returns:
            Analysis results
        """
        result = await self.generate_binder_hypothesis(task_params)

        all_cycles = result['all_cycles']
        passing_structures = sum(
            [len(all_cycles[i]['passing_structures']) for i in range(len(all_cycles))]
        )

        total_sequences = result['total_sequences_generated']

        top_n_binders = await self.get_top_binders(all_cycles, n=5)

        analysis = BinderAnalysis(
            protein_id='',
            num_rounds=result['rounds_completed'],
            total_sequences=total_sequences,
            passing_sequences=result['total_sequences_filtered'],
            passing_structures=passing_structures,
            top_binders=top_n_binders,
            success_rate=passing_structures / total_sequences if total_sequences > 0 else 0.0
        )

        analysis.checkpoint_file = self.write_checkpoint(result)
        analysis.confidence_score = self._calculate_confidence(analysis)
        analysis.tools_used = self._get_tools_used()

        return analysis

    def _calculate_confidence(self, analysis: BinderAnalysis) -> float:
        """Calculate confidence score for analysis."""
        return 0.75

    def _get_tools_used(self) -> List[str]:
        """Get list of tools used."""
        return ['chai', 'proteinmpnn']
