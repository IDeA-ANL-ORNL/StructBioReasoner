from academy.exchange import LocalExchangeFactory
from academy.manager import Manager
from bindcraft.core.agentic import (ForwardFoldingAgent, 
                                    InverseFoldingAgent,
                                    QualityControlAgent,
                                    AnalysisAgent,
                                    PeptideDesignCoordinator)
from bindcraft.core.folding import Folding
from bindcraft.core.inverse_folding import InverseFolding
from bindcraft.analysis.energy import SimpleEnergy
from bindcraft.util.quality_control import SequenceQualityControl
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
from bindcraft.core.folding import Chai
from bindcraft.core.inverse_folding import ProteinMPNN

from jnana.core.model_manager import UnifiedModelManager

from ...data.protein_hypothesis import BinderAnalysis, ProteinHypothesis
from ...core.base_agent import BaseAgent

class BindCraftAgent:
    """"""
    def __init__(self, 
                 agent_id: str,
                 config: dict[str, Any],
                 model_manager: UnifiedModelManager):
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

        self.logger.info(f'BindCraft agent using: {self.fold_backend},{self.inv_fold_backend}')

        # NOTE: look at bindcraft for this
        #self.bindcraft_config = config['bindcraft_config']

        #if 'target_sequence' not in self.bindcraft_config:
        #    raise AttributeError('`target_sequence` not defined in config!')

    async def initialize(self):
        """"""
        # NOTE: check if model is available somehow
        pass

    def is_ready(self) -> bool:
        # NOTE: need to check initialize
        pass

    def cleanup(self):
        pass

    def write_checkpoint(self, results: dict[str, Any]):
        #Use timestemp tom get unique name
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        checkpoint_file = f'bindcraft_checkpoint_{timestamp}.pkl'
        pickle.dump(results, open(checkpoint_file, 'wb'))
        return checkpoint_file

    async def generate_hypotheses(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """"""
        pass

    def get_capabilities(self) -> list[str]:
        return self.capabilities

    async def generate_binder_hypothesis(self, 
                                         data: dict[str, Any]) -> Optional[ProteinHypothesis]:
        """"""
        if not self.is_ready():
            self.logger.error('BindCraft agent not ready')
            return None

        return await self._generate_binder_hypothesis(data)

    async def _generate_binder_hypothesis(self,
                                          data: dict[str, Any]) -> Optional[ProteinHypothesis]:
        """"""
        # prepare output paths
        cwd = Path(data.get('cwd', os.getcwd()))
        cwd.mkdir(exist_ok=True)

        fasta_dir = cwd / "fastas"
        folds_dir = cwd / "folds"
        fasta_dir.mkdir(exist_ok=True)
        folds_dir.mkdir(exist_ok=True)

        # these need to be somehow passed into the call
        target_sequence = data['target_sequence']
        binder_sequence = data.get('binder_sequence', "MKQHKAMIVALIVICITAVVAALVTRKDLCEVHIRTGQTEVAVF")
        device = data.get('device', 'cuda:0')
        num_rounds = data.get('num_rounds', 3)

        if_kwargs = data.get('if_kwargs', {
            'num_seq': data.get('num_seq', 25),
            'batch_size': data.get('batch_size', 250),
            'max_retries': data.get('retries', 5),
            'sampling_temp': data.get('temp', '0.1'),
            'model_name': data.get('mpnn_model', 'v_48_020'),
            'model_weights': data.get('mpnn_weights', 'soluble_model_weights'),
            'proteinmpnn_path': data.get('proteinmpnn_path', '/eagle/FoundEpidem/avasan/Softwares/ProteinMPNN'),
            'device': device
        })

        qc_kwargs = data.get('qc_kwargs', {
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
        chai = Chai(
            fasta_dir=fasta_dir,
            out=folds_dir,
            diffusion_steps=100,
            device=device  # or 'cpu' if GPU not available
        )

        proteinmpnn = ProteinMPNN(**if_kwargs)

        async with await Manager.from_exchange_factory(
            factory=LocalExchangeFactory(),
            executors=ThreadPoolExecutor(),
        ) as manager:
            # Launch individual agents
            forward_folder = await manager.launch(
                ForwardFoldingAgent,
                args=(chai,)
            )
            inverse_folder = await manager.launch(
                InverseFoldingAgent,
                args=(proteinmpnn,)
            )
            qc_agent = await manager.launch(
                QualityControlAgent,
                args=(SequenceQualityControl(**qc_kwargs),)
            )
            analyzer = await manager.launch(
                AnalysisAgent,
                args=(SimpleEnergy(),)
            )

            # Launch coordinator with handles to other agents
            coordinator = await manager.launch(
                PeptideDesignCoordinator,
                args=(forward_folder, inverse_folder, qc_agent, analyzer, if_kwargs['num_seq'], if_kwargs['max_retries'])
            )


            # Run the workflow
            results = await coordinator.run_full_workflow(
                target_sequence=target_sequence,
                binder_sequence=binder_sequence,
                fasta_base_path=fasta_dir,
                pdb_base_path=folds_dir,
                remodel_indices=[],  # Interface indices to redesign
                num_rounds=num_rounds
            )

            return results

    async def _create_binder_hypothesis(self,
                                        results: dict[str, Any]) -> ProteinHypothesis:
        all_cycles = results['all_cycles']
        passing_structures = [all_cycles[i]['passing_structures'] for i in range(len(all_cycles))]

        passing_file = Path('')
        passing_file.write_text('\n'.join(passing_structures))

        hypothesis_content = f"""
        BindCraft run successful for {results['rounds_completed']} rounds. 

        Key findings:
        - {results['total_sequences_filtered']}/{results['total_sequences_generated']} sequences passed
        quality control
        - {len(passing_structures)} passed structural quality control

        Recommended strategies:
        1. Perform molecular dynamics (MD) simulation
        2. Compute free energy by MM-PBSA
        """

        hypothesis = ProteinHypothesis(
            title='BindCraft based binder design',
            content=hypothesis_content.strip(),
            description=f'BindCraft predicts {len(passing_structures)} novel binder sequences',
            hypothesis_type='',
            generation_timestamp=datetime.now().isoformat(),
            metadata=results,
        )

        # Set hallmarks based on analysis quality
        hypothesis.hallmarks = {
            'testability': 8.5,  # MD predictions are highly testable
            'specificity': 7.5,  # Specific residue-level predictions
            'grounded_knowledge': 9.0,  # Based on physics-based simulations
            'predictive_power': 8.0,  # Quantitative predictions
            'parsimony': 7.0   # Straightforward thermostability model
        }

        self.generated_hypotheses.append(hypothesis)
        return hypothesis

    async def analyze_hypothesis(self,
                                 hypothesis: ProteinHypothesis,
                                 task_params: dict[str, Any]) -> BinderAnalysis:
        result = await self._generate_binder_hypothesis(task_params)
        # Write result to file
        all_cycles = result['all_cycles']
        passing_structures = len(
            [all_cycles[i]['passing_structures'] for i in range(len(all_cycles))]
        )
        
        total_sequences = result['total_sequences_generated']

        analysis = BinderAnalysis(
            protein_id='',
            num_rounds = result['rounds_completed'],
            total_sequences = total_sequences,
            passing_sequences = result['total_sequences_filtered'],
            passing_structures = passing_structures,
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
