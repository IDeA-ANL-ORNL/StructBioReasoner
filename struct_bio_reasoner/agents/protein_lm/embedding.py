from academy.agent import Agent, action
import asyncio
import logging
from pathlib import Path
from typing import Optional
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
from itertools import chain
import asyncio
import logging
import parsl
from pathlib import Path
from typing import Any, Optional
from struct_bio_reasoner.agents.embedding.distributed import *
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
from itertools import chain
import asyncio
import logging
import parsl
from pathlib import Path
from typing import Any, Optional

import argparse
import csv
import datetime
from pathlib import Path

import numpy as np
import scipy.special
import torch
from transformers import AutoTokenizer

from genslm_esm.modeling import GenslmEsmcModel
from abc import ABC, abstractmethod

class Embed(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def prepare(self):
        pass
    
    @abstractmethod
    def __call__(self):
        pass

    @abstractmethod
    def postprocess(self):
        pass
        
class GenSLMEmbed(Embed):
    def __init__(model_id='genslm-test/genslm-esmc-600M-contrastive',
                 inference_params: dict = {'batch_size': 32, 'num_workers': 1},
                 device: str = 'xpu'
                ):
        self.model = AutoModel.from_pretrained(model_id, trust_remote_code=True)
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        self.model.to(torch.device(device))
        self.model.eval()

        self.device = device
        self.inf_params = inf_params
        self.inf_params['return_aminoacid'] = True
        self.inf_params['return_codon'] = False

    def prepare(self, seqs):
        dataset = FastaDataset(
            sequences=seqs,
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
            num_workers=self.inf_params['num_workers'],
            pin_memory=True,
        )
        return dataloader

    def __call__(self,
                seqs,
                metadata):
        pbar = self.prepare(seqs)
        all_embeddings = []
        with torch.no_grad():
            for batch in tqdm(pbar):
                # Move batch to device
                items = batch.to(torch.device(self.device))
                
                # Run model
                outputs = cast(GenslmEsmcModelOutput, self.model(**items))
                
                assert outputs.hidden_states is not None, "Hidden states are None"
                
                # Get last hidden state and mean pool
                embeddings = outputs.hidden_states[-1]
                embeddings = embeddings.mean(dim=1).to(torch.float32).cpu().numpy()
                all_embeddings.extend(embeddings)

        results = self.postprocess(seqs, all_embeddings, metadata)
        return results
    
    def postprocess(self, seqs, embeddings, metadata):
        return [(s, e, m) for (s, e, m) in zip(seqs, embeddings, metadata)]

