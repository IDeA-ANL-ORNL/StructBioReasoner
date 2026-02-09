from academy.agent import Agent, action
import asyncio
import logging
from pathlib import Path
from typing import Optional
from struct_bio_reasoner.agents.computational_design.folding import Chai
from struct_bio_reasoner.agents.computational_design.distributed import fold_sequence_task

logger = logging.getLogger(__name__)

class ChaiAgent(Agent):
    """
    Agent responsible for all folding tasks.
    """
    def __init__(
        self,
        root_path: Path,
        diffusion_steps: int=100,
        device: str='cuda'
    ):
        self.root = Path(root_path) # in case it's not already a Path
        self.chai = Chai(
            fasta_dir=self.root / '0' / 'fastas',
            out=self.root / '0' / 'folds',
            diffusion_steps=diffusion_steps,
            device=device,
        )

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
                    fold_sequence_task(self.chai, sequence, name, constraint)
                )
            )

        results = await asyncio.gather(*futures)

        return results

