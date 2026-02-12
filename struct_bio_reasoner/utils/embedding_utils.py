from __future__ import annotations
"""Utils for embedding sequences in protein language model latent spaces.
Currently optimized for GenSLM-ESM embeddings but generalizable for other protein lang models
This version maintains batch efficiency while tracking which embedding
corresponds to which sequence/path.
"""

import numpy as np
import math
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
from dataclasses import dataclass
import torch
import torch.nn.functional as F
from transformers import EsmTokenizer, EsmForMaskedLM
import random

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

def create_dataloader(sequences,
                      tokenizer,
                      inf_params,
                        ):
    dataset = FastaDataset(
        sequences=sequences,
        return_codon=inf_params['return_codon'],
        return_aminoacid=inf_params['return_aminoacid'],
        contains_nucleotide=inf_params['return_codon'],
    )
    
    # Create the collator
    collator = GenslmEsmcDataCollator(
        return_codon=inf_params['return_codon'],
        return_aminoacid=inf_params['return_aminoacid'],
        tokenizer=tokenizer,
    )
    
    # Create dataloader
    dataloader = DataLoader(
        dataset,
        batch_size=inf_params['batch_size'],
        collate_fn=collator,
        num_workers=inf_params['num_workers'],
        pin_memory=True,
    )
    return dataloader

def embed_seqs(pbar, model, device):
    all_embeddings = []
    with torch.no_grad():
        for batch in tqdm(pbar):
            # Move batch to device
            items = batch.to(torch.device(device))
            
            # Run model
            outputs = cast(GenslmEsmcModelOutput, model(**items))
            
            assert outputs.hidden_states is not None, "Hidden states are None"
            
            # Get last hidden state and mean pool
            embeddings = outputs.hidden_states[-1]
            embeddings = embeddings.mean(dim=1).to(torch.float32).cpu().numpy()
            all_embeddings.extend(embeddings)

    return all_embeddings

def num_sample_per_clust(free_en_dict, total_sequences=5_000, min_per_clust=2, max_per_clust=100):
    '''
    The total sequences is sort of an approximation for the number of sequences
    I'm too lazy to get the arithmetic to precisely get sum(clusters) = total_sequences
    '''
    prob_per_clust = {}
    merged_free_ens = list(chain.from_iterable(free_en_dict.values()))
    mean_free_en = np.mean(merged_free_ens)
    max_free_en = np.max(merged_free_ens)
    std_free_en = np.std(merged_free_ens)
    boltz_per_clust = {}
    for c, fs in free_en_dict.items():
        if len(fs)<1:
            boltz_per_clust[c] = 1
            continue
        boltz_per_clust[c] = np.sum([math.exp(-(f-max_free_en)/std_free_en) for f in fs])
    clust_partitions = np.sum(list(chain.from_iterable(boltz_per_clust.values()))) 
    prob_per_clust = {c: boltz/clust_partitions for c, boltz in boltz_per_clust.items()}
    
    count_per_clust = {}

    for c, probs in prob_per_clust.items():
        count_per_clust[c] = min(max(math.ceil(probs * total_sequences), min_per_clust), max_per_clust)

    return count_per_clust

def predict_sequence_prob(model, tokenizer, seq, mode = 'protein', device='xpu'):
    if mode == 'dna':
        from genslm_esm.data import group_codons
        seq_processed = group_codons(seq.upper())
    else:
        seq_processed = ' '.join(seq.upper())
    
    # Tokenize
    inputs = tokenizer(
        seq_processed,
        return_tensors='pt',
        padding=False,
        truncation=True,
        max_length=1024,
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}
    
    # Forward pass
    with torch.no_grad():
        if mode == 'dna':
            outputs = model(
                codon_input_ids=inputs['input_ids'],
                codon_attention_mask=inputs['attention_mask'],
            )
            logits = outputs.codon_logits
        else:
            outputs = model(
                aminoacid_input_ids=inputs['input_ids'],
                aminoacid_attention_mask=inputs['attention_mask'],
            )
            logits = outputs.aminoacid_logits
    
    return logits[0].cpu().numpy()



''' class for sampling mutations with different strategies
>>>     # 1. Pure iterative sampling
>>>     iter_seq = iterative_constrained_sampling(
>>>         sequence, model, tokenizer, positions_to_vary,
>>>         num_iterations=20, mask_fraction=0.3, temperature=1.2, device=device
>>>     )
>>>     num_mutations_iter = sum(a != b for a, b in zip(sequence, iter_seq))
>>>     
>>>     # 2. Beam search
>>>     beam_results = beam_search_mutations(
>>>         sequence, model, tokenizer, positions_to_vary,
>>>         beam_width=5, num_steps=min(10, len(positions_to_vary)), device=device
>>>     )
>>>     for i, (seq, log_prob) in enumerate(beam_results[:3]):
>>>         num_mut = sum(a != b for a, b in zip(sequence, seq))
>>>         print(f"   Rank {i+1}: {num_mut} mutations, log_prob={log_prob:.2f}")
>>>     
>>>     # 3. Hybrid
>>>     hybrid_results = beam_search_with_sampling(
>>>         sequence, model, tokenizer, positions_to_vary,
>>>         beam_width=5, num_iterations=15, mask_fraction=0.3, temperature=1.0, device=device
>>>     )
>>>     for i, (seq, score) in enumerate(hybrid_results):
>>>         num_mut = sum(a != b for a, b in zip(sequence, seq))
>>>         print(f"   Rank {i+1}: {num_mut} mutations, score={score:.2f}")
>>>     
>>>     # Diversity analysis
>>>     all_seqs = [iter_seq] + [s for s, _ in beam_results] + [s for s, _ in hybrid_results]
>>>     unique_seqs = len(set(all_seqs))
>>> 
>>> # Run comparison
>>> compare_methods(original_seq, model, tokenizer, positions_to_vary=[10, 20, 30, 40, 50], device=device)
'''

@dataclass
class SamplingMutations:
    model: object
    tokenizer: object
    positions_to_vary: list(int) = []
    num_iterations: int = 20
    mask_fraction: float = 0.3
    temperature: float = 1.0
    top_p: int = 0.9
    device: str = 'xpu'
    
    def __post_init__(self):
        if self.positions_to_vary == []:
            self.positions_to_vary = [i for i in range(len(current_sequence))]
       
    def iterative_constrained_sampling(
        self,
        sequence,
    ):
        """
        Iteratively refine only specific positions.
    
        Args:
            positions_to_vary: list of 0-indexed positions allowed to mutate
            num_iterations: number of refinement cycles
            mask_fraction: fraction of variable positions to mask per iteration
        """
        current_sequence = sequence
    
        for iteration in range(self.num_iterations):
            # Tokenize
            inputs = self.tokenizer(current_sequence, return_tensors="pt").to(self.device)
            input_ids = inputs['input_ids']
    
            # Select subset of variable positions to mask this iteration
            num_to_mask = max(1, int(len(self.positions_to_vary) * self.mask_fraction))
            positions_this_iter = random.sample(self.positions_to_vary, num_to_mask)
    
            # Mask selected positions (add 1 for special token offset)
            masked_ids = input_ids.clone()
            for pos in positions_this_iter:
                masked_ids[0, pos + 1] = self.tokenizer.mask_token_id
    
            # Predict
            with torch.no_grad():
                outputs = self.model(masked_ids)
                logits = outputs.logits[0]
    
            # Sample for each masked position
            for pos in positions_this_iter:
                pos_token = pos + 1
                pos_logits = logits[pos_token] / self.temperature
    
                # Nucleus sampling
                probs = F.softmax(pos_logits, dim=-1)
                sorted_probs, sorted_indices = torch.sort(probs, descending=True)
                cumulative_probs = torch.cumsum(sorted_probs, dim=-1)
    
                # Find cutoff
                cutoff_mask = cumulative_probs <= self.top_p
                if not cutoff_mask.any():
                    cutoff_mask[0] = True
    
                top_indices = sorted_indices[cutoff_mask]
                top_probs = sorted_probs[cutoff_mask]
                top_probs = top_probs / top_probs.sum()
    
                # Sample
                sampled_idx = torch.multinomial(top_probs, 1).item()
                sampled_id = top_indices[sampled_idx].item()
    
                input_ids[0, pos_token] = sampled_id
    
            # Update sequence
            current_sequence = self.tokenizer.decode(input_ids[0], skip_special_tokens=True).replace(" ", "")
    
        return current_sequence
    
    
    def beam_search_mutations(
        self,
        sequence,
        beam_width=5,
        num_steps=10,
    ):
        """
        Beam search for protein mutations.
        Explores top-k probable sequences at each step.
        
        Returns:
            List of (sequence, cumulative_log_prob) tuples
        """
        # Initialize beam with original sequence
        beams = [(sequence, 0.0)]  # (sequence, cumulative_log_prob)
        
        positions_list = list(positions_to_vary)
        random.shuffle(positions_list)  # Random order for positions
        
        for step in range(min(num_steps, len(positions_list))):
            pos = positions_list[step]
            all_candidates = []
            
            for seq, cum_log_prob in beams:
                # Tokenize
                inputs = self.tokenizer(seq, return_tensors="pt").to(self.device)
                input_ids = inputs['input_ids']
                
                # Mask this position
                masked_ids = input_ids.clone()
                masked_ids[0, pos + 1] = self.tokenizer.mask_token_id
                
                # Get predictions
                with torch.no_grad():
                    outputs = self.model(masked_ids)
                    logits = outputs.logits[0, pos + 1]
                    log_probs = F.log_softmax(logits, dim=-1)
                
                # Get top-k candidates for this position
                top_k_log_probs, top_k_ids = torch.topk(log_probs, beam_width)
                
                for log_prob, token_id in zip(top_k_log_probs, top_k_ids):
                    # Create new sequence with this mutation
                    new_ids = input_ids.clone()
                    new_ids[0, pos + 1] = token_id
                    new_seq = tokenizer.decode(new_ids[0], skip_special_tokens=True).replace(" ", "")
                    
                    # Update cumulative probability
                    new_cum_log_prob = cum_log_prob + log_prob.item()
                    all_candidates.append((new_seq, new_cum_log_prob))
            
            # Keep top beam_width sequences
            all_candidates.sort(key=lambda x: x[1], reverse=True)
            beams = all_candidates[:beam_width]
        
        return beams

    def beam_search_with_sampling(
        self,
        sequence,
        beam_width=5,
        num_iterations=20,
        device='xpu'
    ):
        """
        Hybrid approach: maintain multiple beams, but use sampling within each beam.
        
        Combines exploration (sampling) with exploitation (beam search).
        """
        # Initialize beams
        beams = [(sequence, 0.0) for _ in range(beam_width)]
        
        for iteration in range(num_iterations):
            new_beams = []
            
            for beam_seq, cum_score in beams:
                # Iterative sampling on this beam
                inputs = self.tokenizer(beam_seq, return_tensors="pt").to(self.device)
                input_ids = inputs['input_ids']
                
                # Select positions to mask
                num_to_mask = max(1, int(len(self.positions_to_vary) * self.mask_fraction))
                positions_this_iter = random.sample(self.positions_to_vary, num_to_mask)
                
                # Mask positions
                masked_ids = input_ids.clone()
                for pos in positions_this_iter:
                    masked_ids[0, pos + 1] = self.tokenizer.mask_token_id
                
                # Predict
                with torch.no_grad():
                    outputs = self.model(masked_ids)
                    logits = outputs.logits[0]
                
                total_log_prob = 0.0
                
                # Sample for each position
                for pos in positions_this_iter:
                    pos_token = pos + 1
                    pos_logits = logits[pos_token] / temperature
                    probs = F.softmax(pos_logits, dim=-1)
                    
                    sampled_id = torch.multinomial(probs, 1).item()
                    input_ids[0, pos_token] = sampled_id
                    total_log_prob += torch.log(probs[sampled_id]).item()
                
                # Update sequence and score
                new_seq = self.tokenizer.decode(input_ids[0], skip_special_tokens=True).replace(" ", "")
                new_score = cum_score + total_log_prob / len(positions_this_iter)
                
                new_beams.append((new_seq, new_score))
            
            # Keep top beam_width sequences
            new_beams.sort(key=lambda x: x[1], reverse=True)
            beams = new_beams[:beam_width]
        
        return beams


