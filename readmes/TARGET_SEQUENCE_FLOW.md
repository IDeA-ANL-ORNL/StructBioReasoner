# Target Sequence Data Flow

## 🔄 Complete Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ USER                                                                 │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ research_goal = """
                              │   Design binders for spike protein.
                              │   Target sequence: NITNLCPFGEVFNATR...
                              │ """
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ BinderDesignSystem.generate_protein_hypothesis()                    │
│                                                                      │
│ STEP 1: Extract sequences                                           │
│   target_seq = _extract_target_sequence(research_goal)              │
│   Result: "NITNLCPFGEVFNATR..." ✅                                  │
│                                                                      │
│ STEP 2: Set research_plan_config                                    │
│   generation_agent.memory.metadata['research_plan_config'] = {      │
│       'target_sequence': "NITNLCPFGEVFNATR...",                     │
│       'binder_sequence': "",                                        │
│       'task_type': 'binder_design'                                  │
│   }                                                                  │
│                                                                      │
│ STEP 3: Generate hypothesis                                         │
│   base_hypothesis = generate_single_hypothesis(strategy)            │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ GenerationAgent._generate_hypothesis()                              │
│                                                                      │
│ Get config from memory:                                             │
│   plan_config = memory.metadata.get('research_plan_config', {})    │
│   Result: {                                                         │
│       'target_sequence': "NITNLCPFGEVFNATR...",                     │
│       'binder_sequence': "",                                        │
│       'task_type': 'binder_design'                                  │
│   } ✅                                                              │
│                                                                      │
│ Extract target sequence:                                            │
│   target_seq = plan_config.get('target_sequence', 'UNKNOWN')       │
│   Result: "NITNLCPFGEVFNATR..." ✅                                  │
│                                                                      │
│ Create LLM prompt:                                                  │
│   "This is a BINDER DESIGN task.                                    │
│    Target sequence: NITNLCPFGEVFNATR...                             │
│    Propose 3-5 peptide binders..."                                  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ LLM (OpenAI/Anthropic)                                              │
│                                                                      │
│ Receives prompt with actual target sequence ✅                      │
│                                                                      │
│ Returns JSON:                                                       │
│   {                                                                 │
│     "hypothesis": {...},                                            │
│     "binder_data": {                                                │
│       "target_name": "SARS-CoV-2 spike protein RBD",                │
│       "target_sequence": "NITNLCPFGEVFNATR...", ✅                  │
│       "proposed_peptides": [                                        │
│         {                                                           │
│           "sequence": "MKTAYIAKQRQISFVK...",                        │
│           "source": "literature:PMID12345",                         │
│           "rationale": "...",                                       │
│           "peptide_id": "pep_001"                                   │
│         },                                                          │
│         ...                                                         │
│       ]                                                             │
│     }                                                               │
│   }                                                                 │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ GenerationAgent creates ResearchHypothesis                          │
│                                                                      │
│   metadata = {                                                      │
│     "binder_data": {                                                │
│       "target_sequence": "NITNLCPFGEVFNATR...", ✅                  │
│       ...                                                           │
│     }                                                               │
│   }                                                                 │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ BinderDesignSystem converts to ProteinHypothesis                    │
│                                                                      │
│   ProteinHypothesis.from_unified_hypothesis()                       │
│     → Extracts binder_data from metadata                            │
│     → Creates BinderHypothesisData object                           │
│                                                                      │
│   Result:                                                           │
│     hypothesis.binder_data.target_sequence = "NITNLCPFGEVFNATR..." ✅│
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ USER receives ProteinHypothesis                                     │
│                                                                      │
│   binder_data = hypothesis.get_binder_data()                        │
│   print(binder_data.target_sequence)                                │
│   → "NITNLCPFGEVFNATR..." ✅                                        │
│                                                                      │
│   NOT "UNKNOWN" anymore! 🎉                                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔴 Before Fix (BROKEN)

```
USER
  │ research_goal (contains target sequence)
  ▼
BinderDesignSystem.generate_protein_hypothesis()
  │ ❌ Does NOT extract target sequence
  │ ❌ Does NOT set research_plan_config
  ▼
GenerationAgent._generate_hypothesis()
  │ plan_config = memory.metadata.get('research_plan_config', {})
  │ Result: {} (empty!) ❌
  │
  │ target_seq = plan_config.get('target_sequence', 'UNKNOWN')
  │ Result: 'UNKNOWN' ❌
  ▼
LLM Prompt:
  "Target sequence: UNKNOWN" ❌
  ▼
LLM Response:
  binder_data.target_sequence = "UNKNOWN" ❌
  ▼
USER receives:
  hypothesis.binder_data.target_sequence = "UNKNOWN" ❌
```

---

## 🟢 After Fix (WORKING)

```
USER
  │ research_goal (contains target sequence)
  ▼
BinderDesignSystem.generate_protein_hypothesis()
  │ ✅ Extracts: target_seq = "NITNLCPFGEVFNATR..."
  │ ✅ Sets: research_plan_config = {'target_sequence': "NITNLCPFGEVFNATR..."}
  ▼
GenerationAgent._generate_hypothesis()
  │ plan_config = memory.metadata.get('research_plan_config', {})
  │ Result: {'target_sequence': "NITNLCPFGEVFNATR..."} ✅
  │
  │ target_seq = plan_config.get('target_sequence', 'UNKNOWN')
  │ Result: "NITNLCPFGEVFNATR..." ✅
  ▼
LLM Prompt:
  "Target sequence: NITNLCPFGEVFNATR..." ✅
  ▼
LLM Response:
  binder_data.target_sequence = "NITNLCPFGEVFNATR..." ✅
  ▼
USER receives:
  hypothesis.binder_data.target_sequence = "NITNLCPFGEVFNATR..." ✅
```

---

## 🔑 Key Points

### The Critical Link

The **`research_plan_config`** in GenerationAgent's memory is the critical link:

```python
# This is what was missing before:
generation_agent.memory.metadata['research_plan_config'] = {
    'target_sequence': "NITNLCPFGEVFNATR...",
    'binder_sequence': "",
    'task_type': 'binder_design'
}
```

### Why It Matters

1. **GenerationAgent** reads `research_plan_config` to build LLM prompts
2. **LLM** receives the target sequence in the prompt
3. **LLM** returns binder data with the correct target sequence
4. **User** gets a hypothesis with the actual target sequence

### The Fix

**Before:** `research_plan_config` was never set → LLM got "UNKNOWN"

**After:** `research_plan_config` is set with extracted sequence → LLM gets actual sequence

---

## 📍 Code Locations

### Where Extraction Happens
**File:** `struct_bio_reasoner/core/binder_design_system.py`
**Method:** `_extract_target_sequence()` (line 290)

### Where Config is Set
**File:** `struct_bio_reasoner/core/binder_design_system.py`
**Method:** `generate_protein_hypothesis()` (line 394-406)

### Where Config is Read
**File:** `../Jnana/jnana/protognosis/agents/specialized_agents.py`
**Method:** `_generate_hypothesis()` (line 69)

### Where LLM Prompt is Built
**File:** `../Jnana/jnana/protognosis/agents/specialized_agents.py`
**Methods:** 
- `_create_literature_exploration_prompt()` (line 493)
- `_create_scientific_debate_prompt()` (line 557)
- `_create_assumptions_identification_prompt()` (line 605)
- `_create_research_expansion_prompt()` (line 652)

---

## 🎯 Summary

**The fix ensures the target sequence flows correctly from user input → LLM prompt → LLM response → final hypothesis.**

**No more "UNKNOWN" target sequences!** 🎉

