# Binder Design Workflow Implementation Checklist

## Phase 1: Data Structures (Foundation)

- [x] Extend `BinderHypothesisData` dataclass with `to_dict()` and `from_dict()` methods
	- File: `struct_bio_reasoner/data/protein_hypothesis.py`
	- Lines: ~23-73
- [x] Add `binder_data` field to `ProteinHypothesis.__init__()`
	- File: `struct_bio_reasoner/data/protein_hypothesis.py`
	- Lines: ~254-255
- [x] Add `_extract_binder_data()` class method to `ProteinHypothesis`
	- File: `struct_bio_reasoner/data/protein_hypothesis.py`
	- Lines: ~326-374
- [x] Modify `ProteinHypothesis.from_unified_hypothesis()` to call `_extract_binder_data()`
	- File: `struct_bio_reasoner/data/protein_hypothesis.py`
	- Lines: ~319-322
- [x] Add helper methods to `ProteinHypothesis`: `has_binder_data()`, `get_target_sequence()`, `get_proposed_peptides()`, `add_binder_data()`
	- File: `struct_bio_reasoner/data/protein_hypothesis.py`
	- Lines: ~475-504
- [ ] Extend `BinderAnalysis` dataclass to store optimized hypotheses
	- File: `struct_bio_reasoner/data/protein_hypothesis.py`
	- Current lines: ~64-80
	- Need to add: `optimized_hypotheses`, `passing_hypotheses`, `parameters_used`, `sequences_per_round`, `passing_per_round`
- [ ] Add methods to `BinderAnalysis`: `to_dict()`, `get_best_candidates()`, `get_passing_sequences()`
	- File: `struct_bio_reasoner/data/protein_hypothesis.py`
	- Add after `BinderAnalysis` dataclass definition
- [ ] Add parent-child tracking fields to `ProteinHypothesis`
	- File: `struct_bio_reasoner/data/protein_hypothesis.py`
	- Note: `parent_id` and `children_ids` already exist in `UnifiedHypothesis`, verify they're properly inherited

## Phase 2: CoScientist Integration (Hypothesis Generation)

- [ ] Modify CoScientist prompt template for binder-specific hypothesis generation
	- File: `../Jnana/jnana/protognosis/agents/coscientist_agent.py`
	- Look for: `generate_hypothesis()` or similar method
	- Need to: Add detection for binder design research goals (regex pattern matching)
	- Need to: Create binder-specific prompt that requests JSON with `target_sequence`, `proposed_peptides`, `literature_references`
- [ ] Add structured output parsing for binder hypothesis JSON
	- File: `../Jnana/jnana/protognosis/agents/coscientist_agent.py`
	- Look for: Where hypothesis response is parsed
	- Need to: Parse JSON response and extract binder-specific fields
	- Need to: Store binder data in `UnifiedHypothesis.metadata['binder_data']`
- [ ] Modify `improve_hypothesis()` in CoScientist to accept experimental results
	- File: `../Jnana/jnana/protognosis/agents/coscientist_agent.py`
	- Look for: `improve_hypothesis()` method
	- Need to: Accept `experimental_results` dict with BindCraft and MD data
	- Need to: Format prompt to include BindCraft metrics (passing_sequences, success_rate, etc.)
	- Need to: Format prompt to include MD metrics (stable_complexes, RMSD, binding energy, etc.)
- [ ] Implement decision logic in `improve_hypothesis()` for continue vs. complete
	- File: `../Jnana/jnana/protognosis/agents/coscientist_agent.py`
	- In: `improve_hypothesis()` method
	- Need to: Evaluate if success criteria met (5% stable complexes threshold)
	- Need to: Return decision JSON with `status`, `reasoning`, `new_parameters`
- [ ] Add parameter adjustment logic in `improve_hypothesis()`
	- File: `../Jnana/jnana/protognosis/agents/coscientist_agent.py`
	- In: `improve_hypothesis()` method
	- Need to: LLM suggests new `num_seqs`, `sampling_temp`, `qc_filters`, `structure_filters`, `simulation_time`
	- Need to: Include reasoning for each parameter change in tight JSON format
	- Need to: Validate parameter bounds (e.g., num_seqs > 0 and < 1000)

## Phase 3: ProtoGnosis Adapter (Bridge Layer)

- [ ] Add `generate_hypothesis_with_coscientist()` method to ProtoGnosis adapter
	- File: `../Jnana/jnana/protognosis/utils/jnana_adapter.py`
	- Look for: Existing methods like `generate_hypotheses()`
	- Need to: Call CoScientist with binder-specific prompt
	- Need to: Return `UnifiedHypothesis` with binder data in metadata
	- Need to: Handle case where CoScientist doesn't return proper JSON
- [ ] Add `evaluate_and_improve()` method to ProtoGnosis adapter
	- File: `../Jnana/jnana/protognosis/utils/jnana_adapter.py`
	- Need to: Accept current hypothesis and experimental results (BindCraft + MD)
	- Need to: Call CoScientist's `improve_hypothesis()`
	- Need to: Parse decision JSON and return structured dict
	- Need to: Return: `{'status': 'continue'|'success', 'reasoning': str, 'new_parameters': dict, 'updated_hypothesis': ProteinHypothesis}`

## Phase 4: BindCraft Agent Modifications (Core Logic)

- [ ] Modify `analyze_hypothesis()` to extract binder data from hypothesis
	- File: `struct_bio_reasoner/agents/computational_design/bindcraft_agent.py`
	- Look for: `analyze_hypothesis()` method signature
	- Need to: Check `hypothesis.has_binder_data()` at start
	- Need to: Extract `target_sequence` from `hypothesis.binder_data.target_sequence`
	- Need to: Extract `proposed_peptides` from `hypothesis.binder_data.proposed_peptides`
	- Need to: Handle case where no binder data exists (error or fallback?)
- [ ] Modify `analyze_hypothesis()` to extract parameters from task_params
	- File: `struct_bio_reasoner/agents/computational_design/bindcraft_agent.py`
	- In: `analyze_hypothesis()` method
	- Need to: Extract user-set config from `task_params['computational_design']['user_set']`
	- Need to: Extract agent-decided config from `task_params['computational_design']['agent_decided']`
	- Need to: Provide defaults for agent-decided params if not specified
	- Need to: Validate parameter ranges and required fields
- [ ] Implement fold→inverse fold→fold loop for each proposed peptide
	- File: `struct_bio_reasoner/agents/computational_design/bindcraft_agent.py`
	- In: `analyze_hypothesis()` method
	- Need to: Loop over `proposed_peptides` from hypothesis
	- Need to: For each peptide, run `n_rounds` of fold→inverse fold→fold
	- Need to: Track `peptide_id` to maintain parent-child relationships
	- Need to: Round 1 uses literature peptide, Round 2+ uses best from previous round
- [ ] Implement QC filters (sequence-based)
	- File: `struct_bio_reasoner/agents/computational_design/bindcraft_agent.py`
	- Create helper method: `_apply_qc_filters(sequences, qc_filters)`
	- Need to: Check max_repeat (consecutive identical amino acids)
	- Need to: Check max_charge (net charge at pH 7)
	- Need to: Check hydrophobicity (average using Kyte-Doolittle scale)
	- Need to: Check length (min_length, max_length)
	- Need to: Check forbidden motifs (e.g., N-glycosylation sites)
	- Need to: Return only sequences that pass all filters
- [ ] Implement structure filters (structure-based)
	- File: `struct_bio_reasoner/agents/computational_design/bindcraft_agent.py`
	- Create helper method: `_apply_structure_filters(structures, structure_filters)`
	- Need to: Extract pLDDT scores from AlphaFold predictions
	- Need to: Calculate clash scores using structural analysis
	- Need to: Check geometry (bond angles, lengths) using BioPython or MolProbity
	- Need to: Check binding interface (distance between target and peptide residues)
	- Need to: Return only structures that pass all filters
- [ ] Structure return value as enhanced `BinderAnalysis`
	- File: `struct_bio_reasoner/agents/computational_design/bindcraft_agent.py`
	- In: `analyze_hypothesis()` method, at return statement
	- Need to: Populate `optimized_hypotheses` list with dicts containing: `peptide_id`, `parent_id`, `sequence`, `structure_path`, `metrics`, `round_generated`, `passed_qc`, `passed_structure`
	- Need to: Populate `passing_hypotheses` (subset that passed all filters)
	- Need to: Set `parameters_used` to actual parameters used
	- Need to: Calculate `success_rate` = `passing_structures / total_sequences`
	- Need to: Track `sequences_per_round` and `passing_per_round`
- [ ] Implement multi-round seed selection strategy
	- File: `struct_bio_reasoner/agents/computational_design/bindcraft_agent.py`
	- Create helper method: `_select_seeds_for_next_round(passing_sequences, strategy, top_k)`
	- Need to: Decide between using ALL passing sequences vs TOP K vs random sample
	- Need to: Make `top_k` configurable in agent_decided parameters
	- Need to: Default to top_k=5 or top_k=10
	- Need to: Rank by some metric (pLDDT, binding score, etc.)
- [ ] Add error handling for BindCraft failures
	- File: `struct_bio_reasoner/agents/computational_design/bindcraft_agent.py`
	- In: `analyze_hypothesis()` and helper methods
	- Need to: Catch exceptions from BindCraft subprocess calls
	- Need to: Save partial results before crashing
	- Need to: Return error information in `BinderAnalysis` (add `error_log` field?)
	- Need to: Handle case where NO sequences pass filters

## Phase 5: MDAgent Adapter Modifications (Simulation)

- [ ] Modify `analyze_hypothesis()` to extract target-peptide pairs
	- File: `struct_bio_reasoner/agents/molecular_dynamics/mdagent_adapter.py`
	- Look for: `analyze_hypothesis()` method
	- Need to: Extract `target_sequence` from `hypothesis.binder_data.target_sequence`
	- Need to: Extract optimized peptides from `hypothesis.binder_analysis.optimized_hypotheses`
	- Need to: Handle case where no binder_analysis exists yet (error or skip?)
- [ ] Modify `analyze_hypothesis()` to simulate multiple target-peptide pairs
	- File: `struct_bio_reasoner/agents/molecular_dynamics/mdagent_adapter.py`
	- In: `analyze_hypothesis()` method
	- Need to: Loop over each optimized peptide from BindCraft
	- Need to: For each pair, build complex structure (target + peptide)
	- Need to: Run implicit solvent MD simulation
	- Need to: Extract stability metrics: RMSD, RMSF, binding energy
	- Need to: Decide: run simulations in parallel or sequentially?
- [ ] Extract agent-decided simulation parameters
	- File: `struct_bio_reasoner/agents/molecular_dynamics/mdagent_adapter.py`
	- In: `analyze_hypothesis()` method
	- Need to: Extract user-set config: `force_field`, `platform` (CPU/CUDA)
	- Need to: Extract agent-decided config: `simulation_time`, `temperature`, `implicit_solvent`
	- Need to: Provide defaults if not specified
- [ ] Structure return value as enhanced `SimAnalysis`
	- File: `struct_bio_reasoner/agents/molecular_dynamics/mdagent_adapter.py`
	- In: `analyze_hypothesis()` method, at return
	- Need to: Return `simulation_results` list with dicts: `peptide_id`, `rmsd`, `rmsf`, `binding_energy`, `stability_score`, `trajectory_path`
	- Need to: Calculate `overall_stability` (average across all simulations)
	- Need to: Identify `best_candidate` (peptide with best metrics)
	- Need to: Track which peptides are "stable" (pass energy threshold)
- [ ] Implement filtering by MD energies
	- File: `struct_bio_reasoner/agents/molecular_dynamics/mdagent_adapter.py`
	- Create helper method: `_filter_by_stability(simulation_results, threshold)`
	- Need to: Define what "stable" means (binding energy < threshold? RMSD < threshold?)
	- Need to: Return list of peptide_ids that pass stability criteria
	- Need to: Make threshold configurable in agent_decided parameters
- [ ] Add complex structure building logic
	- File: `struct_bio_reasoner/agents/molecular_dynamics/mdagent_adapter.py`
	- Create helper method: `_build_complex(target_structure, peptide_structure)`
	- Need to: Decide if BindCraft provides complex OR if MD agent does docking
	- Need to: If docking needed: use simple placement or proper docking algorithm?
	- Need to: Return complex structure path for simulation

## Phase 6: BinderDesignSystem Orchestration (Putting It Together)

- [ ] Rewrite `generate_protein_hypothesis()` with iterative loop
	- File: `struct_bio_reasoner/core/binder_design_system.py`
	- Look for: `generate_protein_hypothesis()` method (currently lines ~250-340)
	- Need to: Remove hardcoded config (lines 293-320)
	- Need to: Implement structure: initial hypothesis → loop(BindCraft → MD → evaluate) → return
- [ ] Step 1: Generate initial hypothesis with CoScientist
	- File: `struct_bio_reasoner/core/binder_design_system.py`
	- In: `generate_protein_hypothesis()` method, at start
	- Need to: Call `self.protognosis_adapter.generate_hypothesis_with_coscientist(research_goal)`
	- Need to: Convert to `ProteinHypothesis` using `from_unified_hypothesis()`
	- Need to: Verify binder data exists (`has_binder_data()`)
- [ ] Step 2: Implement iterative optimization loop
	- File: `struct_bio_reasoner/core/binder_design_system.py`
	- In: `generate_protein_hypothesis()` method
	- Need to: Set `max_rounds = 5` (or configurable)
	- Need to: Loop: for round_num in range(max_rounds)
	- Need to: Track all hypotheses generated across rounds
- [ ] Step 3a: Run BindCraft in loop
	- File: `struct_bio_reasoner/core/binder_design_system.py`
	- In: `generate_protein_hypothesis()` loop body
	- Need to: Call `self.design_agents['computational_design'].analyze_hypothesis(protein_hypothesis, task_params)`
	- Need to: Add results to hypothesis: `protein_hypothesis.add_binder_analysis(bindcraft_results)`
	- Need to: Extract optimized peptides for MD simulation
- [ ] Step 3b: Run MD simulation in loop
	- File: `struct_bio_reasoner/core/binder_design_system.py`
	- In: `generate_protein_hypothesis()` loop body
	- Need to: Call `self.design_agents['molecular_dynamics'].analyze_hypothesis(protein_hypothesis, task_params)`
	- Need to: Add results to hypothesis: `protein_hypothesis.add_md_analysis(md_results)`
	- Need to: Extract stability metrics for evaluation
- [ ] Step 3c: CoScientist evaluates and decides
	- File: `struct_bio_reasoner/core/binder_design_system.py`
	- In: `generate_protein_hypothesis()` loop body
	- Need to: Format experimental results: `{'bindcraft': bindcraft_results.to_dict(), 'md_simulation': md_results.to_dict()}`
	- Need to: Call `self.protognosis_adapter.evaluate_and_improve(protein_hypothesis, experimental_results)`
	- Need to: Parse decision dict
- [ ] Step 3d: Check success criteria (5% threshold)
	- File: `struct_bio_reasoner/core/binder_design_system.py`
	- In: `generate_protein_hypothesis()` loop body
	- Need to: Calculate `stable_complexes / total_sequences`
	- Need to: If >= 0.05 (5%) AND decision['status'] == 'success', break loop
	- Need to: Log reasoning from CoScientist
- [ ] Step 3e: Update parameters for next round
	- File: `struct_bio_reasoner/core/binder_design_system.py`
	- In: `generate_protein_hypothesis()` loop body
	- Need to: Extract `decision['new_parameters']`
	- Need to: Update `task_params['computational_design']['agent_decided']` with new values
	- Need to: Update `task_params['molecular_dynamics']['agent_decided']` with new values
	- Need to: Create new hypothesis from best passing sequences for next round
- [ ] Step 4: Create child hypotheses from optimized peptides
	- File: `struct_bio_reasoner/core/binder_design_system.py`
	- Create helper method: `_create_child_hypotheses(parent_hypothesis, optimized_peptides)`
	- Need to: For each passing peptide, create new `ProteinHypothesis`
	- Need to: Set `parent_id` to current hypothesis ID
	- Need to: Create new `BinderHypothesisData` with optimized peptide as `proposed_peptides`
	- Need to: Track lineage (tree structure)
- [ ] Step 5: Return final hypothesis with all results
	- File: `struct_bio_reasoner/core/binder_design_system.py`
	- In: `generate_protein_hypothesis()` method, at end
	- Need to: Return hypothesis with all BindCraft and MD results attached
	- Need to: Include all child hypotheses (or just best ones?)
	- Need to: Save checkpoint/results to disk

## Phase 7: Configuration Management (User Control)

- [ ] Separate user-set vs agent-decided parameters in `binder_config.yaml`
	- File: `config/binder_config.yaml`
	- Need to: Create `user_set` section under `computational_design` agent
	- Need to: Create `agent_decided_defaults` section under `computational_design` agent
	- Need to: Same for `molecular_dynamics` agent
	- Need to: Document which parameters are user-controlled vs agent-controlled
- [ ] Remove hardcoded HPC paths from `binder_design_system.py`
	- File: `struct_bio_reasoner/core/binder_design_system.py`
	- Lines: ~293-320 (currently hardcoded)
	- Need to: Load all paths from config file
	- Need to: Make paths relative or use environment variables
	- Need to: Add validation that paths exist
- [ ] Uncomment tools initialization in `binder_design_system.py`
	- File: `struct_bio_reasoner/core/binder_design_system.py`
	- Line: ~150 (currently commented out)
	- Need to: Uncomment `await self._initialize_design_tools()`
	- Need to: Verify tools are actually needed (or remove if not)
- [ ] Load BindCraft/MD config from file instead of hardcoding
	- File: `struct_bio_reasoner/core/binder_design_system.py`
	- In: `generate_protein_hypothesis()` or `_get_task_params()` method
	- Need to: Read from `self.binder_config['agents']['computational_design']`
	- Need to: Merge user_set + agent_decided_defaults + agent_decided_overrides
	- Need to: Pass merged config as `task_params`

## Phase 8: Testing & Validation

- [ ] Test `BinderHypothesisData` serialization/deserialization
	- Create test: `to_dict()` and `from_dict()` round-trip
	- Verify all fields preserved
- [ ] Test `ProteinHypothesis` binder data extraction
	- Create test with binder data in different locations (metadata, content, biological_context)
	- Verify `_extract_binder_data()` finds it correctly
- [ ] Test BindCraft agent with simple hypothesis
	- Create manual `ProteinHypothesis` with binder data
	- Call `analyze_hypothesis()` with fixed parameters
	- Verify `BinderAnalysis` structure is correct
- [ ] Test QC and structure filters
	- Create sequences that should fail each filter
	- Verify they get filtered out
	- Create sequences that should pass
	- Verify they make it through
- [ ] Test MD agent with target-peptide pairs
	- Create hypothesis with BindCraft results
	- Call MD `analyze_hypothesis()`
	- Verify simulations run and return stability metrics
- [ ] Test CoScientist binder hypothesis generation
	- Call with research goal: "Design peptide binders for TargetX to optimize binding affinity..."
	- Verify JSON response has target_sequence and proposed_peptides
	- Verify conversion to `ProteinHypothesis` works
- [ ] Test CoScientist improve_hypothesis with experimental results
	- Create mock BindCraft and MD results
	- Call `improve_hypothesis()`
	- Verify decision JSON is returned with reasoning and new parameters
- [ ] Test full iterative loop with 2 rounds
	- Run `generate_protein_hypothesis()` with max_rounds=2
	- Verify BindCraft runs twice
	- Verify MD runs twice
	- Verify parameters update between rounds
- [ ] Test success criteria (5% threshold)
	- Mock results where 5% pass → verify loop stops
	- Mock results where <5% pass → verify loop continues
- [ ] Test hypothesis tree structure
	- Verify parent-child relationships are tracked
	- Verify lineage can be reconstructed
- [ ] Test edge cases
	- No sequences pass filters → verify handling
	- BindCraft crashes → verify error handling
	- CoScientist returns invalid JSON → verify fallback

## Phase 9: Documentation & Polish

- [ ] Document the full workflow in README or docs
	- Explain the iterative loop
	- Explain success criteria
	- Provide example research goals
- [ ] Add logging throughout the workflow
	- Log each round's results
	- Log CoScientist's reasoning
	- Log parameter changes
- [ ] Add progress tracking/visualization
	- Show how many sequences generated/passing per round
	- Show success rate trend across rounds
- [ ] Create example script demonstrating the workflow
	- Simple end-to-end example
	- Show how to set research goal
	- Show how to interpret results

---

## Key Files Summary

| File | Purpose | Status |
|------|---------|--------|
| `struct_bio_reasoner/data/protein_hypothesis.py` | Data structures | Partially complete |
| `../Jnana/jnana/protognosis/agents/coscientist_agent.py` | LLM reasoning & decisions | Not started |
| `../Jnana/jnana/protognosis/utils/jnana_adapter.py` | Bridge to Jnana | Not started |
| `struct_bio_reasoner/agents/computational_design/bindcraft_agent.py` | BindCraft integration | Not started |
| `struct_bio_reasoner/agents/molecular_dynamics/mdagent_adapter.py` | MD simulation | Not started |
| `struct_bio_reasoner/core/binder_design_system.py` | Orchestration | Not started |
| `config/binder_config.yaml` | Configuration | Needs restructuring |

---

## Critical Path (Minimum Viable Implementation)

If you want to get something working quickly, focus on these tasks in order:

1. ✅ Data structures (Phase 1) - DONE
2. CoScientist prompt for binder generation (Phase 2, first 2 tasks)
3. BindCraft extract binder data + run single round (Phase 4, first 3 tasks)
4. Simple loop in BinderDesignSystem (Phase 6, tasks 1-3)
5. Test with hardcoded parameters (Phase 8, first 3 tasks)
6. Then add: MD simulation, CoScientist evaluation, multi-round iteration

---

## Notes

- Success criteria: `stable_complexes_from_md / total_generated_sequences >= 0.05` (5% threshold)
- Filtering strategy: BindCraft → QC filters → structure filters → MD simulation → energy filters
- Parameter adjustment: LLM decides with reasoning in tight JSON format
- Hypothesis tree: Parent-child tracking with lineage
- Restart strategy: Use top K passing sequences (K=5 or K=10, configurable)

