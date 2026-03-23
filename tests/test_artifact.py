"""Tests for the Artifact DAG shared state layer (Layer 3)."""

import json
import tempfile
from pathlib import Path

import pytest

from skills._shared.artifact import (
    Artifact,
    ArtifactMetadata,
    ArtifactStatus,
    ArtifactType,
    create_artifact,
)
from skills._shared.artifact_store import ArtifactStore
from skills._shared.artifact_dag import ArtifactDAG


# ---------------------------------------------------------------------------
# Artifact dataclass tests
# ---------------------------------------------------------------------------


class TestArtifactMetadata:
    def test_to_dict_roundtrip(self):
        meta = ArtifactMetadata(
            artifact_type=ArtifactType.SEQUENCE,
            skill_name="bindcraft",
            skill_version="1.0.0",
            tags=frozenset(["binder", "peptide"]),
            extra=(("target", "IL-6"),),
        )
        d = meta.to_dict()
        restored = ArtifactMetadata.from_dict(d)
        assert restored.artifact_type == meta.artifact_type
        assert restored.skill_name == meta.skill_name
        assert restored.skill_version == meta.skill_version
        assert restored.tags == meta.tags
        assert restored.extra == meta.extra

    def test_immutability(self):
        meta = ArtifactMetadata(
            artifact_type=ArtifactType.STRUCTURE,
            skill_name="chai",
        )
        with pytest.raises(AttributeError):
            meta.skill_name = "other"  # type: ignore[misc]


class TestArtifact:
    def test_create_artifact_deterministic(self):
        meta = ArtifactMetadata(
            artifact_type=ArtifactType.SEQUENCE,
            skill_name="test-skill",
        )
        a1 = create_artifact(metadata=meta, data={"seq": "ACGT"})
        a2 = create_artifact(metadata=meta, data={"seq": "ACGT"})
        assert a1.artifact_id == a2.artifact_id

    def test_different_data_different_id(self):
        meta = ArtifactMetadata(
            artifact_type=ArtifactType.SEQUENCE,
            skill_name="test-skill",
        )
        a1 = create_artifact(metadata=meta, data={"seq": "ACGT"})
        a2 = create_artifact(metadata=meta, data={"seq": "TGCA"})
        assert a1.artifact_id != a2.artifact_id

    def test_frozen(self):
        a = create_artifact(
            metadata=ArtifactMetadata(
                artifact_type=ArtifactType.SCORE,
                skill_name="scorer",
            ),
            data={"score": 0.95},
        )
        with pytest.raises(AttributeError):
            a.data = {}  # type: ignore[misc]

    def test_is_root(self):
        a = create_artifact(
            metadata=ArtifactMetadata(artifact_type=ArtifactType.HYPOTHESIS, skill_name="h"),
            data={},
        )
        assert a.is_root()

    def test_has_parent(self):
        parent = create_artifact(
            metadata=ArtifactMetadata(artifact_type=ArtifactType.SEQUENCE, skill_name="s"),
            data={"seq": "AAA"},
        )
        child = create_artifact(
            parent_ids=(parent.artifact_id,),
            metadata=ArtifactMetadata(artifact_type=ArtifactType.STRUCTURE, skill_name="fold"),
            data={"pdb": "..."},
        )
        assert not child.is_root()
        assert child.has_parent(parent.artifact_id)
        assert not child.has_parent("nonexistent")

    def test_to_dict_from_dict_roundtrip(self):
        a = create_artifact(
            parent_ids=("abc",),
            metadata=ArtifactMetadata(
                artifact_type=ArtifactType.ANALYSIS,
                skill_name="analyzer",
                tags=frozenset(["tag1"]),
            ),
            data={"result": 42},
            run_id="run-123",
        )
        d = a.to_dict()
        restored = Artifact.from_dict(d)
        assert restored.artifact_id == a.artifact_id
        assert restored.parent_ids == a.parent_ids
        assert restored.metadata.skill_name == "analyzer"
        assert restored.data == {"result": 42}
        assert restored.run_id == "run-123"


# ---------------------------------------------------------------------------
# ArtifactStore tests
# ---------------------------------------------------------------------------


class TestArtifactStore:
    @pytest.fixture
    def store(self, tmp_path):
        return ArtifactStore(tmp_path / "store")

    def _make_artifact(self, skill="test", atype=ArtifactType.SEQUENCE, data=None):
        return create_artifact(
            metadata=ArtifactMetadata(artifact_type=atype, skill_name=skill),
            data=data or {"seq": "ACGT"},
        )

    def test_put_and_get(self, store):
        a = self._make_artifact()
        store.put(a)
        retrieved = store.get(a.artifact_id)
        assert retrieved is not None
        assert retrieved.artifact_id == a.artifact_id
        assert retrieved.data == a.data

    def test_get_missing(self, store):
        assert store.get("nonexistent") is None

    def test_delete(self, store):
        a = self._make_artifact()
        store.put(a)
        assert store.delete(a.artifact_id)
        assert store.get(a.artifact_id) is None
        assert not store.delete(a.artifact_id)  # already gone

    def test_list_all(self, store):
        a1 = self._make_artifact(data={"seq": "AAA"})
        a2 = self._make_artifact(data={"seq": "BBB"})
        store.put(a1)
        store.put(a2)
        ids = store.list_all()
        assert a1.artifact_id in ids
        assert a2.artifact_id in ids

    def test_query_by_type(self, store):
        seq = self._make_artifact(atype=ArtifactType.SEQUENCE)
        struct = self._make_artifact(atype=ArtifactType.STRUCTURE, data={"pdb": "x"})
        store.put(seq)
        store.put(struct)
        results = store.query_by_type(ArtifactType.SEQUENCE)
        assert len(results) == 1
        assert results[0].artifact_id == seq.artifact_id

    def test_query_by_skill(self, store):
        a1 = self._make_artifact(skill="chai")
        a2 = self._make_artifact(skill="bindcraft", data={"x": 1})
        store.put(a1)
        store.put(a2)
        results = store.query_by_skill("chai")
        assert len(results) == 1
        assert results[0].metadata.skill_name == "chai"

    def test_get_children(self, store):
        parent = self._make_artifact(data={"seq": "PARENT"})
        store.put(parent)
        child = create_artifact(
            parent_ids=(parent.artifact_id,),
            metadata=ArtifactMetadata(artifact_type=ArtifactType.STRUCTURE, skill_name="fold"),
            data={"pdb": "child"},
        )
        store.put(child)
        children = store.get_children(parent.artifact_id)
        assert len(children) == 1
        assert children[0].artifact_id == child.artifact_id

    def test_get_ancestors(self, store):
        root = self._make_artifact(data={"seq": "ROOT"})
        store.put(root)
        mid = create_artifact(
            parent_ids=(root.artifact_id,),
            metadata=ArtifactMetadata(artifact_type=ArtifactType.STRUCTURE, skill_name="fold"),
            data={"pdb": "mid"},
        )
        store.put(mid)
        leaf = create_artifact(
            parent_ids=(mid.artifact_id,),
            metadata=ArtifactMetadata(artifact_type=ArtifactType.SCORE, skill_name="scorer"),
            data={"score": 0.9},
        )
        store.put(leaf)
        ancestors = store.get_ancestors(leaf.artifact_id)
        ancestor_ids = {a.artifact_id for a in ancestors}
        assert mid.artifact_id in ancestor_ids
        assert root.artifact_id in ancestor_ids

    def test_get_roots(self, store):
        root = self._make_artifact(data={"seq": "ROOT"})
        store.put(root)
        child = create_artifact(
            parent_ids=(root.artifact_id,),
            metadata=ArtifactMetadata(artifact_type=ArtifactType.SCORE, skill_name="s"),
            data={},
        )
        store.put(child)
        roots = store.get_roots()
        assert len(roots) == 1
        assert roots[0].artifact_id == root.artifact_id


# ---------------------------------------------------------------------------
# ArtifactDAG high-level tests
# ---------------------------------------------------------------------------


class TestArtifactDAG:
    @pytest.fixture
    def dag(self, tmp_path):
        return ArtifactDAG(str(tmp_path / "dag"))

    def test_store_and_get(self, dag):
        a = create_artifact(
            metadata=ArtifactMetadata(artifact_type=ArtifactType.SEQUENCE, skill_name="test"),
            data={"seq": "ACGT"},
        )
        aid = dag.store(a)
        assert aid == a.artifact_id
        assert dag.get(aid) is not None

    def test_create_and_store(self, dag):
        meta = ArtifactMetadata(artifact_type=ArtifactType.HYPOTHESIS, skill_name="jnana")
        a = dag.create_and_store(metadata=meta, data={"text": "binding improves with..."})
        assert dag.get(a.artifact_id) is not None

    def test_query(self, dag):
        meta_seq = ArtifactMetadata(artifact_type=ArtifactType.SEQUENCE, skill_name="s1")
        meta_str = ArtifactMetadata(artifact_type=ArtifactType.STRUCTURE, skill_name="s2")
        dag.create_and_store(metadata=meta_seq, data={"seq": "AAA"})
        dag.create_and_store(metadata=meta_str, data={"pdb": "..."})
        results = dag.query(artifact_type=ArtifactType.SEQUENCE)
        assert len(results) == 1

    def test_get_lineage(self, dag):
        root = dag.create_and_store(
            metadata=ArtifactMetadata(artifact_type=ArtifactType.SEQUENCE, skill_name="s"),
            data={"seq": "ROOT"},
        )
        child = dag.create_and_store(
            parent_ids=(root.artifact_id,),
            metadata=ArtifactMetadata(artifact_type=ArtifactType.STRUCTURE, skill_name="fold"),
            data={"pdb": "child"},
        )
        lineage = dag.get_lineage(child.artifact_id)
        assert len(lineage) == 2
        assert lineage[0].artifact_id == child.artifact_id
        assert lineage[1].artifact_id == root.artifact_id
