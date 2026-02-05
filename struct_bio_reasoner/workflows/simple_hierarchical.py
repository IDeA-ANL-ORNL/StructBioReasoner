from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Protocol, Tuple
import yaml

import parsl
from parsl import Config, HighThroughputExecutor
from parsl.concurrent import ParslPoolExecutor
from parsl.providers import LocalProvider

from academy.exchange import LocalExchangeFactory, RedisExchangeFactory
from academy.logging import init_logging
from academy.manager import Manager

from ..agents.executive.simple_executive import Executive
from ..agents.manager.manager_agent import ManagerAgent
#from ..core.binder_design_system import BinderDesignSystem
from ..utils.llm_interface import alcfLLM
from ..utils.parsl_settings import LocalSettings, LocalCPUSettings, AuroraSettings

logger = logging.getLogger(__name__)

class StructBioLLC:
    def __init__(self, config): 
        self.config = config
        Path(config.paths.output_dir).mkdir(parents=True, exist_ok=True)
        with open(config.paths.parsl_config) as f:
            self.base_parsl_settings = yaml.safe_load(f)

        self.executive_handle = None
        self.manager_handles: Dic[str, Any] = {}
        self._shutdown_requested = False
        self._initialized = False
        logger.info("StructBioLLC open for business")

    def _create_parsl_config(self, run_dir: Path) -> Config:
        """
        Create the SINGLE Parsl configuration for the entire workflow.

        This is the only place where Parsl Config is created.
        Worker agents receive SharedParslContext instead of creating their own.
        """
        worker_init = self.config.compute.worker_init_cmd

        # FIX: Use python_env (not conda_env which doesn't exist)
        if self.config.compute.python_env:
            worker_init = (
                f"cd {os.getcwd()}; "
                f"source {self.config.compute.python_env}/bin/activate; "
                f"{worker_init}"
            )

        parsl_config = AuroraSettings(**self.base_parsl_settings).config_factory(run_dir)

        '''
        TO-DO
        Need two executors in AuroraSettings 1. CPU, 2. GPU
        Add in decorators in each agent for each type of executor
        '''
        return parsl_config

    def _create_exchange_factory(self):
        """Create the appropriate exchange factory."""
        '''
        TO-DO
        convert this to globus exchange factory
        '''
        if self.config.exchange.use_redis:
            return RedisExchangeFactory(
                self.config.exchange.redis_host,
                self.config.exchange.redis_port
            )
        return LocalExchangeFactory()

    async def start(self):
        logger.info("=" * 80)
        logger.info("INITIATING WORKFLOW")
        logger.info("=" * 80)
        # Step 2: Create SINGLE Parsl configuration
        logger.info("Step 2: Creating single Parsl configuration...")
        run_dir = Path(self.config.paths.output_dir) / 'parsl_runinfo'
        run_dir.mkdir(parents=True, exist_ok=True)

        '''
        Establish parsl context shared for executors and directors
        '''
        self.parsl_config = self._create_parsl_config(run_dir)
        self.parsl_executor = ParslPoolExecutor(parsl_config)

        # Create shared context for worker agents
        self.shared_parsl_context = SharedParslContext(
            config=parsl_config,
            executor=self.parsl_executor,
            run_dir=run_dir,
        )

        logger.info("Board Meeting: New Executive Handle")       
        await self._launch_executive()
        logger.info("Board decision: Executive Handle launched")

        self.state.start_time = datetime.now()
        self._initialized = True
        logger.info("Workflow setup")

    async def _launch_executive(self):
        executive_config = self.config['executive']
        allocation_settings = executive_config['parsl']
        director_config = config['director']
        
        allocation_config = Config() # populate once we get exec engineered
        exec_exchange_factory = self._create_exchange_factory()

        self.academy_manager_ex = await Manager.from_exchange_factory(
                factory=exchange_factory,
                executors=self.parsl_executor,
            )

        await self.academy_manager_ex.__aenter()
        logger.info("Academy Manager initialized (exec -> directory_i)")


        self.executive_handle = await self.academy_manager_ex.launch(
                        Executive,
                        args=(
                            executive_config,
                            allocation_config,
                            director_config,
                            self.parsl_config,
                        ),
                        )
    async def run(self):
        logger.info("Executive hiring directors and beginning production")
        product = await self.executive_handle.perform_experiment()

def main():
    config = ""
    structbiollc = StructBioLLC(config)
    structbiollc.start()
    structbiollc.run()
