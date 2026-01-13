# Tool Calling - Current Status and Limitations

## Current Status: ✅ FULLY IMPLEMENTED (Two-Step Approach)

The tool calling feature has been **fully implemented** using a two-step approach that overcomes OpenAI API limitations!

**Update (Latest)**: The LLM can now actually call BindCraft during hypothesis generation using the two-step approach.

---

## What Works ✅

1. **Tool Registry**: Tools can be registered and managed
2. **Tool Schemas**: BindCraft tool schema is properly defined
3. **Tool Injection**: Tool registry is injected into GenerationAgents
4. **Two-Step Tool Calling**: LLM can decide to call tools and results are incorporated
5. **Tool Execution**: BindCraft is executed when LLM requests it
6. **Result Integration**: Tool results are added to hypothesis with proper metadata
7. **Explicit Tool Calls**: You can still explicitly call BindCraft after hypothesis generation

---

## How It Works ✅

**Two-Step Approach** (Overcomes OpenAI API Limitation):

**Step 1**: Generate initial hypothesis using `response_format: json_object` (no tools)
- LLM generates structured hypothesis with literature/homology/de-novo sequences
- Returns valid JSON matching hypothesis schema

**Step 2**: Ask LLM if it wants to use tools using `tools` parameter (no json_object)
- LLM receives tool schemas and can make function calls
- LLM decides whether to call BindCraft based on the hypothesis
- If yes, tool is executed and results are returned

**Step 3**: Incorporate tool results into hypothesis
- Tool-generated sequences are added to `binder_data.proposed_peptides`
- Source is marked as `"computational:bindcraft"`
- Tool metadata (pLDDT, pAE, pTM, etc.) is preserved

**Result**: Hypothesis contains BOTH literature-based AND computational sequences!

---

## The OpenAI API Limitation (Solved!)

**The Problem**: You cannot use both `tools` parameter AND `response_format: {type: "json_object"}` simultaneously.

From OpenAI docs:
> When using `response_format: {type: "json_object"}`, function calling is not supported.

**Our Solution**: Two-step approach
- Step 1 uses `response_format: json_object` (no tools)
- Step 2 uses `tools` parameter (no json_object)
- Best of both worlds!

---

## Current Behavior

When you run the pipeline with two-step tool calling:

1. ✅ Tool registry is created
2. ✅ BindCraft tool is registered
3. ✅ Tools are logged: `"Tools available for LLM: ['bindcraft_design']"`
4. ✅ **Step 1**: LLM generates initial hypothesis with literature/homology/de-novo sources
5. ✅ **Step 2**: LLM is asked if it wants to use computational tools
6. ✅ **Step 3**: If LLM calls BindCraft, tool is executed and results are incorporated
7. ✅ **Result**: Hypothesis contains sequences with source `"computational:bindcraft"`!

**Result**: The LLM can now actually call BindCraft and the hypothesis includes computational sequences!

---

## Usage

### Approach 1: Two-Step Tool Calling (NEW! ⭐ Recommended)

Let the LLM decide whether to use computational tools:

```python
# Generate hypothesis with tool calling enabled
hypothesis = await system.generate_protein_hypothesis(
    research_goal=research_goal,
    strategy="binder_gen"
)

# Check if tools were called
if hypothesis.metadata.get("tool_calls_made"):
    print(f"✓ LLM called {hypothesis.metadata['tool_call_count']} tools!")

# Hypothesis now contains both literature AND computational sequences
for peptide in hypothesis.binder_data.proposed_peptides:
    print(f"Source: {peptide['source']}")  # May include "computational:bindcraft"
```

**See `examples/example_two_step_tool_calling.py` for full example!**

### Approach 2: Explicit Calls (Still Works!)

You can still explicitly call BindCraft after hypothesis generation:

```python
# Generate hypothesis
hypothesis = await system.generate_protein_hypothesis(...)

# Explicitly call BindCraft
bindcraft_agent = system.design_agents['computational_design']
results = await bindcraft_agent.analyze_hypothesis(
    hypothesis,
    bindcraft_config
)
```

**This is the approach used in `example_full_pipeline.py` and it works great!**

### Approach 3: Hybrid (Best of Both Worlds!)

Combine both approaches:

```python
# Let LLM call tools if it wants
hypothesis = await system.generate_protein_hypothesis(
    research_goal=research_goal,
    strategy="binder_gen"
)

# Then explicitly call BindCraft for additional optimization
results = await bindcraft_agent.analyze_hypothesis(hypothesis, config)
```

---

## Implementation Details

### What Was Implemented

1. **`generate_with_tools()` method** in LLM interface
   - Added to `LLMInterface` base class
   - Implemented for `OpenAILLM` class
   - Returns tool calls made by LLM

2. **`_call_tools_if_needed()` helper** in GenerationAgent
   - Asks LLM if it wants to use tools (Step 2)
   - Executes tools via ToolRegistry
   - Formats results for incorporation

3. **Tool result integration** in `_generate_hypothesis()`
   - Adds tool-generated sequences to `binder_data.proposed_peptides`
   - Marks source as `"computational:bindcraft"`
   - Preserves tool metadata (pLDDT, pAE, pTM, i_pTM)

4. **Metadata tracking**
   - `tool_calls_made`: Boolean flag
   - `tool_call_count`: Number of tools called
   - `tool_metadata`: Metrics from BindCraft

### Code Locations

- **LLM Interface**: `../Jnana/jnana/protognosis/core/llm_interface.py`
  - Lines 99-122: `generate_with_tools()` base method
  - Lines 429-498: OpenAI implementation

- **GenerationAgent**: `../Jnana/jnana/protognosis/agents/specialized_agents.py`
  - Lines 227-259: Tool calling integration
  - Lines 329-411: `_call_tools_if_needed()` helper

- **Example**: `examples/example_two_step_tool_calling.py`

---

## Future Enhancements

### Enhancement 1: Structured Outputs API (Optional)

Use OpenAI's newer `json_schema` response format (supports both tools and structured responses):

```python
response = client.chat.completions.create(
    model="gpt-4o-2024-08-06",  # Requires this model or newer
    messages=messages,
    tools=tools,
    response_format={
        "type": "json_schema",  # New: json_schema instead of json_object
        "json_schema": {
            "name": "hypothesis_response",
            "schema": hypothesis_schema
        }
    }
)
```

**Pros**: Single-step approach, cleaner
**Cons**: Requires newer model, not all providers support it

### Enhancement 2: Multi-Tool Support

Allow LLM to call multiple tools in sequence:
- BindCraft for design
- AlphaFold for structure prediction
- MD simulation for stability
- Literature search for validation

### Enhancement 3: Tool Call History

Track all tool calls made during hypothesis generation:
- Which tools were called
- What parameters were used
- What results were returned
- How results influenced the hypothesis

---

## Recommendation

**Use the Two-Step Tool Calling Approach! ⭐**

```python
# Let the LLM decide whether to use computational tools
hypothesis = await system.generate_protein_hypothesis(
    research_goal=research_goal,
    strategy="binder_gen"
)

# Check if tools were called
if hypothesis.metadata.get("tool_calls_made"):
    print("✓ LLM used computational design!")
    # Hypothesis contains both literature AND computational sequences
```

**Benefits**:
- ✅ LLM-driven decision making
- ✅ Automatic tool calling when appropriate
- ✅ Results automatically incorporated
- ✅ Metadata preserved
- ✅ Works with OpenAI API

**Alternative**: You can still use explicit calls (Approach 2) if you want full control.

---

## What You'll See Now

When you run your pipeline with two-step tool calling:

```
INFO: Tools available for LLM: ['bindcraft_design']
INFO: 🔧 Step 2: Asking LLM if it wants to use computational tools...
INFO: ✓ LLM requested 1 tool call(s)!
INFO: Executing tool: bindcraft_design with args: {...}
INFO: Tool bindcraft_design executed: success=True
INFO: ✓ Tool calling successful! Added 1 tool-generated sequences
```

And the hypothesis will have sources like:
- `literature` (from Step 1)
- `homology` (from Step 1)
- `de-novo` (from Step 1)
- **`computational:bindcraft`** (from Step 2 tool calling!) ⭐

**This is the new behavior!** The LLM can now actually call tools and results are incorporated.

---

## Action Items

### ✅ Completed
- ✅ Implemented two-step approach
- ✅ Added `generate_with_tools()` method to LLM interface
- ✅ Added tool call handling in GenerationAgent
- ✅ Added result incorporation logic
- ✅ Created example script

### Next Steps (Optional Enhancements)
- [ ] Add support for other LLM providers (Anthropic, Gemini)
- [ ] Implement Structured Outputs API for single-step approach
- [ ] Add tool chaining support (call multiple tools in sequence)
- [ ] Add tool call history tracking
- [ ] Add more tools (MD simulation, AlphaFold, literature search)

---

## Summary

**Current State**:
- 🟢 Tool infrastructure: **COMPLETE**
- 🟢 LLM function calling: **WORKING** (Two-step approach)
- 🟢 Explicit tool calls: **WORKING PERFECTLY**
- 🟢 Result integration: **WORKING**

**What to Do**:
- ⭐ Use two-step tool calling (Approach 1) - **Recommended!**
- Or use explicit BindCraft calls (Approach 2) - Still works great!
- Or use hybrid approach (Approach 3) - Best of both worlds!

**Status**:
- ✅ Two-step approach implemented and working
- ✅ LLM can decide when to use computational tools
- ✅ Results are automatically incorporated
- ✅ Metadata is preserved

---

## Questions?

**Q: Does tool calling actually work now?**
A: Yes! The two-step approach is fully implemented and working.

**Q: Which example should I use?**
A: Use `examples/example_two_step_tool_calling.py` to see tool calling in action, or `example_full_pipeline.py` for explicit calls.

**Q: Will the LLM always call tools?**
A: No, the LLM decides whether to use tools based on the hypothesis and research goal. This is intentional!

**Q: Can I force the LLM to use tools?**
A: Use explicit calls (Approach 2) if you want guaranteed tool execution.

**Q: What if I want both?**
A: Use the hybrid approach (Approach 3) - let LLM call tools if it wants, then explicitly call for additional optimization.

**Q: Does this work with all LLM providers?**
A: Currently only OpenAI is fully implemented. Other providers will fall back to explicit calls only.

