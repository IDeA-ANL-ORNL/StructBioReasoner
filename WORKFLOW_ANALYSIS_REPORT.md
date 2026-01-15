# StructBioReasoner Workflow Analysis Report

## Executive Summary

This report analyzes the `parsl_hierarchical_workflow.py` and related files in the StructBioReasoner repository. Three specialized analyses were conducted:
- **Multi-Agent Coordinator**: Architecture and Parsl collision analysis
- **Python-Pro**: Code quality and best practices
- **Refactoring Specialist**: Simplification opportunities

The analysis identified **critical issues with nested Parsl configurations** that likely cause the collision issues you've observed, along with numerous opportunities for simplification.

---

## Table of Contents

1. [Critical Issue: Nested Parsl Configurations](#1-critical-issue-nested-parsl-configurations)
2. [Architecture Overview](#2-architecture-overview)
3. [Specific Parsl Collision Points](#3-specific-parsl-collision-points)
4. [Code Quality Issues](#4-code-quality-issues)
5. [Refactoring Recommendations](#5-refactoring-recommendations)
6. [Implementation Priorities](#6-implementation-priorities)

---

## 1. Critical Issue: Nested Parsl Configurations

### The Problem

The workflow creates Parsl configurations at **three separate levels**, which is an anti-pattern that causes resource contention:

```
Level 1: ParslHierarchicalWorkflow
         └─> AuroraSettings.config_factory() → ParslPoolExecutor

Level 2: Worker Agents (BindCraftAgent, MDAgentAdapter, ChaiAgent, FEAgent)
         └─> Each creates LocalSettings.config_factory() → Config object

Level 3: Coordinators (ParslDesignCoordinator, MDCoordinator, etc.)
         └─> Receive parsl_settings and may call parsl.load_dfk() internally
```

**This creates collision because:**
1. Multiple `Config()` instances compete for the same run directory (`runinfo/`)
2. Multiple executors claim the same GPU accelerators (0-11)
3. Port ranges overlap (`10000-20000` used by all)
4. Parsl's global DataFlowKernel state gets overwritten

### Evidence of Collision

**File**: `struct_bio_reasoner/workflows/parsl_hierarchical_workflow.py`
**Lines**: 268-277, 316-318

```python
# Level 1: Main workflow creates Parsl config
def _create_distributed_parsl_config(self, parsl_settings, run_dir):
    parsl_config = AuroraSettings(**parsl_settings).config_factory(run_dir)
    return parsl_config
```

**File**: `struct_bio_reasoner/agents/computational_design/bindcraft_agent.py`
**Lines**: 119-127

```python
# Level 2: Worker agent creates ANOTHER Parsl config
async def initialize(self, parsl):
    parsl_settings = LocalSettings(**parsl_config).config_factory(Path.cwd())
    # ... creates its own Manager with ThreadPoolExecutor
```

**File**: `struct_bio_reasoner/agents/molecular_dynamics/mdagent_adapter.py`
**Lines**: 159-161

```python
# Level 2: Another worker agent creates ANOTHER Parsl config
self.parsl_settings = LocalSettings(**parsl_config).config_factory(Path.cwd())
```

### Suggested Fix

**Option A: Single Parsl Configuration (Recommended)**

Create one Parsl DataFlowKernel at the top level and pass executor handles down:

```python
# In ParslHierarchicalWorkflow
class ParslHierarchicalWorkflow:
    async def start(self):
        # Single Parsl configuration
        self.parsl_config = self._create_distributed_parsl_config(...)
        parsl.load_dfk(self.parsl_config)  # Load once

        # Pass the DFK or executor to agents instead of letting them create their own
        for agent in self.agents.values():
            await agent.initialize(use_existing_parsl=True)

# In agent classes
class BindCraftAgent:
    async def initialize(self, use_existing_parsl=False):
        if use_existing_parsl:
            # Use existing Parsl DFK instead of creating new config
            self.parsl_settings = parsl.dfk()
        else:
            # Only create new config if running standalone
            self.parsl_settings = LocalSettings(...).config_factory(...)
```

**Option B: Disable Parsl in Worker Agents**

Since worker agents run inside Parsl-managed tasks, they should NOT create their own Parsl configs:

```python
# In worker agents, replace:
parsl_settings = LocalSettings(**parsl_config).config_factory(Path.cwd())

# With ThreadPoolExecutor for local coordination only:
from concurrent.futures import ThreadPoolExecutor
self.local_executor = ThreadPoolExecutor(max_workers=4)
```

**Option C: Resource Partitioning**

If nested Parsl is truly needed, partition resources explicitly:

```python
# struct_bio_reasoner/utils/parsl_settings.py
@dataclass
class LocalSettings(BaseComputeSettings):
    available_accelerators: List[str] = field(default_factory=list)  # Empty by default
    worker_port_range: Tuple[int, int] = (20001, 30000)  # Different range

    def config_factory(self, run_dir: PathLike, partition_id: str = "") -> Config:
        return Config(
            run_dir=str(run_dir / f'runinfo_{partition_id}'),  # Unique run dir
            ...
        )
```

---

## 2. Architecture Overview

### Current Three-Tier Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                     ParslHierarchicalWorkflow                    │
│  - Creates AuroraSettings Parsl config                          │
│  - Manages ParslPoolExecutor                                    │
│  - Launches Academy Manager                                      │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Executive Agent                             │
│  - RAG queries for target identification                        │
│  - Manager lifecycle decisions (continue/kill/duplicate)        │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Manager Agents (N)                            │
│  - One per RAG hit target                                       │
│  - Run indefinitely until killed                                │
│  - Execute task sequences                                       │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Worker Agents                                │
│  BindCraftAgent  │  MDAgentAdapter  │  ChaiAgent  │  FEAgent    │
│  ⚠️ Each creates own Parsl config! ⚠️                           │
└─────────────────────────────────────────────────────────────────┘
```

### Problematic Academy Manager Nesting

Each worker agent creates its own Academy `Manager` with `ThreadPoolExecutor`:

```python
# Pattern repeated in: BindCraftAgent, MDAgentAdapter, ChaiAgent, FEAgent, RAGWrapper
self.manager = await Manager.from_exchange_factory(
    factory=LocalExchangeFactory(),
    executors=ThreadPoolExecutor(),  # Not using parent's ParslPoolExecutor!
)
```

**Impact**:
- Multiple independent event loops
- No coordination between nested managers
- Each agent's coordinators create additional Parsl configs

---

## 3. Specific Parsl Collision Points

### 3.1 Run Directory Conflicts

**Location**: `struct_bio_reasoner/utils/parsl_settings.py`

```python
def config_factory(self, run_dir: PathLike) -> Config:
    return Config(
        run_dir=str(run_dir/'runinfo'),  # All agents write to same directory!
        ...
    )
```

**Fix**: Add unique identifiers to run directories:

```python
def config_factory(self, run_dir: PathLike, agent_id: str = "main") -> Config:
    return Config(
        run_dir=str(run_dir / f'runinfo_{agent_id}_{os.getpid()}'),
        ...
    )
```

### 3.2 Port Range Overlap

**Location**: `struct_bio_reasoner/utils/parsl_settings.py`

```python
# LocalSettings
worker_port_range: Tuple[int, int] = (10000, 20000)

# LocalCPUSettings
worker_port_range: Tuple[int, int] = (10000, 20000)
```

**Fix**: Use different port ranges or dynamic allocation:

```python
@dataclass
class LocalSettings(BaseComputeSettings):
    base_port: int = 10000

    def config_factory(self, run_dir: PathLike) -> Config:
        # Allocate unique port range based on process
        port_offset = (os.getpid() % 100) * 200
        worker_port_range = (self.base_port + port_offset,
                            self.base_port + port_offset + 199)
        ...
```

### 3.3 GPU Accelerator Conflicts

**Location**: Multiple files specify same accelerators

```python
# All configs claim GPUs 0-11
available_accelerators: List[str] = [str(i) for i in range(12)]
```

**Fix**: Implement accelerator partitioning:

```python
class AcceleratorPartitioner:
    _assigned: Dict[str, List[str]] = {}
    _lock = threading.Lock()

    @classmethod
    def allocate(cls, agent_id: str, count: int) -> List[str]:
        with cls._lock:
            all_gpus = set(range(12))
            used = set(sum(cls._assigned.values(), []))
            available = list(all_gpus - used)[:count]
            cls._assigned[agent_id] = available
            return [str(g) for g in available]
```

---

## 4. Code Quality Issues

### 4.1 Critical Bugs

#### Attribute Name Mismatch (Will Cause RuntimeError)

**File**: `struct_bio_reasoner/workflows/parsl_hierarchical_workflow.py`
**Lines**: 273-274

```python
# BUG: conda_env doesn't exist on WorkflowConfig, only python_env does
if self.config.conda_env:  # ❌ AttributeError
    worker_init = f"cd {os.getcwd()}; source {self.config.python_env}/bin/activate; ..."
```

**Fix**:
```python
if self.config.python_env:  # ✓ Correct attribute
    worker_init = f"cd {os.getcwd()}; source {self.config.python_env}/bin/activate; ..."
```

#### Race Condition in Manager ID Generation

**File**: `struct_bio_reasoner/workflows/parsl_hierarchical_workflow.py`
**Lines**: 216-219

```python
# BUG: Not thread-safe
def get_next_manager_id(self) -> str:
    self.manager_counter += 1  # ❌ Can have duplicates
    return f"manager_{self.manager_counter}"
```

**Fix**:
```python
import asyncio

class WorkflowState:
    def __init__(self):
        self._counter_lock = asyncio.Lock()
        self.manager_counter: int = 0

    async def get_next_manager_id(self) -> str:
        async with self._counter_lock:
            self.manager_counter += 1
            return f"manager_{self.manager_counter}"
```

#### Incorrect Variable Check

**File**: `struct_bio_reasoner/workflows/parsl_hierarchical_workflow.py`
**Line**: 664

```python
# BUG: dir() doesn't check local variables
'task': next_task if 'next_task' in dir() else 'unknown',  # ❌ Wrong
```

**Fix**:
```python
'task': next_task if 'next_task' in locals() else 'unknown',  # ✓ Correct
```

### 4.2 Resource Management Issues

#### Unclosed File Handle

**File**: `struct_bio_reasoner/workflows/parsl_hierarchical_workflow.py`
**Line**: 247

```python
# BUG: File handle never closed
self.base_parsl_settings = yaml.safe_load(open(config.parsl_config))  # ❌
```

**Fix**:
```python
with open(config.parsl_config) as f:  # ✓
    self.base_parsl_settings = yaml.safe_load(f)
```

#### Config File Overwriting

**File**: `struct_bio_reasoner/core/binder_design_system.py`
**Lines**: 213-233

The code modifies and overwrites the original config file, which can corrupt configuration:

```python
with open(jnana_config_path, 'w') as f:  # ❌ Overwrites original
    yaml.dump(jnana_config, f, default_flow_style=False)
```

**Fix**: Write to a temporary file or separate runtime config:
```python
runtime_config_path = Path(jnana_config_path).with_suffix('.runtime.yaml')
with open(runtime_config_path, 'w') as f:
    yaml.dump(jnana_config, f, default_flow_style=False)
```

### 4.3 Memory Management

#### Unbounded List Growth

**File**: `struct_bio_reasoner/workflows/parsl_hierarchical_workflow.py`

```python
@dataclass
class ManagerState:
    task_history: List[Dict[str, Any]] = field(default_factory=list)  # ❌ Unbounded
    executive_advice: List[str] = field(default_factory=list)  # ❌ Unbounded

@dataclass
class WorkflowState:
    executive_decisions: List[Dict[str, Any]] = field(default_factory=list)  # ❌ Unbounded
```

**Fix**: Use bounded collections:
```python
from collections import deque

@dataclass
class ManagerState:
    task_history: deque = field(default_factory=lambda: deque(maxlen=100))
    executive_advice: deque = field(default_factory=lambda: deque(maxlen=50))
```

### 4.4 Debug Code Left In

**File**: `struct_bio_reasoner/utils/llm_interface.py`
**Line**: 872
```python
print(f"{response=}")  # ❌ Debug statement
```

**File**: `struct_bio_reasoner/agents/executive/executive_agent.py`
**Line**: 131
```python
if True:  # ❌ Always-true condition
    md_output = await self.fold_handle.analyze_hypothesis({}, mdinput)
```

---

## 5. Refactoring Recommendations

### 5.1 Extract Common Workflow Base Class

**Current**: Two nearly identical workflow files with ~60% code overlap:
- `parsl_hierarchical_workflow.py` (1187 lines)
- `hierarchical_workflow.py` (1100+ lines)

**Suggested Structure**:

```python
# struct_bio_reasoner/workflows/base_workflow.py
class BaseHierarchicalWorkflow(ABC):
    """Common functionality for hierarchical workflows."""

    async def _prepare_worker_handles(self) -> Dict[str, Any]:
        return {
            'folding': self.binder_system.design_agents.get('structure_prediction'),
            'simulation': self.binder_system.design_agents.get('molecular_dynamics'),
            'binder_design': self.binder_system.design_agents.get('computational_design'),
            'free_energy': self.binder_system.design_agents.get('free_energy'),
        }

    def _build_task_params(self, task_type: str, current_state: Dict) -> Dict:
        # Common parameter building logic
        ...

    @abstractmethod
    async def _create_executor(self):
        """Create execution backend (Parsl or local)."""
        ...

# struct_bio_reasoner/workflows/parsl_hierarchical_workflow.py
class ParslHierarchicalWorkflow(BaseHierarchicalWorkflow):
    async def _create_executor(self):
        return ParslPoolExecutor(self._create_parsl_config())

# struct_bio_reasoner/workflows/local_workflow.py
class LocalHierarchicalWorkflow(BaseHierarchicalWorkflow):
    async def _create_executor(self):
        return ThreadPoolExecutor(max_workers=4)
```

### 5.2 Create Agent Manager Mixin

**Current**: Duplicate initialization in 5+ agents

```python
# Repeated in: BindCraftAgent, MDAgentAdapter, ChaiAgent, FEAgent, RAGWrapper
self.manager = await Manager.from_exchange_factory(
    factory=LocalExchangeFactory(),
    executors=ThreadPoolExecutor(),
)
await self.manager.__aenter__()
```

**Suggested Mixin**:

```python
# struct_bio_reasoner/agents/mixins.py
class AgentManagerMixin:
    """Standardized Academy manager lifecycle management."""

    async def _initialize_manager(self, executor=None):
        self.manager = await Manager.from_exchange_factory(
            factory=LocalExchangeFactory(),
            executors=executor or ThreadPoolExecutor(max_workers=4),
        )
        await self.manager.__aenter__()
        self._manager_initialized = True

    async def _cleanup_manager(self):
        if hasattr(self, '_manager_initialized') and self._manager_initialized:
            await self.manager.__aexit__(None, None, None)
            self.manager = None
            self._manager_initialized = False

# Usage
class BindCraftAgent(AgentManagerMixin):
    async def initialize(self, parsl):
        await self._initialize_manager()
        # ... rest of initialization

    async def cleanup(self):
        await self._cleanup_manager()
```

### 5.3 Simplify Configuration Loading

**Current**: 7+ places load configuration differently

**Suggested Centralized Manager**:

```python
# struct_bio_reasoner/config/manager.py
from functools import lru_cache
from pydantic import BaseModel

class BinderConfiguration(BaseModel):
    """Type-safe configuration with validation."""
    agents: AgentConfigs
    parsl: ParslConfig
    history: HistoryConfig

    class Config:
        extra = 'forbid'  # Fail on unknown keys

@lru_cache(maxsize=1)
def get_config(config_path: str = "config/binder_config.yaml") -> BinderConfiguration:
    """Single source of truth for configuration."""
    with open(config_path) as f:
        raw_config = yaml.safe_load(f)
    return BinderConfiguration(**raw_config)

# Usage everywhere:
from struct_bio_reasoner.config.manager import get_config
config = get_config()
parsl_settings = config.parsl
agent_config = config.agents.computational_design
```

### 5.4 Simplify LLM Interface

**Current**: 1095 lines across 10 LLM classes with significant duplication

**Suggested Template Method**:

```python
# struct_bio_reasoner/utils/llm_interface.py
class LLMInterface(ABC):
    """Base class using Template Method pattern."""

    def generate_with_json_output(
        self,
        prompt: str,
        json_schema: Dict,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> Tuple[Dict, int, int]:
        """Template method - subclasses override _call_api only."""
        full_prompt = self._build_json_prompt(prompt, json_schema)
        response, input_tokens, output_tokens = self._call_api(
            full_prompt, temperature, max_tokens
        )
        parsed = self._parse_json_response(response)
        return parsed, input_tokens, output_tokens

    @abstractmethod
    def _call_api(self, prompt: str, temperature: float, max_tokens: int) -> Tuple[str, int, int]:
        """Provider-specific API call. Override this."""
        ...

    def _build_json_prompt(self, prompt: str, schema: Dict) -> str:
        """Shared logic for all providers."""
        return f"{prompt}\n\nRespond ONLY with valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"

    def _parse_json_response(self, response: str) -> Dict:
        """Shared JSON extraction from markdown blocks."""
        # Extract from ```json ... ``` blocks
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', response, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return json.loads(response)

# Much simpler implementations
class AnthropicLLM(LLMInterface):
    def _call_api(self, prompt, temperature, max_tokens):
        response = self.client.messages.create(...)
        return response.content[0].text, response.usage.input_tokens, response.usage.output_tokens
```

### 5.5 Simplify Prompt Managers

**Current**: 594 lines across 7 dataclass-based prompt managers

**Suggested Template Approach**:

```yaml
# struct_bio_reasoner/prompts/templates/rag.yaml
running:
  template: |
    Research Goal: {research_goal}
    Target Protein: {target_protein}

    Generate an optimal HiPerRAG query to identify proteins that:
    1. Physically interact with {target_protein}
    2. Are relevant to {research_focus}
    ...
```

```python
# struct_bio_reasoner/prompts/manager.py
class PromptManager:
    """Unified template-based prompt manager."""

    def __init__(self, agent_type: str, context: Dict[str, Any]):
        self.templates = self._load_templates(agent_type)
        self.context = context

    def _load_templates(self, agent_type: str) -> Dict[str, str]:
        template_path = Path(__file__).parent / f'templates/{agent_type}.yaml'
        with open(template_path) as f:
            return yaml.safe_load(f)

    def running_prompt(self) -> str:
        return self.templates['running']['template'].format(**self.context)

    def conclusion_prompt(self) -> str:
        return self.templates['conclusion']['template'].format(**self.context)

# Usage
prompt_mgr = PromptManager('rag', {'research_goal': goal, 'target_protein': target})
prompt = prompt_mgr.running_prompt()
```

---

## 6. Implementation Priorities

### High Priority (Fix Immediately)

| Issue | Location | Impact |
|-------|----------|--------|
| Nested Parsl configurations | Multiple files | Causes collision/deadlock |
| `conda_env` attribute error | `parsl_hierarchical_workflow.py:273` | Runtime crash |
| Race condition in ID generation | `parsl_hierarchical_workflow.py:216` | Duplicate manager IDs |
| Unclosed file handle | `parsl_hierarchical_workflow.py:247` | Resource leak |

### Medium Priority (Next Sprint)

| Issue | Location | Impact |
|-------|----------|--------|
| Extract base workflow class | Both workflow files | ~300 lines saved |
| Create AgentManagerMixin | 5+ agent files | Standardization |
| Centralize config loading | 7+ locations | Consistency |
| Fix unbounded list growth | Multiple dataclasses | Memory leak |

### Lower Priority (Technical Debt)

| Issue | Location | Impact |
|-------|----------|--------|
| Simplify LLM interface | `llm_interface.py` | ~700 lines saved |
| Template-based prompts | `prompts.py` | ~450 lines saved |
| Remove debug code | Multiple files | Code cleanliness |
| Add comprehensive type hints | Throughout | Maintainability |

---

## Quick Reference: Files to Modify

```
struct_bio_reasoner/
├── workflows/
│   ├── parsl_hierarchical_workflow.py  # Primary fixes needed
│   └── hierarchical_workflow.py        # Extract common base
├── utils/
│   ├── parsl_settings.py               # Fix port/directory conflicts
│   └── llm_interface.py                # Simplify with template method
├── agents/
│   ├── computational_design/
│   │   └── bindcraft_agent.py          # Remove nested Parsl
│   ├── molecular_dynamics/
│   │   └── mdagent_adapter.py          # Remove nested Parsl
│   ├── structure_prediction/
│   │   └── chai_agent.py               # Remove nested Parsl
│   └── hiper_rag/
│       └── rag_agent.py                # Remove nested Parsl
├── core/
│   └── binder_design_system.py         # Fix config overwriting
└── prompts/
    └── prompts.py                      # Simplify to templates
```

---

## Conclusion

The primary issue causing workflow collisions is the **nested Parsl configuration anti-pattern**. Each worker agent creates its own Parsl `Config` object, leading to:
- Run directory conflicts
- Port range collisions
- GPU accelerator competition
- Multiple DataFlowKernel instances

The recommended fix is to use a **single Parsl configuration** at the top level and pass executor handles to agents, rather than having each agent create its own parallel execution framework. This aligns with Parsl's design as a centralized workflow orchestration tool.

Secondary improvements around code consolidation and simplification will significantly reduce maintenance burden and improve system stability.
