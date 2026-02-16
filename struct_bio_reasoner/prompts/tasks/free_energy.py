"""Free energy (MM-PBSA) task prompts."""

import json

from struct_bio_reasoner.prompts._registry import TaskDef, PromptContext, serialize_history


class FreeEnergyTask(TaskDef):
    name = "free_energy"

    def running(self, ctx: PromptContext) -> str:
        return "Run free energy with default configs"

    def conclusion(self, ctx: PromptContext) -> str:
        input_json_str = json.dumps(ctx.input_json, indent=2, default=str)
        sh = serialize_history(ctx.history)

        if ctx.prompt_type == 'hotspot_discovery':
            return f"""You are an expert in evaluating free energy calculations.
Evaluate the calculations and decide which step to take next
and which simulations should be used to calculate hotspots and which should be discarded.
Results:
    {input_json_str}
This is the history of decisions (least recent first):
{sh['decisions']}
and the history of results (least recent first):
{sh['results']}
and the history of configurations (least recent first):
{sh['configurations']}.
There are a few very important items to consider encoded here:
{sh['key_items']}"""

        # binder_design (default)
        return f"""You are an expert in evaluating free energy calculations, especially as performed by MM-PBSA.
Evaluate the following results and decide whether the
current scaffold should be used in the next round of computational_design
or if a new scaffold should be accessed here.
Results:
    {input_json_str}
Inform the scaffold to use 'affibody', 'affitin', 'nanobody' or 'use_top_binders'.
Only suggest 'use_top_binders' if the previous binders produced good free energies and are improving in the workflow.
Put the next_task as 'computational_design' but suggest a new scaffold in the rationale.
This is the history of decisions (least recent first):
{sh['decisions']}
and the history of results (least recent first):
{sh['results']}
and the history of configurations (least recent first):
{sh['configurations']}.
There are a few very important items to consider encoded here:
{sh['key_items']}"""
