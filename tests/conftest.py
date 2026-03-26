"""Shared test fixtures — mocks for external dependencies.

This conftest installs fake ``jnana`` and ``academy`` packages into
``sys.modules`` so that tests can import ``struct_bio_reasoner`` without
having those packages actually installed.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Build fake modules ONCE (at import time of conftest — before collection)
# ---------------------------------------------------------------------------

def _build_fake_jnana():
    """Create a minimal fake ``jnana`` module tree."""
    jnana = ModuleType("jnana")
    jnana.JnanaSystem = type("JnanaSystem", (), {})

    # jnana.data
    jnana_data = ModuleType("jnana.data")
    jnana_data_uh = ModuleType("jnana.data.unified_hypothesis")

    @dataclass
    class _FakeReference:
        title: str = ""
        url: str = ""

    @dataclass
    class _FakeUnifiedHypothesis:
        hypothesis_id: str = ""
        description: str = ""
        references: List[Any] = field(default_factory=list)

    jnana_data_uh.UnifiedHypothesis = _FakeUnifiedHypothesis
    jnana_data_uh.Reference = _FakeReference
    jnana_data.unified_hypothesis = jnana_data_uh

    # jnana.core
    jnana_core = ModuleType("jnana.core")
    jnana_core_mm = ModuleType("jnana.core.model_manager")
    jnana_core_mm.UnifiedModelManager = type("UnifiedModelManager", (), {})
    jnana_core.model_manager = jnana_core_mm

    # jnana.protognosis.core.coscientist
    jnana_proto = ModuleType("jnana.protognosis")
    jnana_proto_core = ModuleType("jnana.protognosis.core")
    jnana_proto_core_cs = ModuleType("jnana.protognosis.core.coscientist")
    jnana_proto_core_cs.CoScientist = type("CoScientist", (), {})
    jnana_proto_core.coscientist = jnana_proto_core_cs
    jnana_proto.core = jnana_proto_core

    mods = {
        "jnana": jnana,
        "jnana.data": jnana_data,
        "jnana.data.unified_hypothesis": jnana_data_uh,
        "jnana.core": jnana_core,
        "jnana.core.model_manager": jnana_core_mm,
        "jnana.protognosis": jnana_proto,
        "jnana.protognosis.core": jnana_proto_core,
        "jnana.protognosis.core.coscientist": jnana_proto_core_cs,
    }
    return mods


def _build_fake_academy():
    """Create a minimal fake ``academy`` module tree."""

    def _action(fn):
        fn._is_action = True
        return fn

    def _loop(fn):
        fn._is_loop = True
        return fn

    class _Agent:
        pass

    class _Handle:
        pass

    class _Manager:
        def __init__(self):
            self._launched = []

        @classmethod
        async def from_exchange_factory(cls, factory, executors=None):
            return cls()

        async def launch(self, agent_cls, args=None):
            instance = agent_cls(*args) if args else agent_cls()
            self._launched.append(instance)
            handle = MagicMock()
            for attr_name in dir(instance):
                attr = getattr(instance, attr_name, None)
                if callable(attr) and getattr(attr, "_is_action", False):
                    setattr(handle, attr_name, attr)
            return handle

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    class _LocalExchangeFactory:
        pass

    class _RedisExchangeFactory:
        def __init__(self, host="localhost", port=6379):
            self.host = host
            self.port = port

    academy = ModuleType("academy")
    agent_mod = ModuleType("academy.agent")
    handle_mod = ModuleType("academy.handle")
    manager_mod = ModuleType("academy.manager")
    exchange_mod = ModuleType("academy.exchange")
    logging_mod = ModuleType("academy.logging")

    agent_mod.Agent = _Agent
    agent_mod.action = _action
    agent_mod.loop = _loop
    handle_mod.Handle = _Handle
    manager_mod.Manager = _Manager
    exchange_mod.LocalExchangeFactory = _LocalExchangeFactory
    exchange_mod.RedisExchangeFactory = _RedisExchangeFactory
    logging_mod.init_logging = lambda *a, **kw: None

    mods = {
        "academy": academy,
        "academy.agent": agent_mod,
        "academy.handle": handle_mod,
        "academy.manager": manager_mod,
        "academy.exchange": exchange_mod,
        "academy.logging": logging_mod,
    }
    return mods


# Install fakes into sys.modules immediately (before pytest collects tests)
_jnana_mods = _build_fake_jnana()
_academy_mods = _build_fake_academy()

for name, mod in {**_jnana_mods, **_academy_mods}.items():
    if name not in sys.modules:
        sys.modules[name] = mod
