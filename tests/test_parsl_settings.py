"""
Tests for struct_bio_reasoner.utils.parsl_settings — compute settings, resource summaries.

NOTE: config_factory() tests are skipped when parsl is mocked because
the mock classes don't support actual Config construction.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# Direct import of parsl_settings module, bypassing utils/__init__.py
# which would trigger MDAnalysis import via protein_utils
_mod = importlib.import_module("struct_bio_reasoner.utils.parsl_settings")
BaseComputeSettings = _mod.BaseComputeSettings
BaseSettings = _mod.BaseSettings
LocalSettings = _mod.LocalSettings
LocalCPUSettings = _mod.LocalCPUSettings
HeterogeneousSettings = _mod.HeterogeneousSettings
PolarisSettings = _mod.PolarisSettings
AuroraSettings = _mod.AuroraSettings
resource_summary_from_config = _mod.resource_summary_from_config

# Detect if parsl is real or mocked
_PARSL_MOCKED = not hasattr(sys.modules.get("parsl", None), "__file__")
_skip_parsl = pytest.mark.skipif(_PARSL_MOCKED, reason="parsl is mocked")


# ---------------------------------------------------------------------------
# BaseSettings (YAML serialization)
# ---------------------------------------------------------------------------

class TestBaseSettings:
    def test_dump_and_load_yaml(self, tmp_path):
        settings = LocalSettings(
            available_accelerators=["0", "1"],
            nodes=1,
            worker_init="module load cuda",
        )
        yaml_path = tmp_path / "settings.yaml"
        settings.dump_yaml(yaml_path)
        loaded = LocalSettings.from_yaml(yaml_path)
        assert loaded.nodes == 1
        assert loaded.worker_init == "module load cuda"
        assert loaded.available_accelerators == ["0", "1"]


# ---------------------------------------------------------------------------
# LocalSettings
# ---------------------------------------------------------------------------

class TestLocalSettings:
    def test_defaults(self):
        s = LocalSettings()
        assert s.nodes == 1
        assert s.retries == 1
        assert s.label == "htex"
        assert len(s.available_accelerators) == 12

    def test_custom(self):
        s = LocalSettings(
            available_accelerators=["0", "1", "2"],
            nodes=2,
            worker_init="source env.sh",
        )
        assert len(s.available_accelerators) == 3
        assert s.nodes == 2

    @_skip_parsl
    def test_config_factory(self, tmp_path):
        s = LocalSettings(available_accelerators=["0", "1"])
        config = s.config_factory(tmp_path)
        assert len(config.executors) == 1
        assert config.retries == 1

    def test_resource_summary(self):
        s = LocalSettings(available_accelerators=["0", "1", "2"], nodes=1)
        summary = s.resource_summary()
        assert "Nodes: 1" in summary
        assert "Accelerators per node: 3" in summary
        assert "Total accelerators (GPUs/tiles): 3" in summary
        assert "local" in summary.lower()

    def test_count_accelerators_list(self):
        s = LocalSettings(available_accelerators=["0", "1", "2"])
        assert s._count_accelerators() == 3


# ---------------------------------------------------------------------------
# LocalCPUSettings
# ---------------------------------------------------------------------------

class TestLocalCPUSettings:
    def test_defaults(self):
        s = LocalCPUSettings()
        assert s.nodes == 1
        assert s.max_workers_per_node == 1
        assert s.cores_per_worker == 1.0
        assert s.available_accelerators == []

    @_skip_parsl
    def test_config_factory(self, tmp_path):
        s = LocalCPUSettings()
        config = s.config_factory(tmp_path)
        assert len(config.executors) == 1

    def test_resource_summary(self):
        s = LocalCPUSettings()
        summary = s.resource_summary()
        assert "Nodes: 1" in summary
        assert "Accelerators per node: 0" in summary


# ---------------------------------------------------------------------------
# HeterogeneousSettings
# ---------------------------------------------------------------------------

class TestHeterogeneousSettings:
    def test_defaults(self):
        s = HeterogeneousSettings()
        assert s.available_accelerators == 12
        assert s.nodes == 1

    @_skip_parsl
    def test_config_factory_two_executors(self, tmp_path):
        s = HeterogeneousSettings()
        config = s.config_factory(tmp_path)
        assert len(config.executors) == 2
        labels = {e.label for e in config.executors}
        assert "gpu" in labels
        assert "cpu" in labels

    def test_count_accelerators_int(self):
        s = HeterogeneousSettings(available_accelerators=8)
        assert s._count_accelerators() == 8

    def test_resource_summary(self):
        s = HeterogeneousSettings(available_accelerators=8, nodes=2)
        summary = s.resource_summary()
        assert "Nodes: 2" in summary
        assert "Total accelerators (GPUs/tiles): 16" in summary


# ---------------------------------------------------------------------------
# PolarisSettings
# ---------------------------------------------------------------------------

class TestPolarisSettings:
    def test_required_fields(self):
        with pytest.raises(Exception):
            PolarisSettings()

    def test_valid(self):
        s = PolarisSettings(
            account="myproject",
            queue="debug",
            walltime="01:00:00",
        )
        assert s.num_nodes == 1
        assert s.available_accelerators == 4
        assert s.cpus_per_node == 64

    @_skip_parsl
    def test_config_factory(self, tmp_path):
        s = PolarisSettings(
            account="proj",
            queue="debug",
            walltime="00:30:00",
        )
        config = s.config_factory(tmp_path)
        assert len(config.executors) == 1

    def test_resource_summary_includes_walltime(self):
        s = PolarisSettings(
            account="proj", queue="prod", walltime="02:00:00",
        )
        summary = s.resource_summary()
        assert "Walltime: 02:00:00" in summary
        assert "polaris" in summary.lower()


# ---------------------------------------------------------------------------
# AuroraSettings
# ---------------------------------------------------------------------------

class TestAuroraSettings:
    def test_required_fields(self):
        with pytest.raises(Exception):
            AuroraSettings()

    def test_valid(self):
        s = AuroraSettings(
            account="myproject",
            queue="debug",
            walltime="01:00:00",
        )
        assert s.num_nodes == 1
        assert len(s.available_accelerators) == 12
        assert s.cpus_per_node == 48

    @_skip_parsl
    def test_config_factory(self, tmp_path):
        s = AuroraSettings(
            account="proj",
            queue="debug",
            walltime="00:30:00",
        )
        config = s.config_factory(tmp_path)
        assert len(config.executors) == 1

    def test_resource_summary(self):
        s = AuroraSettings(
            account="proj", queue="prod", walltime="01:00:00",
            num_nodes=2,
        )
        summary = s.resource_summary()
        assert "Nodes: 2" in summary
        assert "aurora" in summary.lower()
        assert "Total accelerators (GPUs/tiles): 24" in summary


# ---------------------------------------------------------------------------
# resource_summary_from_config
# ---------------------------------------------------------------------------

class TestResourceSummaryFromConfig:
    def test_basic(self):
        parsl_dict = {
            "nodes": 2,
            "available_accelerators": ["0", "1", "2", "3"],
        }
        summary = resource_summary_from_config(parsl_dict)
        assert "Nodes: 2" in summary
        assert "Accelerators per node: 4" in summary
        assert "Total accelerators (GPUs/tiles): 8" in summary

    def test_with_walltime(self):
        parsl_dict = {
            "num_nodes": 1,
            "available_accelerators": 4,
            "walltime": "01:00:00",
        }
        summary = resource_summary_from_config(parsl_dict)
        assert "Walltime: 01:00:00" in summary

    def test_num_nodes_fallback(self):
        parsl_dict = {"num_nodes": 3, "available_accelerators": 12}
        summary = resource_summary_from_config(parsl_dict)
        assert "Nodes: 3" in summary
        assert "Total accelerators (GPUs/tiles): 36" in summary

    def test_defaults(self):
        summary = resource_summary_from_config({})
        assert "Nodes: 1" in summary
        assert "Accelerators per node: 0" in summary

    def test_int_accelerators(self):
        parsl_dict = {"available_accelerators": 6}
        summary = resource_summary_from_config(parsl_dict)
        assert "Accelerators per node: 6" in summary

    def test_no_walltime(self):
        parsl_dict = {"nodes": 1, "available_accelerators": []}
        summary = resource_summary_from_config(parsl_dict)
        assert "Walltime" not in summary
