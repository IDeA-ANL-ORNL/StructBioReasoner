"""
StructBioReasoner: Jnana-Based Structural Biology Reasoning Model

This package extends the Jnana framework for protein engineering applications,
providing specialized agents, tools, and knowledge systems for structural biology.
"""

__version__ = "0.1.0"
__author__ = "StructBioReasoner Team"
__description__ = "Jnana-based structural biology reasoning model for protein engineering"

# Core imports
from .core.protein_system import ProteinEngineeringSystem
from .data.protein_hypothesis import ProteinHypothesis, MutationHypothesis
from .data.mutation_model import Mutation, MutationSet, MutationEffect

# Agent imports
from .agents.structural.structural_agent import StructuralAnalysisAgent
from .agents.evolutionary.conservation_agent import EvolutionaryConservationAgent
from .agents.energetic.energy_agent import EnergeticAnalysisAgent
from .agents.design.mutation_agent import MutationDesignAgent

# Tool imports
from .tools.pymol_wrapper import PyMOLWrapper
from .tools.biopython_utils import BioPythonUtils

# Utility imports
from .utils.protein_utils import load_protein_structure, analyze_sequence
from .utils.config_loader import load_protein_config

# Version information
VERSION_INFO = {
    "version": __version__,
    "jnana_compatible": ">=0.1.0",
    "python_required": ">=3.8",
    "dependencies": {
        "core": ["biopython", "pymol-open-source", "numpy", "pandas"],
        "optional": ["rosetta", "alphafold", "esm"],
        "databases": ["neo4j", "networkx"]
    }
}

# Configuration defaults
DEFAULT_CONFIG = {
    "jnana_config_path": "../Jnana/config/models.yaml",
    "protein_config_path": "config/protein_config.yaml",
    "enable_tools": ["pymol", "biopython"],
    "enable_agents": ["structural", "evolutionary", "energetic", "design"],
    "knowledge_graph": True,
    "literature_processing": True,
    "enable_biomni": False  # Disabled by default
}

# Export main classes and functions
__all__ = [
    # Core system
    "ProteinEngineeringSystem",
    
    # Data models
    "ProteinHypothesis",
    "MutationHypothesis", 
    "Mutation",
    "MutationSet",
    "MutationEffect",
    
    # Agents
    "StructuralAnalysisAgent",
    "EvolutionaryConservationAgent",
    "EnergeticAnalysisAgent",
    "MutationDesignAgent",
    
    # Tools
    "PyMOLWrapper",
    "BioPythonUtils",
    
    # Utilities
    "load_protein_structure",
    "analyze_sequence",
    "load_protein_config",
    
    # Constants
    "VERSION_INFO",
    "DEFAULT_CONFIG"
]

# Package-level configuration
import logging
import os
from pathlib import Path

# Setup logging
logging.getLogger(__name__).addHandler(logging.NullHandler())

# Package paths
PACKAGE_ROOT = Path(__file__).parent
CONFIG_DIR = PACKAGE_ROOT.parent / "config"
DATA_DIR = PACKAGE_ROOT.parent / "data"
TESTS_DIR = PACKAGE_ROOT.parent / "tests"

# Environment variable defaults
os.environ.setdefault("STRUCT_BIO_CONFIG", str(CONFIG_DIR / "protein_config.yaml"))
os.environ.setdefault("STRUCT_BIO_DATA", str(DATA_DIR))

# Compatibility checks
def check_jnana_compatibility():
    """Check if Jnana is available and compatible."""
    try:
        import sys
        sys.path.append(str(Path(__file__).parent.parent.parent / "Jnana"))
        
        from jnana import JnanaSystem
        from jnana.data.unified_hypothesis import UnifiedHypothesis
        return True
    except ImportError as e:
        logging.warning(f"Jnana not found or incompatible: {e}")
        return False

def check_tool_availability():
    """Check availability of optional tools."""
    tools_status = {}

    # Check PyMOL (using same logic as PyMOL wrapper)
    pymol_python_available = False
    try:
        import pymol
        pymol_python_available = True
    except ImportError:
        pass

    # Check for command-line PyMOL
    import shutil
    pymol_command_available = bool(shutil.which("pymol"))

    # Check for Homebrew PyMOL
    import os
    homebrew_pymol_path = "/opt/homebrew/Cellar/pymol/3.0.0/libexec/bin/python"
    homebrew_pymol_available = os.path.exists(homebrew_pymol_path)

    # PyMOL is available if any interface is available
    tools_status["pymol"] = pymol_python_available or pymol_command_available or homebrew_pymol_available
    
    # Check BioPython
    try:
        import Bio
        tools_status["biopython"] = True
    except ImportError:
        tools_status["biopython"] = False
    
    # Check ESM
    try:
        import esm
        tools_status["esm"] = True
    except ImportError:
        tools_status["esm"] = False
    
    # Check Neo4j
    try:
        import neo4j
        tools_status["neo4j"] = True
    except ImportError:
        tools_status["neo4j"] = False
    
    return tools_status

# Run compatibility checks on import
JNANA_AVAILABLE = check_jnana_compatibility()
TOOLS_AVAILABLE = check_tool_availability()

# Package status
PACKAGE_STATUS = {
    "jnana_available": JNANA_AVAILABLE,
    "tools_available": TOOLS_AVAILABLE,
    "config_dir": CONFIG_DIR,
    "data_dir": DATA_DIR
}

def get_package_status():
    """Get current package status and availability."""
    return PACKAGE_STATUS.copy()

def print_package_info():
    """Print package information and status."""
    print(f"StructBioReasoner v{__version__}")
    print(f"Description: {__description__}")
    print(f"Jnana Available: {JNANA_AVAILABLE}")
    print("Tool Availability:")
    for tool, available in TOOLS_AVAILABLE.items():
        status = "✓" if available else "✗"
        print(f"  {status} {tool}")
    print(f"Config Directory: {CONFIG_DIR}")
    print(f"Data Directory: {DATA_DIR}")

# Convenience function for quick setup
def quick_setup(config_path=None, enable_tools=None, **kwargs):
    """
    Quick setup function for StructBioReasoner.
    
    Args:
        config_path: Path to configuration file
        enable_tools: List of tools to enable
        **kwargs: Additional configuration options
    
    Returns:
        ProteinEngineeringSystem instance
    """
    if not JNANA_AVAILABLE:
        raise ImportError("Jnana framework is required but not available")
    
    config_path = config_path or DEFAULT_CONFIG["protein_config_path"]
    enable_tools = enable_tools or DEFAULT_CONFIG["enable_tools"]
    
    return ProteinEngineeringSystem(
        config_path=config_path,
        enable_tools=enable_tools,
        **kwargs
    )
