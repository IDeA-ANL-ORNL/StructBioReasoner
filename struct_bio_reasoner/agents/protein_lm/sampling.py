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
from abc import ABC, abstractmethod
import faiss
import random

class Sampling(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def prepare(self):
        pass

    @abstractmethod
    def call(self):
        pass

    @abstractmethod
    def postprocess(self):
        pass

class ImportanceSampling(Sampling):
    def __init__(self,
                sampling_params = {'min_per_cluster': 2, 'max_per_cluster': 20},
                ): 
        self.min_per_cluster = sampling_params['min_per_cluster']
        self.max_per_cluster = sampling_params['max_per_cluster']

    def num_sample_per_clust(self, free_en_dict, total_sequences):
        '''
        The total sequences is sort of an approximation for the number of sequences
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
            count_per_clust[c] = min(max(math.ceil(probs * total_sequences), self.min_per_clust), self.max_per_clust)
    
        return count_per_clust

    def prepare(self, cluster_dict, seq_free_ens, total_sequences):
        
        free_en_dict = {}
        for c, val in cluster_dict.items():
            free_en_dict[c] = []
            members = val['members']
            cluster_dict[c]['free_ens'] = []
            for m in members:
                if m[0] in seq_free_ens.keys():
                    cluster_dict[c]['free_ens'].append(seq_free_ens[m[0]])
                    free_en_dict[c].append(seq_free_ens[m[0]])
        
        count_per_cluster = num_per_cluster(free_en_dict, total_sequences)
                
        return count_per_cluster

    
    def __call__(self, cluster_dict, seq_free_ens, total_sequences):
        num_per_cluster = self.prepare(cluster_dict, seq_free_ens, total_sequences)
        cluster_reps = {}
        for clust, clust_list in cluster_dict.items():
            n_c = num_per_cluster[clust]
            cluster_reps[clust] = tuple(random.sample(clust_list, n_c))
        
        return cluster_reps

    def postprocess(self, emb_seq_results, cluster_ids):
        pass 
















if False:
    def num_sample_per_clust(self, free_en_dict, total_sequences=5_000, min_per_clust=2, max_per_clust=100):
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

    def prepare(self, emb_seq_results, n_clusters, seq_free_ens):
        cluster_ids = self.cluster(emb_seq_results, n_clusters)
        
        cluster_dict = {}
        for it_e, (e_s_m, c) in enumerate(zip(emb_seq_results, cluster_ids)): 
            if c not in cluster_dict.keys():
                cluster_dict[c] = {'members': [], 'free_ens': []}
                cluster_dict[c]['members'].append(e_s_m)

                if e_s_m[0] in seq_free_ens.keys():
                    cluster_dict[c]['free_ens'].append(seq_free_ens[e_s_m[0]])

        



        return emb_seq_clusts, centroids
