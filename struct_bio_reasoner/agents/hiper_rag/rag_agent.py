"""
Academy wrapper on HiperRAG to inject into StructBioReasoner workflow.

This module implements the HiperRAG pipeline as an agentic workflow
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

from jnana.core.model_manager import UnifiedModelManager

from ...data.protein_hypothesis import  ProteinHypothesis
#BinderAnalysis,
from ...core.base_agent import BaseAgent

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

from distllm.generate.prompts import IdentityPromptTemplate
from distllm.generate.prompts import IdentityPromptTemplateConfig
from distllm.rag.search import Retriever
from distllm.rag.search import RetrieverConfig
from distllm.utils import BaseConfig


logger = logging.getLogger(__name__)

class ChatAppConfig(BaseConfig):
    """Configuration for the evaluation suite."""

    rag_configs: RetrievalAugmentedGenerationConfig = Field(
        ...,
        description='Settings for this RAG application.',
    )
    save_conversation_path: Path = Field(
        ...,
        description='Directory to save the output files.',
    )

class ConversationPromptTemplate(PromptTemplate):
    """Conversation prompt template for RAG.

    Includes the entire conversation history plus the new user question,
    and optionally the retrieved context.
    """

    def __init__(self, conversation_history: list[tuple[str, str]]):
        # conversation_history is a list of (role, text)
        self.conversation_history = conversation_history

    def preprocess(
        self,
        texts: list[str],
        contexts: list[list[str]] | None = None,
        scores: list[list[float]] | None = None,
    ) -> list[str]:
        """
        Preprocess the texts before sending to the model.

        We assume `texts` has exactly one element: the latest user query.
        We build a single string that contains the entire conversation plus
        the new question. If any retrieval contexts are found, we append them.
        """
        if not texts:
            return ['']  # No user input, return empty prompt.

        # The latest user query:
        user_input = texts[0]

        # Build the conversation string
        conversation_str = ''
        for speaker, text in self.conversation_history:
            conversation_str += f'{speaker}: {text}\n'
        # Add the new user question
        conversation_str += f'User: {user_input}\nAssistant:'

        # Optionally, append retrieved context if it exists
        if contexts and len(contexts) > 0 and len(contexts[0]) > 0:
            # contexts[0] is the top-k retrieval results for this query
            conversation_str += '\n\n[Context from retrieval]\n'
            for doc in contexts[0]:
                conversation_str += f'{doc}\n'

        return [conversation_str]


class RAGAgent(Agent):
    '''
    Agent responsible for running RAG
    '''
    def __init__(self,
                config_inp):
        self.config = ChatAppConfig.from_yaml(config_inp)
        self.rag_model = self.config.rag_configs.get_rag_model()
        self.conversation_history = []

    @action
    async def rag_with_model(self,
                        user_input):
        self.conversation_history.append(('User', user_input))  
        conversation_template = ConversationPromptTemplate(
            self.conversation_history,
            )

        # Ask the RAG model to generate a response
        response_list = rag_model.generate(
            texts=[user_input],  # retrieve only on the new user input
            prompt_template=conversation_template,
            retrieval_top_k=20,
            retrieval_score_threshold=0.1,
            debug_retrieval=True,  # Enable debug mode to see retrieval details
        )
        # There's only one element in response_list
        response = response_list[0]
        
        # Add the model's response to the conversation
        self.conversation_history.append(('Assistant', response))
        

