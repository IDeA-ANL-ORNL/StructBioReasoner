"""Analysis task prompts."""

import json

from struct_bio_reasoner.prompts._registry import TaskDef, PromptContext, serialize_history


class AnalysisTask(TaskDef):
    name = "analysis"

    def running(self, ctx: PromptContext) -> str:
        recommendation = ctx.input_json.get('recommendation', {})
        previous_run_type = ctx.input_json.get('previous_run', 'molecular_dynamics')

        return f"""You are an expert in molecular dynamics analysis and understand how to interpret the results.
RECOMMENDATION FROM PREVIOUS RUN ({previous_run_type}):
Task: analyze
Rationale: {recommendation.get('rationale', 'N/A')}.
Evaluate the recommendation and decide which analysis to perform.
Analyses are structured by input type (static vs dynamic) and rigor (basic vs advanced).
Input types ('data_type'):
  static: to be performed on PDBs
  dynamic: to be performed on simulation trajectories

Rigor ('analysis_type'):
  static, basic: interface contacts
  static, advanced: not currently supported
  dynamic, basic: rmsd, rmsf, radius of gyration
  dynamic, advanced: hotspot analysis (which residues do the binders interact with the most)
  dynamic, both: rmsd, rmsf, radius of gyration, and hotspot analysis
Currently all distance_cutoffs refer to distances between alpha carbons, and have a default value of 8.0 angstroms."""

    def conclusion(self, ctx: PromptContext) -> str:
        input_json_str = json.dumps(ctx.input_json, indent=2, default=str)
        sh = serialize_history(ctx.history)

        return f"""You are an expert in evaluating md simulation analyses. Evaluate the analyses here and decide what step should be taken next.

The following analyses have generated the following statistics:
{input_json_str}

HISTORY OF DECISIONS:
{sh['decisions']}

HISTORY OF RESULTS:
{sh['results']}

HISTORY OF CONFIGURATIONS:
{sh['configurations']}

KEY ITEMS:
{sh['key_items']}

Please provide your decision and reasoning and indicate which step should be taken next. For the purpose of testing this workflow, default this to free_energy.
Rationale for each decision:
'molecular_dynamics': before progressing to free energy more simulation steps are needed to make a valid decision.
'free_energy': analysis indicates that produced binders are stable but we need further analysis to characterize binding free energy.
'computational_design': analysis indicates that the produced binders are unstable and we need to restart bindcraft with a different seed."""
