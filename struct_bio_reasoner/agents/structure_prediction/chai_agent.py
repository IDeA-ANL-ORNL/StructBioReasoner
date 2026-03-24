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

from ...data.protein_hypothesis import ProteinHypothesis, FoldAnalysis, GlycanChain
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
            
            parsl_config = self.parsl_config

            if 'parsl' in data:
                parsl = data.pop('parsl')
                for k, v in parsl.values():
                    parsl_config[k] = v
            
            parsl_settings = LocalSettings(**parsl_config).config_factory(Path.cwd())
            
            self.logger.info(f'{data=}')
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
                          parsl_settings,
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

    @staticmethod
    def _append_extra_constraints(base_path: Path, extra_path: Path) -> None:
        """
        Append data rows from *extra_path* into *base_path*, skipping the
        header line of *extra_path* so the combined file stays valid CSV.
        """
        extra_lines = Path(extra_path).read_text().splitlines()
        data_rows = [l for l in extra_lines[1:] if l.strip()]  # skip header
        if data_rows:
            with base_path.open('a') as f:
                f.write('\n'.join(data_rows) + '\n')

    def _inject_glycans(
        self,
        sequences: list,
        glycan_chains: list,
        existing_constraints: list,
        cwd: Optional[str] = None,
    ) -> tuple:
        """
        Extend every fold's sequence list with glycan entries and produce a
        merged Chai-1 restraint CSV per fold.

        Chain assignment logic
        ----------------------
        Chai-1 assigns chain letters in FASTA order: the first sequence block
        becomes chain A, the second chain B, etc.  We discover how many
        protein/binder chains are already in the first fold and let glycans
        occupy the next consecutive letters.

        Constraint merging
        ------------------
        The glycan covalent bonds are written to a base restraint CSV first.
        If a fold already has its own constraint file, the glycan rows are
        appended to a per-fold copy so neither set of constraints is lost.

        Args:
            sequences:            list-of-lists of amino-acid / glycan strings.
            glycan_chains:        list of GlycanChain objects.
            existing_constraints: one entry per fold — a path string or None.
            cwd:                  working directory for output files.

        Returns:
            (new_sequences, new_constraints)
        """
        # How many non-glycan chains come before the glycans?
        n_protein_chains = len(sequences[0]) if sequences else 1
        chain_letters = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')

        # Re-letter glycan chains to sit immediately after protein chains.
        adjusted: list[GlycanChain] = []
        for i, gc in enumerate(glycan_chains):
            slot = n_protein_chains + i
            if slot >= len(chain_letters):
                self.logger.warning(
                    f'Cannot assign chain letter for glycan {i + 1}; '
                    'too many chains — skipping.'
                )
                break
            adjusted.append(GlycanChain(
                chain_id=chain_letters[slot],
                sequence=gc.sequence,
                attachment_residue=gc.attachment_residue,
                protein_chain=gc.protein_chain,
                protein_atom=gc.protein_atom,
                glycan_atom=gc.glycan_atom,
            ))

        glycan_seqs = [gc.sequence for gc in adjusted]
        new_sequences = [list(seq_group) + glycan_seqs for seq_group in sequences]

        # Write the base glycan restraint CSV (glycan bonds only).
        restraint_dir = Path(cwd) if cwd else Path('.')
        restraint_dir.mkdir(exist_ok=True, parents=True)
        base_restraint_path = restraint_dir / 'glycan_restraints.csv'
        GlycanChain.write_restraints_csv(adjusted, base_restraint_path)
        self.logger.info(
            f'Wrote glycan restraint CSV → {base_restraint_path} '
            f'({len(adjusted)} bond(s))'
        )

        # Per-fold: merge with any existing constraint file.
        new_constraints: list[str] = []
        for i, existing in enumerate(existing_constraints):
            if existing is None:
                # No extra constraints — use the shared glycan file directly.
                new_constraints.append(str(base_restraint_path))
            else:
                # Copy the base glycan file, then append the fold's constraints.
                merged_path = restraint_dir / f'merged_restraints_fold{i}.csv'
                merged_path.write_text(base_restraint_path.read_text())
                self._append_extra_constraints(merged_path, Path(existing))
                self.logger.info(
                    f'Fold {i}: merged glycan restraints + {existing} → {merged_path}'
                )
                new_constraints.append(str(merged_path))

        return new_sequences, new_constraints

    async def _generate_binder_hypothesis(self,
                                          data: dict[str, Any]) -> Optional[ProteinHypothesis]:
        """"""
        sequences = data['sequences']
        names = data['names']
        constraints = data.get('constraints', [None] * len(sequences))

        # --- glycan support ------------------------------------------------
        glycan_chains = data.get('glycan_chains', [])
        if glycan_chains:
            self.logger.info(
                f'Injecting {len(glycan_chains)} glycan chain(s) into Chai fold inputs.'
            )
            sequences, constraints = self._inject_glycans(
                sequences,
                glycan_chains,
                existing_constraints=constraints,
                cwd=data.get('cwd'),
            )
        # -------------------------------------------------------------------

        # Run the workflow
        results = await self.coordinator.fold_sequences(
            sequences=sequences,
            names=names,
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
