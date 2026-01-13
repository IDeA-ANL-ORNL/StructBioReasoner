# LLM Reasoner Hypothesis Generation with Tool Calling Workflow

This document provides a comprehensive overview of the hypothesis generation workflow in StructBioReasoner, including the two-step tool calling approach for integrating computational design tools.

---

## 📊 Visual Workflow

See the Mermaid diagram in this directory for a complete visual representation of the workflow.

---

## 🔄 Complete Workflow Overview

### Phase 1: Initialization & Configuration

**Entry Point**: User calls `BinderDesignSystem.generate_protein_hypothesis(research_goal, strategy)`

**Key Functions**:
1. **`BinderDesignSystem.set_research_goal(research_goal)`**
   - Location: `struct_bio_reasoner/core/binder_design_system.py`
   - Extracts target and binder sequences from research goal
   - Creates session in Jnana framework

2. **`BinderDesignSystem._extract_target_sequence(research_goal)`**
   - Location: `struct_bio_reasoner/core/binder_design_system.py` (line 434)
   - Parses research goal to find target protein sequence
   - Returns sequence string or default

3. **Set `research_plan_config` in GenerationAgent memory**
   - Location: `struct_bio_reasoner/core/binder_design_system.py` (lines 460-487)
   - Injects config into all GenerationAgent instances via `coscientist.supervisor.agents`
   - Config structure:
     ```python
     research_plan_config = {
         'target_sequence': 'NITNLCP...',
         'binder_sequence': 'DPIQMGN...',
         'task_type': 'binder_design'
     }
     ```

---

### Phase 2: Strategy Selection & Prompt Building

**Available Strategies**:
- `literature_exploration` - Search literature for known binders
- `scientific_debate` - Multi-perspective analysis
- `assumptions_identification` - Identify key assumptions
- `research_expansion` - Build on existing hypotheses
- `binder_gen` - Specialized binder design strategy

**Key Functions**:

Each strategy has a dedicated prompt builder in `../Jnana/jnana/protognosis/agents/specialized_agents.py`:

1. **`_create_literature_exploration_prompt(research_goal, plan_config, is_binder_design)`**
   - Line: ~493
   - Builds prompt for literature-based hypothesis generation
   - Includes target_sequence from `plan_config`

2. **`_create_scientific_debate_prompt(research_goal, plan_config, is_binder_design)`**
   - Line: ~557
   - Creates multi-perspective debate prompt

3. **`_create_assumptions_identification_prompt(research_goal, plan_config, is_binder_design)`**
   - Line: ~605
   - Identifies key assumptions in the research

4. **`_create_research_expansion_prompt(research_goal, plan_config, is_binder_design)`**
   - Line: ~652
   - Expands on existing hypotheses

5. **`_create_binder_gen_prompt(research_goal, plan_config, is_binder_design)`**
   - Specialized prompt for binder design tasks

**Prompt Structure** (for binder design):
```
Research Goal: {research_goal}

Target Protein Sequence: {target_sequence}
Binder Sequence (if available): {binder_sequence}

Task: Generate a hypothesis for designing peptide binders...

Output Format (JSON):
{
  "hypothesis": {...},
  "binder_data": {
    "target_sequence": "...",
    "proposed_peptides": [
      {
        "sequence": "...",
        "source": "literature" | "homology" | "de-novo",
        "rationale": "...",
        "confidence_score": 0.0-1.0
      }
    ],
    "literature_references": [...]
  }
}
```

---

### Phase 3: STEP 1 - Generate Initial Hypothesis (Structured JSON)

**Key Function**: `GenerationAgent._generate_hypothesis()`
- Location: `../Jnana/jnana/protognosis/agents/specialized_agents.py` (lines 175-265)

**Process**:

1. **Check for tool registry**
   ```python
   tools = None
   if self.tool_registry and is_binder_design:
       tool_schemas = self.tool_registry.get_tool_schemas()
       if tool_schemas:
           tools = tool_schemas
   ```

2. **Call LLM with structured JSON output**
   ```python
   response_data = self.llm.generate_with_json_output(
       prompt,
       schema,
       system_prompt=system_prompt,
       tools=tools  # Logged but not used in json_object mode
   )
   ```
   - **Important**: OpenAI API limitation - cannot use both `response_format: {type: "json_object"}` and `tools` parameter simultaneously
   - This is why we need a two-step approach!

3. **Parse LLM response**
   ```python
   response = {
       "hypothesis": {
           "title": "...",
           "content": "...",
           "summary": "...",
           "key_novelty_aspects": [...],
           "testable_predictions": [...]
       },
       "binder_data": {
           "target_sequence": "NITNLCP...",
           "proposed_peptides": [
               {
                   "sequence": "DPIQMGN...",
                   "source": "literature",
                   "rationale": "Based on PMID:12345...",
                   "confidence_score": 0.85
               }
           ],
           "literature_references": [...]
       },
       "generation_strategy": "literature_exploration",
       "explanation": "..."
   }
   ```

4. **Create metadata dictionary**
   ```python
   metadata = {
       "title": response["hypothesis"]["title"],
       "key_novelty_aspects": response["hypothesis"]["key_novelty_aspects"],
       "testable_predictions": response["hypothesis"]["testable_predictions"],
       "generation_strategy": response["generation_strategy"],
       "explanation": response["explanation"]
   }
   
   if "binder_data" in response:
       metadata["binder_data"] = response["binder_data"]
   ```

---

### Phase 4: STEP 2 - Ask LLM About Tool Usage (Function Calling)

**Key Function**: `GenerationAgent._call_tools_if_needed()`
- Location: `../Jnana/jnana/protognosis/agents/specialized_agents.py` (lines 330-428)

**Process**:

1. **Build tool decision prompt**
   ```python
   tool_decision_prompt = f"""
   You have generated a hypothesis for: {research_goal}
   
   Target protein sequence: {target_sequence[:100]}...
   
   You proposed {len(proposed_peptides)} peptide sequences from literature/homology/de-novo design.
   
   **Question**: Would you like to use computational design tools to generate additional binder sequences?
   
   Available tools:
   - bindcraft_design: Uses ProteinMPNN to computationally design binders for the target protein
   
   If you want to use computational design, call the bindcraft_design tool with appropriate parameters.
   If you're satisfied with the literature-based sequences, you don't need to call any tools.
   """
   ```

2. **Call LLM with function calling support**
   ```python
   tool_response = self.llm.generate_with_tools(
       prompt=tool_decision_prompt,
       tools=tools,  # BindCraft tool schema
       system_prompt="You are a computational biologist deciding whether to use computational tools.",
       temperature=0.3,
       max_tokens=500
   )
   ```

3. **Check LLM decision**
   ```python
   tool_calls = tool_response.get('tool_calls', [])
   
   if not tool_calls:
       # LLM decided NOT to use tools
       logger.info("❌ LLM decided NOT to use computational tools")
       return []
   
   # LLM decided to USE tools
   logger.info(f"✅ LLM DECIDED TO USE COMPUTATIONAL TOOLS! Requested {len(tool_calls)} tool call(s)")
   ```

4. **Parse tool calls**
   ```python
   for tool_call in tool_calls:
       tool_name = tool_call['name']  # 'bindcraft_design'
       tool_args = tool_call['arguments']  # {target_sequence, num_sequences, ...}
   ```

---

### Phase 5: Execute Tool Calls

**Key Functions**:

1. **`ToolRegistry.execute_tool(tool_name, **arguments)`**
   - Location: `../Jnana/jnana/tools/tool_registry.py` (lines 45-60)
   - Routes tool call to appropriate tool wrapper

2. **`BindCraftTool.execute(**kwargs)`**
   - Location: `../Jnana/jnana/tools/bindcraft_tool.py` (lines 113-170)
   
   **Process**:
   
   a. **Merge config defaults with tool call arguments**
      ```python
      # Get config defaults
      config_device = self.config_defaults.get('device', 'cuda:0')
      config_if_kwargs = self.config_defaults.get('if_kwargs', {})
      
      # Tool call parameters override config defaults
      task_params = {
          "target_sequence": kwargs.get("target_sequence"),
          "device": kwargs.get("device", config_device),  # Override priority
          "mpnn_model": kwargs.get("mpnn_model", config_if_kwargs.get('model_name', 'v_48_020')),
          "mpnn_weights": kwargs.get("mpnn_weights", config_if_kwargs.get('model_weights', 'soluble_model_weights')),
          "proteinmpnn_path": kwargs.get("proteinmpnn_path", config_if_kwargs.get('proteinmpnn_path', '...')),
          ...
      }
      ```
   
   b. **Call BindCraftAgent**
      ```python
      result = await self.bindcraft_agent.run_design_cycle(task_params)
      ```

3. **`BindCraftAgent.run_design_cycle(task_params)`**
   - Location: `struct_bio_reasoner/agents/computational_design/bindcraft_agent.py`
   
   **BindCraft Workflow**:
   1. Initialize Chai folding backend
   2. Initialize ProteinMPNN inverse folding
   3. Launch agents via Academy Manager:
      - ForwardFoldingAgent
      - InverseFoldingAgent
      - QualityControlAgent
      - AnalysisAgent
   4. Launch PeptideDesignCoordinator
   5. Run design-fold-filter rounds
   6. Return results with top sequences

4. **`BindCraftTool._format_results(raw_result)`**
   - Location: `../Jnana/jnana/tools/bindcraft_tool.py` (lines 190-247)
   - Extracts top 5 sequences
   - Formats for LLM consumption
   
   **Result Structure**:
   ```python
   {
       "success": True,
       "num_sequences_generated": 25,
       "num_passing_filters": 10,
       "best_energy": -45.2,
       "rounds_completed": 1,
       "top_sequences": [
           {
               "sequence": "MKQHKAM...",
               "plddt": 85.3,
               "pae": 12.1,
               "energy": -45.2
           },
           ...
       ],
       "summary": "BindCraft generated 25 sequences..."
   }
   ```

---

### Phase 6: Incorporate Tool Results

**Location**: `GenerationAgent._generate_hypothesis()` (lines 230-264)

**Process**:

1. **Add tool-generated peptides to metadata**
   ```python
   for result in tool_results:
       if result.get("success") and result.get("top_sequences"):
           for seq_data in result["top_sequences"]:
               metadata["binder_data"]["proposed_peptides"].append({
                   "sequence": seq_data["sequence"],
                   "source": "computational:bindcraft",  # ← Key identifier!
                   "rationale": f"Generated by BindCraft with pLDDT={seq_data.get('plddt')}, pAE={seq_data.get('pae')}",
                   "confidence_score": seq_data.get("plddt", 0.0) / 100.0,
                   "tool_metadata": {
                       "plddt": seq_data.get("plddt"),
                       "pae": seq_data.get("pae"),
                       "ptm": seq_data.get("ptm"),
                       "i_ptm": seq_data.get("i_ptm")
                   }
               })
   ```

2. **Set metadata flags**
   ```python
   metadata["tool_calls_made"] = True
   metadata["tool_call_count"] = len(tool_results)
   ```

---

### Phase 7: Create Final Hypothesis

**Process**:

1. **Create ResearchHypothesis**
   ```python
   hypothesis = ResearchHypothesis(
       content=response["hypothesis"]["content"],
       summary=response["hypothesis"]["summary"],
       metadata=metadata  # Contains binder_data with all peptides
   )
   ```

2. **Convert to ProteinHypothesis**
   - Location: `struct_bio_reasoner/core/binder_design_system.py` (line 505)
   ```python
   protein_hypothesis = ProteinHypothesis.from_unified_hypothesis(
       base_hypothesis,
       biological_context=biological_context
   )
   ```

3. **Return to user**

---

## 🔑 Key Implementation Details

### Config Defaults Priority

**Priority Order** (highest to lowest):
1. **LLM tool call parameters** - Explicitly provided by LLM
2. **Config file defaults** - From `config/binder_config.yaml`
3. **Hardcoded fallbacks** - In code

**Example**:
```yaml
# config/binder_config.yaml
agents:
  computational_design:
    bindcraft:
      device: 'xpu'
      num_rounds: 1
    inverse_folding:
      num_seq: 2
      model_name: "v_48_020"
      proteinmpnn_path: "/path/to/ProteinMPNN"
```

If LLM calls:
```json
{
  "target_sequence": "NITNLCP...",
  "num_sequences": 5,
  "device": "cuda:0"
}
```

Final params:
```python
{
  "num_seq": 5,              # From LLM (overrides config)
  "device": "cuda:0",        # From LLM (overrides config)
  "mpnn_model": "v_48_020",  # From config
  "proteinmpnn_path": "/path/to/ProteinMPNN"  # From config
}
```

### Tool Registry Injection

**Critical Architecture Detail**:
- Agents are stored in `coscientist.supervisor.agents`, NOT `coscientist.agents`
- Tool registry must be injected into each GenerationAgent instance
- Location: `struct_bio_reasoner/core/binder_design_system.py` (lines 292-304)

```python
if hasattr(coscientist, 'supervisor') and hasattr(coscientist.supervisor, 'agents'):
    for agent_id, agent in coscientist.supervisor.agents.items():
        if agent_id.startswith('generation'):
            agent.tool_registry = self.tool_registry
```

---

## 📝 Example Usage

```python
from struct_bio_reasoner.core.binder_design_system import BinderDesignSystem

# Initialize system
system = BinderDesignSystem(
    config_path="config/binder_config.yaml",
    jnana_config_path="config/test_jnana_config.yaml",
    enable_agents=['computational_design']
)
await system.start()

# Set research goal
research_goal = """
Design peptide binders for SARS-CoV-2 spike protein RBD.
Target sequence: NITNLCPFGEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFKCYGVSPTKLNDLCFTNVYADSFVIRGDEVRQIAPGQTGKIADYNYKLPDDFTGCVIAWNSNNLDSKVGGNYNYLYRLFRKSNLKPFERDISTEIYQAGSTPCNGVEGFNCYFPLQSYGFQPTNGVGYQPYRVVVLSFELLHAPATVCGPKKSTNLVKNKCVNF
"""
await system.set_research_goal(research_goal)

# Generate hypothesis with tool calling
hypothesis = await system.generate_protein_hypothesis(
    research_goal=research_goal,
    strategy="binder_gen"  # or "literature_exploration", etc.
)

# Check results
for peptide in hypothesis.binder_data.proposed_peptides:
    print(f"Source: {peptide['source']}")
    print(f"Sequence: {peptide['sequence']}")
    print(f"Confidence: {peptide['confidence_score']}")
    print()
```

---

## 🎯 Summary

This workflow enables:
- ✅ **LLM-driven hypothesis generation** using multiple strategies
- ✅ **Automatic tool calling** when LLM decides it's beneficial
- ✅ **Config-based defaults** with LLM override capability
- ✅ **Seamless integration** of computational and literature-based sequences
- ✅ **Full metadata preservation** throughout the pipeline

The two-step approach overcomes OpenAI API limitations while maintaining the flexibility for the LLM to decide when computational tools are needed.

