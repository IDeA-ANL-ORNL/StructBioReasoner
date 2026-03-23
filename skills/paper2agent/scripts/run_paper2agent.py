#!/usr/bin/env python3
"""
Paper2Agent — Literature-to-Tool Conversion Skill

Orchestrates the Paper2Agent pipeline:
  1. Analyse a scientific paper (PDF, DOI, or raw text)
  2. Extract computational methodologies and reward criteria
  3. Generate executable MCP tool specifications
  4. Record results as artifacts in the DAG (Layer 3)

Ported from struct_bio_reasoner/paper2agent/.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Ensure the shared layer is importable regardless of cwd
# ---------------------------------------------------------------------------
_SKILL_DIR = Path(__file__).resolve().parent.parent          # skills/paper2agent
_SKILLS_ROOT = _SKILL_DIR.parent                              # skills/
_PROJECT_ROOT = _SKILLS_ROOT.parent                           # repo root
for _p in (_SKILLS_ROOT, _PROJECT_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from _shared.artifact import (                                # noqa: E402
    Artifact,
    ArtifactMetadata,
    ArtifactStatus,
    ArtifactType,
    create_artifact,
)
from _shared.artifact_store import ArtifactStore              # noqa: E402
from _shared.provenance import ProvenanceTracker              # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("paper2agent")

_UTC = timezone.utc
_SKILL_NAME = "paper2agent"
_SKILL_VERSION = "0.1.0"

# ── Domain dataclasses ─────────────────────────────────────────────────────


@dataclass
class PaperSource:
    """Input paper to process."""

    title: str = ""
    authors: List[str] = field(default_factory=list)
    doi: str = ""
    abstract: str = ""
    content: str = ""
    github_repo: Optional[str] = None
    publication_year: Optional[int] = None
    journal: Optional[str] = None
    keywords: List[str] = field(default_factory=list)


@dataclass
class MethodologyExtraction:
    """A computational methodology extracted from a paper."""

    name: str
    description: str
    input_parameters: List[Dict[str, Any]]
    output_format: Dict[str, Any]
    algorithm_steps: List[str]
    dependencies: List[str]
    validation_criteria: List[str]
    paper_source: str
    github_repo: Optional[str] = None
    implementation_complexity: str = "medium"
    code_availability: bool = False


@dataclass
class RewardCriterion:
    """A verifiable reward criterion derived from the paper."""

    name: str
    description: str
    metric_type: str   # accuracy, stability, conservation, efficiency, novelty
    weight: float
    validation_method: str
    expected_range: Tuple[float, float]
    paper_source: str
    experimental_validation: bool = False
    computational_validation: bool = True


@dataclass
class MCPToolSpec:
    """MCP tool specification generated from a methodology."""

    tool_name: str
    tool_description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    dependencies: List[str]
    paper_source: str
    confidence_score: float


# ── Paper Analysis ─────────────────────────────────────────────────────────


_DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "md": [
        "molecular dynamics", "md simulation", "thermostability",
        "protein folding", "free energy", "binding affinity",
        "rmsd", "rmsf", "trajectory",
    ],
    "structural": [
        "crystal structure", "cryo-em", "alphafold",
        "protein structure", "structure prediction", "fold",
        "secondary structure", "tertiary structure",
    ],
    "bioinformatics": [
        "sequence analysis", "phylogenetic", "conservation",
        "alignment", "homology", "machine learning",
        "deep learning", "genomics", "proteomics",
    ],
}


def classify_domain(text: str) -> str:
    """Classify paper content into a scientific domain."""
    text_lower = text.lower()
    scores = {
        domain: sum(1 for kw in kws if kw in text_lower)
        for domain, kws in _DOMAIN_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    return best if scores[best] > 0 else "general"


def extract_methodologies(content: str, paper_meta: Dict[str, Any]) -> List[MethodologyExtraction]:
    """Extract computational methodologies from paper content."""
    methodologies: List[MethodologyExtraction] = []
    content_lower = content.lower()
    doi = paper_meta.get("doi", "")
    repo = paper_meta.get("github_repo")

    if "structure prediction" in content_lower:
        methodologies.append(MethodologyExtraction(
            name="structure_prediction",
            description="Predict protein 3D structure from sequence",
            input_parameters=[
                {"name": "sequence", "type": "str", "description": "Protein sequence"},
                {"name": "template_pdb", "type": "str", "description": "Template PDB ID", "optional": True},
            ],
            output_format={"structure": "PDB format string", "confidence": "float", "quality_metrics": "dict"},
            algorithm_steps=["Parse input sequence", "Search for structural templates",
                             "Perform homology modelling", "Refine structure", "Calculate quality metrics"],
            dependencies=["biopython", "numpy", "scipy"],
            validation_criteria=["RMSD < 3.0 Å for known structures"],
            paper_source=doi, github_repo=repo, implementation_complexity="high",
        ))

    if "conservation" in content_lower:
        methodologies.append(MethodologyExtraction(
            name="conservation_analysis",
            description="Analyse evolutionary conservation of protein sequences",
            input_parameters=[
                {"name": "sequences", "type": "list", "description": "List of homologous sequences"},
            ],
            output_format={"conservation_scores": "list", "conserved_positions": "list"},
            algorithm_steps=["Align sequences", "Calculate position-specific conservation",
                             "Identify highly conserved regions"],
            dependencies=["biopython", "numpy"],
            validation_criteria=["Conservation scores correlate with known functional sites"],
            paper_source=doi, implementation_complexity="medium",
        ))

    if "stability prediction" in content_lower or "thermostability" in content_lower:
        methodologies.append(MethodologyExtraction(
            name="stability_prediction",
            description="Predict the effect of mutations on protein stability",
            input_parameters=[
                {"name": "structure", "type": "str", "description": "Protein structure (PDB format)"},
                {"name": "mutations", "type": "list", "description": "List of mutations to evaluate"},
            ],
            output_format={"stability_changes": "dict", "confidence_scores": "dict"},
            algorithm_steps=["Parse structure and mutations", "Calculate energy changes",
                             "Apply machine-learning models", "Rank mutations by predicted stability"],
            dependencies=["biopython", "numpy", "scikit-learn"],
            validation_criteria=["Correlation with experimental ΔΔG values > 0.7"],
            paper_source=doi, implementation_complexity="high",
        ))

    if "binding" in content_lower and ("design" in content_lower or "interaction" in content_lower):
        methodologies.append(MethodologyExtraction(
            name="binding_analysis",
            description="Analyse protein-ligand or protein-protein binding interactions",
            input_parameters=[
                {"name": "complex_structure", "type": "str", "description": "Complex PDB structure"},
                {"name": "chains", "type": "list", "description": "Interacting chain IDs"},
            ],
            output_format={"binding_energy": "float", "interface_residues": "list"},
            algorithm_steps=["Identify interface residues", "Calculate binding energy",
                             "Assess interaction quality"],
            dependencies=["biopython", "numpy"],
            validation_criteria=["Binding energy within 2 kcal/mol of experimental value"],
            paper_source=doi, implementation_complexity="medium",
        ))

    if "molecular dynamics" in content_lower or "md simulation" in content_lower:
        methodologies.append(MethodologyExtraction(
            name="md_simulation_protocol",
            description="Molecular dynamics simulation protocol from paper",
            input_parameters=[
                {"name": "structure", "type": "str", "description": "Starting structure (PDB)"},
                {"name": "duration_ns", "type": "float", "description": "Simulation duration in ns"},
            ],
            output_format={"trajectory": "path", "analysis": "dict"},
            algorithm_steps=["Prepare system (solvation, ions)", "Minimisation",
                             "Equilibration (NVT + NPT)", "Production MD", "Trajectory analysis"],
            dependencies=["openmm", "mdtraj", "numpy"],
            validation_criteria=["Stable RMSD plateau within first 20 ns"],
            paper_source=doi, implementation_complexity="high",
        ))

    logger.info("Extracted %d methodologies from paper", len(methodologies))
    return methodologies


# ── Reward Criteria Extraction ─────────────────────────────────────────────

_REWARD_PATTERNS: Dict[str, Dict[str, Any]] = {
    "thermostability_improvement": {
        "triggers": ["thermostability", "thermal stability", "melting temperature"],
        "metric_type": "stability", "weight": 0.30,
        "validation_method": "md_simulation",
        "expected_range": (0.0, 10.0),
        "experimental": True,
    },
    "structural_stability": {
        "triggers": ["rmsd", "structural stability", "conformational"],
        "metric_type": "accuracy", "weight": 0.25,
        "validation_method": "trajectory_analysis",
        "expected_range": (0.0, 5.0),
        "experimental": False,
    },
    "binding_affinity_prediction": {
        "triggers": ["binding", "affinity", "interaction", "complex"],
        "metric_type": "accuracy", "weight": 0.20,
        "validation_method": "binding_assay_correlation",
        "expected_range": (-15.0, 0.0),
        "experimental": True,
    },
    "structure_prediction_accuracy": {
        "triggers": ["structure prediction", "alphafold", "fold"],
        "metric_type": "accuracy", "weight": 0.35,
        "validation_method": "pdb_comparison",
        "expected_range": (0.0, 5.0),
        "experimental": True,
    },
    "sequence_analysis_accuracy": {
        "triggers": ["sequence", "alignment", "homology"],
        "metric_type": "accuracy", "weight": 0.30,
        "validation_method": "benchmark_comparison",
        "expected_range": (0.0, 1.0),
        "experimental": False,
    },
    "evolutionary_conservation": {
        "triggers": ["conservation", "evolution", "phylogenetic"],
        "metric_type": "conservation", "weight": 0.25,
        "validation_method": "conservation_benchmark",
        "expected_range": (0.0, 1.0),
        "experimental": False,
    },
}


def extract_reward_criteria(content: str, doi: str) -> List[RewardCriterion]:
    """Extract verifiable reward criteria from paper content."""
    criteria: List[RewardCriterion] = []
    content_lower = content.lower()

    for name, cfg in _REWARD_PATTERNS.items():
        if any(trigger in content_lower for trigger in cfg["triggers"]):
            criteria.append(RewardCriterion(
                name=name,
                description=f"Reward criterion: {name.replace('_', ' ')}",
                metric_type=cfg["metric_type"],
                weight=cfg["weight"],
                validation_method=cfg["validation_method"],
                expected_range=cfg["expected_range"],
                paper_source=doi,
                experimental_validation=cfg.get("experimental", False),
                computational_validation=True,
            ))

    logger.info("Extracted %d reward criteria from paper", len(criteria))
    return criteria


# ── MCP Tool Generation ───────────────────────────────────────────────────


def _build_input_schema(params: List[Dict[str, Any]]) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for p in params:
        properties[p["name"]] = {"type": p.get("type", "string"), "description": p.get("description", "")}
        if not p.get("optional", False):
            required.append(p["name"])
    return {"type": "object", "properties": properties, "required": required}


def _build_output_schema(output_format: Dict[str, Any]) -> Dict[str, Any]:
    properties = {k: {"type": "object" if isinstance(v, dict) else "string"} for k, v in output_format.items()}
    return {"type": "object", "properties": properties}


def _confidence_score(method: MethodologyExtraction) -> float:
    score = 0.5
    if method.code_availability:
        score += 0.3
    if len(method.algorithm_steps) > 3:
        score += 0.1
    if len(method.validation_criteria) > 0:
        score += 0.1
    return min(1.0, score)


def generate_tool_specs(methodologies: List[MethodologyExtraction]) -> List[MCPToolSpec]:
    """Generate MCP tool specs from extracted methodologies."""
    specs: List[MCPToolSpec] = []
    for m in methodologies:
        specs.append(MCPToolSpec(
            tool_name=f"paper2agent_{m.name}",
            tool_description=m.description,
            input_schema=_build_input_schema(m.input_parameters),
            output_schema=_build_output_schema(m.output_format),
            dependencies=m.dependencies,
            paper_source=m.paper_source,
            confidence_score=_confidence_score(m),
        ))
    logger.info("Generated %d MCP tool specifications", len(specs))
    return specs


# ── Orchestrator ───────────────────────────────────────────────────────────


def _load_paper(source: str) -> PaperSource:
    """Load paper from a file path or treat *source* as raw text."""
    path = Path(source)
    if path.is_file():
        text = path.read_text()
        return PaperSource(title=path.stem, content=text)
    # Treat as raw text / abstract
    return PaperSource(title="untitled", content=source)


async def run_pipeline(
    paper_source: str,
    output_dir: str,
    artifact_root: Optional[str] = None,
    target_method: Optional[str] = None,
    output_format: str = "config",
) -> Dict[str, Any]:
    """
    End-to-end Paper2Agent pipeline.

    Returns a summary dict with extracted methodologies, reward criteria,
    generated tool specs, and artifact IDs.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Artifact DAG integration
    store: Optional[ArtifactStore] = None
    tracker: Optional[ProvenanceTracker] = None
    if artifact_root:
        art_root = Path(artifact_root)
        store = ArtifactStore(art_root)
        tracker = ProvenanceTracker(art_root)

    # Start provenance run
    prov_record = None
    if tracker:
        prov_record = tracker.start_run(
            skill_name=_SKILL_NAME,
            skill_version=_SKILL_VERSION,
            parameters={"paper_source": paper_source, "target_method": target_method,
                         "output_format": output_format},
        )

    paper = _load_paper(paper_source)
    paper_meta = {
        "title": paper.title, "doi": paper.doi,
        "github_repo": paper.github_repo, "authors": paper.authors,
        "year": paper.publication_year,
    }

    # 1. Extract methodologies
    methodologies = extract_methodologies(paper.content, paper_meta)
    if target_method:
        methodologies = [m for m in methodologies if m.name == target_method]

    # 2. Extract reward criteria
    criteria = extract_reward_criteria(paper.content, paper.doi)

    # 3. Generate MCP tool specs
    tool_specs = generate_tool_specs(methodologies)

    # 4. Record artifacts
    output_artifact_ids: List[str] = []
    if store:
        # Paper source artifact (root of lineage)
        paper_artifact = create_artifact(
            metadata=ArtifactMetadata(
                artifact_type=ArtifactType.LITERATURE,
                skill_name=_SKILL_NAME,
                skill_version=_SKILL_VERSION,
                tags=frozenset(["paper", classify_domain(paper.content)]),
            ),
            data={"title": paper.title, "doi": paper.doi, "authors": paper.authors},
            run_id=prov_record.run_id if prov_record else None,
        )
        store.put(paper_artifact)
        output_artifact_ids.append(paper_artifact.artifact_id)

        # Methodology artifacts
        for m in methodologies:
            art = create_artifact(
                parent_ids=(paper_artifact.artifact_id,),
                metadata=ArtifactMetadata(
                    artifact_type=ArtifactType.WORKFLOW_CONFIG,
                    skill_name=_SKILL_NAME,
                    skill_version=_SKILL_VERSION,
                    tags=frozenset(["methodology", m.name]),
                ),
                data={
                    "name": m.name, "description": m.description,
                    "algorithm_steps": m.algorithm_steps,
                    "dependencies": m.dependencies,
                    "complexity": m.implementation_complexity,
                },
                run_id=prov_record.run_id if prov_record else None,
            )
            store.put(art)
            output_artifact_ids.append(art.artifact_id)

        # Tool spec artifacts
        for spec in tool_specs:
            art = create_artifact(
                parent_ids=(paper_artifact.artifact_id,),
                metadata=ArtifactMetadata(
                    artifact_type=ArtifactType.WORKFLOW_CONFIG,
                    skill_name=_SKILL_NAME,
                    skill_version=_SKILL_VERSION,
                    tags=frozenset(["mcp_tool", spec.tool_name]),
                ),
                data={
                    "tool_name": spec.tool_name,
                    "tool_description": spec.tool_description,
                    "input_schema": spec.input_schema,
                    "output_schema": spec.output_schema,
                    "dependencies": spec.dependencies,
                    "confidence_score": spec.confidence_score,
                },
                run_id=prov_record.run_id if prov_record else None,
            )
            store.put(art)
            output_artifact_ids.append(art.artifact_id)

    # Finish provenance run
    if tracker and prov_record:
        tracker.finish_run(prov_record.run_id, output_artifact_ids, status="success")

    # 5. Write outputs
    summary: Dict[str, Any] = {
        "paper": {"title": paper.title, "doi": paper.doi, "domain": classify_domain(paper.content)},
        "methodologies": [
            {"name": m.name, "description": m.description,
             "steps": m.algorithm_steps, "complexity": m.implementation_complexity}
            for m in methodologies
        ],
        "reward_criteria": [
            {"name": c.name, "metric_type": c.metric_type, "weight": c.weight,
             "validation_method": c.validation_method}
            for c in criteria
        ],
        "tool_specs": [
            {"tool_name": s.tool_name, "description": s.tool_description,
             "confidence": s.confidence_score, "dependencies": s.dependencies}
            for s in tool_specs
        ],
        "artifact_ids": output_artifact_ids,
    }

    summary_path = out_path / "paper2agent_results.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    logger.info("Results written to %s", summary_path)

    if output_format == "script":
        _write_generated_scripts(out_path, tool_specs)

    return summary


def _write_generated_scripts(out_path: Path, tool_specs: List[MCPToolSpec]) -> None:
    """Write skeleton Python scripts for each generated tool."""
    scripts_out = out_path / "generated"
    scripts_out.mkdir(parents=True, exist_ok=True)

    for spec in tool_specs:
        script = (
            f'#!/usr/bin/env python3\n'
            f'"""Auto-generated tool: {spec.tool_name}\n\n'
            f'{spec.tool_description}\n'
            f'Paper: {spec.paper_source}\n'
            f'Confidence: {spec.confidence_score:.2f}\n"""\n\n'
            f'import argparse\n\n\n'
            f'def main():\n'
            f'    parser = argparse.ArgumentParser(description="{spec.tool_description}")\n'
        )
        for prop_name, prop_def in spec.input_schema.get("properties", {}).items():
            script += (
                f'    parser.add_argument("--{prop_name}", '
                f'help="{prop_def.get("description", "")}")\n'
            )
        script += (
            f'    args = parser.parse_args()\n'
            f'    print("Running {spec.tool_name} ...")\n'
            f'    # TODO: implement {spec.tool_name}\n\n\n'
            f'if __name__ == "__main__":\n'
            f'    main()\n'
        )
        (scripts_out / f"{spec.tool_name}.py").write_text(script)

    logger.info("Wrote %d generated scripts to %s", len(tool_specs), scripts_out)


# ── CLI ────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_paper2agent",
        description="Paper2Agent: Convert scientific papers into executable computational workflows",
    )
    parser.add_argument(
        "paper_source",
        help="Path to paper (PDF/text) or raw text string",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="output/paper2agent",
        help="Directory for output files (default: output/paper2agent)",
    )
    parser.add_argument(
        "--artifact-root",
        default=None,
        help="Root directory for artifact DAG storage (enables provenance tracking)",
    )
    parser.add_argument(
        "--target-method",
        default=None,
        help="Extract only a specific methodology (e.g. structure_prediction)",
    )
    parser.add_argument(
        "--output-format",
        choices=["config", "script"],
        default="config",
        help="Output format: 'config' (JSON specs) or 'script' (runnable Python scripts)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = asyncio.run(run_pipeline(
        paper_source=args.paper_source,
        output_dir=args.output_dir,
        artifact_root=args.artifact_root,
        target_method=args.target_method,
        output_format=args.output_format,
    ))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
