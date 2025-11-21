# Tool Integration Guide: BindCraft as LLM-Callable Tool

## Overview

This guide explains how BindCraft computational design has been integrated as a **tool** that LLM agents in Jnana can call during hypothesis generation. This is **optional** and **backward compatible** - the existing pipeline in `examples/example_full_pipeline.py` continues to work unchanged.

---

## 📊 Complete Workflow Documentation

For a comprehensive visual workflow with detailed function calls and step-by-step process, see:
- **[HYPOTHESIS_GENERATION_WORKFLOW.md](./HYPOTHESIS_GENERATION_WORKFLOW.md)** - Complete workflow documentation with Mermaid diagrams showing:
  - All 5 hypothesis generation strategies
  - Two-step tool calling approach
  - Config defaults and override mechanism
  - Complete function call sequence

This document provides a high-level overview of the tool integration architecture.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Jnana CoScientist                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  GenerationAgent (LLM)                                │  │
│  │                                                        │  │
│  │  "I need to design binders for SARS-CoV-2...          │  │
│  │   Let me call bindcraft_design tool"                  │  │
│  └────────────────────┬──────────────────────────────────┘  │
│                       │                                      │
│                       │ Tool Call (Optional)                 │
│                       ▼                                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │         Tool Registry                                 │  │
│  │  - bindcraft_design                                   │  │
│  └────────────────────┬──────────────────────────────────┘  │
└────────────────────────┼─────────────────────────────────────┘
                         │
                         │ Execute
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              StructBioReasoner                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │         BindCraftAgent                                │  │
│  │  - run_design()                                  .       │
│  │  - Returns: sequences, structures, metrics            │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## How It Works

### 1. Tool Registration (Automatic)

When `BinderDesignSystem` starts, it automatically:
1. Creates a `ToolRegistry`
2. Wraps `BindCraftAgent` in a `BindCraftTool`
3. Registers the tool
4. Injects the registry into all GenerationAgents

**Code:** `struct_bio_reasoner/core/binder_design_system.py` lines 272-310

### 2. LLM Awareness (Automatic)

When generating binder hypotheses, the LLM is informed about available tools:

```
This is a BINDER DESIGN task...

**OPTIONAL:** You have access to computational design tools:
   - bindcraft_design: Generate binders computationally using ProteinMPNN
   You can call this tool if you want to supplement literature-based sequences
   with computationally designed ones. However, you can also propose sequences
   purely from literature if you prefer.
```

**Code:** `../Jnana/jnana/protognosis/agents/specialized_agents.py` lines 548-554

### 3. Tool Execution (If LLM Chooses)

If the LLM decides to call the tool:
1. LLM generates a function call with parameters
2. `ToolRegistry.execute_tool()` is called
3. `BindCraftTool.execute()` runs the design
4. Results are formatted and returned to LLM
5. LLM incorporates results into hypothesis

**Code:** `../Jnana/jnana/tools/bindcraft_tool.py`

## Backward Compatibility

### Existing Pipeline Still Works

The existing workflow in `examples/example_full_pipeline.py` is **unchanged**:

```python
# STEP 3: Generate hypothesis (LLM may or may not call tools)
initial_hypothesis = await system.generate_protein_hypothesis(
    research_goal=research_goal,
    strategy="binder_gen"
)

# STEP 4a: Run BindCraft explicitly (as before)
bindcraft_agent = system.design_agents['computational_design']
bindcraft_results = await bindcraft_agent.analyze_hypothesis(
    current_hypothesis,
    bindcraft_config
)
```

**Key Points:**
- If LLM doesn't call the tool → hypothesis has literature-based sequences
- BindCraft is still called explicitly in STEP 4a
- Everything works exactly as before

### Two Ways to Use BindCraft

#### Option 1: LLM Calls Tool During Hypothesis Generation
```python
# LLM decides to call bindcraft_design tool
# Hypothesis includes computationally designed sequences
initial_hypothesis = await system.generate_protein_hypothesis(
    research_goal=research_goal,
    strategy="binder_gen"
)
# hypothesis.binder_data.proposed_peptides contains tool results
```

#### Option 2: Explicit Call in Pipeline (Original)
```python
# LLM proposes literature-based sequences
initial_hypothesis = await system.generate_protein_hypothesis(...)

# Explicitly run BindCraft optimization
bindcraft_results = await bindcraft_agent.analyze_hypothesis(
    current_hypothesis,
    bindcraft_config
)
```

## Tool Schema

The LLM sees this tool definition:

```json
{
  "type": "function",
  "function": {
    "name": "bindcraft_design",
    "description": "Design peptide binders for a target protein using BindCraft...",
    "parameters": {
      "type": "object",
      "properties": {
        "target_sequence": {
          "type": "string",
          "description": "Amino acid sequence of the target protein to bind"
        },
        "binder_sequence": {
          "type": "string",
          "description": "Initial binder sequence (optional, can be empty for de novo)"
        },
        "num_sequences": {
          "type": "integer",
          "description": "Number of binder sequences to generate per round",
          "default": 10
        },
        "num_rounds": {
          "type": "integer",
          "description": "Number of design-fold-filter rounds",
          "default": 1
        },
        "temperature": {
          "type": "number",
          "description": "Sampling temperature for ProteinMPNN (0.0-1.0)",
          "default": 0.1
        }
      },
      "required": ["target_sequence"]
    }
  }
}
```

## Example LLM Interaction

### Scenario: LLM Calls Tool

```
User: Design a binder for SARS-CoV-2 spike protein RBD

LLM: I'll use the bindcraft_design tool to generate novel binders.

[Tool Call: bindcraft_design]
{
  "target_sequence": "NITNLCPFGEVFNATR...",
  "num_sequences": 20,
  "temperature": 0.15
}

[Tool Result]
{
  "success": true,
  "num_sequences_generated": 20,
  "num_passing_filters": 12,
  "top_sequences": [
    {"sequence": "MKTAYIAK...", "plddt": 82.3, "energy": -45.2},
    {"sequence": "VKDLNQRT...", "plddt": 79.1, "energy": -42.8},
    ...
  ],
  "summary": "Generated 20 sequences, 12 passed filters (60% success rate)"
}

LLM: Based on the computational design results, I propose:

**Hypothesis**: The following computationally designed peptides will bind 
to SARS-CoV-2 spike RBD with high affinity:

**binder_data**:
{
  "target_name": "SARS-CoV-2 Spike RBD",
  "target_sequence": "NITNLCPFGEVFNATR...",
  "proposed_peptides": [
    {
      "sequence": "MKTAYIAK...",
      "source": "computational:bindcraft",
      "rationale": "Top-scoring design with pLDDT=82.3 and energy=-45.2",
      "peptide_id": "pep_001"
    },
    ...
  ]
}
```

## Files Modified

### New Files Created
1. `../Jnana/jnana/tools/tool_registry.py` - Tool registry infrastructure
2. `../Jnana/jnana/tools/bindcraft_tool.py` - BindCraft tool wrapper
3. `../Jnana/jnana/tools/__init__.py` - Module exports

### Files Modified
1. `../Jnana/jnana/protognosis/agents/specialized_agents.py`
   - Added `tool_registry` parameter to `GenerationAgent.__init__()`
   - Added tool availability check in `_generate_hypothesis()`
   - Added tool mention in binder design prompt

2. `struct_bio_reasoner/core/binder_design_system.py`
   - Added `_initialize_tool_registry()` method
   - Registers BindCraft tool on startup
   - Injects tool registry into CoScientist agents

## Benefits

### 1. LLM-Driven Decisions
The LLM can decide:
- "Should I design from scratch or use literature sequences?"
- "What parameters should I use based on the target?"
- "Do I need computational design for this task?"

### 2. Hybrid Approach
The LLM can:
- Propose literature-based sequences AND computationally designed sequences
- Compare both approaches in the hypothesis
- Use tool results to inform literature-based proposals

### 3. Flexible Integration
Easy to add more tools:
- `md_simulation_tool`
- `alphafold_prediction_tool`
- `literature_search_tool`

### 4. No Breaking Changes
- Existing pipeline works unchanged
- Tool usage is optional
- Backward compatible with all existing code

## Testing

Run the existing pipeline to verify backward compatibility:

```bash
python examples/example_full_pipeline.py
```

Expected behavior:
- System starts successfully
- Tool registry is initialized
- BindCraft tool is registered
- LLM generates hypothesis (may or may not call tool)
- Explicit BindCraft call in STEP 4a works as before

## Future Enhancements

1. **Full Function Calling Support**: Update LLM interface to support OpenAI-style function calling
2. **More Tools**: Add MD simulation, AlphaFold, literature search as tools
3. **Tool Chaining**: Allow LLM to call multiple tools in sequence
4. **Tool Results in Hypothesis**: Store tool call history in hypothesis metadata

## Summary

✅ BindCraft is now available as an LLM-callable tool
✅ Existing pipeline continues to work unchanged
✅ LLM can optionally use computational design during hypothesis generation
✅ Backward compatible with all existing code
✅ Foundation for adding more tools in the future

