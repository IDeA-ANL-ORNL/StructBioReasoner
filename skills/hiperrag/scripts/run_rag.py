#!/usr/bin/env python3
"""HiPerRAG literature mining skill — OpenClaw script.

Wraps the HiPerRAG RAG pipeline for literature search and synthesis,
supporting both ``interactome`` and ``binder_design`` prompt modes.
Integrates with the Artifact DAG (Layer 3) for provenance tracking.

Usage::

    python skills/hiperrag/scripts/run_rag.py \\
        --query "Identify interacting proteins for KRAS" \\
        --target-protein KRAS \\
        --prompt-type interactome

"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from skills._shared.artifact import (
    ArtifactMetadata,
    ArtifactType,
    create_artifact,
)
from skills._shared.artifact_dag import ArtifactDAG
from skills._shared.provenance import ProvenanceTracker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RAG Prompt Manager (ported from struct_bio_reasoner/prompts/prompts.py)
# ---------------------------------------------------------------------------

# Expected output schema for interactome queries
RAG_OUTPUT_SCHEMA = {
    "interactions": "list[string]",
    "interacting_protein_uniprot_ids": "list[string]",
    "cancer_pathways": "list[string]",
    "interaction_types": "list[string]",
    "therapeutic_rationales": "list[string]",
}


@dataclass
class RAGPromptManager:
    """Generate optimised prompts for HiPerRAG literature mining.

    Supports two prompt modes:

    * ``interactome`` — identify interacting proteins, pathways, and
      therapeutic rationales for a given target protein.
    * ``binder_design`` — find starting binder sequences and scaffolds
      for downstream BindCraft optimisation.
    """

    research_goal: str
    input_json: Dict[str, Any]
    target_protein: str
    prompt_type: str  # "interactome" | "binder_design"

    def running_prompt(self) -> str:
        """Build the RAG query prompt based on *prompt_type*."""
        if self.prompt_type == "interactome":
            return self._interactome_prompt()
        elif self.prompt_type == "binder_design":
            return self._binder_design_prompt()
        else:
            raise ValueError(
                f"Unknown prompt_type '{self.prompt_type}'. "
                "Expected 'interactome' or 'binder_design'."
            )

    def conclusion_prompt(self) -> str:
        """Build a cleanup/formatting prompt for raw RAG output."""
        return (
            f"Using hiper-rag output {self.input_json} clean up and return "
            "as json with the following information cleanly:\n"
            "- interacting_protein_name: string\n"
            "- interacting_protein_uniprot_id: string\n"
            "- cellular_pathway: string\n"
            '- interaction_type: string (e.g., "direct binding", "complex formation")\n'
            "- therapeutic_rationale: string"
        )

    # -- private helpers -----------------------------------------------------

    def _interactome_prompt(self) -> str:
        return (
            f"Given this research goal:\n{self.research_goal}\n\n"
            f"Generate an optimal prompt for a literature mining system (HiPerRAG) to identify:\n"
            f"1. Key proteins that physically interact with {self.target_protein}\n"
            f"2. Proteins involved in cellular pathways\n"
            f"3. Proteins where disrupting the {self.target_protein} interaction could have therapeutic benefit.\n\n"
            "The prompt should request structured output in JSON format with:\n"
            "- interacting_protein_name: string\n"
            "- interacting_protein_uniprot_id: string\n"
            "- cellular_pathway: string\n"
            '- interaction_type: string (e.g., "direct binding", "complex formation")\n'
            "- therapeutic_rationale: string\n\n"
            "Return ONLY the optimized prompt text, no additional explanation "
            "with the prompt in a json format. Strip any \\n characters or "
            "anything that obfuscates the output."
        )

    def _binder_design_prompt(self) -> str:
        return (
            f"Given this research goal:\n{self.research_goal}\n\n"
            "Generate an optimal prompt for literature mining using HiPerRAG to identify:\n"
            "starting binders for bindcraft optimization. If clinical evidence available "
            "use clinically relevant starting peptide otherwise use one of the default "
            "scaffolds for affibody/affitin/nanobody provided in the research goal or "
            f"best binders in the input_json {self.input_json}.\n"
            "Focus on returning a single peptide amino acid sequence and rationale for "
            "this in a json with these keys:\n"
            "- binder_sequence: string\n"
            "- rationale: string"
        )


# ---------------------------------------------------------------------------
# LLM Generator abstraction (lightweight port from rag_utils.py)
# ---------------------------------------------------------------------------


def _build_openai_generator(model: str, api_key: str, base_url: Optional[str] = None):
    """Return a callable ``(prompt: str) -> str`` using the OpenAI API."""
    try:
        import openai
    except ImportError:
        raise SystemExit(
            "openai package is required for the OpenAI generator. "
            "Install via: pip install openai"
        )

    kwargs: Dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = openai.OpenAI(**kwargs)

    def generate(prompt: str) -> str:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_completion_tokens=16384,
        )
        content = response.choices[0].message.content
        if content is None:
            return f"[No content returned. Finish reason: {response.choices[0].finish_reason}]"
        return content

    return generate


def _build_vllm_generator(model: str, server: str, port: int, api_key: str):
    """Return a callable ``(prompt: str) -> str`` using a vLLM endpoint."""
    import requests as _requests

    url = f"http://{server}:{port}/v1/chat/completions"

    def generate(prompt: str) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": 16384,
        }
        resp = _requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json=payload,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        return f"Error {resp.status_code}: {resp.text}"

    return generate


def _build_argo_generator(model: str, base_url: str):
    """Return a callable ``(prompt: str) -> str`` using the Argo proxy."""
    try:
        import openai
    except ImportError:
        raise SystemExit("openai package is required for the Argo generator.")

    client = openai.OpenAI(api_key="whatever+random", base_url=f"{base_url}/v1")

    def generate(prompt: str) -> str:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=16384,
        )
        return response.choices[0].message.content or ""

    return generate


def build_generator(args: argparse.Namespace):
    """Build an LLM generator callable from CLI arguments."""
    if args.generator == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise SystemExit(
                "OPENAI_API_KEY environment variable is required for the OpenAI generator."
            )
        return _build_openai_generator(
            model=args.model,
            api_key=api_key,
            base_url=os.environ.get("OPENAI_BASE_URL"),
        )
    elif args.generator == "vllm":
        return _build_vllm_generator(
            model=args.model,
            server=args.vllm_server,
            port=args.vllm_port,
            api_key=os.environ.get("VLLM_API_KEY", "CELS"),
        )
    elif args.generator == "argo":
        return _build_argo_generator(
            model=args.model,
            base_url=args.argo_base_url,
        )
    else:
        raise SystemExit(f"Unknown generator: {args.generator}")


# ---------------------------------------------------------------------------
# Optional: distllm retriever integration
# ---------------------------------------------------------------------------


def _try_build_retriever(config_path: Optional[str]):
    """Attempt to build a distllm Retriever from a config file.

    Returns ``None`` when distllm is not installed or no config is given.
    """
    if config_path is None:
        return None
    try:
        from distllm.rag.search import Retriever, RetrieverConfig
    except ImportError:
        logger.warning("distllm not installed — running without retrieval.")
        return None

    cfg_data = json.loads(Path(config_path).read_text())
    retriever_cfg = cfg_data.get("retriever_config")
    if retriever_cfg is None:
        return None
    return RetrieverConfig(**retriever_cfg).get_retriever()


# ---------------------------------------------------------------------------
# Core RAG pipeline
# ---------------------------------------------------------------------------


def run_rag(
    *,
    query: str,
    target_protein: str,
    prompt_type: str,
    generator_fn,
    retriever=None,
    retrieval_top_k: int = 200,
    retrieval_score_threshold: float = 0.1,
) -> Dict[str, Any]:
    """Execute a single RAG query and return structured results.

    Parameters
    ----------
    query:
        Free-text research question.
    target_protein:
        Name of the target protein (e.g. KRAS).
    prompt_type:
        ``"interactome"`` or ``"binder_design"``.
    generator_fn:
        Callable ``(prompt: str) -> str`` backed by an LLM.
    retriever:
        Optional distllm ``Retriever`` for document retrieval.
    retrieval_top_k:
        How many documents to retrieve.
    retrieval_score_threshold:
        Minimum similarity score for retrieved documents.

    Returns
    -------
    dict with keys ``prompt``, ``response``, ``retrieved_docs`` (count),
    ``prompt_type``, ``target_protein``.
    """

    # Build the optimised prompt via RAGPromptManager
    pm = RAGPromptManager(
        research_goal=query,
        input_json={},
        target_protein=target_protein,
        prompt_type=prompt_type,
    )
    optimised_prompt = pm.running_prompt()

    # If a retriever is available, prepend retrieved context
    context_docs: List[str] = []
    if retriever is not None:
        try:
            results, _ = retriever.search(
                [optimised_prompt],
                top_k=retrieval_top_k,
                score_threshold=retrieval_score_threshold,
            )
            context_docs = retriever.get_texts(results.total_indices[0])
            context_block = "\n\n[Context from retrieval]\n" + "\n".join(context_docs)
            optimised_prompt += context_block
            logger.info("Retrieved %d documents", len(context_docs))
        except Exception as exc:
            logger.warning("Retrieval failed, proceeding without context: %s", exc)

    # Generate response
    response = generator_fn(optimised_prompt)

    return {
        "prompt": optimised_prompt,
        "response": response,
        "retrieved_docs": len(context_docs),
        "prompt_type": prompt_type,
        "target_protein": target_protein,
    }


# ---------------------------------------------------------------------------
# Artifact DAG integration
# ---------------------------------------------------------------------------


def store_result_as_artifact(
    result: Dict[str, Any],
    dag: ArtifactDAG,
    run_id: str,
    parent_ids: tuple = (),
) -> str:
    """Persist a RAG result in the Artifact DAG and return the artifact ID."""
    metadata = ArtifactMetadata(
        artifact_type=ArtifactType.LITERATURE,
        skill_name="hiperrag",
        skill_version="0.1.0",
        tags=frozenset(
            ["rag", result["prompt_type"], result["target_protein"]]
        ),
    )
    artifact = dag.create_and_store(
        parent_ids=parent_ids,
        metadata=metadata,
        data=result,
        run_id=run_id,
    )
    return artifact.artifact_id


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_rag",
        description=(
            "HiPerRAG literature mining — search and synthesize structural "
            "biology literature using retrieval-augmented generation."
        ),
    )

    # Required arguments
    parser.add_argument(
        "--query", "-q",
        required=True,
        help="Research question or protein target description.",
    )
    parser.add_argument(
        "--target-protein", "-t",
        required=True,
        help="Target protein name (e.g. KRAS, TP53).",
    )

    # Prompt mode
    parser.add_argument(
        "--prompt-type",
        choices=["interactome", "binder_design"],
        default="interactome",
        help="Prompt mode: 'interactome' for pathway/interaction mining, "
             "'binder_design' for scaffold/binder discovery. (default: interactome)",
    )

    # Generator configuration
    parser.add_argument(
        "--generator",
        choices=["openai", "vllm", "argo"],
        default="openai",
        help="LLM backend to use (default: openai).",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="Model name for the selected generator (default: gpt-4o).",
    )
    parser.add_argument(
        "--vllm-server",
        default="localhost",
        help="vLLM server hostname (only used with --generator vllm).",
    )
    parser.add_argument(
        "--vllm-port",
        type=int,
        default=8000,
        help="vLLM server port (only used with --generator vllm).",
    )
    parser.add_argument(
        "--argo-base-url",
        default="http://localhost:56267",
        help="Argo proxy base URL (only used with --generator argo).",
    )

    # Retrieval configuration
    parser.add_argument(
        "--rag-config",
        default=None,
        help="Path to a JSON/YAML RAG config file with retriever settings.",
    )
    parser.add_argument(
        "--retrieval-top-k",
        type=int,
        default=200,
        help="Number of documents to retrieve (default: 200).",
    )

    # Output
    parser.add_argument(
        "--output-dir",
        default="./artifacts",
        help="Directory for artifact storage (default: ./artifacts).",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Write results to this JSON file (in addition to artifact store).",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    # Build generator
    generator_fn = build_generator(args)

    # Optional retriever
    retriever = _try_build_retriever(args.rag_config)

    # Execute RAG pipeline
    logger.info(
        "Running HiPerRAG: target=%s, mode=%s, generator=%s",
        args.target_protein,
        args.prompt_type,
        args.generator,
    )
    result = run_rag(
        query=args.query,
        target_protein=args.target_protein,
        prompt_type=args.prompt_type,
        generator_fn=generator_fn,
        retriever=retriever,
        retrieval_top_k=args.retrieval_top_k,
    )

    # Store in Artifact DAG
    dag = ArtifactDAG(storage_path=args.output_dir)
    provenance = dag.provenance
    run_id = provenance.start_run(
        skill_name="hiperrag",
        skill_version="0.1.0",
        parameters={
            "query": args.query,
            "target_protein": args.target_protein,
            "prompt_type": args.prompt_type,
            "generator": args.generator,
            "model": args.model,
        },
    )

    try:
        artifact_id = store_result_as_artifact(result, dag, run_id)
        provenance.finish_run(
            run_id=run_id,
            output_artifact_ids=[artifact_id],
            status="success",
        )
        logger.info("Stored artifact %s (run %s)", artifact_id, run_id)
    except Exception as exc:
        provenance.finish_run(run_id=run_id, status="failed", error=str(exc))
        raise

    # Optionally write JSON output
    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, default=str))
        logger.info("Wrote results to %s", out_path)

    # Print summary to stdout
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
