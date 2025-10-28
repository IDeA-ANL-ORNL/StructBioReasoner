# MDAgent Integration Guide

## Overview

StructBioReasoner now supports **MDAgent** as an alternative backend for molecular dynamics simulations. This integration provides users with the flexibility to choose between:

- **OpenMM**: Lightweight, Python-native MD engine (default)
- **MDAgent**: Full-featured MD workflow with Academy framework integration

## Architecture

The integration uses an **Adapter Pattern** to wrap MDAgent components while maintaining compatibility with StructBioReasoner's hypothesis-centric design:

```
StructBioReasoner
├── MolecularDynamicsAgent (Enhanced)
│   ├── OpenMM Backend (default)
│   └── MDAgent Backend (optional)
│       └── MDAgentAdapter
│           ├── Builder (system preparation)
│           ├── MDSimulator (MD execution)
│           └── MDCoordinator (workflow orchestration)
└── Role-Based System
    └── MDAgentExpert (new)
        └── Uses MDAgent for expert-level simulations
```

## Installation

### Prerequisites

1. **StructBioReasoner** (already installed)
2. **MDAgent** (optional, for MDAgent backend)

### Installing MDAgent

**Quick Setup**:

```bash
# Clone MDAgent repository
git clone https://github.com/msinclair-py/MDAgent.git

# Add to Python path
export PYTHONPATH="${PYTHONPATH}:/path/to/MDAgent"

# Verify installation
python -c "from agents import Builder, MDSimulator, MDCoordinator; print('Success!')"
```

**For detailed installation instructions**, see: [`docs/MDAGENT_SETUP.md`](MDAGENT_SETUP.md)

### Installing Trajectory Analysis Tools (Optional)

For detailed trajectory analysis:

```bash
pip install mdtraj numpy
```

## Configuration

### Basic Configuration

Edit `config/protein_config.yaml`:

```yaml
agents:
  molecular_dynamics:
    enabled: true
    md_backend: "mdagent"  # Change from "openmm" to "mdagent"
    
    # MDAgent-specific configuration
    mdagent:
      solvent_model: "explicit"  # or "implicit"
      force_field: "amber14"
      water_model: "tip3p"
      equil_steps: 10_000
      prod_steps: 1_000_000
      protein: true
      output_file: "system.pdb"
```

### Backend Selection

You can choose the backend in three ways:

#### 1. Configuration File (Global)

```yaml
# config/protein_config.yaml
agents:
  molecular_dynamics:
    md_backend: "mdagent"
```

#### 2. Agent Initialization (Per-Agent)

```python
config = {
    "md_backend": "mdagent",
    "mdagent": {
        "solvent_model": "explicit"
    }
}
agent = MolecularDynamicsAgent(config)
```

#### 3. Runtime Selection (Dynamic)

```python
# Start with OpenMM
agent = MolecularDynamicsAgent({"md_backend": "openmm"})

# Switch to MDAgent (requires reinitialization)
agent.backend = "mdagent"
await agent.initialize()
```

## Usage Examples

### Example 1: Basic MD Simulation

```python
import asyncio
from struct_bio_reasoner.agents.molecular_dynamics.md_agent import MolecularDynamicsAgent

async def run_md_simulation():
    # Configure with MDAgent backend
    config = {
        "md_backend": "mdagent",
        "mdagent": {
            "solvent_model": "explicit",
            "equil_steps": 10_000,
            "prod_steps": 1_000_000
        }
    }
    
    # Create and initialize agent
    agent = MolecularDynamicsAgent(config)
    await agent.initialize()
    
    # Generate hypotheses
    context = {
        'protein_sequence': 'MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG',
        'target_protein': 'ubiquitin',
        'pdb_path': 'data/1ubq.pdb',
        'analysis_goals': ['thermostability']
    }
    
    hypotheses = await agent.generate_hypotheses(context)
    print(f"Generated {len(hypotheses)} hypotheses")

asyncio.run(run_md_simulation())
```

### Example 2: Using MDAgent Expert Role

```python
from struct_bio_reasoner.agents.roles.mdagent_expert import MDAgentExpert

async def use_mdagent_expert():
    # Create expert
    expert = MDAgentExpert({
        "mdagent": {
            "solvent_model": "explicit"
        }
    })
    
    await expert.initialize()
    
    # Execute thermostability analysis task
    task = {
        "task_type": "thermostability_analysis",
        "protein_data": {
            "pdb_path": "data/1ubq.pdb",
            "name": "ubiquitin"
        }
    }
    
    result = await expert.execute_task(task)
    print(f"Analysis: {result['expert_assessment']}")
    print(f"Recommendations: {result['recommendations']}")

asyncio.run(use_mdagent_expert())
```

### Example 3: Backend Comparison

```python
async def compare_backends():
    for backend in ["openmm", "mdagent"]:
        agent = MolecularDynamicsAgent({"md_backend": backend})
        await agent.initialize()
        
        status = agent.get_agent_status()
        print(f"{backend}: {status['initialized']}")

asyncio.run(compare_backends())
```

## Features

### MDAgent Backend Features

1. **System Building**
   - Automatic solvation (implicit/explicit)
   - Force field selection
   - System preparation and minimization

2. **MD Simulation**
   - Equilibration phase
   - Production runs
   - Configurable timesteps and duration

3. **Trajectory Analysis** (with MDTraj)
   - RMSD (Root Mean Square Deviation)
   - RMSF (Root Mean Square Fluctuation)
   - Radius of gyration
   - Secondary structure analysis (DSSP)
   - Flexible/stable residue identification

4. **Hypothesis Generation**
   - Automatic conversion of MD results to ProteinHypothesis objects
   - Confidence scoring based on trajectory quality
   - Integration with StructBioReasoner workflows

### Comparison: OpenMM vs MDAgent

| Feature | OpenMM Backend | MDAgent Backend |
|---------|---------------|-----------------|
| Installation | Lightweight | Requires MDAgent |
| Solvent Models | Implicit/Explicit | Implicit/Explicit |
| System Building | Manual | Automatic |
| Workflow | Custom | Standardized |
| Integration | Native | Adapter |
| Best For | Quick simulations | Production workflows |

## Advanced Usage

### Custom Simulation Parameters

```python
config = {
    "md_backend": "mdagent",
    "mdagent": {
        "solvent_model": "explicit",
        "force_field": "amber14",
        "water_model": "tip3p",
        "equil_steps": 50_000,      # Longer equilibration
        "prod_steps": 5_000_000,    # 10 ns production
        "protein": true,
        "output_file": "custom_system.pdb"
    }
}
```

### Accessing Raw MDAgent Results

```python
# Run simulation
result = await agent.mdagent_adapter.run_md_simulation(
    pdb_path=Path("data/1ubq.pdb"),
    protein_name="ubiquitin"
)

# Access trajectory analysis
if result['success']:
    traj_analysis = result['trajectory_analysis']
    print(f"RMSD: {traj_analysis['rmsd']}")
    print(f"RMSF: {traj_analysis['rmsf']}")
    print(f"Flexible residues: {traj_analysis['flexibility_analysis']['flexible_residues']}")
```

### Integration with Role Orchestrator

```python
from struct_bio_reasoner.agents.roles.role_orchestrator import RoleOrchestrator
from struct_bio_reasoner.agents.roles.mdagent_expert import MDAgentExpert

# Create orchestrator
orchestrator = RoleOrchestrator({})

# Add MDAgent expert
mdagent_expert = MDAgentExpert({"mdagent": {"solvent_model": "explicit"}})
await mdagent_expert.initialize()
orchestrator.register_expert_role("mdagent_expert", mdagent_expert)

# Execute workflow
protein_data = {
    "pdb_path": "data/1ubq.pdb",
    "name": "ubiquitin",
    "sequence": "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG"
}

results = await orchestrator.execute_protein_engineering_workflow(
    protein_data=protein_data,
    objectives=["thermostability", "stability_enhancement"]
)
```

## Troubleshooting

### MDAgent Not Available

**Error**: `MDAgent not available - cannot initialize adapter`

**Solution**: Install MDAgent:
```bash
git clone https://github.com/msinclair-py/MDAgent.git
cd MDAgent
pip install -e .
```

### Trajectory Analysis Fails

**Error**: `MDTraj not available - skipping detailed trajectory analysis`

**Solution**: Install MDTraj:
```bash
pip install mdtraj
```

### Fallback to OpenMM

If MDAgent initialization fails, the system automatically falls back to OpenMM:

```
WARNING - MDAgent not available - falling back to OpenMM
```

This ensures your workflows continue to work even if MDAgent is not installed.

## Performance Considerations

### Memory Usage

- **Explicit Solvent**: Higher memory usage (~2-10 GB depending on system size)
- **Implicit Solvent**: Lower memory usage (~500 MB - 2 GB)

### Simulation Time

- **Equilibration**: ~1-5 minutes (10,000 steps)
- **Production**: ~10-60 minutes per ns (depends on system size and hardware)

### Recommendations

1. **Development/Testing**: Use implicit solvent with shorter simulations
2. **Production**: Use explicit solvent with longer simulations (>10 ns)
3. **GPU Acceleration**: Enable CUDA for 10-100x speedup

## API Reference

### MolecularDynamicsAgent

```python
class MolecularDynamicsAgent(BaseAgent):
    def __init__(self, config: Dict[str, Any])
    async def initialize(self) -> bool
    async def generate_hypotheses(self, context: Dict[str, Any]) -> List[Dict[str, Any]]
    def get_agent_status(self) -> Dict[str, Any]
```

### MDAgentAdapter

```python
class MDAgentAdapter(BaseAgent):
    async def run_md_simulation(
        self,
        pdb_path: Path,
        protein_name: str,
        custom_build_kwargs: Optional[Dict[str, Any]] = None,
        custom_sim_kwargs: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]
```

### MDAgentExpert

```python
class MDAgentExpert(BaseRole):
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]
    def get_capabilities(self) -> Dict[str, Any]
```

## Contributing

To extend the MDAgent integration:

1. Add new analysis methods to `MDAgentAdapter._analyze_trajectory()`
2. Implement additional task types in `MDAgentExpert.execute_task()`
3. Enhance hypothesis generation in `MolecularDynamicsAgent._generate_thermostability_mdagent()`

## References

- [MDAgent Repository](https://github.com/msinclair-py/MDAgent)
- [StructBioReasoner Documentation](../README.md)
- [OpenMM Documentation](http://docs.openmm.org/)
- [MDTraj Documentation](https://mdtraj.org/)

