from academy.agent import Agent, action
from academy.exchange import LocalExchangeFactory
from academy.handle import Handle
from academy.manager import Manager
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, fields
import importlib
import logging
import parsl
from parsl import Config
from pathlib import Path
from typing import Any, Optional, Literal

@dataclass
class AgentRegistry:
    reasoner: "struct_bio_reasoner.agents.language_model.jnana_agent:JnanaAgent"
    bindcraft: "struct_bio_reasoner.agents.computational_design.bindcraft_coordinator:BindCraftCoordinator"
    md: "struct_bio_reasoner.agents.molecular_dynamics.MD:MDCoordinator"
    mmpbsa: "struct_bio_reasoner.agents.molecular_dynamics.mmpbsa_agent:FECoordinator"
    folding: "struct_bio_reasoner.agents.structure_prediction.chai_agent:ChaiAgent"

    def get(self, label: str) -> type:
        path = getattr(self, label)
        module_path, class_name = path.split(':')
        return getattr(importlib.import_module(module_path), class_name)

    def available(self) -> list[str]:
        return [f.name for f in fields(self)]

class Director(Agent):
    def __init__(self,
                 runtime_config: dict,
                 parsl_config: Config):
        super().__init__()
        self.config = runtime_config
        self.parsl_config = parsl_config
        self.agent_registry = AgentRegistry()

    async def initialize(self):
        self.manager = await Manager.from_exchange_factory(
            factory = LocalExchangeFactory(),
            executors = ThreadPoolExecutor(),
        )

        await self.manager.__aenter__()

        await self.load_agents(self.config)
    
    async def cleanup(self):
        try:
            self.manager.__aexit__(None, None, None)
        except:
            continue
        finally:
            self.manager = None

    async def agent_on_startup(self) -> None:
        self.dfk = parsl.load(self.parsl_config)

    async def agent_on_shutdown(self):
        if self.dfk:
            self.dfk.cleanup()
            self.dfk = None

        parsl.clear()

    async def load_agents(self,
                          config):
        """"""
        self.agents = {}
        for agent, args in config.items():
            self.agents[agent] = await self.manager.agent_launch_alongside(
                    self.agent_registry.get(agent),
                    args=(
                        *args
                    )
            )

    async def test(self):
        """Test main loop"""
        previous_run = 'starting'
        results = {'results': 'none'}
        history = ''

        reasoner_input = {
            'results': results,
            'previous_run': previous_run,
            'history': history,
        }
        response = await self.query_reasoner(reasoner_input) # gets prompt for tool call

        # unpack reasoning trace
        previous_run = response['previous_run']
        tool = response['tool']
        plan = response['plan']

        results = await self.tool_call(tool, plan) # do tool call

    async def main(self):
        """Main while loop logic"""
        previous_run = 'starting'
        results = {'results': 'none'}
        history = ''
        while True:
            reasoner_input = {
                'results': results,
                'previous_run': previous_run,
                'history': history,
            }
            response = await self.query_reasoner(reasoner_input) # gets prompt for tool call

            # unpack reasoning trace
            previous_run = response['previous_run']
            tool = response['tool']
            plan = response['plan']

            results = await self.tool_call(tool, plan) # do tool call

    @action
    async def query_reasoner(self,
                             data: dict[str, Any]) -> dict[str, Any]:
        recommendation = await self.agents['reasoner'].generate_recommendation(
            results=data['results'],
            previous_run=data['previous_run'],
            history=data['history'],
        )

        config = await self.agents['reasoner'].plan_run(
            recommendation=recommendation,
            history=data['history']
        )

        return {
            'previous_run': data['previous_run'],
            'history': data['history'].append(data['previous_run']),
            'recommendation': recommendation,
            'tool': recommendation['recommendation']['next_task'],
            'plan', config
        }

    @action
    async def tool_call(self,
                        tool: str,
                        plan: dict[str, Any]):
        """Access correct subagent based on the `tool` key. Pass in
        the inputs in the form of **kwargs."""
        return await self.agents[tool].run(**plan)
