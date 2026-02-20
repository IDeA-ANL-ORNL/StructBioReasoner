from academy.agent import Agent, action
import asyncio
import logging
import MDAnalysis as mda
import parsl
from parsl import Config
from pathlib import Path
from typing import Any, Optional
from .distributed import fold_sequence_task, inverse_fold_task, qc_task, energy_task
from .energy import EnergyCalculation, SimpleEnergy
from .folding import Folding, ChaiBinder
from .inverse_folding import InverseFolding, ProteinMPNN
from .quality_control import SequenceQualityControl

Result = dict[int, dict[str, Any]]

class BindCraftCoordinator(Agent):
    """Coordinator agent that orchestrates the peptide design workflow."""
    def __init__(
        self,
        root_dir: str,
        fold_backend: str,
        inv_fold_backend: str,
        device: str,
        inverse_folding: dict,
        quality_control: dict,
        nseq: int,
        retries: int,
        target_sequence: str = '',
    ) -> None:
        super().__init__()

        self.root_dir = Path(root_dir)
        self.target_sequence = target_sequence
        self.device = device
        self.inverse_folding = inverse_folding
        self.quality_control = quality_control
        self.nseq = nseq
        self.retries = retries
        self.energy_threshold = -10.0
        self.do_seq_qc = quality_control.get('enabled', True)
        
        match fold_backend:
            case 'chai':
                self.fold_alg = ChaiBinder
            case _: # for now the default
                self.fold_alg = ChaiBinder

        match inv_fold_backend:
            case 'proteinmpnn':
                self.inv_fold_alg = ProteinMPNN 
            case _:
                self.inv_fold_alg = ProteinMPNN


        self.logger = logging.getLogger(__name__)

    async def agent_on_startup(self):
        # These are plain objects (not Academy agents) because they get passed
        # to Parsl tasks which require picklable arguments.
        self.fold_handle = self.fold_alg(
            fasta_dir=self.root_dir / 'bindcraft' / 'fastas',
            out=self.root_dir / 'bindcraft' / 'folds',
            diffusion_steps=100,
            device=self.device,
        )

        self.inv_fold_handle = self.inv_fold_alg(**self.inverse_folding)

        qc_kwargs = {k: v for k, v in self.quality_control.items() if k != 'enabled'}
        self.qc_handle = SequenceQualityControl(**qc_kwargs)

        self.energy_handle = SimpleEnergy()
        
    @action
    async def prepare_run(self,
                          target_sequence: str,
                          binder_sequence: str,):
        self.logger.info('Forward folding: Initial fold for trial 0')
        sequences = [target_sequence, binder_sequence]
        label = 'trial_0'
        seq_label = 'seq_0'

        structure = self.fold_handle(sequences, label, seq_label)
        self.logger.info(f'Initial structure folded: {structure}')

        return structure

    @action
    async def refold_sequences(self,
                               target_sequence: str,
                               sequences: list[str],
                               trial: int,
                               constraints: Optional[dict]=None) -> Result:
        self.logger.info(f'Forward folding: Folding {len(sequences)} seqs for trial {trial}')
        label = f'trial_{trial}'

        folded_structures = {}
        futures = []
        for i, seq in enumerate(sequences):
            seq_label = f'seq_{i}'
            seqs = [target_sequence, seq]
            futures.append(
                asyncio.wrap_future(
                    fold_sequence_task(self.fold_handle, seqs, label, seq_label, constraints)
                )
            )

        structures = await asyncio.gather(*futures)

        folded_structures = {i: {
            'sequence': sequences[i],
            'structure': str(structures[i]),
            'energy': None,
            'rmsd': None
        } for i in range(len(structures))}

        self.logger.info(f'Folded {len(folded_structures)} structures')

        return folded_structures

    @action
    async def generate_sequences(self,
                                 fasta_in: Path,
                                 pdb_path: Path,
                                 fasta_out: Path,
                                 remodel_indices: list[int]) -> list[str]:
        self.logger.info('Inverse folding: Generating sequences')

        sequences = await asyncio.wrap_future(
            inverse_fold_task(
                inv_fold_alg=self.inv_fold_handle,
                input_path=fasta_in,
                pdb_path=pdb_path,
                output_path=fasta_out,
                remodel_positions=remodel_indices
            )
        )

        self.logger.info(f'Generated {len(sequences)} sequences')
        return sequences

    @action
    async def filter_sequences(self,
                               sequences: list[str]) -> list[str]:
        self.logger.info(f'Quality control: Filtering {len(sequences)} sequences')

        futures = [
            asyncio.wrap_future(qc_task(self.qc_handle, seq))
            for seq in sequences
        ]
        results = await asyncio.gather(*futures)

        filtered = [seq for seq, passed in zip(sequences, results) if passed]

        self.logger.info(f'Quality control: {len(filtered)} / {len(sequences)} sequences passed QC')

        return filtered

    @action
    async def evaluate_structures(self,
                                  folded_structures: Result) -> tuple[Result, list[str]]:
        self.logger.info(f'Analysis: Evaluating {len(folded_structures)} structures')
        keys = list(folded_structures.keys())
        vals = list(folded_structures.values())
        structures = [Path(val['structure']) for val in vals]
        self.logger.info(f'Computing {len(structures)} calculations')
        futures = [asyncio.wrap_future(energy_task(self.energy_handle, structure)) 
                   for structure in structures]

        energies = await asyncio.gather(*futures)

        evaluated = {}
        passing = []
        for key, val, struc, energy in zip(keys, vals, structures, energies):
            val['energy'] = energy
            evaluated[key] = val

            if energy < self.energy_threshold:
                passing.append(str(struc))

        self.logger.info(f'Analysis: {len(passing)} / {len(evaluated)} structures passed filtering')

        return evaluated, passing

    @action
    async def run_design_cycle(
        self,
        target_sequence: str,
        binder_sequence: str,
        fasta_in: Path,
        pdb_path: Path,
        fasta_out: Path,
        remodel_indices: list[int],
        trial: int,
        constraints: Optional[dict]=None,
        do_seq_qc: bool=False,
    ) -> dict[str, Any]:
        """Run one complete design cycle."""
        self.logger.info(f"Coordinator: Starting design cycle for trial {trial}")
        try:
            filtered_sequences = []
            i = 0

            while len(filtered_sequences) < self.nseq and i < self.retries:
                # Step 1: Inverse folding
                generated_sequences = await self.generate_sequences(
                    fasta_in, pdb_path, fasta_out, remodel_indices
                )

                if do_seq_qc:
                    # Step 2: Quality control
                    filtered_sequences += await self.filter_sequences(
                        generated_sequences
                    )
                else:
                    filtered_sequences += generated_sequences

                i += 1

            if not filtered_sequences:
                self.logger.warning("No sequences passed quality control, max retries attempted.")
                return {
                    "success": False,
                    "error": "No sequences passed QC",
                    "trial": trial,
                }

            # Step 3: Refolding
            folded_structures = await self.refold_sequences(
                target_sequence, filtered_sequences, trial, constraints
            )

            self.logger.info('Measuring energy')

            # Step 4: Analysis and filtering
            evaluated_structures, passing_structures = (
                await self.evaluate_structures(folded_structures)
            )

            self.logger.info(
                f"Coordinator: Cycle {trial} complete. "
                f"{len(passing_structures)} structures passed filtering"
            )

            return {
                "success": True,
                "trial": trial,
                "generated_sequences": len(generated_sequences),
                "filtered_sequences": len(filtered_sequences),
                "folded_structures": len(folded_structures),
                "passing_structures": passing_structures,
                "evaluated_structures": evaluated_structures,
            }

        except Exception as e:
            self.logger.error(f"Coordinator: Error in design cycle {trial}: {e}")
            return {
                "success": False,
                "error": str(e),
                "trial": trial,
            }
    
    @action
    async def run(
        self,
        binder_sequence: str,
        num_rounds: int = 3,
        constraints: Optional[dict]=None,
        remodel_indices: Optional[list[int]]=None,
    ) -> dict[str, Any]:
        """Run the complete peptide design workflow."""
        target_sequence = self.target_sequence
        fasta_base_path = self.root_dir / 'bindcraft' / 'fastas'
        pdb_base_path = self.root_dir / 'bindcraft' / 'folds'
        fasta_base_path.mkdir(parents=True, exist_ok=True)
        pdb_base_path.mkdir(parents=True, exist_ok=True)

        if remodel_indices is not None and len(remodel_indices) == 0:
            remodel_indices = None
        if not constraints:
            constraints = None

        self.logger.info(f"Coordinator: Starting full workflow for {num_rounds} rounds")

        results = {
            "success": True,
            "rounds_completed": 0,
            "total_sequences_generated": 0,
            "total_sequences_filtered": 0,
            "best_energy": float("inf"),
            "all_cycles": [],
            "error_message": "",
        }

        (fasta_base_path / 'trial_0').mkdir(exist_ok=True, parents=True)
        (pdb_base_path / 'trial_0').mkdir(exist_ok=True, parents=True)
        structure = await self.refold_sequences(target_sequence, [binder_sequence], 0, constraints)
        self.logger.info(structure)

        evaluated, _ = await self.evaluate_structures(structure)

        results['all_cycles'].append({
            'success': True,
            'trial': 0,
            'generated_sequences': 1,
            'filtered_sequences': 1,
            'folded_structures': 1,
            'passing_structures': [str(structure[0]['structure'])],
            'evaluated_structures': evaluated
            })
            
        # Update metrics
        results["rounds_completed"] += 1
        results["total_sequences_generated"] += 1
        results["total_sequences_filtered"] += 1 

        if remodel_indices is None:
            remodel_indices = await self.get_remodel_indices(structure[0]['structure'])

        for trial in range(1, num_rounds + 1):
            # Construct paths for this trial
            last_trial = trial - 1
            fasta_in = fasta_base_path / f"trial_{last_trial}"
            fasta_out = fasta_base_path / f"trial_{trial}"
            pdb_path = pdb_base_path / f"trial_{last_trial}"

            cycle_result = await self.run_design_cycle(
                target_sequence,
                binder_sequence,
                fasta_in,
                pdb_path,
                fasta_out,
                remodel_indices,
                trial,
                constraints,
                do_seq_qc=self.do_seq_qc,
            )

            results["all_cycles"].append(cycle_result)

            if not cycle_result["success"]:
                self.logger.warning(f"Design cycle {trial} failed: {cycle_result.get('error')}")
                results["success"] = False
                break

            # Update metrics
            results["rounds_completed"] += 1
            results["total_sequences_generated"] += cycle_result.get(
                "generated_sequences", 0
            )
            results["total_sequences_filtered"] += cycle_result.get(
                "filtered_sequences", 0
            )

        self.logger.info(f"Coordinator: Workflow complete. {results['rounds_completed']} rounds completed")
        return results

    async def get_remodel_indices(self,
                                  pdb_file: Path):
        u = mda.Universe(str(pdb_file))

        sel = u.select_atoms('chainID B and around 4 chainID A')
        return sel.residues.resids


class ForwardFoldingAgent(Agent):
    """
    Agent responsible for all folding tasks.
    """
    def __init__(self,
                 fold_alg: str,
                 fold_config: dict):
        self.fold_handle = fold_alg(**fold_config)
    
    @action
    async def run(
        self,
        sequences: list[str],
        names: list[str],
        constraints: Optional[list[dict]]=None,
    ) -> str:
        """Perform initial forward folding on target-binder complex."""
        logger.info(f"Folding {len(sequences)} seqs with Chai-1")
        
        if isinstance(sequences, str): # single sequence passed
            sequences = [[sequences]]
        
        futures = []
        for sequence, name, constraint in zip(sequences, names, constraints):
            if isinstance(sequence, str): # single sequence to fold
                sequence = [sequence]

            futures.append(
                asyncio.wrap_future(
                    fold_sequence_task(self.fold_handle, sequence, name, constraint)
                )
            )

        results = await asyncio.gather(*futures)

        return results


class InverseFoldingAgent:
    def __init__(self,
                 inv_fold_alg: InverseFolding):
        self.inv_fold_handle = inv_fold_alg

    @action
    async def generate_sequences(
        self,
        fasta_in: Path,
        pdb_path: Path,
        fasta_out: Path,
        remodel_indices: list[int],
    ) -> list[str]:
        """Generate new sequences via inverse folding."""
        logger.info(f"Inverse folding: Generating sequences")
        
        sequences = await asyncio.wrap_future(inverse_fold_task(
            inv_fold_alg=self.inv_fold_handle,
            input_path=fasta_in,
            pdb_path=pdb_path,
            output_path=fasta_out,
            remodel_positions=remodel_indices
        ))

        logger.info(f"Generated {len(sequences)} sequences")

        return sequences


class QualityControlAgent(Agent):
    """Agent responsible for sequence quality control filtering."""

    def __init__(self, qc_filter: SequenceQualityControl) -> None:
        super().__init__()
        self.qc_filter = qc_filter

    @action
    async def filter_sequences(self, sequences: list[str]) -> list[str]:
        """Filter sequences based on quality control criteria."""
        logger.info(f"Quality control: Filtering {len(sequences)} sequences")

        filtered_sequences = []

        for seq in sequences:
            if self.qc_filter(seq):
                filtered_sequences.append(seq)

        logger.info(
            f"Quality control: {len(filtered_sequences)} / {len(sequences)} "
            "sequences passed QC"
        )

        return filtered_sequences


class AnalysisAgent(Agent):
    """Agent responsible for structure analysis and filtering."""

    def __init__(self, energy_handle: EnergyCalculation) -> None:
        super().__init__()
        self.energy_handle = energy_alg

    @action
    async def evaluate_structures(
        self,
        folded_structures: dict[int, dict[str, Any]],
        energy_threshold: float = -10.0,
    ) -> tuple[dict[int, dict[str, Any]], list[str]]:
        """Analyze folded structures and filter based on energy."""
        logger.info(f"Analysis: Evaluating {len(folded_structures)} structures")

        evaluated_structures = {}
        passing_structures = []

        for idx, struct_data in folded_structures.items():
            logger.info(f'Analyzing: {idx}, {struct_data["structure"]}')
            try:
                energy = self.energy_handle(Path(struct_data["structure"]))
                struct_data["energy"] = energy
                
                if energy < energy_threshold:
                    passing_structures.append(struct_data["structure"])
            except Exception as e:
                logger.warning(f"Energy calculation failed for structure {idx}: {e}")

        logger.info(
            f"Analysis: {len(passing_structures)} / {len(evaluated_structures)} "
            "structures passed filtering"
        )

        return evaluated_structures, passing_structures
