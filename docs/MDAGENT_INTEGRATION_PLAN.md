# MDAgent Integration Plan for StructBioReasoner

## Executive Summary

This document outlines the strategy for integrating the MDAgent architecture (from https://github.com/msinclair-py/MDAgent) into StructBioReasoner's design philosophy while maintaining compatibility with both systems.

## Architecture Comparison

### MDAgent Design Philosophy
- **Framework**: Academy-based agent framework with `@action` decorators
- **Communication**: Handle-based inter-agent communication
- **Workflow**: Sequential build → simulate pipeline
- **Specialization**: Focused on MD simulation execution
- **Tool Integration**: Direct integration with `molecular_simulations` library
- **Coordination**: Explicit coordinator pattern (MDCoordinator)

### StructBioReasoner Design Philosophy
- **Framework**: Custom async BaseAgent with hypothesis generation
- **Communication**: Direct communication + role-based orchestration
- **Workflow**: Multi-agent consensus with expert/critic feedback loops
- **Specialization**: Broad protein engineering capabilities
- **Tool Integration**: Wrapper pattern (OpenMMWrapper, PyMOLWrapper, etc.)
- **Coordination**: RoleOrchestrator with multi-stage workflows

## Integration Strategy

### Option 1: Adapter Pattern (Recommended)
**Wrap MDAgent components as StructBioReasoner agents**

**Advantages:**
- Preserves both architectures
- Minimal changes to existing code
- Allows gradual migration
- Maintains compatibility with both systems

**Implementation:**
1. Create `MDAgentAdapter` that wraps MDAgent's Builder, MDSimulator, and MDCoordinator
2. Implement StructBioReasoner's `BaseAgent` interface
3. Translate between Academy's `@action` pattern and StructBioReasoner's async methods
4. Convert MD results into `ProteinHypothesis` objects

### Option 2: Hybrid Architecture
**Integrate MDAgent's coordination pattern into StructBioReasoner**

**Advantages:**
- Leverages MDAgent's proven MD workflow
- Enhances StructBioReasoner's MD capabilities
- Maintains hypothesis-centric design

**Implementation:**
1. Extend `MolecularDynamicsAgent` to use MDAgent's Builder/Simulator pattern
2. Add explicit build/simulate separation
3. Integrate implicit/explicit solvent handling
4. Maintain hypothesis generation wrapper

### Option 3: Unified Framework
**Create a unified agent framework supporting both patterns**

**Advantages:**
- Most flexible long-term solution
- Supports multiple agent paradigms
- Enables best-of-both-worlds

**Disadvantages:**
- Most complex implementation
- Requires significant refactoring
- Higher maintenance burden

## Recommended Implementation: Adapter Pattern

### Phase 1: Core Adapter Implementation

#### 1.1 Create MDAgent Adapter Base Class
```python
# struct_bio_reasoner/agents/molecular_dynamics/mdagent_adapter.py

from academy.agent import Agent
from academy.handle import Handle
from ..core.base_agent import BaseAgent
from ...data.protein_hypothesis import ProteinHypothesis

class MDAgentAdapter(BaseAgent):
    """
    Adapter that wraps MDAgent components to work within StructBioReasoner.
    
    This adapter translates between:
    - Academy's @action pattern → StructBioReasoner's async methods
    - MDAgent's Handle communication → Direct method calls
    - MD simulation results → ProteinHypothesis objects
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.agent_type = "md_simulation"
        self.specialization = "molecular_dynamics"
        
        # MDAgent components (initialized in initialize())
        self.builder = None
        self.simulator = None
        self.coordinator = None
```

#### 1.2 Implement Builder Agent Wrapper
```python
# struct_bio_reasoner/agents/molecular_dynamics/md_builder_agent.py

from mdagent.agents import Builder  # Assuming MDAgent is installed
from ..core.base_agent import BaseAgent

class MDBuilderAgent(BaseAgent):
    """
    Wrapper for MDAgent's Builder that conforms to StructBioReasoner interface.
    """
    
    async def build_system(self, 
                          path: Path,
                          pdb: Path,
                          build_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build MD system using MDAgent's Builder.
        
        Returns hypothesis about system preparation.
        """
        # Call MDAgent's builder
        result_path = await self.builder.build(path, pdb, build_kwargs)
        
        # Convert to hypothesis
        hypothesis = self._create_build_hypothesis(result_path, build_kwargs)
        return hypothesis
```

#### 1.3 Implement Simulator Agent Wrapper
```python
# struct_bio_reasoner/agents/molecular_dynamics/md_simulator_agent.py

from mdagent.agents import MDSimulator
from ..core.base_agent import BaseAgent

class MDSimulatorAgent(BaseAgent):
    """
    Wrapper for MDAgent's MDSimulator that conforms to StructBioReasoner interface.
    """
    
    async def run_simulation(self,
                            path: Path,
                            sim_kwargs: Dict[str, Any]) -> ProteinHypothesis:
        """
        Run MD simulation using MDAgent's Simulator.
        
        Returns hypothesis about simulation results.
        """
        # Call MDAgent's simulator
        result_path = await self.simulator.simulate(path, sim_kwargs)
        
        # Analyze results and create hypothesis
        hypothesis = await self._create_simulation_hypothesis(result_path, sim_kwargs)
        return hypothesis
```

### Phase 2: Enhanced MD Agent

#### 2.1 Extend MolecularDynamicsAgent
Enhance the existing `MolecularDynamicsAgent` to optionally use MDAgent components:

```python
# struct_bio_reasoner/agents/molecular_dynamics/md_agent.py (enhanced)

class MolecularDynamicsAgent(BaseAgent):
    """
    Enhanced MD agent with optional MDAgent backend.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Choose backend: 'openmm' or 'mdagent'
        self.backend = config.get('md_backend', 'openmm')
        
        if self.backend == 'mdagent':
            self.md_adapter = MDAgentAdapter(config)
        else:
            self.openmm_wrapper = OpenMMWrapper(config)
    
    async def run_thermostability_analysis(self, 
                                          structure_data: Dict[str, Any]) -> ProteinHypothesis:
        """
        Run thermostability analysis using configured backend.
        """
        if self.backend == 'mdagent':
            return await self._run_mdagent_thermostability(structure_data)
        else:
            return await self._run_openmm_thermostability(structure_data)
```

### Phase 3: Role Integration

#### 3.1 Create MD Expert Role using MDAgent
```python
# struct_bio_reasoner/agents/roles/mdagent_expert.py

from .base_role import BaseRole, RoleType
from ..molecular_dynamics.mdagent_adapter import MDAgentAdapter

class MDAgentExpert(BaseRole):
    """
    Expert role that uses MDAgent for high-quality MD simulations.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(
            role_name="MDAgent Expert",
            role_type=RoleType.EXPERT,
            config=config
        )
        
        self.md_adapter = MDAgentAdapter(config)
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute MD simulation task using MDAgent backend.
        """
        # Use MDAgent's proven workflow
        build_result = await self.md_adapter.build_system(...)
        sim_result = await self.md_adapter.run_simulation(...)
        
        # Generate expert analysis
        return self._create_expert_analysis(build_result, sim_result)
```

## Key Design Decisions

### 1. Solvent Model Handling
**MDAgent Approach**: Explicit implicit/explicit solvent switching
**Integration**: Add solvent model selection to StructBioReasoner's MD config

```yaml
# config/protein_config.yaml
molecular_dynamics:
  backend: mdagent  # or 'openmm'
  solvent_model: explicit  # or 'implicit'
  force_field: amber14
  water_model: tip3p
```

### 2. Build/Simulate Separation
**MDAgent Approach**: Separate Builder and Simulator agents
**Integration**: Add explicit build phase to StructBioReasoner workflows

```python
# Workflow becomes:
# 1. Build system (MDAgent Builder)
# 2. Run simulation (MDAgent Simulator)
# 3. Analyze results (StructBioReasoner analysis)
# 4. Generate hypothesis (StructBioReasoner hypothesis generation)
```

### 3. Hypothesis Generation
**MDAgent**: Returns paths to simulation results
**StructBioReasoner**: Returns ProteinHypothesis objects

**Integration**: Adapter converts MD results → hypotheses

```python
def _create_simulation_hypothesis(self, 
                                 sim_results: Path,
                                 sim_kwargs: Dict[str, Any]) -> ProteinHypothesis:
    """Convert MDAgent simulation results to ProteinHypothesis."""
    # Analyze trajectory
    analysis = self._analyze_trajectory(sim_results)
    
    # Create hypothesis
    return ProteinHypothesis(
        title=f"MD Simulation Analysis",
        content=f"Simulation completed with {analysis['stability_score']} stability",
        hypothesis_type="md_simulation",
        metadata={
            'simulation_path': str(sim_results),
            'simulation_params': sim_kwargs,
            'analysis_results': analysis
        }
    )
```

## Implementation Roadmap

### Week 1: Foundation
- [ ] Create `MDAgentAdapter` base class
- [ ] Implement basic Builder wrapper
- [ ] Implement basic Simulator wrapper
- [ ] Add configuration support for MDAgent backend

### Week 2: Integration
- [ ] Extend `MolecularDynamicsAgent` with backend selection
- [ ] Implement hypothesis conversion methods
- [ ] Add solvent model configuration
- [ ] Create integration tests

### Week 3: Role Enhancement
- [ ] Create `MDAgentExpert` role
- [ ] Integrate with `RoleOrchestrator`
- [ ] Add MDAgent-specific critic evaluations
- [ ] Test multi-agent workflows

### Week 4: Validation & Documentation
- [ ] Comprehensive testing with both backends
- [ ] Performance comparison (OpenMM vs MDAgent)
- [ ] Update documentation
- [ ] Create migration guide

## Benefits of This Integration

1. **Best of Both Worlds**: Leverage MDAgent's proven MD workflow within StructBioReasoner's hypothesis framework
2. **Flexibility**: Users can choose between OpenMM (lightweight) and MDAgent (full-featured) backends
3. **Maintainability**: Adapter pattern keeps both systems independent
4. **Extensibility**: Easy to add more MDAgent features over time
5. **Compatibility**: Existing StructBioReasoner code continues to work

## Next Steps

1. **Install MDAgent**: Add MDAgent as a dependency
2. **Create Adapter**: Implement the adapter pattern
3. **Test Integration**: Validate with example workflows
4. **Document**: Update user guides and API documentation

