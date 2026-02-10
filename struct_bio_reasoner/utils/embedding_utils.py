from __future__ import annotations
"""Utils for embedding sequences in protein language model latent spaces.
Currently optimized for GenSLM-ESM embeddings but generalizable for other protein lang models
This version maintains batch efficiency while tracking which embedding
corresponds to which sequence/path.
"""

import numpy as np
from pathlib import Path
from tqdm import tqdm
import argparse
from typing import cast, Dict, List, Tuple, Optional
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoTokenizer
from genslm_esm.modeling import GenslmEsmcModelOutput
from genslm_esm.data import FastaDataset, GenslmEsmcDataCollator
import pandas as pd
from collections import defaultdict
import sys

# ============================================================================
# CUSTOM DATASET WITH TRACKING
# ============================================================================

class TrackedFastaDataset(FastaDataset):
    """FastaDataset that tracks original sequence indices for reconstruction"""
    
    def __init__(self, sequences: List[str], *args, **kwargs):
        #print(sequences[0])
        sys.stdout.flush()
        super().__init__(sequences=sequences, *args, **kwargs)
        self.original_sequences = sequences  # Keep original sequences
    
    def __getitem__(self, idx):
        item = super().__getitem__(idx)
        # Add the original index and sequence to the item dict
        item['original_idx'] = idx
        item['original_seq'] = self.original_sequences[idx]
        return item


class TrackedCollator(GenslmEsmcDataCollator):
    """Collator that preserves tracking information"""
    
    def __call__(self, batch):
        # Extract tracking info before calling parent collator
        original_indices = [item.pop('original_idx') for item in batch]
        original_seqs = [item.pop('original_seq') for item in batch]
        
        # Call parent collator
        result = super().__call__(batch)
        
        # Add tracking info back
        result['original_indices'] = original_indices
        result['original_seqs'] = original_seqs
        
        return result

# ============================================================================
# MAIN EMBEDDING FUNCTION
# ============================================================================

def load_model(model_id: str, device: str = "xpu"):
    """Load model and tokenizer"""
    model = AutoModel.from_pretrained(model_id, trust_remote_code=True)
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    
    model.to(torch.device(device))
    model.eval()
    
    try:
        model = model.to(torch.bfloat16)
    except Exception as e:
        print(f"Warning: Could not convert to bfloat16: {e}")
    
    return model, tokenizer



