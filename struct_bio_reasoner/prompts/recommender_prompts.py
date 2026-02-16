import json
import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RecommenderPromptManager(BaseModel):
    research_goal: str
    enabled_agents: list[str]

    prompt_r: str | None = Field(default=None, exclude=True)

    def recommend_prompt(self,
                    previous_run,
                    previous_conclusion,
                    history
                    ):
        history_str = json.dumps(history, indent=2, default=str)
        base_prompt = (
            f"You are an AI co-scientist specializing in recommending the next run {self.enabled_agents} to perform based on previous conclusions.\n\n"
            f"Research goal:\n{self.research_goal}\n\n"
        )

        base_prompt += (
                f"Please base this recommendation on previous run + conclusion and history.\n\n"
                f"Previous run type: {previous_run}\n\n"
                f"Previous run conclusion: {previous_conclusion}\n\n"
                f"History: {history_str}\n\n"
                "Your recommendation must include:\n\n"
                f"1. **Next run suggestion:**\n"
                f"2. **Next run parameters:**\n"
                f"   - Should parameters: change, not change (in those exact words)\n"
                f"2. **Rationale for the run choice:**\n"
                f"   - Why should I make this run choice and change or not change params"
            )

        self.prompt_r = base_prompt
        return base_prompt
