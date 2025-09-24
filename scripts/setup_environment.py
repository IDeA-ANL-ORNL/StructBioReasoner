#!/usr/bin/env python3
"""
Environment setup script for StructBioReasoner.

This script helps set up the development and runtime environment
for the protein engineering system.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import List, Dict, Any


def check_python_version():
    """Check if Python version is compatible."""
    print("Checking Python version...")
    
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        print(f"Current version: {sys.version}")
        return False
    
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True


def check_jnana_availability():
    """Check if Jnana framework is available."""
    print("Checking Jnana availability...")
    
    jnana_path = Path(__file__).parent.parent.parent / "Jnana"
    
    if not jnana_path.exists():
        print("❌ Jnana directory not found")
        print(f"Expected location: {jnana_path}")
        print("Please ensure Jnana is cloned in the parent directory")
        return False
    
    # Check if Jnana has the required files
    required_files = [
        "jnana/__init__.py",
        "jnana/core/jnana_system.py",
        "jnana/data/unified_hypothesis.py",
        "config/models.yaml"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not (jnana_path / file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ Jnana installation incomplete")
        print("Missing files:")
        for file_path in missing_files:
            print(f"  - {file_path}")
        return False
    
    print("✅ Jnana framework found")
    return True


def install_dependencies():
    """Install Python dependencies."""
    print("Installing Python dependencies...")
    
    # Try minimal requirements first, fall back to full requirements
    requirements_file = Path(__file__).parent.parent / "requirements_minimal.txt"
    if not requirements_file.exists():
        requirements_file = Path(__file__).parent.parent / "requirements.txt"
    
    if not requirements_file.exists():
        print("❌ requirements.txt not found")
        return False
    
    try:
        subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
        ], check=True)
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False


def check_optional_tools():
    """Check availability of optional tools."""
    print("Checking optional tools...")
    
    tools_status = {}
    
    # Check PyMOL
    try:
        import pymol
        tools_status["pymol"] = True
        print("✅ PyMOL available")
    except ImportError:
        tools_status["pymol"] = False
        print("⚠️  PyMOL not available (optional)")
    
    # Check BioPython
    try:
        import Bio
        tools_status["biopython"] = True
        print("✅ BioPython available")
    except ImportError:
        tools_status["biopython"] = False
        print("❌ BioPython not available (required)")
    
    # Check ESM
    try:
        import esm
        tools_status["esm"] = True
        print("✅ ESM (Facebook protein models) available")
    except ImportError:
        tools_status["esm"] = False
        print("⚠️  ESM not available (optional)")
    
    # Check Neo4j
    try:
        import neo4j
        tools_status["neo4j"] = True
        print("✅ Neo4j driver available")
    except ImportError:
        tools_status["neo4j"] = False
        print("⚠️  Neo4j driver not available (optional)")
    
    return tools_status


def create_directories():
    """Create necessary directories."""
    print("Creating directories...")
    
    base_dir = Path(__file__).parent.parent
    directories = [
        "data",
        "data/pdb_cache",
        "data/uniprot_cache",
        "data/alphafold_cache",
        "data/literature",
        "data/literature/pdfs",
        "data/literature/parsed",
        "data/knowledge_graph",
        "logs",
        "output",
        "temp"
    ]
    
    for dir_path in directories:
        full_path = base_dir / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        print(f"✅ Created directory: {dir_path}")
    
    return True


def create_config_files():
    """Create configuration files if they don't exist."""
    print("Setting up configuration files...")
    
    base_dir = Path(__file__).parent.parent
    config_dir = base_dir / "config"
    
    # Create config directory
    config_dir.mkdir(exist_ok=True)
    
    # Create example configuration if it doesn't exist
    example_config = config_dir / "protein_config.example.yaml"
    if not example_config.exists():
        try:
            # Add the project root to Python path for imports
            sys.path.insert(0, str(base_dir))
            from struct_bio_reasoner.utils.config_loader import create_config_file
            create_config_file(example_config, template=True)
            print("✅ Created example configuration file")
        except ImportError as e:
            print(f"⚠️  Could not create example configuration (import error): {e}")
            # Create a basic config manually
            _create_basic_config(example_config, template=True)

    # Create default configuration if it doesn't exist
    default_config = config_dir / "protein_config.yaml"
    if not default_config.exists():
        try:
            # Add the project root to Python path for imports
            sys.path.insert(0, str(base_dir))
            from struct_bio_reasoner.utils.config_loader import create_config_file
            create_config_file(default_config, template=False)
            print("✅ Created default configuration file")
        except ImportError as e:
            print(f"⚠️  Could not create default configuration (import error): {e}")
            # Create a basic config manually
            _create_basic_config(default_config, template=False)
    
    return True


def _create_basic_config(config_path: Path, template: bool = False):
    """Create a basic configuration file manually."""
    if template:
        content = """# StructBioReasoner Configuration Template
jnana:
  config_path: "../Jnana/config/models.yaml"
  enable_protognosis: true
  enable_biomni: true

tools:
  pymol:
    enabled: true
    headless_mode: true
  biopython:
    enabled: true

agents:
  structural_analysis:
    enabled: true
  evolutionary_conservation:
    enabled: true
  energetic_analysis:
    enabled: true
  mutation_design:
    enabled: true

logging:
  level: "INFO"
"""
    else:
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
"""

    with open(config_path, 'w') as f:
        f.write(content)

    print(f"✅ Created basic configuration file: {config_path.name}")


def setup_environment_variables():
    """Setup environment variables."""
    print("Setting up environment variables...")
    
    base_dir = Path(__file__).parent.parent
    
    # Create .env file if it doesn't exist
    env_file = base_dir / ".env"
    if not env_file.exists():
        env_content = f"""# StructBioReasoner Environment Variables

# Paths
STRUCT_BIO_ROOT={base_dir}
STRUCT_BIO_CONFIG={base_dir}/config/protein_config.yaml
STRUCT_BIO_DATA={base_dir}/data
STRUCT_BIO_LOGS={base_dir}/logs

# API Keys (set these with your actual keys)
# OPENAI_API_KEY=your_openai_key_here
# ANTHROPIC_API_KEY=your_anthropic_key_here
# NEO4J_PASSWORD=your_neo4j_password_here

# Optional tool paths
# ROSETTA_PATH=/path/to/rosetta
# ALPHAFOLD_PATH=/path/to/alphafold
"""
        
        with open(env_file, 'w') as f:
            f.write(env_content)
        
        print("✅ Created .env file")
        print("⚠️  Please edit .env file to add your API keys")
    else:
        print("✅ .env file already exists")
    
    return True


def run_basic_tests():
    """Run basic functionality tests."""
    print("Running basic tests...")
    
    try:
        # Test imports
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from struct_bio_reasoner import get_package_status
        status = get_package_status()
        
        if status["jnana_available"]:
            print("✅ Jnana integration test passed")
        else:
            print("❌ Jnana integration test failed")
            return False
        
        print("✅ Basic tests passed")
        return True
        
    except Exception as e:
        print(f"❌ Basic tests failed: {e}")
        return False


def main():
    """Main setup function."""
    print("🧬 StructBioReasoner Environment Setup")
    print("=" * 50)
    
    success = True
    
    # Check Python version
    if not check_python_version():
        success = False
    
    # Check Jnana availability
    if not check_jnana_availability():
        success = False
        print("\n📋 To fix Jnana issues:")
        print("1. Clone Jnana repository in the parent directory")
        print("2. Ensure Jnana is properly configured")
    
    # Install dependencies
    if success and not install_dependencies():
        success = False
    
    # Check optional tools
    tools_status = check_optional_tools()
    if not tools_status.get("biopython", False):
        success = False
    
    # Create directories
    if not create_directories():
        success = False
    
    # Create configuration files
    if not create_config_files():
        success = False
    
    # Setup environment variables
    if not setup_environment_variables():
        success = False
    
    # Run basic tests
    if success and not run_basic_tests():
        success = False
    
    print("\n" + "=" * 50)
    if success:
        print("✅ Setup completed successfully!")
        print("\n📋 Next steps:")
        print("1. Edit config/protein_config.yaml for your needs")
        print("2. Add API keys to .env file")
        print("3. Run: python struct_bio_reasoner.py --mode status")
    else:
        print("❌ Setup completed with errors")
        print("\n📋 Please fix the issues above and run setup again")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
