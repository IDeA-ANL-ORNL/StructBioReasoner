import json
import asyncio
import logging
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from dataclasses import dataclass
logger = logging.getLogger(__name__)

@dataclass
class RecommenderPromptManager():
    research_goal: str
    enabled_agents: list[str] = ['computational_design', 'molecular_dynamics', 'rag', 'analysis', 'free_energy', 'stop']
    def __post_init__(self):
        self.prompt_r = None
    def recommend_prompt(self, 
                    previous_run,
                    previous_conclusion,
                    ):
        base_prompt = (
            f"You are an AI co-scientist specializing in recommending the next run {self.enabled_agents} to perform based on previous conclusions.\n\n"
            f"Research goal:\n{self.research_goal}\n\n"
        )

        base_prompt += (
                f"Please base this recommendation on previous run + conclusions.\n\n"
                f"Previous run type: {previous_run}\n\n"
                f"Previous run conclusion: {previous_conclusion}\n\n"
                "Your recommendation must include:\n\n"
                f"1. **Next run suggestion:**\n"
                f"2. **Next run parameters:**\n"
                f"   - Should paramaters: change, not change (in those exact words)\n"
                f"2. **Rationale for the run choice:**\n"
                f"   - Why should I make this run choice and change or not change params"
            )

        self.prompt_r = base_prompt
        return base_prompt
