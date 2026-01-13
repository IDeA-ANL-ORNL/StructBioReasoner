# Integration Test Guide: Jnana + StructBioReasoner

This guide explains how to test the integration between Jnana's hypothesis generation system and StructBioReasoner's binder design pipeline.

---

## 📋 Overview

The integration connects:

1. **Jnana Framework** → Hypothesis generation and iterative improvement
2. **StructBioReasoner** → Binder design execution (BindCraft + MDAgent)

**Data Flow:**
```
Jnana CoScientist
    ↓ (generates)
ResearchHypothesis with binder_data
    ↓ (converts to)
ProteinHypothesis
    ↓ (executes)
BindCraft optimization
    ↓ (validates)
MD simulations
    ↓ (evaluates)
Jnana improve_hypothesis()
    ↓ (decides)
Continue or Complete
```

---

## 🚀 Quick Start

### Step 1: Run Quick Integration Test (No LLM Required)

This test verifies that all components can be imported and key methods exist:

```bash
python test_quick_integration.py
```

**What it tests:**
- ✅ Jnana imports work
- ✅ StructBioReasoner imports work
- ✅ `improve_hypothesis()` method exists in CoScientist
- ✅ `_improve_hypothesis()` method exists in GenerationAgent
- ✅ Data structures (BinderHypothesisData, BinderAnalysis) work
- ✅ Parameter validation method exists

**Expected output:**
```
============================================================
QUICK INTEGRATION TEST
Jnana + StructBioReasoner Connection Verification
============================================================

============================================================
TEST 1: Import Verification
============================================================

1. Importing Jnana components...
   ✓ Jnana imports successful

2. Importing StructBioReasoner components...
   ✓ StructBioReasoner imports successful

✅ TEST 1 PASSED: All imports work!

...

============================================================
SUMMARY
============================================================
imports: ✅ PASSED
methods: ✅ PASSED
data_structures: ✅ PASSED
validation: ✅ PASSED

Total: 4/4 tests passed

🎉 ALL TESTS PASSED!
```

---

### Step 2: Run Full Integration Test (Requires LLM API)

This test actually calls Jnana's LLM to generate hypotheses and test improvement logic:

```bash
# Make sure you have API keys set
export ANTHROPIC_API_KEY="your-key-here"

# Run the full test
python test_jnana_structbioreasoner_integration.py
```

**What it tests:**
- ✅ Generate binder hypothesis using Jnana's CoScientist
- ✅ Verify binder data is included in hypothesis metadata
- ✅ Call `improve_hypothesis()` with mock experimental results
- ✅ Verify decision logic (continue vs complete)
- ✅ Verify parameter suggestions are within bounds
- ✅ Test conversion to ProteinHypothesis

**Expected output:**
```
================================================================================
TEST 1: Jnana Binder Hypothesis Generation
================================================================================

✓ Binder design detected: True
✓ Plan config keys: ['main_objective', 'target_sequence', 'domain', ...]

✓ Hypothesis generated: hyp_abc123
✓ Summary: Design peptide binders for SARS-CoV-2 spike protein...

✓ Binder data found!
  - Target: SARS-CoV-2 RBD
  - Target sequence length: 201
  - Proposed peptides: 3

  First peptide:
    - ID: pep_001
    - Sequence: ACDEFGHIKLMNPQRSTVWY
    - Source: Literature (PubMed:12345678)
    - Rationale: This peptide was shown to bind RBD with high affinity...

✅ TEST 1 PASSED: Hypothesis generation successful!

================================================================================
TEST 2: Improve Hypothesis with Mock Experimental Results
================================================================================

✓ Generated hypothesis: hyp_abc123

✓ Mock experimental results created:
  - BindCraft: 8/150 sequences passed
  - MD: 5/8 stable complexes
  - Success rate: 3.33%

✓ Improvement result received:
  - Decision status: continue
  - Reasoning: Success rate (3.33%) is below threshold (5.0%). Recommend...
  - Confidence: 0.85
  - Success rate: 3.33%
  - Meets threshold: False

✓ New parameters suggested:
  - num_seqs: 75
  - sampling_temp: 0.15
  - simulation_time: 50

✓ Parameters within bounds!

✅ TEST 2 PASSED: improve_hypothesis() works correctly!
```

---

## 📊 Test Details

### Test 1: Hypothesis Generation

**Purpose:** Verify Jnana can generate binder-specific hypotheses

**Research Goal:**
```
Design peptide binders for SARS-CoV-2 spike protein receptor binding domain (RBD) 
to optimize binding affinity and stability.
```

**Expected Binder Data Structure:**
```python
{
    "target_name": "SARS-CoV-2 RBD",
    "target_sequence": "NITNLCPFGEVFNATR...",
    "proposed_peptides": [
        {
            "peptide_id": "pep_001",
            "sequence": "ACDEFGHIKLMNPQRSTVWY",
            "source": "Literature (PubMed:12345678)",
            "rationale": "This peptide was shown to bind..."
        }
    ],
    "literature_references": ["doi:10.1234/example"],
    "binding_affinity_goal": "< 10 nM",
    "clinical_context": "Therapeutic antibody development"
}
```

---

### Test 2: Improve Hypothesis

**Purpose:** Verify CoScientist can evaluate results and suggest improvements

**Mock Experimental Results:**
```python
{
    "bindcraft": {
        "num_rounds": 3,
        "total_sequences": 150,
        "passing_sequences": 8,
        "success_rate": 0.053,
        "sequences_per_round": [50, 50, 50],
        "passing_per_round": [2, 3, 3],
        "parameters_used": {...}
    },
    "md": {
        "stable_complexes": 5,
        "total_simulations": 8,
        "avg_rmsd": 2.3,
        "avg_binding_energy": -45.2,
        "simulation_time": 100
    }
}
```

**Expected Decision Logic:**
- If `stable_complexes / total_sequences >= 0.05` → status: "complete"
- If `stable_complexes / total_sequences < 0.05` → status: "continue"

**Parameter Bounds:**
- `num_seqs`: 10-250
- `sampling_temp`: 0.1-0.3
- `simulation_time`: 1-100 ns
- `qc_filters`: dict with 9 keys (multiplicity, diversity, repeat, etc.)
- `structure_filters`: dict with 4 keys (energy, rmsd, rmsf, passing)

---

### Test 3: Conversion to ProteinHypothesis

**Purpose:** Verify ResearchHypothesis can be converted to ProteinHypothesis

**Note:** This test checks if the method exists. Full implementation is in Phase 3 of the checklist.

---

## 🔧 Troubleshooting

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'jnana'`

**Solution:**
```bash
# Make sure Jnana is in your Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/../Jnana"

# Or install Jnana as a package
cd ../Jnana
pip install -e .
```

---

**Problem:** `ModuleNotFoundError: No module named 'struct_bio_reasoner'`

**Solution:**
```bash
# Install StructBioReasoner
pip install -e .
```

---

### LLM API Errors

**Problem:** `AuthenticationError: Invalid API key`

**Solution:**
```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Or use OpenAI
export OPENAI_API_KEY="sk-..."
```

---

**Problem:** `Timeout waiting for hypothesis generation`

**Solution:**
- Increase timeout in test: `coscientist.wait_for_completion(timeout=300)`
- Check LLM API status
- Verify network connection

---

### Method Not Found Errors

**Problem:** `AttributeError: 'CoScientist' object has no attribute 'improve_hypothesis'`

**Solution:**
- Make sure you're using the updated Jnana code
- Check that commit `2ea425bf` is present in Jnana repo
- Verify file: `../Jnana/jnana/protognosis/core/coscientist.py` has `improve_hypothesis()` method

---

## 📝 Next Steps After Tests Pass

Once all tests pass, you can proceed with:

### 1. Implement ProtoGnosis Adapter (Phase 3)

Create `../Jnana/jnana/protognosis/utils/jnana_adapter.py` with:
- `generate_hypothesis_with_coscientist()` method
- `evaluate_and_improve()` method
- Conversion from ResearchHypothesis to ProteinHypothesis

### 2. Integrate with BinderDesignSystem (Phase 6)

Modify `struct_bio_reasoner/core/binder_design_system.py`:
- Replace hardcoded config in `generate_protein_hypothesis()`
- Add iterative loop: initial hypothesis → BindCraft → MD → evaluate → repeat
- Add parent-child hypothesis tracking

### 3. Run End-to-End Test

Create a full pipeline test:
```python
# Initialize system
system = BinderDesignSystem(config_path="config/binder_config.yaml")
await system.start()

# Generate initial hypothesis
hypothesis = await system.generate_protein_hypothesis(
    research_goal="Design binders for target protein",
    strategy="coscientist_binder_design"
)

# System automatically:
# 1. Generates hypothesis with CoScientist
# 2. Runs BindCraft optimization
# 3. Runs MD simulations
# 4. Evaluates results with improve_hypothesis()
# 5. Decides to continue or complete
# 6. If continue, adjusts parameters and repeats
```

---

## 📚 Related Documentation

- `BINDER_DESIGN_IMPLEMENTATION_CHECKLIST.md` - Full implementation roadmap
- `IMPROVE_HYPOTHESIS_IMPLEMENTATION.md` - Details on improve_hypothesis()
- `BRANCH_WORKFLOW.md` - Git workflow for development
- `BINDER_JNANA_CHANGES_SUMMARY.md` - Summary of Jnana modifications

---

## ✅ Success Criteria

Your integration is working correctly if:

1. ✅ Quick test passes (all 4 tests)
2. ✅ Full integration test passes (all 3 tests)
3. ✅ Binder data is properly extracted from hypotheses
4. ✅ `improve_hypothesis()` returns valid decisions
5. ✅ Parameter suggestions are within bounds
6. ✅ No import errors or missing methods

---

## 🎯 Current Status

Based on the work completed:

- ✅ Phase 1: Data Structures (100% complete)
- ✅ Phase 2: CoScientist Integration (100% complete)
- ⏳ Phase 3: ProtoGnosis Adapter (0% complete - next step)
- ⏳ Phase 4-9: Remaining phases

**You are here:** Ready to test the Jnana ↔ StructBioReasoner connection!

Run the tests and let me know the results! 🚀

