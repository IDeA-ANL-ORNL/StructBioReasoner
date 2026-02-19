"""
Tests for struct_bio_reasoner.data.mutation_model — Mutation, MutationSet, MutationLibrary.
"""

from __future__ import annotations

import uuid

import pytest

from struct_bio_reasoner.data.mutation_model import (
    Mutation,
    MutationEffect,
    MutationLibrary,
    MutationSet,
    MutationType,
)


# ---------------------------------------------------------------------------
# MutationType Enum
# ---------------------------------------------------------------------------

class TestMutationType:
    def test_all_members(self):
        expected = {
            "SUBSTITUTION", "INSERTION", "DELETION", "INDEL",
            "SILENT", "NONSENSE", "FRAMESHIFT",
        }
        assert {m.name for m in MutationType} == expected

    def test_values(self):
        assert MutationType.SUBSTITUTION.value == "substitution"
        assert MutationType.FRAMESHIFT.value == "frameshift"

    def test_from_value(self):
        assert MutationType("substitution") is MutationType.SUBSTITUTION


# ---------------------------------------------------------------------------
# MutationEffect Enum
# ---------------------------------------------------------------------------

class TestMutationEffect:
    def test_all_members(self):
        expected = {
            "STABILIZING", "DESTABILIZING", "NEUTRAL",
            "ACTIVATING", "DEACTIVATING",
            "BINDING_ENHANCING", "BINDING_REDUCING", "UNKNOWN",
        }
        assert {m.name for m in MutationEffect} == expected

    def test_values(self):
        assert MutationEffect.UNKNOWN.value == "unknown"
        assert MutationEffect.STABILIZING.value == "stabilizing"


# ---------------------------------------------------------------------------
# Mutation
# ---------------------------------------------------------------------------

class TestMutation:
    def test_defaults(self):
        m = Mutation()
        assert m.position == 0
        assert m.wild_type == ""
        assert m.mutant == ""
        assert m.mutation_type == MutationType.SUBSTITUTION
        assert m.predicted_effect == MutationEffect.UNKNOWN
        assert m.prediction_confidence == 0.0
        assert m.experimental_validation is False
        assert isinstance(m.mutation_id, str)
        assert m.tools_used == []

    def test_custom_values(self):
        m = Mutation(
            position=42,
            wild_type="A",
            mutant="V",
            mutation_type=MutationType.SUBSTITUTION,
            predicted_effect=MutationEffect.STABILIZING,
            stability_change=-1.5,
            prediction_confidence=0.9,
        )
        assert m.position == 42
        assert m.wild_type == "A"
        assert m.mutant == "V"
        assert m.stability_change == -1.5

    def test_str(self):
        m = Mutation(position=42, wild_type="A", mutant="V")
        assert str(m) == "A42V"

    def test_repr(self):
        m = Mutation(
            position=10, wild_type="G", mutant="D",
            predicted_effect=MutationEffect.DESTABILIZING,
        )
        assert "G10D" in repr(m)
        assert "destabilizing" in repr(m)

    def test_unique_ids(self):
        m1 = Mutation()
        m2 = Mutation()
        assert m1.mutation_id != m2.mutation_id

    def test_to_dict(self):
        m = Mutation(
            position=42, wild_type="A", mutant="V",
            stability_change=-1.5,
            tools_used=["FoldX"],
        )
        d = m.to_dict()
        assert d["position"] == 42
        assert d["wild_type"] == "A"
        assert d["mutant"] == "V"
        assert d["mutation_type"] == "substitution"
        assert d["predicted_effect"] == "unknown"
        assert d["stability_change"] == -1.5
        assert d["tools_used"] == ["FoldX"]
        assert "mutation_id" in d
        assert "created_at" in d

    def test_from_dict_full(self):
        original = Mutation(
            position=42, wild_type="A", mutant="V",
            mutation_type=MutationType.INSERTION,
            predicted_effect=MutationEffect.BINDING_ENHANCING,
            stability_change=-2.0,
            activity_change=1.5,
            tools_used=["Rosetta", "FoldX"],
            rationale="Improve binding",
        )
        d = original.to_dict()
        restored = Mutation.from_dict(d)
        assert restored.position == 42
        assert restored.wild_type == "A"
        assert restored.mutant == "V"
        assert restored.mutation_type == MutationType.INSERTION
        assert restored.predicted_effect == MutationEffect.BINDING_ENHANCING
        assert restored.stability_change == -2.0
        assert restored.activity_change == 1.5
        assert restored.tools_used == ["Rosetta", "FoldX"]
        assert restored.rationale == "Improve binding"

    def test_from_dict_minimal(self):
        m = Mutation.from_dict({})
        assert m.position == 0
        assert m.wild_type == ""
        assert m.mutation_type == MutationType.SUBSTITUTION
        assert m.predicted_effect == MutationEffect.UNKNOWN

    def test_from_dict_preserves_id(self):
        uid = str(uuid.uuid4())
        m = Mutation.from_dict({"mutation_id": uid})
        assert m.mutation_id == uid

    def test_is_conservative_hydrophobic(self):
        m = Mutation(wild_type="A", mutant="I")
        assert m.is_conservative() is True

    def test_is_conservative_polar(self):
        m = Mutation(wild_type="N", mutant="Q")
        assert m.is_conservative() is True

    def test_is_conservative_positive_charged(self):
        m = Mutation(wild_type="K", mutant="R")
        assert m.is_conservative() is True

    def test_is_conservative_negative_charged(self):
        m = Mutation(wild_type="D", mutant="E")
        assert m.is_conservative() is True

    def test_is_not_conservative(self):
        m = Mutation(wild_type="A", mutant="D")
        assert m.is_conservative() is False

    def test_is_conservative_special(self):
        m = Mutation(wild_type="C", mutant="G")
        assert m.is_conservative() is True

    def test_get_chemical_change_conservative(self):
        m = Mutation(wild_type="I", mutant="L")
        assert m.get_chemical_change() == "conservative"

    def test_get_chemical_change_hydrophobic_to_polar(self):
        m = Mutation(wild_type="I", mutant="N")
        assert m.get_chemical_change() == "hydrophobic_to_polar"

    def test_get_chemical_change_polar_to_hydrophobic(self):
        m = Mutation(wild_type="N", mutant="I")
        assert m.get_chemical_change() == "polar_to_hydrophobic"

    def test_get_chemical_change_charge_reversal(self):
        m = Mutation(wild_type="K", mutant="D")
        assert m.get_chemical_change() == "charge_reversal"

    def test_get_chemical_change_charge_reversal_reverse(self):
        m = Mutation(wild_type="E", mutant="R")
        assert m.get_chemical_change() == "charge_reversal"

    def test_get_chemical_change_moderate(self):
        m = Mutation(wild_type="C", mutant="K")
        assert m.get_chemical_change() == "moderate"

    def test_get_chemical_change_unknown_residues(self):
        m = Mutation(wild_type="X", mutant="Z")
        # Both unknown — should not crash
        result = m.get_chemical_change()
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# MutationSet
# ---------------------------------------------------------------------------

class TestMutationSet:
    def _make_mutation(self, pos, wt, mut):
        return Mutation(position=pos, wild_type=wt, mutant=mut)

    def test_defaults(self):
        ms = MutationSet()
        assert ms.mutations == []
        assert ms.name == ""
        assert ms.set_type == ""
        assert isinstance(ms.set_id, str)

    def test_add_mutation(self):
        ms = MutationSet()
        m = self._make_mutation(10, "A", "V")
        ms.add_mutation(m)
        assert ms.get_mutation_count() == 1

    def test_remove_mutation(self):
        ms = MutationSet()
        m = self._make_mutation(10, "A", "V")
        ms.add_mutation(m)
        ms.remove_mutation(m.mutation_id)
        assert ms.get_mutation_count() == 0

    def test_remove_nonexistent(self):
        ms = MutationSet()
        m = self._make_mutation(10, "A", "V")
        ms.add_mutation(m)
        ms.remove_mutation("nonexistent-id")
        assert ms.get_mutation_count() == 1

    def test_get_positions(self):
        ms = MutationSet(mutations=[
            self._make_mutation(10, "A", "V"),
            self._make_mutation(20, "G", "D"),
            self._make_mutation(30, "K", "R"),
        ])
        assert ms.get_positions() == [10, 20, 30]

    def test_has_overlapping_positions_false(self):
        ms = MutationSet(mutations=[
            self._make_mutation(10, "A", "V"),
            self._make_mutation(20, "G", "D"),
        ])
        assert ms.has_overlapping_positions() is False

    def test_has_overlapping_positions_true(self):
        ms = MutationSet(mutations=[
            self._make_mutation(10, "A", "V"),
            self._make_mutation(10, "A", "G"),
        ])
        assert ms.has_overlapping_positions() is True

    def test_get_mutation_string(self):
        ms = MutationSet(mutations=[
            self._make_mutation(10, "A", "V"),
            self._make_mutation(20, "G", "D"),
        ])
        assert ms.get_mutation_string() == "A10V/G20D"

    def test_get_mutation_string_empty(self):
        ms = MutationSet()
        assert ms.get_mutation_string() == ""

    def test_to_dict(self):
        m = self._make_mutation(10, "A", "V")
        ms = MutationSet(
            name="test_set",
            description="A test mutation set",
            mutations=[m],
            set_type="single",
            design_strategy="rational",
            combined_stability_change=-1.0,
        )
        d = ms.to_dict()
        assert d["name"] == "test_set"
        assert d["set_type"] == "single"
        assert d["combined_stability_change"] == -1.0
        assert len(d["mutations"]) == 1
        assert d["mutations"][0]["position"] == 10

    def test_to_dict_empty(self):
        ms = MutationSet()
        d = ms.to_dict()
        assert d["mutations"] == []
        assert "set_id" in d


# ---------------------------------------------------------------------------
# MutationLibrary
# ---------------------------------------------------------------------------

class TestMutationLibrary:
    def _make_set(self, n_mutations=1):
        mutations = [
            Mutation(position=i, wild_type="A", mutant="V")
            for i in range(n_mutations)
        ]
        return MutationSet(mutations=mutations)

    def test_defaults(self):
        lib = MutationLibrary()
        assert lib.mutation_sets == []
        assert lib.actual_size == 0
        assert lib.theoretical_size == 0
        assert lib.coverage == 0.0

    def test_add_mutation_set(self):
        lib = MutationLibrary()
        ms = self._make_set(2)
        lib.add_mutation_set(ms)
        assert lib.actual_size == 1
        assert len(lib.mutation_sets) == 1

    def test_add_multiple_sets(self):
        lib = MutationLibrary()
        for _ in range(5):
            lib.add_mutation_set(self._make_set())
        assert lib.actual_size == 5

    def test_calculate_theoretical_size(self):
        lib = MutationLibrary(
            allowed_amino_acids={
                10: ["A", "V", "I"],
                20: ["D", "E"],
            }
        )
        size = lib.calculate_theoretical_size()
        assert size == 6  # 3 * 2
        assert lib.theoretical_size == 6

    def test_calculate_theoretical_size_empty(self):
        lib = MutationLibrary()
        assert lib.calculate_theoretical_size() == 0

    def test_calculate_coverage(self):
        lib = MutationLibrary(
            allowed_amino_acids={10: ["A", "V"], 20: ["D", "E"]},
        )
        lib.calculate_theoretical_size()  # = 4
        lib.add_mutation_set(self._make_set())
        lib.add_mutation_set(self._make_set())
        coverage = lib.calculate_coverage()
        assert coverage == pytest.approx(0.5)  # 2/4

    def test_calculate_coverage_zero_theoretical(self):
        lib = MutationLibrary()
        assert lib.calculate_coverage() == 0.0

    def test_calculate_coverage_auto_computes_theoretical(self):
        lib = MutationLibrary(
            allowed_amino_acids={10: ["A", "V", "I", "L"]},
        )
        lib.add_mutation_set(self._make_set())
        coverage = lib.calculate_coverage()
        assert lib.theoretical_size == 4
        assert coverage == pytest.approx(0.25)

    def test_get_library_summary(self):
        lib = MutationLibrary(
            name="test_lib",
            library_type="saturation",
            target_positions=[10, 20],
            allowed_amino_acids={10: ["A", "V"], 20: ["D"]},
        )
        lib.calculate_theoretical_size()
        lib.add_mutation_set(self._make_set())
        summary = lib.get_library_summary()
        assert summary["name"] == "test_lib"
        assert summary["library_type"] == "saturation"
        assert summary["target_positions"] == [10, 20]
        assert summary["theoretical_size"] == 2
        assert summary["actual_size"] == 1
        assert summary["mutation_sets_count"] == 1
