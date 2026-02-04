from academy.agent import Agent, action
from academy.exchange import RedisExchangeFactory
from academy.manager import Manager
import asyncio
from dataclasses import dataclass, fields
import importlib
import parsl
from parsl import Config, python_app
from parsl.concurrent import ParslPoolExecutor
from pathlib import Path
from typing import Any

@dataclass
class AgentRegistry:
    reasoner: "struct_bio_reasoner.agents.language_model.jnana_agent:JnanaAgent"
    director: "struct_bio_reasoner.agents.manager.director_agent:Director"

    def get(self, label: str) -> type:
        path = getattr(self, label)
        module_path, class_name = path.split(':')
        return getattr(importlib.import_module(module_path), class_name)

    def available(self) -> list[str]:
        return [f.name for f in fields(self)]

class Executive(Agent):
    def __init__(self,
                 executive_config: dict[str, Any],
                 allocation_config: Config,
                 director_config: dict[str, Any],
                 parsl_settings: dict[str, Any],
                ):
        self.config = executive_config
        self.allocation_config = allocation_config
        self.directory_config = director_config
        self.parsl_settings = parsl_settings

        self.agent_registry = AgentRegistry()
        self.directors = {}

        super().__init__()

    async def agent_on_startup(self):
        # probably do something with parsl here unless we launch
        # directors directly with academy
        pass

    async def agent_on_shutdown(self):
        # probably kill parsl here unless this is also an academy
        # endeavor
        pass

    async def perfom_experiment(self):
        await self.initialize()
        
        # is this how you use a timer loop?
        while await self.manage_directors():
            continue

    async def initialize(self):
        await self.launch_reasoner()
        # initial reasoning here
        # launch initial directors here

    @timer(interval=600) # seconds
    async def manage_directors(self):
        for director in self.directors.values():
            signal = await self.evaluate_director(director)

            match signal:
                case 'KILL':
                    self.available_resources.append(
                        await self.kill_director(director)
                    )
                case 'ADVISE':
                    await self.advise_director(director)
                case _:
                    continue

        if self.available_resources:
            await self.launch_director(self.available_resources)

        if await self.end_experiment():
            return False

        return True

    @action
    async def launch_reasoner(self):
        self.reasoner = await self.agent_launch_alongside(
            self.agent_registry['reasoner'],
            args=(
            ),
        )
        
    @action
    async def launch_director(self):
        # how do we do this?
        pass

    @action
    async def kill_director(self,
                            director: Agent) -> None:
        await director.agent_shutdown()

    @action
    async def advise_director(self,
                              director: Agent):
        await director.receive_instruction(instruction)

    @action
    async def evaluate_director(self,
                                director: Agent) -> None:
        # how do we do this?
        status = director.check_status()
        recommendation = self.reasoner.generate_recommendation(
            status,
            previous_run='',
            history='',
        )

        return recommendation[0]

    @action
    async def end_experiment(self):
        # what is the kill signal?
        pass

async def main(configuration_file: str):
    config = yaml.safe_load(configuration_file)

    executive_config = config['executive']
    allocation_settings = executive_config['parsl']
    director_config = config['director']
    parsl_config = director_config['parsl']

    allocation_config = Config(
    )

    manager = await Manager.from_exchange_factory(
        factory = RedisExchangeFactory('localhost', 6379),
        executors = ParslPoolExecutor(allocation_config),
        
    )

    await manager.__aenter__()

    executive = await manager.launch(
        Executive,
        args=(
            executive_config,
            allocation_config,
            director_config,
            parsl_config,
        ),
    )

    await executive.perform_experiment()

    await manager.__aexit__()

if __name__ == '__main__':
    asyncio.run(
        main(
            configuration_file='',
        )
    )
