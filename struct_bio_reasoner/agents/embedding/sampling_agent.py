from academy.agent import Agent, action
import asyncio
import logging
from pathlib import Path
from typing import Optional
from struct_bio_reasoner.agents.computational_design.distributed import fold_sequence_task
import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoTokenizer
from genslm_esm.modeling import GenslmEsmcModelOutput
from genslm_esm.data import FastaDataset, GenslmEsmcDataCollator
import pandas as pd
from collections import defaultdict
import sys
from struct_bio_reasoner.utils.embedding_utils import *

logger = logging.getLogger(__name__)

class GenSLMAgent(Agent):
    """
    Agent responsible for various GenSLM related actions.
    These include:
        - embedding sequences
        - diversity sampling embedding space
        - mutating 
    """
    def __init__(
        self,
        root_path: Path,
        model_id,
        batch_size: int = 32,
        num_workers: int = 1,
        return_aminoacid: bool=True,
        return_codon: bool = False,
        device: str = 'xpu',
    ):
        self.root = Path(root_path) # in case it's not already a Path
        self.model, self.tokenizer = load_model(model_id = model_id, device = device)
        self.device = device
        self.inf_params = {'batch_size': batch_size,
                            'num_workers': num_workers,
                            'return_aminoacid': return_aminoacid,
                            'return_codon': return_codon}
        
    def create_dataloader(self, sequences, metadata):

        # The dataset splits the sequences into codons
        dataset = FastaDataset(
            sequences=sequences,
            return_codon=self.inf_params['return_codon'],
            return_aminoacid=self.inf_params['return_aminoacid'],
            contains_nucleotide=self.inf_params['return_codon'],
        )
        
        # Create the collator
        collator = GenslmEsmcDataCollator(
            return_codon=self.inf_params['return_codon'],
            return_aminoacid=self.inf_params['return_aminoacid'],
            tokenizer=self.tokenizer,
        )
        # Create dataloader
        dataloader = DataLoader(
              dataset,
              batch_size=self.inf_params['batch_size'],
              collate_fn=collator,
              num_workers=num_workers,
              pin_memory=True)
        
        return dataloader
    
    @action
    async def embed_sequences(
                self,
                dataloader,
                ):
        
        
        
        
        
        
        
        
        
        
        
        
        
        

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

