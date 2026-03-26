"""
Academy wrapper on LLM interface (Jnana) to inject into StructBioReasoner workflow.
This module implements the reasoner agent within the agentic workflow
using Academy agents, enabling dynamic decision-making and adaptive optimization.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any
import parsl
from parsl import Config
from parsl import HighThroughputExecutor
from parsl.providers import LocalProvider
from parsl.launchers import MpiExecLauncher
try:
    from academy.agent import Agent, action
    from academy.handle import Handle
    from academy.exchange import LocalExchangeFactory
    from academy.manager import Manager
except ImportError:
    raise ImportError(
        "The 'academy' package is required for Jnana agent. "
        "Install Jnana with: pip install git+https://github.com/acadev/Jnana.git --no-deps"
    )
from concurrent.futures import ThreadPoolExecutor
from ...data.protein_hypothesis import  ProteinHypothesis
from ...core.base_agent import BaseAgent

from struct_bio_reasoner.prompts.recommender_prompts import RecommenderPromptManager 
from struct_bio_reasoner.prompts.prompts import get_prompt_manager, config_master
from struct_bio_reasoner.utils.llm_interface import create_llm
import json
import os
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
import numpy as np
import openai
import requests
from dotenv import load_dotenv
from pydantic import Field
from pydantic import model_validator

logger = logging.getLogger(__name__)


class JnanaAgent(Agent):
    '''
    Agent responsible for running RAG
    '''
    def __init__(self,
                config_inp,
                ):
        self.config = config_inp
        self.research_goal = self.config['research_goal']
        self.enabled_agents = self.config['enabled_agents']
        self.llm_provider = self.config['llm_provider']
        self.rec_prompt_man = RecommenderPromptManager(
                                research_goal,
                                enabled_agents)

        self.rec_schema = {
            'next_task': 'string',
            'change_parameters': 'boolean',
            'rationale': 'string',
            }

        self.plan_schema = {
            'new_config': 'placeholder',
            'rationale': 'string'
            }
        self.llm = create_llm(self.llm_provider)
        
    def fill_prompt_template(
        self,
        system_str: str='system',
        agent_type='recommender',
        role='Recommend next runs to make'
        ):
        return

    @action
    async def generate_recommendation(
              self,
              results,
              previous_run,
              agent_prompt_manager
              ):

        """
        Generate a protein-specific hypothesis.

        Args:
            results
        Returns:
            Generated recommendation
        """
        agent_prompt_manager.input_json = results
        agent_prompt_manager.conclusion_prompt()
        
        self.rec_prompt_man.recommend_prompt(
            previous_run,
            agent_prompt_manager.prompt_c
            )

        system_prompt = self.fill_prompt_template(
                        'system',
                        agent_type='recommender',
                        role='Recommend next runs to make')

        response_data = self.llm.generate_with_json_output(
                        prompt = self.rec_prompt_man.prompt_r,
                        schema = self.rec_schema,
                        system_prompt = system_prompt,
                        tools=None)
        
        return response_data
        
    @action
    async def plan_run(
              self,
              previous_run,
              recommendation,
              agent_prompt_manager,
              ):
        agent_prompt_manager.running_prompt()
        system_prompt = self.fill_prompt_template(
                            system='system',
                            agent_type = 'recommender',
                            role='Recommend next runs to make')

        self.plan_schema['new_config'] = config_master[recommendation['next_task']]
        response_data = self.llm.generate_with_json_output(
                        prompt=prompt,
                        schema=schema,
                        system_prompt = system_prompt,
                        tools=None,
                        )
        return response_data


class JnanaWrapper:
    '''
    Wrapper on top of academy 
    for StructBioReasoner
    '''
    
    def __init__(self,
                 agent_id:str,
                 config: dict[str, Any],
                 research_goal: str,
                 enabled_agents: list[str]
                 ):
        
        self.agent_id = agent_id
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.generated_hypotheses = []
                                                               
        self.jnana_config = config
        self.research_goal = research_goal
        self.enabled_agents = enabled_agents

    async def initialize(self):
        logger.info('Initializing Jnana agent')
        self.manager = await Manager.from_exchange_factory(
                factory=LocalExchangeFactory(),
                executors = ThreadPoolExecutor(),
                )
        await self.manager.__aenter__()

        try:
            self.jnana_coord = await self.manager.launch(
                JnanaAgent,
                args=(
                    self.jnana_config,
                    ),
            )
            logger.info('Launching Jnana')
            self.initialized = True
        except Exception as e:
            self.logger.exception("An error occurred with the RAGAgent")
            return False
        return True

    async def is_ready(self) -> bool:
        self.logger.debug('Checking if we are initialized')
        if not hasattr(self, 'initialized'):
            await self.initialize()
            
        return self.initialized

    async def cleanup(self):
        try:
            if self.manager:
                try:
                    await self.manager.__aexit__(None, None, None)
                    self.logger.info('Academy manager context exited successfully')
                except Exception as e:
                    self.logger.warning(f'Error exiting manager context: {e}')
                finally:
                    self.manager = None
                    delattr(self, 'initialized')

            self.logger.info('Jnana agent cleanup completed')

        except Exception as e:
            self.logger.error(f'Jnana agent cleanup failed: {e}')

    def write_checkpoint(self, results: dict[str, Any]):
        #Use timestemp tom get unique name
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        checkpoint_file = f'jnana_checkpoint_{timestamp}.pkl'
        pickle.dump(results, open(checkpoint_file, 'wb'))
        return checkpoint_file

    async def generate_jnana_hypothesis(self,
                            data: dict[str, Any]) -> str:
        if not await self.is_ready():
            self.logger.error('Jnana agent not ready')
            return None
        jnana_results =  await self._generate_jnana_hypothesis(data)
        self.logger.debug(f"{jnana_results=}")
        return await jnana_results

    async def _generate_jnana_hypothesis(self,
                    data: dict[str, Any]) -> dict[str, Any]:
        '''
        call Jnana agent with input data
        data includes user prompt
        '''
        results = data['results']
        previous_run = data['previous_run']
        agent_prompt_manager = data['agent_prompt_manager']
        recommendation = await self.jnana_coord.generate_recommendation(
                        results = results,
                        previous_run = previous_run,
                        agent_prompt_manager = agent_prompt_manager
        )

        recommended_config = await self.jnana_coord.plan_run(
                            previous_run = previous_run,
                            recommendation = recommendation,
                            agent_prompt_manager = agent_prompt_manager)

        results = {
                      'previous_run': previous_run,
                      'recommendation': recommendation,
                      'plan': recommended_config  
                    }

        await self.cleanup()
        return results
    
    async def postprocess(self,
                            results: dict[str, Any]) -> ProteinHypothesis:
        hypothesis_content = f"""
        Recommendation: {results['recommendation']}.
        Plan for new run: {results['plan']}
        """

        hypothesis = ProteinHypothesis(
            title='Jnana recommendation',
            content=hypothesis_content.strip(),
            description=f'Jnana generates this hypothesis based on the previous run: {results["previous_run"]}',
            hypothesis_type='',
            generation_timestamp=datetime.now().isoformat(),
            metadata=results,
        )

        # Set hallmarks based on analysis quality
        hypothesis.hallmarks = {
            'testability': 8.5,  # MD predictions are highly testable
            'specificity': 7.5,  # Specific residue-level predictions
            'grounded_knowledge': 9.0,  # Based on physics-based simulations
            'predictive_power': 8.0,  # Quantitative predictions
            'parsimony': 7.0   # Straightforward thermostability model
        }

        self.generated_hypotheses.append(hypothesis)
        return hypothesis

