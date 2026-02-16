from academy.agent import Agent, action
from academy.manager import Manager
import asyncio
import importlib
import logging
import parsl
from parsl import Config
from pathlib import Path
from typing import Any, Optional, Literal

from pydantic import BaseModel


class AgentRegistry(BaseModel):
    reasoner: str = 'struct_bio_reasoner.agents.language_model.pydantic_ai_agent:ReasonerAgent'
    bindcraft: str = 'struct_bio_reasoner.agents.computational_design.bindcraft_coordinator:BindCraftCoordinator'
    md: str = 'struct_bio_reasoner.agents.molecular_dynamics.MD:MDAgent'
    mmpbsa: str = 'struct_bio_reasoner.agents.molecular_dynamics.mmpbsa_agent:FEAgent'
    folding: str = 'struct_bio_reasoner.agents.structure_prediction.chai_agent:ChaiAgent'

    def get(self, label: str) -> type:
        path = getattr(self, label)
        module_path, class_name = path.split(':')
        return getattr(importlib.import_module(module_path), class_name)

    def available(self) -> list[str]:
        return list(type(self).model_fields.keys())

class Director(Agent):
    def __init__(self,
                 runtime_config: dict[str, Any],
                 parsl_config: Config,):
        self.runtime_config = runtime_config
        self.parsl_config = parsl_config
        self.agent_registry = AgentRegistry()

        self.previous_run = 'starting'
        self.history = []

        self.logger = logging.getLogger(__name__)

        super().__init__()

    async def agent_on_startup(self) -> None:
        self.dfk = parsl.load(self.parsl_config)
        await self.load_agents()

    async def agent_on_shutdown(self):
        if self.dfk:
            self.dfk.cleanup()
            self.dfk = None

        parsl.clear()

    async def load_agents(self):
        """"""
        self.agents = {}
        available_agents = self.agent_registry.available()
        for agent, kwargs in self.runtime_config.items():
            print(kwargs)
            if agent in available_agents:
                self.agents[agent] = await self.agent_launch_alongside(
                    self.agent_registry.get(agent),
                    args=None,
                    kwargs=kwargs,
                )

        self.logger.info(f'Loaded {len(self.agents)} agents!')

    @action
    async def agentic_test(self) -> tuple[str, Any]:
        """Test main loop"""
        previous_run = 'starting'
        results = {'results': 'none'}
        history = ''

        reasoner_input = {
            'results': results,
            'previous_run': previous_run,
            'history': history,
        }
        tool, plan = await self.query_reasoner(reasoner_input)
        self.logger.info(f"Next task: {tool}")

        results = await self.tool_call(tool, plan)

        return tool, results

    @action
    async def agentic_run(self):
        """Main while loop logic"""
        results = {'results': 'none'}
        while True:
            reasoner_input = {
                'results': results,
                'previous_run': self.previous_run,
                'history': self.history,
            }

            tool, plan = await self.query_reasoner(reasoner_input) # gets prompt for tool call

            results = await self.tool_call(tool, plan) # do tool call

    async def query_reasoner(self,
                             data: dict[str, Any]) -> tuple[str, BaseModel]:
        recommendation = await self.agents['reasoner'].generate_recommendation(
            results=data['results'],
            previous_run=data['previous_run'],
            history=data['history'],
        )

        config = await self.agents['reasoner'].plan_run(
            recommendation=recommendation,
            history=data['history']
        )

        self.previous_run = data['previous_run']
        self.history.append(data['history'])

        return recommendation.recommendation.next_task, config

    async def tool_call(self,
                        tool: str,
                        plan: BaseModel | dict[str, Any]):
        """Access correct subagent based on the `tool` key. Pass in
        the inputs in the form of **kwargs."""
        kwargs = plan.model_dump() if isinstance(plan, BaseModel) else plan
        return await self.agents[tool].run(**kwargs)

    @action
    async def executive_reasoning(self,
                                  prompt: str):
        """Hook into the reasoning agent for the executive agent.
        """
        response = await self.agents['reasoner'].query()

    @action
    async def check_status(self) -> str:
        """"""
        status = await self.agents['reasoner'].evaluate_history(self.history)
        return status

    @action
    async def receive_instruction(self,
                                  instruction: str):
        """Receive instructions from Executive agent. Utilize this in the next
        reasoning trace to guide next task(s)."""
        # Somehow incorporate a signal from upstream reasoning into the next task
        pass
