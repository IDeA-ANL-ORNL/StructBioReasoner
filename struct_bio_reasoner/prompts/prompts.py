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

    'rag_output': {'interactions': 'list[string]',
                   'interacting_protein_uniprot_ids': 'list[string]',
                   'cancer_pathways': 'list[string]',
                   'interaction_types': 'list[string]',
                   'therapeutic_rationales': 'list[string]'},

    'computational_design': {
                    "binder_sequence": 'string',
                    'num_rounds': 'int',
                     'batch_size': 'int', 
                     'max_retries': 'int', 
                     'sampling_temp': 'float', 
                     'qc_kwargs': {'max_repeat': 'int', 
                                   'max_appearance_ratio': 'float', 
                                   'max_charge': 'int', 
                                   'max_charge_ratio': 'float', 
                                   'max_hydrophobic_ratio': 'float', 
                                   'min_diversity': 'int'}},

    'structure_prediction': {'sequences': 'list[list[str]', 'names': 'list[str]'},

    'molecular_dynamics': {'simulation_paths': 'list[str]', 'root_output_path': 'str', 'steps': 'int'},

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
    prompt_type: str
    def __post_init__(self):
        pass
        #self.prompt_r = self.running_prompt()
        #self.prompt_c = self.conclusion_prompt()
    def running_prompt(self):
    # Use Jnana's LLM to generate optimal prompt for HiPerRAG
        if self.prompt_type == 'interactome':
            prompt_optimization_request = f""" Given this research goal:
            {self.research_goal}
            Generate an optimal prompt for a literature mining system (HiPerRAG) to identify:
            1. Key proteins that physically interact with {self.target_prot}
            2. Proteins involved in cancer pathways
            3. Proteins where disrupting the {self.target_prot} interaction could have therapeutic benefit.
                Evaluate P53 binding here as well and return if relevant

            The prompt should request structured output in JSON format with:
            - interacting_protein_name: string
            - interacting_protein_uniprot_id: string
            - cancer_pathway: string
            - interaction_type: string (e.g., "direct binding", "complex formation")
            - therapeutic_rationale: string

            Return ONLY the optimized prompt text, no additional explanation with the prompt in a json format as {config_master['rag']} strip any /n characters or anything that obfuscates teh output."""

        elif self.prompt_type == 'binder_design':
            prompt_optimization_request = f""" Given this research goal:
            {self.research_goal}
            Generate an optimal prompt for literature mining using HiPerRAG to identify:
                starting binders for bindcraft optimization. If clinical evidence available use clinically relevant starting peptide otherwise use one of the default scaffolds for affibody/nanobody/affitin provided in the research goal or best binders in the input_json {input_json}.
                Focus on returning a single peptide amino acid sequence and rationale for this in a json with these keys:
                 - binder_sequence: string
                  - rationale: string """ 

        self.prompt_r = prompt_optimization_request
        return prompt_optimization_request
    def conclusion_prompt(self):
       prompt =f""" Using hiper-rag output {self.input_json} clean up and return as json with the following information cleanly: 
       - interacting_protein_name: string
       - interacting_protein_uniprot_id: string
       - cancer_pathway: string
       - interaction_type: string (e.g., "direct binding", "complex formation")
       - therapeutic_rationale: string""" 
       self.prompt_c = prompt
       return prompt

@dataclass
class BindCraftPromptManager():
    research_goal: str
    input_json: dict[str, Any]
    target_prot: str
    prompt_type: str
    history : dict
    num_history: int = 3
    def __post_init__(self):

        self.prompt_r = None
        self.prompt_c = None

        if self.prompt_type == 'conclusion':
            self.num_rounds = self.input_json.get('num_rounds', 1)
            self.total_sequences = self.input_json.get('total_sequences', 100)
            self.passing_sequences = self.input_json.get('passing_sequences', 0)
            self.passing_structures = self.input_json.get('passing_structures', 0)
            self.top_binders = self.input_json.get('top_binders', {})#dict(sorted(self.input_json['all_cycles'][self.num_rounds].items(), key=lambda x: x[1]['energy'])[:5])
            if self.top_binders == {}:
                self.top_binders == 'No top binders'
            #self.prompt_c = self.conclusion_prompt()

        elif self.prompt_type == 'running':
            self.previous_run_type = self.input_json.get('previous_run_type', 'bindcraft')
            self.recommendation = self.input_json.get('recommendation', None)
            #self.prompt_r = self.running_prompt()
    def running_prompt(self):
        # Serialize history for better LLM readability
        decisions_str = json.dumps(self.history['decisions'], indent=2, default=str) if self.history['decisions'] else 'No history'
        results_str = json.dumps(self.history['results'], indent=2, default=str) if self.history['results'] else 'No history'
        configs_str = json.dumps(self.history['configurations'], indent=2, default=str) if self.history['configurations'] else 'No history'
        key_items_str = json.dumps(self.history['key_items'], indent=2, default=str) if self.history['key_items'] else 'No key items yet'
        config_schema_str = json.dumps(config_master['computational_design'], indent=2)

        prompt = f"""
        You are an expert in computational peptide design optimization. Evaluate the current optimization progress and generate the next configuration.

        RECOMMENDATION FROM PREVIOUS RUN ({self.previous_run_type}):
        Task: {self.recommendation.metadata['next_task']}
        Rationale: {self.recommendation.metadata['rationale']}

        HISTORY OF DECISIONS (least recent first):
        {decisions_str}

        HISTORY OF RESULTS (least recent first):
        {results_str}

        HISTORY OF CONFIGURATIONS (least recent first):
        {configs_str}

        KEY ITEMS TO CONSIDER (best binders from each iteration):
        {key_items_str}

        IMPORTANT: You MUST provide a complete configuration in JSON format matching this schema:
        {config_schema_str}

        CRITICAL REQUIREMENTS:
        1. The 'binder_sequence' field is REQUIRED - you must include a full amino acid sequence
        2. Choose the binder_sequence from one of these sources:
           a) A top-performing binder from the key_items above
           b) A scaffold sequence mentioned in the research goal: {self.research_goal}
           c) A sequence from previous configurations that showed promise
        3. All other parameters (num_rounds, batch_size, etc.) should be optimized based on previous results
        4. Return ONLY the JSON configuration, no additional text

        Generate the configuration now:"""
        self.prompt_r = prompt
        return prompt

    def conclusion_prompt(self):
        # Serialize for better LLM readability
        top_binders_str = json.dumps(self.top_binders, indent=2, default=str) if self.top_binders and self.top_binders != {} else 'No top binders yet'
        decisions_str = json.dumps(self.history['decisions'], indent=2, default=str) if self.history['decisions'] else 'No history'
        results_str = json.dumps(self.history['results'], indent=2, default=str) if self.history['results'] else 'No history'
        configs_str = json.dumps(self.history['configurations'], indent=2, default=str) if self.history['configurations'] else 'No history'
        key_items_str = json.dumps(self.history['key_items'], indent=2, default=str) if self.history['key_items'] else 'No key items yet'

        prompt = f"""
        You are an expert in computational peptide design optimization. Evaluate the current optimization progress and recommend the next task.

        BINDCRAFT OPTIMIZATION RESULTS:
        - Total rounds completed: {self.num_rounds}
        - Total sequences generated: {self.total_sequences}
        - Passing sequences: {self.passing_sequences}
        - Passing structures: {self.passing_structures}
        - Top 5 binders:
        {top_binders_str}

        HISTORY OF DECISIONS (least recent first):
        {decisions_str}

        HISTORY OF RESULTS (least recent first):
        {results_str}

        HISTORY OF CONFIGURATIONS (least recent first):
        {configs_str}

        KEY ITEMS TO CONSIDER (best binders from each iteration) disregard rmsd column for now since it is not being measured accurately:
        {key_items_str}

        AVAILABLE NEXT STEPS:
        1. computational_design - Run more BindCraft optimization rounds
        2. molecular_dynamics - Validate binders with MD simulations
        3. free_energy - Calculate binding free energies
        4. stop - Sufficient optimization achieved

        Please provide your recommendation in JSON format:
        {{
            "next_task": "computational_design|molecular_dynamics|free_energy|stop",
            "rationale": "detailed explanation of why this is the best next step",
            "confidence": 0.0-1.0
        }}

        NOTE: This is a RECOMMENDATION only. The actual configuration will be generated in a separate step.
        """
        logger.info('Bindcraft conclusion prompt')
        logger.info(f'{prompt=}')
        self.prompt_c = prompt
        return prompt


@dataclass
class CHAIPromptManager():
    research_goal: str
    input_json: list[dict]
    target_prot: str
    prompt_type: str
    history : dict
    num_history: int = 3
    def __post_init__(self):
        self.prompt_c = None
        self.prompt_r = None
        #if self.prompt_type == 'conclusion':
        #    self.prompt_c = self.conclusion_prompt()
        #elif self.prompt_type == 'running':
        #    self.prompt_r = self.running_prompt()

    def running_prompt(self):
        # Serialize input_json to a formatted string for better LLM readability
        input_json_str = json.dumps(self.input_json, indent=2, default=str)
        config_str = json.dumps(config_master['structure_prediction'], indent=2)

        prompt = f"""
        You are an expert in protein structure prediction and understand cellular/cancer pathways.
        Evaluate the output from hiperrag and decide which protein complexes: ({self.target_prot} and interacting partners) are the most promising to fold.
        The results will be a dictionary with multiple keys. The elements of each key will be a list and each value in each list is related to each other via index.
        Try to focus on folding the most relevant and smallest proteins possible. The length of partner + target sequencehas to be <1500 or folding will fail. 
        Output from hiperrag:
        {input_json_str}

        Make your decision based on this data:
        - cancer_pathway: string
        - interaction_type: string (e.g., "direct binding", "complex formation")
        - therapeutic_rationale: string
        - sequence length: string
        Focus on returning multiple pairs of sequences (target,partner) and multiple names as a json with the following format:
        {config_str}

        Include only sequence for target {self.target_prot} and sequence for interacting partner."""
        self.prompt_r = prompt
        return prompt

    def conclusion_prompt(self):
        # Serialize input_json and history to formatted strings
        input_json_str = json.dumps(self.input_json, indent=2, default=str)
        history_str = json.dumps(self.history, indent=2, default=str)
        config_str = json.dumps(config_master['molecular_dynamics'], indent=2)

        prompt = f"""
        You are an expert in evaluating folded structures. Evaluate which structures are the most promising for simulation and which ones should be discarded.

        The following structures have been generated including path (which describes the interacting protein name + chai score):
        {input_json_str}

        Here is the history (which may include details from hiperrag about the interacting proteins):
        {history_str}

        Please provide your decision and reasoning and include the paths of the structures to keep in the format:
        {config_str}
        Also include the root_output_path and steps for the simulation. Right now we are running some short simulations (100000 steps) to test the waters."""
        self.prompt_c = prompt
        return prompt
    
@dataclass
class MDPromptManager():
    research_goal: str
    input_json: dict[str, Any]
    target_prot: str
    prompt_type: str
    history : dict
    num_history: int = 3
    def __post_init__(self):
        self.prompt_c = None #self.conclusion_prompt()
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
            {self.history['decisions'] if self.history['decisions'] != [] else 'No history'}
        and the history of results (least recent first):
            {self.history['results'] if self.history['results'] != [] else 'No history'}
        and the history of configurations (least recent first):
            {self.history['configurations'] if self.history['configurations'] != [] else 'No history'}.
        There are a few very important items to consider encoded here:
            {self.history['key_items']}
            Please provide your decision and reasoning and include the paths of the simulations to analyze in the format {config_master['hotspot']}."""
        elif self.prompt_type == 'binder_design':
            prompt = f"""
            You are an expert in computational peptide design optimization and md simulations. Evaluate the current optimization progress and decide which step to take next ('computational_design', 'molecular_dynamics', 'analysis', 'free_energy'). 
            Previous round results: {self.input_json}
            This is the history of decisions (least recent first):
            {self.history['decisions'] if self.history['decisions'] != [] else 'No history'}
        and the history of results (least recent first):
            {self.history['results'] if self.history['results'] != [] else 'No history'}
        and the history of configurations (least recent first):
            {self.history['configurations'] if self.history['configurations'] != [] else 'No history'}.
        There are a few very important items to consider encoded here:
            {self.history['key_items']}
            Please provide your decision and reasoning."""
        self.prompt_c = prompt
        return prompt


@dataclass
class AnalysisPromptManager():
    research_goal: str
    input_json: list[dict]
    target_prot: str
    prompt_type: str
    history : dict
    num_history: int = 3
    def __post_init__(self):
        self.prompt_c = None
        self.prompt_r = None
        #if self.prompt_type == 'conclusion':
        #    self.prompt_c = self.conclusion_prompt()
        #elif self.prompt_type == 'running':
        #    self.prompt_r = self.running_prompt()

    def running_prompt(self):
        # Serialize input_json to a formatted string for better LLM readability
        input_json_str = json.dumps(self.input_json, indent=2, default=str)
        config_str = json.dumps(config_master['structure_prediction'], indent=2)

        prompt = f"""
        You are an expert in protein structure prediction and understand cellular/cancer pathways.
        Evaluate the output from hiperrag and decide which protein complexes: ({self.target_prot} and interacting partners) are the most promising to fold.
        The results will be a dictionary with multiple keys. The elements of each key will be a list and each value in each list is related to each other via index.
        Try to focus on folding the most relevant and smallest proteins possible. The length of partner + target sequencehas to be <1500 or folding will fail. 
        Output from hiperrag:
        {input_json_str}

        Make your decision based on this data:
        - cancer_pathway: string
        - interaction_type: string (e.g., "direct binding", "complex formation")
        - therapeutic_rationale: string
        - sequence length: string
        Focus on returning multiple pairs of sequences (target,partner) and multiple names as a json with the following format:
        {config_str}

        Include only sequence for target {self.target_prot} and sequence for interacting partner."""
        self.prompt_r = prompt
        return prompt

    def conclusion_prompt(self):
        # Serialize input_json and history to formatted strings
        input_json_str = json.dumps(self.input_json, indent=2, default=str)
        history_str = json.dumps(self.history, indent=2, default=str)
        config_str = json.dumps(config_master['molecular_dynamics'], indent=2)

        prompt = f"""
        You are an expert in evaluating folded structures. Evaluate which structures are the most promising for simulation and which ones should be discarded.

        The following structures have been generated including path (which describes the interacting protein name + chai score):
        {input_json_str}

        Here is the history (which may include details from hiperrag about the interacting proteins):
        {history_str}

        Please provide your decision and reasoning and include the paths of the structures to keep in the format:
        {config_str}
        Also include the root_output_path and steps for the simulation. Right now we are running some short simulations (100000 steps) to test the waters."""
        self.prompt_c = prompt
        return prompt









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
            Please provide your decision and reasoning and include the paths of the simulations to analyze in the format {config_master['molecular_dynamics']}."""
        elif self.prompt_type == 'binder_design':
            prompt = f"""
            You are an expert in computational peptide design optimization and md simulations. Evaluate the current optimization progress and decide which step to take next (bindcraft, md_simulation, free energy simulations).
            Previous round results: {self.input_json}
            This is the history of decisions (least recent first):
            {self.history_list[:self.num_history]}
            Please provide your decision and reasoning."""


# I want to make a factory class that can generate the right prompt manager based on the agent type
def get_prompt_manager(agent_type: str, research_goal: str, input_json: dict[str, Any] | list[dict], target_prot: str, prompt_type: str, history: dict, num_history: int = 3):
    if agent_type == 'rag':
        return RAGPromptManager(research_goal, input_json, target_prot, prompt_type)
    elif agent_type == 'computational_design':
        if history == []:
            history = {'key_items': [], 'decisions': [], 'results': [], 'configurations': []}
        return BindCraftPromptManager(research_goal, input_json, target_prot, prompt_type, history, num_history)
    elif agent_type == 'structure_prediction':
        return CHAIPromptManager(research_goal, input_json, target_prot, prompt_type, history, num_history)
    elif agent_type == 'molecular_dynamics':
        return MDPromptManager(research_goal, input_json, target_prot, prompt_type, history, num_history)

        
        
