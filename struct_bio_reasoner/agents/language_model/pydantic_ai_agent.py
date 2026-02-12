"""
Pydantic-AI based reasoner agent for StructBioReasoner.

Drop-in replacement for JnanaAgent. Uses pydantic-ai with PromptedOutput
mode for structured JSON generation against ALCF's vLLM inference endpoints
(or any OpenAI-compatible endpoint).

To switch over, update AgentRegistry in director_agent.py:
    reasoner: str = 'struct_bio_reasoner.agents.language_model.pydantic_ai_agent:PydanticAIReasonerAgent'
"""

import logging
from typing import Any, Optional

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from pydantic_ai import Agent as pAgent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.output import PromptedOutput
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from academy.agent import Agent, action
from struct_bio_reasoner.prompts.prompts_v2 import config_master, get_prompt_manager
from struct_bio_reasoner.prompts.recommender_prompts import RecommenderPromptManager
from struct_bio_reasoner.utils.inference_auth_token import get_access_token

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section 1: Pydantic Output Models
# ---------------------------------------------------------------------------

class Recommendation(BaseModel):
    """Schema for the reasoner's next-task recommendation."""
    next_task: str = Field(description="Name of the next task to run")
    change_parameters: bool = Field(description="Whether to change parameters from the previous run")
    rationale: str = Field(description="Explanation of why this task was recommended")


class QCKwargs(BaseModel):
    max_repeat: int = Field(default=3)
    max_appearance_ratio: float = Field(default=0.5)
    max_charge: int = Field(default=5)
    max_charge_ratio: float = Field(default=0.5)
    max_hydrophobic_ratio: float = Field(default=0.6)
    min_diversity: int = Field(default=3)


class Constraint(BaseModel):
    residues_bind: list[str] = Field(default_factory=list)


class ComputationalDesignConfig(BaseModel):
    binder_sequence: str = Field(description="Full amino acid sequence for the binder")
    num_rounds: int = Field(default=2)
    batch_size: int = Field(default=50)
    max_retries: int = Field(default=3)
    sampling_temp: float = Field(default=0.2)
    qc_kwargs: QCKwargs = Field(default_factory=QCKwargs)
    constraint: Constraint = Field(default_factory=Constraint)


class ComputationalDesignPlan(BaseModel):
    new_config: ComputationalDesignConfig
    rationale: str


class MolecularDynamicsConfig(BaseModel):
    simulation_paths: list[str]
    root_output_path: str
    steps: int


class MolecularDynamicsPlan(BaseModel):
    new_config: MolecularDynamicsConfig
    rationale: str


class StructurePredictionConfig(BaseModel):
    sequences: list[list[str]]
    names: list[str]


class StructurePredictionPlan(BaseModel):
    new_config: StructurePredictionConfig
    rationale: str


class AnalysisConfig(BaseModel):
    data_type: str = Field(description="'static', 'dynamic', or 'both'")
    analysis_type: str = Field(description="'basic', 'advanced', or 'both'")
    distance_cutoff: float = Field(default=8.0)


class AnalysisPlan(BaseModel):
    new_config: AnalysisConfig
    rationale: str


class FreeEnergyConfig(BaseModel):
    simulation_paths: list[str]


class FreeEnergyPlan(BaseModel):
    new_config: FreeEnergyConfig
    rationale: str


class RAGConfig(BaseModel):
    prompt: str


class RAGPlan(BaseModel):
    new_config: RAGConfig
    rationale: str


PLAN_MODELS: dict[str, type[BaseModel]] = {
    "computational_design": ComputationalDesignPlan,
    "molecular_dynamics": MolecularDynamicsPlan,
    "structure_prediction": StructurePredictionPlan,
    "analysis": AnalysisPlan,
    "free_energy": FreeEnergyPlan,
    "rag": RAGPlan,
}

# ---------------------------------------------------------------------------
# Section 2: ALCF Provider Setup
# ---------------------------------------------------------------------------

ALCF_ENDPOINTS = {
    "sophia": "https://inference-api.alcf.anl.gov/resource_server/sophia/vllm/v1",
    "metis": "https://inference-api.alcf.anl.gov/resource_server/metis/api/v1",
}


def _resolve_alcf_endpoint(model: str) -> tuple[str, str]:
    """Return (base_url, cleaned_model_name) based on model string.

    Models prefixed with 'metis/' route to the Metis endpoint; everything
    else goes to Sophia.
    """
    if model.startswith("metis/"):
        return ALCF_ENDPOINTS["metis"], model.removeprefix("metis/")
    return ALCF_ENDPOINTS["sophia"], model


class ALCFTokenAuth(httpx.Auth):
    """httpx auth handler that refreshes the Globus access token per request."""

    def auth_flow(self, request: httpx.Request):
        token = get_access_token()
        request.headers["Authorization"] = f"Bearer {token}"
        yield request


def create_alcf_model(model_name: str = "openai/gpt-oss-120b") -> OpenAIModel:
    """Build a pydantic-ai OpenAIModel pointing at an ALCF vLLM endpoint.

    Uses ALCFTokenAuth so the Globus bearer token is refreshed on every
    HTTP request — no stale-token issues even in long-running sessions.
    """
    base_url, cleaned_model = _resolve_alcf_endpoint(model_name)

    http_client = httpx.AsyncClient(
        auth=ALCFTokenAuth(),
        timeout=httpx.Timeout(120.0, connect=30.0),
    )

    openai_client = AsyncOpenAI(
        api_key="placeholder",  # overridden by ALCFTokenAuth per-request
        base_url=base_url,
        http_client=http_client,
    )

    provider = OpenAIProvider(openai_client=openai_client)
    return OpenAIModel(model_name=cleaned_model, provider=provider)


# ---------------------------------------------------------------------------
# Section 3: pydantic-ai Agent Factories
# ---------------------------------------------------------------------------

def _build_recommend_agent(model: OpenAIModel) -> pAgent:
    """Agent used for generate_recommendation() — fixed Recommendation schema."""
    return pAgent(
        model=model,
        output_type=PromptedOutput(Recommendation),
        instructions="You output only valid JSON according to the specified schema.",
    )


def _build_plan_agent(model: OpenAIModel) -> pAgent:
    """Agent used for plan_run() — output_type is overridden per call."""
    return pAgent(
        model=model,
        output_type=str,  # placeholder; overridden at runtime
        instructions="You output only valid JSON according to the specified schema.",
    )


# ---------------------------------------------------------------------------
# Section 4: Academy Agent Wrapper
# ---------------------------------------------------------------------------

class PydanticAIReasonerAgent(Agent):
    """Academy-compatible reasoner agent backed by pydantic-ai.

    API-compatible with JnanaAgent — same __init__ signature, same @action
    methods, same return shapes.
    """

    def __init__(
        self,
        research_goal: str,
        enabled_agents: list[str],
        llm_provider: str,
        target_protein: str,
    ):
        self.research_goal = research_goal
        self.enabled_agents = enabled_agents
        self.llm_provider = llm_provider
        self.target_protein = target_protein

        # Build the pydantic-ai model for the configured provider
        self._model = create_alcf_model()  # default ALCF model

        # Two internal pydantic-ai agents
        self._recommend_agent = _build_recommend_agent(self._model)
        self._plan_agent = _build_plan_agent(self._model)

        # Reuse existing prompt managers
        self.recommender_manager = RecommenderPromptManager(
            self.research_goal,
            self.enabled_agents,
        )

        # Keep legacy schemas around for reference / logging
        self.recommendation_schema = {
            "next_task": "string",
            "change_parameters": "boolean",
            "rationale": "string",
        }
        self.plan_schema = {
            "new_config": "placeholder",
            "rationale": "string",
        }

    # -- helpers -------------------------------------------------------------

    def fill_prompt_template(
        self,
        system_str: str = "system",
        agent_type: str = "recommender",
        role: str = "Recommend next runs to make",
    ) -> Optional[str]:
        return None

    # -- actions -------------------------------------------------------------

    @action
    async def generate_recommendation(
        self,
        results: Any,
        previous_run: str,
        history: dict,
        prompt_type: str = "",
    ) -> dict:
        """Generate a recommended next task.

        Mirrors JnanaAgent.generate_recommendation exactly:
        1. Build prompt via existing prompt managers
        2. Call the recommendation pydantic-ai agent
        3. Return {'previous_run': ..., 'recommendation': dict}
        """
        agent_prompt_manager = get_prompt_manager(
            agent_type=previous_run,
            research_goal=self.research_goal,
            input_json=results,
            target_prot=self.target_protein,
            prompt_type=prompt_type,
            history=history,
            num_history=3,
        )

        agent_prompt_manager.conclusion_prompt()
        logger.debug(agent_prompt_manager.prompt_c)

        self.recommender_manager.recommend_prompt(
            previous_run,
            agent_prompt_manager.prompt_c,
            history,
        )

        logger.debug(self.recommender_manager.prompt_r)

        result = await self._recommend_agent.run(
            user_prompt=self.recommender_manager.prompt_r,
            model_settings=ModelSettings(temperature=0.3, max_tokens=32768),
        )

        recommendation = result.output
        logger.debug(recommendation)

        return {
            "previous_run": previous_run,
            "recommendation": recommendation.model_dump(),
        }

    @action
    async def plan_run(
        self,
        recommendation: dict,
        history: dict,
        prompt_type: str = "",
    ) -> dict:
        """Generate a config for the recommended next task.

        Mirrors JnanaAgent.plan_run exactly:
        1. Look up the correct Pydantic plan model for next_task
        2. Build prompt via existing prompt managers
        3. Call the plan pydantic-ai agent with runtime output_type
        4. Return result as dict
        """
        next_task = recommendation["recommendation"]["next_task"]
        logger.debug(f"{next_task}")

        agent_prompt_manager = get_prompt_manager(
            agent_type=next_task,
            research_goal=self.research_goal,
            input_json=recommendation,
            target_prot=self.target_protein,
            prompt_type=prompt_type,
            history=history,
            num_history=3,
        )

        agent_prompt_manager.running_prompt()

        plan_model = PLAN_MODELS.get(next_task)
        if plan_model is None:
            logger.warning(
                f"No Pydantic plan model for task '{next_task}', falling back to str output"
            )
            result = await self._plan_agent.run(
                user_prompt=agent_prompt_manager.prompt_r,
                model_settings=ModelSettings(temperature=0.3, max_tokens=32768),
            )
            return {"raw": result.output}

        result = await self._plan_agent.run(
            user_prompt=agent_prompt_manager.prompt_r,
            output_type=PromptedOutput(plan_model),
            model_settings=ModelSettings(temperature=0.3, max_tokens=32768),
        )

        return result.output.model_dump()

    @action
    async def query(self, prompt: str) -> str:
        """Send a free-form prompt to the LLM and return the response."""
        result = await self._plan_agent.run(
            user_prompt=prompt,
            output_type=str,
            model_settings=ModelSettings(temperature=0.7, max_tokens=32768),
        )
        return result.output

    @action
    async def evaluate_history(self, history: str) -> tuple[str]:
        """Examine a director's history and return a decision signal."""
        prompt = (
            f"Evaluate the following workflow history and decide whether to "
            f"continue, stop, or change strategy. History:\n{history}\n\n"
            f"Return a brief decision and explanation."
        )
        result = await self._plan_agent.run(
            user_prompt=prompt,
            output_type=str,
            model_settings=ModelSettings(temperature=0.3, max_tokens=4096),
        )
        return (result.output,)
