"""
Artifact DAG — shared state layer (Layer 3).

Artifacts are immutable, typed data objects that form a directed acyclic graph
through parent lineage. They serve as the shared memory between:
  - OpenClaw skills (Layer 1) — WRITE artifacts when producing outputs
  - Jnana (Layer 2) — READS artifacts to evaluate results and update hypotheses
  - Academy agents (Layer 4) — produce/consume artifacts during distributed execution
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

_UTC = timezone.utc


class ArtifactType(Enum):
    """Classification of artifact content types."""
    SEQUENCE = "sequence"
    STRUCTURE = "structure"
    PDB_STRUCTURE = "pdb_structure"
    HYPOTHESIS = "hypothesis"
    ANALYSIS = "analysis"
    SIMULATION = "simulation"
    TRAJECTORY = "trajectory"
    SCORE = "score"
    SCORE_TABLE = "score_table"
    ALIGNMENT = "alignment"
    EMBEDDING = "embedding"
    LITERATURE = "literature"
    PARAMETER_SET = "parameter_set"
    WORKFLOW_CONFIG = "workflow_config"
    VISUALIZATION = "visualization"
    RAW_OUTPUT = "raw_output"


class ArtifactStatus(Enum):
    """Lifecycle status of an artifact."""
    CREATED = "created"
    VALIDATED = "validated"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ArtifactMetadata:
    """Typed, immutable metadata attached to an artifact."""
    artifact_type: ArtifactType
    skill_name: str
    skill_version: str = "0.1.0"
    tags: FrozenSet[str] = field(default_factory=frozenset)
    extra: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_type": self.artifact_type.value,
            "skill_name": self.skill_name,
            "skill_version": self.skill_version,
            "tags": sorted(self.tags),
            "extra": {k: v for k, v in self.extra},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactMetadata":
        return cls(
            artifact_type=ArtifactType(data["artifact_type"]),
            skill_name=data["skill_name"],
            skill_version=data.get("skill_version", "0.1.0"),
            tags=frozenset(data.get("tags", [])),
            extra=tuple(
                (k, v) for k, v in data.get("extra", {}).items()
            ),
        )


@dataclass(frozen=True)
class Artifact:
    """
    An immutable artifact node in the provenance DAG.

    Artifacts are content-addressed: the artifact_id is a deterministic hash
    of (parent_ids, metadata, data) so identical inputs always produce the
    same artifact identity.

    Attributes:
        artifact_id: Deterministic content hash (SHA-256 hex prefix).
        parent_ids: Tuple of parent artifact IDs forming the DAG edges.
        metadata: Typed, immutable metadata about this artifact.
        data: The artifact payload (must be JSON-serialisable).
        created_at: ISO-8601 creation timestamp.
        status: Lifecycle status of this artifact.
        run_id: ID of the provenance run that produced this artifact.
    """
    artifact_id: str
    parent_ids: Tuple[str, ...] = field(default_factory=tuple)
    metadata: ArtifactMetadata = field(
        default_factory=lambda: ArtifactMetadata(
            artifact_type=ArtifactType.RAW_OUTPUT,
            skill_name="unknown",
        )
    )
    data: Any = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(tz=_UTC).isoformat())
    status: ArtifactStatus = ArtifactStatus.CREATED
    run_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "parent_ids": list(self.parent_ids),
            "metadata": self.metadata.to_dict(),
            "data": self.data,
            "created_at": self.created_at,
            "status": self.status.value,
            "run_id": self.run_id,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Artifact":
        return cls(
            artifact_id=d["artifact_id"],
            parent_ids=tuple(d.get("parent_ids", [])),
            metadata=ArtifactMetadata.from_dict(d["metadata"]),
            data=d.get("data", {}),
            created_at=d.get("created_at", datetime.now(tz=_UTC).isoformat()),
            status=ArtifactStatus(d.get("status", "created")),
            run_id=d.get("run_id"),
        )

    # -- DAG helpers ----------------------------------------------------------

    def is_root(self) -> bool:
        return len(self.parent_ids) == 0

    def has_parent(self, parent_id: str) -> bool:
        return parent_id in self.parent_ids

    def lineage_depth(self, store: "ArtifactStore") -> int:
        """Walk parents to compute depth (root = 0)."""
        if self.is_root():
            return 0
        max_depth = 0
        for pid in self.parent_ids:
            parent = store.get(pid)
            if parent is not None:
                max_depth = max(max_depth, parent.lineage_depth(store) + 1)
        return max_depth


# ---------------------------------------------------------------------------
# Factory helper — builds an Artifact with a content-addressed ID
# ---------------------------------------------------------------------------

def create_artifact(
    *,
    parent_ids: Tuple[str, ...] = (),
    metadata: ArtifactMetadata,
    data: Any,
    run_id: Optional[str] = None,
    status: ArtifactStatus = ArtifactStatus.CREATED,
) -> Artifact:
    """Create a new Artifact with a deterministic content-addressed ID."""
    canonical = json.dumps(
        {
            "parent_ids": sorted(parent_ids),
            "metadata": metadata.to_dict(),
            "data": data,
        },
        sort_keys=True,
        default=str,
    )
    artifact_id = hashlib.sha256(canonical.encode()).hexdigest()[:16]

    return Artifact(
        artifact_id=artifact_id,
        parent_ids=parent_ids,
        metadata=metadata,
        data=data,
        created_at=datetime.now(tz=_UTC).isoformat(),
        status=status,
        run_id=run_id,
    )
