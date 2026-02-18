"""Utilities for StructBioReasoner."""

from .config_loader import (
    load_protein_config,
    validate_config,
    create_config_file,
    get_config_template
)
from .protein_utils import (
    load_protein_structure,
    analyze_sequence,
    validate_protein_sequence,
    get_sequence_info
)
from .parsl_settings import (
    AuroraSettings,
    HeterogeneousSettings,
    LocalSettings,
    LocalCPUSettings,
    PolarisSettings,
    resource_summary_from_config,
)

# Hotspot analysis utilities
try:
    from .hotspot import (
        analyze_hotspots_from_simulations,
        get_hotspot_resids_from_simulations,
        save_hotspot_results,
        visualize_hotspots,
        HotspotResidue,
        HotspotAnalysisResult
    )
    _HOTSPOT_AVAILABLE = True
except ImportError:
    # MDAnalysis not installed
    _HOTSPOT_AVAILABLE = False

__all__ = [
    "load_protein_config",
    "validate_config",
    "create_config_file",
    "get_config_template",
    "load_protein_structure",
    "analyze_sequence",
    "validate_protein_sequence",
    "get_sequence_info",
    "AuroraSettings",
    "PolarisSettings"
]

# Add hotspot utilities if available
if _HOTSPOT_AVAILABLE:
    __all__.extend([
        "analyze_hotspots_from_simulations",
        "get_hotspot_resids_from_simulations",
        "save_hotspot_results",
        "visualize_hotspots",
        "HotspotResidue",
        "HotspotAnalysisResult"
    ])
