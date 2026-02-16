"""Structure prediction (CHAI) task prompts."""

import json

from struct_bio_reasoner.prompts._registry import TaskDef, PromptContext


class StructurePredictionTask(TaskDef):
    name = "structure_prediction"

    def running(self, ctx: PromptContext) -> str:
        input_json_str = json.dumps(ctx.input_json, indent=2, default=str)

        return f"""You are an expert in protein structure prediction and understand cellular/cancer pathways.
Evaluate the output from hiperrag and decide which protein complexes: ({ctx.target_prot} and interacting partners) are the most promising to fold.
The results will be a dictionary with multiple keys. The elements of each key will be a list and each value in each list is related to each other via index.
Try to focus on folding the most relevant and smallest proteins possible. The length of partner + target sequence has to be <1500 or folding will fail.
Output from hiperrag:
{input_json_str}

Make your decision based on this data:
- cancer_pathway: string
- interaction_type: string (e.g., "direct binding", "complex formation")
- therapeutic_rationale: string
- sequence length: string
Focus on returning multiple pairs of sequences (target,partner) and multiple names.

Include only sequence for target {ctx.target_prot} and sequence for interacting partner."""

    def conclusion(self, ctx: PromptContext) -> str:
        input_json_str = json.dumps(ctx.input_json, indent=2, default=str)
        history_str = json.dumps(ctx.history.model_dump(), indent=2, default=str)

        return f"""You are an expert in evaluating folded structures. Evaluate which structures are the most promising for simulation and which ones should be discarded.

The following structures have been generated including path (which describes the interacting protein name + chai score):
{input_json_str}

Here is the history (which may include details from hiperrag about the interacting proteins):
{history_str}

Please provide your decision and reasoning and include the paths of the structures to keep.
Also include the root_output_path and steps for the simulation. Right now we are running some short simulations (100000 steps) to test the waters."""
