#!/usr/bin/env python3
"""Diversity sampling over protein embedding space.

Clusters pre-computed embeddings with FAISS k-means, then selects
representative sequences using Boltzmann importance sampling weighted
by optional free-energy scores.  Produces a sampled-set artifact
linked to the source embedding artifact in the DAG.

Usage examples::

    # Cluster + uniform sample from an embedding artifact
    python run_sampling.py --embeddings-json ./artifacts/artifacts/<id>.json \
        --n-clusters 100 --total-samples 500 --output-dir ./artifacts

    # Importance-sample using free-energy scores
    python run_sampling.py --embeddings-json ./artifacts/artifacts/<id>.json \
        --free-energies-json scores.json \
        --sampling-method importance --total-samples 500 --output-dir ./artifacts
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import sys
from itertools import chain
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from skills._shared.artifact import (
    ArtifactMetadata,
    ArtifactType,
    create_artifact,
)
from skills._shared.artifact_store import ArtifactStore
from skills._shared.provenance import ProvenanceTracker


# ── Clustering ─────────────────────────────────────────────────────────────

def faiss_cluster(
    embeddings: np.ndarray,
    n_clusters: int = 100,
    n_iter: int = 20,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """K-means via FAISS.  Returns (cluster_ids, centroids)."""
    try:
        import faiss
    except ImportError:
        logger.warning("faiss not installed — falling back to sklearn KMeans")
        return _sklearn_cluster(embeddings, n_clusters, seed)

    d = embeddings.shape[1]
    kmeans = faiss.Clustering(d, n_clusters)
    kmeans.niter = n_iter
    kmeans.seed = seed
    kmeans.verbose = False

    index = faiss.IndexFlatL2(d)
    emb_f32 = embeddings.astype("float32")
    kmeans.train(emb_f32, index)

    centroids = faiss.vector_float_to_array(kmeans.centroids).reshape(n_clusters, d).astype("float32")
    index_final = faiss.IndexFlatL2(d)
    index_final.add(centroids)
    _, cluster_ids = index_final.search(emb_f32, 1)
    return cluster_ids.flatten(), centroids


def _sklearn_cluster(
    embeddings: np.ndarray, n_clusters: int, seed: int
) -> Tuple[np.ndarray, np.ndarray]:
    from sklearn.cluster import MiniBatchKMeans

    km = MiniBatchKMeans(n_clusters=n_clusters, random_state=seed, batch_size=256)
    labels = km.fit_predict(embeddings)
    return labels, km.cluster_centers_


# ── Sampling ───────────────────────────────────────────────────────────────

def uniform_sample(
    cluster_dict: Dict[int, List[Dict]],
    total_samples: int,
    min_per_cluster: int = 1,
    max_per_cluster: int = 50,
) -> Dict[int, List[Dict]]:
    """Uniform sampling — equal draws per cluster."""
    n_clusters = max(len(cluster_dict), 1)
    per_cluster = max(min_per_cluster, min(total_samples // n_clusters, max_per_cluster))
    sampled: Dict[int, List[Dict]] = {}
    for cid, members in cluster_dict.items():
        k = min(per_cluster, len(members))
        sampled[cid] = random.sample(members, k)
    return sampled


def importance_sample(
    cluster_dict: Dict[int, List[Dict]],
    free_energies: Dict[str, float],
    total_samples: int,
    min_per_cluster: int = 2,
    max_per_cluster: int = 50,
) -> Dict[int, List[Dict]]:
    """Boltzmann importance sampling weighted by free energy per cluster."""
    # Gather per-cluster free energies
    fe_per_cluster: Dict[int, List[float]] = {}
    for cid, members in cluster_dict.items():
        fes = []
        for m in members:
            seq = m.get("sequence", "")
            if seq in free_energies:
                fes.append(free_energies[seq])
        fe_per_cluster[cid] = fes

    all_fes = list(chain.from_iterable(fe_per_cluster.values()))
    if not all_fes:
        logger.info("No free-energy scores found — falling back to uniform sampling")
        return uniform_sample(cluster_dict, total_samples, min_per_cluster, max_per_cluster)

    max_fe = max(all_fes)
    std_fe = max(np.std(all_fes), 1e-8)

    # Boltzmann weight per cluster
    boltz: Dict[int, float] = {}
    for cid, fes in fe_per_cluster.items():
        if not fes:
            boltz[cid] = 1.0
            continue
        boltz[cid] = sum(math.exp(-(f - max_fe) / std_fe) for f in fes)

    partition = sum(boltz.values())
    probs = {cid: b / partition for cid, b in boltz.items()}

    # Allocate samples
    count_per_cluster: Dict[int, int] = {}
    for cid, p in probs.items():
        count_per_cluster[cid] = min(max(math.ceil(p * total_samples), min_per_cluster), max_per_cluster)

    sampled: Dict[int, List[Dict]] = {}
    for cid, members in cluster_dict.items():
        k = min(count_per_cluster.get(cid, min_per_cluster), len(members))
        sampled[cid] = random.sample(members, k)
    return sampled


# ── Main ───────────────────────────────────────────────────────────────────

def run_sampling(
    embeddings_data: List[Dict[str, Any]],
    source_artifact_id: Optional[str] = None,
    n_clusters: int = 100,
    total_samples: int = 500,
    sampling_method: str = "uniform",
    free_energies: Optional[Dict[str, float]] = None,
    min_per_cluster: int = 2,
    max_per_cluster: int = 50,
    output_dir: str = "./artifacts",
) -> Dict[str, Any]:
    """Cluster embeddings and sample representatives."""
    store = ArtifactStore(output_dir)
    tracker = ProvenanceTracker(output_dir)

    parent_ids = (source_artifact_id,) if source_artifact_id else ()
    record = tracker.start_run(
        skill_name="protein-lm",
        input_artifact_ids=list(parent_ids),
        parameters={
            "task": "sample",
            "n_clusters": n_clusters,
            "total_samples": total_samples,
            "sampling_method": sampling_method,
        },
    )

    # Build numpy array of embeddings
    emb_list = [np.array(e["embedding"], dtype="float32") for e in embeddings_data]
    embeddings = np.stack(emb_list)

    # Adjust n_clusters if more clusters than sequences
    n_clusters = min(n_clusters, len(embeddings))

    cluster_ids, centroids = faiss_cluster(embeddings, n_clusters=n_clusters)

    # Build cluster dict
    cluster_dict: Dict[int, List[Dict]] = {}
    for idx, cid in enumerate(cluster_ids):
        cid_int = int(cid)
        if cid_int not in cluster_dict:
            cluster_dict[cid_int] = []
        cluster_dict[cid_int].append(embeddings_data[idx])

    # Sample
    if sampling_method == "importance" and free_energies:
        sampled = importance_sample(cluster_dict, free_energies, total_samples, min_per_cluster, max_per_cluster)
    else:
        sampled = uniform_sample(cluster_dict, total_samples, min_per_cluster, max_per_cluster)

    # Flatten results
    sampled_flat: List[Dict[str, Any]] = []
    for cid, members in sampled.items():
        for m in members:
            sampled_flat.append({
                "header": m.get("header", ""),
                "sequence": m.get("sequence", ""),
                "cluster_id": cid,
            })

    artifact = create_artifact(
        parent_ids=parent_ids,
        metadata=ArtifactMetadata(
            artifact_type=ArtifactType.ANALYSIS,
            skill_name="protein-lm",
            tags=frozenset({"protein-lm", "diversity-sampling", sampling_method}),
            extra=(
                ("n_clusters", str(n_clusters)),
                ("total_sampled", str(len(sampled_flat))),
                ("sampling_method", sampling_method),
            ),
        ),
        data={
            "sampled_sequences": sampled_flat,
            "n_clusters": n_clusters,
            "cluster_sizes": {str(k): len(v) for k, v in cluster_dict.items()},
        },
        run_id=record.run_id,
    )
    store.put(artifact)
    tracker.finish_run(record.run_id, output_artifact_ids=[artifact.artifact_id])

    logger.info(
        "Stored sampling artifact %s (%d sequences from %d clusters)",
        artifact.artifact_id, len(sampled_flat), len(cluster_dict),
    )
    return {
        "artifact_id": artifact.artifact_id,
        "run_id": record.run_id,
        "n_clusters": n_clusters,
        "total_sampled": len(sampled_flat),
        "sampling_method": sampling_method,
        "output_path": str(Path(output_dir) / "artifacts" / f"{artifact.artifact_id}.json"),
    }


# ── CLI ────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_sampling",
        description="Diversity sampling over protein embedding space via clustering.",
    )
    p.add_argument(
        "--embeddings-json", type=str, required=True,
        help="Path to embedding artifact JSON (from run_embedding.py)",
    )
    p.add_argument("--n-clusters", type=int, default=100, help="Number of k-means clusters")
    p.add_argument("--total-samples", type=int, default=500, help="Target number of sampled sequences")
    p.add_argument(
        "--sampling-method", choices=["uniform", "importance"], default="uniform",
        help="Sampling strategy (default: uniform)",
    )
    p.add_argument(
        "--free-energies-json", type=str, default=None,
        help="JSON file mapping sequence → free energy (for importance sampling)",
    )
    p.add_argument("--min-per-cluster", type=int, default=2, help="Minimum samples per cluster")
    p.add_argument("--max-per-cluster", type=int, default=50, help="Maximum samples per cluster")
    p.add_argument("--output-dir", type=str, default="./artifacts", help="Artifact store root directory")
    p.add_argument("--seed", type=int, default=42, help="Random seed")
    return p


def main(argv: Optional[List[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    random.seed(args.seed)
    np.random.seed(args.seed)

    # Load embedding artifact
    emb_path = Path(args.embeddings_json)
    if not emb_path.exists():
        print(f"Error: embeddings file not found: {emb_path}", file=sys.stderr)
        sys.exit(1)

    with open(emb_path) as f:
        artifact_data = json.load(f)

    # Extract embeddings list from artifact envelope
    if "data" in artifact_data and "embeddings" in artifact_data["data"]:
        embeddings_data = artifact_data["data"]["embeddings"]
        source_artifact_id = artifact_data.get("artifact_id")
    elif isinstance(artifact_data, list):
        embeddings_data = artifact_data
        source_artifact_id = None
    else:
        print("Error: unrecognised embeddings JSON format", file=sys.stderr)
        sys.exit(1)

    # Load free energies
    free_energies: Optional[Dict[str, float]] = None
    if args.free_energies_json:
        with open(args.free_energies_json) as f:
            free_energies = json.load(f)

    result = run_sampling(
        embeddings_data=embeddings_data,
        source_artifact_id=source_artifact_id,
        n_clusters=args.n_clusters,
        total_samples=args.total_samples,
        sampling_method=args.sampling_method,
        free_energies=free_energies,
        min_per_cluster=args.min_per_cluster,
        max_per_cluster=args.max_per_cluster,
        output_dir=args.output_dir,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
