"""Computational design (BindCraft) task prompts."""

import json

from struct_bio_reasoner.prompts._registry import TaskDef, PromptContext, serialize_history


class ComputationalDesignTask(TaskDef):
    name = "computational_design"

    def running(self, ctx: PromptContext) -> str:
        previous_run_type = ctx.input_json.get('previous_run', 'bindcraft')
        recommendation = ctx.input_json.get('recommendation', {})

        sh = serialize_history(ctx.history)

        resource_block = ""
        if ctx.resource_summary:
            resource_block = (
                f"\nCOMPUTE RESOURCES AVAILABLE:\n{ctx.resource_summary}\n"
                f"Keep num_rounds and batch sizes within what the available "
                f"accelerators can handle concurrently.\n"
            )

        return f"""You are an expert in computational peptide design optimization. Evaluate the current optimization progress and generate the next configuration.
RECOMMENDATION FROM PREVIOUS RUN ({previous_run_type}):
Task: {recommendation.get('next_task', 'N/A')}
Rationale: {recommendation.get('rationale', 'N/A')}
{resource_block}
HISTORY OF DECISIONS (least recent first):
{sh['decisions']}

HISTORY OF RESULTS (least recent first):
{sh['results']}

HISTORY OF CONFIGURATIONS (least recent first):
{sh['configurations']}

KEY ITEMS TO CONSIDER (including best binders from each iteration + hotspot residues):
{sh['key_items']}

CRITICAL REQUIREMENTS:
1. The 'binder_sequence' field is REQUIRED - you must include a full amino acid sequence
2. Choose the binder_sequence from one of these sources:
   a) A top-performing binder from the key_items above
   b) A scaffold sequence mentioned in the research goal: {ctx.research_goal}
   c) A sequence from previous configurations that showed promise
3. The 'constraint' residues_bind indicates residues for the target protein identified based on interactome simulations/literature. Fill this if it is included in the key items to consider otherwise list as 'None'
4. All other parameters (num_rounds, batch_size, etc.) should be optimized based on previous results
5. Return ONLY the JSON configuration, no additional text

Generate the configuration now:"""

    def conclusion(self, ctx: PromptContext) -> str:
        input_json = ctx.input_json
        if hasattr(input_json, 'model_dump'):
            input_json = input_json.model_dump()

        num_rounds = input_json.get('num_rounds', 1)
        total_sequences = input_json.get('total_sequences', 10)
        passing_sequences = input_json.get('passing_sequences', 10)
        passing_structures = input_json.get('passing_structures', 10)
        top_binders = input_json.get('top_binders', {})

        if not top_binders:
            top_binders_str = 'No top binders yet since this is the beginning of the workflow. No need for changing parameters because of this.'
        else:
            top_binders_str = json.dumps(top_binders, indent=2, default=str)

        sh = serialize_history(ctx.history)

        return f"""You are an expert in computational peptide design optimization. Evaluate the current optimization progress and recommend the next task.

BINDCRAFT OPTIMIZATION RESULTS:
- Total rounds completed: {num_rounds}
- Total sequences generated: {total_sequences}
- Passing sequences: {passing_sequences}
- Passing structures: {passing_structures}
- Top 5 binders:
{top_binders_str}

HISTORY OF DECISIONS (least recent first):
{sh['decisions']}

HISTORY OF RESULTS (least recent first):
{sh['results']}

HISTORY OF CONFIGURATIONS (least recent first):
{sh['configurations']}

KEY ITEMS TO CONSIDER (best binders from each iteration) disregard rmsd column for now since it is not being measured accurately:
{sh['key_items']}

AVAILABLE NEXT STEPS:
1. computational_design - Run more BindCraft optimization rounds
2. molecular_dynamics - Validate binders with MD simulations
3. free_energy - Calculate binding free energies
4. stop - Sufficient optimization achieved

NOTE: This is a RECOMMENDATION only. The actual configuration will be generated in a separate step."""
