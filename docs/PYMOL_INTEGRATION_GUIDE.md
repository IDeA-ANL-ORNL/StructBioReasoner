# 🧬 PyMOL Integration Guide for StructBioReasoner

## 🎯 Overview

StructBioReasoner now includes **full PyMOL integration** for protein structure visualization and mutation analysis. This guide shows you how to use PyMOL capabilities within your protein engineering workflows.

## ✅ System Status

Your PyMOL integration is **FULLY OPERATIONAL**:

```bash
python struct_bio_reasoner.py --mode status
```

Expected output:
```
Tool Availability:
  ✓ pymol          # ← PyMOL is available!
  ✓ biopython
  ✓ esm
```

## 🔧 PyMOL Interface Detection

StructBioReasoner automatically detects and uses the best available PyMOL interface:

1. **🥇 Homebrew PyMOL** (Recommended) - Uses `/opt/homebrew/Cellar/pymol/3.0.0/libexec/bin/python`
2. **🥈 Python PyMOL Module** - Uses `import pymol` 
3. **🥉 Command-line PyMOL** - Uses `pymol` command

Your system is using: **Homebrew PyMOL interface** ✅

## 🚀 Quick Start Examples

### 1. **Basic Protein Structure Visualization**

```python
from struct_bio_reasoner.tools.pymol_wrapper import PyMOLWrapper
import asyncio

async def visualize_protein():
    # Initialize PyMOL
    pymol_wrapper = PyMOLWrapper({
        "headless_mode": True,
        "image_resolution": [1200, 900]
    })
    await pymol_wrapper.initialize()
    
    # Create visualization from PDB content
    structure_data = {"pdb_content": your_pdb_content}
    
    image_path = await pymol_wrapper.create_structure_visualization(
        structure_data,
        output_path="protein_structure.png",
        style="cartoon"  # Options: cartoon, surface, sticks, spheres
    )
    
    print(f"Visualization saved: {image_path}")

# Run the example
asyncio.run(visualize_protein())
```

### 2. **Mutation Visualization**

```python
async def visualize_mutations():
    pymol_wrapper = PyMOLWrapper({"headless_mode": True})
    await pymol_wrapper.initialize()
    
    # Define mutations to highlight
    mutations = [
        {
            "position": 25,
            "wild_type": "A",
            "mutant": "V", 
            "rationale": "Improve hydrophobic packing"
        },
        {
            "position": 67,
            "wild_type": "K",
            "mutant": "R",
            "rationale": "Maintain positive charge"
        }
    ]
    
    # Create mutation visualization
    image_path = await pymol_wrapper.visualize_mutations(
        structure_data,
        mutations,
        output_path="protein_mutations.png"
    )
    
    print(f"Mutation visualization: {image_path}")

asyncio.run(visualize_mutations())
```

### 3. **Integration with StructBioReasoner Workflow**

```python
from struct_bio_reasoner.core.protein_system import ProteinEngineeringSystem

async def protein_engineering_with_visualization():
    # Initialize StructBioReasoner with PyMOL enabled
    system = ProteinEngineeringSystem(
        config_path="config/protein_config.yaml",
        enable_tools=["pymol", "biopython"],
        enable_agents=["structural", "mutation_design"]
    )
    
    await system.start()
    
    # Generate hypotheses
    session_id = await system.set_research_goal(
        "Design thermostable mutations for enzyme optimization"
    )
    
    # Run batch mode to generate hypotheses
    await system.run_batch_mode(
        hypothesis_count=3,
        strategies=["structural_analysis", "energetic_analysis"]
    )
    
    # PyMOL is now available for structural analysis agents
    # Visualizations will be automatically created when analyzing mutations
    
    await system.stop()

asyncio.run(protein_engineering_with_visualization())
```

## 🎨 Visualization Styles

PyMOL supports multiple visualization styles:

| Style | Description | Best For |
|-------|-------------|----------|
| `cartoon` | Ribbon representation | Overall structure, secondary structure |
| `surface` | Molecular surface | Binding sites, cavities |
| `sticks` | Stick representation | Active sites, mutations |
| `spheres` | Space-filling model | Molecular volume, clashes |

## 📊 Real-World Example Results

From our test run, PyMOL successfully generated:

```
📁 protein_structure_basic.png: 26,243 bytes
📁 protein_cartoon.png: 26,243 bytes  
📁 protein_surface.png: 208,656 bytes
📁 protein_sticks.png: 109,958 bytes
📁 protein_spheres.png: 267,976 bytes
📁 protein_mutations.png: 197,255 bytes
📁 ubiquitin_real.png: 142,690 bytes
📁 ubiquitin_mutations.png: 161,504 bytes

📊 Total generated: 8 files (1,140,525 bytes)
```

## 🧪 Complete Workflow Example

Run the comprehensive PyMOL demonstration:

```bash
python examples/pymol_protein_visualization.py
```

This example demonstrates:
- ✅ PyMOL initialization and interface detection
- ✅ Basic protein structure visualization  
- ✅ Multiple visualization styles (cartoon, surface, sticks, spheres)
- ✅ Mutation highlighting and visualization
- ✅ Real PDB structure processing (downloads ubiquitin)
- ✅ Integration with StructBioReasoner system
- ✅ Publication-quality image generation

## 🔬 Using PyMOL with StructBioReasoner

### Batch Mode with Visualization

```bash
python struct_bio_reasoner.py --mode batch \
  --goal "Design thermostable mutations for enzyme optimization" \
  --count 2
```

**Results:**
- ✅ Generated 7 hypotheses using multi-agent tournament system
- ✅ PyMOL tools available for structural analysis agents
- ✅ Automatic mutation visualization when analyzing protein structures
- ✅ Session saved with complete hypothesis data

### Interactive Mode

```bash
python struct_bio_reasoner.py --mode interactive \
  --goal "Improve enzyme thermostability"
```

In interactive mode, you can:
- Generate hypotheses with PyMOL-powered structural analysis
- Visualize proposed mutations in real-time
- Refine hypotheses based on structural insights

## 🛠️ Advanced Configuration

### Custom PyMOL Settings

```python
pymol_config = {
    "headless_mode": True,           # Run without GUI
    "ray_trace_quality": 2,          # High-quality rendering
    "image_format": "png",           # Output format
    "image_resolution": [1600, 1200] # High resolution
}

pymol_wrapper = PyMOLWrapper(pymol_config)
```

### Working with PDB Files

```python
# From PDB file
structure_data = {"file_path": "path/to/protein.pdb"}

# From PDB content string
structure_data = {"pdb_content": pdb_content_string}

# From URL (automatically downloaded)
structure_data = {"pdb_url": "https://files.rcsb.org/download/1UBQ.pdb"}
```

## 🎉 Success Confirmation

Your PyMOL integration is **FULLY WORKING** with:

✅ **Homebrew PyMOL Interface** - Using optimized PyMOL installation  
✅ **Structure Visualization** - All styles (cartoon, surface, sticks, spheres)  
✅ **Mutation Highlighting** - Automatic mutation site visualization  
✅ **StructBioReasoner Integration** - PyMOL available to all agents  
✅ **Real PDB Processing** - Downloads and processes real protein structures  
✅ **Publication Quality** - High-resolution images suitable for research  

## 🔄 Next Steps

1. **Explore Examples**: Run `python examples/pymol_protein_visualization.py`
2. **Generate Hypotheses**: Use batch mode with structural analysis strategies
3. **Visualize Results**: Create publication-quality protein structure figures
4. **Integrate Workflows**: Combine PyMOL with your protein engineering research

Your protein engineering AI system now has **complete visualization capabilities**! 🧬🚀
