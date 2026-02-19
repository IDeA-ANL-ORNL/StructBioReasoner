"""
Reasoner agent for StructBioReasoner.

Uses pydantic-ai with PromptedOutput mode for structured JSON generation
against any OpenAI-compatible endpoint.
"""

import logging
from typing import Any

import httpx
from pydantic_ai import Agent as pAgent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.output import PromptedOutput
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from pydantic import BaseModel
from academy.agent import Agent, action
from struct_bio_reasoner.models import Recommendation, RecommendationResult
from struct_bio_reasoner.prompts import (
    build_prompt_context, get_conclusion_prompt, get_running_prompt,
    get_plan_model, build_recommender_prompt,
)
from struct_bio_reasoner.utils.inference_auth_token import get_access_token

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section 2: ALCF Auth Utility
# ---------------------------------------------------------------------------

class ALCFTokenAuth(httpx.Auth):
    """httpx auth handler that refreshes the Globus access token per request."""

    def auth_flow(self, request: httpx.Request):
        token = get_access_token()
        request.headers["Authorization"] = f"Bearer {token}"
        yield request


# ---------------------------------------------------------------------------
# Section 3: Academy Agent Wrapper
# ---------------------------------------------------------------------------

class ReasonerAgent(Agent):
    """Academy-compatible reasoner agent backed by pydantic-ai.

    To point at a different endpoint, pass keyword-only args:
        ReasonerAgent(goal, agents, provider, protein,
            base_url="http://localhost:8000/v1",
            model_name="meta-llama/Llama-3-70b",
        )
    For ALCF Globus auth, pass auth=ALCFTokenAuth().
    """

    def __init__(
        self,
        research_goal: str,
        enabled_agents: list[str],
        llm_provider: str,
        target_protein: str,
        *,
        resource_summary: str = "",
        base_url: str = "https://inference-api.alcf.anl.gov/resource_server/sophia/vllm/v1",
        model_name: str = "openai/gpt-oss-120b",
        api_key: str = "placeholder",
        auth: httpx.Auth | None = None,
        timeout: httpx.Timeout = httpx.Timeout(120.0, connect=30.0),
    ):
        self.research_goal = research_goal
        self.enabled_agents = enabled_agents
        self.llm_provider = llm_provider
        self.target_protein = target_protein
        self.resource_summary = resource_summary

        # Default to ALCF Globus auth when provider is 'alcf'
        if auth is None and llm_provider == "alcf":
            auth = ALCFTokenAuth()

        # Build the pydantic-ai model
        http_client = httpx.AsyncClient(auth=auth, timeout=timeout)
        provider = OpenAIProvider(base_url=base_url, api_key=api_key, http_client=http_client)
        self._model = OpenAIChatModel(model_name, provider=provider)

        # Single internal pydantic-ai agent; output_type is overridden per call
        self._agent = pAgent(
            model=self._model,
            output_type=str,
            instructions="You output only valid JSON according to the specified schema.",
        )

    # -- actions -------------------------------------------------------------

    @action
    async def generate_recommendation(
        self,
        results: Any,
        previous_run: str,
        history: dict,
        prompt_type: str = "",
        executive_instruction: str | None = None,
    ) -> RecommendationResult:
        """Generate a recommended next task.

        Returns a typed RecommendationResult with nested Recommendation model.
        """
        ctx = build_prompt_context(
            agent_type=previous_run,
            research_goal=self.research_goal,
            input_json=results,
            target_prot=self.target_protein,
            prompt_type=prompt_type,
            history=history,
            resource_summary=self.resource_summary,
        )

        conclusion_text = get_conclusion_prompt(previous_run, ctx)
        logger.debug(conclusion_text)

        recommender_prompt = build_recommender_prompt(
            enabled_agents=self.enabled_agents,
            research_goal=self.research_goal,
            previous_run=previous_run,
            previous_conclusion=conclusion_text,
            history=ctx.history,
            resource_summary=self.resource_summary,
        )

        if executive_instruction:
            recommender_prompt += (
                f"\n\n## Executive Instruction\n"
                f"The executive has provided the following guidance:\n"
                f"{executive_instruction}\n"
                f"Take this into account when making your recommendation."
            )

        logger.debug(recommender_prompt)

        result = await self._agent.run(
            user_prompt=recommender_prompt,
            output_type=PromptedOutput(Recommendation),
            model_settings=ModelSettings(temperature=0.3, max_tokens=32768),
        )

        recommendation = result.output
        logger.debug(recommendation)

        return RecommendationResult(
            previous_run=previous_run,
            recommendation=recommendation,
        )

    @action
    async def plan_run(
        self,
        recommendation: RecommendationResult,
        history: dict,
        prompt_type: str = "",
    ) -> BaseModel | dict[str, Any]:
        """Generate a config for the recommended next task.

        Returns the plan as a typed Pydantic model (e.g. ComputationalDesignPlan),
        or a raw dict if no plan model is defined for the task.
        """
        next_task = recommendation.recommendation.next_task
        logger.debug(next_task)

        ctx = build_prompt_context(
            agent_type=next_task,
            research_goal=self.research_goal,
            input_json=recommendation.model_dump(),
            target_prot=self.target_protein,
            prompt_type=prompt_type,
            history=history,
            resource_summary=self.resource_summary,
        )

        running_text = get_running_prompt(next_task, ctx)

        plan_model = get_plan_model(next_task)
        if plan_model is None:
            logger.warning(
                f"No Pydantic plan model for task '{next_task}', falling back to str output"
            )
            result = await self._agent.run(
                user_prompt=running_text,
                model_settings=ModelSettings(temperature=0.3, max_tokens=32768),
            )
            return {"raw": result.output}

        result = await self._agent.run(
            user_prompt=running_text,
            output_type=PromptedOutput(plan_model),
            model_settings=ModelSettings(temperature=0.3, max_tokens=32768),
        )

        return result.output

    @action
    async def query(self, prompt: str) -> str:
        """Send a free-form prompt to the LLM and return the response."""
        result = await self._agent.run(
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
        result = await self._agent.run(
            user_prompt=prompt,
            output_type=str,
            model_settings=ModelSettings(temperature=0.3, max_tokens=4096),
        )
        return (result.output,)


# Backward-compat alias
PydanticAIReasonerAgent = ReasonerAgent
