from academy.exchange import RedisExchangeFactory
from academy.handle import Handle
from academy.manager import Manager
import asyncio
import parsl
from parsl import Config, python_app
from parsl.concurrent import ParslPoolExecutor
from pathlib import Path
from time import sleep
from typing import Any
from struct_bio_reasoner.agents.language_model.jnana_agent import JnanaAgent
from struct_bio_reasoner.agents.manager.director_agent import Director
from struct_bio_reasoner.utils import HeterogeneousSettings

class Executive:
    def __init__(self,
                 configuration_file: str):
        full_configuration = yaml.safe_load(configuration_file)
        self.config = full_configuration['executive']
        self.allocation_config = self.config['parsl']
        self.director_config = full_configuration['director']
        self.parsl_factory = HeterogeneousSettings(**self.director_config['parsl'])

        self.directors = {}
        self.available_ids = []

    async def perfom_experiment(self):
        await self.initialize()
        
        # is this how you use a timer loop?
        while await self.manage_directors():
            pass
            sleep(self.config['check_interval'])

        await self.summarize_experiment()

    async def initialize(self):
        # what does this config need to look like?
        allocation_config = Config(
            
        )

        # do these settings make sense for the redisexchange?
        self.manager = await Manager.from_exchange_factory(
            factory = RedisExchangeFactory('localhost', 6379),
            executors = ParslPoolExecutor(allocation_config),
        )

        await self.manager.__aenter__()

        # how do we handle this now?
        await self.launch_reasoner()
        # initial reasoning here
        # launch initial directors here based on resources in allocation + parsl

    async def manage_directors(self):
        for director_id, director in self.directors.items():
            signal = await self.evaluate_director(director)

            match signal:
                case 'KILL':
                    # maybe return director history to inform next director
                    await self.kill_director(director)
                    self.available_ids.append(director_id)
                case 'ADVISE':
                    # somehow generate instruction for director
                    await self.advise_director(director)
                case _:
                    continue

        while self.available_ids:
            director_id = self.available_ids.pop()
            self.directors[director_id] = await self.launch_director()

        if await self.end_experiment():
            return False

        return True

    async def launch_reasoner(self) -> None:
        # NOTE: rework this
        self.reasoner = await self.agent_launch_alongside(
            self.agent_registry['reasoner'],
            args=(
            ),
        )
        
    async def launch_director(self) -> Handle:
        director_handle = self.manager.launch(
            Director,
            args=(
                self.director_config,
                self.parsl_factory,
            ),
        )

        return director_handle

    async def kill_director(self,
                            director: Agent) -> None:
        await director.agent_shutdown()

    async def advise_director(self,
                              director: Agent,
                              instruction: str) -> None:
        await director.receive_instruction(instruction)

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

    async def end_experiment(self):
        # what is the kill signal?
        pass

    async def summarize_experiment(self):
        # use reasoner to do this
        self.manager.__aexit__()
        pass

if __name__ == '__main__':
    asyncio.run(
        main(
            configuration_file='',
        )
    )
