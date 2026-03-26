"""Shared infrastructure for the StructBioReasoner skills layer.

Provides:
  - Artifact / ArtifactStore / ArtifactDAG — immutable DAG-structured data objects (Layer 3)
  - ProvenanceTracker — skill execution history
  - SkillRegistry — skill discovery and metadata
"""

from .artifact import (
    Artifact,
    ArtifactMetadata,
    ArtifactStatus,
    ArtifactType,
    create_artifact,
)
from .artifact_store import ArtifactStore
from .artifact_dag import ArtifactDAG
from .provenance import ProvenanceRecord, ProvenanceTracker
from .registry import SkillInfo, SkillRegistry

__all__ = [
    "Artifact",
    "ArtifactDAG",
    "ArtifactMetadata",
    "ArtifactStatus",
    "ArtifactType",
    "ArtifactStore",
    "ProvenanceRecord",
    "ProvenanceTracker",
    "SkillInfo",
    "SkillRegistry",
    "create_artifact",
]
