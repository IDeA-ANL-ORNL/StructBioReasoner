"""Molecular dynamics task prompts."""

from struct_bio_reasoner.prompts._registry import TaskDef, PromptContext, serialize_history


class MolecularDynamicsTask(TaskDef):
    name = "molecular_dynamics"

    def running(self, ctx: PromptContext) -> str:
        previous_run_type = ctx.input_json.get('previous_run', 'bindcraft')
        recommendation = ctx.input_json.get('recommendation', {})
        sh = serialize_history(ctx.history)

        if ctx.prompt_type == 'hotspot_discovery':
            return f"""You are an expert in setting up molecular dynamics simulations.
Here is the previous_run_type: {previous_run_type},
and the recommendation: {recommendation.get('rationale', 'N/A')}
Also evaluate the following history and decide how long to run the simulations for here.

Instructions:
- Suggest sufficiently long simulations to explore hotspots to target interactions between {ctx.target_prot} and interacting partners. 100-1000 ns

This is the history to evaluate:
- History of decisions made by the reasoner:
    - {sh['decisions']}
- History of results (least recent first):
    - {sh['results']}
- History of configurations (least recent first):
    - {sh['configurations']}.
- Very important key items to consider:
    - {sh['key_items']}"""

        # binder_design (default)
        return f"""You are an expert in setting up molecular dynamics simulations.
Here is the previous_run_type: {previous_run_type},
and the recommendation: {recommendation.get('rationale', 'N/A')}
Evaluate the following history and decide how long to run the simulations for here.

Instructions:
- At the beginning of the workflow we should run shorter simulations (10_000 to 50_000) to test if binder design is setup correctly.
- Once enough binders (several thousand) have been identified, suggest longer simulations (1_000_000 to 2_500_000) to provide enough statistics
for hotspot analysis and free energy calculations.

This is the history to evaluate:
- History of decisions made by the reasoner:
    - {sh['decisions']}
- History of results (least recent first):
    - {sh['results']}
- History of configurations (least recent first):
    - {sh['configurations']}.
- Very important key items to consider:
    - {sh['key_items']}"""

    def conclusion(self, ctx: PromptContext) -> str:
        sh = serialize_history(ctx.history)

        if ctx.prompt_type == 'hotspot_discovery':
            return f"""You are an expert in evaluating md simulations. Evaluate the simulations and decide which ones should be used to calculate hotspots and which should be discarded.
Here is the results from the simulations:
{ctx.input_json}
Here is the history (which may include details from hiperrag about the interacting proteins):
{sh['decisions']}
and the history of results (least recent first):
{sh['results']}
and the history of configurations (least recent first):
{sh['configurations']}.
There are a few very important items to consider encoded here:
{sh['key_items']}
Please provide your decision and reasoning
and include the paths of the simulations to analyze."""

        # binder_design (default)
        return f"""You are an expert in computational peptide design optimization and md simulations.
Evaluate the current optimization progress
and decide which step to take next ('molecular_dynamics', 'analysis', 'free_energy').
Previous round results: {ctx.input_json}
This is the history of decisions (least recent first):
{sh['decisions']}
and the history of results (least recent first):
{sh['results']}
and the history of configurations (least recent first):
{sh['configurations']}.
There are a few very important items to consider encoded here:
    {sh['key_items']}
Please provide your decision and reasoning. Orient your decision process with this logic:
- if only a few simulation timesteps have been run, suggest 'molecular_dynamics' and to increase timesteps
- if sufficient timesteps have been run but analysis has not been suggested in the past few steps, suggest 'analysis' to measure rmsd, rmsf, radius of gyration and interacting residues.
- if sufficient timesteps have been run and analysis has been suggested recently, suggest 'free_energy' to run MM-PBSA to evalute free energies of binding"""
