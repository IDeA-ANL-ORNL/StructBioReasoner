"""Artifact DAG — high-level interface for the shared state layer (Layer 3).

Wraps ArtifactStore with convenience methods for the three consuming layers:
  - OpenClaw writes artifacts when skills produce outputs
  - Jnana reads artifacts to evaluate results
  - Academy agents produce/consume artifacts during distributed execution
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .artifact import (
    Artifact,
    ArtifactMetadata,
    ArtifactStatus,
    ArtifactType,
    create_artifact,
)
from .artifact_store import ArtifactStore
from .provenance import ProvenanceTracker


class ArtifactDAG:
    """Directed acyclic graph of computational artifacts.

    Provides shared state and provenance tracking across all four layers.
    Backed by a filesystem-based ArtifactStore and ProvenanceTracker.
    """

    def __init__(self, storage_path: str = "./artifacts") -> None:
        self._storage_path = storage_path
        self._store = ArtifactStore(storage_path)
        self._provenance = ProvenanceTracker(storage_path)

    @property
    def artifact_store(self) -> ArtifactStore:
        return self._store

    @property
    def provenance(self) -> ProvenanceTracker:
        return self._provenance

    def store(self, artifact: Artifact) -> str:
        """Store an artifact and return its ID."""
        self._store.put(artifact)
        return artifact.artifact_id

    def get(self, artifact_id: str) -> Optional[Artifact]:
        """Retrieve an artifact by ID."""
        return self._store.get(artifact_id)

    def get_lineage(self, artifact_id: str) -> List[Artifact]:
        """Get the full lineage (ancestor chain) of an artifact."""
        ancestors = self._store.get_ancestors(artifact_id)
        art = self._store.get(artifact_id)
        if art:
            return [art] + ancestors
        return ancestors

    def query(
        self,
        artifact_type: Optional[ArtifactType] = None,
        producing_skill: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Artifact]:
        """Query artifacts by type, producing skill, or tags."""
        if artifact_type and not producing_skill:
            results = self._store.query_by_type(artifact_type)
        elif producing_skill and not artifact_type:
            results = self._store.query_by_skill(producing_skill)
        elif artifact_type and producing_skill:
            by_type = {a.artifact_id for a in self._store.query_by_type(artifact_type)}
            results = [
                a for a in self._store.query_by_skill(producing_skill)
                if a.artifact_id in by_type
            ]
        else:
            results = [
                a for aid in self._store.list_all()
                if (a := self._store.get(aid)) is not None
            ]

        if tags:
            tag_set = set(tags)
            results = [a for a in results if tag_set & set(a.metadata.tags)]

        return results

    def create_and_store(
        self,
        *,
        parent_ids: Tuple[str, ...] = (),
        metadata: ArtifactMetadata,
        data: Any,
        run_id: Optional[str] = None,
    ) -> Artifact:
        """Create a content-addressed artifact and persist it."""
        artifact = create_artifact(
            parent_ids=parent_ids,
            metadata=metadata,
            data=data,
            run_id=run_id,
        )
        self._store.put(artifact)
        return artifact
