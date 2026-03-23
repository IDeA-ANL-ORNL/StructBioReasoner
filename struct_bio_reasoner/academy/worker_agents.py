"""Worker Agent classes for the Academy execution fabric (Layer 4).

Each worker wraps a single computational skill (BindCraft, folding,
molecular dynamics, etc.) as an ``Academy.Agent`` with ``@action``
methods.  Workers are launched by the Manager and invoked via Handle RPC.

The WORKER_REGISTRY maps skill names to their Agent class so that
``AcademyDispatch`` can launch the right worker on demand.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from academy.agent import Agent, action

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BindCraft — computational peptide binder design
# ---------------------------------------------------------------------------

class BindCraftWorker(Agent):
    """Worker agent for BindCraft binder design.

    Wraps the existing ``BindCraftAgent`` wrapper so it can be launched
    via ``Manager.launch()`` and called through Handle RPC.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self._agent = None
        logger.info("BindCraftWorker initialised (config keys: %s)", list(config.keys()))

    async def _ensure_agent(self) -> None:
        if self._agent is not None:
            return
        from struct_bio_reasoner.agents.computational_design.bindcraft_agent import (
            BindCraftAgent,
        )

        self._agent = BindCraftAgent(
            agent_id=self.config.get("agent_id", "bindcraft-worker"),
            config=self.config,
            model_manager=self.config.get("model_manager"),
            parsl_config=self.config.get("parsl_config", {}),
        )
        await self._agent.initialize(self.config.get("parsl"))

    @action
    async def run_design(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a BindCraft binder-design workflow."""
        await self._ensure_agent()
        result = await self._agent.analyze_hypothesis(None, params)
        return result if isinstance(result, dict) else {"result": str(result)}

    @action
    async def get_capabilities(self) -> List[str]:
        """Return the list of capabilities this worker provides."""
        return ["binder_design", "antibody_design", "peptide_design"]


# ---------------------------------------------------------------------------
# Structure prediction (Chai / AlphaFold)
# ---------------------------------------------------------------------------

class FoldingWorker(Agent):
    """Worker agent for protein structure prediction."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self._agent = None
        logger.info("FoldingWorker initialised")

    async def _ensure_agent(self) -> None:
        if self._agent is not None:
            return
        from struct_bio_reasoner.agents.structure_prediction.chai_agent import (
            ChaiAgent,
        )

        self._agent = ChaiAgent()
        await self._agent.initialize(self.config)

    @action
    async def fold_sequences(
        self,
        sequences: List[str],
        names: List[str],
        constraints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fold protein sequences and return predicted structures."""
        await self._ensure_agent()
        params = {
            "sequences": sequences,
            "names": names,
            "constraints": constraints or {},
        }
        result = await self._agent.analyze_hypothesis(None, params)
        return result if isinstance(result, dict) else {"result": str(result)}


# ---------------------------------------------------------------------------
# Molecular dynamics (OpenMM + MDAgent)
# ---------------------------------------------------------------------------

class MDWorker(Agent):
    """Worker agent for molecular dynamics simulations."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self._agent = None
        logger.info("MDWorker initialised")

    async def _ensure_agent(self) -> None:
        if self._agent is not None:
            return
        from struct_bio_reasoner.agents.molecular_dynamics.mdagent_adapter import (
            MDAgentAdapter,
        )

        self._agent = MDAgentAdapter(self.config)
        await self._agent.initialize(self.config.get("parsl"))

    @action
    async def run_simulation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run an MD simulation with the given parameters."""
        await self._ensure_agent()
        result = await self._agent.analyze_hypothesis(None, params)
        return result if isinstance(result, dict) else {"result": str(result)}


# ---------------------------------------------------------------------------
# HiPerRAG literature mining
# ---------------------------------------------------------------------------

class RAGWorker(Agent):
    """Worker agent for RAG-based literature mining."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self._agent = None
        logger.info("RAGWorker initialised")

    async def _ensure_agent(self) -> None:
        if self._agent is not None:
            return
        from struct_bio_reasoner.agents.hiper_rag.rag_agent import RAGWrapper

        self._agent = RAGWrapper(self.config)
        await self._agent.initialize()

    @action
    async def generate_rag_hypothesis(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a literature-guided hypothesis."""
        await self._ensure_agent()
        result = await self._agent.generate_rag_hypothesis(data)
        return result if isinstance(result, dict) else {"result": str(result)}


# ---------------------------------------------------------------------------
# Evolutionary conservation (MUSCLE)
# ---------------------------------------------------------------------------

class ConservationWorker(Agent):
    """Worker agent for evolutionary conservation analysis."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        logger.info("ConservationWorker initialised")

    @action
    async def run_conservation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run MUSCLE-based conservation analysis."""
        sequence = params.get("sequence", "")
        # Placeholder — the actual conservation skill will be wired in Wave 2
        return {
            "sequence_length": len(sequence),
            "conservation_scores": [],
            "status": "placeholder",
        }


# ---------------------------------------------------------------------------
# Protein language model (ESM / GenSLM)
# ---------------------------------------------------------------------------

class ProteinLMWorker(Agent):
    """Worker agent for protein language model inference."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        logger.info("ProteinLMWorker initialised")

    @action
    async def embed_sequence(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Embed a protein sequence using ESM or GenSLM."""
        sequence = params.get("sequence", "")
        return {
            "sequence_length": len(sequence),
            "embedding_dim": 1280,
            "status": "placeholder",
        }

    @action
    async def score_mutations(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Score mutations with a protein language model."""
        return {"scores": [], "status": "placeholder"}


# ---------------------------------------------------------------------------
# Trajectory analysis
# ---------------------------------------------------------------------------

class TrajectoryAnalysisWorker(Agent):
    """Worker agent for MD trajectory analysis and clustering."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        logger.info("TrajectoryAnalysisWorker initialised")

    @action
    async def cluster_trajectories(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Cluster MD trajectories and return representative structures."""
        return {
            "n_clusters": params.get("n_clusters", 5),
            "representatives": [],
            "status": "placeholder",
        }

    @action
    async def analyze_hotspots(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Identify binding hotspots from simulation data."""
        return {"hotspots": [], "status": "placeholder"}


# ---------------------------------------------------------------------------
# Registry: skill name → Agent class
# ---------------------------------------------------------------------------

WORKER_REGISTRY: Dict[str, type[Agent]] = {
    "bindcraft": BindCraftWorker,
    "binder_design": BindCraftWorker,
    "folding": FoldingWorker,
    "structure_prediction": FoldingWorker,
    "md": MDWorker,
    "simulation": MDWorker,
    "molecular_dynamics": MDWorker,
    "rag": RAGWorker,
    "literature": RAGWorker,
    "hiperrag": RAGWorker,
    "conservation": ConservationWorker,
    "protein_lm": ProteinLMWorker,
    "trajectory_analysis": TrajectoryAnalysisWorker,
    "clustering": TrajectoryAnalysisWorker,
}
