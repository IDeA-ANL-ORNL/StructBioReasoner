#!/usr/bin/env python3
"""Protein language model embedding and mutation-effect prediction.

Wraps ESM-2 and GenSLM-ESMc models to produce per-sequence embeddings and
optionally score single-point mutations.  Outputs are stored as Artifact DAG
nodes so downstream skills (clustering, sampling) can consume them.

Usage examples::

    # Embed sequences from a FASTA file using ESM-2
    python run_embedding.py --fasta sequences.fasta --model esm2 --output-dir ./out

    # Embed inline sequences using GenSLM
    python run_embedding.py --sequences MKTLIF MGSSHHH --model genslm --output-dir ./out

    # Predict mutation effects
    python run_embedding.py --sequences MKTLIFAGL --model esm2 --task mutation_effect \
        --mutations A3G L7F --output-dir ./out
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Lazy imports — torch / transformers are heavy; only import when needed.
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# Resolve project root so ``skills._shared`` is importable.
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


# ── Helpers ────────────────────────────────────────────────────────────────

def _read_fasta(path: str | Path) -> List[Tuple[str, str]]:
    """Return list of (header, sequence) from a FASTA file."""
    entries: List[Tuple[str, str]] = []
    header = ""
    seq_parts: List[str] = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line.startswith(">"):
                if header or seq_parts:
                    entries.append((header, "".join(seq_parts)))
                header = line[1:]
                seq_parts = []
            elif line:
                seq_parts.append(line)
    if header or seq_parts:
        entries.append((header, "".join(seq_parts)))
    return entries


# ── Model backends ─────────────────────────────────────────────────────────

class _ESM2Backend:
    """Mean-pool last hidden state from ESM-2 (facebook/esm2_*)."""

    def __init__(self, model_name: str = "facebook/esm2_t6_8M_UR50D", device: str = "cpu"):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.device = torch.device(device)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(self.device).eval()

    def embed(self, sequences: List[str], batch_size: int = 32) -> np.ndarray:
        import torch

        all_embs: List[np.ndarray] = []
        for i in range(0, len(sequences), batch_size):
            batch = sequences[i : i + batch_size]
            tokens = self.tokenizer(batch, return_tensors="pt", padding=True, truncation=True).to(self.device)
            with torch.no_grad():
                out = self.model(**tokens)
            # Mean-pool over sequence length (dim=1), skip special tokens via attention mask
            mask = tokens["attention_mask"].unsqueeze(-1).float()
            hidden = out.last_hidden_state * mask
            embs = (hidden.sum(dim=1) / mask.sum(dim=1)).cpu().numpy()
            all_embs.append(embs)
        return np.concatenate(all_embs, axis=0)

    def predict_mutation_scores(
        self, sequence: str, mutations: List[str], alpha: float = 1.0
    ) -> List[Dict[str, Any]]:
        """Score mutations via masked marginal probability ratio."""
        import scipy.special
        import torch

        tokens = self.tokenizer(sequence, return_tensors="pt").to(self.device)
        with torch.no_grad():
            logits = self.model(**tokens).last_hidden_state  # (1, L, vocab)
        # For ESM masked-marginal we use the logits directly
        logits_np = logits[0].cpu().numpy()
        probs = scipy.special.softmax(logits_np, axis=-1)
        vocab = self.tokenizer.get_vocab()
        results: List[Dict[str, Any]] = []
        for mut in mutations:
            wt_aa, pos_str, mt_aa = mut[0], mut[1:-1], mut[-1]
            pos = int(pos_str)
            # +1 for CLS token offset
            idx = pos + 1
            if idx >= probs.shape[0]:
                results.append({"mutation": mut, "error": "position out of range"})
                continue
            wt_prob = probs[idx, vocab.get(wt_aa, 0)]
            mt_prob = probs[idx, vocab.get(mt_aa, 0)]
            ratio = float(mt_prob / wt_prob) if wt_prob > 0 else float("inf")
            results.append({
                "mutation": mut,
                "wt_prob": float(wt_prob),
                "mt_prob": float(mt_prob),
                "ratio": ratio,
                "favourable": ratio > alpha,
            })
        return results


class _GenSLMBackend:
    """Mean-pool last hidden state from GenSLM-ESMc contrastive model."""

    def __init__(
        self,
        model_name: str = "genslm-test/genslm-esmc-600M-contrastive",
        device: str = "cpu",
    ):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.device = torch.device(device)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(model_name, trust_remote_code=True).to(self.device).eval()

    def embed(self, sequences: List[str], batch_size: int = 32) -> np.ndarray:
        import torch

        try:
            from genslm_esm.data import FastaDataset, GenslmEsmcDataCollator
            from genslm_esm.modeling import GenslmEsmcModelOutput
            return self._embed_genslm_native(sequences, batch_size)
        except ImportError:
            return self._embed_hf_fallback(sequences, batch_size)

    def _embed_genslm_native(self, sequences: List[str], batch_size: int) -> np.ndarray:
        """Use GenSLM native dataset/collator when available."""
        import torch
        from typing import cast
        from torch.utils.data import DataLoader
        from genslm_esm.data import FastaDataset, GenslmEsmcDataCollator
        from genslm_esm.modeling import GenslmEsmcModelOutput

        dataset = FastaDataset(
            sequences=sequences,
            return_codon=False,
            return_aminoacid=True,
            contains_nucleotide=False,
        )
        collator = GenslmEsmcDataCollator(
            return_codon=False,
            return_aminoacid=True,
            tokenizer=self.tokenizer,
        )
        loader = DataLoader(dataset, batch_size=batch_size, collate_fn=collator, num_workers=0)
        all_embs: List[np.ndarray] = []
        with torch.no_grad():
            for batch in loader:
                items = batch.to(self.device)
                outputs = cast(GenslmEsmcModelOutput, self.model(**items))
                assert outputs.hidden_states is not None
                embs = outputs.hidden_states[-1].mean(dim=1).float().cpu().numpy()
                all_embs.append(embs)
        return np.concatenate(all_embs, axis=0)

    def _embed_hf_fallback(self, sequences: List[str], batch_size: int) -> np.ndarray:
        """Fallback using plain HuggingFace tokenizer."""
        import torch

        all_embs: List[np.ndarray] = []
        for i in range(0, len(sequences), batch_size):
            batch = sequences[i : i + batch_size]
            tokens = self.tokenizer(batch, return_tensors="pt", padding=True, truncation=True).to(self.device)
            with torch.no_grad():
                out = self.model(**tokens)
            hidden = out.last_hidden_state if hasattr(out, "last_hidden_state") else out.hidden_states[-1]
            embs = hidden.mean(dim=1).float().cpu().numpy()
            all_embs.append(embs)
        return np.concatenate(all_embs, axis=0)

    def predict_mutation_scores(
        self, sequence: str, mutations: List[str], alpha: float = 1.0
    ) -> List[Dict[str, Any]]:
        """GenSLM mutation scoring (same masked marginal approach)."""
        import scipy.special
        import torch

        tokens = self.tokenizer(sequence, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model(**tokens)
        logits = out.last_hidden_state if hasattr(out, "last_hidden_state") else out.hidden_states[-1]
        logits_np = logits[0].cpu().numpy()
        probs = scipy.special.softmax(logits_np, axis=-1)
        vocab = self.tokenizer.get_vocab()
        results: List[Dict[str, Any]] = []
        for mut in mutations:
            wt_aa, pos_str, mt_aa = mut[0], mut[1:-1], mut[-1]
            pos = int(pos_str)
            idx = pos + 1
            if idx >= probs.shape[0]:
                results.append({"mutation": mut, "error": "position out of range"})
                continue
            wt_prob = probs[idx, vocab.get(wt_aa, 0)]
            mt_prob = probs[idx, vocab.get(mt_aa, 0)]
            ratio = float(mt_prob / wt_prob) if wt_prob > 0 else float("inf")
            results.append({
                "mutation": mut,
                "wt_prob": float(wt_prob),
                "mt_prob": float(mt_prob),
                "ratio": ratio,
                "favourable": ratio > alpha,
            })
        return results


def _get_backend(model: str, device: str):
    if model == "genslm":
        return _GenSLMBackend(device=device)
    return _ESM2Backend(device=device)


# ── Main ───────────────────────────────────────────────────────────────────

def run_embedding(
    sequences: List[str],
    headers: List[str],
    model: str = "esm2",
    device: str = "cpu",
    batch_size: int = 32,
    output_dir: str = "./artifacts",
    parent_ids: Tuple[str, ...] = (),
) -> Dict[str, Any]:
    """Compute embeddings, store as artifact, return result dict."""
    store = ArtifactStore(output_dir)
    tracker = ProvenanceTracker(output_dir)

    record = tracker.start_run(
        skill_name="protein-lm",
        parameters={"model": model, "task": "embedding", "n_sequences": len(sequences)},
    )

    backend = _get_backend(model, device)
    embeddings = backend.embed(sequences, batch_size=batch_size)

    # Build per-sequence result list
    results = []
    for i, (hdr, seq) in enumerate(zip(headers, sequences)):
        results.append({
            "header": hdr,
            "sequence": seq,
            "embedding": embeddings[i].tolist(),
        })

    artifact = create_artifact(
        parent_ids=parent_ids,
        metadata=ArtifactMetadata(
            artifact_type=ArtifactType.EMBEDDING,
            skill_name="protein-lm",
            tags=frozenset({"protein-lm", model, "embedding"}),
            extra=(("model", model), ("n_sequences", str(len(sequences)))),
        ),
        data={"embeddings": results},
        run_id=record.run_id,
    )
    store.put(artifact)
    tracker.finish_run(record.run_id, output_artifact_ids=[artifact.artifact_id])

    logger.info("Stored embedding artifact %s (%d seqs)", artifact.artifact_id, len(sequences))
    return {
        "artifact_id": artifact.artifact_id,
        "run_id": record.run_id,
        "n_sequences": len(sequences),
        "embedding_dim": int(embeddings.shape[1]),
        "output_path": str(Path(output_dir) / "artifacts" / f"{artifact.artifact_id}.json"),
    }


def run_mutation_effect(
    sequence: str,
    mutations: List[str],
    model: str = "esm2",
    device: str = "cpu",
    alpha: float = 1.0,
    output_dir: str = "./artifacts",
    parent_ids: Tuple[str, ...] = (),
) -> Dict[str, Any]:
    """Score mutations and store results as artifact."""
    store = ArtifactStore(output_dir)
    tracker = ProvenanceTracker(output_dir)

    record = tracker.start_run(
        skill_name="protein-lm",
        parameters={"model": model, "task": "mutation_effect", "mutations": mutations, "alpha": alpha},
    )

    backend = _get_backend(model, device)
    scores = backend.predict_mutation_scores(sequence, mutations, alpha=alpha)

    artifact = create_artifact(
        parent_ids=parent_ids,
        metadata=ArtifactMetadata(
            artifact_type=ArtifactType.SCORE,
            skill_name="protein-lm",
            tags=frozenset({"protein-lm", model, "mutation_effect"}),
            extra=(("model", model),),
        ),
        data={"sequence": sequence, "mutations": scores},
        run_id=record.run_id,
    )
    store.put(artifact)
    tracker.finish_run(record.run_id, output_artifact_ids=[artifact.artifact_id])

    logger.info("Stored mutation-effect artifact %s", artifact.artifact_id)
    return {
        "artifact_id": artifact.artifact_id,
        "run_id": record.run_id,
        "mutations": scores,
    }


# ── CLI ────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_embedding",
        description="Protein language model embeddings and mutation-effect prediction.",
    )
    p.add_argument("--fasta", type=str, default=None, help="Path to FASTA file with input sequences")
    p.add_argument("--sequences", nargs="+", default=None, help="Inline amino-acid sequences")
    p.add_argument("--model", choices=["esm2", "genslm"], default="esm2", help="Model backend (default: esm2)")
    p.add_argument("--task", choices=["embedding", "mutation_effect"], default="embedding", help="Task to run")
    p.add_argument("--mutations", nargs="+", default=None, help="Mutations to score (e.g. A3G L7F)")
    p.add_argument("--alpha", type=float, default=1.0, help="Threshold for favourable mutation ratio")
    p.add_argument("--device", type=str, default="cpu", help="Torch device (cpu, cuda, xpu)")
    p.add_argument("--batch-size", type=int, default=32, help="Batch size for embedding")
    p.add_argument("--output-dir", type=str, default="./artifacts", help="Artifact store root directory")
    p.add_argument("--parent-ids", nargs="*", default=[], help="Parent artifact IDs for provenance")
    return p


def main(argv: Optional[List[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # Collect sequences
    sequences: List[str] = []
    headers: List[str] = []
    if args.fasta:
        for hdr, seq in _read_fasta(args.fasta):
            headers.append(hdr)
            sequences.append(seq)
    if args.sequences:
        for i, seq in enumerate(args.sequences):
            headers.append(f"seq_{i}")
            sequences.append(seq)

    if not sequences:
        print("Error: provide --fasta or --sequences", file=sys.stderr)
        sys.exit(1)

    parent_ids = tuple(args.parent_ids)

    if args.task == "embedding":
        result = run_embedding(
            sequences=sequences,
            headers=headers,
            model=args.model,
            device=args.device,
            batch_size=args.batch_size,
            output_dir=args.output_dir,
            parent_ids=parent_ids,
        )
    elif args.task == "mutation_effect":
        if not args.mutations:
            print("Error: --mutations required for mutation_effect task", file=sys.stderr)
            sys.exit(1)
        result = run_mutation_effect(
            sequence=sequences[0],
            mutations=args.mutations,
            model=args.model,
            device=args.device,
            alpha=args.alpha,
            output_dir=args.output_dir,
            parent_ids=parent_ids,
        )
    else:
        print(f"Unknown task: {args.task}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
