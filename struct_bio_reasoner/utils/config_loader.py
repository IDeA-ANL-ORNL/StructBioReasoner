"""
Configuration loader for StructBioReasoner.

This module handles loading and validation of configuration files
for the protein engineering system.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union


def load_protein_config(config_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Load protein engineering configuration from YAML file.

    Args:
        config_path: Path to configuration file

    Returns:
        Configuration dictionary

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid YAML
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Validate configuration
        validated_config = validate_config(config)

        # Expand environment variables
        expanded_config = expand_environment_variables(validated_config)

        logging.info(f"Configuration loaded from {config_path}")
        return expanded_config

    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Invalid YAML in configuration file: {e}")


def load_binder_config(config_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Load binder design configuration from YAML file.

    Args:
        config_path: Path to configuration file

    Returns:
        Configuration dictionary

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid YAML
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Validate configuration
        validated_config = validate_config(config)

        # Expand environment variables
        expanded_config = expand_environment_variables(validated_config)

        logging.info(f"Binder configuration loaded from {config_path}")
        return expanded_config

    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Invalid YAML in configuration file: {e}")


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate configuration structure and provide defaults.
    
    Args:
        config: Raw configuration dictionary
        
    Returns:
        Validated configuration with defaults
    """
    # Default configuration structure
    default_config = {
        "jnana": {
            "config_path": "../Jnana/config/models.yaml",
            "enable_protognosis": True,
            "enable_biomni": False,  # Disabled by default
            "enable_wisteria_ui": True
        },
        "protein_engineering": {
            "default_analysis": {
                "include_structure": True,
                "include_sequence": True,
                "include_evolution": True,
                "include_energetics": True,
                "include_dynamics": False
            },
            "mutation_design": {
                "max_mutations_per_hypothesis": 5,
                "consider_conservative_mutations": True,
                "include_combinatorial_designs": False,
                "energy_cutoff_kcal_mol": 2.0
            },
            "validation": {
                "min_sequence_identity": 0.3,
                "max_rmsd_threshold": 3.0,
                "min_confidence_score": 0.6
            }
        },
        "knowledge_sources": {
            "databases": {
                "pdb": {"enabled": True},
                "uniprot": {"enabled": True},
                "alphafold_db": {"enabled": True}
            },
            "literature": {
                "adaparse": {"enabled": False},
                "hiperrag": {"enabled": False}
            },
            "knowledge_graph": {
                "enabled": False,
                "database_type": "neo4j"
            }
        },
        "tools": {
            "pymol": {"enabled": True},
            "biopython": {"enabled": True},
            "rosetta": {"enabled": False},
            "alphafold": {"enabled": False},
            "esm": {"enabled": True}
        },
        "agents": {
            "structural_analysis": {"enabled": True},
            "evolutionary_conservation": {"enabled": True},
            "energetic_analysis": {"enabled": True},
            "mutation_design": {"enabled": True},
            "literature_analysis": {"enabled": True}
        },
        "performance": {
            "max_concurrent_agents": 5,
            "max_memory_gb": 16,
            "enable_gpu_acceleration": True
        },
        "logging": {
            "level": "INFO",
            "format": "structured"
        }
    }
    
    # Merge with defaults
    merged_config = merge_configs(default_config, config)
    
    # Validate specific sections
    validate_jnana_config(merged_config.get("jnana", {}))
    validate_tools_config(merged_config.get("tools", {}))
    validate_agents_config(merged_config.get("agents", {}))
    
    return merged_config


def merge_configs(default: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge user configuration with defaults.
    
    Args:
        default: Default configuration
        user: User configuration
        
    Returns:
        Merged configuration
    """
    merged = default.copy()
    
    for key, value in user.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_configs(merged[key], value)
        else:
            merged[key] = value
    
    return merged


def validate_jnana_config(jnana_config: Dict[str, Any]):
    """Validate Jnana integration configuration."""
    config_path = jnana_config.get("config_path")
    if config_path and not Path(config_path).exists():
        logging.warning(f"Jnana config path does not exist: {config_path}")


def validate_tools_config(tools_config: Dict[str, Any]):
    """Validate tools configuration."""
    # Check if at least one analysis tool is enabled
    analysis_tools = ["pymol", "biopython", "rosetta", "alphafold"]
    enabled_tools = [tool for tool in analysis_tools if tools_config.get(tool, {}).get("enabled", False)]
    
    if not enabled_tools:
        logging.warning("No analysis tools enabled - functionality will be limited")
    
    # Validate tool-specific configurations
    if tools_config.get("rosetta", {}).get("enabled", False):
        rosetta_path = tools_config.get("rosetta", {}).get("executable_path")
        if rosetta_path and not Path(rosetta_path).exists():
            logging.warning(f"Rosetta executable path does not exist: {rosetta_path}")
    
    if tools_config.get("alphafold", {}).get("enabled", False):
        alphafold_models = tools_config.get("alphafold", {}).get("model_path")
        if alphafold_models and not Path(alphafold_models).exists():
            logging.warning(f"AlphaFold model path does not exist: {alphafold_models}")


def validate_agents_config(agents_config: Dict[str, Any]):
    """Validate agents configuration."""
    # Check if at least one agent is enabled
    enabled_agents = [agent for agent, config in agents_config.items() 
                     if config.get("enabled", False)]
    
    if not enabled_agents:
        logging.warning("No agents enabled - system will have limited functionality")


def expand_environment_variables(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expand environment variables in configuration values.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Configuration with expanded environment variables
    """
    def expand_value(value):
        if isinstance(value, str):
            return os.path.expandvars(value)
        elif isinstance(value, dict):
            return {k: expand_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [expand_value(item) for item in value]
        else:
            return value
    
    return expand_value(config)


def get_config_template() -> str:
    """
    Get a template configuration file content.
    
    Returns:
        YAML configuration template as string
    """
    template = """# StructBioReasoner Configuration Template
# Copy this file to protein_config.yaml and customize as needed

# Jnana Integration Settings
jnana:
  config_path: "../Jnana/config/models.yaml"
  enable_protognosis: true
  enable_biomni: false  # Disabled by default
  enable_wisteria_ui: true

# Protein Engineering Settings
protein_engineering:
  default_analysis:
    include_structure: true
    include_sequence: true
    include_evolution: true
    include_energetics: true
    include_dynamics: false

  mutation_design:
    max_mutations_per_hypothesis: 5
    consider_conservative_mutations: true
    include_combinatorial_designs: false
    energy_cutoff_kcal_mol: 2.0

  validation:
    min_sequence_identity: 0.3
    max_rmsd_threshold: 3.0
    min_confidence_score: 0.6

# Knowledge Sources
knowledge_sources:
  databases:
    pdb:
      enabled: true
      api_url: "https://www.rcsb.org/pdb/rest/webservices"
      local_cache: "./data/pdb_cache"
    
    uniprot:
      enabled: true
      api_url: "https://www.uniprot.org/uniprot/"
      local_cache: "./data/uniprot_cache"
    
    alphafold_db:
      enabled: true
      api_url: "https://alphafold.ebi.ac.uk/api/"
      local_cache: "./data/alphafold_cache"

  literature:
    adaparse:
      enabled: false  # Set to true if AdaParse is available
      pdf_directory: "./data/literature/pdfs"
      output_directory: "./data/literature/parsed"
    
    hiperrag:
      enabled: false  # Set to true if HiPerRAG is available
      index_path: "./data/literature/hiperrag_index"

  knowledge_graph:
    enabled: false  # Set to true to enable Neo4j knowledge graph
    database_type: "neo4j"
    connection:
      uri: "bolt://localhost:7687"
      username: "neo4j"
      password: "${NEO4J_PASSWORD}"

# Computational Tools
tools:
  pymol:
    enabled: true
    headless_mode: true
    ray_trace_quality: 2

  biopython:
    enabled: true
    pdb_parser: "PDBParser"
    sequence_alignment_tool: "muscle"

  rosetta:
    enabled: false  # Set to true if Rosetta license available
    executable_path: "/path/to/rosetta/bin"
    score_function: "ref2015"

  alphafold:
    enabled: false  # Set to true if AlphaFold installed locally
    model_path: "/path/to/alphafold/models"

  esm:
    enabled: true
    model_name: "esm2_t33_650M_UR50D"
    device: "auto"

# Agent Configuration
agents:
  structural_analysis:
    enabled: true
    capabilities:
      - "active_site_identification"
      - "cavity_analysis"
      - "interface_prediction"
    confidence_threshold: 0.7

  evolutionary_conservation:
    enabled: true
    capabilities:
      - "msa_generation"
      - "conservation_scoring"
      - "coevolution_analysis"
    min_sequences_for_msa: 50

  energetic_analysis:
    enabled: true
    capabilities:
      - "stability_prediction"
      - "binding_affinity_estimation"
    energy_units: "kcal/mol"

  mutation_design:
    enabled: true
    capabilities:
      - "rational_mutation_proposal"
      - "library_design"
    max_mutations_per_round: 10

# Performance Settings
performance:
  max_concurrent_agents: 5
  max_memory_gb: 16
  enable_gpu_acceleration: true

# Logging Configuration
logging:
  level: "INFO"
  format: "structured"
  output_file: "./logs/struct_bio_reasoner.log"
"""
    return template


def create_config_file(output_path: Union[str, Path], template: bool = True):
    """
    Create a configuration file.
    
    Args:
        output_path: Path where to create the config file
        template: Whether to create a template file
    """
    output_path = Path(output_path)
    
    if template:
        content = get_config_template()
    else:
        # Create minimal working config
        content = """# StructBioReasoner Configuration
jnana:
  config_path: "../Jnana/config/models.yaml"

tools:
  pymol:
    enabled: true
  biopython:
    enabled: true

agents:
  structural_analysis:
    enabled: true
  evolutionary_conservation:
    enabled: true
"""
    
    # Create directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        f.write(content)
    
    logging.info(f"Configuration file created: {output_path}")


if __name__ == "__main__":
    # Create example configuration file
    create_config_file("config/protein_config.example.yaml", template=True)
