from academy import Agent, action
from pathlib import Path

class ChromaAgent(Agent):
    def __init__(self):
        super().__init__()

    @action
    def design(self,
               target_pdb: Path):
        pass
