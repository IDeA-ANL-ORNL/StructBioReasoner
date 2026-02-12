from __future__ import annotations
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

logger = logging.getLogger(__name__)

@parsl.python_app(executors=['gpu', 'htex'])
def embedding_task(
    sequences: list[str],
    model: object,
    tokenizer: object,
    inf_params: dict,
    device: str = 'xpu'
) -> dict:
    """Parsl task for folding a single sequence."""
        
    import struct_bio_reasoner.utils.embedding_utils as embedding_utils
    pbar = embedding_utils.create_dataloader(sequences,
                    tokenizer,
                    inf_params)

    all_embeddings = embedding_utils.embed_seqs(pbar, model, device)
    results = [(seq, emb) for seq, emb in zip(sequences, all_embeddings)]
    return results


@parsl.python_app(executors=['gpu', 'htex'])
def mutation_task(
        seq: str,
        model: object,
        tokenizer: object,
        alpha: float = 1.0,
        mode: str = 'protein',
        offset: int = 1,
        device: str = 'xpu'
        ) -> list[tuple[int, str, str]]:

    import scipy
    import struct_bio_reasoner.utils.embedding_utils as embedding_utils
    """Suggest mutations where P(mutant) > alpha * P(wild-type)."""
    exclude = {'B', 'J', 'O', 'U', 'X', 'Z', '-', '.', '<', '>', '[', ']'}

    logits = embedding_utils.predict_sequence_prob(model, tokenizer, seq, mode=mode, device=device)
    probs = scipy.special.softmax(logits, axis=1)

    vocab = tokenizer.get_vocab()
    id_to_token = {v: k for k, v in vocab.items()}

    mutations = []

    # Iterate over sequence positions (skip CLS=0, ignore EOS)
    for i in range(1, len(seq) + 1):
        pos = i - offset
        if pos < 0 or pos >= len(seq):
            continue

        wt_token = seq[pos]
        wt_j = vocab.get(wt_token, vocab.get(tokenizer.unk_token))
        wt_prob = probs[i, wt_j]

        for j in range(probs.shape[1]):
            mt = id_to_token[j]
            if mt in exclude or '<' in mt or mt == wt_token:
                continue
            mt_prob = probs[i, j]
            if mt_prob > alpha * wt_prob:
                mutations.append((pos, wt_token, mt))

    return mutations

