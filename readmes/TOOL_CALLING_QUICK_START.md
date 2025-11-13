# Tool Calling Quick Start Guide

## Overview

BindCraft can now be called in **two ways**:

1. **Tool Calling**: LLM decides to call BindCraft during hypothesis generation (NEW!)
2. **Explicit Call**: You explicitly call BindCraft after hypothesis generation (EXISTING)

Both approaches work and can be used together!

---

## Quick Comparison

| Feature | Tool Calling | Explicit Call |
|---------|-------------|---------------|
| **Who decides?** | LLM | You |
| **When?** | During hypothesis generation | After hypothesis generation |
| **Control** | LLM chooses parameters | You choose parameters |
| **Use case** | Let LLM make design decisions | Controlled optimization pipeline |
| **Code** | `generate_protein_hypothesis()` | `bindcraft_agent.analyze_hypothesis()` |

---

## Example Scripts

### 1. Basic Tool Calling Example

**File:** `examples/example_tool_calling.py`

```bash
# Run full example
python examples/example_tool_calling.py

# Run minimal example
python examples/example_tool_calling.py --minimal
```

**What it does:**
- Shows how LLM can call BindCraft as a tool
- Inspects results to see if tool was called
- Compares with explicit BindCraft call

### 2. Tool vs Explicit Comparison

**File:** `examples/example_tool_vs_explicit.py`

```bash
# Run all three approaches
python examples/example_tool_vs_explicit.py

# Run specific approach
python examples/example_tool_vs_explicit.py --approach 1  # Tool calling
python examples/example_tool_vs_explicit.py --approach 2  # Explicit
python examples/example_tool_vs_explicit.py --approach 3  # Hybrid
```

**What it does:**
- Demonstrates all three approaches side-by-side
- Shows when to use each approach
- Explains the differences

### 3. Existing Full Pipeline (Still Works!)

**File:** `examples/example_full_pipeline.py`

```bash
python examples/example_full_pipeline.py
```

**What it does:**
- Complete iterative optimization pipeline
- Uses explicit BindCraft calls (as before)
- 100% backward compatible

---

## Code Examples

### Approach 1: Tool Calling

```python
from struct_bio_reasoner.core.binder_design_system import BinderDesignSystem

# Initialize system
system = BinderDesignSystem(
    config_path="config/binder_config.yaml",
    jnana_config_path="config/test_jnana_config.yaml",
    enable_agents=['computational_design']
)
await system.start()

# Set research goal (mention tools to encourage LLM to use them)
research_goal = """
Design peptide binders for SARS-CoV-2 spike RBD.
Target: NITNLCPFGEVFNATR...

Please use computational design tools to generate novel binders.
"""
await system.set_research_goal(research_goal)

# Generate hypothesis - LLM may call bindcraft_design tool
hypothesis = await system.generate_protein_hypothesis(
    research_goal=research_goal,
    strategy="binder_gen"
)

# Check if tool was called
if hypothesis.has_binder_data():
    for peptide in hypothesis.binder_data.proposed_peptides:
        source = peptide.get('source', '')
        if 'computational' in source or 'bindcraft' in source:
            print("✅ LLM called the BindCraft tool!")
            break
```

### Approach 2: Explicit Call

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
research_goal = "Design peptide binders for SARS-CoV-2 spike RBD..."
await system.set_research_goal(research_goal)

# Generate hypothesis (LLM proposes literature-based sequences)
hypothesis = await system.generate_protein_hypothesis(
    research_goal=research_goal,
    strategy="binder_gen"
)

# Explicitly call BindCraft
if hypothesis.has_binder_data():
    binder_data = hypothesis.binder_data
    
    bindcraft_config = {
        "target_sequence": binder_data.target_sequence,
        "binder_sequence": binder_data.proposed_peptides[0]["sequence"],
        "num_rounds": 3,
        "num_seqs": 50,
        "sampling_temp": 0.2
    }
    
    bindcraft_agent = system.design_agents['computational_design']
    results = await bindcraft_agent.analyze_hypothesis(
        hypothesis,
        bindcraft_config
    )
    
    print(f"✅ Generated {results.total_sequences} sequences")
```

### Approach 3: Hybrid (Both!)

```python
# Generate hypothesis (LLM may call tools)
hypothesis = await system.generate_protein_hypothesis(
    research_goal=research_goal,
    strategy="binder_gen"
)

# ALSO explicitly call BindCraft for optimization
if hypothesis.has_binder_data():
    bindcraft_config = {
        "target_sequence": hypothesis.binder_data.target_sequence,
        "binder_sequence": hypothesis.binder_data.proposed_peptides[0]["sequence"],
        "num_rounds": 5,  # More rounds for optimization
        "num_seqs": 100,  # More sequences
        "sampling_temp": 0.3
    }
    
    results = await bindcraft_agent.analyze_hypothesis(
        hypothesis,
        bindcraft_config
    )
    
    # Now you have:
    # 1. Initial sequences from LLM (possibly tool-generated)
    # 2. Optimized sequences from explicit BindCraft call
```

---

## When to Use Each Approach

### Use Tool Calling When:
- ✅ You want the LLM to make design decisions
- ✅ You want to explore different design strategies
- ✅ You trust the LLM to choose appropriate parameters
- ✅ You want a more autonomous workflow

### Use Explicit Call When:
- ✅ You need precise control over parameters
- ✅ You're running a specific optimization protocol
- ✅ You want reproducible results
- ✅ You're iterating with specific parameter adjustments

### Use Hybrid When:
- ✅ You want the best of both worlds
- ✅ You want LLM reasoning + controlled optimization
- ✅ You're running complex iterative workflows
- ✅ You want to compare LLM-generated vs optimized sequences

---

## How to Encourage Tool Use

To encourage the LLM to call the BindCraft tool, include phrases like:

```python
research_goal = """
Design peptide binders for target X.

Please use computational design tools to generate novel binders.
"""

# OR

research_goal = """
Design peptide binders for target X.

Consider using BindCraft to computationally design sequences.
"""

# OR

research_goal = """
Design peptide binders for target X.

Generate both literature-based and computationally designed sequences.
"""
```

---

## Checking if Tool Was Called

```python
hypothesis = await system.generate_protein_hypothesis(...)

if hypothesis.has_binder_data():
    tool_called = False
    
    for peptide in hypothesis.binder_data.proposed_peptides:
        source = peptide.get('source', '')
        
        # Check if source indicates tool use
        if any(keyword in source.lower() for keyword in ['computational', 'bindcraft', 'tool']):
            tool_called = True
            print(f"✅ Tool was called! Source: {source}")
            break
    
    if not tool_called:
        print("📚 LLM used literature-based sequences only")
```

---

## Troubleshooting

### Tool Not Being Called?

1. **Check tool registry:**
   ```python
   if hasattr(system, 'tool_registry'):
       print(f"Tools: {system.tool_registry.list_tools()}")
   ```

2. **Check research goal:** Make sure it mentions computational design or tools

3. **Check logs:** Look for "Tools available for LLM" in logs

### Tool Call Failed?

Check logs for:
- `BindCraft tool execution failed: ...`
- `BindCraft agent not initialized`

Make sure `enable_agents=['computational_design']` is set.

---

## Summary

✅ **Tool calling is OPTIONAL** - LLM decides whether to use it
✅ **Explicit calls still work** - 100% backward compatible
✅ **Both can be used together** - Hybrid approach
✅ **No breaking changes** - Existing code works unchanged

**Try it out:**
```bash
python examples/example_tool_calling.py
python examples/example_tool_vs_explicit.py
```

For more details, see `readmes/TOOL_INTEGRATION_GUIDE.md`

