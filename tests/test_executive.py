"""
Tests for the TestExecutive and LocalDirector — helper functions, config, lifecycle.

These tests mock Academy and Parsl to test orchestration logic.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from struct_bio_reasoner.agents.executive.test_executive import (
    LocalDirector,
    TestExecutive,
    TestExecutiveConfig,
    build_director_runtime,
    split_list,
)


# ---------------------------------------------------------------------------
# split_list helper
# ---------------------------------------------------------------------------

class TestSplitList:
    def test_even_split(self):
        result = split_list([0, 1, 2, 3], 2)
        assert result == [[0, 1], [2, 3]]

    def test_uneven_split(self):
        result = split_list([0, 1, 2, 3, 4], 2)
        assert result == [[0, 1, 2], [3, 4]]

    def test_single_chunk(self):
        result = split_list([0, 1, 2], 1)
        assert result == [[0, 1, 2]]

    def test_more_chunks_than_items(self):
        result = split_list([0, 1], 4)
        assert len(result) == 4
        non_empty = [c for c in result if c]
        assert len(non_empty) == 2

    def test_empty_list(self):
        result = split_list([], 3)
        assert len(result) == 3
        assert all(c == [] for c in result)

    def test_string_items(self):
        result = split_list(["a", "b", "c", "d", "e", "f"], 3)
        assert result == [["a", "b"], ["c", "d"], ["e", "f"]]

    def test_twelve_into_two(self):
        items = [str(i) for i in range(12)]
        result = split_list(items, 2)
        assert len(result) == 2
        assert len(result[0]) == 6
        assert len(result[1]) == 6


# ---------------------------------------------------------------------------
# build_director_runtime helper
# ---------------------------------------------------------------------------

class TestBuildDirectorRuntime:
    def test_basic(self):
        base = {
            "reasoner": {"research_goal": "test"},
            "parsl": {"nodes": 2},
        }
        runtime = build_director_runtime(base, ["0", "1"])
        assert runtime["reasoner"]["research_goal"] == "test"
        assert runtime["parsl"]["available_accelerators"] == ["0", "1"]
        assert runtime["parsl"]["nodes"] == 2

    def test_overwrites_accelerators(self):
        base = {
            "parsl": {"available_accelerators": ["0", "1", "2", "3"]},
        }
        runtime = build_director_runtime(base, ["2", "3"])
        assert runtime["parsl"]["available_accelerators"] == ["2", "3"]

    def test_no_parsl_section(self):
        base = {"reasoner": {"goal": "x"}}
        runtime = build_director_runtime(base, ["0"])
        assert runtime["parsl"]["available_accelerators"] == ["0"]

    def test_does_not_mutate_original(self):
        base = {"parsl": {"nodes": 1, "available_accelerators": ["0", "1"]}}
        runtime = build_director_runtime(base, ["0"])
        assert base["parsl"]["available_accelerators"] == ["0", "1"]


# ---------------------------------------------------------------------------
# TestExecutiveConfig
# ---------------------------------------------------------------------------

class TestTestExecutiveConfig:
    def test_defaults(self):
        cfg = TestExecutiveConfig()
        assert cfg.config_path == "config/binder_config.yaml"
        assert cfg.num_directors == 2
        assert cfg.output_dir == "test_executive_output"
        assert cfg.max_runtime_minutes == 60.0
        assert cfg.review_interval_seconds == 120.0

    def test_custom(self):
        cfg = TestExecutiveConfig(
            config_path="/my/config.yaml",
            num_directors=4,
            output_dir="/my/output",
            max_runtime_minutes=120,
            review_interval_seconds=30,
        )
        assert cfg.num_directors == 4
        assert cfg.max_runtime_minutes == 120


# ---------------------------------------------------------------------------
# TestExecutive._should_stop
# ---------------------------------------------------------------------------

class TestShouldStop:
    def _make_executive(self, tmp_path):
        """Create a TestExecutive with a minimal config file."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "parsl:\n  available_accelerators: ['0','1','2','3']\n"
            "reasoner:\n  research_goal: test\n"
        )
        cfg = TestExecutiveConfig(
            config_path=str(config_path),
            num_directors=2,
            output_dir=str(tmp_path / "out"),
            max_runtime_minutes=1.0,
        )
        return TestExecutive(cfg)

    def test_stop_when_shutdown_requested(self, tmp_path):
        exe = self._make_executive(tmp_path)
        exe._shutdown_requested = True
        exe.director_tasks = {}
        assert exe._should_stop() is True

    def test_stop_when_max_runtime_exceeded(self, tmp_path):
        exe = self._make_executive(tmp_path)
        exe._start_time = time.monotonic() - 120  # 2 minutes ago
        exe.director_tasks = {"d0": MagicMock(done=lambda: False)}
        assert exe._should_stop() is True

    def test_stop_when_all_directors_done(self, tmp_path):
        exe = self._make_executive(tmp_path)
        exe._start_time = time.monotonic()
        done_task = MagicMock()
        done_task.done.return_value = True
        exe.director_tasks = {"d0": done_task, "d1": done_task}
        assert exe._should_stop() is True

    def test_continue_when_running(self, tmp_path):
        exe = self._make_executive(tmp_path)
        exe._start_time = time.monotonic()
        running_task = MagicMock()
        running_task.done.return_value = False
        exe.director_tasks = {"d0": running_task}
        assert exe._should_stop() is False


# ---------------------------------------------------------------------------
# TestExecutive.__init__
# ---------------------------------------------------------------------------

class TestExecutiveInit:
    def test_init(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "parsl:\n  available_accelerators: ['0','1','2','3']\n"
        )
        cfg = TestExecutiveConfig(
            config_path=str(config_path),
            num_directors=2,
            output_dir=str(tmp_path / "out"),
        )
        exe = TestExecutive(cfg)
        assert len(exe.accel_chunks) == 2
        assert len(exe.accel_chunks[0]) == 2
        assert len(exe.accel_chunks[1]) == 2
        assert exe.experiment_id  # UUID generated
        assert exe._shutdown_requested is False

    def test_init_creates_output_dir(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("parsl:\n  available_accelerators: ['0']\n")
        out_dir = tmp_path / "new_output"
        cfg = TestExecutiveConfig(
            config_path=str(config_path),
            num_directors=1,
            output_dir=str(out_dir),
        )
        exe = TestExecutive(cfg)
        assert out_dir.exists()


# ---------------------------------------------------------------------------
# TestExecutive._emit
# ---------------------------------------------------------------------------

class TestExecutiveEmit:
    @pytest.mark.asyncio
    async def test_emit_no_data_agent(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("parsl:\n  available_accelerators: ['0']\n")
        cfg = TestExecutiveConfig(
            config_path=str(config_path),
            num_directors=1,
            output_dir=str(tmp_path / "out"),
        )
        exe = TestExecutive(cfg)
        # Should not raise when data_agent_handle is None
        await exe._emit({"event_type": "test", "payload": {}})

    @pytest.mark.asyncio
    async def test_emit_with_data_agent(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("parsl:\n  available_accelerators: ['0']\n")
        cfg = TestExecutiveConfig(
            config_path=str(config_path),
            num_directors=1,
            output_dir=str(tmp_path / "out"),
        )
        exe = TestExecutive(cfg)
        exe.data_agent_handle = AsyncMock()
        await exe._emit({"event_type": "test", "payload": {}})
        exe.data_agent_handle.record_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_failure_swallowed(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("parsl:\n  available_accelerators: ['0']\n")
        cfg = TestExecutiveConfig(
            config_path=str(config_path),
            num_directors=1,
            output_dir=str(tmp_path / "out"),
        )
        exe = TestExecutive(cfg)
        mock_data = AsyncMock()
        mock_data.record_event.side_effect = RuntimeError("DB boom")
        exe.data_agent_handle = mock_data
        # Should not raise
        await exe._emit({"event_type": "test", "payload": {}})
