"""Starting (bootstrap) task prompts."""

from struct_bio_reasoner.prompts._registry import TaskDef, PromptContext


class StartingTask(TaskDef):
    name = "starting"

    def running(self, ctx: PromptContext) -> str:
        return ""

    def conclusion(self, ctx: PromptContext) -> str:
        return """This is to initialize the workflow.
Please recommend 'computational_design' as the initial run and recommend few rounds (1/2)
and to start at a default in the research goal"""
