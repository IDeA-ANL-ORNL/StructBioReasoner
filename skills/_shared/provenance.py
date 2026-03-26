"""
Provenance tracker for skill executions.

Records every skill call with its inputs, outputs (artifact IDs), timestamps,
and optional metadata so the full computation history is reproducible.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

_UTC = timezone.utc
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProvenanceRecord:
    """A single provenance entry recording one skill invocation."""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    skill_name: str = ""
    skill_version: str = "0.1.0"
    started_at: str = field(default_factory=lambda: datetime.now(tz=_UTC).isoformat())
    finished_at: Optional[str] = None
    input_artifact_ids: List[str] = field(default_factory=list)
    output_artifact_ids: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: str = "running"  # "running", "success", "failed"
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "skill_name": self.skill_name,
            "skill_version": self.skill_version,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "input_artifact_ids": self.input_artifact_ids,
            "output_artifact_ids": self.output_artifact_ids,
            "parameters": self.parameters,
            "status": self.status,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProvenanceRecord":
        return cls(
            run_id=d["run_id"],
            skill_name=d.get("skill_name", ""),
            skill_version=d.get("skill_version", "0.1.0"),
            started_at=d.get("started_at", datetime.now(tz=_UTC).isoformat()),
            finished_at=d.get("finished_at"),
            input_artifact_ids=d.get("input_artifact_ids", []),
            output_artifact_ids=d.get("output_artifact_ids", []),
            parameters=d.get("parameters", {}),
            status=d.get("status", "running"),
            error=d.get("error"),
            metadata=d.get("metadata", {}),
        )


class ProvenanceTracker:
    """
    Filesystem-backed provenance log.

    Layout::

        root/
          provenance/
            <run_id>.json
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._dir = self._root / "provenance"
        self._dir.mkdir(parents=True, exist_ok=True)

    def start_run(
        self,
        skill_name: str,
        skill_version: str = "0.1.0",
        input_artifact_ids: Optional[List[str]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProvenanceRecord:
        """Begin a new provenance run and persist the initial record."""
        record = ProvenanceRecord(
            skill_name=skill_name,
            skill_version=skill_version,
            input_artifact_ids=input_artifact_ids or [],
            parameters=parameters or {},
            metadata=metadata or {},
        )
        self._save(record)
        logger.debug("Started provenance run %s for skill %s", record.run_id, skill_name)
        return record

    def finish_run(
        self,
        run_id: str,
        output_artifact_ids: List[str],
        status: str = "success",
        error: Optional[str] = None,
    ) -> Optional[ProvenanceRecord]:
        """Mark a run as finished, recording outputs and final status."""
        record = self.get(run_id)
        if record is None:
            logger.warning("Provenance run %s not found", run_id)
            return None
        # ProvenanceRecord is mutable (not frozen)
        record.finished_at = datetime.now(tz=_UTC).isoformat()
        record.output_artifact_ids = output_artifact_ids
        record.status = status
        record.error = error
        self._save(record)
        logger.debug("Finished provenance run %s — %s", run_id, status)
        return record

    def get(self, run_id: str) -> Optional[ProvenanceRecord]:
        path = self._dir / f"{run_id}.json"
        if not path.exists():
            return None
        return ProvenanceRecord.from_dict(json.loads(path.read_text()))

    def list_runs(self) -> List[str]:
        return [p.stem for p in sorted(self._dir.glob("*.json"))]

    def query_by_skill(self, skill_name: str) -> List[ProvenanceRecord]:
        results: List[ProvenanceRecord] = []
        for run_id in self.list_runs():
            rec = self.get(run_id)
            if rec and rec.skill_name == skill_name:
                results.append(rec)
        return results

    def query_by_artifact(self, artifact_id: str) -> List[ProvenanceRecord]:
        """Find all runs that consumed or produced a given artifact."""
        results: List[ProvenanceRecord] = []
        for run_id in self.list_runs():
            rec = self.get(run_id)
            if rec is None:
                continue
            if artifact_id in rec.input_artifact_ids or artifact_id in rec.output_artifact_ids:
                results.append(rec)
        return results

    def _save(self, record: ProvenanceRecord) -> None:
        path = self._dir / f"{record.run_id}.json"
        path.write_text(json.dumps(record.to_dict(), indent=2, default=str))
