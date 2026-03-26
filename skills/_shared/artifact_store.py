"""
Filesystem-backed artifact store.

Stores artifacts as JSON files in a configurable directory, with indexing by
artifact type, skill name, and lineage for efficient queries.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set

from .artifact import Artifact, ArtifactStatus, ArtifactType

logger = logging.getLogger(__name__)


class ArtifactStore:
    """
    Persistent, filesystem-backed store for Artifact objects.

    Layout::

        root/
          artifacts/
            <artifact_id>.json
          index/
            by_type/<type>.json        # list of artifact IDs
            by_skill/<skill>.json      # list of artifact IDs
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._artifacts_dir = self._root / "artifacts"
        self._index_dir = self._root / "index"
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        (self._index_dir / "by_type").mkdir(parents=True, exist_ok=True)
        (self._index_dir / "by_skill").mkdir(parents=True, exist_ok=True)

    # -- CRUD ----------------------------------------------------------------

    def put(self, artifact: Artifact) -> None:
        """Persist an artifact and update indexes."""
        path = self._artifacts_dir / f"{artifact.artifact_id}.json"
        path.write_text(json.dumps(artifact.to_dict(), indent=2, default=str))
        self._index_add("by_type", artifact.metadata.artifact_type.value, artifact.artifact_id)
        self._index_add("by_skill", artifact.metadata.skill_name, artifact.artifact_id)
        logger.debug("Stored artifact %s", artifact.artifact_id)

    def get(self, artifact_id: str) -> Optional[Artifact]:
        """Retrieve an artifact by ID, or None if not found."""
        path = self._artifacts_dir / f"{artifact_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return Artifact.from_dict(data)

    def delete(self, artifact_id: str) -> bool:
        """Remove an artifact and clean up indexes. Returns True if found."""
        path = self._artifacts_dir / f"{artifact_id}.json"
        if not path.exists():
            return False
        artifact = self.get(artifact_id)
        path.unlink()
        if artifact:
            self._index_remove("by_type", artifact.metadata.artifact_type.value, artifact_id)
            self._index_remove("by_skill", artifact.metadata.skill_name, artifact_id)
        return True

    def list_all(self) -> List[str]:
        """Return all artifact IDs in the store."""
        return [
            p.stem for p in sorted(self._artifacts_dir.glob("*.json"))
        ]

    # -- Query helpers -------------------------------------------------------

    def query_by_type(self, artifact_type: ArtifactType) -> List[Artifact]:
        """Return all artifacts of a given type."""
        ids = self._index_read("by_type", artifact_type.value)
        return [a for aid in ids if (a := self.get(aid)) is not None]

    def query_by_skill(self, skill_name: str) -> List[Artifact]:
        """Return all artifacts produced by a given skill."""
        ids = self._index_read("by_skill", skill_name)
        return [a for aid in ids if (a := self.get(aid)) is not None]

    def query_by_status(self, status: ArtifactStatus) -> List[Artifact]:
        """Return all artifacts with a given status (full scan)."""
        results: List[Artifact] = []
        for aid in self.list_all():
            art = self.get(aid)
            if art and art.status == status:
                results.append(art)
        return results

    def get_children(self, artifact_id: str) -> List[Artifact]:
        """Return all artifacts that list *artifact_id* as a parent."""
        children: List[Artifact] = []
        for aid in self.list_all():
            art = self.get(aid)
            if art and artifact_id in art.parent_ids:
                children.append(art)
        return children

    def get_ancestors(self, artifact_id: str) -> List[Artifact]:
        """Walk the DAG upward and return all ancestors (breadth-first)."""
        visited: Set[str] = set()
        queue = [artifact_id]
        ancestors: List[Artifact] = []
        while queue:
            current_id = queue.pop(0)
            art = self.get(current_id)
            if art is None:
                continue
            for pid in art.parent_ids:
                if pid not in visited:
                    visited.add(pid)
                    parent = self.get(pid)
                    if parent:
                        ancestors.append(parent)
                        queue.append(pid)
        return ancestors

    def get_roots(self) -> List[Artifact]:
        """Return all root artifacts (no parents)."""
        return [
            a for aid in self.list_all()
            if (a := self.get(aid)) is not None and a.is_root()
        ]

    # -- Index management (private) ------------------------------------------

    def _index_path(self, category: str, key: str) -> Path:
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self._index_dir / category / f"{safe_key}.json"

    def _index_read(self, category: str, key: str) -> List[str]:
        path = self._index_path(category, key)
        if not path.exists():
            return []
        return json.loads(path.read_text())

    def _index_add(self, category: str, key: str, artifact_id: str) -> None:
        ids = self._index_read(category, key)
        if artifact_id not in ids:
            ids.append(artifact_id)
        path = self._index_path(category, key)
        path.write_text(json.dumps(ids))

    def _index_remove(self, category: str, key: str, artifact_id: str) -> None:
        ids = self._index_read(category, key)
        if artifact_id in ids:
            ids.remove(artifact_id)
            path = self._index_path(category, key)
            path.write_text(json.dumps(ids))
