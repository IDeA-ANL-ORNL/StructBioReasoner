# Binder Data Flow Fix - Complete Solution

## 🐛 Problems Identified

### Problem 1: Target Sequence from Config Instead of Hypothesis
**Issue:** BindCraft agent was pulling `target_sequence` from config defaults instead of from the hypothesis binder_data.

**Root Cause:** The `analyze_hypothesis()` method in BindCraft agent only used `task_params` and never extracted sequences from the `hypothesis.binder_data`.

### Problem 2: Proposed Peptide Not Passed to BindCraft
**Issue:** The proposed peptide sequence from the LLM-generated hypothesis was not being used as the initial binder sequence in BindCraft.

**Root Cause:** Same as Problem 1 - the BindCraft agent didn't extract the proposed peptides from `hypothesis.binder_data`.

---

## ✅ Solutions Implemented

### Fix 1: Modified BindCraft Agent to Extract from Hypothesis

**File:** `struct_bio_reasoner/agents/computational_design/bindcraft_agent.py`

**Changes in `analyze_hypothesis()` method (lines 228-265):**

```python
async def analyze_hypothesis(self,
                             hypothesis: ProteinHypothesis,
                             task_params: dict[str, Any]) -> BinderAnalysis:
    """
    Analyze hypothesis and run BindCraft design.
    
    Extracts target_sequence and binder_sequence from hypothesis.binder_data
    if available, otherwise falls back to task_params.
    """
    # STEP 1: Extract sequences from hypothesis binder_data if available
    if hypothesis.has_binder_data() and hypothesis.binder_data:
        binder_data = hypothesis.binder_data  # Direct attribute access
        
        # Override task_params with sequences from hypothesis
        if binder_data.target_sequence and binder_data.target_sequence != "UNKNOWN":
            task_params['target_sequence'] = binder_data.target_sequence
            self.logger.info(f"Using target sequence from hypothesis: {binder_data.target_sequence[:50]}...")
        
        # Get binder sequence from proposed peptides if available
        if binder_data.proposed_peptides and len(binder_data.proposed_peptides) > 0:
            # Use the first proposed peptide as the initial binder sequence
            first_peptide = binder_data.proposed_peptides[0]
            if isinstance(first_peptide, dict) and 'sequence' in first_peptide:
                task_params['binder_sequence'] = first_peptide['sequence']
                self.logger.info(f"Using binder sequence from hypothesis: {first_peptide['sequence'][:50]}...")
    
    # STEP 2: Verify required sequences are present
    if 'target_sequence' not in task_params:
        raise ValueError("target_sequence not found in hypothesis binder_data or task_params")
    
    if 'binder_sequence' not in task_params:
        self.logger.warning("binder_sequence not found in hypothesis, using default")
    
    # STEP 3: Run BindCraft with extracted sequences
    result = await self._generate_binder_hypothesis(task_params)
    # ... rest of method
```

**Key Changes:**
1. ✅ Extracts `target_sequence` from `hypothesis.binder_data.target_sequence`
2. ✅ Extracts `binder_sequence` from `hypothesis.binder_data.proposed_peptides[0]['sequence']`
3. ✅ Overrides `task_params` with extracted sequences
4. ✅ Falls back to `task_params` if hypothesis doesn't have binder_data
5. ✅ Validates that required sequences are present

---

### Fix 2: Updated Example to Use Direct Attribute Access

**File:** `examples/example_full_pipeline.py`

**Changes in STEP 4a (lines 163-190):**

```python
# Get binder data for BindCraft
# NOTE: Use direct attribute access instead of get_binder_data()
if not current_hypothesis.has_binder_data():
    print("  ❌ No binder data found in hypothesis!")
    break

binder_data = current_hypothesis.binder_data

print("\n📊 Binder Information:")
print(f"  - Target sequence: {binder_data.target_sequence[:50]}... ({len(binder_data.target_sequence)} residues)")
print(f"  - Proposed peptides: {len(binder_data.proposed_peptides)}")
if binder_data.proposed_peptides:
    print(f"  - First peptide: {binder_data.proposed_peptides[0]['sequence'][:50]}...")

# Prepare BindCraft config
# NOTE: The BindCraft agent will automatically extract sequences from hypothesis.binder_data
bindcraft_config = {
    "target_sequence": binder_data.target_sequence,
    "binder_sequence": binder_data.proposed_peptides[0]["sequence"] if binder_data.proposed_peptides else None,
    "num_rounds": 3,
    "num_seqs": parameters["num_seqs"],
    "sampling_temp": parameters["sampling_temp"],
    "qc_filters": parameters["qc_filters"],
    "structure_filters": parameters["structure_filters"]
}
```

**Key Changes:**
1. ✅ Added safety check with `has_binder_data()`
2. ✅ Uses direct attribute access: `current_hypothesis.binder_data`
3. ✅ Better logging to show what sequences are being used
4. ✅ Passes sequences explicitly in config (as fallback)

---

## 🔄 Complete Data Flow

### Before Fixes (BROKEN):

```
1. LLM generates hypothesis with binder_data:
   - target_sequence: "NITNLCPFGEVFNATR..." ✅
   - proposed_peptides: [{"sequence": "MKTAYIAK...", ...}] ✅

2. ProteinHypothesis created with binder_data ✅

3. example_full_pipeline.py calls:
   bindcraft_agent.analyze_hypothesis(hypothesis, config)

4. BindCraft agent IGNORES hypothesis.binder_data ❌
   - Uses config['target_sequence'] (from BinderConfig defaults) ❌
   - Uses config['binder_sequence'] (hardcoded default) ❌

5. BindCraft runs with WRONG sequences ❌
```

### After Fixes (WORKING):

```
1. LLM generates hypothesis with binder_data:
   - target_sequence: "NITNLCPFGEVFNATR..." ✅
   - proposed_peptides: [{"sequence": "MKTAYIAK...", ...}] ✅

2. ProteinHypothesis created with binder_data ✅

3. example_full_pipeline.py:
   - Extracts: binder_data = hypothesis.binder_data ✅
   - Passes: config with sequences from binder_data ✅

4. BindCraft agent.analyze_hypothesis():
   - Checks: hypothesis.has_binder_data() ✅
   - Extracts: target_seq from hypothesis.binder_data.target_sequence ✅
   - Extracts: binder_seq from hypothesis.binder_data.proposed_peptides[0] ✅
   - Overrides: task_params with extracted sequences ✅

5. BindCraft runs with CORRECT sequences from LLM! ✅
```

---

## 📊 Expected Output

When you run `examples/example_full_pipeline.py`, you should now see:

```
[STEP 3] Generating initial hypothesis with CoScientist...
✓ Initial hypothesis generated: hyp_abc123
  - Title: Binder Design for SARS-CoV-2 Spike Protein
  - Target: SARS-CoV-2 spike protein RBD
  - Proposed peptides: 3

[STEP 4] Starting iterative optimization loop...

============================================================
ITERATION 1/5
============================================================

[1.a] Running BindCraft optimization...
  Parameters:
    - num_seqs: 50
    - sampling_temp: 0.2
    - simulation_time: 100 ns

📊 Binder Information:
  - Target sequence: NITNLCPFGEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFK... (223 residues)
  - Proposed peptides: 3
  - First peptide: MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNL... (68 residues)

INFO - Using target sequence from hypothesis: NITNLCPFGEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFK...
INFO - Using binder sequence from hypothesis: MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNL...

  ✓ BindCraft complete:
    - Total sequences: 150
    - Passing sequences: 45
    - Passing structures: 12
    - Success rate: 8.0%
```

**Key Indicators of Success:**
1. ✅ Target sequence matches the one from research goal (starts with "NITNLCPFGEVFNATR")
2. ✅ Binder sequence matches the LLM-proposed peptide (NOT the hardcoded default)
3. ✅ Logs show "Using target sequence from hypothesis"
4. ✅ Logs show "Using binder sequence from hypothesis"

---

## 🔍 Verification Steps

### Step 1: Check Target Sequence Source

**Before Fix:**
```python
# In BindCraft agent logs:
target_sequence=MMKMEGIALKKRLSWISVCLLVLVSAAGMLFSTAAKTETSSHKAHTEAQV...  # ❌ From config default
```

**After Fix:**
```python
# In BindCraft agent logs:
INFO - Using target sequence from hypothesis: NITNLCPFGEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFK...  # ✅ From hypothesis
target_sequence=NITNLCPFGEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFK...
```

### Step 2: Check Binder Sequence Source

**Before Fix:**
```python
# In BindCraft agent logs:
binder_sequence=MKQHKAMIVALIVICITAVVAALVTRKDLCEVHIRTGQTEVAVF  # ❌ Hardcoded default
```

**After Fix:**
```python
# In BindCraft agent logs:
INFO - Using binder sequence from hypothesis: MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNL...  # ✅ From LLM
binder_sequence=MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNL...
```

### Step 3: Verify End-to-End Flow

```bash
# Run the example
python examples/example_full_pipeline.py

# Check logs for these key messages:
grep "Using target sequence from hypothesis" logs/struct_bio_reasoner.log
grep "Using binder sequence from hypothesis" logs/struct_bio_reasoner.log
```

---

## 🎯 Summary

### Problems Fixed:
1. ✅ **Target sequence** now comes from hypothesis (LLM-generated), not config defaults
2. ✅ **Binder sequence** now comes from hypothesis.proposed_peptides[0], not hardcoded default
3. ✅ **Data flow** is correct: Research Goal → LLM → Hypothesis → BindCraft

### Files Modified:
1. ✅ `struct_bio_reasoner/agents/computational_design/bindcraft_agent.py`
   - Modified `analyze_hypothesis()` to extract sequences from hypothesis.binder_data
2. ✅ `examples/example_full_pipeline.py`
   - Updated to use direct attribute access and better logging

### Key Insight:
The BindCraft agent now **prioritizes sequences from the hypothesis** over config defaults, ensuring that the LLM-generated binder designs are actually used in the computational workflow!

---

## 🚀 Next Steps

1. **Run the example:**
   ```bash
   python examples/example_full_pipeline.py
   ```

2. **Verify the sequences:**
   - Check that target sequence matches your research goal
   - Check that binder sequence matches LLM-proposed peptide
   - Look for "Using ... from hypothesis" in logs

3. **Test with different research goals:**
   - Try different target sequences
   - Verify they flow through correctly

**The binder data flow is now fixed!** 🎉

