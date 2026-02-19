"""
Shared test fixtures and mocking infrastructure.

Mocks external dependencies (academy, parsl, pydantic_ai, MDAnalysis, etc.)
so tests can run without the full HPC stack installed.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock unavailable dependencies before any package imports.
# ---------------------------------------------------------------------------

_SBR_ROOT = Path(__file__).resolve().parent.parent / "struct_bio_reasoner"


def _ensure_mock_module(name: str, **attrs) -> types.ModuleType:
    """Insert a stub ModuleType into sys.modules if not already present."""
    if name not in sys.modules:
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod
    return sys.modules[name]


# ── 1. Mock 'academy' and all submodules ──

class _AgentStub:
    def __init__(self, *a, **kw):
        pass
    async def agent_launch_alongside(self, cls, args=None, kwargs=None):
        return None

def _action_stub(fn):
    return fn

_acad = _ensure_mock_module("academy")
_acad.__path__ = []

_acad_agent = _ensure_mock_module("academy.agent", Agent=_AgentStub, action=_action_stub)
_ensure_mock_module("academy.handle", Handle=type("Handle", (), {}))
_ensure_mock_module("academy.manager", Manager=type("Manager", (), {}))

_acad_exchange = _ensure_mock_module("academy.exchange", LocalExchangeFactory=type("LocalExchangeFactory", (), {}))
_acad_exchange.__path__ = []
_ensure_mock_module("academy.exchange.cloud", HttpExchangeFactory=type("HttpExchangeFactory", (), {}))
_ensure_mock_module("academy.logging", init_logging=lambda *a, **kw: None)

# Wire submodules into parent
for attr, subkey in [
    ("agent", "academy.agent"),
    ("handle", "academy.handle"),
    ("manager", "academy.manager"),
    ("exchange", "academy.exchange"),
    ("logging", "academy.logging"),
]:
    setattr(sys.modules["academy"], attr, sys.modules[subkey])


# ── 2. Mock 'parsl' ──

_parsl = _ensure_mock_module("parsl")
_parsl.__path__ = []
_parsl.load = MagicMock(return_value=MagicMock())
_parsl.clear = MagicMock()
_parsl.dfk = MagicMock(return_value=MagicMock())
# Expose Config at top level (`from parsl import Config`)
_parsl.Config = _Config = type("Config", (), {"__init__": lambda self, **kw: None})
_parsl.python_app = lambda *a, **kw: lambda fn: fn

# Parsl sub-modules needed by parsl_settings.py and director
_Config = type("Config", (), {"__init__": lambda self, **kw: None})
_ensure_mock_module("parsl.config", Config=_Config)

_LocalProvider = type("LocalProvider", (), {"__init__": lambda self, **kw: None})
_PBSProProvider = type("PBSProProvider", (), {"__init__": lambda self, **kw: None})
_ensure_mock_module("parsl.providers", LocalProvider=_LocalProvider, PBSProProvider=_PBSProProvider)

_HighThroughputExecutor = type("HighThroughputExecutor", (), {"__init__": lambda self, **kw: None})
_ensure_mock_module("parsl.executors", HighThroughputExecutor=_HighThroughputExecutor)

_MpiExecLauncher = type("MpiExecLauncher", (), {"__init__": lambda self, **kw: None})
_GnuParallelLauncher = type("GnuParallelLauncher", (), {"__init__": lambda self, **kw: None})
_ensure_mock_module("parsl.launchers", MpiExecLauncher=_MpiExecLauncher, GnuParallelLauncher=_GnuParallelLauncher)

_ensure_mock_module("parsl.addresses", address_by_interface=lambda *a: "localhost", address_by_hostname=lambda *a: "localhost")
_ensure_mock_module("parsl.utils", get_all_checkpoints=lambda *a: [])


# ── 3. Mock 'pydantic_ai' ──

_ensure_mock_module("pydantic_ai")
_pai_agent = _ensure_mock_module("pydantic_ai.agent")

class _FakePAgent:
    def __init__(self, **kw):
        pass
    async def run(self, **kw):
        return MagicMock()

sys.modules["pydantic_ai"].Agent = _FakePAgent

_ensure_mock_module("pydantic_ai.models")
_ensure_mock_module("pydantic_ai.models.openai", OpenAIChatModel=type("OpenAIChatModel", (), {"__init__": lambda self, *a, **kw: None}))
_ensure_mock_module("pydantic_ai.output", PromptedOutput=type("PromptedOutput", (), {"__init__": lambda self, *a, **kw: None}))
_ensure_mock_module("pydantic_ai.providers")
_ensure_mock_module("pydantic_ai.providers.openai", OpenAIProvider=type("OpenAIProvider", (), {"__init__": lambda self, **kw: None}))
_ensure_mock_module("pydantic_ai.settings", ModelSettings=type("ModelSettings", (), {"__init__": lambda self, **kw: None}))


# ── 4. Mock MDAnalysis ──

_ensure_mock_module("MDAnalysis")


# ── 5. Mock globus_compute_sdk ──

_ensure_mock_module("globus_compute_sdk", Executor=type("Executor", (), {}))


# ── 6. Mock struct_bio_reasoner root __init__ ──

if "struct_bio_reasoner" not in sys.modules:
    _root_pkg = types.ModuleType("struct_bio_reasoner")
    _root_pkg.__path__ = [str(_SBR_ROOT)]
    _root_pkg.__package__ = "struct_bio_reasoner"
    sys.modules["struct_bio_reasoner"] = _root_pkg


# ── 7. Mock package __init__ files to avoid cascading imports ──

def _ensure_package(dotted: str, fs_path: Path) -> None:
    if dotted not in sys.modules:
        pkg = types.ModuleType(dotted)
        pkg.__path__ = [str(fs_path)]
        pkg.__package__ = dotted
        sys.modules[dotted] = pkg

_ensure_package("struct_bio_reasoner.agents", _SBR_ROOT / "agents")
_ensure_package("struct_bio_reasoner.agents.director", _SBR_ROOT / "agents" / "director")
_ensure_package("struct_bio_reasoner.agents.executive", _SBR_ROOT / "agents" / "executive")
_ensure_package("struct_bio_reasoner.agents.language_model", _SBR_ROOT / "agents" / "language_model")
_ensure_package("struct_bio_reasoner.utils", _SBR_ROOT / "utils")

# Wire subpackages as attributes of parent modules so unittest.mock.patch can resolve them
sys.modules["struct_bio_reasoner"].agents = sys.modules["struct_bio_reasoner.agents"]
sys.modules["struct_bio_reasoner.agents"].director = sys.modules["struct_bio_reasoner.agents.director"]
sys.modules["struct_bio_reasoner.agents"].executive = sys.modules["struct_bio_reasoner.agents.executive"]
sys.modules["struct_bio_reasoner.agents"].language_model = sys.modules["struct_bio_reasoner.agents.language_model"]
sys.modules["struct_bio_reasoner"].utils = sys.modules["struct_bio_reasoner.utils"]


# ── 8. Mock inference auth token utility ──

_ensure_mock_module(
    "struct_bio_reasoner.utils.inference_auth_token",
    get_access_token=lambda: "mock-token",
)
