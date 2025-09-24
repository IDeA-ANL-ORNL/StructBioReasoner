#!/usr/bin/env python3
"""
Setup verification script for StructBioReasoner.

This script verifies that the protein engineering system is properly
configured and ready for use.
"""

import sys
import asyncio
from pathlib import Path
from typing import Dict, List, Any


def verify_file_structure():
    """Verify that all required files and directories exist."""
    print("Verifying file structure...")
    
    base_dir = Path(__file__).parent.parent
    
    required_files = [
        "struct_bio_reasoner.py",
        "struct_bio_reasoner/__init__.py",
        "struct_bio_reasoner/core/protein_system.py",
        "struct_bio_reasoner/data/protein_hypothesis.py",
        "struct_bio_reasoner/data/mutation_model.py",
        "struct_bio_reasoner/utils/config_loader.py",
        "config/protein_config.yaml",
        "requirements.txt",
        "README.md"
    ]
    
    required_dirs = [
        "struct_bio_reasoner",
        "struct_bio_reasoner/core",
        "struct_bio_reasoner/data",
        "struct_bio_reasoner/agents",
        "struct_bio_reasoner/tools",
        "struct_bio_reasoner/utils",
        "config",
        "data",
        "scripts"
    ]
    
    missing_files = []
    missing_dirs = []
    
    for file_path in required_files:
        if not (base_dir / file_path).exists():
            missing_files.append(file_path)
    
    for dir_path in required_dirs:
        if not (base_dir / dir_path).exists():
            missing_dirs.append(dir_path)
    
    if missing_files or missing_dirs:
        print("❌ File structure verification failed")
        if missing_files:
            print("Missing files:")
            for file_path in missing_files:
                print(f"  - {file_path}")
        if missing_dirs:
            print("Missing directories:")
            for dir_path in missing_dirs:
                print(f"  - {dir_path}")
        return False
    
    print("✅ File structure verified")
    return True


def verify_imports():
    """Verify that all required modules can be imported."""
    print("Verifying imports...")
    
    # Add the project root to Python path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    import_tests = [
        ("struct_bio_reasoner", "Main package"),
        ("struct_bio_reasoner.core.protein_system", "Core system"),
        ("struct_bio_reasoner.data.protein_hypothesis", "Data models"),
        ("struct_bio_reasoner.utils.config_loader", "Configuration loader")
    ]
    
    failed_imports = []
    
    for module_name, description in import_tests:
        try:
            __import__(module_name)
            print(f"✅ {description}: {module_name}")
        except ImportError as e:
            print(f"❌ {description}: {module_name} - {e}")
            failed_imports.append((module_name, str(e)))
    
    if failed_imports:
        print("❌ Import verification failed")
        return False
    
    print("✅ All imports successful")
    return True


def verify_jnana_integration():
    """Verify Jnana integration."""
    print("Verifying Jnana integration...")
    
    try:
        from struct_bio_reasoner import get_package_status
        status = get_package_status()
        
        if not status["jnana_available"]:
            print("❌ Jnana not available")
            print("Please ensure Jnana is properly installed and configured")
            return False
        
        print("✅ Jnana integration verified")
        return True
        
    except Exception as e:
        print(f"❌ Jnana integration failed: {e}")
        return False


def verify_configuration():
    """Verify configuration files."""
    print("Verifying configuration...")
    
    try:
        from struct_bio_reasoner.utils.config_loader import load_protein_config
        
        config_path = Path(__file__).parent.parent / "config" / "protein_config.yaml"
        
        if not config_path.exists():
            print("❌ Configuration file not found")
            return False
        
        config = load_protein_config(config_path)
        
        # Check required sections
        required_sections = ["jnana", "tools", "agents"]
        missing_sections = []
        
        for section in required_sections:
            if section not in config:
                missing_sections.append(section)
        
        if missing_sections:
            print("❌ Configuration missing required sections:")
            for section in missing_sections:
                print(f"  - {section}")
            return False
        
        print("✅ Configuration verified")
        return True
        
    except Exception as e:
        print(f"❌ Configuration verification failed: {e}")
        return False


def verify_dependencies():
    """Verify that required dependencies are available."""
    print("Verifying dependencies...")
    
    core_dependencies = [
        ("yaml", "PyYAML"),
        ("pathlib", "pathlib (built-in)"),
        ("asyncio", "asyncio (built-in)"),
        ("logging", "logging (built-in)")
    ]
    
    optional_dependencies = [
        ("Bio", "BioPython"),
        ("pymol", "PyMOL"),
        ("neo4j", "Neo4j driver"),
        ("esm", "ESM (Facebook protein models)")
    ]
    
    failed_core = []
    available_optional = []
    
    # Check core dependencies
    for module_name, description in core_dependencies:
        try:
            __import__(module_name)
            print(f"✅ {description}")
        except ImportError:
            print(f"❌ {description}")
            failed_core.append(module_name)
    
    # Check optional dependencies
    for module_name, description in optional_dependencies:
        try:
            __import__(module_name)
            print(f"✅ {description} (optional)")
            available_optional.append(module_name)
        except ImportError:
            print(f"⚠️  {description} (optional, not available)")
    
    if failed_core:
        print("❌ Core dependencies missing")
        return False
    
    if not available_optional:
        print("⚠️  No optional dependencies available - functionality will be limited")
    
    print("✅ Dependencies verified")
    return True


async def verify_system_initialization():
    """Verify that the system can be initialized."""
    print("Verifying system initialization...")
    
    try:
        from struct_bio_reasoner import ProteinEngineeringSystem
        
        # Try to create system instance
        system = ProteinEngineeringSystem(
            config_path="config/protein_config.yaml",
            enable_tools=["biopython"],  # Use minimal tools for testing
            enable_agents=["structural"],
            knowledge_graph=False,  # Disable for testing
            literature_processing=False  # Disable for testing
        )
        
        print("✅ System instance created")
        
        # Try to get status
        status = system.get_protein_system_status()
        print(f"✅ System status retrieved: {len(status)} status fields")
        
        return True
        
    except Exception as e:
        print(f"❌ System initialization failed: {e}")
        return False


def verify_command_line_interface():
    """Verify that the command-line interface works."""
    print("Verifying command-line interface...")
    
    try:
        import subprocess
        
        script_path = Path(__file__).parent.parent / "struct_bio_reasoner.py"
        
        # Test --version flag
        result = subprocess.run([
            sys.executable, str(script_path), "--version"
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("✅ Command-line interface working")
            return True
        else:
            print(f"❌ Command-line interface failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Command-line interface verification failed: {e}")
        return False


async def main():
    """Main verification function."""
    print("🧬 StructBioReasoner Setup Verification")
    print("=" * 50)
    
    verification_tests = [
        ("File Structure", verify_file_structure),
        ("Imports", verify_imports),
        ("Jnana Integration", verify_jnana_integration),
        ("Configuration", verify_configuration),
        ("Dependencies", verify_dependencies),
        ("System Initialization", verify_system_initialization),
        ("Command-line Interface", verify_command_line_interface)
    ]
    
    results = {}
    overall_success = True
    
    for test_name, test_func in verification_tests:
        print(f"\n--- {test_name} ---")
        try:
            if asyncio.iscoroutinefunction(test_func):
                success = await test_func()
            else:
                success = test_func()
            
            results[test_name] = success
            if not success:
                overall_success = False
                
        except Exception as e:
            print(f"❌ {test_name} verification failed with exception: {e}")
            results[test_name] = False
            overall_success = False
    
    # Summary
    print("\n" + "=" * 50)
    print("VERIFICATION SUMMARY")
    print("=" * 50)
    
    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print("\n" + "=" * 50)
    if overall_success:
        print("🎉 ALL VERIFICATIONS PASSED!")
        print("\nStructBioReasoner is ready for use.")
        print("\nNext steps:")
        print("1. Run: python struct_bio_reasoner.py --mode status")
        print("2. Try: python struct_bio_reasoner.py --mode interactive --goal 'Test hypothesis'")
    else:
        print("❌ SOME VERIFICATIONS FAILED")
        print("\nPlease fix the issues above before using StructBioReasoner.")
        print("You may need to:")
        print("1. Run the setup script: python scripts/setup_environment.py")
        print("2. Install missing dependencies")
        print("3. Configure Jnana integration")
    
    return overall_success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
