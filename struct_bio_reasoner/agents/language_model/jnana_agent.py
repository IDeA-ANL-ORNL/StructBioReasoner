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
from academy.agent import Agent, action
from academy.handle import Handle
from academy.exchange import LocalExchangeFactory
from academy.manager import Manager
from concurrent.futures import ThreadPoolExecutor
from ...data.protein_hypothesis import  ProteinHypothesis
from ...core.base_agent import BaseAgent

from struct_bio_reasoner.prompts.recommender_prompts import RecommenderPromptManager 
from struct_bio_reasoner.prompts.prompts_v2 import get_prompt_manager, config_master
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
        '''
        config_inp: includes
        - research_goal
        - enabled_agents
        - llm_provider
        - target_prot
        '''
        self.config = config_inp
        self.research_goal = self.config['research_goal']
        self.enabled_agents = self.config['enabled_agents']
        self.llm_provider = self.config['llm_provider']
        self.target_prot = self.config['target_prot']

        ### Setting up llm
        self.llm = create_llm(self.llm_provider)

        ### Setting up prompt manager for recommendations
        self.rec_prompt_man = RecommenderPromptManager(
                                self.research_goal,
                                self.enabled_agents)
        
        ### Schema for making recommendations
        self.rec_schema = {
            'next_task': 'string',
            'change_parameters': 'boolean',
            'rationale': 'string',
            }

        ### Schema for generating appropriate configs
        self.plan_schema = {
            'new_config': 'placeholder',
            'rationale': 'string'
            }
        
    ### TO-DO: Write this function based on jnana internal stuff
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
              history,
              prompt_type=""
              ):
        
        """
        Generate a recommended next task.
        - results, previous_run, prompt_type, history ---> prompt_manager --> agent_prompt_manager
        - previous_run, agent_prompt_manager.prompt_c ---> recommendation_prompt + rec_schema ---> llm ---> recommendation for next task

        Args:
            results
        Returns:
            Generated recommendation
        """

        ### Fix prompts to take in simpler recommendation types and only use two prompt_types:
        ### binder_design or hotspot_discovery
        agent_prompt_manager = get_prompt_manager(
                                    agent_type=previous_run,
                                    research_goal = self.research_goal,
                                    input_json = results,
                                    target_prot = self.target_prot,
                                    prompt_type = prompt_type,
                                    history = history,
                                    num_history = 3)

        agent_prompt_manager.conclusion_prompt()
        logger.info(f'{agent_prompt_manager.prompt_c=}')
        self.rec_prompt_man.recommend_prompt(
            previous_run,
            agent_prompt_manager.prompt_c,
            history
            )

        system_prompt = self.fill_prompt_template(
                        'system',
                        agent_type='recommender',
                        role='Recommend next runs to make')

        logger.info(self.rec_prompt_man.prompt_r)
        response_data = self.llm.generate_with_json_output(
                        prompt = self.rec_prompt_man.prompt_r,
                        json_schema = self.rec_schema,
                        system_prompt = system_prompt,
                        temperature = 0.3,
                        max_tokens = 32768, 
                        tools=None)
        logger.info(f'{response_data=}')
        results = {'previous_run': previous_run, 'recommendation': response_data[0]}
        return results
        
    @action
    async def plan_run(
              self,
              recommendation,
              history,
              prompt_type=""
              ):
        """
        Generate a useful config for the next_task.
        - recommendation['next_task'], recommendation['rationale'], prompt_type, history ---> prompt_manager --> agent_prompt_manager
        - previous_run, agent_prompt_manager.prompt_c ---> recommendation_prompt + rec_schema ---> llm ---> recommendation

        Args:
            results
        Returns:
            Generated recommendation
        """
        logger.info(f"{history=}")
        ### TO-DO: fix prompts so that they use the new simpler recommendation format ('next_task' and 'rationale')
        logger.info(f"{recommendation['recommendation']['next_task']}")
        agent_prompt_manager = get_prompt_manager(
                                    agent_type=recommendation['recommendation']['next_task'],
                                    research_goal = self.research_goal,
                                    input_json = recommendation,
                                    target_prot = self.target_prot,
                                    prompt_type = prompt_type,
                                    history = history,
                                    num_history = 3)

        agent_prompt_manager.running_prompt()
        system_prompt = self.fill_prompt_template(
                            'system',
                            agent_type = 'recommender',
                            role='Recommend next runs to make')

        self.plan_schema['new_config'] = config_master[recommendation['recommendation']['next_task']]
        response_data = self.llm.generate_with_json_output(
                        prompt=agent_prompt_manager.prompt_r,
                        json_schema=self.plan_schema,
                        system_prompt = system_prompt,
                        temperature = 0.3,
                        max_tokens = 32768,
                        tools=None,
                        )
        return response_data[0]


class JnanaWrapper:
    '''
    Wrapper on top of academy 
    for StructBioReasoner
    '''
    ''' 
    TO-DOs:
        - system: initialize jnana agent: DONE
        - workflow script: insert jnana wrapper and use this to move to next task + new config: DONE
        - workflow script: append to history using jnana results after recommendation: DONE
        - prompts.prompts: take in recommendation properly DONE
        - prompts.prompts: use either binder_design or hotspot_discovery as prompt_types: DONE
        - 
    '''

    
    def __init__(self,
                 agent_id:str,
                 config: dict[str, Any],
                 research_goal: str,
                 enabled_agents: list[str],
                 target_prot: str
                 ):
        
        self.agent_id = agent_id
        #self.config = config
        self.logger = logging.getLogger(__name__)
        self.generated_hypotheses = []
                                                               
        '''
        Config_inp should already have llm_provider
        We add:
            - research_goal
            - enabled_agents
            - target_prot
        '''
        self.jnana_config = config
        
        self.jnana_config['research_goal'] = research_goal
        self.jnana_config['enabled_agents'] = enabled_agents
        self.jnana_config['target_prot'] = target_prot

    async def initialize(self):
        logger.info('Initializing Jnana agent')
        self.manager = await Manager.from_exchange_factory(
                factory=LocalExchangeFactory(),
                executors = ThreadPoolExecutor(),
                )
        await self.manager.__aenter__()

        try:
            '''
            Launching jnana coordinator with only jnana config
            '''
            self.jnana_coord = await self.manager.launch(
                JnanaAgent,
                args=(
                    self.jnana_config,
                    ),
            )
            logger.info('Launching Jnana')
            self.initialized = True
        except Exception as e:
            self.logger.exception("An error occurred with the Jnana agent")
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
        return jnana_results

    async def _generate_jnana_hypothesis(self,
                    data: dict[str, Any]) -> dict[str, Any]:
        '''
        call Jnana agent with input data
        data includes:
            - results
            - previous_run
            - prompt_type: binder_design or hotspot_discovery
            - history
        '''
        results = data['results']
        previous_run = data['previous_run']
        prompt_type = data['prompt_type']
        history = data['history']
        #agent_prompt_manager = data['agent_prompt_manager']
        recommendation = await self.jnana_coord.generate_recommendation(
                        results = results,
                        previous_run = previous_run,
                        history=history,#agent_prompt_manager = agent_prompt_manager
                        prompt_type = prompt_type
        )
        logger.info(f'{history=}')
        recommended_config = await self.jnana_coord.plan_run(
                            recommendation = recommendation,
                            history = history,
                            prompt_type = prompt_type)

        results = {
                      'previous_run': previous_run,
                      'recommendation': recommendation,
                      'plan': recommended_config
                    }

        await self.cleanup()
        return results
    
