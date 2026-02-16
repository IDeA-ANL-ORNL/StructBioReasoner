"""RAG (HiPerRAG) task prompts."""

from struct_bio_reasoner.prompts._registry import TaskDef, PromptContext


class RAGTask(TaskDef):
    name = "rag"

    def running(self, ctx: PromptContext) -> str:
        if ctx.prompt_type == 'hotspot_discovery':
            return f"""Given this research goal:
{ctx.research_goal}
Generate an optimal prompt for a literature mining system (HiPerRAG) to identify:
1. Key proteins that physically interact with {ctx.target_prot}
2. Proteins involved in cellular pathways
3. Proteins where disrupting the {ctx.target_prot} interaction could have therapeutic benefit.

The prompt should request structured output in JSON format with:
- interacting_protein_name: string
- interacting_protein_uniprot_id: string
- cellular_pathway: string
- interaction_type: string (e.g., "direct binding", "complex formation")
- therapeutic_rationale: string

Return ONLY the optimized prompt text, no additional explanation."""

        # binder_design (default)
        return f"""Given this research goal:
{ctx.research_goal}
Generate an optimal prompt for literature mining using HiPerRAG to identify:
    starting binders for bindcraft optimization.
    If clinical evidence available use clinically relevant starting peptide
    otherwise use one of the default scaffolds for affibody/affitin/nanobody
    provided in the research goal or best binders in the input_json {ctx.input_json}.
    Focus on returning a single peptide amino acid sequence and rationale for this in a json with these keys:
     - binder_sequence: string
     - rationale: string"""

    def conclusion(self, ctx: PromptContext) -> str:
        return f"""Using hiper-rag output {ctx.input_json} clean up and return as json with the following information cleanly:
- interacting_protein_name: string
- interacting_protein_uniprot_id: string
- cellular_pathway: string
- interaction_type: string (e.g., "direct binding", "complex formation")
- therapeutic_rationale: string"""
