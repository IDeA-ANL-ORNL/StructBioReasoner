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

class Clustering(ABC):
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

class FaissClustering(Clustering):
    def __init__(self,
                ):
        
        n_iter = 20
        self.n_iter = n_iter

    def prepare(self, emb_seq_results, n_clusters):
        embeddings = [e_s_pairs[1] for e_s_pairs in emb_seq_pairs] 
        kmeans = faiss.Clustering(embeddings.shape[1], n_clusters)
        kmeans.niter = self.n_iter
        kmeans.verbose = True
        kmeans.seed = 42

        index = faiss.IndexFlatL2(embeddings.shape[1])
        
        return embeddings, kmeans, index

    def run(self, embeddings, kmeans, index):

        kmeans.train(embeddings, index) 

        # Convert FAISS Float32Vector to numpy array
        centroids_vector = kmeans.centroids
        centroids = faiss.vector_float_to_array(centroids_vector)
        centroids = centroids.reshape(n_clusters, embeddings.shape[1]).astype('float32')
        
        # Get cluster assignments
        index_final = faiss.IndexFlatL2(embeddings.shape[1])
        index_final.add(centroids)  # Now this is a numpy array
        distances, cluster_ids = index_final.search(embeddings, 1)
        cluster_ids = cluster_ids.flatten()
        return cluster_ids
    
    def __call__(self, emb_seq_results, n_clusters):
        embeddings, kmeans, index = self.prepare(emb_seq_results, n_clusters)
        cluster_ids = self.run(embeddings, kmeans, index)
        cluster_dict = self.postprocess(emb_seq_results, cluster_ids)
        return cluster_dict

    def postprocess(self, emb_seq_results, cluster_ids):
        cluster_dict = {}
        for it_e, (e_s_m, c) in enumerate(zip(emb_seq_results, cluster_ids)): 
            if c not in cluster_dict.keys():
                cluster_dict[c] = {'members': []}
                cluster_dict[c]['members'].append(e_s_m)
        return cluster_dict

















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
