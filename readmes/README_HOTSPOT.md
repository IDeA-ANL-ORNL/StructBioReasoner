# Hotspot Analysis Utility

## Overview

The `hotspot.py` module provides comprehensive tools for identifying binding hotspots from MD simulation trajectories. Hotspots are residues with high contact frequency, low flexibility (RMSF), and close proximity to binding partners.

## Features

- ✅ **Multi-simulation analysis** - Analyze multiple MD simulations in parallel
- ✅ **Contact frequency calculation** - Identify residues with persistent contacts
- ✅ **RMSF analysis** - Measure residue flexibility
- ✅ **Distance analysis** - Calculate average distances to binding partners
- ✅ **Hotspot scoring** - Combined metric for ranking residues
- ✅ **Contact matrix generation** - Residue-residue interaction maps
- ✅ **Visualization** - Automatic plot generation
- ✅ **Export** - JSON and CSV output formats

## Installation

Requires MDAnalysis:

```bash
pip install MDAnalysis
```

Optional (for visualization):

```bash
pip install matplotlib seaborn
```

## Quick Start

### Basic Usage

```python
from pathlib import Path
from struct_bio_reasoner.utils.hotspot import analyze_hotspots_from_simulations

# List of simulation directories (each containing system.pdb and prod.dcd)
sim_dirs = [
    Path('./data/md_simulations/NMNAT2_PARTNER1'),
    Path('./data/md_simulations/NMNAT2_PARTNER2'),
    Path('./data/md_simulations/NMNAT2_PARTNER3')
]

# Analyze hotspots
results = analyze_hotspots_from_simulations(
    simulation_dirs=sim_dirs,
    topology_file="system.pdb",      # Topology file name
    trajectory_file="prod.dcd",      # Trajectory file name
    selection1="protein and segid A", # Target protein
    selection2="protein and segid B", # Partner/binder protein
    contact_cutoff=4.5,              # Distance cutoff (Angstroms)
    contact_frequency_threshold=0.3,  # Minimum contact frequency
    top_n=10,                        # Number of top hotspots
    stride=10                        # Analyze every 10th frame
)

# Get top hotspots for each simulation
for sim_name, result in results.items():
    top_hotspots = result.get_top_hotspots(n=5)
    print(f"{sim_name}: {[h.resid for h in top_hotspots]}")
```

### Convenience Function

```python
from struct_bio_reasoner.utils.hotspot import get_hotspot_resids_from_simulations

# Get just the residue IDs
hotspot_resids = get_hotspot_resids_from_simulations(
    sim_dirs,
    top_n=10,
    selection1="protein and chainID A",
    selection2="protein and chainID B"
)

# Output: {'sim1': [45, 67, 89, 102, 134], 'sim2': [45, 67, 91, 105, 138]}
```

### Command Line Usage

```bash
# Analyze simulations from command line
python -m struct_bio_reasoner.utils.hotspot ./data/md_sim1 ./data/md_sim2

# Output saved to ./hotspot_analysis_results/
```

## API Reference

### Main Functions

#### `analyze_hotspots_from_simulations()`

Analyze binding hotspots from multiple MD simulation directories.

**Parameters:**
- `simulation_dirs` (List[Path]): List of paths to simulation directories
- `topology_file` (str): Name of topology file (default: "system.pdb")
- `trajectory_file` (str): Name of trajectory file (default: "prod.dcd")
- `selection1` (str): MDAnalysis selection for target protein
- `selection2` (str): MDAnalysis selection for partner/binder
- `contact_cutoff` (float): Distance cutoff for contacts in Angstroms (default: 4.5)
- `contact_frequency_threshold` (float): Minimum contact frequency (default: 0.3)
- `top_n` (int): Number of top hotspots to identify (default: 10)
- `stride` (int): Frame stride for analysis (default: 10)

**Returns:**
- `Dict[str, HotspotAnalysisResult]`: Dictionary mapping simulation names to results

#### `get_hotspot_resids_from_simulations()`

Convenience function to get hotspot residue IDs.

**Parameters:**
- `simulation_dirs` (List[Path]): List of simulation directory paths
- `top_n` (int): Number of top hotspots per simulation
- `**kwargs`: Additional arguments for `analyze_hotspots_from_simulations()`

**Returns:**
- `Dict[str, List[int]]`: Dictionary mapping simulation names to residue ID lists

#### `save_hotspot_results()`

Save hotspot analysis results to file.

**Parameters:**
- `results` (Dict[str, HotspotAnalysisResult]): Analysis results
- `output_dir` (Path): Output directory path
- `format` (str): Output format ('json' or 'csv')

#### `visualize_hotspots()`

Create visualization of hotspot analysis results.

**Parameters:**
- `result` (HotspotAnalysisResult): Single simulation result
- `output_file` (Optional[Path]): Path to save figure

### Data Classes

#### `HotspotResidue`

Represents a single hotspot residue.

**Attributes:**
- `resid` (int): Residue ID
- `resname` (str): Residue name (e.g., "ALA", "GLY")
- `chain` (str): Chain/segment ID
- `contact_frequency` (float): Contact frequency (0.0 to 1.0)
- `avg_distance` (float): Average distance to partner (Angstroms)
- `rmsf_value` (float): RMSF value (Angstroms)
- `score` (float): Combined hotspot score

**Methods:**
- `to_dict()`: Convert to dictionary

#### `HotspotAnalysisResult`

Results from hotspot analysis.

**Attributes:**
- `hotspot_residues` (List[HotspotResidue]): List of hotspot residues
- `contact_matrix` (np.ndarray): Residue-residue contact matrix
- `rmsf_per_residue` (np.ndarray): RMSF values for all residues
- `simulation_path` (Path): Path to simulation directory

**Methods:**
- `get_top_hotspots(n: int)`: Get top N hotspots by score
- `get_hotspot_resids(threshold: float)`: Get residue IDs above score threshold

## Hotspot Scoring Algorithm

The hotspot score combines three metrics:

```python
score = contact_frequency × (1 - normalized_rmsf) × (1 - normalized_distance)
```

**Components:**
1. **Contact Frequency** (0.0 to 1.0): Fraction of frames with contact
2. **Normalized RMSF** (0.0 to 1.0): Residue flexibility (lower is better)
3. **Normalized Distance** (0.0 to 1.0): Average distance to partner (lower is better)

**Interpretation:**
- **High score**: Frequent contacts, rigid residue, close to partner → **Strong hotspot**
- **Low score**: Infrequent contacts, flexible residue, far from partner → **Weak hotspot**

## Selection Strings

MDAnalysis selection syntax for different file formats:

### PDB Files with Chain IDs
```python
selection1 = "protein and chainID A"
selection2 = "protein and chainID B"
```

### Files with Segment IDs
```python
selection1 = "protein and segid A"
selection2 = "protein and segid B"
```

### Specific Residue Ranges
```python
selection1 = "protein and resid 1-250"
selection2 = "protein and resid 251-300"
```

### By Residue Name
```python
selection1 = "protein and not resname HOH"  # Exclude water
selection2 = "resname LIG"  # Ligand only
```

## Integration with NMNAT-2 Workflow

Use in the agentic workflow:

```python
from struct_bio_reasoner.utils.hotspot import get_hotspot_resids_from_simulations

# After MD simulations complete
md_simulation_dirs = [
    Path('./data/md_simulations/NMNAT2_PARTNER1'),
    Path('./data/md_simulations/NMNAT2_PARTNER2')
]

# Identify hotspots
hotspot_resids = get_hotspot_resids_from_simulations(
    md_simulation_dirs,
    top_n=10,
    selection1="protein and segid A",  # NMNAT-2
    selection2="protein and segid B",  # Partner protein
    contact_cutoff=4.5,
    stride=10
)

# Use hotspots for BindCraft
for sim_name, resids in hotspot_resids.items():
    print(f"{sim_name} hotspots: {resids}")

    # Pass to BindCraft
    bindcraft_task = {
        'target_sequence': nmnat2_sequence,
        'hotspot_residues': resids,
        'num_rounds': 3,
        'num_sequences': 25
    }
```

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
    ],
    "simulation_path": "./data/md_simulations/NMNAT2_PARTNER1",
    "n_hotspots": 10
  }
}
```

### CSV Format

```csv
simulation,resid,resname,chain,contact_frequency,avg_distance,rmsf,score
NMNAT2_PARTNER1,45,GLU,A,0.870,3.20,0.80,0.750
NMNAT2_PARTNER1,67,ASP,A,0.820,3.45,0.75,0.720
```

### Visualization

Four-panel figure for each simulation:
1. **Contact Frequency vs RMSF** - Scatter plot colored by score
2. **Hotspot Scores** - Bar chart of ranked hotspots
3. **Contact Matrix** - Heatmap of residue-residue contacts
4. **RMSF per Residue** - Line plot with hotspots highlighted

## Examples

### Example 1: Basic Analysis

```python
from pathlib import Path
from struct_bio_reasoner.utils.hotspot import analyze_hotspots_from_simulations

sim_dirs = [Path('./md_sim1'), Path('./md_sim2')]

results = analyze_hotspots_from_simulations(
    sim_dirs,
    selection1="protein and chainID A",
    selection2="protein and chainID B"
)

for sim_name, result in results.items():
    print(f"\n{sim_name}:")
    for hotspot in result.get_top_hotspots(n=5):
        print(f"  Residue {hotspot.resid}: score={hotspot.score:.3f}")
```

### Example 2: Custom Parameters

```python
results = analyze_hotspots_from_simulations(
    sim_dirs,
    topology_file="complex.pdb",
    trajectory_file="trajectory.dcd",
    selection1="protein and segid PROA",
    selection2="protein and segid PROB",
    contact_cutoff=5.0,              # Looser cutoff
    contact_frequency_threshold=0.5,  # Stricter threshold
    top_n=20,                        # More hotspots
    stride=5                         # More frames
)
```

### Example 3: Save and Visualize

```python
from struct_bio_reasoner.utils.hotspot import (
    analyze_hotspots_from_simulations,
    save_hotspot_results,
    visualize_hotspots
)

results = analyze_hotspots_from_simulations(sim_dirs)

# Save results
output_dir = Path('./hotspot_results')
save_hotspot_results(results, output_dir, format='json')
save_hotspot_results(results, output_dir, format='csv')

# Create visualizations
for sim_name, result in results.items():
    output_file = output_dir / f'{sim_name}_hotspots.png'
    visualize_hotspots(result, output_file)
```

### Example 4: Filter by Score Threshold

```python
results = analyze_hotspots_from_simulations(sim_dirs)

for sim_name, result in results.items():
    # Get all hotspots with score > 0.5
    high_score_resids = result.get_hotspot_resids(threshold=0.5)
    print(f"{sim_name}: {len(high_score_resids)} high-scoring hotspots")
    print(f"  Residue IDs: {high_score_resids}")
```

## Troubleshooting

### Issue: "No module named 'MDAnalysis'"

**Solution:**
```bash
pip install MDAnalysis
```

### Issue: Selection returns 0 atoms

**Error:** `ValueError: Selection1 'protein and segid A' returned 0 atoms`

**Solution:** Check available segments/chains:
```python
import MDAnalysis as mda
u = mda.Universe("system.pdb", "prod.dcd")
print(f"Segments: {u.segments.segids}")
print(f"Chains: {set([a.chainID for a in u.atoms if hasattr(a, 'chainID')])}")
```

Then adjust selection strings accordingly.

### Issue: Trajectory file not found

**Error:** `FileNotFoundError: Trajectory file not found: /path/to/prod.dcd`

**Solution:** Ensure each simulation directory contains both `system.pdb` and `prod.dcd`:
```
md_simulations/
├── NMNAT2_PARTNER1/
│   ├── system.pdb
│   └── prod.dcd
└── NMNAT2_PARTNER2/
    ├── system.pdb
    └── prod.dcd
```

### Issue: Memory error with large trajectories

**Solution:** Increase stride to analyze fewer frames:
```python
results = analyze_hotspots_from_simulations(
    sim_dirs,
    stride=50  # Analyze every 50th frame instead of every 10th
)
```

### Issue: RMSF calculation fails

**Error:** Related to alignment or CA atom selection

**Solution:** The code automatically falls back to all atoms if CA selection fails. Check logs for warnings.

## Performance Tips

- **Stride**: Use `stride=10` or higher for faster analysis
- **Contact cutoff**: Smaller cutoff (3.5-4.5 Å) = faster calculation
- **Top N**: Request only the hotspots you need
- **Parallel processing**: Analyze multiple simulations in parallel (future enhancement)

## Citation

If you use this hotspot analysis utility in your research, please cite:
- **StructBioReasoner**: https://github.com/IDeA-ANL-ORNL/StructBioReasoner
- **MDAnalysis**: Michaud-Agrawal et al. (2011) J. Comput. Chem. 32, 2319-2327

## Support

For issues or questions:
1. Check this README for common solutions
2. Verify MDAnalysis is installed correctly
3. Check simulation file formats and paths
4. Open an issue on GitHub with error logs
