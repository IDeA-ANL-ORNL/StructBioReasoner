"""
Hotspot Analysis Utilities

This module provides functions to identify binding hotspots from MD simulation trajectories.
Hotspots are defined as residues with high contact frequency, low RMSF, or significant
interaction energy with binding partners.

Author: StructBioReasoner Team
Date: 2025-12-09
"""

import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from pydantic import BaseModel, ConfigDict

try:
    import MDAnalysis as mda
    from MDAnalysis.analysis import contacts, rms
    from MDAnalysis.analysis.rms import RMSF as rmsf
    from MDAnalysis.analysis.distances import distance_array
except ImportError:
    raise ImportError(
        "MDAnalysis is required for hotspot analysis. "
        "Install with: pip install MDAnalysis"
    )

logger = logging.getLogger(__name__)


class HotspotResidue(BaseModel):
    """Data class for hotspot residue information."""
    resid: int
    resname: str
    chain: str
    contact_frequency: float
    avg_distance: float
    rmsf_value: float
    score: float  # Combined hotspot score

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump()


class HotspotAnalysisResult(BaseModel):
    """Results from hotspot analysis."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    hotspot_residues: List[HotspotResidue]
    contact_matrix: np.ndarray
    rmsf_per_residue: np.ndarray
    simulation_path: Path
    
    def get_top_hotspots(self, n: int = 10) -> List[HotspotResidue]:
        """Get top N hotspots by score."""
        sorted_hotspots = sorted(
            self.hotspot_residues,
            key=lambda x: x.score,
            reverse=True
        )
        return sorted_hotspots[:n]
    
    def get_hotspot_resids(self, threshold: float = 0.5) -> List[int]:
        """Get residue IDs with score above threshold."""
        return [
            h.resid for h in self.hotspot_residues
            if h.score >= threshold
        ]


def analyze_hotspots_from_simulations(
    simulation_dirs: List[Path],
    topology_file: str = "system.pdb",
    trajectory_file: str = "prod.dcd",
    selection1: str = "protein and chainID A",
    selection2: str = "protein and chainID B",
    contact_cutoff: float = 4.5,
    contact_frequency_threshold: float = 0.3,
    top_n: int = 10,
    stride: int = 10
) -> Dict[str, HotspotAnalysisResult]:
    """
    Analyze binding hotspots from multiple MD simulation directories.
    
    Args:
        simulation_dirs: List of paths to simulation directories
        topology_file: Name of topology file (default: "system.pdb")
        trajectory_file: Name of trajectory file (default: "prod.dcd")
        selection1: MDAnalysis selection for first protein (target)
        selection2: MDAnalysis selection for second protein (partner/binder)
        contact_cutoff: Distance cutoff for contacts in Angstroms (default: 4.5)
        contact_frequency_threshold: Minimum contact frequency to be hotspot (default: 0.3)
        top_n: Number of top hotspots to identify (default: 10)
        stride: Frame stride for analysis (default: 10, every 10th frame)
        
    Returns:
        Dictionary mapping simulation directory names to HotspotAnalysisResult objects
        
    Example:
        >>> sim_dirs = [Path('./md_sim1'), Path('./md_sim2')]
        >>> results = analyze_hotspots_from_simulations(
        ...     sim_dirs,
        ...     selection1="protein and chainID A",
        ...     selection2="protein and chainID B"
        ... )
        >>> for sim_name, result in results.items():
        ...     top_hotspots = result.get_top_hotspots(n=5)
        ...     print(f"{sim_name}: {[h.resid for h in top_hotspots]}")
    """
    results = {}
    
    for sim_dir in simulation_dirs:
        sim_dir = Path(sim_dir)
        sim_name = sim_dir.name
        
        logger.info(f"Analyzing hotspots for {sim_name}...")
        
        try:
            result = analyze_single_simulation(
                sim_dir=sim_dir,
                topology_file=topology_file,
                trajectory_file=trajectory_file,
                selection1=selection1,
                selection2=selection2,
                contact_cutoff=contact_cutoff,
                contact_frequency_threshold=contact_frequency_threshold,
                top_n=top_n,
                stride=stride
            )
            results[sim_name] = result
            logger.info(f"✓ Found {len(result.hotspot_residues)} hotspot residues in {sim_name}")
            
        except Exception as e:
            logger.error(f"Failed to analyze {sim_name}: {e}")
            continue
    
    return results


def analyze_single_simulation(
    sim_dir: Path,
    topology_file: str,
    trajectory_file: str,
    selection1: str,
    selection2: str,
    contact_cutoff: float,
    contact_frequency_threshold: float,
    top_n: int,
    stride: int
) -> HotspotAnalysisResult:
    """
    Analyze hotspots from a single MD simulation.

    Args:
        sim_dir: Path to simulation directory
        topology_file: Topology file name
        trajectory_file: Trajectory file name
        selection1: Selection string for target protein
        selection2: Selection string for partner/binder
        contact_cutoff: Distance cutoff for contacts (Angstroms)
        contact_frequency_threshold: Minimum contact frequency
        top_n: Number of top hotspots
        stride: Frame stride

    Returns:
        HotspotAnalysisResult object
    """
    # Load trajectory
    topology_path = sim_dir / topology_file
    trajectory_path = sim_dir / trajectory_file

    if not topology_path.exists():
        raise FileNotFoundError(f"Topology file not found: {topology_path}")
    if not trajectory_path.exists():
        raise FileNotFoundError(f"Trajectory file not found: {trajectory_path}")

    logger.info(f"Loading trajectory: {trajectory_path}")
    u = mda.Universe(str(topology_path), str(trajectory_path))

    # Select protein groups
    try:
        protein1 = u.select_atoms(selection1)
        protein2 = u.select_atoms(selection2)
    except Exception as e:
        logger.error(f"Selection failed: {e}")
        logger.info(f"Available segments: {u.segments.segids}")
        logger.info(f"Available chains: {set([a.chainID for a in u.atoms if hasattr(a, 'chainID')])}")
        raise

    if len(protein1) == 0:
        raise ValueError(f"Selection1 '{selection1}' returned 0 atoms")
    if len(protein2) == 0:
        raise ValueError(f"Selection2 '{selection2}' returned 0 atoms")

    logger.info(f"Protein1: {len(protein1)} atoms, {len(protein1.residues)} residues")
    logger.info(f"Protein2: {len(protein2)} atoms, {len(protein2.residues)} residues")

    # Calculate contact frequencies per residue
    logger.info("Calculating contact frequencies...")
    contact_freq = calculate_contact_frequencies(
        u, protein1, protein2, contact_cutoff, stride
    )

    # Calculate RMSF for protein1 residues
    logger.info("Calculating RMSF...")
    rmsf_values = calculate_rmsf(u, protein1, stride)

    # Calculate average distances
    logger.info("Calculating average distances...")
    avg_distances = calculate_average_distances(
        u, protein1, protein2, stride
    )

    # Identify hotspot residues
    logger.info("Identifying hotspot residues...")
    hotspot_residues = identify_hotspots(
        protein1.residues,
        contact_freq,
        rmsf_values,
        avg_distances,
        contact_frequency_threshold,
        top_n
    )

    # Create contact matrix for visualization
    contact_matrix = create_contact_matrix(
        u, protein1, protein2, contact_cutoff, stride
    )

    result = HotspotAnalysisResult(
        hotspot_residues=hotspot_residues,
        contact_matrix=contact_matrix,
        rmsf_per_residue=rmsf_values,
        simulation_path=sim_dir
    )

    return result


def calculate_contact_frequencies(
    universe: mda.Universe,
    protein1: mda.AtomGroup,
    protein2: mda.AtomGroup,
    cutoff: float,
    stride: int
) -> np.ndarray:
    """
    Calculate contact frequency for each residue in protein1 with protein2.

    Args:
        universe: MDAnalysis Universe
        protein1: Target protein atom group
        protein2: Partner protein atom group
        cutoff: Distance cutoff for contacts (Angstroms)
        stride: Frame stride

    Returns:
        Array of contact frequencies per residue (0.0 to 1.0)
    """
    n_residues = len(protein1.residues)
    contact_counts = np.zeros(n_residues)
    n_frames = 0

    for ts in universe.trajectory[::stride]:
        n_frames += 1

        # Calculate distances between all atoms
        dist_matrix = distance_array(
            protein1.positions,
            protein2.positions,
            box=universe.dimensions
        )

        # Find contacts (any atom pair within cutoff)
        contacts_mask = dist_matrix < cutoff

        # Count contacts per residue
        for i, residue in enumerate(protein1.residues):
            residue_atom_indices = residue.atoms.indices - protein1.atoms[0].index
            if np.any(contacts_mask[residue_atom_indices, :]):
                contact_counts[i] += 1

    # Convert to frequencies
    contact_frequencies = contact_counts / n_frames if n_frames > 0 else contact_counts

    return contact_frequencies


def calculate_rmsf(
    universe: mda.Universe,
    protein: mda.AtomGroup,
    stride: int
) -> np.ndarray:
    """
    Calculate RMSF (root mean square fluctuation) per residue.

    Args:
        universe: MDAnalysis Universe
        protein: Protein atom group
        stride: Frame stride

    Returns:
        Array of RMSF values per residue (Angstroms)
    """
    # Use C-alpha atoms for RMSF calculation
    try:
        ca_atoms = protein.select_atoms("name CA")
    except:
        # Fallback to all atoms if CA selection fails
        ca_atoms = protein

    if len(ca_atoms) == 0:
        logger.warning("No CA atoms found, using all atoms for RMSF")
        ca_atoms = protein

    # Align trajectory to first frame
    from MDAnalysis.analysis import align
    align.AlignTraj(universe, universe, select=protein.select_atoms("name CA and backbone"),
                    in_memory=False).run(step=stride)

    # Calculate RMSF
    rmsf_analysis = rmsf.RMSF(ca_atoms).run(step=stride)
    rmsf_values = rmsf_analysis.results.rmsf

    return rmsf_values


def calculate_average_distances(
    universe: mda.Universe,
    protein1: mda.AtomGroup,
    protein2: mda.AtomGroup,
    stride: int
) -> np.ndarray:
    """
    Calculate average minimum distance from each residue to partner protein.

    Args:
        universe: MDAnalysis Universe
        protein1: Target protein atom group
        protein2: Partner protein atom group
        stride: Frame stride

    Returns:
        Array of average minimum distances per residue (Angstroms)
    """
    n_residues = len(protein1.residues)
    min_distances = np.zeros((n_residues, len(universe.trajectory[::stride])))

    for frame_idx, ts in enumerate(universe.trajectory[::stride]):
        for i, residue in enumerate(protein1.residues):
            # Calculate minimum distance from this residue to protein2
            dist_matrix = distance_array(
                residue.atoms.positions,
                protein2.positions,
                box=universe.dimensions
            )
            min_distances[i, frame_idx] = np.min(dist_matrix)

    # Average over trajectory
    avg_distances = np.mean(min_distances, axis=1)

    return avg_distances


def create_contact_matrix(
    universe: mda.Universe,
    protein1: mda.AtomGroup,
    protein2: mda.AtomGroup,
    cutoff: float,
    stride: int
) -> np.ndarray:
    """
    Create residue-residue contact matrix averaged over trajectory.

    Args:
        universe: MDAnalysis Universe
        protein1: Target protein atom group
        protein2: Partner protein atom group
        cutoff: Distance cutoff for contacts (Angstroms)
        stride: Frame stride

    Returns:
        2D array of contact frequencies (n_residues1 x n_residues2)
    """
    n_res1 = len(protein1.residues)
    n_res2 = len(protein2.residues)
    contact_matrix = np.zeros((n_res1, n_res2))
    n_frames = 0

    for ts in universe.trajectory[::stride]:
        n_frames += 1

        for i, res1 in enumerate(protein1.residues):
            for j, res2 in enumerate(protein2.residues):
                # Calculate minimum distance between residues
                dist_matrix = distance_array(
                    res1.atoms.positions,
                    res2.atoms.positions,
                    box=universe.dimensions
                )
                min_dist = np.min(dist_matrix)

                if min_dist < cutoff:
                    contact_matrix[i, j] += 1

    # Convert to frequencies
    contact_matrix = contact_matrix / n_frames if n_frames > 0 else contact_matrix

    return contact_matrix


def identify_hotspots(
    residues: mda.ResidueGroup,
    contact_frequencies: np.ndarray,
    rmsf_values: np.ndarray,
    avg_distances: np.ndarray,
    contact_threshold: float,
    top_n: int
) -> List[HotspotResidue]:
    """
    Identify hotspot residues based on contact frequency, RMSF, and distance.

    Hotspot score is calculated as:
        score = contact_frequency * (1 - normalized_rmsf) * (1 - normalized_distance)

    Args:
        residues: MDAnalysis ResidueGroup
        contact_frequencies: Contact frequency per residue
        rmsf_values: RMSF per residue
        avg_distances: Average distance per residue
        contact_threshold: Minimum contact frequency
        top_n: Number of top hotspots to return

    Returns:
        List of HotspotResidue objects sorted by score
    """
    # Normalize RMSF and distances to [0, 1]
    rmsf_norm = rmsf_values / np.max(rmsf_values) if np.max(rmsf_values) > 0 else rmsf_values
    dist_norm = avg_distances / np.max(avg_distances) if np.max(avg_distances) > 0 else avg_distances

    # Calculate hotspot scores
    # High contact frequency, low RMSF (rigid), low distance (close) = high score
    scores = contact_frequencies * (1 - rmsf_norm) * (1 - dist_norm)

    # Create HotspotResidue objects
    hotspot_list = []
    for i, residue in enumerate(residues):
        # Only include residues above contact threshold
        if contact_frequencies[i] >= contact_threshold:
            hotspot = HotspotResidue(
                resid=residue.resid,
                resname=residue.resname,
                chain=residue.segid if hasattr(residue, 'segid') else
                      (residue.chainID if hasattr(residue, 'chainID') else 'A'),
                contact_frequency=float(contact_frequencies[i]),
                avg_distance=float(avg_distances[i]),
                rmsf_value=float(rmsf_values[i]),
                score=float(scores[i])
            )
            hotspot_list.append(hotspot)

    # Sort by score (descending)
    hotspot_list.sort(key=lambda x: x.score, reverse=True)

    # Return top N
    return hotspot_list[:top_n] if top_n > 0 else hotspot_list


def save_hotspot_results(
    results: Dict[str, HotspotAnalysisResult],
    output_dir: Path,
    format: str = 'json'
) -> None:
    """
    Save hotspot analysis results to file.

    Args:
        results: Dictionary of HotspotAnalysisResult objects
        output_dir: Output directory path
        format: Output format ('json' or 'csv')
    """
    import json
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if format == 'json':
        # Save as JSON
        output_data = {}
        for sim_name, result in results.items():
            output_data[sim_name] = {
                'hotspot_residues': [h.to_dict() for h in result.hotspot_residues],
                'simulation_path': str(result.simulation_path),
                'n_hotspots': len(result.hotspot_residues)
            }

        output_file = output_dir / 'hotspot_analysis.json'
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)

        logger.info(f"Saved hotspot results to {output_file}")

    elif format == 'csv':
        # Save as CSV
        import csv
        output_file = output_dir / 'hotspot_analysis.csv'

        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'simulation', 'resid', 'resname', 'chain',
                'contact_frequency', 'avg_distance', 'rmsf', 'score'
            ])

            for sim_name, result in results.items():
                for hotspot in result.hotspot_residues:
                    writer.writerow([
                        sim_name,
                        hotspot.resid,
                        hotspot.resname,
                        hotspot.chain,
                        f"{hotspot.contact_frequency:.3f}",
                        f"{hotspot.avg_distance:.2f}",
                        f"{hotspot.rmsf_value:.2f}",
                        f"{hotspot.score:.3f}"
                    ])

        logger.info(f"Saved hotspot results to {output_file}")


def visualize_hotspots(
    result: HotspotAnalysisResult,
    output_file: Optional[Path] = None
) -> None:
    """
    Create visualization of hotspot analysis results.

    Args:
        result: HotspotAnalysisResult object
        output_file: Optional path to save figure
    """
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ImportError:
        logger.warning("matplotlib/seaborn not available, skipping visualization")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))

    # Plot 1: Contact frequency vs RMSF
    ax = axes[0, 0]
    hotspots = result.hotspot_residues
    contact_freqs = [h.contact_frequency for h in hotspots]
    rmsf_vals = [h.rmsf_value for h in hotspots]
    scores = [h.score for h in hotspots]

    scatter = ax.scatter(contact_freqs, rmsf_vals, c=scores, cmap='viridis', s=100)
    ax.set_xlabel('Contact Frequency')
    ax.set_ylabel('RMSF (Å)')
    ax.set_title('Hotspot Residues: Contact Frequency vs RMSF')
    plt.colorbar(scatter, ax=ax, label='Hotspot Score')

    # Plot 2: Hotspot scores
    ax = axes[0, 1]
    resids = [h.resid for h in hotspots]
    ax.bar(range(len(hotspots)), scores)
    ax.set_xlabel('Hotspot Rank')
    ax.set_ylabel('Hotspot Score')
    ax.set_title('Hotspot Scores (Ranked)')

    # Plot 3: Contact matrix heatmap
    ax = axes[1, 0]
    sns.heatmap(result.contact_matrix, cmap='YlOrRd', ax=ax, cbar_kws={'label': 'Contact Frequency'})
    ax.set_xlabel('Partner Residue Index')
    ax.set_ylabel('Target Residue Index')
    ax.set_title('Residue-Residue Contact Matrix')

    # Plot 4: RMSF per residue
    ax = axes[1, 1]
    ax.plot(result.rmsf_per_residue, linewidth=1)
    ax.scatter(
        [i for i, h in enumerate(hotspots)],
        [h.rmsf_value for h in hotspots],
        c='red', s=50, zorder=5, label='Hotspots'
    )
    ax.set_xlabel('Residue Index')
    ax.set_ylabel('RMSF (Å)')
    ax.set_title('RMSF per Residue')
    ax.legend()

    plt.tight_layout()

    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        logger.info(f"Saved visualization to {output_file}")
    else:
        plt.show()

    plt.close()


def get_hotspot_resids_from_simulations(
    simulation_dirs: List[Path],
    top_n: int = 10,
    **kwargs
) -> Dict[str, List[int]]:
    """
    Convenience function to get hotspot residue IDs from simulations.

    Args:
        simulation_dirs: List of simulation directory paths
        top_n: Number of top hotspots to return per simulation
        **kwargs: Additional arguments passed to analyze_hotspots_from_simulations

    Returns:
        Dictionary mapping simulation names to lists of hotspot residue IDs

    Example:
        >>> sim_dirs = [Path('./md_sim1'), Path('./md_sim2')]
        >>> hotspots = get_hotspot_resids_from_simulations(sim_dirs, top_n=5)
        >>> print(hotspots)
        {'md_sim1': [45, 67, 89, 102, 134], 'md_sim2': [45, 67, 91, 105, 138]}
    """
    results = analyze_hotspots_from_simulations(
        simulation_dirs,
        top_n=top_n,
        **kwargs
    )

    hotspot_resids = {}
    for sim_name, result in results.items():
        top_hotspots = result.get_top_hotspots(n=top_n)
        hotspot_resids[sim_name] = [h.resid for h in top_hotspots]

    return hotspot_resids


# Example usage
if __name__ == "__main__":
    import sys

    # Example: Analyze hotspots from command line
    # python -m struct_bio_reasoner.utils.hotspot /path/to/sim1 /path/to/sim2

    if len(sys.argv) < 2:
        print("Usage: python -m struct_bio_reasoner.utils.hotspot <sim_dir1> [sim_dir2] ...")
        print("\nExample:")
        print("  python -m struct_bio_reasoner.utils.hotspot ./data/md_sim1 ./data/md_sim2")
        sys.exit(1)

    # Parse simulation directories from command line
    sim_dirs = [Path(arg) for arg in sys.argv[1:]]

    # Analyze hotspots
    print(f"Analyzing {len(sim_dirs)} simulations...")
    results = analyze_hotspots_from_simulations(
        sim_dirs,
        selection1="protein and segid A",
        selection2="protein and segid B",
        contact_cutoff=4.5,
        contact_frequency_threshold=0.3,
        top_n=10,
        stride=10
    )

    # Print results
    print("\n" + "="*80)
    print("HOTSPOT ANALYSIS RESULTS")
    print("="*80)

    for sim_name, result in results.items():
        print(f"\n{sim_name}:")
        print(f"  Total hotspots identified: {len(result.hotspot_residues)}")
        print(f"  Top 5 hotspots:")

        for i, hotspot in enumerate(result.get_top_hotspots(n=5), 1):
            print(f"    {i}. Residue {hotspot.resid} ({hotspot.resname})")
            print(f"       Contact freq: {hotspot.contact_frequency:.3f}")
            print(f"       Avg distance: {hotspot.avg_distance:.2f} Å")
            print(f"       RMSF: {hotspot.rmsf_value:.2f} Å")
            print(f"       Score: {hotspot.score:.3f}")

    # Save results
    output_dir = Path('./hotspot_analysis_results')
    save_hotspot_results(results, output_dir, format='json')
    save_hotspot_results(results, output_dir, format='csv')

    # Create visualizations
    for sim_name, result in results.items():
        output_file = output_dir / f'{sim_name}_hotspots.png'
        visualize_hotspots(result, output_file)

    print(f"\n✓ Results saved to {output_dir}")
    print("="*80)

