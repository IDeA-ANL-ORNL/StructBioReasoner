"""Runs a single step of the binding hypothesis."""
from dataclasses import asdict
from pathlib import Path
import asyncio

from parsl import Config, HighThroughputExecutor

from struct_bio_reasoner.agents.computational_design.bindcraft_agent import BindCraftAgent
from struct_bio_reasoner.agents.shared_parsl_mixin import StandaloneParslContext
from struct_bio_reasoner.core.binder_design_system import BinderConfig
import struct_bio_reasoner as sbr


async def main(config: BinderConfig):
    agent = BindCraftAgent(
        'name',
        config=asdict(config),
        model_manager=None,  # TODO: pass in a real model manager
        parsl_config={},
    )

    # Launch Parsl and pass it to initializer
    parsl_config = Config(
        executors=[
            HighThroughputExecutor(
                max_workers_per_node=1,
                encrypted=False
            )
        ]
    )
    context = StandaloneParslContext(config=parsl_config)
    await agent.initialize(shared_context=context)
    assert await agent.is_ready()

    # Invoke the run
    await agent.generate_binder_hypothesis({
        'target_sequence': 'MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFPDWQNYTPGPGIRYPLKF',
    })

if __name__ == "__main__":
    _config = BinderConfig(
        cwd=Path.cwd(),
        device='cuda',
    )

    # Set the path to the proteinMPNN (assumed to be in the same directory as SBR)
    _sbr_path = Path(sbr.__file__).parents[2] / 'ProteinMPNN'
    _config.if_kwargs['proteinmpnn_path'] = str(_sbr_path)
    asyncio.run(main(_config))
