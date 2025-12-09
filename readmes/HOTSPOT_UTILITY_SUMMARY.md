# Hotspot Analysis Utility - Summary

## What Was Created

A comprehensive hotspot analysis utility for identifying binding hotspots from MD simulation trajectories.

### Files Created

1. **`struct_bio_reasoner/utils/hotspot.py`** (703 lines)
   - Complete hotspot analysis implementation
   - Contact frequency calculation
   - RMSF analysis
   - Distance calculations
   - Hotspot scoring algorithm
   - Contact matrix generation
   - Visualization functions
   - Save/export functions

2. **`struct_bio_reasoner/utils/README_HOTSPOT.md`** (440 lines)
   - Comprehensive documentation
   - API reference
   - Usage examples
   - Troubleshooting guide
   - Integration examples

3. **`examples/example_hotspot_analysis.py`** (150 lines)
   - Standalone example script
   - 4 different usage examples
   - Demonstrates all major features

### Files Modified

1. **`examples/nmnat2_agentic_binder_workflow.py`**
   - Integrated hotspot utility (line ~390)
   - Removed placeholder function
   - Now uses real hotspot analysis from MD trajectories

## Key Features

### 🔬 Analysis Capabilities

- **Contact Frequency**: Identifies residues with persistent contacts to binding partners
- **RMSF Analysis**: Measures residue flexibility (rigid residues = better hotspots)
- **Distance Analysis**: Calculates average distances to binding partners
- **Combined Scoring**: Integrates all metrics into a single hotspot score
- **Contact Matrix**: Generates residue-residue interaction maps

### 📊 Hotspot Scoring Algorithm

```python
score = contact_frequency × (1 - normalized_rmsf) × (1 - normalized_distance)
```

**High score** = Frequent contacts + Rigid residue + Close proximity = **Strong hotspot**

### 🎯 Input/Output

**Input:**
- List of simulation directories
- Each directory contains:
  - `system.pdb` (topology)
  - `prod.dcd` (trajectory)

**Output:**
- Ranked list of hotspot residues
- Contact matrices
- RMSF values
- JSON/CSV export
- Visualization plots

## Usage Examples

### Quick Start

```python
from pathlib import Path
from struct_bio_reasoner.utils.hotspot import get_hotspot_resids_from_simulations

# Analyze simulations
sim_dirs = [
    Path('./data/md_simulations/NMNAT2_PARTNER1'),
    Path('./data/md_simulations/NMNAT2_PARTNER2')
]

hotspot_resids = get_hotspot_resids_from_simulations(
    sim_dirs,
    top_n=10,
    selection1="protein and segid A",
    selection2="protein and segid B"
)

# Output: {'NMNAT2_PARTNER1': [45, 67, 89, 102, 134, ...], ...}
```

### Full Analysis

```python
from struct_bio_reasoner.utils.hotspot import (
    analyze_hotspots_from_simulations,
    save_hotspot_results,
    visualize_hotspots
)

# Analyze
results = analyze_hotspots_from_simulations(
    sim_dirs,
    contact_cutoff=4.5,
    contact_frequency_threshold=0.3,
    top_n=10,
    stride=10
)

# Save
save_hotspot_results(results, Path('./output'), format='json')
save_hotspot_results(results, Path('./output'), format='csv')

# Visualize
for sim_name, result in results.items():
    visualize_hotspots(result, Path(f'./output/{sim_name}.png'))
```

### Command Line

```bash
python -m struct_bio_reasoner.utils.hotspot ./data/md_sim1 ./data/md_sim2
```

## Integration with NMNAT-2 Workflow

The hotspot utility is now integrated into the agentic workflow:

```python
# In nmnat2_agentic_binder_workflow.py (line ~390)

from struct_bio_reasoner.utils.hotspot import get_hotspot_resids_from_simulations

# After MD simulations complete
hotspot_resids_dict = get_hotspot_resids_from_simulations(
    sim_directories,
    top_n=10,
    selection1="protein and segid A",  # NMNAT-2
    selection2="protein and segid B",  # Partner protein
    contact_cutoff=4.5,
    contact_frequency_threshold=0.3,
    stride=10
)

# Use hotspots for BindCraft
bindcraft_task = {
    'target_sequence': nmnat2_sequence,
    'hotspot_residues': hotspot_resids_dict['NMNAT2_PARTNER1'],
    'num_rounds': 3,
    'num_sequences': 25
}
```

## API Reference

### Main Functions

#### `analyze_hotspots_from_simulations()`
Full analysis with all metrics and visualizations.

#### `get_hotspot_resids_from_simulations()`
Convenience function - returns just residue IDs.

#### `save_hotspot_results()`
Export to JSON or CSV format.

#### `visualize_hotspots()`
Generate 4-panel visualization figure.

### Data Classes

#### `HotspotResidue`
- `resid`: Residue ID
- `resname`: Residue name
- `chain`: Chain/segment ID
- `contact_frequency`: 0.0 to 1.0
- `avg_distance`: Angstroms
- `rmsf_value`: Angstroms
- `score`: Combined hotspot score

#### `HotspotAnalysisResult`
- `hotspot_residues`: List of HotspotResidue objects
- `contact_matrix`: 2D numpy array
- `rmsf_per_residue`: 1D numpy array
- `simulation_path`: Path to simulation

## Output Files

### JSON Format
```json
{
  "NMNAT2_PARTNER1": {
    "hotspot_residues": [
      {
        "resid": 45,
        "resname": "GLU",
        "chain": "A",
        "contact_frequency": 0.87,
        "avg_distance": 3.2,
        "rmsf_value": 0.8,
        "score": 0.75
      }
    ]
  }
}
```

### CSV Format
```csv
simulation,resid,resname,chain,contact_frequency,avg_distance,rmsf,score
NMNAT2_PARTNER1,45,GLU,A,0.870,3.20,0.80,0.750
```

### Visualization
Four-panel figure:
1. Contact Frequency vs RMSF scatter plot
2. Hotspot scores bar chart
3. Contact matrix heatmap
4. RMSF per residue line plot

## Requirements

```bash
pip install MDAnalysis
pip install matplotlib seaborn  # Optional, for visualization
```

## Documentation

- **Full API docs**: `struct_bio_reasoner/utils/README_HOTSPOT.md`
- **Example script**: `examples/example_hotspot_analysis.py`
- **Source code**: `struct_bio_reasoner/utils/hotspot.py`

## Next Steps

1. **Test the utility** with your MD simulation data
2. **Integrate into workflow** (already done in `nmnat2_agentic_binder_workflow.py`)
3. **Customize parameters** for your specific use case
4. **Visualize results** to validate hotspot identification

## Support

For issues or questions:
- Check `README_HOTSPOT.md` for troubleshooting
- Run `example_hotspot_analysis.py` to verify installation
- Ensure MDAnalysis is installed correctly
- Verify simulation file formats (PDB + DCD)
