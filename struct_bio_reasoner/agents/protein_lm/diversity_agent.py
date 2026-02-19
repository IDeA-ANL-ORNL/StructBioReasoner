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
#from struct_bio_reasoner.utils.embedding_utils import *
from itertools import chain
import asyncio
import logging
import parsl
from pathlib import Path
from typing import Any, Optional
from struct_bio_reasoner.agents.embedding.distributed import *
from struct_bio_reasoner.agents.embedding.embedding import GenSLMEmbed
logger = logging.getLogger(__name__)
from itertools import batched

class DivSampleAgent(Agent):
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
        embedding_type: str = 'genslm',
        clustering_method: str = 'faiss',
        sampling_method: str = 'importance',
        batch_size: int = 32,
        num_workers: int = 1,
        min_per_cluster = 2,
        max_per_cluster = 20,
        device: str = 'xpu',
    ):

        self.root = Path(root_path) # in case it's not already a Path
        self.device = device
        self.inf_params = {'batch_size': batch_size,
                            'num_workers': num_workers}

        self.sampling_params = {'min_per_cluster': min_per_cluster,
                                'max_per_cluster': max_per_cluster}
        ### TO-DO: add embedding, sampling, and generation to separate algorithms
        match embedding_type:
            case 'genslm':
                self.model_id = 'genslm-test/genslm-esmc-600M-contrastive'
                self.embed_alg = GenSLMEmbed
            case _:
                # GenSLM default
                self.embed_alg = GenSLMEmbed

        match clustering_method:
            case 'faiss':
                self.cluster_alg = FaissClustering 
            case _:
                # FAISS default
                self.cluster_alg = FaissClustering

        match sampling_method:
            case 'importance':
                self.sampling_alg = ImportanceSampling
            case 'uniform':
                self.sampling_alg = UniformSampling
            case _:
                self.sampling_alg = UniformSampling


    async def agent_on_startup(self):
        self.embedding_handle = self.agent_launch_alongside(
            self.embed_alg,
            args=(self.model_id,
                  self.inference_params,))

        self.clustering_handle = self.agent_launch_alongside(
            self.cluster_alg,
            args=None)
        
        self.sampling_handle = self.agent_launch_alongside(
            self.sampling_alg,
            args=(sampling_params,))

    @action
    async def prepare_run(self,):
        self.logger.info('Preparing diversity sampling for binders') 
         
    @action
    async def run_embeddings(all_sequences,
                    metadata,
                    chunk_size):

        seq_chunks = list(batched(all_sequences, chunk_size))
        if len(metadata)>0:
            meta_chunks = list(batched(metadata, chunk_size))
        else:
            meta_chunks = [[] for _ in range(len(seq_chunks))]
        futures = [asyncio.wrap_future(embedding_task(self.embedding_handle, s_chunk, m_chunk) for s_chunk, m_chunk in zip(seq_chunks, meta_chunks))]

        embeds = await asyncio.gather(*futures)

        return embeds

    @action
    async def run(self,
                all_sequences,
                metadata= [],
                seq_free_ens=[],
                chunk_size = 1000):
        
        embeds = await run_embedding(all_sequences,
                                     metadata,
                                     chunk_size)
        
        cluster_dict = self.clustering_handle(embeds, 1000)

        results = self.sampling_handle(cluster_dict, seq_free_ens, 10_000)
        
        return results 

    async def embedding_sequences(
                self,
                all_sequences,
                metadata= [],
                chunk_size = 1000
                ):

        '''
        run_embedding: seqs -> embeddings
        
        inputs:
            all_sequences: sampled sequences from rounds of binder design
            metadata: paths for folded sequences from binder design rounds
        outputs:
            [sequences, embeddings, paths]
        '''
        if len(all_sequences) < chunk_size:
            # Split in half
            mid = len(all_sequences) // 2
            chunks = [all_sequences[:mid], all_sequences[mid:]]
        else:
            # Split into chunks
            chunks = [all_sequences[i:i+chunk_size] for i in range(0, len(all_sequences), chunk_size)]
        futures = []
        for i, chunk_i in enumerate(chunks):
            futures.append(
                asyncio.wrap_future(
                    embedding_task(
                        chunk_i,
                        self.model,
                        self.tokenizer,
                        self.inf_params,
                        device='xpu')))

        emb_seq_pair_chunks = await asyncio.gather(*futures) 

        emb_seq_pairs = list(chain.from_iterable(emb_seq_pair_chunks))
        if len(metadata)<1:
            metadata = ['' for _ in range(len(emb_seq_pairs))]

        emb_seq_pairs = [(e[0], e[1], m) for (e, m) in zip(emb_seq_pairs, metadata)]
        return emb_seq_pairs
        
    @action
    async def cluster_embeddings(
        emb_seq_pairs,
        n_clusters=1_000,
        n_iter=20):
        
        embeddings = [e_s_pairs[1] for e_s_pairs in emb_seq_pairs] 
        sequences = [e_s_pairs[0] for e_s_pairs in emb_seq_pairs]
        metadata = [e_s_pairs[2] for e_s_pairs in emb_seq_pairs]
        n_cores = faiss.omp_get_max_threads()
        kmeans = faiss.Clustering(embeddings.shape[1], n_clusters)
        kmeans.niter = n_iter
        kmeans.verbose = True
        kmeans.seed = 42

        index = faiss.IndexFlatL2(embeddings.shape[1])
        kmeans.train(embeddings, index) 

        # Convert FAISS Float32Vector to numpy array
        # This is the key fix!
        centroids_vector = kmeans.centroids
        centroids = faiss.vector_float_to_array(centroids_vector)
        centroids = centroids.reshape(n_clusters, embeddings.shape[1]).astype('float32')
        
        # Get cluster assignments
        index_final = faiss.IndexFlatL2(embeddings.shape[1])
        index_final.add(centroids)  # Now this is a numpy array
        distances, cluster_ids = index_final.search(embeddings, 1)
        cluster_ids = cluster_ids.flatten()
        emb_seq_clusts = [(s, e, c, m) for (s, e, c, m) in zip(sequences, embeddings, cluster_ids, metadata)]
        return emb_seq_clusts, centroids

    @action
    async def sample_clusters(
        emb_seq_clusts,
        seq_free_ens,
        total_sequences=5_000,
        min_per_clust= 2,
        max_per_clust = 100,
        num_unkn_clust = 5):
        
        '''
        merge seq/emb + free en data into pools for each cluster
        '''
        cluster_dict = {}
        free_en_dict = {}
        for it_e, e in enumerate(enumerate(emb_seq_clusts)):
            if e[2] not in cluster_dict.keys():
                cluster_dict[e[2]] = []
            cluster_dict[e[2]].append(e)
            
            if e[0] in seq_free_ens.keys():
                if e[2] not in free_en_dict.keys():
                    free_en_dict[e[2]] = []
                free_en_dict[e[2]].append(seq_free_ens[e[0]])
        for c in cluster_dict.keys():
            if c not in free_en_dict.keys():
                free_en_dict[c] = []

        '''
        sample according to prob = exp(-FE_i/beta)/sum_i^N(exp(-FE_i/beta)) 
        '''
        num_per_cluster = num_sample_per_clust(free_en_dict,
                                total_sequences=total_sequences,
                                min_per_clust = min_per_clust,
                                max_per_clust = max_per_clust)

        cluster_reps = {}
        
        for clust, clust_list in cluster_dict.items():
            n_c = num_per_cluster[clust]
            cluster_reps[clust] = tuple(random.sample(clust_list, n_c))
        
        return cluster_reps

        
        
        
        
        
        
        
        


