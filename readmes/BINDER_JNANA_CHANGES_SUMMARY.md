# Binder-Specific Hypothesis Generation - Jnana Changes Summary

## Overview
Modified the Jnana framework to support binder-specific hypothesis generation with structured output for peptide binder design tasks.

## Files Modified
- `../Jnana/jnana/protognosis/agents/specialized_agents.py`

## Changes Made

### 1. Detection of Binder Design Tasks
**Location:** `_generate_hypothesis()` method (lines 72-74)

**What was added:**
```python
# Detect if this is a binder design task
is_binder_design = ('target_sequence' in plan_config or 
                   'binder_sequence' in plan_config)
```

**Purpose:** Automatically detect when a research goal is a binder design task based on the presence of `target_sequence` or `binder_sequence` in the research plan configuration.

---

### 2. Binder-Specific Output Schema
**Location:** `_generate_hypothesis()` method (lines 118-157)

**What was added:**
```python
if is_binder_design:
    schema = {
        "hypothesis": {
            "title": "string",
            "content": "string",
            "summary": "string",
            "key_novelty_aspects": ["string"],
            "testable_predictions": ["string"]
        },
        "binder_data": {
            "target_name": "string",
            "target_sequence": "string",
            "proposed_peptides": [
                {
                    "sequence": "string",
                    "source": "string",
                    "rationale": "string",
                    "peptide_id": "string"
                }
            ],
            "literature_references": ["string"],
            "binding_affinity_goal": "string",
            "clinical_context": "string"
        },
        "explanation": "string",
        "generation_strategy": "string"
    }
```

**Purpose:** Define a structured schema that includes a `binder_data` section with all necessary fields for peptide binder design.

---

### 3. Binder Data Storage in Hypothesis Metadata
**Location:** `_generate_hypothesis()` method (lines 176-195)

**What was added:**
```python
# Create a new hypothesis object
metadata = {
    "title": response["hypothesis"]["title"],
    "key_novelty_aspects": response["hypothesis"]["key_novelty_aspects"],
    "testable_predictions": response["hypothesis"]["testable_predictions"],
    "generation_strategy": response["generation_strategy"],
    "explanation": response["explanation"]
}

# Add binder data if present
if "binder_data" in response:
    metadata["binder_data"] = response["binder_data"]
    self.logger.info(f"Binder data included in hypothesis: {len(response['binder_data'].get('proposed_peptides', []))} peptides proposed")

hypothesis = ResearchHypothesis(
    content=response["hypothesis"]["content"],
    summary=response["hypothesis"]["summary"],
    agent_id=self.agent_id,
    metadata=metadata
)
```

**Purpose:** Extract binder data from the LLM response and store it in the hypothesis metadata for later retrieval by StructBioReasoner.

---

### 4. Binder-Specific Prompt Templates

#### 4.1 Literature Exploration Prompt
**Location:** `_create_literature_exploration_prompt()` method (lines 333-395)

**What was added:**
- Added `is_binder_design` parameter
- Conditional binder-specific instructions when `is_binder_design=True`
- Requests for:
  - Target protein name and sequence
  - 3-5 proposed peptide binders with sequences, sources, rationales, and IDs
  - Literature references (PubMed IDs, DOIs)
  - Binding affinity goals
  - Clinical context

**Example binder-specific section:**
```
This is a BINDER DESIGN task. Your hypothesis must include:

1. **Target Information:**
   - Target protein name
   - Target sequence: {target_seq}

2. **Proposed Peptide Binders (3-5 candidates):**
   For each peptide, provide:
   - Amino acid sequence (single-letter code)
   - Source (e.g., 'literature:PMID12345', 'homology:ProteinX', 'de_novo')
   - Rationale for why this peptide might bind the target
   - Unique peptide ID (e.g., 'pep_001', 'pep_002')

3. **Literature Support:**
   - List of relevant literature references (PubMed IDs, DOIs, or citations)
   - Key findings from literature that support your peptide choices

4. **Design Goals:**
   - Desired binding affinity (e.g., 'nanomolar', 'sub-micromolar')
   - Clinical context or application (if applicable)
```

#### 4.2 Scientific Debate Prompt
**Location:** `_create_scientific_debate_prompt()` method (lines 397-443)

**What was added:**
- Added `is_binder_design` parameter
- Simulates debate among experts (structural biologist, peptide chemist, computational biologist, medicinal chemist)
- Focuses on proposing and refining peptide binder candidates through expert critique

#### 4.3 Assumptions Identification Prompt
**Location:** `_create_assumptions_identification_prompt()` method (lines 445-490)

**What was added:**
- Added `is_binder_design` parameter
- Challenges assumptions in peptide binder design (e.g., size limits, charge requirements, binding motifs)
- Proposes unconventional peptide sequences based on challenging these assumptions

#### 4.4 Research Expansion Prompt
**Location:** `_create_research_expansion_prompt()` method (lines 492-552)

**What was added:**
- Added `is_binder_design` parameter
- Builds upon existing hypotheses to propose new peptide binder candidates
- Maintains structured binder_data output format

---

### 5. Prompt Method Signatures Updated
**Location:** Lines 100-107

**What was changed:**
All internal prompt method calls now pass the `is_binder_design` flag:
```python
if strategy == "literature_exploration":
    prompt = self._create_literature_exploration_prompt(research_goal, plan_config, is_binder_design)
elif strategy == "scientific_debate":
    prompt = self._create_scientific_debate_prompt(research_goal, plan_config, is_binder_design)
elif strategy == "assumptions_identification":
    prompt = self._create_assumptions_identification_prompt(research_goal, plan_config, is_binder_design)
elif strategy == "research_expansion":
    top_hypotheses = self.memory.get_top_hypotheses(3)
    top_summaries = "\n".join([f"- {h.summary}" for h in top_hypotheses]) if top_hypotheses else "No existing hypotheses yet."
    prompt = self._create_research_expansion_prompt(research_goal, plan_config, top_summaries, is_binder_design)
```

---

## Integration with StructBioReasoner

### How It Works:
1. **Research Goal Parsing:** When a binder design research goal is provided, `SupervisorAgent.parse_research_goal()` (already implemented) extracts `target_sequence` and `binder_sequence` into `plan_config`

2. **Hypothesis Generation:** `GenerationAgent._generate_hypothesis()` detects binder design from `plan_config` and uses binder-specific prompts and schema

3. **Structured Output:** LLM generates hypothesis with `binder_data` section containing:
   - `target_name` and `target_sequence`
   - `proposed_peptides` (list of 3-5 peptides with sequences, sources, rationales, IDs)
   - `literature_references`
   - `binding_affinity_goal`
   - `clinical_context`

4. **Metadata Storage:** Binder data is stored in `ResearchHypothesis.metadata['binder_data']`

5. **Conversion to UnifiedHypothesis:** When converted to `UnifiedHypothesis`, the binder data flows through in the metadata

6. **Extraction in StructBioReasoner:** `ProteinHypothesis._extract_binder_data()` retrieves the binder data from metadata and creates `BinderHypothesisData` objects

---

## Expected Output Format

When a binder design hypothesis is generated, the LLM will return JSON like:

```json
{
  "hypothesis": {
    "title": "Novel Peptide Binders for SARS-CoV-2 Spike Protein",
    "content": "Based on literature analysis...",
    "summary": "Propose 5 peptide binders targeting the RBD of SARS-CoV-2 spike protein",
    "key_novelty_aspects": ["Unconventional binding motifs", "Multi-epitope targeting"],
    "testable_predictions": ["Nanomolar binding affinity", "Broad variant coverage"]
  },
  "binder_data": {
    "target_name": "SARS-CoV-2 Spike Protein RBD",
    "target_sequence": "NITNLCPFGEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFKCYGVSPTKLNDLCFTNVYADSFVIRGDEVRQIAPGQTGKIADYNYKLPDDFTGCVIAWNSNNLDSKVGGNYNYLYRLFRKSNLKPFERDISTEIYQAGSTPCNGVEGFNCYFPLQSYGFQPTNGVGYQPYRVVVLSFELLHAPATVCGPKKSTNLVKNKCVNF",
    "proposed_peptides": [
      {
        "sequence": "YQAGSTPCNGV",
        "source": "literature:PMID33234567",
        "rationale": "This sequence mimics the ACE2 binding interface and has shown binding in previous studies",
        "peptide_id": "pep_001"
      },
      {
        "sequence": "FNCYFPLQSYG",
        "source": "de_novo",
        "rationale": "Computationally designed to target a conserved epitope across variants",
        "peptide_id": "pep_002"
      }
    ],
    "literature_references": [
      "PMID:33234567 - ACE2-mimicking peptides for SARS-CoV-2",
      "DOI:10.1038/s41586-020-2456-9 - Structural basis of receptor recognition"
    ],
    "binding_affinity_goal": "sub-nanomolar (< 1 nM)",
    "clinical_context": "Therapeutic peptide for COVID-19 treatment"
  },
  "explanation": "These peptides were selected based on...",
  "generation_strategy": "literature_exploration"
}
```

---

## Testing Recommendations

1. **Test with binder design research goal:**
   ```python
   research_goal = "Design peptide binders for SARS-CoV-2 spike protein to optimize binding affinity"
   ```

2. **Verify binder data extraction:**
   - Check that `metadata['binder_data']` exists in generated hypotheses
   - Verify all required fields are present
   - Confirm 3-5 peptides are proposed

3. **Test all generation strategies:**
   - Literature exploration
   - Scientific debate
   - Assumptions identification
   - Research expansion

4. **Integration test with StructBioReasoner:**
   - Generate hypothesis in Jnana
   - Convert to UnifiedHypothesis
   - Extract in ProteinHypothesis
   - Verify BinderHypothesisData is created correctly

---

## Next Steps

✅ **Completed:**
- Binder design detection
- Binder-specific schema
- Binder-specific prompts for all 4 strategies
- Binder data storage in metadata

📋 **Remaining (from checklist):**
- [ ] Add structured output parsing for binder hypothesis JSON (may already work with current implementation)
- [ ] Modify `improve_hypothesis()` in CoScientist to accept experimental results
- [ ] Implement decision logic in `improve_hypothesis()` for continue vs. complete
- [ ] Add parameter adjustment logic in `improve_hypothesis()`

