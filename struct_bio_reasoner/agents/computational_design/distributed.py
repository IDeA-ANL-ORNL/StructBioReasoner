"""
Agentic workflow for peptide design using Academy agents.

This module implements the BindCraft peptide design pipeline as an agentic workflow
using Academy agents, enabling dynamic decision-making and adaptive optimization.

Workflow steps:
1. Forward Folding: Initial structure prediction
2. Inverse Folding: Sequence generation
3. Quality Control: Filter sequences
4. Refolding: Predict structures for new sequences
5. Analysis & Filtering: Evaluate and select best candidates
"""

import asyncio
import logging
import parsl
from pathlib import Path
from typing import Any, Optional

from .folding import Folding
from .inverse_folding import InverseFolding
from .energy import EnergyCalculation, SimpleEnergy
from .quality_control import SequenceQualityControl

logger = logging.getLogger(__name__)

@parsl.python_app(executors=['gpu'])
def fold_sequence_task(
    fold_alg: Folding,
    sequence: str,
    label: str,
    seq_label: Optional[str]=None,
    constraints: Optional[dict]=None
) -> dict:
    """Parsl task for folding a single sequence.

    Works with both Chai (3-arg) and ChaiBinder (4-arg) signatures:
      Chai.__call__(seqs, name, constraints)
      ChaiBinder.__call__(seqs, exp_label, out_label, constraints)
    """
    if seq_label is not None:
        result = fold_alg(sequence, label, seq_label, constraints)
    else:
        result = fold_alg(sequence, label, constraints)
    return result

@parsl.python_app(executors=['gpu'])
def inverse_fold_task(
    inv_fold_alg: InverseFolding,
    input_path: Path,
    pdb_path: Path,
    output_path: Path,
    remodel_positions: list[int]
) -> list[str]:

    sequences = inv_fold_alg(
        input_path=input_path,
        pdb_path=pdb_path,
        output_path=output_path,
        remodel_positions=remodel_positions,
    )

    return sequences

@parsl.python_app(executors=['cpu'])
def qc_task(
    qc_alg: SequenceQualityControl,
    sequence: str,
) -> bool:
    """Parsl task to run QC on a single sequence. Returns True if it passes."""
    return qc_alg(sequence)

@parsl.python_app(executors=['cpu'])
def energy_task(
    energy_alg: EnergyCalculation,
    structure: Path,
) -> float:
    energy = energy_alg(structure)
    return energy
