import json
import asyncio
import logging
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from dataclasses import dataclass
logger = logging.getLogger(__name__)

config_master = {
    'rag': {'prompt': 'string'},
    'bindcraft': {'num_rounds': 'int',
                     'batch_size': 'int', 
                     'max_retries': 'int', 
                     'sampling_temp': 'float', 
                     'qc_kwargs': {'max_repeat': 'int', 
                                   'max_appearance_ratio': 'float', 
                                   'max_charge': 'int', 
                                   'max_charge_ratio': 'float', 
                                   'max_hydrophobic_ratio': 'float', 
                                   'min_diversity': 'int'}},
    'chai': {'sequences_to_fold': 'list[list[str]', 'interacting_protein_name': 'list[str]'},
    'mdagent': {'paths_to_simulate': 'list[str]'},
    'hotspot': {'paths_to_analyze': 'list[int]'},
    'free_energy': {''}
}


# Create empty PromptManager class as a template and define other classes to inherit from it
class PromptManager:
    def __init__(self, prompt_file: Union[str, Path]):
        pass

@dataclass
class RAGPromptManager():
    research_goal: str
    input_json: dict[str, Any]
    target_prot: str
    def __post_init__(self):
        self.prompt_r = self.running_prompt()
        self.prompt_c = self.conclusion_prompt()
    def running_prompt(self):
    # Use Jnana's LLM to generate optimal prompt for HiPerRAG
        prompt_optimization_request = f""" Given this research goal:
        {self.research_goal}
        Generate an optimal prompt for a literature mining system (HiPerRAG) to identify:
        1. Key proteins that physically interact with {self.target_prot}
        2. Proteins involved in cancer pathways
        3. Proteins where disrupting the {self.target_prot} interaction could have therapeutic benefit

        The prompt should request structured output in JSON format with:
        - interacting_protein_name: string
        - interacting_protein_uniprot_id: string
        - cancer_pathway: string
        - interaction_type: string (e.g., "direct binding", "complex formation")
        - therapeutic_rationale: string

        Return ONLY the optimized prompt text, no additional explanation with the prompt in a json format as {config_master['rag']}."""

        return prompt_optimization_request
    def conclusion_prompt(self):
       prompt =f""" Generate recommendation using verbatim from this hiper-rag output: 
       {self.input_json}""" 
       return prompt
@dataclass
class BindCraftPromptManager():
    research_goal: str
    input_json: dict[str, Any]
    target_prot: str
    prompt_type: str
    history_list : list[dict]
    num_history: int = 3
    def __post_init__(self):

        self.prompt_r = None
        self.prompt_c = None

        if self.prompt_type == 'conclusion':
            self.num_rounds = self.input_json.get('num_rounds', 1)
            self.total_sequences = self.input_json.get('total_sequences', 100)
            self.passing_sequences = self.input_json.get('passing_sequences', 0)
            self.passing_structures = self.input_json.get('passing_structures', 0)
            self.prompt_c = self.conclusion_prompt()
        elif self.prompt_type == 'running':
            self.previous_run_type = self.input_json.get('previous_run_type', 'bindcraft')
            self.recommendation = self.input_json.get('recommendation', None)
            self.prompt_r = self.running_prompt()
    def running_prompt(self):
        prompt = f"""
        You are an expert in computational peptide design optimization. Evaluate the current optimization progress and decide whether to continue optimization or proceed to validation.

        RECOMMENDATION FROM PREVIOUS RUN ({self.previous_run_type}):
        run {self.recommendation.metadata['next_task']} for this reason: {self.recommendation.metadata['rationale']}
        This is the history of decisions (least recent first):
        {self.history_list[:self.num_history] if self.history_list != [] else 'No history'}
        Please provide your decision and reasoning as a json format with the following format: {config_master['bindcraft']}"""
        return prompt

    def conclusion_prompt(self):
        prompt = f"""
        You are an expert in computational peptide design optimization. Evaluate the current optimization progress and decide which step to take next (bindcraft, md_simulation).

        BINDCRAFT OPTIMIZATION RESULTS:
        - Total rounds completed: {self.num_rounds}
        - Total sequences generated: {self.total_sequences}
        - Passing sequences: {self.passing_sequences}
        - Passing structures: {self.passing_structures}
        This is the history of decisions (least recent first):
        {self.history_list[:self.num_history]}
        Please provide your decision and reasoning."""
        return prompt


@dataclass
class CHAIPromptManager():
    research_goal: str
    input_json: list[dict]
    target_prot: str
    prompt_type: str
    history_list : list[dict]
    num_history: int = 3
    def __post_init__(self):
        self.prompt_c = None
        self.prompt_r = None
        if self.prompt_type == 'conclusion':
            self.prompt_c = self.conclusion_prompt()
        elif self.prompt_type == 'running':
            self.prompt_r = self.running_prompt()

    def running_prompt(self):
        prompt = f"""
        You are an expert in protein structure prediction and understand cellular/cancer pathways. 
        Evaluate the output from hiperrag and decide which protein complexes (self.target_prot and interacting partners) are the most promising to fold.

        Output from hiperrag:
        {self.input_json}
        Make your decision based on this data:
        - cancer_pathway: string
        - interaction_type: string (e.g., "direct binding", "complex formation")
        - therapeutic_rationale: string
        Focus on returning the interacting protein name and the list of lists of sequences (target,partner) as a json with the following format:
        {config_master['chai']}"""
        return prompt

    def conclusion_prompt(self):
        prompt = f"""
        You are an expert in evaluating folded structures. Evaluate which structures are the most promising for simulation and which ones should be discarded.
        The following structures have been generated including path (which describes the interacting protein name + chai score):
        {self.input_json}
        Here is the history (which may include details from hiperrag about the interacting proteins):
        {self.history_list[:self.num_history]}
        Please provide your decision and reasoning and include the paths of the structures to keep in the format {config_master['mdagent']}."""
        return prompt
    
@dataclass
class MDPromptManager():
    research_goal: str
    input_json: dict[str, Any]
    target_prot: str
    prompt_type: str
    history_list : list[dict]
    num_history: int = 3
    def __post_init__(self):
        self.prompt_c = self.conclusion_prompt()
        self.prompt_r = None
    def running_prompt(self):
        pass

    def conclusion_prompt(self):
        if self.prompt_type == 'interactome_simulation':
            prompt = f"""
            You are an expert in evaluating md simulations. Evaluate the simulations and decide which ones should be used to calculate hotspots and which should be discarded.
            Here is the results from the simulations:
            {self.input_json}
            Here is the history (which may include details from hiperrag about the interacting proteins):
            {self.history_list[:self.num_history]}
            Please provide your decision and reasoning and include the paths of the simulations to analyze in the format {config_master['mdagent']}."""
        elif self.prompt_type == 'binder_design':
            prompt = f"""
            You are an expert in computational peptide design optimization and md simulations. Evaluate the current optimization progress and decide which step to take next (bindcraft, md_simulation, free energy simulations).
            Previous round results: {self.input_json}
            This is the history of decisions (least recent first):
            {self.history_list[:self.num_history]}
            Please provide your decision and reasoning."""

@dataclass
class FreeEnergyPromptManager():
    research_goal: str
    input_json: dict[str, Any]
    target_prot: str
    prompt_type: str
    history_list : list[dict]
    num_history: int = 3
    def __post_init__(self):
        pass
        #if self.prompt_type == 'interactome_simulation' or self.prompt_type == 'binder_design':
        #    self.previous_run_type = self.input_json.get('previous_run_type', 'bindcraft')
        #    self.recommendation = self.input_json.get('recommendation', 'string')

    def running_prompt(self):
        pass

    def conclusion_prompt(self):
        if self.prompt_type == 'interactome_simulation':
            prompt = f"""
            You are an expert in evaluating md simulations. Evaluate the simulations and decide which ones should be used to calculate hotspots and which should be discarded.
            Here is the results from the simulations:
            {self.input_json}
            Here is the history (which may include details from hiperrag about the interacting proteins):
            {self.history_list[:self.num_history]}
            Please provide your decision and reasoning and include the paths of the simulations to analyze in the format {config_master['mdagent']}."""
        elif self.prompt_type == 'binder_design':
            prompt = f"""
            You are an expert in computational peptide design optimization and md simulations. Evaluate the current optimization progress and decide which step to take next (bindcraft, md_simulation, free energy simulations).
            Previous round results: {self.input_json}
            This is the history of decisions (least recent first):
            {self.history_list[:self.num_history]}
            Please provide your decision and reasoning."""


# I want to make a factory class that can generate the right prompt manager based on the agent type
def get_prompt_manager(agent_type: str, research_goal: str, input_json: dict[str, Any] | list[dict], target_prot: str, prompt_type: str, history_list: list[dict], num_history: int = 3):
    if agent_type == 'rag':
        return RAGPromptManager(research_goal, input_json, target_prot)
    elif agent_type == 'bindcraft':
        return BindCraftPromptManager(research_goal, input_json, target_prot, prompt_type, history_list, num_history)
    elif agent_type == 'chai':
        return CHAIPromptManager(research_goal, input_json, target_prot, prompt_type, history_list, num_history)
    elif agent_type == 'mdagent':
        return MDPromptManager(research_goal, input_json, target_prot, prompt_type, history_list, num_history)

        
        
