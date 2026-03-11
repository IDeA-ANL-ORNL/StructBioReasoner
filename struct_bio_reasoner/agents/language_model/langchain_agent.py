"""An implementation which uses LangChain.

Introduced to allow for inference with models provided by NVIDIA (which are not yet supported in Pydantic AI)"""
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import SystemMessagePromptTemplate
from langchain_nvidia import ChatNVIDIA
from langchain.chat_models import BaseChatModel
from pydantic import BaseModel
import httpx

from .pydantic_ai_agent import ReasonerAgent
from ...models import Recommendation


class LangChainAgent(ReasonerAgent):
    """LangChain-based agent. Currently inherits from PydanticAgent, but can be extended with LangChain-specific logic as needed."""

    def __init__(
            self,
            research_goal: str,
            enabled_agents: list[str],
            llm_provider: str,
            target_protein: str,
            *,
            resource_summary: str = "",
            base_url: str = "http://127.0.0.1:18000/v1/",
            model_name: str = "nvidia/llama-3.1-nemotron-nano-8b-v1",
            base_class: type[BaseChatModel] = ChatNVIDIA,
            api_key: str = "placeholder",
            auth: httpx.Auth | None = None,
            timeout: httpx.Timeout = httpx.Timeout(120.0, connect=30.0),
    ):
        super().__init__(
            research_goal=research_goal,
            enabled_agents=enabled_agents,
            llm_provider=llm_provider,
            target_protein=target_protein,
            resource_summary=resource_summary,
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            auth=auth,
            timeout=timeout,
        )

        # Replace the Pydantic AI client with a LangChain client here, using the same parameters
        self._agent = base_class(
            base_url=base_url,
            model=model_name,
            api_key=api_key
        )

    async def _invoke_agent(
            self,
            prompt: str,
            output_type: type[BaseModel] | None = None,
            temperature: float = 0.3,
            max_tokens: int = 32768,
    ) -> BaseModel | str:
        model = self._agent
        if output_type is not None:
            model = model.with_structured_output(Recommendation)

        messages = [
            SystemMessage(content="You output only valid JSON according to the specified schema."),
            HumanMessage(content=prompt),
        ]

        return await model.ainvoke(
            messages,
            config=dict(temperature=temperature, max_completion_tokens=max_tokens),
        )
