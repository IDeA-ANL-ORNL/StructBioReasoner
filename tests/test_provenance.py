"""Tests for the provenance tracker and skill registry."""

from pathlib import Path

import pytest

from skills._shared.provenance import ProvenanceRecord, ProvenanceTracker
from skills._shared.registry import SkillInfo, SkillRegistry, _parse_yaml_frontmatter


# ---------------------------------------------------------------------------
# ProvenanceRecord tests
# ---------------------------------------------------------------------------


class TestProvenanceRecord:
    def test_to_dict_from_dict_roundtrip(self):
        rec = ProvenanceRecord(
            run_id="run-1",
            skill_name="bindcraft",
            skill_version="2.0.0",
            input_artifact_ids=["a1", "a2"],
            output_artifact_ids=["a3"],
            parameters={"num_designs": 10},
            status="success",
            metadata={"cluster": "polaris"},
        )
        d = rec.to_dict()
        restored = ProvenanceRecord.from_dict(d)
        assert restored.run_id == "run-1"
        assert restored.skill_name == "bindcraft"
        assert restored.input_artifact_ids == ["a1", "a2"]
        assert restored.output_artifact_ids == ["a3"]
        assert restored.parameters == {"num_designs": 10}
        assert restored.status == "success"

    def test_defaults(self):
        rec = ProvenanceRecord()
        assert rec.status == "running"
        assert rec.error is None
        assert rec.finished_at is None


# ---------------------------------------------------------------------------
# ProvenanceTracker tests
# ---------------------------------------------------------------------------


class TestProvenanceTracker:
    @pytest.fixture
    def tracker(self, tmp_path):
        return ProvenanceTracker(tmp_path / "prov")

    def test_start_and_finish_run(self, tracker):
        rec = tracker.start_run(
            skill_name="chai",
            input_artifact_ids=["input-1"],
            parameters={"model": "v2"},
        )
        assert rec.status == "running"
        assert rec.skill_name == "chai"

        finished = tracker.finish_run(
            run_id=rec.run_id,
            output_artifact_ids=["output-1"],
            status="success",
        )
        assert finished is not None
        assert finished.status == "success"
        assert finished.output_artifact_ids == ["output-1"]
        assert finished.finished_at is not None

    def test_finish_nonexistent(self, tracker):
        result = tracker.finish_run("no-such-run", [])
        assert result is None

    def test_list_runs(self, tracker):
        r1 = tracker.start_run(skill_name="s1")
        r2 = tracker.start_run(skill_name="s2")
        runs = tracker.list_runs()
        assert r1.run_id in runs
        assert r2.run_id in runs

    def test_query_by_skill(self, tracker):
        tracker.start_run(skill_name="chai")
        tracker.start_run(skill_name="bindcraft")
        tracker.start_run(skill_name="chai")
        results = tracker.query_by_skill("chai")
        assert len(results) == 2

    def test_query_by_artifact(self, tracker):
        r1 = tracker.start_run(skill_name="s1", input_artifact_ids=["art-1"])
        tracker.finish_run(r1.run_id, output_artifact_ids=["art-2"])
        r2 = tracker.start_run(skill_name="s2", input_artifact_ids=["art-2"])
        tracker.finish_run(r2.run_id, output_artifact_ids=["art-3"])

        # art-2 was output of r1 and input of r2
        results = tracker.query_by_artifact("art-2")
        assert len(results) == 2

    def test_failed_run(self, tracker):
        rec = tracker.start_run(skill_name="broken")
        finished = tracker.finish_run(
            rec.run_id,
            output_artifact_ids=[],
            status="failed",
            error="CUDA out of memory",
        )
        assert finished is not None
        assert finished.status == "failed"
        assert finished.error == "CUDA out of memory"


# ---------------------------------------------------------------------------
# SkillRegistry tests
# ---------------------------------------------------------------------------


class TestYamlFrontmatter:
    def test_basic_parse(self):
        text = "---\nname: test-skill\ndescription: A test\n---\n# Content"
        result = _parse_yaml_frontmatter(text)
        assert result["name"] == "test-skill"
        assert result["description"] == "A test"

    def test_no_frontmatter(self):
        assert _parse_yaml_frontmatter("# Just markdown") == {}


class TestSkillRegistry:
    @pytest.fixture
    def skills_dir(self, tmp_path):
        """Create a mock skills directory with two skills."""
        (tmp_path / "bindcraft").mkdir()
        (tmp_path / "bindcraft" / "SKILL.md").write_text(
            "---\nname: bindcraft\ndescription: Binder design\n---\n# BindCraft\n"
        )
        (tmp_path / "chai").mkdir()
        (tmp_path / "chai" / "SKILL.md").write_text(
            "---\nname: chai\ndescription: Structure prediction\n---\n# Chai\n"
        )
        # _shared should be skipped (starts with _)
        (tmp_path / "_shared").mkdir()
        # no-skill has no SKILL.md — should be skipped
        (tmp_path / "no-skill").mkdir()
        return tmp_path

    def test_discover(self, skills_dir):
        reg = SkillRegistry(skills_dir)
        count = reg.discover()
        assert count == 2
        assert reg.has_skill("bindcraft")
        assert reg.has_skill("chai")
        assert not reg.has_skill("_shared")
        assert not reg.has_skill("no-skill")

    def test_list_skills(self, skills_dir):
        reg = SkillRegistry(skills_dir)
        reg.discover()
        names = reg.list_names()
        assert "bindcraft" in names
        assert "chai" in names

    def test_get(self, skills_dir):
        reg = SkillRegistry(skills_dir)
        reg.discover()
        info = reg.get("bindcraft")
        assert info is not None
        assert info.name == "bindcraft"
        assert info.description == "Binder design"

    def test_manual_register(self):
        reg = SkillRegistry(Path("/nonexistent"))
        reg.register(SkillInfo(name="custom", description="Manual skill"))
        assert reg.has_skill("custom")

    def test_discover_real_skills(self):
        """Test against the actual skills/ directory in the repo."""
        repo_skills = Path(__file__).parent.parent / "skills"
        if not repo_skills.exists():
            pytest.skip("skills/ directory not found")
        reg = SkillRegistry(repo_skills)
        count = reg.discover()
        assert count >= 1  # at least bindcraft has SKILL.md
        assert reg.has_skill("bindcraft")
