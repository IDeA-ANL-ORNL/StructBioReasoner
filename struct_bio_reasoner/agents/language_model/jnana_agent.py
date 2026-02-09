"""
Academy wrapper on LLM interface (Jnana) to inject into StructBioReasoner workflow.
This module implements the reasoner agent within the agentic workflow
using Academy agents, enabling dynamic decision-making and adaptive optimization.
"""

import asyncio
from academy.agent import Agent, action
import logging
from pathlib import Path
from typing import Any

from struct_bio_reasoner.prompts.recommender_prompts import RecommenderPromptManager 
from struct_bio_reasoner.prompts.prompts_v2 import get_prompt_manager, config_master
from struct_bio_reasoner.utils.llm_interface import create_llm

logger = logging.getLogger(__name__)


class JnanaAgent(Agent):
    """
    Agent responsible for running RAG
    """
    def __init__(self,
                 research_goal: str,
                 enabled_agents: list[str],
                 llm_provider: str,
                 target_protein: str):
        self.research_goal = research_goal
        self.enabled_agents = enabled_agent
        self.llm_provider = llm_provider
        self.target_protein = target_protein

        ### Setting up llm
        self.llm = create_llm(self.llm_provider)

        ### Setting up prompt manager for recommendations
        self.recommender_manager = RecommenderPromptManager(
            self.research_goal,
            self.enabled_agents
        )
        
        ### Schema for making recommendations
        self.recommendation_schema = {
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
    def fill_prompt_template(self,
                             system_str: str='system',
                             agent_type='recommender',
                             role='Recommend next runs to make') -> None:
        return

    @action
    async def query(self,
                    prompt: str) -> str:
        """Send a prescribed prompt to the Reasoner and return the response."""
        pass

    @action
    async def evaluate_history(self,
                               history: str) -> tuple[str]:
        """Examine a director's history with the reasoner and return a decision signal
        and explanation of the decision."""
        pass

    @action
    async def generate_recommendation(self,
                                      results: Any,
                                      previous_run: str,
                                      history: dict,
                                      prompt_type: str="") -> str:
        
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
                                    target_prot = self.target_protein,
                                    prompt_type = prompt_type,
                                    history = history,
                                    num_history = 3)

        agent_prompt_manager.conclusion_prompt()
        logger.debug(agent_prompt_manager.prompt_c=)
        
        self.recommender_manager.recommend_prompt(
            previous_run,
            agent_prompt_manager.prompt_c,
            history
        )

        system_prompt = self.fill_prompt_template(
                        'system',
                        agent_type='recommender',
                        role='Recommend next runs to make')

        logger.debug(self.rec_prompt_man.prompt_r)
        response_data = self.llm.generate_with_json_output(
                        prompt = self.recommender_manager.prompt_r,
                        json_schema = self.recommendation_schema,
                        system_prompt = system_prompt,
                        temperature = 0.3,
                        max_tokens = 32768, 
                        tools=None)
        logger.debug(response_data)
        results = {'previous_run': previous_run, 'recommendation': response_data[0]}
        return results
        
    @action
    async def plan_run(self,
                       recommendation: str,
                       history: dict,
                       prompt_type: str='') -> str:
        """
        Generate a useful config for the next_task.
        - recommendation['next_task'], recommendation['rationale'], prompt_type, history ---> prompt_manager --> agent_prompt_manager
        - previous_run, agent_prompt_manager.prompt_c ---> recommendation_prompt + rec_schema ---> llm ---> recommendation

        Args:
            results
        Returns:
            Generated recommendation
        """
        logger.debug(history)
        ### TO-DO: fix prompts so that they use the new simpler recommendation format ('next_task' and 'rationale')
        logger.debug(f"{recommendation['recommendation']['next_task']}")
        agent_prompt_manager = get_prompt_manager(
                                    agent_type=recommendation['recommendation']['next_task'],
                                    research_goal = self.research_goal,
                                    input_json = recommendation,
                                    target_prot = self.target_protein,
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
